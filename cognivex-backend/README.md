# CR Cognivex — NSE Stock Research API

A FastAPI backend for the CR Cognivex Wix Stock Research Lab. Read-only endpoint, 15-minute in-memory cache, five whitelisted NSE symbols.

Endpoints:
- GET /api/health
- GET /api/analyze?ticker=RELIANCE.NS&period=6mo
- GET /

Render service settings (branch `cr-cognivex-market-api`):
- Build: `cd cognivex-backend && pip install -r requirements.txt`
- Start: `cd cognivex-backend && uvicorn app:app --host 0.0.0.0 --port $PORT`
- Health: `/api/health`

Warning: This reports rule-based technical indicators, not reliable forecasts. Yahoo Finance data may be delayed or unavailable. Review market data licensing and API abuse protections before public high-volume use.
