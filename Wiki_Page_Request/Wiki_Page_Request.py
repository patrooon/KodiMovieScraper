import logging
import sys
import textwrap
from pathlib import Path

import requests

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import MovieCacheDatabase

WIKI_API_URL = "https://en.wikipedia.org/w/api.php"

HEADERS = {
    "User-Agent": "KodiMovieScraper"
}


class WikipediaMovieRequester:
    """Fetches movie information from Wikipedia/Wikidata and formats it for display."""

    def __init__(self, cache=None, wiki_api_url=WIKI_API_URL, headers=None):
        self.cache = cache or MovieCacheDatabase()
        self.wiki_api_url = wiki_api_url
        self.headers = headers or HEADERS

    def search_wikipedia(self, title):
        params = {
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": title,
            "srlimit": 5
        }

        try:
            response = requests.get(self.wiki_api_url, params=params, headers=self.headers, timeout=10)
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as e:
            logging.error(f"Wikipedia search failed: {e}")
            return []

        results = data.get("query", {}).get("search", [])
        return [r["title"] for r in results if "title" in r]

    def get_page_data(self, title):
        params = {
            "action": "query",
            "format": "json",
            "prop": "extracts|pageimages|pageprops",
            "titles": title,
            "exintro": True,
            "explaintext": True,
            "pithumbsize": 500
        }

        try:
            response = requests.get(self.wiki_api_url, params=params, headers=self.headers, timeout=10)
            response.raise_for_status()

            if not response.text.strip():
                return None

            data = response.json()
        except (requests.RequestException, ValueError) as e:
            logging.error(f"Wikipedia page request failed: {e}")
            return None

        pages = data.get("query", {}).get("pages", {})
        if not pages:
            return None

        page = next(iter(pages.values()))

        if "missing" in page:
            return None

        return page

    def is_film(self, wikidata_id):
        if not wikidata_id:
            return False

        url = f"https://www.wikidata.org/wiki/Special:EntityData/{wikidata_id}.json"

        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            data = response.json()

            claims = data["entities"][wikidata_id]["claims"]

            # P31 = instance of
            for claim in claims.get("P31", []):
                value = claim["mainsnak"].get("datavalue", {}).get("value", {})
                if value.get("id") == "Q11424":  # Q11424 is the identifier for films
                    return True

        except (requests.RequestException, ValueError, KeyError, TypeError) as e:
            logging.error(f"Wikidata check failed: {e}")

        return False

    def get_movie_info(self, title):
        candidates = [f"{title} (film)"] + self.search_wikipedia(title)

        for candidate in candidates:
            page = self.get_page_data(candidate)
            if not page:
                continue

            wikidata_id = page.get("pageprops", {}).get("wikibase_item")

            if self.is_film(wikidata_id):
                pageprops = page.get("pageprops", {})

                return {
                    "id": wikidata_id,
                    "title": page.get("title"),
                    "summary": page.get("extract"),
                    "thumbnail": self.get_image_url(pageprops.get("page_image")),
                    "wikidata_id": wikidata_id
                }

        return None

    def get_image_url(self, filename):
        if not filename:
            return None

        try:
            response = requests.get(
                self.wiki_api_url,
                params={
                    "action": "query",
                    "format": "json",
                    "titles": f"File:{filename}",
                    "prop": "imageinfo",
                    "iiprop": "url"
                },
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            pages = data.get("query", {}).get("pages", {})
            page = next(iter(pages.values()))

            imageinfo = page.get("imageinfo") or [{}]
            return imageinfo[0].get("url")
        except (requests.RequestException, ValueError, StopIteration, KeyError, TypeError) as e:
            logging.error(f"Wikipedia image request failed: {e}")
            return None

    def format_movie_info(self, movie_info):
        title = movie_info.get("title") or "Unknown title"
        summary = movie_info.get("summary") or "No summary available."
        thumbnail = movie_info.get("thumbnail") or "No thumbnail available."
        wikidata_id = movie_info.get("wikidata_id") or "No Wikidata ID available."
        search_term = movie_info.get("search_term") or "No search term available."

        wrapped_summary = textwrap.fill(summary, width=88)

        return f"""
============================================================
Movie found
============================================================
Title:       {title}
Search term: {search_term}
Wikidata ID: {wikidata_id}
Thumbnail:   {thumbnail}

Summary:
{wrapped_summary}
============================================================
""".strip()

    def run_cli(self):
        self.cache.init_db()
        movie_title = input("Enter movie title: ")

        info = self.get_movie_info(movie_title)

        if not info:
            print("No movie found.")
            return

        self.cache.save_movie_to_db(movie_title, info)
        cached_info = self.cache.get_movie_from_db(movie_title)
        print(self.format_movie_info(cached_info))


if __name__ == "__main__":
    WikipediaMovieRequester().run_cli()
