import sqlite3
import time
import logging
from contextlib import closing
from pathlib import Path

# ==========================================
# KONFIGURATION & SQL-KONSTANTEN
# ==========================================
DB_NAME = Path(__file__).with_name("wikipedia_cache.db")

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
INSERT OR REPLACE INTO movie_cache (search_term, wikidata_id, title, summary, thumbnail, last_updated)
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


# ==========================================
# DATENBANK-FUNKTIONEN (API FÜR DAS ADDON)
# ==========================================

def get_connection():
    """Erstellt eine threadsichere Verbindung mit Timeout."""
    return sqlite3.connect(str(DB_NAME), timeout=10.0, check_same_thread=False)


def init_db():
    """Erstellt die Datenbankdatei und die Tabelle, falls sie nicht existieren."""
    try:
        with closing(get_connection()) as conn:
            conn.isolation_level = None
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.isolation_level = ''

            with conn:
                conn.execute(SQL_CREATE_TABLE)

    except sqlite3.Error as e:
        logging.error(f"Datenbankfehler bei der Initialisierung: {e}")


def save_movie_to_db(search_term, movie_info):
    """
    Speichert oder aktualisiert einen Film im Cache.
    Erfordert nun zwingend den Suchbegriff als Schlüssel.
    """
    if not search_term or not movie_info or not movie_info.get("title"):
        return False

    current_time = int(time.time())

    try:
        with closing(get_connection()) as conn:
            with conn:
                conn.execute(SQL_UPSERT_MOVIE, (
                    search_term,
                    movie_info.get("wikidata_id"),
                    movie_info.get("title"),
                    movie_info.get("summary"),
                    movie_info.get("thumbnail"),
                    current_time
                ))
        return True
    except sqlite3.Error as e:
        logging.error(f"Fehler beim Speichern in den Cache: {e}")
        return False


def get_movie_from_db(search_term):
    """
    Ruft einen Film anhand des Suchbegriffs (Input von Kodi) aus dem Cache ab.
    """
    if not search_term:
        return None

    try:
        with closing(get_connection()) as conn:
            cursor = conn.cursor()
            cursor.execute(SQL_GET_MOVIE, (search_term,))
            result = cursor.fetchone()

            if result:
                return {
                    "wikidata_id": result[0],
                    "title": result[1],
                    "summary": result[2],
                    "thumbnail": result[3],
                    "search_term": search_term
                }
        return None
    except sqlite3.Error as e:
        logging.error(f"Fehler beim Lesen aus dem Cache: {e}")
        return None


def cleanup_cache(days_to_keep=30):
    """Löscht Einträge, die älter als die angegebene Anzahl an Tagen sind."""
    seconds_to_keep = days_to_keep * 24 * 60 * 60
    cutoff_time = int(time.time()) - seconds_to_keep

    try:
        with closing(get_connection()) as conn:
            with conn:
                conn.execute(SQL_CLEANUP_CACHE, (cutoff_time,))
    except sqlite3.Error as e:
        logging.error(f"Fehler bei der Cache-Bereinigung: {e}")
