# shadow-pa UI (IBM Carbon)

React + [Carbon Design System](https://carbondesignsystem.com/) control panel for memory review, ingest, server, and training policies.

## Setup

Requires Node.js 18+.

```bash
cd ui
npm install
npm run build
```

## Run

**Production (single server):**

```bash
# from project root
pip install -e ".[ui]"
shadow-pa ui run
# → http://127.0.0.1:8787
```

**Development (hot reload):**

```bash
# terminal 1
shadow-pa ui run --dev

# terminal 2
cd ui && npm run dev
# → http://127.0.0.1:5173 (proxies /api to 8787)
```

## Pages

| Page | Purpose |
|------|---------|
| Dashboard | Ollama status, pending proposals, memory counts |
| Memory review | Approve / reject proposals (Carbon tiles) |
| Live memory | Profile, preferences, episodes tables |
| Ingest | Per-source raw/parsed counts, trigger parse |
| Server | Ingest server token + curl examples |
| Policies | Edit `config/training_policy.yaml` toggles |
