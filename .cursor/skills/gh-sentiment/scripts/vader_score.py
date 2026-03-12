#!/usr/bin/env python3
"""
vader_score.py - Add VADER compound scores to a JSON array of GitHub issues.

Reads from a file path argument or stdin ("-"), writes scored JSON to stdout.

Usage:
    python vader_score.py issues.json
    python vader_score.py -          # read from stdin
    gh issue list --repo owner/repo --json number,title,body | python vader_score.py -
"""

import json
import sys

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer


def score_issues(issues: list[dict]) -> list[dict]:
    analyzer = SentimentIntensityAnalyzer()
    for issue in issues:
        title = issue.get("title", "")
        body = (issue.get("body") or "").strip()
        text = f"{title}. {body}" if body else title
        issue["vader_score"] = round(analyzer.polarity_scores(text)["compound"], 4)
    return issues


def main():
    if len(sys.argv) < 2 or sys.argv[1] == "-":
        raw = sys.stdin.read()
    else:
        with open(sys.argv[1]) as f:
            raw = f.read()

    issues = json.loads(raw)
    if not isinstance(issues, list):
        print("Error: expected a JSON array of issues", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(score_issues(issues), indent=2))


if __name__ == "__main__":
    main()
