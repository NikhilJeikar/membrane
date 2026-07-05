"""Tests for fine-tune trainer helpers."""

from pathlib import Path

import pytest

from membrane.learning.trainer import (
    FineTuneError,
    _load_jsonl_dataset,
    register_ollama_model,
    resolve_hf_model,
    training_deps_available,
)


def test_resolve_hf_model_known_tag():
    assert resolve_hf_model("qwen2.5:7b") == "unsloth/Qwen2.5-7B-Instruct-bnb-4bit"


def test_resolve_hf_model_override():
    assert resolve_hf_model("custom:tag", "org/MyModel") == "org/MyModel"


def test_resolve_hf_model_unknown_raises():
    with pytest.raises(FineTuneError, match="No Hugging Face mapping"):
        resolve_hf_model("totally-unknown-model")


def test_load_jsonl_dataset(tmp_path: Path):
    path = tmp_path / "data.jsonl"
    path.write_text('{"messages":[{"role":"user","content":"hi"}]}\n\n', encoding="utf-8")
    rows = _load_jsonl_dataset(path)
    assert len(rows) == 1
    assert rows[0]["messages"][0]["content"] == "hi"


def test_training_deps_available_without_install():
    assert training_deps_available() is False


def test_register_ollama_model(monkeypatch, tmp_path: Path):
    adapter = tmp_path / "adapter.gguf"
    adapter.write_bytes(b"gguf")

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        class Result:
            returncode = 0
            stdout = "created"
            stderr = ""

        return Result()

    monkeypatch.setattr("membrane.learning.trainer.subprocess.run", fake_run)
    register_ollama_model("qwen2.5:7b", adapter, "membrane-pa:latest")
    assert calls
    assert calls[0][:3] == ["ollama", "create", "membrane-pa:latest"]
