'use strict';

const path = require('path');
const express = require('express');
const cors = require('cors');
const { spawn } = require('child_process');
const VALID_SYMBOLS = require('./stocks');

const PORT = Number(process.env.PORT) || 3015;
const SYMBOL_RE = /^[A-Z.\-]{1,10}$/;
const PY_BIN = process.env.PYTHON_BIN || (process.platform === 'win32' ? 'python' : 'python3');
const SCRAPER_PATH = path.join(__dirname, 'scraper.py');
// MOCK=1 lets the whole stack run without an Alpha Vantage key.
const MOCK = /^(1|true|yes|on)$/i.test(String(process.env.MOCK || '').trim());

const app = express();
app.disable('x-powered-by');
app.use(cors());
app.use(express.static(path.join(__dirname, 'public')));

/**
 * Spawn the Python scraper and parse its single-line JSON result.
 * Any spawn, exit-code, or parse failure is surfaced as a rejected promise
 * carrying a structured error object the caller can return to the client.
 */
function runScraper(args) {
  return new Promise((resolve, reject) => {
    let child;
    try {
      child = spawn(PY_BIN, [SCRAPER_PATH, ...args], {
        env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
        stdio: ['ignore', 'pipe', 'pipe'],
      });
    } catch (err) {
      return reject({ error: 'spawn_failed', detail: err.message });
    }

    let out = '';
    let err = '';
    child.stdout.setEncoding('utf-8');
    child.stderr.setEncoding('utf-8');
    child.stdout.on('data', (d) => {
      out += d;
    });
    child.stderr.on('data', (d) => {
      err += d;
    });
    child.on('error', (e) => reject({ error: 'spawn_error', detail: e.message }));
    child.on('close', (code) => {
      if (code !== 0) {
        return reject({ error: 'scraper_exit', code, detail: err.trim() || 'non-zero exit' });
      }
      try {
        resolve(JSON.parse(out));
      } catch (e) {
        reject({ error: 'scraper_parse', detail: e.message, stdout: out });
      }
    });
  });
}

function asyncRoute(handler) {
  return (req, res, next) => Promise.resolve(handler(req, res, next)).catch(next);
}

app.get('/api/health', (req, res) => {
  res.json({ ok: true, time: new Date().toISOString(), python: PY_BIN, mock: MOCK });
});

app.get('/api/stocks', (req, res) => {
  res.json(VALID_SYMBOLS);
});

app.get(
  '/api/news/:symbol',
  asyncRoute(async (req, res) => {
    const raw = String(req.params.symbol || '');
    const symbol = raw.trim().toUpperCase();
    if (!SYMBOL_RE.test(symbol)) {
      return res.status(400).json({ error: 'invalid_symbol', symbol });
    }
    if (!VALID_SYMBOLS.includes(symbol)) {
      return res.status(404).json({ error: 'symbol_not_supported', symbol });
    }
    if (!MOCK && !process.env.ALPHA_VANTAGE_API_KEY) {
      return res.status(503).json({ error: 'missing_api_key' });
    }
    const result = await runScraper(['news', symbol]);
    if (result && result.error) {
      const status = result.error === 'rate_limited' ? 429 : 502;
      return res.status(status).json(result);
    }
    res.json(result);
  }),
);

// Express error tail — keep last.
app.use((err, req, res, _next) => {
  // err may be either a thrown Error or a structured object from runScraper.
  const payload =
    err && typeof err === 'object' && 'error' in err
      ? err
      : { error: 'internal', detail: err && err.message ? err.message : String(err) };
  console.error('[stock4]', req.method, req.path, payload);
  res.status(500).json(payload);
});

const server = app.listen(PORT, () => {
  console.log(`stock4-app-1 listening on http://localhost:${PORT}`);
  console.log(`  python: ${PY_BIN}`);
  const keyState = MOCK
    ? 'MOCK MODE (upstream disabled)'
    : process.env.ALPHA_VANTAGE_API_KEY
      ? 'present'
      : 'MISSING (set ALPHA_VANTAGE_API_KEY)';
  console.log(`  api key: ${keyState}`);
});

function shutdown(sig) {
  console.log(`\n[stock4] ${sig} received, closing...`);
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(1), 5000).unref();
}
process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));