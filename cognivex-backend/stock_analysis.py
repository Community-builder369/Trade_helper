"""CR Cognivex Stock Research Lab: indicators for NSE and BSE equities.
Rule-based technical signals are NOT price forecasts or investment advice.
"""
from __future__ import annotations
import math
import re
from typing import Any
import pandas as pd

ALLOWED_PERIODS = {"3mo", "6mo", "1y"}
MIN_BARS = 35
# Accept Yahoo Finance symbols for Indian NSE and BSE equities.
# Actual coverage depends on market-data provider availability.
INDIAN_EQUITY_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9&._-]{0,29}\.(?:NS|BO)$")

def validate_ticker(ticker: str) -> str:
    """Validate Indian equity symbols; unsuffixed tickers default to NSE."""
    symbol = ticker.strip().upper()
    if "." not in symbol:
        symbol += ".NS"
    if symbol == "TATAMOTORS.NS":
        raise ValueError(
            "TATAMOTORS.NS is an obsolete NSE ticker after the 2025 demerger. "
            "Use TMPV.NS for Tata Motors Passenger Vehicles or TMCV.NS "
            "for Tata Motors Commercial Vehicles."
        )
    if not INDIAN_EQUITY_SYMBOL.fullmatch(symbol):
        raise ValueError(
            "Invalid Indian equity ticker. Use an NSE symbol such as ICICIBANK.NS "
            "or a BSE code such as 500325.BO."
        )
    return symbol

def fetch_prices(ticker: str, period: str = "6mo") -> pd.DataFrame:
    ticker = validate_ticker(ticker)
    if period not in ALLOWED_PERIODS:
        raise ValueError("Unsupported period; choose 3mo, 6mo or 1y.")
    try:
        import yfinance as yf
        data = yf.Ticker(ticker).history(period=period, interval="1d", auto_adjust=True)
    except Exception as exc:
        raise RuntimeError(f"Market data provider could not retrieve {ticker}: {exc}") from exc
    if data is None or data.empty:
        raise RuntimeError(f"No recent OHLC prices were returned for {ticker}.")
    return data

def analyze_prices(prices: pd.DataFrame, ticker: str, period: str = "6mo") -> dict[str, Any]:
    ticker = validate_ticker(ticker)
    if period not in ALLOWED_PERIODS:
        raise ValueError("Unsupported period; choose 3mo, 6mo or 1y.")
    if prices is None or prices.empty:
        raise ValueError("No price history is available.")
    needed = ("High", "Low", "Close")
    if not all(c in prices.columns for c in needed):
        raise ValueError("Price history must contain High, Low and Close.")
    df = prices.copy()
    for col in needed:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.replace([float("inf"), float("-inf")], float("nan"))
    df = df.dropna(subset=list(needed)).sort_index()
    df = df.loc[(df.High >= df.Low) & (df.Close <= df.High) & (df.Close >= df.Low)]
    if len(df) < MIN_BARS:
        raise ValueError(f"At least {MIN_BARS} valid daily observations required.")
    df["EMA12"] = df.Close.ewm(span=12, adjust=False).mean()
    df["EMA26"] = df.Close.ewm(span=26, adjust=False).mean()
    df["MACD"] = df.EMA12 - df.EMA26
    df["Signal"] = df.MACD.ewm(span=9, adjust=False).mean()
    upper = df.High.rolling(14, min_periods=14).max()
    lower = df.Low.rolling(14, min_periods=14).min()
    spread = (upper - lower).replace(0, float("nan"))
    df["Williams %R"] = -100 * (upper - df.Close) / spread
    high = float(df.High.max())
    low = float(df.Low.min())
    if not math.isfinite(high-low) or high <= low:
        raise ValueError("Fibonacci levels undefined for flat price history.")
    fib = {label: round(high-(high-low)*frac,4) for label,frac in [
        ("0.0%",0),("23.6%",.236),("38.2%",.382),("50.0%",.5),
        ("61.8%",.618),("78.6%",.786),("100.0%",1)
    ]}
    latest = df.iloc[-1]
    price, macd, signal, wr = (float(latest[c]) for c in ("Close","MACD","Signal","Williams %R"))
    def direction(v: float, comparison: float) -> str:
        if not math.isfinite(v): return "unavailable"
        if abs(v-comparison)<1e-9: return "neutral"
        return "bullish" if v>comparison else "bearish"
    votes = {"macd":direction(macd-signal,0),
             "williams_r":direction(wr,-50),
             "fibonacci":direction(price,fib["50.0%"])}
    stance = votes["macd"] if len(set(votes.values()))==1 and votes["macd"] in ("bullish","bearish") else "mixed"
    wr_zone = "unavailable" if not math.isfinite(wr) else (
        "overbought" if wr>=-20 else "oversold" if wr<=-80 else "middle")
    chart = [
        {"date":pd.Timestamp(t).date().isoformat(),
         "close":round(float(row["Close"]),4),
         "macd":round(float(row["MACD"]),5),
         "signal":round(float(row["Signal"]),5)}
        for t,row in df.tail(100).iterrows()
    ]
    return {
        "ticker":ticker,"period":period,
        "as_of":pd.Timestamp(df.index[-1]).date().isoformat(),
        "observations":len(df),"currency":"INR","price":round(price,4),
        "indicators":{"macd":round(macd,5),"signal":round(signal,5),
            "williams_r":round(wr,4) if math.isfinite(wr) else None,
            "williams_zone":wr_zone},
        "fib_levels":fib,"votes":votes,"stance":stance,"chart":chart,
        "disclaimer":"Rule-based technical confluence; not a statistical price forecast or investment advice."
    }

def analyze_ticker(ticker: str, period: str = "6mo") -> dict[str, Any]:
    ticker = validate_ticker(ticker)
    return analyze_prices(fetch_prices(ticker, period), ticker, period)
