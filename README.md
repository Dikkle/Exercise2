# stock4-app-1

NASDAQ-10 stock news dashboard.

- **Backend**: Node.js + Express (`server.js`) on port `3015`.
- **Scraper**: Python stdlib only (`scraper.py`) — calls Alpha Vantage `NEWS_SENTIMENT`.
- **Frontend**: Single static page (`public/index.html`) using React 18 — UMD builds are
  self-hosted in `public/vendor/`, so the app needs no CDN access and no build step.

The 10 supported symbols live in [`stocks.js`](./stocks.js) and are exposed via `GET /api/stocks`. The frontend is a tiny React app that lets the user pick a symbol and renders up to 10 latest news cards.

## Prerequisites

- Node.js **>= 18** (`node --version`)
- Python **>= 3.9** (`python --version`)
- An Alpha Vantage API key — grab a free one from <https://www.alphavantage.co/support/#api-key>

## Setup

```bash
# 1. install node deps
npm install

# 2. configure secrets
cp .env.example .env
#   then edit .env and set ALPHA_VANTAGE_API_KEY=...

# 3. run
npm start
# → http://localhost:3015
```

The server loads `.env` automatically via `node --env-file=.env` if you prefer:

```bash
node --env-file=.env server.js
```

## Mock mode

Run the full stack without an Alpha Vantage key or without consuming API quota:

```bash
# PowerShell
$env:MOCK='1'; npm start

# bash
MOCK=1 npm start
```

`scraper.py` then emits eight synthetic news items per symbol instead of calling the
upstream API. Every response carries `"mock": true`, `GET /api/health` reports
`"mock": true`, and the frontend renders a yellow warning banner plus a `[MOCK]`
prefix on each headline so synthetic data can never be mistaken for real news.

Symbol validation, the NASDAQ-10 allow-list, and all error paths behave identically
in mock mode — only the upstream HTTP call is short-circuited.

## API

| Method | Path                | Description                                            |
|--------|---------------------|--------------------------------------------------------|
| GET    | `/api/health`       | Liveness probe + python path                           |
| GET    | `/api/stocks`       | Returns the 10 supported symbols                       |
| GET    | `/api/news/:symbol` | Returns up to 10 latest news items for a NASDAQ symbol |

### `GET /api/news/AAPL`

Success:

```json
{
  "symbol": "AAPL",
  "count": 10,
  "fetched_at": 1730000000,
  "items": [
    {
      "title": "...",
      "url": "https://...",
      "source": "Reuters",
      "published": "20260213T143000",
      "summary": "...",
      "sentiment": "Bullish",
      "ticker_sentiment": "0.18"
    }
  ]
}
```

Errors are returned as `{ "error": "<code>", "detail": "..." }` with appropriate HTTP status:

| Code                 | HTTP | Meaning                                                                  |
|----------------------|------|--------------------------------------------------------------------------|
| `invalid_symbol`     | 400  | Symbol failed regex validation                                           |
| `symbol_not_supported` | 404 | Symbol not in the NASDAQ-10 list                                        |
| `missing_api_key`    | 503  | Server is missing `ALPHA_VANTAGE_API_KEY`                                |
| `rate_limited`       | 429  | Alpha Vantage throttled (free tier: 5 req/min, 500/day)                  |
| `api_error`          | 502  | Alpha Vantage returned an `Information` notice                           |
| `network` / `http`   | 502  | Upstream connectivity issue                                              |
| `parse`              | 502  | Alpha Vantage returned non-JSON                                          |

## Validation tests (manual)

```bash
# 1. Liveness
curl http://localhost:3015/api/health

# 2. Symbol list contains 10 entries
curl http://localhost:3015/api/stocks

# 3. Valid symbol w/ API key
curl http://localhost:3015/api/news/AAPL

# 4. Invalid symbol (regex)
curl -i http://localhost:3015/api/news/$$$

# 5. Supported-symbol filter
curl -i http://localhost:3015/api/news/IBM

# 6. Missing key surface
curl -i http://localhost:3015/api/news/AAPL   # run with the env unset
```

## CI/CD (GitHub Actions)

The pipeline lives in [`.github/workflows/ci-cd.yml`](./.github/workflows/ci-cd.yml).

### CI — triggered on every push and pull request

| Job | What it does |
|-----|--------------|
| `test-python` | Installs `requirements.txt`, runs `pytest` (`test_app.py` smoke-tests the Flask app) |
| `test-node`   | `npm ci`, then syntax-checks `server.js` and `stocks.js` with `node --check` |

### CD — triggered on every push to `main` (after both CI jobs pass)

1. Logs in to **GHCR** (GitHub Container Registry) with the built-in `GITHUB_TOKEN`.
2. Builds the `Dockerfile` and pushes the image tagged `latest` + the commit SHA, e.g.
   `ghcr.io/<owner>/<repo>:latest`.
3. Runs a placeholder deploy step — replace it with your real deployment
   (SSH, `kubectl apply`, or a cloud provider action).

> One-time setup: Settings → Actions → General → Workflow permissions → enable
> **"Read and write permissions"** so the workflow can push packages.

Run the tests locally the same way CI does:

```bash
pip install -r requirements.txt
python -m pytest test_app.py -v
```

## Project layout

```
.
├── server.js              # Express app, spawns scraper.py, exposes /api/*
├── scraper.py             # Alpha Vantage NEWS_SENTIMENT scraper (stdlib only)
├── stocks.js              # Frozen NASDAQ-10 list
├── public/
│   └── index.html         # Static frontend
├── package.json
├── .env.example
├── .gitignore
└── README.md
```

## Deployment notes

- Never commit `.env` or any file containing your real `ALPHA_VANTAGE_API_KEY`. Only `.env.example` is tracked.
- The Python scraper reads the env var in-process — it never logs the key.
- Rate limit handling: a `Note` from Alpha Vantage becomes `rate_limited` (HTTP 429). The frontend shows a friendly "try again in a minute" message.
- For process monitoring, run under your supervisor of choice (`pm2`, `systemd`, Docker, etc.). The server handles `SIGINT`/`SIGTERM` and exits gracefully.