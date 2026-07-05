"""Background fine-tune job orchestration."""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import UTC, datetime

from membrane.config_integrations import FineTuneConfig, load_integrations, save_integrations
from membrane.learning.trainer import FineTuneProgress, FineTuneResult, FineTuneRunner

_lock = threading.Lock()
_running = False


class FineTuneBusyError(RuntimeError):
    pass


def is_fine_tune_running() -> bool:
    with _lock:
        return _running


def _update_fine_tune(**fields: object) -> FineTuneConfig:
    config = load_integrations()
    for key, value in fields.items():
        setattr(config.fine_tune, key, value)
    save_integrations(config)
    return config.fine_tune


def _progress(update: FineTuneProgress) -> None:
    _update_fine_tune(
        status=update.stage,
        progress_pct=update.pct,
        status_message=update.message,
        train_step=update.train_step,
        train_total_steps=update.train_total_steps,
        train_epoch=update.train_epoch,
    )


def _execute(runner: FineTuneRunner) -> FineTuneResult:
    _update_fine_tune(
        status="exporting",
        status_message="Exporting SFT dataset...",
        progress_pct=5,
        last_error=None,
        train_step=0,
        train_total_steps=0,
        train_epoch=0,
    )
    result = runner.run(progress=_progress)
    now = datetime.now(tz=UTC).isoformat()
    _update_fine_tune(
        status="ready",
        status_message=f"Model {result.output_model} registered in Ollama",
        progress_pct=100,
        last_export_at=now,
        last_run_at=now,
        base_model=runner.config.base_model or runner.persona.llm.model,
        output_model=result.output_model,
    )
    return result


def run_fine_tune_sync(runner: FineTuneRunner) -> FineTuneResult:
    """Run fine-tuning in the current thread (CLI)."""
    global _running
    with _lock:
        if _running:
            raise FineTuneBusyError("A fine-tune job is already running")
        _running = True

    try:
        return _execute(runner)
    except Exception as exc:
        _update_fine_tune(
            status="failed",
            status_message="Fine-tune failed",
            last_error=str(exc),
            progress_pct=0,
        )
        raise
    finally:
        with _lock:
            _running = False


def start_fine_tune_job(runner_factory: Callable[[], FineTuneRunner]) -> FineTuneConfig:
    """Start fine-tuning on a background thread (API)."""
    global _running
    with _lock:
        if _running:
            raise FineTuneBusyError("A fine-tune job is already running")
        _running = True

    def _run() -> None:
        global _running
        try:
            _execute(runner_factory())
        except Exception:
            pass
        finally:
            with _lock:
                _running = False

    thread = threading.Thread(target=_run, daemon=True, name="membrane-fine-tune")
    thread.start()
    return load_integrations().fine_tune
