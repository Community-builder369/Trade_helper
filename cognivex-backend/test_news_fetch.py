"""Offline regression tests for GDELT rate-limit behaviour."""
import unittest
from unittest.mock import patch

import news_fetch


class TestGdeltRateLimiting(unittest.TestCase):
    def setUp(self):
        news_fetch._cache.clear()
        news_fetch._next_upstream_at = 0
        news_fetch._cooldown_seconds = news_fetch.INITIAL_COOLDOWN

    @patch("news_fetch._query_gdelt")
    def test_429_enters_cooldown_and_prevents_further_calls(self, fetch):
        fetch.side_effect = news_fetch.NewsProviderLimited(120)
        first = news_fetch.get_stock_news("RELIANCE.NS")
        self.assertEqual(first["status"], "rate_limited")
        self.assertIsNone(first["overall_score"])
        self.assertGreaterEqual(first["retry_after_seconds"], 120)
        next_stock = news_fetch.get_stock_news("TCS.NS")
        self.assertEqual(next_stock["status"], "rate_limited")
        fetch.assert_called_once()

    @patch("news_fetch._query_gdelt", return_value=[])
    def test_empty_news_is_explicit_not_neutral(self, fetch):
        result = news_fetch.get_stock_news("RELIANCE.NS")
        self.assertEqual(result["status"], "no_recent_news")
        self.assertEqual(result["overall_label"], "insufficient_signal")
        self.assertIsNone(result["overall_score"])
        repeat = news_fetch.get_stock_news("RELIANCE.NS")
        self.assertEqual(repeat["status"], "no_recent_news")
        fetch.assert_called_once()

    @patch("news_fetch._query_gdelt", return_value=[])
    def test_global_pacing_does_not_fetch_second_company(self, fetch):
        news_fetch.get_stock_news("RELIANCE.NS")
        pending = news_fetch.get_stock_news("TCS.NS")
        self.assertEqual(pending["status"], "rate_limited")
        self.assertEqual(fetch.call_count, 1)

    @patch("news_fetch._query_gdelt")
    def test_stale_result_is_labelled_when_upstream_rate_limits(self, fetch):
        news_fetch._cache["RELIANCE.NS"] = (
            news_fetch.time.monotonic() - news_fetch.TTL_SECONDS - 1,
            {"ticker": "RELIANCE.NS", "overall_score": 30, "disclaimer": "Original.",
             "articles": [{"title": "Earlier news"}]},
        )
        fetch.side_effect = news_fetch.NewsProviderLimited(300)
        result = news_fetch.get_stock_news("RELIANCE.NS")
        self.assertEqual(result["status"], "stale_cached")
        self.assertIn("outdated", result["disclaimer"])


if __name__ == "__main__":
    unittest.main()
