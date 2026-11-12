"""Symbol suggestions for CR Cognivex: an NSE master-list cache and offline fallback.

NSE publishes an equity master CSV. Availability of individual tickers in
Yahoo Finance price history is separate from appearing in this directory.
"""
from __future__ import annotations

import csv
import io
import threading
import time
from urllib.request import Request, urlopen

NSE_CSV_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
CACHE_SECONDS = 24 * 60 * 60
RETRY_SECONDS = 60 * 60
CATALOG_TIMEOUT = 7

# This small directory ensures mobile suggestions work when NSE is unavailable.
POPULAR_NSE = {
    "RELIANCE": "Reliance Industries",
    "TCS": "Tata Consultancy Services",
    "INFY": "Infosys",
    "HDFCBANK": "HDFC Bank",
    "HINDUNILVR": "Hindustan Unilever",
    "ICICIBANK": "ICICI Bank",
    "SBIN": "State Bank of India",
    "BHARTIARTL": "Bharti Airtel",
    "ITC": "ITC",
    "LT": "Larsen & Toubro",
    "WIPRO": "Wipro",
    "TMPV": "Tata Motors Passenger Vehicles",
    "TMCV": "Tata Motors Commercial Vehicles",
    "TATASTEEL": "Tata Steel",
    "TATAPOWER": "Tata Power",
    "TATACONSUM": "Tata Consumer Products",
    "TITAN": "Titan Company",
    "MARUTI": "Maruti Suzuki India",
    "M&M": "Mahindra & Mahindra",
    "BAJFINANCE": "Bajaj Finance",
    "BAJAJFINSV": "Bajaj Finserv",
    "BAJAJ-AUTO": "Bajaj Auto",
    "AXISBANK": "Axis Bank",
    "KOTAKBANK": "Kotak Mahindra Bank",
    "INDUSINDBK": "IndusInd Bank",
    "BANKBARODA": "Bank of Baroda",
    "PNB": "Punjab National Bank",
    "CANBK": "Canara Bank",
    "IDFCFIRSTB": "IDFC First Bank",
    "UNIONBANK": "Union Bank of India",
    "FEDERALBNK": "Federal Bank",
    "POWERGRID": "Power Grid Corporation",
    "NTPC": "NTPC",
    "ONGC": "Oil and Natural Gas Corporation",
    "COALINDIA": "Coal India",
    "IOC": "Indian Oil Corporation",
    "BPCL": "Bharat Petroleum",
    "HINDPETRO": "Hindustan Petroleum",
    "ADANIENT": "Adani Enterprises",
    "ADANIPORTS": "Adani Ports",
    "ADANIGREEN": "Adani Green Energy",
    "ADANIPOWER": "Adani Power",
    "SUNPHARMA": "Sun Pharmaceutical",
    "DRREDDY": "Dr. Reddy's Laboratories",
    "CIPLA": "Cipla",
    "DIVISLAB": "Divi's Laboratories",
    "APOLLOHOSP": "Apollo Hospitals",
    "ASIANPAINT": "Asian Paints",
    "ULTRACEMCO": "UltraTech Cement",
    "GRASIM": "Grasim Industries",
    "JSWSTEEL": "JSW Steel",
    "HINDALCO": "Hindalco Industries",
    "JINDALSTEL": "Jindal Steel & Power",
    "VEDL": "Vedanta",
    "HCLTECH": "HCL Technologies",
    "TECHM": "Tech Mahindra",
    "PERSISTENT": "Persistent Systems",
    "LTIM": "LTIMindtree",
    "OFSS": "Oracle Financial Services Software",
    "HAL": "Hindustan Aeronautics",
    "BEL": "Bharat Electronics",
    "IRCTC": "Indian Railway Catering & Tourism Corporation",
    "IRFC": "Indian Railway Finance Corporation",
    "RVNL": "Rail Vikas Nigam",
    "ZOMATO": "Eternal (formerly Zomato)",
    "ETERNAL": "Eternal",
    "DMART": "Avenue Supermarts",
    "TRENT": "Trent",
    "DABUR": "Dabur India",
    "BRITANNIA": "Britannia Industries",
    "NESTLEIND": "Nestlé India",
    "EICHERMOT": "Eicher Motors",
    "HEROMOTOCO": "Hero MotoCorp",
    "TVSMOTOR": "TVS Motor Company",
    "ASHOKLEY": "Ashok Leyland",
    "DLF": "DLF",
    "GODREJCP": "Godrej Consumer Products",
    "PFC": "Power Finance Corporation",
    "RECLTD": "REC",
    "NHPC": "NHPC",
    "BIOCON": "Biocon",
    "BSE": "BSE Limited",
    "CDSL": "Central Depository Services",
    "NAUKRI": "Info Edge India",
    "INDIGO": "InterGlobe Aviation",
    "SIEMENS": "Siemens",
    "ABB": "ABB India",
    "PIDILITIND": "Pidilite Industries",
    "GAIL": "GAIL India",
    "HAVELLS": "Havells India",
    "POLYCAB": "Polycab India",
    "SBILIFE": "SBI Life Insurance",
    "HDFCLIFE": "HDFC Life Insurance",
    "ICICIPRULI": "ICICI Prudential Life Insurance",
}

# BSE scrip codes; any other valid .BO code remains manually searchable.
POPULAR_BSE = {
    "500325": "Reliance Industries",
    "532540": "Tata Consultancy Services",
    "500209": "Infosys",
    "500180": "HDFC Bank",
    "532174": "ICICI Bank",
    "500112": "State Bank of India",
    "507685": "Wipro",
    "500696": "Hindustan Unilever",
}
_lock = threading.Lock()
_nse_catalog: dict[str, str] = dict(POPULAR_NSE)
_refresh_requested_at = 0.0
_last_success_at = 0.0
_refresh_in_progress = False


def _refresh_nse() -> None:
    global _nse_catalog, _last_success_at, _refresh_in_progress
    try:
        req = Request(
            NSE_CSV_URL,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; CR-Cognivex/1.0)",
                "Referer": "https://www.nseindia.com/",
                "Accept": "text/csv,*/*",
            },
        )
        with urlopen(req, timeout=CATALOG_TIMEOUT) as response:
            data = response.read(1_000_000)
        rows = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
        discovered: dict[str, str] = {}
        for row in rows:
            normalized = {str(k).strip().upper(): str(v or "").strip()
                          for k, v in row.items() if k}
            symbol = normalized.get("SYMBOL", "").upper()
            name = normalized.get("NAME OF COMPANY", "")
            series = normalized.get("SERIES", "EQ").upper()
            if (symbol and name and len(symbol) <= 30
                    and series in {"EQ", "BE", "SM", "ST", "BZ", "E1", "E2"}):
                discovered[symbol] = name
        if len(discovered) > 500:
            with _lock:
                # Prefer the current official name when a fallback symbol overlaps.
                _nse_catalog = {**POPULAR_NSE, **discovered}
                _last_success_at = time.monotonic()
    except Exception:
        # Do not break suggestions when the exchange blocks requests.
        pass
    finally:
        with _lock:
            _refresh_in_progress = False


def search_stocks(query: str, exchange: str = "NS", limit: int = 12) -> dict:
    global _refresh_requested_at, _refresh_in_progress
    exchange = exchange.upper()
    if exchange not in {"NS", "BO"}:
        raise ValueError("Exchange must be NS or BO.")
    limit = max(1, min(int(limit), 20))
    query = (query or "").strip().upper()[:40]
    now = time.monotonic()
    with _lock:
        if (exchange == "NS" and not _refresh_in_progress
                and now - _refresh_requested_at >
                  (CACHE_SECONDS if _last_success_at else RETRY_SECONDS)):
            _refresh_in_progress = True
            _refresh_requested_at = now
            threading.Thread(target=_refresh_nse, daemon=True).start()
        directory = dict(_nse_catalog if exchange == "NS" else POPULAR_BSE)
        source = "nse-master" if exchange == "NS" and _last_success_at else "fallback"

    def rank(item):
        symbol, name = item
        upper_name = name.upper()
        if symbol == query:
            return (0, len(symbol))
        if symbol.startswith(query):
            return (1, len(symbol))
        if upper_name.startswith(query):
            return (2, len(symbol))
        if any(word.startswith(query) for word in upper_name.split()):
            return (3, len(symbol))
        return (4, len(symbol))

    matches = [(symbol, name) for symbol, name in directory.items()
               if not query or query in symbol or query in name.upper()]
    matches.sort(key=lambda item: (rank(item), item[0]))
    items = [{"symbol": symbol, "name": name, "ticker": symbol + "." + exchange}
             for symbol, name in matches[:limit]]
    return {
        "query": query,
        "exchange": exchange,
        "items": items,
        "source": source,
        "limited": source == "fallback" or exchange == "BO",
    }
