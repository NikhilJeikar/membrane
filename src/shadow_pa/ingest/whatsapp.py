"""WhatsApp chat export parser."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from shadow_pa.memory.models import WhatsAppMessage
from shadow_pa.utils.redact import redact_text

# [05/07/2026, 10:32:15] Name: message
# [05/07/2026, 10:32:15 AM] Name: message  (12h)
LINE_RE = re.compile(
    r"^\[(?P<date>\d{1,2}/\d{1,2}/\d{2,4}),\s*(?P<time>\d{1,2}:\d{2}(?::\d{2})?(?:\s*[APMapm]{2})?)\]\s"
    r"(?P<sender>[^:]+):\s(?P<text>.*)$"
)

SYSTEM_MARKERS = (
    "Messages and calls are end-to-end encrypted",
    "created group",
    "changed the subject",
    "changed this group's icon",
    "You deleted this message",
    "<Media omitted>",
    " omitted",
)


def _parse_timestamp(date_part: str, time_part: str) -> datetime:
    date_part = date_part.strip()
    time_part = time_part.strip().upper()
    for fmt in (
        "%d/%m/%Y %I:%M:%S %p",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %I:%M %p",
        "%d/%m/%Y %H:%M",
        "%m/%d/%Y %I:%M:%S %p",
        "%m/%d/%Y %H:%M:%S",
    ):
        try:
            return datetime.strptime(f"{date_part} {time_part}", fmt)
        except ValueError:
            continue
    raise ValueError(f"Could not parse timestamp: {date_part} {time_part}")


def _is_system_message(text: str) -> bool:
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in SYSTEM_MARKERS)


def parse_whatsapp_export(
    content: str,
    self_names: list[str] | None = None,
    redact: bool = True,
) -> list[WhatsAppMessage]:
    self_names_lower = {n.lower() for n in (self_names or ["You"])}
    messages: list[WhatsAppMessage] = []
    current: WhatsAppMessage | None = None

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = LINE_RE.match(line)
        if match:
            text = match.group("text")
            if _is_system_message(text):
                current = None
                continue
            if redact:
                text = redact_text(text)
            sender = match.group("sender").strip()
            ts = _parse_timestamp(match.group("date"), match.group("time"))
            current = WhatsAppMessage(
                timestamp=ts,
                sender=sender,
                text=text,
                is_self=sender.lower() in self_names_lower or sender.lower() == "you",
            )
            messages.append(current)
        elif current is not None:
            extra = redact_text(line) if redact else line
            current.text = f"{current.text}\n{extra}"

    return messages


def ingest_whatsapp_file(
    source: Path,
    output_dir: Path,
    self_names: list[str] | None = None,
    redact: bool = True,
    manifest: object | None = None,
    force: bool = False,
) -> tuple[Path | None, bool]:
    """Returns (output path or None, was_skipped)."""
    from shadow_pa.tracking.manifest import ManifestStore

    store: ManifestStore | None = manifest  # type: ignore[assignment]
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{source.stem}.jsonl"

    if store and not store.needs_ingest("whatsapp", source, out_path, force=force):
        return None, True

    content = source.read_text(encoding="utf-8", errors="replace")
    messages = parse_whatsapp_export(content, self_names=self_names, redact=redact)
    with out_path.open("w", encoding="utf-8") as f:
        for msg in messages:
            f.write(json.dumps(msg.model_dump(mode="json")) + "\n")
    if store:
        store.record_ingest("whatsapp", source, out_path)
    return out_path, False


def load_parsed_messages(path: Path) -> list[WhatsAppMessage]:
    messages: list[WhatsAppMessage] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            messages.append(WhatsAppMessage.model_validate(json.loads(line)))
    return messages


def chunk_messages(
    messages: list[WhatsAppMessage],
    chunk_size: int = 40,
    self_only: bool = False,
) -> list[list[WhatsAppMessage]]:
    filtered = [m for m in messages if not self_only or m.is_self]
    return [filtered[i : i + chunk_size] for i in range(0, len(filtered), chunk_size)]


def format_chunk_for_extraction(chunk: list[WhatsAppMessage]) -> str:
    lines: list[str] = []
    for msg in chunk:
        role = "SELF" if msg.is_self else "OTHER"
        ts = msg.timestamp.strftime("%Y-%m-%d %H:%M")
        lines.append(f"[{ts}] {role} ({msg.sender}): {msg.text}")
    return "\n".join(lines)
