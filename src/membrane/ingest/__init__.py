"""Ingestion pipelines."""

from membrane.ingest.cursor import (
    chunk_cursor_turns,
    cursor_sessions_to_chat_sessions,
    discover_cursor_transcripts,
    format_cursor_chunk_for_extraction,
    ingest_cursor_path,
    load_parsed_cursor_turns,
    parse_cursor_transcript,
)
from membrane.ingest.whatsapp import (
    chunk_messages,
    format_chunk_for_extraction,
    ingest_whatsapp_file,
    load_parsed_messages,
    parse_whatsapp_export,
)
from membrane.ingest.wikipedia import (
    build_summarization_corpus,
    download_hf_wikipedia,
    fetch_random_articles,
    label_summaries_with_ollama,
    load_articles,
    save_articles,
    save_summarization_jsonl,
)

__all__ = [
    "build_summarization_corpus",
    "chunk_cursor_turns",
    "chunk_messages",
    "cursor_sessions_to_chat_sessions",
    "discover_cursor_transcripts",
    "download_hf_wikipedia",
    "fetch_random_articles",
    "format_chunk_for_extraction",
    "format_cursor_chunk_for_extraction",
    "ingest_cursor_path",
    "ingest_whatsapp_file",
    "label_summaries_with_ollama",
    "load_articles",
    "load_parsed_cursor_turns",
    "load_parsed_messages",
    "parse_cursor_transcript",
    "parse_whatsapp_export",
    "save_articles",
    "save_summarization_jsonl",
]
