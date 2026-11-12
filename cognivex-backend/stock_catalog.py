"""Small manually maintained stock symbol examples.

Avoid automatically collecting NSE websites or republishing exchange master lists
until applicable data-use permissions have been confirmed.
The examples are not guaranteed current, complete, or eligible for market data.
"""
from __future__ import annotations

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


def search_stocks(query: str, exchange: str = "NS", limit: int = 12) -> dict:
    exchange = exchange.upper()
    if exchange not in {"NS", "BO"}:
        raise ValueError("Exchange must be NS or BO.")
    limit = max(1, min(int(limit), 20))
    query = (query or "").strip().upper()[:40]
    directory = POPULAR_NSE if exchange == "NS" else POPULAR_BSE
    def rank(item):
        symbol, name = item
        name = name.upper()
        if symbol == query: return (0, len(symbol))
        if symbol.startswith(query): return (1, len(symbol))
        if name.startswith(query): return (2, len(symbol))
        if any(word.startswith(query) for word in name.split()): return (3, len(symbol))
        return (4, len(symbol))
    matches = [(symbol, name) for symbol, name in directory.items()
               if not query or query in symbol or query in name.upper()]
    matches.sort(key=lambda item: (rank(item), item[0]))
    return {
        "query": query,
        "exchange": exchange,
        "items": [
            {"symbol": symbol, "name": name, "ticker": symbol + "." + exchange}
            for symbol, name in matches[:limit]
        ],
        "source": "curated-example-list",
        "limited": True,
    }
