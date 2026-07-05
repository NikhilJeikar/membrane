"""Optional Firecrawl client for scraping pages (self-hosted Podman/Docker)."""

from __future__ import annotations

import httpx

from membrane.config import FirecrawlConfig


class FirecrawlError(RuntimeError):
    pass


def _normalize_base_url(url: str) -> str:
    return url.rstrip("/")


def _extract_markdown(payload: dict) -> str:
    data = payload.get("data")
    if isinstance(data, dict):
        markdown = data.get("markdown")
        if isinstance(markdown, str):
            return markdown
    markdown = payload.get("markdown")
    if isinstance(markdown, str):
        return markdown
    return ""


def scrape_page(url: str, config: FirecrawlConfig) -> str:
    """Scrape a URL via Firecrawl and return markdown text."""
    if not config.enabled:
        return ""

    base = _normalize_base_url(config.base_url)
    body = {"url": url, "formats": ["markdown"]}
    headers = {"Content-Type": "application/json"}
    if config.api_key.strip():
        headers["Authorization"] = f"Bearer {config.api_key.strip()}"

    last_error: Exception | None = None
    try:
        with httpx.Client(timeout=config.timeout_seconds) as client:
            for path in ("/v1/scrape", "/v2/scrape"):
                try:
                    response = client.post(f"{base}{path}", json=body, headers=headers)
                    if response.status_code == 404:
                        continue
                    response.raise_for_status()
                    payload = response.json()
                    if payload.get("success") is False:
                        detail = payload.get("error") or payload.get("message") or "unknown error"
                        raise FirecrawlError(str(detail))
                    text = _extract_markdown(payload)
                    if not text.strip():
                        continue
                    if len(text) > config.max_chars:
                        text = text[: config.max_chars - 3].rstrip() + "..."
                    return text
                except httpx.HTTPError as exc:
                    last_error = exc
    except httpx.HTTPError as exc:
        raise FirecrawlError(f"firecrawl scrape failed: {exc}") from exc

    if last_error is not None:
        raise FirecrawlError(f"firecrawl scrape failed: {last_error}") from last_error
    raise FirecrawlError("firecrawl scrape returned no content")
