"""Licensed-provider stock news retrieval. No scraping or market-price access."""
from __future__ import annotations
import json
import os
import time
from datetime import datetime, timedelta, timezone
from threading import Lock
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from news_sentiment import Headline, analyse_news
from stock_catalog import POPULAR_NSE, POPULAR_BSE

_cache = {}
_lock = Lock()
TTL_SECONDS = 900

class NewsProviderError(RuntimeError):
    pass

def get_stock_news(ticker: str) -> dict:
    """Return scored news for a selected known symbol, using an authorised GNews plan."""
    if os.getenv("ENABLE_LICENSED_NEWS", "").lower() not in {"true", "1", "yes"}:
        raise NewsProviderError("Automatic news lookup is not enabled until a commercial news-data licence is confirmed.")
    key = os.getenv("GNEWS_API_KEY", "").strip()
    if not key:
        raise NewsProviderError("Licensed news provider credentials have not been configured.")
    symbol, exchange = ticker.rsplit(".", 1)
    catalog = POPULAR_NSE if exchange == "NS" else POPULAR_BSE
    company = catalog.get(symbol)
    if not company:
        raise ValueError("Automatic news lookup currently supports stocks in the curated company directory.")
    now = time.monotonic()
    with _lock:
        cached = _cache.get(ticker)
        if cached and now - cached[0] < TTL_SECONDS:
            return cached[1]
    params = urlencode({
        "q": f'"{company}"', "lang": "en", "max": 10, "sortby": "publishedAt",
        "from": (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "apikey": key,
    })
    req = Request("https://gnews.io/api/v4/search?" + params,
                  headers={"Accept": "application/json", "User-Agent": "CR-Cognivex/1.0"})
    try:
        with urlopen(req, timeout=8) as response:
            payload = json.load(response)
    except HTTPError as exc:
        raise NewsProviderError("News provider rejected the request or its quota was reached.") from exc
    except (URLError, TimeoutError, ValueError, OSError) as exc:
        raise NewsProviderError("News provider is temporarily unavailable.") from exc
    articles = []
    seen = set()
    for item in payload.get("articles", [])[:20]:
        title, url = item.get("title"), item.get("url")
        if not isinstance(title, str) or not isinstance(url, str) or url in seen:
            continue
        try:
            article = Headline(title=title, source_url=url,
                               publisher=(item.get("source") or {}).get("name"),
                               published_at=item.get("publishedAt"))
        except (ValueError, TypeError):
            continue
        articles.append(article)
        seen.add(url)
        if len(articles) == 10:
            break
    result = analyse_news(ticker, articles)
    result["company"] = company
    result["source"] = "GNews licensed API"
    result["lookback_days"] = 7
    result["status"] = "ok" if articles else "no_recent_news"
    result["disclaimer"] += " News reflects provider coverage, not all publications."
    with _lock:
        if len(_cache) >= 256:
            _cache.clear()
        _cache[ticker] = (now, result)
    return result
