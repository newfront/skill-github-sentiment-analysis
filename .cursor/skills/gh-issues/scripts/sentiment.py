#!/usr/bin/env python3
"""
sentiment.py - Hybrid sentiment analysis for GitHub issues.

Pipeline per issue:
  1. VADER   — fast offline compound score (-1.0 to +1.0)
  2. LLM     — nuanced fixed tone label + freeform sub-label + 1-sentence summary

LLM provider is selected via env vars:
  LLM_PROVIDER  = openai | anthropic | databricks  (default: openai)
  LLM_MODEL     = model name                        (default: provider default)
  OPENAI_API_KEY / ANTHROPIC_API_KEY / DATABRICKS_HOST + DATABRICKS_TOKEN

MLflow tracing is applied to:
  - The root `analyze_issues` call (CHAIN span — full batch)
  - Each `_llm_analyze` call (LLM span — per issue)

Usage:
    from sentiment import analyze_issues
    enriched = analyze_issues(issues)
"""

import asyncio
import contextvars
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed — env vars must be set manually

import mlflow
from mlflow.entities import SpanType
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TONE_LABELS = [
    "neutral",
    "frustrated",
    "enthusiastic",
    "disappointed",
    "urgent",
    "constructive",
]

_PROVIDER = os.environ.get("LLM_PROVIDER", "openai").lower()
_MAX_WORKERS = int(os.environ.get("SENTIMENT_MAX_WORKERS", "5"))

_SYSTEM_PROMPT = """\
You are a GitHub issue sentiment analyst. Analyze the provided issue and return \
a JSON object with exactly these fields:
  "tone_label"  — one of: neutral, frustrated, enthusiastic, disappointed, urgent, constructive
  "tone_detail" — a 1-3 word freeform descriptor that refines the primary label (e.g. "mildly critical")
  "summary"     — a single sentence summarising what the issue is asking for or reporting

Respond with raw JSON only — no markdown fences, no extra text.\
"""


# ---------------------------------------------------------------------------
# LLM client helpers (lazy-loaded to avoid import errors when not used)
# ---------------------------------------------------------------------------

def _build_user_message(issue: dict, vader_score: float) -> str:
    title = issue.get("title", "")
    body = (issue.get("body") or "").strip()
    labels = ", ".join(l["name"] for l in issue.get("labels", [])) or "none"
    text = f"Title: {title}"
    if body:
        # Truncate very long bodies — LLMs don't need the full wall of text
        text += f"\n\nBody:\n{body[:2000]}"
    text += f"\n\nGitHub labels: {labels}"
    text += f"\nVADER compound score: {vader_score:.3f}"
    return text


def _call_openai(user_message: str) -> str:
    from openai import OpenAI  # type: ignore
    model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
    client = OpenAI()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )
    return response.choices[0].message.content


def _call_anthropic(user_message: str) -> str:
    import anthropic  # type: ignore
    model = os.environ.get("LLM_MODEL", "claude-3-haiku-20240307")
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=256,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    return response.content[0].text


def _call_databricks(user_message: str) -> str:
    from openai import OpenAI  # type: ignore
    model = os.environ.get("LLM_MODEL", "databricks-meta-llama/Meta-Llama-3.1-70B-Instruct")
    host = os.environ["DATABRICKS_HOST"].rstrip("/")
    token = os.environ["DATABRICKS_TOKEN"]
    client = OpenAI(
        base_url=f"{host}/serving-endpoints",
        api_key=token,
    )
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0,
    )
    return response.choices[0].message.content


def _call_cursor(_user_message: str) -> str:
    raise RuntimeError(
        "LLM_PROVIDER=cursor is not supported in script mode.\n"
        "To use the Cursor agent as the LLM, ask me in chat instead — "
        "the 'gh-sentiment' skill handles the full pipeline conversationally."
    )


_PROVIDER_MAP = {
    "openai": _call_openai,
    "anthropic": _call_anthropic,
    "databricks": _call_databricks,
    "cursor": _call_cursor,
}


# ---------------------------------------------------------------------------
# Core analysis functions
# ---------------------------------------------------------------------------

_vader = SentimentIntensityAnalyzer()


def _vader_score(issue: dict) -> float:
    """Combine title + body into one text block and return VADER compound score."""
    title = issue.get("title", "")
    body = (issue.get("body") or "").strip()
    text = f"{title}. {body}" if body else title
    return _vader.polarity_scores(text)["compound"]


@mlflow.trace(span_type=SpanType.LLM)
def _llm_analyze(issue: dict, vader_score: float) -> dict:
    """Call the configured LLM provider and parse the JSON response."""
    import json as _json

    user_message = _build_user_message(issue, vader_score)
    call_fn = _PROVIDER_MAP.get(_PROVIDER)
    if call_fn is None:
        raise ValueError(
            f"Unknown LLM_PROVIDER={_PROVIDER!r}. "
            f"Choose from: {list(_PROVIDER_MAP)}"
        )

    raw = call_fn(user_message)

    try:
        parsed = _json.loads(raw)
    except _json.JSONDecodeError:
        # Graceful fallback if the model doesn't return clean JSON
        parsed = {
            "tone_label": "neutral",
            "tone_detail": "unparseable response",
            "summary": raw.strip()[:200],
        }

    # Validate tone_label against the fixed vocabulary
    if parsed.get("tone_label") not in TONE_LABELS:
        parsed["tone_label"] = "neutral"

    span = mlflow.get_current_active_span()
    if span:
        span.set_attributes({
            "issue.number": issue.get("number", -1),
            "issue.title": issue.get("title", ""),
            "vader.compound": vader_score,
            "llm.provider": _PROVIDER,
        })

    return parsed


def _analyze_one(issue: dict) -> dict:
    """Run the full hybrid pipeline for a single issue and return enriched dict."""
    vader = _vader_score(issue)
    llm_result = _llm_analyze(issue, vader)
    return {
        **issue,
        "sentiment": {
            "vader_score": round(vader, 4),
            "tone_label": llm_result.get("tone_label", "neutral"),
            "tone_detail": llm_result.get("tone_detail", ""),
            "summary": llm_result.get("summary", ""),
            "llm_provider": _PROVIDER,
        },
    }


@mlflow.trace(name="analyze_issues", span_type=SpanType.CHAIN)
def analyze_issues(issues: list[dict]) -> list[dict]:
    """
    Run hybrid sentiment analysis concurrently over a list of GitHub issues.

    Each issue is enriched with a `sentiment` dict containing:
      - vader_score   : float, -1.0 to +1.0
      - tone_label    : fixed-vocabulary primary label
      - tone_detail   : freeform 1-3 word sub-label from LLM
      - summary       : 1-sentence summary from LLM
      - llm_provider  : which provider was used
    """
    if not issues:
        return issues

    span = mlflow.get_current_active_span()
    if span:
        span.set_attributes({
            "issue.count": len(issues),
            "llm.provider": _PROVIDER,
            "sentiment.max_workers": _MAX_WORKERS,
        })

    ctx = contextvars.copy_context()

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        futures = [
            executor.submit(ctx.run, _analyze_one, issue)
            for issue in issues
        ]
        results = [f.result() for f in futures]

    return results
