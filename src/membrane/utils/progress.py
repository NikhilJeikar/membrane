"""Progress reporting for long-running batch jobs."""

from __future__ import annotations

from collections.abc import Callable

ProgressCallback = Callable[[int, int, str], None]
StopProgress = Callable[[], None]


def noop_progress(_completed: int, _total: int, _description: str) -> None:
    pass


def make_rich_progress(console: object) -> tuple[ProgressCallback, StopProgress]:
    """Return a progress callback and a stop function using Rich."""
    from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(bar_width=40),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,  # type: ignore[arg-type]
        transient=False,
    )
    task_id: int | None = None

    def callback(completed: int, total: int, description: str) -> None:
        nonlocal task_id
        if task_id is None:
            progress.start()
            task_id = progress.add_task(description, total=max(total, 1))
        progress.update(
            task_id,
            completed=min(completed, total),
            total=max(total, 1),
            description=description,
        )

    def stop() -> None:
        progress.stop()

    return callback, stop
