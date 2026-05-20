"""Kodi entry point for the movie scraper addon."""

import base64
import os
import sys
from pathlib import Path

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs


def _translate_path(path):
    if hasattr(xbmcvfs, "translatePath"):
        return xbmcvfs.translatePath(path)
    return xbmc.translatePath(path)


def _add_project_import_paths(addon_path):
    paths = [
        addon_path,
        str(Path(addon_path).parent),
    ]

    for path in paths:
        if path not in sys.path:
            sys.path.insert(0, path)


def create_black_background_image(profile_path):
    """Erstellt automatisch eine 1x1 schwarze PNG-Datei."""

    black_png_path = os.path.join(profile_path, "black.png")

    if not os.path.exists(black_png_path):
        black_png_base64 = (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
            "AAAADUlEQVR42mNkYGD4DwABBAEAghVjVwAAAABJRU5ErkJggg=="
        )

        with open(black_png_path, "wb") as file:
            file.write(base64.b64decode(black_png_base64))

    return black_png_path.replace("\\", "/")


class CustomMovieDialog(xbmcgui.WindowXMLDialog):
    """Benutzerdefiniertes Fenster für die Filmanzeige."""

    def onInit(self):
        if hasattr(self, "black_background_path") and self.black_background_path:
            self.setProperty("black_background", self.black_background_path)

        if hasattr(self, "thumbnail_url") and self.thumbnail_url:
            self.getControl(100).setImage(self.thumbnail_url)

        if hasattr(self, "movie_title") and self.movie_title:
            self.getControl(200).setLabel(self.movie_title)

        if hasattr(self, "movie_summary") and self.movie_summary:
            self.getControl(300).setText(self.movie_summary)

    def onClick(self, controlId):
        if controlId == 1:
            self.close()


def main():
    addon = xbmcaddon.Addon()
    addon_path = _translate_path(addon.getAddonInfo("path"))
    profile_path = _translate_path(addon.getAddonInfo("profile"))

    xbmcvfs.mkdirs(profile_path)
    _add_project_import_paths(addon_path)

    black_background_path = create_black_background_image(profile_path)

    try:
        from database import MovieCacheDatabase
        from wiki_page_request import WikipediaMovieRequester
    except Exception as exc:
        xbmcgui.Dialog().ok("Kodi Movie Scraper Fehler", "Import-Fehler: {}".format(exc))
        xbmc.log("Kodi Movie Scraper import error: {}".format(exc), xbmc.LOGERROR)
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
                label = "{} [{}]".format(label, movie.wikidata_id)

            labels.append(label)

        index = dialog.select("Film auswählen", labels)

        if index < 0:
            return

        selected = movies[index]
        cache.save_movie(title, selected)

        ui = CustomMovieDialog(
            "script-movie-info.xml",
            addon_path,
            "default",
            "1080i",
        )

        ui.black_background_path = black_background_path
        ui.thumbnail_url = selected.thumbnail
        ui.movie_title = selected.title
        ui.movie_summary = selected.summary

        ui.doModal()
        del ui

    except Exception as exc:
        xbmcgui.Dialog().ok("Kodi Movie Scraper Fehler", str(exc))
        xbmc.log("Kodi Movie Scraper runtime error: {}".format(exc), xbmc.LOGERROR)


if __name__ == "__main__":
    main()