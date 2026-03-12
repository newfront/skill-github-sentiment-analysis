# AGENTS.md — skill-github-sentiment-analysis

This file gives any AI agent full context on this project's purpose, structure, skills, and conventions. Read it before taking any action.

---

## What this project is

A learning project for performing **hybrid sentiment analysis on GitHub issues**. Each issue is analyzed in two stages:

1. **VADER** — fast offline compound score (-1.0 to +1.0)
2. **LLM** — nuanced tone label, freeform sub-label, and one-sentence summary

Two invocation modes exist: a CLI script (external LLM API) and a Cursor agent skill (no API key — the agent is the LLM).

---

## Project structure

```
.cursor/skills/
├── gh-issues/                  # Fetch & analyze issues (CLI + agent)
│   ├── SKILL.md                # Agent instructions for this skill
│   └── scripts/
│       ├── gh_issues.py        # Main CLI — flags: --body --related --sentiment --output --export
│       └── sentiment.py        # Hybrid VADER + LLM pipeline with MLflow tracing
└── gh-sentiment/               # Agent-only sentiment (no API key required)
    ├── SKILL.md                # Agent instructions for this skill
    └── scripts/
        └── vader_score.py      # Standalone VADER scorer — reads file or stdin

.env                            # Local secrets — gitignored, never commit
.env.example                    # Committed template — all supported env vars
requirements.txt                # Python deps: vaderSentiment, mlflow, openai, python-dotenv
```

---

## Skills

### `gh-issues` — Fetch, summarize & optionally analyze issues

**Trigger phrases:** "fetch issues", "get issues from", "show me issues for", "list GitHub issues", GitHub repo URL + question about issues

**Script (CLI):**
```bash
python .cursor/skills/gh-issues/scripts/gh_issues.py <owner/repo> [OPTIONS]

# Flags
--limit N        # default 20
--body           # include issue description
--related        # fetch related PRs + branches
--sentiment      # run hybrid VADER + LLM analysis
--state          # open | closed | all  (default: open)
--output         # markdown | json  (default: markdown)
--export FILE    # write to file
```

**Agent (chat):** Follow the workflow in `.cursor/skills/gh-issues/SKILL.md`.

---

### `gh-sentiment` — Agent-guided sentiment, no API key

**Trigger phrases:** "analyze sentiment", "score these issues", "what's the tone of this issue", "run sentiment without an API key"

**Agent workflow (always follow this order):**
1. Fetch issues: `gh issue list --repo <owner/repo> --limit <N> --state open --json number,title,state,createdAt,author,labels,url,body`
2. Score with VADER: `python .cursor/skills/gh-sentiment/scripts/vader_score.py /tmp/issues.json`
3. For each issue, reason about tone using the vocabulary below and produce `tone_label`, `tone_detail`, `summary`
4. Output a summary table + per-issue Sentiment block (markdown) or enriched JSON

**Tone vocabulary:**

| Label | When to use |
|-------|-------------|
| `neutral` | Factual, no strong emotion, routine request |
| `frustrated` | Pain, blocker, "broken", anger |
| `enthusiastic` | Excitement about a feature, very positive framing |
| `disappointed` | Expectation not met, mild negative without anger |
| `urgent` | Time pressure, production impact, outage |
| `constructive` | Thoughtful improvement proposal, reasoned feature request |

**VADER reasoning guidance:**
- score < -0.3 → skews negative
- score > +0.3 → skews positive
- `bug` label → suggests frustrated/urgent; `enhancement` → constructive/enthusiastic
- Always read the full title + body, not just the score

---

## Sentiment pipeline (script mode)

`sentiment.py` is imported by `gh_issues.py` when `--sentiment` is passed.

```
fetch_issues()
    └── analyze_issues()          @mlflow.trace CHAIN — full batch
            └── _analyze_one()   per issue
                    ├── _vader_score()     offline, no API
                    └── _llm_analyze()    @mlflow.trace LLM — calls provider
```

**LLM providers** (set via `LLM_PROVIDER` env var):

| Value | Default model | Credentials |
|-------|--------------|-------------|
| `openai` (default) | `gpt-4o-mini` | `OPENAI_API_KEY` |
| `anthropic` | `claude-3-haiku-20240307` | `ANTHROPIC_API_KEY` |
| `databricks` | `databricks-meta-llama/Meta-Llama-3.1-70B-Instruct` | `DATABRICKS_HOST` + `DATABRICKS_TOKEN` |
| `cursor` | — | Not valid in script mode — use chat instead |

**Concurrency:** `SENTIMENT_MAX_WORKERS` (default 5) controls parallel LLM calls. MLflow context is propagated across threads via `contextvars.copy_context()` so nested spans stay attached.

---

## Environment & configuration

`.env` is loaded automatically at startup via `python-dotenv`. Shell environment takes precedence over `.env`.

```bash
cp .env.example .env   # then fill in values
```

Key variables:

| Var | Default | Purpose |
|-----|---------|---------|
| `LLM_PROVIDER` | `openai` | Which LLM backend to use |
| `LLM_MODEL` | provider default | Override model name |
| `OPENAI_API_KEY` | — | OpenAI credentials |
| `ANTHROPIC_API_KEY` | — | Anthropic credentials |
| `DATABRICKS_HOST` | — | Databricks workspace URL |
| `DATABRICKS_TOKEN` | — | Databricks PAT |
| `SENTIMENT_MAX_WORKERS` | `5` | Concurrent LLM calls |
| `MLFLOW_TRACKING_URI` | — | Omit to skip tracing |
| `MLFLOW_EXPERIMENT_NAME` | `gh-issues-sentiment` | Experiment for traces |

---

## MLflow tracing

When `MLFLOW_TRACKING_URI` is set, every `--sentiment` script run logs two span types:
- `analyze_issues` **(CHAIN)** — batch level: issue count, provider, worker count
- `_llm_analyze` **(LLM)** — per issue: issue number, title, VADER score, provider

```python
# Verify traces after a run
import mlflow
traces = mlflow.search_traces(experiment_names=["gh-issues-sentiment"])
print(f"Found {len(traces)} trace(s)")
```

---

## JSON output shape

```json
{
  "number": 3,
  "title": "Add the Sentiment Analysis Feature.",
  "labels": [{"name": "enhancement"}],
  "sentiment": {
    "vader_score": 0.1027,
    "tone_label": "constructive",
    "tone_detail": "feature proposal",
    "summary": "Proposes adding LLM-based sentiment tagging to issues as a derived triage label.",
    "llm_provider": "openai"
  }
}
```

---

## Conventions

- All scripts load `.env` via `python-dotenv` at the top — no manual `export` needed in dev
- `vader_score.py` accepts a file path or `-` for stdin — pipe-friendly
- `gh_issues.py --sentiment` automatically fetches `body` — no need to also pass `--body`
- Body is truncated to 2000 chars before sending to the LLM — avoids token bloat on long issues
- `tone_label` is validated against the fixed vocabulary after LLM response; defaults to `neutral` on invalid output
- Never commit `.env` — it is gitignored; commit only `.env.example`
