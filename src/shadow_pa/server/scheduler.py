"""Background periodic raw → parsed parsing."""

from __future__ import annotations

import logging
import threading
from typing import Callable

logger = logging.getLogger(__name__)


class ParseScheduler:
    def __init__(
        self,
        interval_seconds: int,
        parse_fn: Callable[[], None],
    ) -> None:
        self.interval_seconds = interval_seconds
        self.parse_fn = parse_fn
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="shadow-pa-parse", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        self.parse_fn()
        while not self._stop.wait(self.interval_seconds):
            try:
                self.parse_fn()
            except Exception:
                logger.exception("Periodic parse failed")
