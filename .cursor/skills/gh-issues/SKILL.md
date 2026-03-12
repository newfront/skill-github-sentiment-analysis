---
name: gh-issues
description: >-
  Fetches, displays, and summarizes GitHub issues from any accessible repository.
  Supports filtering by limit, state, and optionally expanding issue bodies with
  AI summarization, and fetching related open PRs and branches per issue.
  Use when the user asks to fetch issues, list GitHub issues, summarize issues,
  find bugs or feature requests in a repo, or says things like "gh issues",
  "get issues from", "show me issues for", or provides a GitHub repo URL and
  asks about its issues.
---

# GitHub Issues Fetcher

## Quick Start

Two invocation modes are available:

**Script (terminal):**
```bash
# Interactive step-by-step prompting
python .cursor/skills/gh-issues/scripts/gh_issues.py --interactive

# One-liner with flags
python .cursor/skills/gh-issues/scripts/gh_issues.py <repo_url_or_owner/repo> [OPTIONS]
```

**Agent-guided:** Ask in chat — the agent will walk through options and call `gh` directly.

---

## Script flags

| Flag | Default | Description |
|------|---------|-------------|
| `--limit N` | `20` | Number of issues to fetch |
| `--body` | off | Include full issue description |
| `--related` | off | Fetch related open PRs + branches per issue |
| `--state` | `open` | `open` \| `closed` \| `all` |
| `--output` | `markdown` | `markdown` \| `json` |
| `--export FILE` | — | Write output to a file |
| `--interactive` / `-i` | — | Step-by-step terminal prompting |

---

## Examples

```bash
# Last 5 open issues, markdown summary
python .cursor/skills/gh-issues/scripts/gh_issues.py unitycatalog/unitycatalog --limit 5

# Last 10 issues with descriptions and related PRs/branches
python .cursor/skills/gh-issues/scripts/gh_issues.py https://github.com/unitycatalog/unitycatalog --limit 10 --body --related

# Export JSON for downstream processing
python .cursor/skills/gh-issues/scripts/gh_issues.py owner/repo --limit 50 --output json --export issues.json

# Interactive mode
python .cursor/skills/gh-issues/scripts/gh_issues.py -i
```

---

## Agent-Guided Workflow

When the user asks for issues conversationally (not running the script), follow these steps:

### Step 1 — Identify the repo
Parse the repo from whatever the user provides:
- Full URL: `https://github.com/owner/repo` → `owner/repo`
- Shorthand: `owner/repo` → use as-is
- If ambiguous, ask: *"Which GitHub repo? (owner/repo or full URL)"*

### Step 2 — Gather options (ask if not provided)
- **Limit**: default 20; ask if user wants more
- **State**: default `open`; ask if they want closed or all
- **Body**: ask *"Would you like me to expand and summarize each issue's description?"*
- **Related**: ask *"Should I also fetch related open PRs and branches for each issue?"*

### Step 3 — Fetch issues
```bash
gh issue list --repo <owner/repo> --limit <N> --state <state> \
  --json number,title,state,createdAt,author,labels,url,body
```

### Step 4 — Output a summary table
Always start with a compact table:

```
| # | Title | Author | Labels | Created |
|---|-------|--------|--------|---------|
| #123 | ... | user | `bug` | 2026-03-10 |
```

### Step 5 — Per-issue detail (if `--body` requested)
For each issue with a body, **summarize** it in 2-3 sentences rather than dumping the raw text. Focus on:
- What the problem is
- What the expected vs actual behavior is
- Any reproduction steps or environment info mentioned

### Step 6 — Related PRs and branches (if `--related` requested)
For each issue, run:
```bash
# Related PRs
gh pr list --repo <owner/repo> \
  --search "closes #<N> OR fixes #<N> OR resolves #<N>" \
  --json number,title,state,headRefName,url --limit 10

# Related branches (filter refs containing the issue number)
gh api repos/<owner/repo>/git/refs/heads --paginate \
  --jq '[.[] | .ref | ltrimstr("refs/heads/")] | map(select(test("(^|[-/_])<N>([-/_]|$)")))'
```

---

## Output Format

### Markdown (default)
- Summary table at the top
- Per-issue sections with description summary and related items
- Good for reading in chat or saving as a report

### JSON
- Raw `gh` API output; useful for piping to other tools or saving for analysis
- Use `--export issues.json` to write to disk

---

## Requirements

- `gh` CLI installed and authenticated (`gh auth status`)
- Repo must be accessible with your GitHub token
- Python 3.10+ (for script mode)
