# skill-github-sentiment-analysis

Learning to do sentiment analysis on a collection of GitHub issues.

Supports two modes — a CLI script (with external LLM) and a Cursor agent skill (no API key needed).

---

## Prerequisites

```bash
# Install the GitHub CLI
brew install gh

# Authenticate
gh auth login

# Install Python dependencies
pip install -r requirements.txt

# Set up your environment
cp .env.example .env
# Edit .env and fill in your values — it's gitignored, never committed
```

---

## Project Structure

```
.cursor/skills/
├── gh-issues/                  # Fetch & analyze issues (CLI + agent)
│   ├── SKILL.md                # Agent instructions
│   └── scripts/
│       ├── gh_issues.py        # Main CLI script
│       └── sentiment.py        # Hybrid VADER + LLM sentiment pipeline
└── gh-sentiment/               # Agent-only sentiment skill (no API key)
    ├── SKILL.md                # Agent instructions
    └── scripts/
        └── vader_score.py      # Offline VADER scoring helper

.env.example                    # Committed template — copy to .env
requirements.txt
```

---

## Skills

### `gh-issues` — Fetch, Summarize & Analyze GitHub Issues

Fetch open (or closed) issues from any GitHub repo you have access to, with optional body expansion, related PR/branch discovery, and hybrid sentiment analysis.

#### Terminal — flags

```bash
# Basic: last 20 open issues (default)
python .cursor/skills/gh-issues/scripts/gh_issues.py owner/repo

# Full GitHub URL works too
python .cursor/skills/gh-issues/scripts/gh_issues.py https://github.com/owner/repo --limit 10

# Expand issue descriptions
python .cursor/skills/gh-issues/scripts/gh_issues.py owner/repo --limit 10 --body

# Add related open PRs and branches per issue
python .cursor/skills/gh-issues/scripts/gh_issues.py owner/repo --limit 10 --body --related

# Run sentiment analysis on each issue (hybrid VADER + LLM)
python .cursor/skills/gh-issues/scripts/gh_issues.py owner/repo --sentiment --output json

# Combine everything
python .cursor/skills/gh-issues/scripts/gh_issues.py owner/repo \
  --limit 10 --body --related --sentiment --output json --export enriched.json

# Filter by state
python .cursor/skills/gh-issues/scripts/gh_issues.py owner/repo --state closed --limit 5
```

| Flag | Default | Description |
|------|---------|-------------|
| `--limit N` | `20` | Number of issues to fetch |
| `--body` | off | Include full issue body/description |
| `--related` | off | Fetch related open PRs + branches per issue |
| `--sentiment` | off | Run hybrid VADER + LLM sentiment analysis |
| `--state` | `open` | `open` \| `closed` \| `all` |
| `--output` | `markdown` | `markdown` \| `json` |
| `--export FILE` | — | Write output to a file |

#### Terminal — interactive mode

Step-by-step prompts guide you through all options:

```bash
python .cursor/skills/gh-issues/scripts/gh_issues.py --interactive
# or shorthand:
python .cursor/skills/gh-issues/scripts/gh_issues.py -i
```

You'll be prompted for:
1. Repo URL or `owner/repo`
2. Number of issues (default: 20)
3. State filter (open / closed / all)
4. Whether to include descriptions
5. Whether to fetch related PRs and branches
6. Whether to run sentiment analysis
7. Output format (markdown / json)
8. Optional file export path

#### In chat (agent-guided)

Just ask naturally in Cursor — the agent picks up the `gh-issues` skill automatically:

> _"Fetch the last 10 issues from unitycatalog/unitycatalog with descriptions and related PRs"_

> _"Show me the 5 most recent open bugs in owner/repo"_

> _"Get issues from https://github.com/owner/repo and run sentiment analysis, export as JSON"_

---

### `gh-sentiment` — Agent-Guided Sentiment Analysis (no API key)

A dedicated skill that lets the Cursor agent perform the full sentiment pipeline conversationally. The agent fetches issues with `gh`, runs VADER offline, and performs the nuanced tone analysis itself — no external LLM API key required.

#### In chat

Just ask in Cursor:

> _"Analyze the sentiment of the open issues in newfront/skill-github-sentiment-analysis"_

> _"Score the tone of the last 5 issues in owner/repo and export as JSON"_

The agent will:
1. Fetch issues via `gh issue list`
2. Run `vader_score.py` to produce numeric compound scores
3. Reason about tone, sub-label, and a one-sentence summary for each issue
4. Return enriched markdown or JSON

#### `vader_score.py` — standalone VADER scorer

The helper script can also be used directly to add VADER scores to any issues JSON:

```bash
# Score from a file
python .cursor/skills/gh-sentiment/scripts/vader_score.py issues.json

# Score from stdin (pipe from gh CLI)
gh issue list --repo owner/repo --json number,title,body \
  | python .cursor/skills/gh-sentiment/scripts/vader_score.py -
```

Outputs the same JSON array with a `vader_score` field added to each issue.

---

## Sentiment Analysis

### How the hybrid pipeline works

Every issue goes through two stages:

**Stage 1 — VADER (offline)**
[VADER](https://github.com/cjhutto/vaderSentiment) produces a **compound score** from -1.0 (most negative) to +1.0 (most positive). Fast, free, no API calls required. The score is passed to the LLM as a grounding signal.

**Stage 2 — LLM (nuanced)**
The configured LLM (or the Cursor agent in chat mode) returns:

| Field | Description |
|-------|-------------|
| `tone_label` | Fixed vocabulary: `neutral` `frustrated` `enthusiastic` `disappointed` `urgent` `constructive` |
| `tone_detail` | Freeform 1-3 word sub-label (e.g. `mildly critical`, `cautiously optimistic`) |
| `summary` | One sentence summarising what the issue asks for or reports |

In script mode, issues are processed **concurrently** (default 5 workers) to minimise total wall-clock time.

### Choosing a mode

| Mode | How to invoke | API key needed? |
|------|---------------|-----------------|
| **Script** (`--sentiment`) | CLI via `gh_issues.py` | Yes — OpenAI / Anthropic / Databricks |
| **Agent** (Cursor chat) | Ask me in chat | No — Cursor agent is the LLM |

### JSON output shape

```json
{
  "number": 3,
  "title": "Add the Sentiment Analysis Feature.",
  "labels": [{"name": "enhancement"}],
  "sentiment": {
    "vader_score": 0.1027,
    "tone_label": "constructive",
    "tone_detail": "feature proposal",
    "summary": "Proposes adding LLM-based sentiment tagging to GitHub issues as a derived label for triage prioritization.",
    "llm_provider": "openai"
  }
}
```

---

## Configuration

All values can be set in `.env` (copied from `.env.example`) or as regular environment variables. Shell environment always takes precedence over `.env`.

```bash
cp .env.example .env
# then edit .env
```

| Env var | Default | Description |
|---------|---------|-------------|
| `LLM_PROVIDER` | `openai` | `openai` \| `anthropic` \| `databricks` \| `cursor`* |
| `LLM_MODEL` | provider default | Override model name (e.g. `gpt-4o-mini`, `claude-3-haiku-20240307`) |
| `OPENAI_API_KEY` | — | Required for `openai` provider |
| `ANTHROPIC_API_KEY` | — | Required for `anthropic` provider |
| `DATABRICKS_HOST` | — | Required for `databricks` provider |
| `DATABRICKS_TOKEN` | — | Required for `databricks` provider |
| `SENTIMENT_MAX_WORKERS` | `5` | Concurrent LLM calls per script run |
| `MLFLOW_TRACKING_URI` | — | MLflow server URI — omit to skip tracing |
| `MLFLOW_EXPERIMENT_NAME` | `gh-issues-sentiment` | Experiment name (if `MLFLOW_EXPERIMENT_ID` not set) |

_\* `LLM_PROVIDER=cursor` is not valid in script mode — use the `gh-sentiment` agent skill in Cursor chat instead._

---

## MLflow Tracing

When `MLFLOW_TRACKING_URI` is set, every `--sentiment` script run is automatically traced:

- **`analyze_issues` span** (CHAIN) — covers the full batch with issue count, provider, and worker count
- **`_llm_analyze` span** (LLM) — one per issue, capturing issue number/title, VADER score, and provider

```bash
# View traces after a run
python - <<'EOF'
import mlflow
traces = mlflow.search_traces(experiment_names=["gh-issues-sentiment"])
print(f"Found {len(traces)} trace(s)")
EOF
```
