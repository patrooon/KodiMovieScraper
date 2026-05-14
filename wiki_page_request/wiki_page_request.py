"""Wikipedia and Wikidata movie lookup client.

The requester searches Wikipedia for a title, confirms candidates through
Wikidata, fetches a short summary and thumbnail URL, then optionally stores the
result in the SQLite cache.
"""

import logging
import sys
import textwrap
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

if __package__ in (None, ""):
    # Direct execution from inside this package removes the project root from
    # sys.path. Add it back so `from database import ...` still works.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import MovieCacheDatabase

WIKI_API_URL = "https://en.wikipedia.org/w/api.php"

HEADERS = {
    "User-Agent": "KodiMovieScraper"
}


@dataclass(frozen=True)
class WikipediaRequestConfig:
    """Configuration for Wikipedia and Wikidata HTTP requests."""

    wiki_api_url: str = WIKI_API_URL
    headers: Mapping[str, str] = field(default_factory=lambda: dict(HEADERS))
    timeout: float = 10.0


@dataclass(frozen=True)
class MovieInfo(Mapping[str, Any]):
    """Normalized movie metadata returned by the requester."""

    title: str
    wikidata_id: str | None = None
    summary: str | None = None
    thumbnail: str | None = None
    search_term: str | None = None

    @property
    def id(self) -> str | None:
        """Backward-compatible alias for the Wikidata ID."""
        return self.wikidata_id

    def __getitem__(self, key: str) -> Any:
        """Return field values using dictionary-style access."""
        return self.to_dict()[key]

    def __iter__(self):
        """Iterate over dictionary-style field names."""
        return iter(self.to_dict())

    def __len__(self) -> int:
        """Return the number of dictionary-style fields."""
        return len(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        """Convert movie metadata to the cache/API dictionary shape."""
        return {
            "id": self.id,
            "title": self.title,
            "summary": self.summary,
            "thumbnail": self.thumbnail,
            "wikidata_id": self.wikidata_id,
            "search_term": self.search_term,
        }


class WikipediaMovieRequester:
    """Fetches movie information from Wikipedia/Wikidata and formats it for display."""

    def __init__(
        self,
        cache: MovieCacheDatabase | None = None,
        config: WikipediaRequestConfig | None = None,
        wiki_api_url: str | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> None:
        """Initialize the requester.

        Args:
            cache: Cache object compatible with MovieCacheDatabase. A default
                cache is created when none is provided.
            config: Request configuration. Constructor keyword overrides below
                are applied on top of this config when provided.
            wiki_api_url: Optional Wikipedia API endpoint override.
            headers: Optional HTTP headers override.
            timeout: Optional request timeout override, in seconds.
        """
        self.cache = cache or MovieCacheDatabase()
        request_config = config or WikipediaRequestConfig()
        self.config = WikipediaRequestConfig(
            wiki_api_url=wiki_api_url or request_config.wiki_api_url,
            headers=headers or request_config.headers,
            timeout=timeout if timeout is not None else request_config.timeout,
        )

    def search_wikipedia(self, title: str) -> list[str]:
        """Search Wikipedia for candidate page titles.

        Args:
            title: Movie title or search phrase.

        Returns:
            list[str]: Candidate Wikipedia page titles. Returns an empty list
            when the request fails or the response is malformed.
        """
        params = {
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": title,
            "srlimit": 5
        }

        try:
            response = requests.get(
                self.config.wiki_api_url,
                params=params,
                headers=self.config.headers,
                timeout=self.config.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as e:
            logging.error(f"Wikipedia search failed: {e}")
            return []

        results = data.get("query", {}).get("search", [])
        return [r["title"] for r in results if "title" in r]

    def get_page_data(self, title: str) -> dict[str, Any] | None:
        """Fetch summary, image, and Wikidata metadata for a Wikipedia page.

        Args:
            title: Exact Wikipedia page title.

        Returns:
            dict | None: Raw Wikipedia page data, or None when the page is
            missing/unavailable.
        """
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
            response = requests.get(
                self.config.wiki_api_url,
                params=params,
                headers=self.config.headers,
                timeout=self.config.timeout,
            )
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

    def is_film(self, wikidata_id: str | None) -> bool:
        """Check whether a Wikidata entity is a film.

        Args:
            wikidata_id: Wikidata entity ID, such as ``Q204057``.

        Returns:
            bool: True if the entity has an "instance of film" claim.
        """
        if not wikidata_id:
            return False

        url = f"https://www.wikidata.org/wiki/Special:EntityData/{wikidata_id}.json"

        try:
            response = requests.get(
                url,
                headers=self.config.headers,
                timeout=self.config.timeout,
            )
            response.raise_for_status()
            data = response.json()

            claims = data["entities"][wikidata_id]["claims"]

            # P31 means "instance of" in Wikidata; Q11424 is "film".
            for claim in claims.get("P31", []):
                value = claim["mainsnak"].get("datavalue", {}).get("value", {})
                if value.get("id") == "Q11424":
                    return True

        except (requests.RequestException, ValueError, KeyError, TypeError) as e:
            logging.error(f"Wikidata check failed: {e}")

        return False

    def get_movie_info(self, title: str) -> MovieInfo | None:
        """Find the best matching film page and return normalized movie data.

        Args:
            title: Movie title entered by the user.

        Returns:
            MovieInfo | None: Normalized movie data with title, summary, thumbnail,
            and Wikidata ID. Returns None when no film candidate is found.
        """
        candidates = [f"{title} (film)"] + self.search_wikipedia(title)

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

    def get_image_url(self, filename: str | None) -> str | None:
        """Resolve a Wikipedia image filename to a public image URL.

        Args:
            filename: Wikipedia page image filename.

        Returns:
            str | None: Public image URL, or None when no image is available.
        """
        if not filename:
            return None

        try:
            response = requests.get(
                self.config.wiki_api_url,
                params={
                    "action": "query",
                    "format": "json",
                    "titles": f"File:{filename}",
                    "prop": "imageinfo",
                    "iiprop": "url",
                },
                headers=self.config.headers,
                timeout=self.config.timeout,
            )
            response.raise_for_status()
            data = response.json()
            pages = data.get("query", {}).get("pages", {})
            page = next(iter(pages.values()))

            imageinfo = page.get("imageinfo") or [{}]
            return imageinfo[0].get("url")
        except (
            requests.RequestException,
            ValueError,
            StopIteration,
            KeyError,
            TypeError,
        ) as e:
            logging.error(f"Wikipedia image request failed: {e}")
            return None

    def format_movie_info(self, movie_info: Mapping[str, Any]) -> str:
        """Format movie metadata for console output.

        Args:
            movie_info: Movie metadata dictionary from the cache or requester.

        Returns:
            str: Human-readable movie details block.
        """
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

    def run_cli(self) -> None:
        """Run the interactive command-line lookup flow."""
        self.cache.init_db()
        movie_title = input("Enter movie title: ")

        info = self.get_movie_info(movie_title)

        if not info:
            print("No movie found.")
            return

        self.cache.save_movie(movie_title, info)
        cached_info = self.cache.get_movie(movie_title)
        print(self.format_movie_info(cached_info))


def main() -> None:
    """Run the command-line entry point."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    WikipediaMovieRequester().run_cli()


if __name__ == "__main__":
    main()
