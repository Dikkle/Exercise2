#!/usr/bin/env python3
"""stock4-app-1 — Alpha Vantage news scraper.

Usage:
    python scraper.py news SYMBOL

Writes a single JSON document to stdout:
    {"symbol": "AAPL", "count": N, "items": [...]}
    {"error": "<machine-readable code>", "detail": "..."}

Exit codes:
    0  success
    1  transient / upstream failure (HTTP, network, parse)
    2  bad invocation / missing config

Required env:
    ALPHA_VANTAGE_API_KEY
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API_BASE = "https://www.alphavantage.co/query"
SYMBOL_RE = re.compile(r"^[A-Z][A-Z.\-]{0,9}$")
HTTP_TIMEOUT = 15
USER_AGENT = "stock4-app-1/1.0 (+https://www.alphavantage.co)"

# MOCK=1 short-circuits the upstream call and emits synthetic news so the
# frontend/backend wiring can be exercised without burning API quota.
MOCK_ON = (os.environ.get("MOCK") or "").strip().lower() in {"1", "true", "yes", "on"}


def _sanitize(text: str, limit: int = 600) -> str:
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _http_get(params: dict) -> dict:
    url = f"{API_BASE}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw)


def _validate_symbol(symbol: str) -> str:
    symbol = (symbol or "").strip().upper()
    if not SYMBOL_RE.match(symbol):
        raise ValueError(f"invalid symbol: {symbol!r}")
    return symbol


def _process_entry(entry: dict) -> dict | None:
    title = _sanitize(entry.get("title") or "", limit=200)
    url = entry.get("url") or ""
    if not title or not url:
        return None
    return {
        "title": title,
        "url": url,
        "source": _sanitize(entry.get("source") or "", limit=80),
        "published": entry.get("time_published") or "",
        "summary": _sanitize(entry.get("summary") or "", limit=600),
        "sentiment": _sanitize(entry.get("overall_sentiment_label") or "", limit=20) or None,
        "ticker_sentiment": _sanitize(entry.get("overall_sentiment_score") or "", limit=10) or None,
    }


_MOCK_TEMPLATES = (
    ("Reuters", "Bullish", "0.42", "{S} beats quarterly estimates on resilient demand"),
    ("Bloomberg", "Bullish", "0.31", "Analysts raise price target on {S} after upbeat guidance"),
    ("CNBC", "Neutral", "0.05", "{S} trades flat as sector rotation continues"),
    ("MarketWatch", "Neutral", "-0.02", "{S} outlines product roadmap for the next fiscal year"),
    ("TechCrunch", "Bullish", "0.36", "{S} expands data-center footprint into new regions"),
    ("Barron's", "Bearish", "-0.28", "{S} faces margin pressure from rising component costs"),
    ("Seeking Alpha", "Neutral", "0.08", "{S} valuation check: what the current multiples imply"),
    ("The Motley Fool", "Bullish", "0.24", "Is {S} still a buy after the latest pullback?"),
)


def mock_news(symbol: str) -> dict:
    """Synthetic feed used when MOCK=1. Clearly flagged so UIs can badge it."""
    now = int(time.time())
    items = []
    for i, (source, sentiment, score, headline) in enumerate(_MOCK_TEMPLATES):
        items.append(
            {
                "title": "[MOCK] " + headline.replace("{S}", symbol),
                "url": "https://www.alphavantage.co/documentation/",
                "source": source,
                "published": time.strftime("%Y%m%dT%H%M%S", time.localtime(now - i * 3600)),
                "summary": (
                    f"Synthetic summary for {symbol}: {headline.replace('{S}', symbol)}. "
                    "This entry is generated locally by scraper.py in MOCK mode and does "
                    "not represent real market news."
                ),
                "sentiment": sentiment,
                "ticker_sentiment": score,
            }
        )
    return {"symbol": symbol, "count": len(items), "items": items, "fetched_at": now, "mock": True}


def fetch_news(symbol: str, api_key: str) -> dict:
    data = _http_get(
        {
            "function": "NEWS_SENTIMENT",
            "tickers": symbol,
            "apikey": api_key,
            "limit": 20,
            "sort": "LATEST",
        }
    )

    if not isinstance(data, dict):
        return {"error": "bad_response", "detail": "non-object payload"}

    if "Note" in data:
        return {"error": "rate_limited", "detail": _sanitize(data["Note"])}
    if "Information" in data:
        return {"error": "api_error", "detail": _sanitize(data["Information"])}
    if "Error Message" in data:
        return {"error": "bad_request", "detail": _sanitize(data["Error Message"])}

    feed = data.get("feed") or []
    items = []
    for entry in feed[:10]:
        item = _process_entry(entry)
        if item:
            items.append(item)

    return {"symbol": symbol, "count": len(items), "items": items, "fetched_at": int(time.time())}


def cmd_news(argv: list[str]) -> int:
    if len(argv) < 3:
        print(json.dumps({"error": "missing_symbol"}))
        return 2
    try:
        symbol = _validate_symbol(argv[2])
    except ValueError as exc:
        print(json.dumps({"error": "invalid_symbol", "detail": str(exc)}))
        return 2

    if MOCK_ON:
        print(json.dumps(mock_news(symbol), ensure_ascii=False))
        return 0

    api_key = (os.environ.get("ALPHA_VANTAGE_API_KEY") or "").strip()
    if not api_key:
        print(json.dumps({"error": "missing_api_key"}))
        return 2

    try:
        result = fetch_news(symbol, api_key)
    except urllib.error.HTTPError as exc:
        print(json.dumps({"error": "http", "status": exc.code, "detail": exc.reason}))
        return 1
    except urllib.error.URLError as exc:
        print(json.dumps({"error": "network", "detail": str(exc.reason)}))
        return 1
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": "parse", "detail": str(exc)}))
        return 1
    except (TimeoutError, OSError) as exc:
        print(json.dumps({"error": "io", "detail": str(exc)}))
        return 1

    print(json.dumps(result, ensure_ascii=False))
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(json.dumps({"error": "missing_command"}))
        return 2
    cmd = argv[1].lower()
    if cmd == "news":
        return cmd_news(argv)
    print(json.dumps({"error": "unknown_command", "command": cmd}))
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except BrokenPipeError:
        # Downstream (node server.js) terminated; suppress noisy traceback.
        sys.exit(1)