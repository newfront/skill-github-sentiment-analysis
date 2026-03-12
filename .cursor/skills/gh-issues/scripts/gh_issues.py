#!/usr/bin/env python3
"""
gh_issues.py - Fetch and summarize GitHub issues from any accessible repo.

Requires: gh CLI (authenticated)

Usage (flags):
    python gh_issues.py <repo_url_or_owner/repo> [OPTIONS]

    Options:
        --limit N          Number of issues to fetch (default: 20)
        --body             Include full issue body/description
        --related          Fetch related open PRs and branches per issue
        --sentiment        Run hybrid VADER + LLM sentiment analysis on each issue
        --output           markdown | json  (default: markdown)
        --state            open | closed | all (default: open)
        --export FILE      Write output to file

    Sentiment env vars:
        LLM_PROVIDER       openai | anthropic | databricks  (default: openai)
        LLM_MODEL          Model name override
        MLFLOW_TRACKING_URI     MLflow server for tracing (optional)
        MLFLOW_EXPERIMENT_NAME  Experiment to log traces under (optional)

Usage (interactive):
    python gh_issues.py --interactive
    python gh_issues.py   (no args also triggers interactive mode)
"""

import argparse
import json
import os
import re
import subprocess
import sys
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed — env vars must be set manually


def run_gh(args: list[str]) -> list | dict:
    result = subprocess.run(
        ["gh"] + args,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def parse_repo(repo_input: str) -> str:
    """Accept full GitHub URL or owner/repo format."""
    match = re.search(r"github\.com/([^/]+/[^/]+?)(?:\.git|/|$)", repo_input)
    if match:
        return match.group(1)
    if "/" in repo_input and not repo_input.startswith("http"):
        return repo_input.strip()
    raise ValueError(f"Cannot parse repo from: {repo_input!r}")


def fetch_issues(repo: str, limit: int, include_body: bool, state: str, sentiment: bool = False) -> list:
    fields = ["number", "title", "state", "createdAt", "author", "labels", "url"]
    if include_body or sentiment:
        # sentiment always needs body + title to produce a meaningful analysis
        fields += ["body", "comments"]
    return run_gh([
        "issue", "list",
        "--repo", repo,
        "--limit", str(limit),
        "--state", state,
        "--json", ",".join(fields),
    ])


def fetch_related_prs(repo: str, issue_number: int) -> list:
    """Search for PRs that reference this issue via closes/fixes/resolves keywords."""
    try:
        return run_gh([
            "pr", "list",
            "--repo", repo,
            "--search",
            f"closes #{issue_number} OR fixes #{issue_number} OR resolves #{issue_number}",
            "--json", "number,title,state,headRefName,url",
            "--limit", "10",
        ])
    except subprocess.CalledProcessError:
        return []


def fetch_related_branches(repo: str, issue_number: int) -> list[str]:
    """Find branches whose names contain the issue number."""
    try:
        refs = run_gh(["api", f"repos/{repo}/git/refs/heads", "--paginate"])
        pattern = re.compile(rf"(^|[-/_])0*{issue_number}([-/_]|$)")
        return [
            ref["ref"].replace("refs/heads/", "")
            for ref in refs
            if pattern.search(ref["ref"].replace("refs/heads/", ""))
        ]
    except (subprocess.CalledProcessError, KeyError):
        return []


def format_markdown(
    issues: list,
    repo: str,
    include_related: bool,
) -> str:
    lines = [
        f"## GitHub Issues — `{repo}`",
        f"_Showing {len(issues)} issue(s)_\n",
        "| # | Title | Author | State | Labels | Created |",
        "|---|-------|--------|-------|--------|---------|",
    ]
    for issue in issues:
        labels = ", ".join(f"`{l['name']}`" for l in issue.get("labels", [])) or "—"
        lines.append(
            f"| [#{issue['number']}]({issue['url']}) "
            f"| {issue['title']} "
            f"| {issue['author']['login']} "
            f"| {issue['state']} "
            f"| {labels} "
            f"| {issue['createdAt'][:10]} |"
        )

    lines.append("")

    for issue in issues:
        lines.append(f"---\n### #{issue['number']} — {issue['title']}")
        lines.append(f"**URL**: {issue['url']}  ")
        lines.append(f"**Author**: {issue['author']['login']} | **Created**: {issue['createdAt'][:10]} | **State**: {issue['state']}")

        labels = ", ".join(f"`{l['name']}`" for l in issue.get("labels", [])) or "—"
        lines.append(f"**Labels**: {labels}\n")

        if "body" in issue and issue.get("body"):
            body = issue["body"].strip()
            lines.append("**Description:**")
            lines.append(f"> {body.replace(chr(10), chr(10) + '> ')}\n")

        sentiment = issue.get("sentiment")
        if sentiment:
            score = sentiment["vader_score"]
            tone = sentiment["tone_label"]
            detail = sentiment.get("tone_detail", "")
            summary = sentiment.get("summary", "")
            provider = sentiment.get("llm_provider", "")
            tone_display = f"{tone}" + (f" — {detail}" if detail else "")
            lines.append("**Sentiment:**")
            lines.append(f"- Tone: `{tone_display}`")
            lines.append(f"- VADER score: `{score:+.4f}`")
            if summary:
                lines.append(f"- Summary: {summary}")
            if provider:
                lines.append(f"- _(via {provider})_")
            lines.append("")

        if include_related:
            prs = fetch_related_prs(repo, issue["number"])
            branches = fetch_related_branches(repo, issue["number"])
            if prs:
                lines.append("**Related PRs:**")
                for pr in prs:
                    branch = pr.get("headRefName", "—")
                    lines.append(f"- [#{pr['number']}] {pr['title']} (`{branch}`) — **{pr['state']}** — {pr['url']}")
            if branches:
                lines.append("**Related Branches:**")
                for b in branches:
                    lines.append(f"- `{b}`")
            if not prs and not branches:
                lines.append("_No related PRs or branches found._")
            lines.append("")

    return "\n".join(lines)


def interactive_mode() -> tuple:
    print("=== GitHub Issues Fetcher ===\n")

    repo_input = input("GitHub repo URL or owner/repo: ").strip()
    repo = parse_repo(repo_input)

    raw_limit = input("Issues to fetch [20]: ").strip()
    limit = int(raw_limit) if raw_limit.isdigit() else 20

    raw_state = input("Issue state — open / closed / all [open]: ").strip().lower()
    state = raw_state if raw_state in ("open", "closed", "all") else "open"

    include_body = input("Include full issue description? [y/N]: ").strip().lower() == "y"
    include_related = input("Fetch related PRs and branches? [y/N]: ").strip().lower() == "y"
    run_sentiment = input("Run sentiment analysis? [y/N]: ").strip().lower() == "y"

    raw_fmt = input("Output format — markdown / json [markdown]: ").strip().lower()
    output_format = raw_fmt if raw_fmt in ("json", "markdown") else "markdown"

    export_file = input("Export to file? Enter path or leave blank: ").strip() or None

    return repo, limit, state, include_body, include_related, run_sentiment, output_format, export_file


def _setup_mlflow() -> None:
    """Configure MLflow from env vars if set; silently skip if mlflow not installed."""
    try:
        import mlflow  # noqa: F401 — already imported at module level in sentiment.py
        tracking_uri = os.environ.get("MLFLOW_TRACKING_URI")
        experiment_name = os.environ.get("MLFLOW_EXPERIMENT_NAME", "gh-issues-sentiment")
        if tracking_uri:
            mlflow.set_tracking_uri(tracking_uri)
        if not os.environ.get("MLFLOW_EXPERIMENT_ID"):
            mlflow.set_experiment(experiment_name)
    except ImportError:
        pass


def main():
    parser = argparse.ArgumentParser(
        description="Fetch and summarize GitHub issues from any accessible repo."
    )
    parser.add_argument("repo", nargs="?", help="GitHub repo URL or owner/repo")
    parser.add_argument("--limit", type=int, default=20, help="Number of issues (default: 20)")
    parser.add_argument("--body", action="store_true", help="Include issue body/description")
    parser.add_argument("--related", action="store_true", help="Fetch related PRs and branches")
    parser.add_argument("--sentiment", action="store_true", help="Run hybrid sentiment analysis")
    parser.add_argument("--output", choices=["markdown", "json"], default="markdown")
    parser.add_argument("--state", choices=["open", "closed", "all"], default="open")
    parser.add_argument("--export", metavar="FILE", help="Write output to a file")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive mode")

    args = parser.parse_args()

    if args.interactive or not args.repo:
        repo, limit, state, include_body, include_related, run_sentiment, output_format, export_file = (
            interactive_mode()
        )
    else:
        repo = parse_repo(args.repo)
        limit = args.limit
        state = args.state
        include_body = args.body
        include_related = args.related
        run_sentiment = args.sentiment
        output_format = args.output
        export_file = args.export

    print(f"\nFetching {limit} {state} issues from {repo}...\n", file=sys.stderr)

    try:
        issues = fetch_issues(repo, limit, include_body, state, sentiment=run_sentiment)
    except subprocess.CalledProcessError as e:
        print(f"Error: gh CLI failed — {e.stderr.strip()}", file=sys.stderr)
        sys.exit(1)

    if run_sentiment:
        try:
            from sentiment import analyze_issues  # noqa: PLC0415
        except ImportError as e:
            print(
                f"Error: sentiment dependencies not installed — {e}\n"
                "Run: pip install vaderSentiment mlflow openai",
                file=sys.stderr,
            )
            sys.exit(1)

        _setup_mlflow()
        print("Running sentiment analysis...\n", file=sys.stderr)
        issues = analyze_issues(issues)

    if output_format == "json":
        output = json.dumps(issues, indent=2)
    else:
        output = format_markdown(issues, repo, include_related)

    if export_file:
        with open(export_file, "w") as f:
            f.write(output)
        print(f"Exported to {export_file}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
