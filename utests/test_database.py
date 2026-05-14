from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import database


def use_temp_db(monkeypatch, tmp_path):
    db_path = tmp_path / "test_wikipedia_cache.db"
    monkeypatch.setattr(database, "DB_NAME", db_path)
    database.init_db()
    return db_path


def test_init_db_creates_movie_cache_table(monkeypatch, tmp_path):
    db_path = use_temp_db(monkeypatch, tmp_path)

    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            ("movie_cache",),
        )

        assert cursor.fetchone() == ("movie_cache",)


def test_save_and_get_movie_round_trip(monkeypatch, tmp_path):
    use_temp_db(monkeypatch, tmp_path)
    movie_info = {
        "wikidata_id": "Q123",
        "title": "Example Movie",
        "summary": "A useful test movie.",
        "thumbnail": "https://example.com/image.jpg",
    }

    saved = database.save_movie_to_db("example", movie_info)
    result = database.get_movie_from_db("example")

    assert saved is True
    assert result == {
        "wikidata_id": "Q123",
        "title": "Example Movie",
        "summary": "A useful test movie.",
        "thumbnail": "https://example.com/image.jpg",
        "search_term": "example",
    }


def test_save_movie_rejects_empty_inputs(monkeypatch, tmp_path):
    use_temp_db(monkeypatch, tmp_path)

    assert database.save_movie_to_db("", {"title": "No key"}) is False
    assert database.save_movie_to_db("missing-info", None) is False
    assert database.save_movie_to_db("missing-title", {"summary": "No title"}) is False
    assert database.get_movie_from_db("") is None


def test_save_movie_replaces_existing_search_term(monkeypatch, tmp_path):
    use_temp_db(monkeypatch, tmp_path)

    database.save_movie_to_db(
        "same search",
        {
            "wikidata_id": "Q1",
            "title": "Old Title",
            "summary": "Old summary",
            "thumbnail": "old.jpg",
        },
    )
    database.save_movie_to_db(
        "same search",
        {
            "wikidata_id": "Q2",
            "title": "New Title",
            "summary": "New summary",
            "thumbnail": "new.jpg",
        },
    )

    result = database.get_movie_from_db("same search")

    assert result["wikidata_id"] == "Q2"
    assert result["title"] == "New Title"
    assert result["summary"] == "New summary"
    assert result["thumbnail"] == "new.jpg"


def test_get_movie_returns_none_for_unknown_search_term(monkeypatch, tmp_path):
    use_temp_db(monkeypatch, tmp_path)

    assert database.get_movie_from_db("not cached") is None


def test_cleanup_cache_removes_only_expired_entries(monkeypatch, tmp_path):
    use_temp_db(monkeypatch, tmp_path)

    fake_now = 1_700_000_000
    monkeypatch.setattr(database.time, "time", lambda: fake_now)

    database.save_movie_to_db(
        "fresh",
        {
            "wikidata_id": "QFresh",
            "title": "Fresh Movie",
            "summary": "Still valid.",
            "thumbnail": None,
        },
    )

    with database.get_connection() as conn:
        conn.execute(
            database.SQL_UPSERT_MOVIE,
            (
                "old",
                "QOld",
                "Old Movie",
                "Expired entry.",
                None,
                fake_now - (31 * 24 * 60 * 60),
            ),
        )

    database.cleanup_cache(days_to_keep=30)

    assert database.get_movie_from_db("fresh")["title"] == "Fresh Movie"
    assert database.get_movie_from_db("old") is None
