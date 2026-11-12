"""GDELT DOC 2.0 selected-stock news retrieval, with upstream rate-limit protection.

Fetches GDELT article-index metadata only, never scrapes publisher articles.
No share-price data, trading predictions or scraped article text.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from threading import Lock
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from news_sentiment import Headline, analyse_news
from stock_catalog import POPULAR_NSE, POPULAR_BSE

ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"
TTL_SECONDS = 3600                    # Successful results shared for one hour.
STALE_SECONDS = 24 * 3600             # Explicitly labelled prior results during outages.
MIN_QUERY_INTERVAL = 45.0            # Protect GDELT, including across different stock queries.
INITIAL_COOLDOWN = 5 * 60.0
MAX_COOLDOWN = 30 * 60.0

_cache: dict[str, tuple[float, dict]] = {}
_lock = Lock()
_next_upstream_at = 0.0
_cooldown_seconds = INITIAL_COOLDOWN


class NewsProviderError(RuntimeError):
    pass


class NewsProviderLimited(NewsProviderError):
    """A provider-imposed limit, never a signal to retry rapidly."""


def _parse_gdelt_date(value: str | None):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _title_mentions_company(title: str, company: str) -> bool:
    title = re.sub(r"[^a-z0-9]+", " ", title.casefold()).strip()
    company = re.sub(r"[^a-z0-9]+", " ", company.casefold()).strip()
    if not company:
        return False
    if " " not in company:
        return bool(re.search(r"\b" + re.escape(company) + r"\b", title)) and bool(
            re.search(r"\b(stock|stocks|shares|earnings|profit|revenue|investors|nse|bse)\b", title)
        )
    return bool(re.search(r"\b" + re.escape(company) + r"\b", title))


def _retry_after_seconds(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        return min(max(int(raw), 0), 1800)
    except ValueError:
        try:
            parsed = parsedate_to_datetime(raw).astimezone(timezone.utc)
            return min(max(int((parsed - datetime.now(timezone.utc)).total_seconds()), 0), 1800)
        except (TypeError, ValueError, OverflowError):
            return None


def _query_gdelt(company: str) -> list[Headline]:
    # Called with _lock held; one upstream request at a time per server process.
    query = '"' + company.replace('"', "") + '" sourcelang:english'
    params = urlencode({
        "query": query,
        "mode": "artlist",
        "format": "json",
        "maxrecords": 35,
        "timespan": "7d",
        "sort": "datedesc",
    })
    req = Request(ENDPOINT + "?" + params, headers={
        "Accept": "application/json",
        "User-Agent": "CR-Cognivex-Research/1.0 (+https://www.checkbeforetrade.com/)",
    })
    try:
        with urlopen(req, timeout=10) as response:
            if "json" not in response.headers.get("Content-Type", "").lower():
                raise NewsProviderError("GDELT returned a non-JSON response.")
            payload = json.load(response)
    except HTTPError as exc:
        if exc.code == 429:
            raise NewsProviderLimited(_retry_after_seconds(exc.headers.get("Retry-After"))) from exc
        raise NewsProviderError(f"GDELT could not complete the request (HTTP {exc.code}).") from exc
    except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        raise NewsProviderError("The open news index is temporarily unavailable.") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("articles", []), list):
        raise NewsProviderError("GDELT returned an unexpected response.")
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
                publisher=str(item.get("domain") or parsed.hostname)[:100],
                published_at=_parse_gdelt_date(item.get("seendate")),
            )
        except (ValueError, TypeError):
            continue
        seen.add(link)
        articles.append(article)
        if len(articles) >= 10:
            break
    return articles


def _unavailable(ticker: str, company: str, status: str, wait: int = 0) -> dict:
    # An unavailable score must be null; never represent missing news as neutral.
    result = analyse_news(ticker, [])
    result.update({
        "company": company,
        "source": "GDELT Project DOC 2.0",
        "source_attribution": "https://www.gdeltproject.org/",
        "lookback_days": 7,
        "status": status,
        "retry_after_seconds": wait,
    })
    result["disclaimer"] += " No live sentiment score is available while the news index is limited or unavailable."
    return result


def _stale_or_unavailable(ticker: str, company: str, status: str, wait: int, now: float) -> dict:
    existing = _cache.get(ticker)
    if existing and now - existing[0] <= STALE_SECONDS:
        # A copy prevents background mutations of the cached response.
        data = dict(existing[1])
        data["status"] = "stale_cached"
        data["retry_after_seconds"] = wait
        data["disclaimer"] = (
            "Previously retrieved, potentially outdated news results; "
            "the open news source is currently unavailable. "
            + str(existing[1].get("disclaimer", ""))
        )
        return data
    return _unavailable(ticker, company, status, wait)


def get_stock_news(ticker: str) -> dict:
    global _next_upstream_at, _cooldown_seconds
    symbol, exchange = ticker.rsplit(".", 1)
    catalog = POPULAR_NSE if exchange == "NS" else POPULAR_BSE
    company = catalog.get(symbol)
    if not company:
        raise ValueError("Automatic news lookup currently supports the curated company directory.")

    with _lock:
        now = time.monotonic()
        cached = _cache.get(ticker)
        if cached and now - cached[0] < TTL_SECONDS:
            return cached[1]
        if now < _next_upstream_at:
            wait = max(1, int(_next_upstream_at - now))
            return _stale_or_unavailable(ticker, company, "rate_limited", wait, now)

        # Reserve an upstream slot before making the network call.
        _next_upstream_at = now + MIN_QUERY_INTERVAL
        try:
            articles = _query_gdelt(company)
        except NewsProviderLimited as exc:
            explicit = exc.args[0] if exc.args and isinstance(exc.args[0], int) else 0
            delay = max(_cooldown_seconds, explicit)
            _next_upstream_at = time.monotonic() + delay
            _cooldown_seconds = min(_cooldown_seconds * 2, MAX_COOLDOWN)
            return _stale_or_unavailable(ticker, company, "rate_limited", int(delay), time.monotonic())
        except NewsProviderError:
            _next_upstream_at = time.monotonic() + 90
            return _stale_or_unavailable(ticker, company, "news_unavailable", 90, time.monotonic())

        _cooldown_seconds = INITIAL_COOLDOWN
        result = analyse_news(ticker, articles)
        result.update({
            "company": company,
            "source": "GDELT Project DOC 2.0",
            "source_attribution": "https://www.gdeltproject.org/",
            "lookback_days": 7,
            "status": "ok" if articles else "no_recent_news",
            "retry_after_seconds": 0,
        })
        result["disclaimer"] += (
            " News index: GDELT Project; coverage is incomplete. "
            "Only company-naming headlines are scored, not publisher article content. "
            "These scores cannot establish actual market impact."
        )
        if len(_cache) >= 250:
            # Purge only expired entries first, retaining commonly viewed tickers.
            for key in list(_cache):
                if now - _cache[key][0] > STALE_SECONDS:
                    del _cache[key]
            if len(_cache) >= 250:
                _cache.pop(next(iter(_cache)))
        _cache[ticker] = (time.monotonic(), result)
        return result
