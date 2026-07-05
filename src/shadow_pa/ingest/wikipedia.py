"""Wikipedia corpus download and summarization dataset preparation."""

from __future__ import annotations

import json
import re
from pathlib import Path

import httpx
from pydantic import BaseModel, Field

WIKI_API = "https://{lang}.wikipedia.org/w/api.php"
WHITESPACE_RE = re.compile(r"\n{3,}")


class WikipediaArticle(BaseModel):
    title: str
    text: str
    lang: str = "en"
    source: str = "wikipedia"
    url: str | None = None
    char_count: int = 0


class SummarizationExample(BaseModel):
    messages: list[dict[str, str]]
    metadata: dict = Field(default_factory=dict)
    document: str = ""
    title: str = ""


def _clean_text(text: str) -> str:
    text = WHITESPACE_RE.sub("\n\n", text.strip())
    return text


def _article_from_page(page: dict, lang: str) -> WikipediaArticle | None:
    title = page.get("title", "").strip()
    text = _clean_text(page.get("extract", ""))
    if not title or len(text) < 200:
        return None
    page_id = page.get("pageid")
    url = f"https://{lang}.wikipedia.org/?curid={page_id}" if page_id else None
    return WikipediaArticle(
        title=title,
        text=text,
        lang=lang,
        url=url,
        char_count=len(text),
    )


def fetch_random_articles(
    *,
    lang: str = "en",
    limit: int = 100,
    min_chars: int = 500,
    max_chars: int = 12000,
) -> list[WikipediaArticle]:
    """Sample random Wikipedia articles via the public API (no extra deps)."""
    articles: list[WikipediaArticle] = []
    api = WIKI_API.format(lang=lang)
    batch = min(limit, 50)

    with httpx.Client(timeout=60.0) as client:
        while len(articles) < limit:
            response = client.get(
                api,
                params={
                    "action": "query",
                    "generator": "random",
                    "grnnamespace": 0,
                    "grnlimit": batch,
                    "prop": "extracts",
                    "explaintext": True,
                    "format": "json",
                },
            )
            response.raise_for_status()
            data = response.json()
            pages = data.get("query", {}).get("pages", {})
            if not pages:
                break
            for page in pages.values():
                article = _article_from_page(page, lang)
                if not article:
                    continue
                if article.char_count < min_chars or article.char_count > max_chars:
                    continue
                articles.append(article)
                if len(articles) >= limit:
                    break

    return articles[:limit]


def download_hf_wikipedia(
    *,
    lang: str = "en",
    limit: int = 1000,
    min_chars: int = 500,
    max_chars: int = 12000,
) -> list[WikipediaArticle]:
    """Stream articles from Hugging Face wikimedia/wikipedia (requires `datasets`)."""
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise ImportError(
            "Install corpus extras: pip install 'shadow-pa[corpus]'"
        ) from exc

    config = f"20231101.{lang}"
    dataset = load_dataset("wikimedia/wikipedia", config, split="train", streaming=True)
    articles: list[WikipediaArticle] = []

    for row in dataset:
        text = _clean_text(row.get("text", ""))
        title = row.get("title", "").strip()
        if not title or len(text) < min_chars or len(text) > max_chars:
            continue
        articles.append(
            WikipediaArticle(
                title=title,
                text=text,
                lang=lang,
                url=row.get("url"),
                char_count=len(text),
            )
        )
        if len(articles) >= limit:
            break

    return articles


def save_articles(articles: list[WikipediaArticle], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for article in articles:
            f.write(json.dumps(article.model_dump(mode="json")) + "\n")
    return output_path


def load_articles(path: Path) -> list[WikipediaArticle]:
    articles: list[WikipediaArticle] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            articles.append(WikipediaArticle.model_validate(json.loads(line)))
    return articles


def article_to_document_prompt(article: WikipediaArticle, instruction: str | None = None) -> str:
    instr = instruction or "Summarize the following article in 5 concise bullet points."
    return f"{instr}\n\nTitle: {article.title}\n\n{article.text}"


def build_summarization_corpus(
    articles: list[WikipediaArticle],
    *,
    instruction: str | None = None,
    include_lead_summary: bool = False,
) -> list[SummarizationExample]:
    """Build summarization training rows (documents ready for local teacher labeling)."""
    examples: list[SummarizationExample] = []
    instr = instruction or "Summarize the following article in 5 concise bullet points."

    for article in articles:
        user_content = article_to_document_prompt(article, instruction=instr)
        messages = [
            {
                "role": "system",
                "content": "Task: summarization. Be faithful; do not add facts not in the document.",
            },
            {"role": "user", "content": user_content},
        ]
        assistant_content = ""
        if include_lead_summary:
            assistant_content = article.text.split("\n\n")[0][:800]

        if assistant_content:
            messages.append({"role": "assistant", "content": assistant_content})

        examples.append(
            SummarizationExample(
                messages=messages,
                document=article.text,
                title=article.title,
                metadata={
                    "task": "summarization",
                    "source": "wikipedia",
                    "lang": article.lang,
                    "url": article.url,
                    "labeled": bool(assistant_content),
                },
            )
        )
    return examples


def save_summarization_jsonl(examples: list[SummarizationExample], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex.model_dump(mode="json")) + "\n")
    return output_path


SUMMARIZE_SYSTEM = (
    "You summarize documents faithfully. Use concise bullet points. Do not add facts."
)

SUMMARIZE_USER = """Summarize this Wikipedia article in 5 bullet points.

Title: {title}

{document}
"""


def label_summaries_with_ollama(
    examples: list[SummarizationExample],
    *,
    client: object,
    model: str,
    max_document_chars: int = 8000,
    workers: int = 0,
) -> list[SummarizationExample]:
    """Fill assistant summaries using a local Ollama model (parallel when workers > 1)."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from shadow_pa.utils.parallel import default_workers

    def label_one(ex: SummarizationExample) -> SummarizationExample:
        doc = ex.document[:max_document_chars]
        user_prompt = SUMMARIZE_USER.format(title=ex.title, document=doc)
        summary = client.chat(  # type: ignore[attr-defined]
            messages=[
                {"role": "system", "content": SUMMARIZE_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            model=model,
            temperature=0.3,
        )
        messages = [
            {"role": "system", "content": "Task: summarization. Be faithful; do not add facts."},
            {"role": "user", "content": ex.messages[1]["content"]},
            {"role": "assistant", "content": summary.strip()},
        ]
        return SummarizationExample(
            messages=messages,
            document=ex.document,
            title=ex.title,
            metadata={**ex.metadata, "labeled": True, "labeler": "ollama"},
        )

    if not examples:
        return []

    pool_size = min(default_workers(workers), getattr(client, "parallel_requests", lambda: 1)(), len(examples))
    if pool_size <= 1:
        return [label_one(ex) for ex in examples]

    results: list[SummarizationExample | None] = [None] * len(examples)
    with ThreadPoolExecutor(max_workers=pool_size) as pool:
        futures = {pool.submit(label_one, ex): idx for idx, ex in enumerate(examples)}
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    return [r for r in results if r is not None]
