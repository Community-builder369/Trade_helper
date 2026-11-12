"""CR Cognivex Stock Research Lab API for Render."""
from __future__ import annotations
import os
import time
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from stock_analysis import ALLOWED_PERIODS, analyze_ticker, validate_ticker
from stock_catalog import search_stocks

app = FastAPI(title="CR Cognivex Stock Research API", version="1.1.0")
allow_origins = [s.strip() for s in os.getenv("ALLOWED_ORIGINS", "*").split(",") if s.strip()]
app.add_middleware(CORSMiddleware,allow_origins=allow_origins,allow_methods=["GET"],allow_headers=["*"])
_cache: dict[tuple[str,str],tuple[float,dict]] = {}
CACHE_SECONDS = 900
MAX_CACHE_ENTRIES = 256
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
def analyze(ticker: str = Query("RELIANCE.NS"), period: str = Query("6mo")):
    if not ALLOW_PUBLIC_PRICE_DATA:
        raise HTTPException(
            status_code=503,
            detail="Public market-data delivery is paused pending third-party data-usage permissions. You can upload OHLC CSV data you are authorised to use, or explore the synthetic demo."
        )
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
