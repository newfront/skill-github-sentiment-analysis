---
name: gh-sentiment
description: >-
  Fetches GitHub issues and performs hybrid sentiment analysis using VADER (offline
  scoring) and the Cursor agent as the LLM (no API key required). Produces a
  sentiment-enriched JSON or markdown report per issue: tone label, tone detail,
  and a one-sentence summary. Use when the user asks to analyze sentiment of GitHub
  issues, score issue tone, classify issue mood, summarize issues with sentiment,
  or says things like "analyze sentiment", "score these issues", "what's the tone
  of this issue", or "run sentiment analysis without an API key".
---

# GitHub Issue Sentiment Analysis (Agent-Guided)

Performs hybrid sentiment analysis on GitHub issues using VADER for a fast numeric
score and the Cursor agent for nuanced tone classification — no external LLM API key needed.

## Quick Start

```bash
# 1. Fetch issues as JSON
gh issue list --repo <owner/repo> --limit <N> --state open \
  --json number,title,state,createdAt,author,labels,url,body \
  > /tmp/issues.json

# 2. Score each issue with VADER
python .cursor/skills/gh-sentiment/scripts/vader_score.py /tmp/issues.json \
  > /tmp/issues_scored.json

# 3. Agent performs nuanced analysis (see Agent Workflow below)
```

## Agent Workflow

When the user asks for sentiment analysis on GitHub issues, follow these steps:

### Step 1 — Resolve the repo

Parse from whatever the user provides:
- Full URL: `https://github.com/owner/repo` → `owner/repo`
- Shorthand: `owner/repo` → use as-is
- If ambiguous, ask

### Step 2 — Fetch issues

```bash
gh issue list --repo <owner/repo> --limit <N> --state open \
  --json number,title,state,createdAt,author,labels,url,body
```

If `--limit` not specified, default to 20.

### Step 3 — Run VADER scoring

```bash
python .cursor/skills/gh-sentiment/scripts/vader_score.py - <<'JSON'
<paste issues JSON here>
JSON
```

Or pipe from a file:

```bash
python .cursor/skills/gh-sentiment/scripts/vader_score.py /tmp/issues.json
```

The script outputs the same issues array with a `vader_score` field added to each.

### Step 4 — Agent performs nuanced analysis

For each issue in the VADER-scored output, reason about the issue text and produce:

| Field | Description |
|-------|-------------|
| `tone_label` | One of: `neutral` `frustrated` `enthusiastic` `disappointed` `urgent` `constructive` |
| `tone_detail` | 1-3 word freeform sub-label (e.g. `mildly critical`, `feature proposal`) |
| `summary` | Single sentence — what the issue asks for or reports |

**Reasoning guidance:**
- Use `vader_score` as a grounding signal: < -0.3 skews negative, > 0.3 skews positive
- Read the full title and body, not just the score
- Labels like `bug` suggest frustration/urgency; `enhancement` suggests constructive/enthusiastic
- Match the fixed `tone_label` vocabulary; use `tone_detail` for nuance
- Keep `summary` to one sentence; focus on the core ask or problem

### Step 5 — Output

Merge the agent's analysis into each issue and produce the final output.

**JSON shape per issue:**
```json
{
  "number": 3,
  "title": "...",
  "labels": [{"name": "enhancement"}],
  "sentiment": {
    "vader_score": 0.1027,
    "tone_label": "constructive",
    "tone_detail": "feature proposal",
    "summary": "Proposes adding LLM-based sentiment tagging to issues as a derived triage label.",
    "llm_provider": "cursor-agent"
  }
}
```

**Markdown output:** Render a summary table followed by per-issue sections matching the
format used by the `gh-issues` skill, with a **Sentiment** block appended to each issue.

### Step 6 — Optional export

If the user wants to save the output:
```bash
# Agent writes final JSON to disk
```
Ask: _"Would you like me to export this to a file?"_ — if yes, write to the provided path.

---

## Tone vocabulary reference

| Label | When to use |
|-------|-------------|
| `neutral` | Factual report, no strong emotion, routine request |
| `frustrated` | Expresses pain, blocker, "broken", anger |
| `enthusiastic` | Excitement about a feature, very positive framing |
| `disappointed` | Expectation not met, mild negative without anger |
| `urgent` | Time pressure, production impact, "ASAP", outage |
| `constructive` | Thoughtful improvement proposal, reasoned feature request |

---

## Requirements

- `gh` CLI installed and authenticated
- Python 3.10+ with `vaderSentiment` installed (`pip install vaderSentiment`)
- No LLM API key needed — the Cursor agent provides the nuanced analysis
