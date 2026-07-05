# Summarization datasets

## Wikipedia (built-in)

```bash
# Quick sample via Wikipedia API (no extra deps)
shadow-pa ingest wiki --limit 500 --lang en

# Large corpus via Hugging Face
pip install 'shadow-pa[corpus]'
shadow-pa ingest wiki --hf --limit 10000 --lang en

# Build JSONL (add --label for local Ollama summaries)
shadow-pa dataset prepare-summarization --lang en --label

# Copy to training export
shadow-pa export summarization --lang en
```

Output: `data/datasets/summarization/wiki_en.jsonl`

Schema:

```json
{
  "messages": [
    {"role": "system", "content": "Task: summarization..."},
    {"role": "user", "content": "Summarize...\n\nTitle: ...\n\n..."},
    {"role": "assistant", "content": "..."}
  ],
  "document": "...",
  "title": "...",
  "metadata": {"task": "summarization", "source": "wikipedia", "labeled": true}
}
```

Unlabeled rows (without `--label`) are documents ready for a teacher model later.
