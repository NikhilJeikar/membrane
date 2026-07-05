"""Tests for optional Firecrawl page scraping."""

from __future__ import annotations

import httpx

from membrane.config import FirecrawlConfig
from membrane.inference.firecrawl import FirecrawlError, scrape_page
from membrane.inference.websearch import (
    SearchResult,
    enrich_search_with_pages,
    fetch_page_content,
)
from membrane.inference.websearch import fetch_page_text


def test_scrape_page_v1_markdown(monkeypatch):
    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {
                "success": True,
                "data": {"markdown": "# Hello\n\nWorld content here."},
            }

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, json, headers):
            assert json["url"] == "https://example.com/page"
            assert "/v1/scrape" in url
            return FakeResponse()

    monkeypatch.setattr(httpx, "Client", FakeClient)
    config = FirecrawlConfig(enabled=True, base_url="http://localhost:3002")
    text = scrape_page("https://example.com/page", config)
    assert "Hello" in text
    assert "World content here." in text


def test_scrape_page_falls_back_to_v2(monkeypatch):
    calls: list[str] = []

    class FakeResponse:
        def __init__(self, status_code: int, payload: dict | None = None):
            self.status_code = status_code
            self._payload = payload or {}

        def json(self):
            return self._payload

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError("fail", request=None, response=self)

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, json, headers):
            calls.append(url)
            if url.endswith("/v1/scrape"):
                return FakeResponse(404)
            return FakeResponse(
                200,
                {"success": True, "data": {"markdown": "v2 markdown body"}},
            )

    monkeypatch.setattr(httpx, "Client", FakeClient)
    config = FirecrawlConfig(enabled=True)
    text = scrape_page("https://example.com", config)
    assert text == "v2 markdown body"
    assert calls[0].endswith("/v1/scrape")
    assert calls[1].endswith("/v2/scrape")


def test_scrape_page_disabled_returns_empty():
    config = FirecrawlConfig(enabled=False)
    assert scrape_page("https://example.com", config) == ""


def test_fetch_page_content_prefers_firecrawl(monkeypatch):
    config = FirecrawlConfig(enabled=True)

    monkeypatch.setattr(
        "membrane.inference.websearch.scrape_page",
        lambda url, cfg: "firecrawl markdown",
    )

    text = fetch_page_content("https://example.com", firecrawl=config)
    assert text == "firecrawl markdown"


def test_fetch_page_content_falls_back_to_httpx(monkeypatch):
    config = FirecrawlConfig(enabled=True)

    def _fail(url, cfg):
        raise FirecrawlError("down")

    class FakeResponse:
        text = "<html><body><p>fallback text</p></body></html>"

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            return FakeResponse()

    monkeypatch.setattr("membrane.inference.websearch.scrape_page", _fail)
    monkeypatch.setattr(httpx, "Client", FakeClient)
    text = fetch_page_content("https://example.com", firecrawl=config)
    assert "fallback text" in text


def test_enrich_search_with_pages(monkeypatch):
    config = FirecrawlConfig(enabled=True, scrape_in_chat=True, max_pages_in_chat=2)
    results = [
        SearchResult(title="A", url="https://a.example", snippet=""),
        SearchResult(title="B", url="https://b.example", snippet=""),
        SearchResult(title="C", url="https://c.example", snippet=""),
    ]

    monkeypatch.setattr(
        "membrane.inference.websearch.fetch_page_content",
        lambda url, **kwargs: f"content for {url}",
    )

    block = enrich_search_with_pages(results, config)
    assert "[WEB PAGE CONTENT]" in block
    assert "https://a.example" in block
    assert "https://b.example" in block
    assert "https://c.example" not in block


def test_fetch_page_text_still_works(monkeypatch):
    class FakeResponse:
        text = "<html><body><h1>Title</h1><p>Hello world</p></body></html>"

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            return FakeResponse()

    monkeypatch.setattr(httpx, "Client", FakeClient)
    text = fetch_page_text("https://example.com/page")
    assert "Hello world" in text
    assert "<p>" not in text
