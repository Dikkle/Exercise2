"""app.py

Flask frontend for the merged SQLite database (merged_data.db).

Pages / endpoints:
  GET /                     -> main page (rendered by JS from the API below)
  GET /api/merged-orders    -> rows of the merged_orders table
  GET /api/summary          -> rows of the avg_amount_by_region table
  GET /api/status           -> database modification time (used for auto-refresh)

The frontend polls /api/status every 2 seconds and automatically reloads
the tables when the database file changes.
"""

import os
import sqlite3

from flask import Flask, jsonify, render_template

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "merged_data.db")

app = Flask(__name__)


def query_db(sql: str):
    """Run a SELECT query and return rows as a list of dicts."""
    if not os.path.exists(DB_PATH):
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(sql).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def db_mtime():
    """Modification time of the database file (0 if it does not exist)."""
    try:
        return os.path.getmtime(DB_PATH)
    except OSError:
        return 0


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def status():
    return jsonify({"db_mtime": db_mtime(), "db_exists": os.path.exists(DB_PATH)})


@app.route("/api/merged-orders")
def merged_orders():
    rows = query_db("SELECT * FROM merged_orders ORDER BY order_id")
    return jsonify({"rows": rows})


@app.route("/api/summary")
def summary():
    rows = query_db(
        "SELECT region, avg_amount_cny FROM avg_amount_by_region ORDER BY avg_amount_cny DESC"
    )
    # Round for display
    for r in rows:
        r["avg_amount_cny"] = round(r["avg_amount_cny"], 2)
    return jsonify({"rows": rows})


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
