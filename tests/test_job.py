"""Tests for fine-tune background jobs."""

from membrane.learning.export import SftExportStats
from membrane.learning.job import (
    FineTuneBusyError,
    is_fine_tune_running,
    run_fine_tune_sync,
    start_fine_tune_job,
)
from membrane.learning.trainer import FineTuneProgress, FineTuneResult


class _FakeRunner:
    def __init__(self, config, persona):
        self.config = config
        self.persona = persona

    def run(self, progress=None):
        if progress:
            progress(
                FineTuneProgress(
                    stage="training",
                    pct=50,
                    message="Training",
                    train_step=5,
                    train_total_steps=10,
                    train_epoch=1,
                )
            )
        return FineTuneResult(
            sft_path=__import__("pathlib").Path("/tmp/sft.jsonl"),
            adapter_gguf=__import__("pathlib").Path("/tmp/adapter.gguf"),
            output_model="membrane-pa:latest",
            stats=SftExportStats(
                ui_sessions=1,
                agent_sessions=0,
                total_sessions=1,
                chat_examples=2,
                memory_examples=0,
                book_examples=0,
                web_examples=0,
                total_examples=2,
                include_chats=True,
                enrich_from_web=False,
                fetch_search_pages=False,
            ),
            run_dir=__import__("pathlib").Path("/tmp/run"),
        )


def test_run_fine_tune_sync_updates_status(tmp_path, monkeypatch):
    from membrane.config_integrations import FineTuneConfig, load_integrations, save_integrations
    from membrane.config_store import reset_config_store

    reset_config_store()
    cfg = load_integrations()
    cfg.fine_tune = FineTuneConfig(base_model="qwen2.5:3b", output_model="membrane-pa:latest")
    save_integrations(cfg)

    persona = __import__("membrane.config", fromlist=["PersonaConfig"]).PersonaConfig()
    runner = _FakeRunner(cfg.fine_tune, persona)

    result = run_fine_tune_sync(runner)
    assert result.output_model == "membrane-pa:latest"

    updated = load_integrations().fine_tune
    assert updated.status == "ready"
    assert updated.progress_pct == 100
    assert updated.last_run_at is not None
    assert is_fine_tune_running() is False


def test_start_fine_tune_job_rejects_parallel(monkeypatch):
    from membrane.config_integrations import FineTuneConfig, load_integrations, save_integrations
    from membrane.config_store import reset_config_store

    reset_config_store()
    cfg = load_integrations()
    cfg.fine_tune = FineTuneConfig(base_model="qwen2.5:3b", output_model="membrane-pa:latest")
    save_integrations(cfg)

    persona = __import__("membrane.config", fromlist=["PersonaConfig"]).PersonaConfig()

    import membrane.learning.job as job_mod

    monkeypatch.setattr(job_mod, "_running", True)
    try:
        with __import__("pytest").raises(FineTuneBusyError):
            start_fine_tune_job(lambda: _FakeRunner(cfg.fine_tune, persona))
    finally:
        monkeypatch.setattr(job_mod, "_running", False)
