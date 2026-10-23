import os
import sys
from pathlib import Path

import pytest

TEST_DB = Path(__file__).resolve().parent / "test_transcriptions.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB}"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app, engine  # noqa: E402


def _reset_db():
    # Close pooled connections before deleting the file, or SQLite keeps a stale handle.
    engine.dispose()
    if TEST_DB.exists():
        TEST_DB.unlink()


@pytest.fixture()
def client():
    _reset_db()
    with TestClient(app) as c:
        yield c
    _reset_db()


def test_full_crud_roundtrip(client):
    r = client.post(
        "/api/transcriptions",
        json={"text": "  मुझे kal meeting schedule karni hai  ", "language": "hi-IN"},
    )
    assert r.status_code == 201
    item = r.json()
    assert item["text"] == "मुझे kal meeting schedule karni hai"
    assert item["created_at"].endswith(("Z", "+00:00"))

    item_url = f"/api/transcriptions/{item['id']}"
    assert client.get(item_url).json()["language"] == "hi-IN"

    r = client.put(item_url, json={"text": "Updated text"})
    assert r.status_code == 200
    assert r.json()["text"] == "Updated text"
    assert r.json()["language"] == "hi-IN"  # untouched field keeps its value

    found = client.get("/api/transcriptions", params={"q": "UPDATED"}).json()
    assert [x["id"] for x in found] == [item["id"]]

    assert client.delete(item_url).status_code == 204
    assert client.get(item_url).status_code == 404


def test_list_is_newest_first_and_paginated(client):
    for text in ["first", "second", "third"]:
        client.post("/api/transcriptions", json={"text": text, "language": "en-IN"})
    texts = [x["text"] for x in client.get("/api/transcriptions").json()]
    assert texts == ["third", "second", "first"]
    page = client.get("/api/transcriptions", params={"limit": 1, "offset": 1}).json()
    assert [x["text"] for x in page] == ["second"]


def test_rejects_blank_text(client):
    assert client.post("/api/transcriptions", json={"text": "   "}).status_code == 422


def test_rejects_invalid_language(client):
    r = client.post("/api/transcriptions", json={"text": "hello", "language": "!!"})
    assert r.status_code == 422


def test_search_treats_wildcards_literally(client):
    client.post("/api/transcriptions", json={"text": "100% done"})
    client.post("/api/transcriptions", json={"text": "nothing here"})
    found = client.get("/api/transcriptions", params={"q": "%"}).json()
    assert [x["text"] for x in found] == ["100% done"]


def test_update_unknown_id_returns_404(client):
    assert client.put("/api/transcriptions/9999", json={"text": "x"}).status_code == 404


def test_index_page_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Speech to Text" in r.text
