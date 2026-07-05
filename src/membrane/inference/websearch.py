"""Optional web search step for chat (DuckDuckGo, no API key).

Flow: the model first decides whether the latest user message needs fresh
web information and emits a search query. Membrane fetches DuckDuckGo
results and injects them as an extra system message before the final reply.
"""

from __future__ import annotations

import html as html_lib
import json
import re
from datetime import date
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from pydantic import BaseModel

from membrane.config import FirecrawlConfig, WebSearchConfig
from membrane.inference.firecrawl import FirecrawlError, scrape_page
from membrane.llm.ollama import OllamaClient, OllamaError
from membrane.memory.models import ChatTurn

SEARCH_ENDPOINT = "https://html.duckduckgo.com/html/"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/127.0"
)

_RESULT_LINK_RE = re.compile(
    r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
    re.DOTALL,
)
_RESULT_SNIPPET_RE = re.compile(
    r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
    re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str = ""


class SearchError(RuntimeError):
    pass


def _strip_tags(fragment: str) -> str:
    return html_lib.unescape(_TAG_RE.sub("", fragment)).strip()


def _resolve_url(href: str) -> str:
    """DuckDuckGo wraps result URLs as //duckduckgo.com/l/?uddg=<encoded>."""
    href = html_lib.unescape(href)
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        if target:
            return unquote(target)
    return href


def parse_duckduckgo_html(page: str, max_results: int) -> list[SearchResult]:
    links = _RESULT_LINK_RE.findall(page)
    snippets = [_strip_tags(s) for s in _RESULT_SNIPPET_RE.findall(page)]
    results: list[SearchResult] = []
    for index, (href, title_html) in enumerate(links):
        url = _resolve_url(href)
        # Skip ads and internal links that don't resolve to an external page.
        if "duckduckgo.com" in urlparse(url).netloc:
            continue
        title = _strip_tags(title_html)
        if not title or not url.startswith("http"):
            continue
        snippet = snippets[index] if index < len(snippets) else ""
        results.append(SearchResult(title=title, url=url, snippet=snippet))
        if len(results) >= max_results:
            break
    return results


def search_web(query: str, config: WebSearchConfig) -> list[SearchResult]:
    try:
        with httpx.Client(
            timeout=config.timeout_seconds,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        ) as client:
            response = client.post(SEARCH_ENDPOINT, data={"q": query})
            response.raise_for_status()
            return parse_duckduckgo_html(response.text, config.max_results)
    except httpx.HTTPError as exc:
        raise SearchError(f"web search failed: {exc}") from exc


_DECISION_SYSTEM = """You decide whether a web search would improve the answer to the user's latest message.

Prefer searching when external context would strengthen your case: news, current events, prices, weather, releases, documentation, comparisons, or facts you may not know or that change over time.
When unsure whether search would help, lean toward searching rather than answering from memory alone.
Do NOT search for pure greetings, creative writing with no factual needs, or trivial acknowledgments.

Today's date: {today}

Respond with JSON only:
{{"search": true, "query": "<concise search query>"}}
or
{{"search": false, "query": ""}}"""


def decide_search(client: OllamaClient, turns: list[ChatTurn]) -> str | None:
    """Ask the model whether to search. Returns a query string or None."""
    recent = [t for t in turns if t.role in ("user", "assistant")][-6:]
    convo = "\n".join(f"{t.role}: {t.content}" for t in recent)
    messages = [
        {"role": "system", "content": _DECISION_SYSTEM.format(today=date.today().isoformat())},
        {"role": "user", "content": f"Conversation:\n{convo}\n\nShould you search the web?"},
    ]
    try:
        raw = client.chat(messages, json_mode=True, temperature=0.0)
        data = json.loads(raw)
    except (OllamaError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or not data.get("search"):
        return None
    query = str(data.get("query", "")).strip()
    return query or None


def format_results_block(query: str, results: list[SearchResult]) -> str:
    parts = [
        "[WEB SEARCH RESULTS]",
        f"Live web results for: {query}",
        "Use these to answer questions about the world; they are current and trustworthy.",
        "Mention the source site when you rely on a result.",
        "",
    ]
    for i, r in enumerate(results, 1):
        parts.append(f"{i}. {r.title}")
        parts.append(f"   URL: {r.url}")
        if r.snippet:
            parts.append(f"   {r.snippet}")
    return "\n".join(parts)


_WHITESPACE_RE = re.compile(r"\s+")


def fetch_page_text(
    url: str,
    *,
    timeout_seconds: float = 15.0,
    max_chars: int = 8000,
) -> str:
    """Fetch a URL and return plain text (best-effort, for training enrichment)."""
    try:
        with httpx.Client(
            timeout=timeout_seconds,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        ) as client:
            response = client.get(url)
            response.raise_for_status()
            html = response.text
    except httpx.HTTPError:
        return ""

    text = _strip_tags(html)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    if len(text) > max_chars:
        text = text[: max_chars - 3].rstrip() + "..."
    return text


def fetch_page_content(
    url: str,
    *,
    firecrawl: FirecrawlConfig | None = None,
    timeout_seconds: float = 15.0,
    max_chars: int = 8000,
) -> str:
    """Fetch page text, preferring Firecrawl when enabled."""
    if firecrawl and firecrawl.enabled:
        try:
            return scrape_page(url, firecrawl)
        except FirecrawlError:
            pass
    return fetch_page_text(url, timeout_seconds=timeout_seconds, max_chars=max_chars)


def enrich_search_with_pages(
    results: list[SearchResult],
    firecrawl: FirecrawlConfig,
) -> str:
    """Scrape top search result pages and format as context blocks."""
    if not firecrawl.enabled or firecrawl.max_pages_in_chat <= 0:
        return ""

    blocks: list[str] = []
    for result in results[: firecrawl.max_pages_in_chat]:
        page_text = fetch_page_content(result.url, firecrawl=firecrawl)
        if page_text:
            blocks.append(format_page_content_block(result.title, result.url, page_text))
    return "\n\n".join(blocks)


def format_page_content_block(title: str, url: str, page_text: str) -> str:
    parts = [
        "[WEB PAGE CONTENT]",
        f"Source: {title}",
        f"URL: {url}",
        "",
        page_text,
    ]
    return "\n".join(parts)
