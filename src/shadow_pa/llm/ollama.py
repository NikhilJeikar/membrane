"""Local LLM client (Ollama)."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from shadow_pa.config import LLMConfig
from shadow_pa.utils.parallel import cpu_count


class OllamaError(RuntimeError):
    pass


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

        last_error: Exception | None = None
        attempts = self.config.max_retries + 1
        timeout = self._httpx_timeout()

        for attempt in range(attempts):
            try:
                with httpx.Client(timeout=timeout) as client:
                    response = client.post(f"{self.base_url}/api/chat", json=payload)
                    response.raise_for_status()
                    data = response.json()
                    return data["message"]["content"]
            except httpx.HTTPError as exc:
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

    def parse_json_response(self, text: str) -> Any:
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        return json.loads(text)
