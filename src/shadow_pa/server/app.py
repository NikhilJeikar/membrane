"""Local HTTP ingest server for email, calendar, and search history."""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from shadow_pa.config import PersonaConfig, Settings
from shadow_pa.ingest.lifecycle import parse_all_server_sources
from shadow_pa.ingest.server_common import save_raw_envelope
from shadow_pa.ingest.server_models import SERVER_SOURCES, ServerSource
from shadow_pa.server.auth import check_bearer_auth, resolve_server_token
from shadow_pa.server.scheduler import ParseScheduler
from shadow_pa.shadow.offline import OfflineExtractor
from shadow_pa.tracking.manifest import ManifestStore

logger = logging.getLogger(__name__)


@dataclass
class ServerState:
    settings: Settings
    persona: PersonaConfig
    token: str
    manifest: ManifestStore
    memory_store: Any
    started_at: datetime = field(default_factory=lambda: datetime.now().astimezone())
    last_parse_at: datetime | None = None
    last_parse_stats: dict[str, dict[str, int]] = field(default_factory=dict)
    ingest_counts: dict[str, int] = field(default_factory=lambda: {s: 0 for s in SERVER_SOURCES})
    lock: threading.Lock = field(default_factory=threading.Lock)


def run_parse_cycle(state: ServerState) -> dict[str, dict[str, int]]:
    results = parse_all_server_sources(state.settings, state.manifest, redact=True)
    stats = {
        source: {"processed": r.processed, "skipped": r.skipped}
        for source, r in results.items()
    }
    state.last_parse_at = datetime.now().astimezone()
    state.last_parse_stats = stats

    if state.persona.server.auto_extract:
        extractor = OfflineExtractor(store=state.memory_store)
        for source in SERVER_SOURCES:
            parsed_dir = state.settings.server_parsed_dir(source)
            method = getattr(extractor, f"extract_{source}_parsed_dir", None)
            if method:
                method(
                    parsed_dir,
                    auto_propose=True,
                    manifest=state.manifest,
                    only_new=True,
                )
    return stats


class ShadowPARequestHandler(BaseHTTPRequestHandler):
    server_state: ServerState  # set on HTTPServer subclass

    def log_message(self, format: str, *args: Any) -> None:
        logger.info("%s - %s", self.address_string(), format % args)

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any] | list[Any] | None:
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return None
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return None

    def _authorized(self) -> bool:
        return check_bearer_auth(self.headers.get("Authorization"), self.server_state.token)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/health":
            self._send_json(200, {"status": "ok"})
            return
        if path == "/v1/status":
            if not self._authorized():
                self._send_json(401, {"error": "unauthorized"})
                return
            state = self.server_state
            pending = {
                source: len(list(state.settings.server_raw_dir(source).glob("*.json")))
                for source in SERVER_SOURCES
            }
            parsed = {
                source: len(list(state.settings.server_parsed_dir(source).glob("*.jsonl")))
                for source in SERVER_SOURCES
            }
            self._send_json(
                200,
                {
                    "started_at": state.started_at.isoformat(),
                    "last_parse_at": state.last_parse_at.isoformat() if state.last_parse_at else None,
                    "last_parse_stats": state.last_parse_stats,
                    "ingest_counts": state.ingest_counts,
                    "raw_files": pending,
                    "parsed_files": parsed,
                },
            )
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if not self._authorized():
            self._send_json(401, {"error": "unauthorized"})
            return

        path = urlparse(self.path).path
        if path == "/v1/parse":
            stats = run_parse_cycle(self.server_state)
            self._send_json(200, {"parsed": stats})
            return

        for source in SERVER_SOURCES:
            if path == f"/v1/ingest/{source}":
                body = self._read_json()
                if body is None:
                    self._send_json(400, {"error": "invalid json body"})
                    return
                saved = self._save_ingest(source, body)
                self._send_json(201, {"saved": str(saved), "id": saved.stem})
                return

        self._send_json(404, {"error": "not found"})

    def _save_ingest(self, source: ServerSource, body: dict[str, Any] | list[Any]) -> Path:
        state = self.server_state
        metadata: dict[str, Any] = {}
        if isinstance(body, dict) and "metadata" in body:
            metadata = body.get("metadata") or {}
            payload = body.get("items", body)
        else:
            payload = body
        path = save_raw_envelope(
            source,
            payload,  # type: ignore[arg-type]
            state.settings.server_raw_dir(source),
            metadata=metadata,
        )
        with state.lock:
            state.ingest_counts[source] += 1
        return path


def run_server(
    settings: Settings,
    persona: PersonaConfig,
    manifest: ManifestStore,
    memory_store: Any,
    *,
    host: str | None = None,
    port: int | None = None,
    parse_interval: int | None = None,
) -> None:
    token = resolve_server_token(settings, persona)
    bind_host = host or persona.server.host
    bind_port = port or persona.server.port
    interval = parse_interval or persona.server.parse_interval_seconds

    state = ServerState(
        settings=settings,
        persona=persona,
        token=token,
        manifest=manifest,
        memory_store=memory_store,
    )

    class _Server(ThreadingHTTPServer):
        pass

    handler = ShadowPARequestHandler
    handler.server_state = state  # type: ignore[attr-defined]

    httpd = _Server((bind_host, bind_port), handler)

    def parse_job() -> None:
        stats = run_parse_cycle(state)
        logger.info("Parsed server sources: %s", stats)

    scheduler = ParseScheduler(interval, parse_job)
    scheduler.start()

    print(f"shadow-pa server listening on http://{bind_host}:{bind_port}")
    print(f"Auth token: {token}")
    print(f"Parse interval: {interval}s")
    print("Endpoints:")
    for source in SERVER_SOURCES:
        print(f"  POST /v1/ingest/{source}")
    print("  POST /v1/parse   GET /v1/status   GET /health")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server…")
    finally:
        scheduler.stop()
        httpd.server_close()
