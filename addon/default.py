"""Kodi entry point for the movie scraper addon."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs


def _translate_path(path: str) -> str:
    """Return a filesystem path from a Kodi special path."""
    if hasattr(xbmcvfs, "translatePath"):
        return xbmcvfs.translatePath(path)
    return xbmc.translatePath(path)


def _add_project_import_paths(addon_path: str) -> None:
    """Add addon/project paths so packaged scraper modules can be imported."""
    paths = [
        addon_path,
        str(Path(addon_path).parent),
    ]

    for path in paths:
        if path not in sys.path:
            sys.path.insert(0, path)


def main() -> None:
    """Run the Kodi addon flow."""
    addon = xbmcaddon.Addon()
    addon_path = _translate_path(addon.getAddonInfo("path"))
    profile_path = _translate_path(addon.getAddonInfo("profile"))
    xbmcvfs.mkdirs(profile_path)
    _add_project_import_paths(addon_path)

    try:
        from database import MovieCacheDatabase
        from wiki_page_request import WikipediaMovieRequester
    except Exception as exc:
        xbmcgui.Dialog().ok("Kodi Movie Scraper Fehler", f"Import-Fehler: {exc}")
        xbmc.log(f"Kodi Movie Scraper import error: {exc}", xbmc.LOGERROR)
        return

    dialog = xbmcgui.Dialog()
    title = dialog.input("Film suchen", type=xbmcgui.INPUT_ALPHANUM)
    if not title:
        return

    try:
        db_path = os.path.join(profile_path, "wikipedia_cache.db")
        cache = MovieCacheDatabase(db_path)
        cache.init_db()
        requester = WikipediaMovieRequester(cache=cache)

        movies = requester.get_movie_infos(title, limit=15)
        if not movies:
            dialog.notification(
                "Kodi Movie Scraper",
                "Kein Film gefunden.",
                xbmcgui.NOTIFICATION_WARNING,
                5000,
            )
            return

        labels = []
        for movie in movies:
            label = movie.title or "Unbekannter Film"
            if movie.wikidata_id:
                label = f"{label} [{movie.wikidata_id}]"
            labels.append(label)

        index = dialog.select("Film auswählen", labels)
        if index < 0:
            return

        selected = movies[index]
        cache.save_movie(title, selected)
        text = requester.format_movie_info(selected)
        dialog.textviewer(selected.title or "Film-Informationen", text)
    except Exception as exc:
        xbmcgui.Dialog().ok("Kodi Movie Scraper Fehler", str(exc))
        xbmc.log(f"Kodi Movie Scraper runtime error: {exc}", xbmc.LOGERROR)


if __name__ == "__main__":
    main()
