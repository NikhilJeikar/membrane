"""Books the user has read: store plus episode-memory sync."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from membrane.memory.models import EpisodeEntry, MemorySource, new_id
from membrane.memory.store import MemoryStore


def _utc_now() -> datetime:
    return datetime.now().astimezone()


class BookEntry(BaseModel):
    id: str = Field(default_factory=new_id)
    title: str
    author: str = ""
    rating: int | None = Field(default=None, ge=1, le=5)
    notes: str = ""
    read_year: int | None = Field(default=None, ge=1900, le=2200)
    added_at: datetime = Field(default_factory=_utc_now)
    episode_id: str | None = None


class BooksStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> list[BookEntry]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return [BookEntry.model_validate(item) for item in data]

    def save(self, books: list[BookEntry]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps([b.model_dump(mode="json") for b in books], indent=2),
            encoding="utf-8",
        )

    def get(self, book_id: str) -> BookEntry | None:
        return next((b for b in self.load() if b.id == book_id), None)

    def upsert(self, book: BookEntry) -> BookEntry:
        books = [b for b in self.load() if b.id != book.id]
        books.append(book)
        books.sort(key=lambda b: b.added_at)
        self.save(books)
        return book

    def delete(self, book_id: str) -> BookEntry | None:
        books = self.load()
        target = next((b for b in books if b.id == book_id), None)
        if target is None:
            return None
        self.save([b for b in books if b.id != book_id])
        return target


def book_episode_summary(book: BookEntry) -> str:
    parts = [f"Read the book '{book.title}'"]
    if book.author:
        parts.append(f"by {book.author}")
    summary = " ".join(parts) + "."
    if book.read_year:
        summary += f" Finished in {book.read_year}."
    if book.rating:
        summary += f" Rated {book.rating}/5."
    if book.notes:
        summary += f" Takeaway: {book.notes}"
    return summary


def sync_book_episode(memory: MemoryStore, book: BookEntry) -> BookEntry:
    """Create or update the episode memory entry linked to this book."""
    episodes = memory.load_episodes()
    existing = next((e for e in episodes if e.id == book.episode_id), None)
    if existing:
        existing.summary = book_episode_summary(book)
        memory.save_episodes(episodes)
        return book
    episode = EpisodeEntry(
        summary=book_episode_summary(book),
        tags=["books", "reading"],
        source=MemorySource.BOOKS,
    )
    memory.append_episode(episode)
    book.episode_id = episode.id
    return book


def remove_book_episode(memory: MemoryStore, book: BookEntry) -> bool:
    if not book.episode_id:
        return False
    episodes = memory.load_episodes()
    kept = [e for e in episodes if e.id != book.episode_id]
    if len(kept) == len(episodes):
        return False
    memory.save_episodes(kept)
    return True
