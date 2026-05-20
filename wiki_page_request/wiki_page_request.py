"""Wikipedia and Wikidata movie lookup client."""

import json
import logging
import sys
import textwrap
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from database import MovieCacheDatabase
except ImportError:
    from database.database import MovieCacheDatabase


WIKI_API_URL = "https://en.wikipedia.org/w/api.php"

HEADERS = {
    "User-Agent": "KodiMovieScraper/0.1.3"
}


@dataclass(frozen=True)
class WikipediaRequestConfig:
    """Configuration for Wikipedia and Wikidata HTTP requests."""

    wiki_api_url: str = WIKI_API_URL
    headers: Mapping = field(default_factory=lambda: dict(HEADERS))
    timeout: float = 10.0


@dataclass(frozen=True)
class MovieInfo(Mapping):
    """Normalized movie metadata returned by the requester."""

    title: str
    wikidata_id: str | None = None
    summary: str | None = None
    thumbnail: str | None = None
    search_term: str | None = None

    @property
    def id(self):
        return self.wikidata_id

    def __getitem__(self, key):
        return self.to_dict()[key]

    def __iter__(self):
        return iter(self.to_dict())

    def __len__(self):
        return len(self.to_dict())

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "summary": self.summary,
            "thumbnail": self.thumbnail,
            "wikidata_id": self.wikidata_id,
            "search_term": self.search_term,
        }

    def get(self, key, default=None):
        return self.to_dict().get(key, default)


class WikipediaMovieRequester:
    """Fetches movie information from Wikipedia/Wikidata and formats it for display."""

    def __init__(
        self,
        cache=None,
        config=None,
        wiki_api_url=None,
        headers=None,
        timeout=None,
    ):
        self.cache = cache or MovieCacheDatabase()
        request_config = config or WikipediaRequestConfig()

        self.config = WikipediaRequestConfig(
            wiki_api_url=wiki_api_url or request_config.wiki_api_url,
            headers=headers or request_config.headers,
            timeout=timeout if timeout is not None else request_config.timeout,
        )

    def _get_json(self, url, params=None):
        """Send a GET request and return JSON data."""

        if params:
            query = urllib.parse.urlencode(params)
            url = url + "?" + query

        request = urllib.request.Request(
            url,
            headers=dict(self.config.headers),
        )

        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout) as response:
                text = response.read().decode("utf-8")

                if not text.strip():
                    return None

                return json.loads(text)

        except Exception as e:
            logging.error("HTTP request failed: %s", e)
            return None

    def search_wikipedia(self, title):
        """Search Wikipedia for candidate page titles."""

        params = {
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": title,
            "srlimit": 5,
        }

        data = self._get_json(self.config.wiki_api_url, params)

        if not data:
            return []

        results = data.get("query", {}).get("search", [])

        return [result["title"] for result in results if "title" in result]

    def get_page_data(self, title):
        """Fetch summary, image, and Wikidata metadata for a Wikipedia page."""

        params = {
            "action": "query",
            "format": "json",
            "prop": "extracts|pageimages|pageprops",
            "titles": title,
            "exintro": True,
            "explaintext": True,
            "pithumbsize": 500,
        }

        data = self._get_json(self.config.wiki_api_url, params)

        if not data:
            return None

        pages = data.get("query", {}).get("pages", {})

        if not pages:
            return None

        page = next(iter(pages.values()))

        if "missing" in page:
            return None

        return page

    def is_film(self, wikidata_id):
        """Check whether a Wikidata entity is a film."""

        if not wikidata_id:
            return False

        url = f"https://www.wikidata.org/wiki/Special:EntityData/{wikidata_id}.json"

        data = self._get_json(url)

        if not data:
            return False

        try:
            claims = data["entities"][wikidata_id]["claims"]

            for claim in claims.get("P31", []):
                value = claim["mainsnak"].get("datavalue", {}).get("value", {})

                if value.get("id") == "Q11424":
                    return True

        except (KeyError, TypeError, ValueError) as e:
            logging.error("Wikidata check failed: %s", e)

        return False

    def get_movie_info(self, title):
        """Find the best matching film page and return normalized movie data."""

        candidates = [title + " (film)"] + self.search_wikipedia(title)

        for candidate in candidates:
            page = self.get_page_data(candidate)

            if not page:
                continue

            wikidata_id = page.get("pageprops", {}).get("wikibase_item")

            if self.is_film(wikidata_id):
                pageprops = page.get("pageprops", {})

                return MovieInfo(
                    title=page.get("title") or candidate,
                    wikidata_id=wikidata_id,
                    summary=page.get("extract"),
                    thumbnail=self.get_image_url(pageprops.get("page_image")),
                )

        return None

    def get_movie_infos(self, title, limit=15):
        """Find film candidates for a title."""

        candidates = [title + " (film)"] + self.search_wikipedia(title)
        movies = []
        seen_titles = set()

        for candidate in candidates:
            if len(movies) >= limit:
                break

            page = self.get_page_data(candidate)

            if not page:
                continue

            page_title = page.get("title") or candidate

            if page_title in seen_titles:
                continue

            wikidata_id = page.get("pageprops", {}).get("wikibase_item")

            if not self.is_film(wikidata_id):
                continue

            pageprops = page.get("pageprops", {})

            movies.append(
                MovieInfo(
                    title=page_title,
                    wikidata_id=wikidata_id,
                    summary=page.get("extract"),
                    thumbnail=self.get_image_url(pageprops.get("page_image")),
                )
            )

            seen_titles.add(page_title)

        return movies

    def get_image_url(self, filename):
        """Resolve a Wikipedia image filename to a public image URL."""

        if not filename:
            return None

        params = {
            "action": "query",
            "format": "json",
            "titles": f"File:{filename}",
            "prop": "imageinfo",
            "iiprop": "url",
        }

        data = self._get_json(self.config.wiki_api_url, params)

        if not data:
            return None

        try:
            pages = data.get("query", {}).get("pages", {})
            page = next(iter(pages.values()))
            imageinfo = page.get("imageinfo") or [{}]

            return imageinfo[0].get("url")

        except (StopIteration, KeyError, TypeError) as e:
            logging.error("Wikipedia image request failed: %s", e)
            return None

    def format_movie_info(self, movie_info):
        """Format movie metadata for console output."""

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
        """Run the interactive command-line lookup flow."""

        self.cache.init_db()
        movie_title = input("Enter movie title: ")

        info = self.get_movie_info(movie_title)

        if not info:
            print("No movie found.")
            return

        self.cache.save_movie(movie_title, info.to_dict())
        cached_info = self.cache.get_movie(movie_title)

        print(self.format_movie_info(cached_info))


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    WikipediaMovieRequester().run_cli()


if __name__ == "__main__":
    main()