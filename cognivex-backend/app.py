"""CR Cognivex Stock Research Lab API for Render."""
from __future__ import annotations
import os
import time
from collections import deque
from threading import Lock
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from stock_analysis import ALLOWED_PERIODS, analyze_ticker, validate_ticker
from stock_catalog import search_stocks
from news_sentiment import NewsSentimentRequest, analyse_news
from news_fetch import get_stock_news, NewsProviderError
from free_news_api import get_free_news

app = FastAPI(title="CR Cognivex Stock Research API", version="1.1.0")
allow_origins = [s.strip() for s in os.getenv("ALLOWED_ORIGINS", "*").split(",") if s.strip()]
app.add_middleware(CORSMiddleware,allow_origins=allow_origins,allow_methods=["GET","POST"],allow_headers=["*"])
_cache: dict[tuple[str,str],tuple[float,dict]] = {}
CACHE_SECONDS = 900
MAX_CACHE_ENTRIES = 256

# Bound public requests to protect the free instance and upstream market-data source.
_RATE_WINDOW = 600.0
_MAX_IP_REQUESTS = 60
_MAX_GLOBAL_REQUESTS = 1200
_ip_requests: dict[str, deque[float]] = {}
_global_requests: deque[float] = deque()
_rate_lock = Lock()

def _limit_analyze_request(request: Request) -> None:
    now = time.monotonic()
    # Render forwards the real client address to the ASGI server.
    ip = request.client.host if request.client else "unknown"
    with _rate_lock:
        while _global_requests and now - _global_requests[0] >= _RATE_WINDOW:
            _global_requests.popleft()
        if len(_ip_requests) > 2048:
            for key, bucket in list(_ip_requests.items()):
                if not bucket or now - bucket[-1] >= _RATE_WINDOW:
                    del _ip_requests[key]
        bucket = _ip_requests.setdefault(ip, deque())
        while bucket and now - bucket[0] >= _RATE_WINDOW:
            bucket.popleft()
        if len(bucket) >= _MAX_IP_REQUESTS or len(_global_requests) >= _MAX_GLOBAL_REQUESTS:
            raise HTTPException(
                status_code=429,
                detail="Analysis request limit reached. Please try again in a few minutes."
            )
        bucket.append(now)
        _global_requests.append(now)

# Default to no public redistribution until a suitable market-data licence is verified.
ALLOW_PUBLIC_PRICE_DATA = os.getenv("ALLOW_PUBLIC_PRICE_DATA", "false").lower() in {"yes", "true", "1"}

@app.get("/")
def index():
    return {"name":"CR Cognivex Stock Research API","health":"/api/health","analyze":"/api/analyze?ticker=RELIANCE.NS&period=6mo"}

@app.get("/api/health")
def health():
    return {"ok":True,"service":"CR Cognivex Stock Research API","live_price_data_enabled":ALLOW_PUBLIC_PRICE_DATA}

@app.get("/api/stocks")
def stocks(q: str = Query("", max_length=40), exchange: str = Query("NS"), limit: int = Query(12, ge=1, le=20)):
    """Mobile-friendly symbol and company-name autocomplete (not a quote endpoint)."""
    try:
        return search_stocks(q, exchange, limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/analyze")
def analyze(request: Request, ticker: str = Query("RELIANCE.NS"), period: str = Query("6mo")):
    if not ALLOW_PUBLIC_PRICE_DATA:
        raise HTTPException(
            status_code=503,
            detail="Public market-data delivery is paused pending third-party data-usage permissions. You can upload OHLC CSV data you are authorised to use, or explore the synthetic demo."
        )
    _limit_analyze_request(request)
    try:
        ticker = validate_ticker(ticker)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if period not in ALLOWED_PERIODS:
        raise HTTPException(status_code=400,detail="Choose 1mo, 3mo or 6mo.")
    key=(ticker,period)
    entry=_cache.get(key)
    if entry and time.monotonic()-entry[0]<CACHE_SECONDS:
        return entry[1]
    try:
        result=analyze_ticker(ticker,period)
    except (ValueError,RuntimeError) as exc:
        raise HTTPException(status_code=503,detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503,detail="Unable to retrieve market data right now.") from exc
    _cache[key]=(time.monotonic(),result)
    if len(_cache) > MAX_CACHE_ENTRIES:
        _cache.pop(next(iter(_cache)))
    return result

@app.post("/api/news/sentiment")
def news_sentiment(request: Request, payload: NewsSentimentRequest):
    """Analyse user-supplied or licensed financial headlines. No news fetching."""
    _limit_analyze_request(request)
    try:
        ticker = validate_ticker(payload.ticker)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return analyse_news(ticker, payload.headlines)


@app.get("/api/news/stock")
def selected_stock_news(request: Request, ticker: str = Query(..., min_length=3, max_length=32)):
    """Score latest licensed news for the stock selected in the interface."""
    _limit_analyze_request(request)
    try:
        symbol = validate_ticker(ticker)
        if os.getenv('FREE_NEWS_API_KEY', '').strip():
            return get_free_news(symbol)
        return get_stock_news(symbol)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except NewsProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
