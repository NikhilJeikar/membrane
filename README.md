# shadow-pa

Local personal assistant framework: memory, WhatsApp shadowing, and privacy-first learning. No cloud teachers — personal data stays on your machine.

## Features

- **Structured memory** — profile facts, preferences, episodic summaries
- **WhatsApp ingest** — parse exports, redact PII, extract learnings locally
- **Cursor ingest** — decode agent transcript JSONL, strip tool calls, learn from sessions
- **Hash tracking** — SHA256 manifest skips unchanged raw/parsed files on ingest and extract
- **Ingest server** — local HTTP collector for email, calendar, and search history
- **Wikipedia corpus** — download articles for summarization training (API or Hugging Face)
- **Review workflow** — proposed memory updates require approval before commit
- **Context builder** — inject memory + persona into prompts for local LLMs (Ollama)
- **Training export** — JSONL for SFT/DPO from chats, Cursor, and summarization datasets
- **Dataset layout** — folders for summarization, coding, and PA distillation data

## Quick start

```bash
cd ~/Projects/shadow-pa
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Copy example memory and persona, then edit for yourself
cp memory/examples/profile.json memory/profile.json
cp memory/examples/preferences.json memory/preferences.json
cp config/persona.example.yaml config/persona.yaml

# Ingest a WhatsApp export (without media)
shadow-pa ingest whatsapp data/whatsapp/raw/my-chat.txt --self-name "Nikhil"

# Ingest Cursor agent sessions (all transcripts under a project)
shadow-pa ingest cursor ~/.cursor/projects/empty-window/agent-transcripts/

# Download Wikipedia for summarization training (API sample)
shadow-pa ingest wiki --limit 500 --lang en

# Full Wikipedia stream via Hugging Face (install corpus extra first)
pip install 'shadow-pa[corpus]'
shadow-pa ingest wiki --hf --limit 5000 --lang en

# Prepare summarization dataset (optional: label with local Ollama)
shadow-pa dataset prepare-summarization --lang en
shadow-pa dataset prepare-summarization --lang en --label

# Extract memory proposals (requires Ollama running locally)
shadow-pa extract run --source cursor
shadow-pa extract run --source all

# Only new/changed files are processed (tracked in data/ingest_manifest.json)
shadow-pa ingest cursor ~/.cursor/projects/.../agent-transcripts/   # skips unchanged raw
shadow-pa extract run --source cursor                                 # skips already extracted
shadow-pa extract run --source cursor --force                         # re-extract everything

# One-time migration if you already ingested/extracted before tracking existed:
shadow-pa tracking reconcile
shadow-pa tracking mark-extracted --source cursor

# Web UI (IBM Carbon)
pip install -e ".[ui]"
cd ui && npm install && npm run build
shadow-pa ui run
# Dev: terminal 1 → shadow-pa ui run --dev   terminal 2 → cd ui && npm run dev

# Review and approve proposals
shadow-pa memory list-proposed
shadow-pa memory review                    # interactive: a=approve, r=reject, s=skip, q=quit
shadow-pa memory review --category profile # filter by type
shadow-pa memory approve --all             # bulk approve (use carefully)

# Local ingest server (email, calendar, search history)
shadow-pa server run                       # listens on 127.0.0.1:8765, parses every 5 min
shadow-pa server status                    # show counts + auth token
shadow-pa server parse                     # one-shot raw → parsed

# Send data (use token from server status)
curl -X POST http://127.0.0.1:8765/v1/ingest/search \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"items":[{"query":"fedora hyprland ricing","engine":"google"}]}'

# Extract → review → approve (same workflow as Cursor)
shadow-pa extract run --source search --offline
shadow-pa memory review

# Build prompt context for inference
shadow-pa context build "What did we plan for Goa?"

# Export training data
shadow-pa export sft
shadow-pa export dpo
shadow-pa export summarization --lang en
```

## Project layout

```
shadow-pa/
├── config/persona.yaml       # Controllable behavior knobs
├── memory/                   # Live memory store (gitignored)
├── memory/examples/          # Safe templates committed to git
├── data/
│   ├── whatsapp/             # Raw + parsed chat exports
│   ├── cursor/               # Cursor agent transcript ingest
│   ├── email/                # Server-ingested email (raw + parsed)
│   ├── calendar/             # Server-ingested calendar events
│   ├── search/               # Server-ingested search history
│   ├── server/               # Server auth token (gitignored)
│   ├── corpus/wiki/          # Downloaded Wikipedia articles
│   ├── chats/                # PA + Cursor sessions for SFT
│   ├── datasets/             # Distillation datasets by task
│   ├── training/             # SFT/DPO export output
│   └── ingest_manifest.json  # Raw/parsed/extracted SHA256 tracking (gitignored)
└── src/shadow_pa/            # Python package
```

## Local LLM (Ollama)

Extraction uses Ollama by default (`qwen2.5:7b`). Start Ollama and pull the model:

```bash
ollama pull qwen2.5:7b
```

Configure in `config/persona.yaml` under `llm:`.

## Privacy

- Raw WhatsApp files and live memory are **gitignored**
- Processing is local-only via Ollama HTTP API
- Review proposals before they enter memory
- Redaction runs automatically on ingest

## License

MIT
