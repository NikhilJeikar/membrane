"""Local LLM client (Ollama)."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from membrane.config import LLMConfig
from membrane.utils.parallel import cpu_count


class OllamaError(RuntimeError):
    pass


class OllamaModelNotFoundError(OllamaError):
    pass


@dataclass(frozen=True)
class ChatStreamChunk:
    kind: Literal["thinking", "content"]
    text: str


class OllamaClient:
    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self.base_url = config.base_url.rstrip("/")

    def _httpx_timeout(self) -> httpx.Timeout:
        read = self.config.timeout_seconds
        return httpx.Timeout(connect=15.0, read=read, write=read, pool=15.0)

    def _ollama_options(self, temperature: float | None) -> dict[str, Any]:
        options: dict[str, Any] = {
            "temperature": temperature if temperature is not None else self.config.temperature,
        }
        threads = self.config.num_threads if self.config.num_threads > 0 else cpu_count()
        options["num_thread"] = threads
        return options

    def parallel_requests(self) -> int:
        if self.config.parallel_requests > 0:
            return self.config.parallel_requests
        return 1

    def list_models(self) -> list[str]:
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                data = response.json()
                return sorted(m["name"] for m in data.get("models", []) if m.get("name"))
        except httpx.HTTPError:
            return []

    def has_model(self, model: str | None = None) -> bool:
        name = model or self.config.model
        installed = self.list_models()
        if name in installed:
            return True
        if ":" not in name:
            return any(m == name or m.startswith(f"{name}:") for m in installed)
        return False

    def _raise_for_response(self, response: httpx.Response, model: str) -> None:
        if response.status_code == 404:
            detail = ""
            try:
                detail = response.json().get("error", "")
            except (json.JSONDecodeError, AttributeError):
                detail = response.text
            if "not found" in detail.lower():
                raise OllamaModelNotFoundError(
                    f"Model '{model}' is not installed. Pull it with: ollama pull {model}"
                ) from None
        response.raise_for_status()

    def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float | None = None,
        json_mode: bool = False,
    ) -> str:
        payload: dict[str, Any] = {
            "model": model or self.config.model,
            "messages": messages,
            "stream": False,
            "options": self._ollama_options(temperature),
        }
        if json_mode:
            payload["format"] = "json"

        model_name = payload["model"]
        last_error: Exception | None = None
        attempts = self.config.max_retries + 1
        timeout = self._httpx_timeout()

        for attempt in range(attempts):
            try:
                with httpx.Client(timeout=timeout) as client:
                    response = client.post(f"{self.base_url}/api/chat", json=payload)
                    self._raise_for_response(response, model_name)
                    data = response.json()
                    return data["message"]["content"]
            except OllamaModelNotFoundError:
                raise
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt < attempts - 1:
                    time.sleep(min(2**attempt, 8))

        raise OllamaError(
            f"Ollama request failed after {attempts} attempt(s): {last_error}"
        ) from last_error

    def chat_stream(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float | None = None,
        *,
        think: bool | None = None,
    ) -> Iterator[ChatStreamChunk]:
        """Yield thinking and content chunks as they arrive from Ollama."""
        use_think = self.config.thinking_enabled if think is None else think
        payload: dict[str, Any] = {
            "model": model or self.config.model,
            "messages": messages,
            "stream": True,
            "options": self._ollama_options(temperature),
        }
        if use_think:
            payload["think"] = True
        model_name = payload["model"]
        last_error: Exception | None = None
        attempts = self.config.max_retries + 1
        timeout = self._httpx_timeout()

        for attempt in range(attempts):
            started = False
            try:
                with httpx.Client(timeout=timeout) as client:
                    with client.stream(
                        "POST", f"{self.base_url}/api/chat", json=payload
                    ) as response:
                        if response.status_code >= 400:
                            response.read()
                            self._raise_for_response(response, model_name)
                        for line in response.iter_lines():
                            if not line.strip():
                                continue
                            data = json.loads(line)
                            if data.get("error"):
                                raise OllamaError(data["error"])
                            message = data.get("message", {})
                            thinking_chunk = message.get("thinking", "")
                            content_chunk = message.get("content", "")
                            if thinking_chunk:
                                started = True
                                yield ChatStreamChunk("thinking", thinking_chunk)
                            if content_chunk:
                                started = True
                                yield ChatStreamChunk("content", content_chunk)
                            if data.get("done"):
                                return
                return
            except OllamaModelNotFoundError:
                raise
            except httpx.HTTPError as exc:
                # Once tokens were emitted, retrying would duplicate output.
                if started:
                    raise OllamaError(f"Ollama stream interrupted: {exc}") from exc
                last_error = exc
                if attempt < attempts - 1:
                    time.sleep(min(2**attempt, 8))

        raise OllamaError(
            f"Ollama request failed after {attempts} attempt(s): {last_error}"
        ) from last_error

    def health_check(self) -> bool:
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{self.base_url}/api/tags")
                return response.status_code == 200
        except httpx.HTTPError:
            return False

    def model_ready(self, model: str | None = None) -> bool:
        return self.health_check() and self.has_model(model)

    def parse_json_response(self, text: str) -> Any:
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        return json.loads(text)
