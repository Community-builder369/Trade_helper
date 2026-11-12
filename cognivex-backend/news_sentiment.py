"""Explainable, rule-based financial headline sentiment for CR Cognivex.

No scraping, text storage, market-data fetching, price forecasting or advice.
Callers must have rights to supply the headlines and links. Scores are heuristic,
not calibrated AI probabilities or future price predictions.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator

POSITIVE = {
    "profit rises": 3, "profit grows": 3, "profit increases": 3,
    "profits rise": 3, "profits grow": 3,
    "revenue rises": 2, "revenue grows": 2, "revenue increases": 2,
    "earnings beat": 3, "beats estimates": 3, "beat estimates": 3,
    "above estimates": 2, "record profit": 3, "record earnings": 3,
    "upgrades guidance": 3, "raises guidance": 3,
    "dividend increase": 2, "dividend raised": 2,
    "wins contract": 2, "wins order": 2, "secures contract": 2,
    "debt reduced": 2, "debt falls": 2,
    "expands capacity": 1, "strong demand": 2, "growth accelerates": 2,
}
NEGATIVE = {
    "profit falls": 3, "profit declines": 3, "profit drops": 3,
    "profits fall": 3, "profits decline": 3,
    "revenue falls": 2, "revenue declines": 2, "revenue drops": 2,
    "earnings miss": 3, "misses estimates": 3, "below estimates": 2,
    "net loss": 3, "quarterly loss": 3, "reports loss": 3,
    "cuts guidance": 3, "lowers guidance": 3, "profit warning": 3,
    "dividend cut": 2, "cuts dividend": 2,
    "debt rises": 2, "debt increases": 2,
    "regulatory fine": 2, "regulatory probe": 2,
    "fraud allegations": 3, "plant shutdown": 2,
    "weak demand": 2, "demand slows": 2,
}
NEGATORS = {"not", "no", "never", "without", "fails", "failed", "doesnt", "didnt"}
WORD_RE = re.compile(r"[a-z0-9]+")


class Headline(BaseModel):
    title: str = Field(min_length=8, max_length=240)
    source_url: str = Field(min_length=12, max_length=500)
    publisher: str | None = Field(default=None, max_length=100)
    published_at: datetime | None = None

    @field_validator("source_url")
    @classmethod
    def check_source_url(cls, value: str) -> str:
        try:
            parsed = urlsplit(value.strip())
            if (parsed.scheme.lower() != "https" or not parsed.hostname
                    or parsed.username or parsed.password
                    or any(char in value for char in "\r\n\t")):
                raise ValueError
        except ValueError as exc:
            raise ValueError("source_url must be a valid HTTPS article URL") from exc
        return value.strip()

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        title = " ".join(value.split())
        if len(title) < 8:
            raise ValueError("Headline is too short")
        return title


class NewsSentimentRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)
    headlines: list[Headline] = Field(min_length=1, max_length=10)


def score_headline(title: str) -> dict[str, Any]:
    """Return phrase-based financial signals or insufficient_signal."""
    words = WORD_RE.findall(title.lower())
    matches = []
    phrases = sorted(
        [(phrase, weight, 1) for phrase, weight in POSITIVE.items()]
        + [(phrase, weight, -1) for phrase, weight in NEGATIVE.items()],
        key=lambda entry: -len(entry[0]),
    )
    occupied: set[int] = set()
    for phrase, weight, polarity in phrases:
        tokens = phrase.split()
        for index in range(len(words) - len(tokens) + 1):
            span = set(range(index, index + len(tokens)))
            if span & occupied or words[index:index + len(tokens)] != tokens:
                continue
            negated = any(w in NEGATORS for w in words[max(0, index - 3):index])
            effect = "negative" if polarity * (-1 if negated else 1) < 0 else "positive"
            matches.append({"term": phrase, "effect": effect})
            occupied.update(span)
    positive = sum(POSITIVE.get(m["term"], NEGATIVE.get(m["term"], 0))
                   for m in matches if m["effect"] == "positive")
    negative = sum(POSITIVE.get(m["term"], NEGATIVE.get(m["term"], 0))
                   for m in matches if m["effect"] == "negative")
    total = positive + negative
    if total == 0:
        return {"label": "insufficient_signal", "score": None, "signals": []}
    score = round(100 * (positive - negative) / (total + 1))
    label = "positive" if score >= 20 else "negative" if score <= -20 else "neutral"
    return {"label": label, "score": score, "signals": matches}


def analyse_news(ticker: str, headlines: list[Headline]) -> dict[str, Any]:
    articles = []
    scores = []
    for article in headlines:
        sentiment = score_headline(article.title)
        if sentiment["score"] is not None:
            scores.append(sentiment["score"])
        articles.append({
            "title": article.title,
            "source_url": article.source_url,
            "publisher": article.publisher,
            "published_at": article.published_at.isoformat() if article.published_at else None,
            **sentiment,
        })
    overall = round(sum(scores) / len(scores)) if scores else None
    label = ("insufficient_signal" if overall is None else
             "positive" if overall >= 20 else
             "negative" if overall <= -20 else "neutral")
    return {
        "ticker": ticker,
        "analysed_at": datetime.now(timezone.utc).isoformat(),
        "method": "rule_based_headline_lexicon_v1",
        "overall_label": label,
        "overall_score": overall,
        "headlines_received": len(headlines),
        "headlines_scored": len(scores),
        "articles": articles,
        "disclaimer": (
            "Heuristic headline classification only; not an AI probability, "
            "price prediction, or investment recommendation. Source data must "
            "be supplied with appropriate usage rights."
        ),
    }
