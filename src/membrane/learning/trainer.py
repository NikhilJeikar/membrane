"""End-to-end LoRA fine-tuning and Ollama model registration."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from membrane.config_integrations import FineTuneConfig
from membrane.learning.export import SftExportStats, TrainingExporter

if TYPE_CHECKING:
    from membrane.config import PersonaConfig, Settings
    from membrane.llm.ollama import OllamaClient

ProgressCallback = Callable[["FineTuneProgress"], None]


@dataclass
class FineTuneProgress:
    stage: str
    pct: int
    message: str = ""
    train_step: int = 0
    train_total_steps: int = 0
    train_epoch: int = 0

# Common Ollama tags → Hugging Face instruct checkpoints for LoRA training.
OLLAMA_TO_HF: dict[str, str] = {
    "qwen2.5:0.5b": "unsloth/Qwen2.5-0.5B-Instruct-bnb-4bit",
    "qwen2.5:1.5b": "unsloth/Qwen2.5-1.5B-Instruct-bnb-4bit",
    "qwen2.5:3b": "unsloth/Qwen2.5-3B-Instruct-bnb-4bit",
    "qwen2.5:7b": "unsloth/Qwen2.5-7B-Instruct-bnb-4bit",
    "qwen2.5:14b": "unsloth/Qwen2.5-14B-Instruct-bnb-4bit",
    "qwen2.5:32b": "unsloth/Qwen2.5-32B-Instruct-bnb-4bit",
    "llama3.2:1b": "unsloth/Llama-3.2-1B-Instruct-bnb-4bit",
    "llama3.2:3b": "unsloth/Llama-3.2-3B-Instruct-bnb-4bit",
    "llama3.1:8b": "unsloth/Meta-Llama-3.1-8B-Instruct-bnb-4bit",
    "mistral:7b": "unsloth/mistral-7b-instruct-v0.3-bnb-4bit",
    "gemma2:2b": "unsloth/gemma-2-2b-it-bnb-4bit",
    "gemma2:9b": "unsloth/gemma-2-9b-it-bnb-4bit",
    "phi3:mini": "unsloth/Phi-3-mini-4k-instruct-bnb-4bit",
    "phi3:medium": "unsloth/Phi-3-medium-4k-instruct-bnb-4bit",
}


class TrainingDependencyError(ImportError):
    """Raised when optional training packages are not installed."""


class FineTuneError(RuntimeError):
    pass


@dataclass
class FineTuneResult:
    sft_path: Path
    adapter_gguf: Path
    output_model: str
    stats: SftExportStats
    run_dir: Path


def training_deps_available() -> bool:
    try:
        import unsloth  # noqa: F401
        import torch  # noqa: F401

        return True
    except ImportError:
        return False


def training_requirements_hint() -> str:
    return "Install training extras: pip install 'membrane[train]'"


def resolve_hf_model(ollama_model: str, override: str = "") -> str:
    if override.strip():
        return override.strip()
    key = ollama_model.strip().lower()
    if key in OLLAMA_TO_HF:
        return OLLAMA_TO_HF[key]
    if ":" not in key:
        tagged = f"{key}:latest"
        if tagged in OLLAMA_TO_HF:
            return OLLAMA_TO_HF[tagged]
        for tag, hf_id in OLLAMA_TO_HF.items():
            if tag.startswith(f"{key}:"):
                return hf_id
    base = key.split(":")[0]
    for tag, hf_id in OLLAMA_TO_HF.items():
        if tag.startswith(f"{base}:"):
            return hf_id
    raise FineTuneError(
        f"No Hugging Face mapping for Ollama model '{ollama_model}'. "
        "Set fine_tune.hf_base_model to a compatible instruct checkpoint."
    )


def _load_jsonl_dataset(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _find_gguf_adapter(directory: Path) -> Path:
    matches = sorted(directory.rglob("*.gguf"))
    if not matches:
        raise FineTuneError(f"No GGUF adapter produced under {directory}")
    return matches[0]


def register_ollama_model(base_model: str, adapter_gguf: Path, output_model: str) -> None:
    modelfile_path = adapter_gguf.parent / "Modelfile"
    modelfile_path.write_text(
        f"FROM {base_model}\nADAPTER {adapter_gguf.resolve()}\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["ollama", "create", output_model, "-f", str(modelfile_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "unknown error").strip()
        raise FineTuneError(f"ollama create failed: {detail}")


class FineTuneRunner:
    def __init__(
        self,
        *,
        config: FineTuneConfig,
        settings: Settings,
        persona: PersonaConfig,
        exporter: TrainingExporter,
        ollama: OllamaClient | None = None,
    ) -> None:
        self.config = config
        self.settings = settings
        self.persona = persona
        self.exporter = exporter
        self.ollama = ollama

    def run(self, progress: ProgressCallback | None = None) -> FineTuneResult:
        def notify(
            stage: str,
            pct: int,
            message: str = "",
            *,
            train_step: int = 0,
            train_total_steps: int = 0,
            train_epoch: int = 0,
        ) -> None:
            if progress is not None:
                progress(
                    FineTuneProgress(
                        stage=stage,
                        pct=pct,
                        message=message,
                        train_step=train_step,
                        train_total_steps=train_total_steps,
                        train_epoch=train_epoch,
                    )
                )

        if not training_deps_available():
            raise TrainingDependencyError(training_requirements_hint())

        import torch

        if not torch.cuda.is_available():
            raise FineTuneError(
                "CUDA GPU is required for fine-tuning. "
                "Install PyTorch with CUDA support and ensure a GPU is visible."
            )

        base_model = (
            self.config.base_model.strip()
            or self.persona.llm.model.strip()
        )
        output_model = self.config.output_model.strip()
        if not base_model or not output_model:
            raise FineTuneError("base_model and output_model are required")

        if self.ollama is not None and not self.ollama.has_model(base_model):
            raise FineTuneError(
                f"Base model '{base_model}' is not installed in Ollama. "
                f"Pull it with: ollama pull {base_model}"
            )

        notify("exporting", 5, "Exporting SFT dataset")
        _, stats = self.exporter.build_sft_examples()
        if stats.total_examples < 1:
            raise FineTuneError(
                "No SFT examples found. Add chat history, memory, or books before fine-tuning."
            )

        run_id = datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S")
        run_dir = self.settings.training_dir / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        sft_path = self.exporter.export_sft(output_name=f"pa_sft_{run_id}.jsonl")
        notify("exporting", 12, f"Exported {stats.total_examples} SFT examples")

        notify("training", 15, f"Loading model ({stats.total_examples} examples)")
        hf_model = resolve_hf_model(base_model, self.config.hf_base_model)
        adapter_gguf = self._train_lora(hf_model, sft_path, run_dir, notify, self.config.epochs)

        notify("registering", 90, f"Creating Ollama model {output_model}")
        register_ollama_model(base_model, adapter_gguf, output_model)

        if self.config.set_as_chat_model:
            from membrane.config import save_persona

            self.persona.llm.model = output_model
            save_persona(self.persona)

        notify("ready", 100, f"Registered {output_model} in Ollama")
        return FineTuneResult(
            sft_path=sft_path,
            adapter_gguf=adapter_gguf,
            output_model=output_model,
            stats=stats,
            run_dir=run_dir,
        )

    def _train_lora(
        self,
        hf_model: str,
        sft_path: Path,
        run_dir: Path,
        notify: Callable[..., None],
        epochs: int,
    ) -> Path:
        from datasets import Dataset
        from transformers import TrainerCallback
        from trl import SFTConfig, SFTTrainer
        from unsloth import FastLanguageModel

        class TrainProgressCallback(TrainerCallback):
            def on_train_begin(self, args, state, control, **kwargs) -> None:
                notify(
                    "training",
                    35,
                    "Starting LoRA training",
                    train_total_steps=state.max_steps,
                )

            def on_log(self, args, state, control, logs=None, **kwargs) -> None:
                if state.max_steps <= 0:
                    return
                pct = 35 + min(43, int(43 * state.global_step / state.max_steps))
                epoch = int(state.epoch) + 1 if state.epoch is not None else 1
                notify(
                    "training",
                    pct,
                    f"Epoch {epoch}/{epochs} · step {state.global_step}/{state.max_steps}",
                    train_step=state.global_step,
                    train_total_steps=state.max_steps,
                    train_epoch=epoch,
                )

        rows = _load_jsonl_dataset(sft_path)
        notify("training", 25, f"Preparing dataset ({len(rows)} rows)")

        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=hf_model,
            max_seq_length=self.config.max_seq_length,
            dtype=None,
            load_in_4bit=True,
        )
        model = FastLanguageModel.get_peft_model(
            model,
            r=self.config.lora_rank,
            target_modules=[
                "q_proj",
                "k_proj",
                "v_proj",
                "o_proj",
                "gate_proj",
                "up_proj",
                "down_proj",
            ],
            lora_alpha=self.config.lora_alpha,
            lora_dropout=0,
            bias="none",
            use_gradient_checkpointing="unsloth",
            random_state=3407,
        )

        def format_example(row: dict[str, Any]) -> dict[str, str]:
            messages = row.get("messages") or []
            text = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=False,
            )
            return {"text": text}

        dataset = Dataset.from_list([format_example(row) for row in rows])
        notify("training", 30, f"Loaded {hf_model}")

        trainer = SFTTrainer(
            model=model,
            tokenizer=tokenizer,
            train_dataset=dataset,
            args=SFTConfig(
                per_device_train_batch_size=self.config.batch_size,
                gradient_accumulation_steps=self.config.gradient_accumulation_steps,
                num_train_epochs=self.config.epochs,
                learning_rate=self.config.learning_rate,
                logging_steps=1,
                optim="adamw_8bit",
                weight_decay=0.01,
                lr_scheduler_type="linear",
                seed=3407,
                output_dir=str(run_dir / "checkpoints"),
                report_to="none",
            ),
            dataset_text_field="text",
            callbacks=[TrainProgressCallback()],
        )
        trainer.train()

        gguf_dir = run_dir / "gguf"
        notify("training", 80, "Exporting LoRA adapter for Ollama")
        model.save_pretrained_gguf(str(gguf_dir), tokenizer, save_method="lora")
        return _find_gguf_adapter(gguf_dir)
