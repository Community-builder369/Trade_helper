"""Free News API adapter for selected-stock research.

Use the free commercial-permitted API plan with a private server-side API key.
https://freenewsapi.ai/docs  (free tier permits commercial use)
"""
from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from news_sentiment import Headline, analyse_news
from stock_catalog import POPULAR_NSE, POPULAR_BSE
from news_fetch import NewsProviderError, _title_mentions_company

URL = "https://freenewsapi.ai/v1/search"


def get_free_news(ticker: str) -> dict:
    key = os.getenv("FREE_NEWS_API_KEY", "").strip()
    if not key:
        raise NewsProviderError("Free News API server key is not configured.")
    symbol, suffix = ticker.rsplit(".", 1)
    company = (POPULAR_NSE if suffix == "NS" else POPULAR_BSE).get(symbol)
    if not company:
        raise ValueError("Selected stock is not yet in our curated news directory.")
    params = urlencode({
        "q": company,
        "date": "7d",
        "lang": "en",
        "size": 30,
        "sort": "date",
    })
    req = Request(URL + "?" + params, headers={
        "Accept": "application/json",
        "Authorization": "Bearer " + key,
        "User-Agent": "CR-Cognivex-Research/1.1",
    })
    try:
        with urlopen(req, timeout=12) as response:
            if "json" not in response.headers.get("Content-Type", "").lower():
                raise NewsProviderError("Free News API returned a non-JSON response.")
            result = json.load(response)
    except HTTPError as exc:
        # Do not expose keys, upstream bodies, or request details to visitors.
        if exc.code == 429:
            raise NewsProviderError("News provider is temporarily rate limiting searches.") from exc
        if exc.code == 402:
            raise NewsProviderError("The free news provider's monthly allowance was reached.") from exc
        if exc.code in (401, 403):
            raise NewsProviderError("The news provider requires a valid server-side API key.") from exc
        raise NewsProviderError("The news provider could not complete this request.") from exc
    except (URLError, TimeoutError, ValueError, OSError, json.JSONDecodeError) as exc:
        raise NewsProviderError("The news provider is temporarily unavailable.") from exc
    if not isinstance(result, dict) or not isinstance(result.get("results", []), list):
        raise NewsProviderError("The news provider returned an unexpected response.")
    headlines = []
    seen = set()
    for item in result.get("results", []):
        if not isinstance(item, dict):
            continue
        title, link = item.get("title"), item.get("url")
        if not isinstance(title, str) or not isinstance(link, str):
            continue
        title = " ".join(title.split())
        if not _title_mentions_company(title, company):
            continue
        try:
            u = urlsplit(link)
            if u.scheme != "https" or not u.hostname or link in seen:
                continue
            headline = Headline(
                title=title[:240],
                source_url=link,
                publisher=str(item.get("sitename") or item.get("host") or u.hostname)[:100],
                published_at=item.get("published_at"),
            )
        except (ValueError, TypeError):
            continue
        headlines.append(headline)
        seen.add(link)
        if len(headlines) >= 10:
            break
    response = analyse_news(ticker, headlines)
    response.update({
        "company": company,
        "source": "Free News API",
        "source_attribution": "https://freenewsapi.ai/",
        "lookback_days": 7,
        "status": "ok" if headlines else "no_recent_news",
        "retry_after_seconds": 0,
    })
    response["disclaimer"] += (
        " News index: Free News API. Coverage is incomplete. "
        "Only matching source headlines are scored; scores do not predict share prices."
    )
    return response
