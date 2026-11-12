"""Offline unit tests: python -m unittest discover -s . -p "test_*.py" """
import unittest
from pydantic import ValidationError
from fastapi import FastAPI
from fastapi.testclient import TestClient

from news_sentiment import Headline, NewsSentimentRequest, analyse_news, score_headline


class TestNewsSentiment(unittest.TestCase):
    def test_positive(self):
        result = score_headline("Company profit rises and revenue grows")
        self.assertEqual(result["label"], "positive")
        self.assertEqual(len(result["signals"]), 2)

    def test_negative(self):
        result = score_headline("Company profit falls below estimates")
        self.assertEqual(result["label"], "negative")

    def test_no_evidence_is_unclassified(self):
        result = score_headline("Company announces meeting next Tuesday")
        self.assertEqual(result["label"], "insufficient_signal")
        self.assertIsNone(result["score"])

    def test_negation(self):
        self.assertEqual(score_headline("Company does not beat estimates")["label"], "negative")

    def test_aggregate_excludes_unclassified(self):
        news = [
            Headline(title="Company profit rises and revenue grows", source_url="https://example.com/a"),
            Headline(title="Company announces meeting next Tuesday", source_url="https://example.com/b"),
        ]
        result = analyse_news("INFY.NS", news)
        self.assertEqual(result["headlines_received"], 2)
        self.assertEqual(result["headlines_scored"], 1)
        self.assertEqual(result["overall_label"], "positive")

    def test_reject_insecure_url(self):
        with self.assertRaises(ValidationError):
            Headline(title="Company profit rises and revenue grows", source_url="http://example.com/a")

    def test_limit_headlines(self):
        items = [{"title": "Company profit rises and revenue grows",
                  "source_url": "https://example.com/a"}] * 11
        with self.assertRaises(ValidationError):
            NewsSentimentRequest(ticker="INFY.NS", headlines=items)

    def test_post_schema(self):
        app = FastAPI()

        @app.post("/api/news/sentiment")
        def analyse(payload: NewsSentimentRequest):
            return analyse_news(payload.ticker, payload.headlines)

        with TestClient(app) as client:
            payload = {"ticker": "INFY.NS", "headlines": [
                {"title": "Company profit rises and revenue grows",
                 "source_url": "https://example.com/a"}]}
            self.assertEqual(client.post("/api/news/sentiment", json=payload).status_code, 200)
            payload["headlines"] = []
            self.assertEqual(client.post("/api/news/sentiment", json=payload).status_code, 422)


if __name__ == "__main__":
    unittest.main()
