"""GDELT Project DOC 2.0 company-news retrieval for the CR Cognivex prototype.

Uses only GDELT article-index metadata, never scrapes publisher pages.
GDELT Project usage: https://www.gdeltproject.org/about.html
This is not the separate GDELT Cloud commercial product.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from threading import Lock
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from news_sentiment import Headline, analyse_news
from stock_catalog import POPULAR_NSE, POPULAR_BSE

ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"
TTL_SECONDS = 1200
MIN_QUERY_INTERVAL = 6.0
_cache: dict[str, tuple[float, dict]] = {}
_cache_lock = Lock()
_upstream_lock = Lock()
_last_query_at = 0.0

class NewsProviderError(RuntimeError):
    pass


def _parse_gdelt_date(value: str | None):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _title_mentions_company(title: str, company: str) -> bool:
    """Don't attribute a story about another company just because search matched its body."""
    simplified_title = re.sub(r"[^a-z0-9]+", " ", title.casefold()).strip()
    simplified_company = re.sub(r"[^a-z0-9]+", " ", company.casefold()).strip()
    if not simplified_company:
        return False
    # For ambiguous single words, require a stock-market phrase as context.
    if " " not in simplified_company:
        return (bool(re.search(r"\b" + re.escape(simplified_company) + r"\b", simplified_title))
                and bool(re.search(r"\b(stock|stocks|shares|earnings|profit|revenue|investors|nse|bse)\b", simplified_title)))
    return bool(re.search(r"\b" + re.escape(simplified_company) + r"\b", simplified_title))


def _fetch_gdelt(company: str) -> list[Headline]:
    global _last_query_at
    query = '"' + company.replace('"', "") + '" sourcelang:english'
    params = urlencode({
        "query": query,
        "mode": "artlist",
        "format": "json",
        "maxrecords": 50,
        "timespan": "7d",
        "sort": "datedesc",
    })
    # Serialise upstream calls to respect DOC API pacing and avoid bursts.
    with _upstream_lock:
        remaining = MIN_QUERY_INTERVAL - (time.monotonic() - _last_query_at)
        if remaining > 0:
            time.sleep(remaining)
        _last_query_at = time.monotonic()
        req = Request(ENDPOINT + "?" + params, headers={
            "Accept": "application/json",
            "User-Agent": "CR-Cognivex-Research/1.0 (GDELT attribution: gdeltproject.org)",
        })
        try:
            with urlopen(req, timeout=12) as response:
                if "json" not in response.headers.get("Content-Type", "").lower():
                    raise NewsProviderError("GDELT returned a non-JSON response.")
                payload = json.load(response)
        except HTTPError as exc:
            raise NewsProviderError(f"GDELT news search unavailable (HTTP {exc.code}).") from exc
        except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
            raise NewsProviderError("GDELT news search is temporarily unavailable.") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("articles", []), list):
        raise NewsProviderError("GDELT returned an unexpected result format.")
    articles: list[Headline] = []
    seen: set[str] = set()
    for item in payload.get("articles", []):
        if not isinstance(item, dict):
            continue
        title, link = item.get("title"), item.get("url")
        if not isinstance(title, str) or not isinstance(link, str):
            continue
        title = " ".join(title.split())
        if not _title_mentions_company(title, company):
            continue
        try:
            parsed = urlsplit(link)
            if parsed.scheme != "https" or not parsed.hostname or link in seen:
                continue
            article = Headline(
                title=title[:240],
                source_url=link,
                publisher=(item.get("domain") or parsed.hostname)[:100],
                published_at=_parse_gdelt_date(item.get("seendate")),
            )
        except (ValueError, TypeError):
            continue
        articles.append(article)
        seen.add(link)
        if len(articles) >= 10:
            break
    return articles


def get_stock_news(ticker: str) -> dict:
    """Fetch source-linked GDELT article metadata and score financial headline language."""
    symbol, exchange = ticker.rsplit(".", 1)
    catalog = POPULAR_NSE if exchange == "NS" else POPULAR_BSE
    company = catalog.get(symbol)
    if not company:
        raise ValueError("Automatic news lookup currently supports the curated company directory.")
    now = time.monotonic()
    with _cache_lock:
        entry = _cache.get(ticker)
        if entry and now - entry[0] < TTL_SECONDS:
            return entry[1]
    headlines = _fetch_gdelt(company)
    result = analyse_news(ticker, headlines)
    result.update({
        "company": company,
        "source": "GDELT Project DOC 2.0",
        "source_attribution": "https://www.gdeltproject.org/",
        "lookback_days": 7,
        "status": "ok" if headlines else "no_recent_news",
    })
    result["disclaimer"] += (
        " News index: GDELT Project. Coverage may be incomplete. "
        "Only headlines naming the selected company are used; "
        "headlines do not prove market impact. Original articles remain with publishers."
    )
    with _cache_lock:
        if len(_cache) >= 250:
            _cache.clear()
        _cache[ticker] = (time.monotonic(), result)
    return result
