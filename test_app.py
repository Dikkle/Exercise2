"""Minimal smoke tests for the Flask app (run by CI)."""

from app import app


def test_index_returns_200():
    client = app.test_client()
    resp = client.get("/")
    assert resp.status_code == 200


def test_index_renders_template():
    client = app.test_client()
    resp = client.get("/")
    assert b"<html" in resp.data.lower()
