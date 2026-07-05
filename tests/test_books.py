"""Tests for books store, episode sync, and training export rows."""

import json

from membrane.config import PersonaConfig
from membrane.inference.context import ContextBuilder
from membrane.learning.export import TrainingExporter
from membrane.memory.books import (
    BookEntry,
    BooksStore,
    book_episode_summary,
    remove_book_episode,
    sync_book_episode,
)
from membrane.memory.models import MemorySource
from membrane.memory.store import MemoryStore


def test_book_episode_summary_includes_details():
    book = BookEntry(title="Deep Work", author="Cal Newport", rating=5, notes="Focus wins.", read_year=2025)
    summary = book_episode_summary(book)
    assert "Deep Work" in summary
    assert "Cal Newport" in summary
    assert "5/5" in summary
    assert "2025" in summary
    assert "Focus wins." in summary


def test_sync_and_remove_book_episode(tmp_path):
    memory = MemoryStore(tmp_path / "memory")
    book = BookEntry(title="Dune", author="Frank Herbert")

    book = sync_book_episode(memory, book)
    episodes = memory.load_episodes()
    assert len(episodes) == 1
    assert episodes[0].id == book.episode_id
    assert episodes[0].source == MemorySource.BOOKS

    book.rating = 4
    sync_book_episode(memory, book)
    episodes = memory.load_episodes()
    assert len(episodes) == 1
    assert "4/5" in episodes[0].summary

    assert remove_book_episode(memory, book)
    assert memory.load_episodes() == []


def test_export_sft_includes_book_recall_rows(tmp_path):
    memory = MemoryStore(tmp_path / "memory")
    books_path = tmp_path / "books" / "books.json"
    books = BooksStore(books_path)
    books.upsert(BookEntry(title="Dune", author="Frank Herbert", notes="Fear is the mind-killer."))

    chats_dir = tmp_path / "chats"
    chats_dir.mkdir()
    exporter = TrainingExporter(
        store=memory,
        context_builder=ContextBuilder(memory, PersonaConfig()),
        chats_dir=chats_dir,
        export_dir=tmp_path / "export",
        books_path=books_path,
    )
    out = exporter.export_sft()
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    subtypes = {row["metadata"].get("subtype") for row in rows}
    assert "book_recall" in subtypes
    assert "book_takeaway" in subtypes
    assert "book_list" in subtypes
    recall = next(r for r in rows if r["metadata"].get("subtype") == "book_recall")
    assert "Dune" in recall["messages"][1]["content"]
