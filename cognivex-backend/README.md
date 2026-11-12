# CR Cognivex — Stock Research and News Sentiment API

FastAPI backend for the CR Cognivex Wix Stock Research Lab, running on Render.

## Endpoints
- GET /api/health — service health and stock-data permission flag
- GET /api/stocks?q=RELIANCE — curated example symbols, **not exchange data**
- GET /api/analyze?ticker=RELIANCE.NS&period=6mo — **disabled by default** until appropriate public market-data permissions are in place
- POST /api/news/sentiment — simple, explainable sentiment analysis of supplied / licensed financial news headlines (no fetching or scraping)
- GET /docs — interactive API schema

### News sentiment request

```json
{
  "ticker": "INFY.NS",
  "headlines": [
    {
      "title": "Company profit rises as revenue grows",
      "source_url": "https://example.com/news/article",
      "publisher": "Example Publisher"
    }
  ]
}
```

The response contains `overall_label`, `overall_score` (from -100 to +100, or null when insufficient evidence), `headlines_scored`, and per-headline `signals`. **This is a keyword/phrase-based heuristic prototype, NOT a trained AI model, calibrated confidence, future price forecast or investment advice.** It does not check company relevance, event accuracy, source reliability or actual market impact.

Only send headlines and links from sources whose terms allow the intended commercial analysis. No external news feeds are queried and the server does not retain the supplied headlines. Production ingestion needs a licensed news provider, authentication and stronger persistence/rate controls.

## Render service
- Branch: `cr-cognivex-market-api`
- Build: `cd cognivex-backend && pip install -r requirements.txt`
- Start: `cd cognivex-backend && uvicorn app:app --host 0.0.0.0 --port $PORT`
- Health: `/api/health`

The stock-price endpoint remains gated by `ALLOW_PUBLIC_PRICE_DATA=false` until data licensing is verified. Live UI integration and notifications are separate follow-on work.


## Automatic stock news (opt-in, licensed data)

The GET `/api/news/stock?ticker=RELIANCE.NS` endpoint maps a selected NSE/BSE ticker to its company, fetches up to ten recent English headlines through the configured GNews provider, and returns the same explainable sentiment scores as `/api/news/sentiment`. Results are cached for 15 minutes; the underlying public price-data endpoint stays disabled.

This endpoint intentionally returns HTTP 503 until both `ENABLE_LICENSED_NEWS=true` and `GNEWS_API_KEY` are configured by the service owner **after confirming that the provider plan permits this commercial, public-facing use, including headline display and derived scores**. Don't set these flags for an unlicensed trial/free API key. The application neither scrapes publications nor fabricates a score when the provider fails or finds no relevant news. Only symbols in the curated catalog have a reliable company name for lookup.

Front-end integration: upon stock selection, GET `/api/news/stock?ticker=<selected encoded ticker>`, display `overall_score` (−100 to +100), `overall_label`, `analysed_at`, and the returned article titles, publisher, publication time, and source links; do not ask visitors to paste URLs. Display a data-unavailable state on 503 and an insufficient-evidence state when `overall_score` is null. Debounce stock changes and reject stale responses. Keep article text and links rendered safely, and label the score as rule-based news sentiment, not investment advice.
