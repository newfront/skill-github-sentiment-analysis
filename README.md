# skill-github-sentiment-analysis

Learning to do semantic analysis on a collection of GitHub issues.

## Prerequisites

```bash
# Install the GitHub CLI
brew install gh

# Authenticate
gh auth login
```

---

## Skills

### `gh-issues` — Fetch & Summarize GitHub Issues

Fetch open (or closed) issues from any GitHub repo you have access to, with optional body expansion and related PR/branch discovery.

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

# Filter by state
python .cursor/skills/gh-issues/scripts/gh_issues.py owner/repo --state closed --limit 5

# Export as JSON
python .cursor/skills/gh-issues/scripts/gh_issues.py owner/repo --output json --export issues.json
```

| Flag | Default | Description |
|------|---------|-------------|
| `--limit N` | `20` | Number of issues to fetch |
| `--body` | off | Include full issue description |
| `--related` | off | Fetch related open PRs + branches per issue |
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
6. Output format (markdown / json)
7. Optional file export path

#### In chat (agent-guided)

Just ask naturally in Cursor — the agent will use this skill automatically:

> _"Fetch the last 10 issues from unitycatalog/unitycatalog with descriptions and related PRs"_

> _"Show me the 5 most recent open bugs in owner/repo"_

> _"Get issues from https://github.com/owner/repo and export as JSON"_
