"""Tests for the chat web search step."""

from __future__ import annotations

import json

from membrane.config import WebSearchConfig
from membrane.inference.websearch import (
    SearchResult,
    decide_search,
    format_results_block,
    parse_duckduckgo_html,
)
from membrane.memory.models import ChatTurn

SAMPLE_HTML = """
<div class="result results_links results_links_deep web-result">
  <h2 class="result__title">
    <a rel="nofollow" class="result__a"
       href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fnews&amp;rut=abc">
      Example <b>News</b> Today
    </a>
  </h2>
  <a class="result__snippet" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fnews">
    Latest &amp; greatest <b>headlines</b> from Example.
  </a>
</div>
<div class="result">
  <h2 class="result__title">
    <a rel="nofollow" class="result__a" href="https://another.org/page">Another Page</a>
  </h2>
  <a class="result__snippet" href="https://another.org/page">Second snippet.</a>
</div>
"""


def test_parse_duckduckgo_html_unwraps_redirects_and_strips_tags():
    results = parse_duckduckgo_html(SAMPLE_HTML, max_results=5)
    assert len(results) == 2
    assert results[0].title == "Example News Today"
    assert results[0].url == "https://example.com/news"
    assert "Latest & greatest headlines" in results[0].snippet
    assert results[1].url == "https://another.org/page"


def test_parse_duckduckgo_html_respects_max_results():
    results = parse_duckduckgo_html(SAMPLE_HTML, max_results=1)
    assert len(results) == 1


class FakeDecisionClient:
    def __init__(self, response: str):
        self.response = response
        self.calls: list[list[dict]] = []

    def chat(self, messages, json_mode=False, temperature=None):
        self.calls.append(messages)
        return self.response


def _turns(text: str) -> list[ChatTurn]:
    return [ChatTurn(role="user", content=text)]


def test_decide_search_returns_query():
    client = FakeDecisionClient(json.dumps({"search": True, "query": "weather delhi today"}))
    query = decide_search(client, _turns("what's the weather in delhi?"))
    assert query == "weather delhi today"
    assert client.calls[0][0]["role"] == "system"


def test_decide_search_declines():
    client = FakeDecisionClient(json.dumps({"search": False, "query": ""}))
    assert decide_search(client, _turns("hey, how are you?")) is None


def test_decide_search_survives_bad_json():
    client = FakeDecisionClient("not json at all")
    assert decide_search(client, _turns("anything")) is None


def test_format_results_block_lists_sources():
    block = format_results_block(
        "python 3.13 release",
        [SearchResult(title="Python 3.13", url="https://python.org/313", snippet="Released.")],
    )
    assert "[WEB SEARCH RESULTS]" in block
    assert "python 3.13 release" in block
    assert "https://python.org/313" in block


def test_web_search_config_defaults_off():
    config = WebSearchConfig()
    assert config.enabled is False
    assert 1 <= config.max_results <= 10
