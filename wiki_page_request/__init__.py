"""Public exports for the Wikipedia movie requester package."""

from .wiki_page_request import (
    HEADERS,
    WIKI_API_URL,
    WikipediaMovieRequester,
    WikipediaRequestConfig,
)

__all__ = [
    "HEADERS",
    "WIKI_API_URL",
    "WikipediaRequestConfig",
    "WikipediaMovieRequester",
]
