"""SQLite cache storage for movie metadata.

This module contains the cache class used by the Wikipedia requester. The cache
stores successful lookups by the original search term so repeated requests from
Kodi or the command line do not need to hit Wikipedia again.
"""

import logging
import sqlite3
import time
from contextlib import closing
from pathlib import Path

DB_NAME = Path(__file__).resolve().parents[1] / "wikipedia_cache.db"

SQL_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS movie_cache (
    search_term TEXT PRIMARY KEY,
    wikidata_id TEXT,
    title TEXT NOT NULL,
    summary TEXT,
    thumbnail TEXT,
    last_updated INTEGER NOT NULL
);
"""

SQL_UPSERT_MOVIE = """
INSERT OR REPLACE INTO movie_cache (
    search_term,
    wikidata_id,
    title,
    summary,
    thumbnail,
    last_updated
)
VALUES (?, ?, ?, ?, ?, ?);
"""

SQL_GET_MOVIE = """
SELECT wikidata_id, title, summary, thumbnail
FROM movie_cache
WHERE search_term = ?;
"""

SQL_CLEANUP_CACHE = """
DELETE FROM movie_cache
WHERE last_updated < ?;
"""


class MovieCacheDatabase:
    """SQLite cache for movie data returned by the Wikipedia requester."""

    def __init__(self, db_name=DB_NAME):
        """Initialize the cache wrapper.

        Args:
            db_name: Path to the SQLite database file. Defaults to the project
                root cache file.
        """
        self.db_name = Path(db_name)

    def get_connection(self):
        """Create a SQLite connection with a short busy timeout.

        Returns:
            sqlite3.Connection: Open connection to the configured cache file.
        """
        return sqlite3.connect(
            str(self.db_name),
            timeout=10.0,
            check_same_thread=False,
        )

    def init_db(self):
        """Create the database file and table if they do not already exist."""
        try:
            with closing(self.get_connection()) as conn:
                # WAL improves read/write behavior when Kodi or tests open
                # short-lived connections close together in time.
                conn.isolation_level = None
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.isolation_level = ""

                with conn:
                    conn.execute(SQL_CREATE_TABLE)

        except sqlite3.Error as e:
            logging.error(f"Datenbankfehler bei der Initialisierung: {e}")

    def save_movie_to_db(self, search_term, movie_info):
        """Save or update a movie cache entry.

        Args:
            search_term: Original user/Kodi search term. Used as the cache key.
            movie_info: Movie metadata dictionary returned by the requester.

        Returns:
            bool: True when the entry was saved, False for invalid input or a
            database error.
        """
        if not search_term or not movie_info or not movie_info.get("title"):
            return False

        current_time = int(time.time())

        try:
            with closing(self.get_connection()) as conn:
                with conn:
                    conn.execute(
                        SQL_UPSERT_MOVIE,
                        (
                            search_term,
                            movie_info.get("wikidata_id"),
                            movie_info.get("title"),
                            movie_info.get("summary"),
                            movie_info.get("thumbnail"),
                            current_time,
                        ),
                    )
            return True
        except sqlite3.Error as e:
            logging.error(f"Fehler beim Speichern in den Cache: {e}")
            return False

    def get_movie_from_db(self, search_term):
        """Load a movie cache entry by search term.

        Args:
            search_term: Original user/Kodi search term.

        Returns:
            dict | None: Cached movie metadata, or None when no entry exists.
        """
        if not search_term:
            return None

        try:
            with closing(self.get_connection()) as conn:
                cursor = conn.cursor()
                cursor.execute(SQL_GET_MOVIE, (search_term,))
                result = cursor.fetchone()

                if result:
                    return {
                        "wikidata_id": result[0],
                        "title": result[1],
                        "summary": result[2],
                        "thumbnail": result[3],
                        "search_term": search_term,
                    }
            return None
        except sqlite3.Error as e:
            logging.error(f"Fehler beim Lesen aus dem Cache: {e}")
            return None

    def cleanup_cache(self, days_to_keep=30):
        """Delete cache entries older than the configured age.

        Args:
            days_to_keep: Number of days a cache entry should remain valid.
        """
        seconds_to_keep = days_to_keep * 24 * 60 * 60
        cutoff_time = int(time.time()) - seconds_to_keep

        try:
            with closing(self.get_connection()) as conn:
                with conn:
                    conn.execute(SQL_CLEANUP_CACHE, (cutoff_time,))
        except sqlite3.Error as e:
            logging.error(f"Fehler bei der Cache-Bereinigung: {e}")
