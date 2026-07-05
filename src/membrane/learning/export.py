"""Export training datasets (SFT / DPO) from local memory and chats."""

from __future__ import annotations

import json
from pathlib import Path

from membrane.inference.context import ContextBuilder
from membrane.learning.chat_log import ChatLogger
from membrane.memory.models import ChatSession, SFTExample
from membrane.memory.store import MemoryStore


class TrainingExporter:
    def __init__(
        self,
        store: MemoryStore,
        context_builder: ContextBuilder,
        chats_dir: Path,
        export_dir: Path,
    ) -> None:
        self.store = store
        self.context_builder = context_builder
        self.chat_logger = ChatLogger(chats_dir)
        self.export_dir = export_dir
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def export_sft(self, output_name: str = "pa_sft.jsonl") -> Path:
        out_path = self.export_dir / output_name
        examples: list[SFTExample] = []

        memory_context = self.context_builder.build_memory_context_dict()
        system_prompt = self.context_builder.build_system_prompt()

        for session_path in self.chat_logger.list_sessions():
            session = ChatSession.model_validate_json(session_path.read_text(encoding="utf-8"))
            messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
            for turn in session.turns:
                if turn.role in ("user", "assistant"):
                    messages.append({"role": turn.role, "content": turn.content})
            if len(messages) >= 3:
                examples.append(
                    SFTExample(
                        messages=messages,
                        memory_context=memory_context,
                        metadata={"session_id": session.id, "task": "personal_assistant"},
                    )
                )

        examples.extend(self._memory_qa_examples())

        with out_path.open("w", encoding="utf-8") as f:
            for ex in examples:
                f.write(json.dumps(ex.model_dump(mode="json")) + "\n")
        return out_path

    def _memory_qa_examples(self) -> list[SFTExample]:
        """Generate simple recall examples from profile entries."""
        examples: list[SFTExample] = []
        for entry in self.store.load_profile():
            system = self.context_builder.build_system_prompt()
            user_q = f"What do you know about my {entry.key.replace('_', ' ')}?"
            assistant_a = entry.value
            examples.append(
                SFTExample(
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_q},
                        {"role": "assistant", "content": assistant_a},
                    ],
                    memory_context=self.context_builder.build_memory_context_dict(user_q),
                    metadata={"task": "personal_assistant", "subtype": "profile_recall"},
                )
            )
        return examples

    def export_dpo(self, output_name: str = "pa_dpo.jsonl") -> Path:
        out_path = self.export_dir / output_name
        dpo_source = self.export_dir.parent / "dpo"
        lines: list[str] = []
        if dpo_source.exists():
            for path in sorted(dpo_source.glob("*.jsonl")):
                lines.extend(path.read_text(encoding="utf-8").splitlines())
        out_path.write_text("\n".join(line for line in lines if line.strip()) + ("\n" if lines else ""), encoding="utf-8")
        return out_path

    def export_memory_snapshot(self, output_name: str = "memory_snapshot.json") -> Path:
        out_path = self.export_dir / output_name
        out_path.write_text(json.dumps(self.store.snapshot(), indent=2), encoding="utf-8")
        return out_path
