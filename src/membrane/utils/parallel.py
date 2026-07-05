"""CPU parallelism helpers."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from typing import TypeVar

T = TypeVar("T")
R = TypeVar("R")


def cpu_count() -> int:
    return os.cpu_count() or 4


def default_workers(requested: int = 0) -> int:
    """Return worker count; 0 means use (CPU cores - 1), minimum 1."""
    if requested > 0:
        return requested
    return max(1, cpu_count() - 1)


def map_parallel(
    func: Callable[[T], R],
    items: Iterable[T],
    *,
    workers: int = 0,
    use_processes: bool = False,
) -> list[R]:
    """Run func over items using a thread or process pool."""
    item_list = list(items)
    if not item_list:
        return []
    n = min(default_workers(workers), len(item_list))
    if n <= 1:
        return [func(item) for item in item_list]

    executor_cls = ProcessPoolExecutor if use_processes else ThreadPoolExecutor
    results: list[R | None] = [None] * len(item_list)
    with executor_cls(max_workers=n) as pool:
        future_map = {pool.submit(func, item): idx for idx, item in enumerate(item_list)}
        for future in as_completed(future_map):
            results[future_map[future]] = future.result()
    return [r for r in results if r is not None]
