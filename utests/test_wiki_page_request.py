from pathlib import Path
import sys

import pytest

requests = pytest.importorskip("requests")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import Wiki_Page_Request as wiki


class FakeResponse:
    def __init__(self, payload=None, text="response body", error=None):
        self.payload = payload or {}
        self.text = text
        self.error = error

    def raise_for_status(self):
        if self.error:
            raise self.error

    def json(self):
        return self.payload


def test_search_wikipedia_returns_titles_and_ignores_malformed_results(monkeypatch):
    def fake_get(url, params, headers, timeout):
        assert url == wiki.WIKI_API_URL
        assert params["list"] == "search"
        assert headers == wiki.HEADERS
        assert timeout == 10
        return FakeResponse(
            {
                "query": {
                    "search": [
                        {"title": "Arrival"},
                        {"snippet": "Missing title should be ignored"},
                        {"title": "Arrival (film)"},
                    ]
                }
            }
        )

    monkeypatch.setattr(wiki.requests, "get", fake_get)

    assert wiki.search_wikipedia("Arrival") == ["Arrival", "Arrival (film)"]


def test_search_wikipedia_returns_empty_list_on_request_error(monkeypatch):
    def fake_get(url, params, headers, timeout):
        return FakeResponse(error=requests.RequestException("network failed"))

    monkeypatch.setattr(wiki.requests, "get", fake_get)

    assert wiki.search_wikipedia("Anything") == []


def test_get_page_data_returns_page_for_existing_title(monkeypatch):
    page = {
        "title": "Arrival",
        "extract": "A science fiction film.",
        "pageprops": {"wikibase_item": "Q204057"},
    }

    def fake_get(url, params, headers, timeout):
        assert params["titles"] == "Arrival"
        return FakeResponse({"query": {"pages": {"123": page}}})

    monkeypatch.setattr(wiki.requests, "get", fake_get)

    assert wiki.get_page_data("Arrival") == page


def test_get_page_data_returns_none_for_empty_or_missing_pages(monkeypatch):
    monkeypatch.setattr(
        wiki.requests,
        "get",
        lambda url, params, headers, timeout: FakeResponse(text=""),
    )
    assert wiki.get_page_data("Empty response") is None

    monkeypatch.setattr(
        wiki.requests,
        "get",
        lambda url, params, headers, timeout: FakeResponse(
            {"query": {"pages": {"-1": {"missing": ""}}}}
        ),
    )
    assert wiki.get_page_data("Missing page") is None


def test_is_film_detects_wikidata_film_instance(monkeypatch):
    def fake_get(url, headers, timeout):
        assert "Q204057" in url
        return FakeResponse(
            {
                "entities": {
                    "Q204057": {
                        "claims": {
                            "P31": [
                                {
                                    "mainsnak": {
                                        "datavalue": {"value": {"id": "Q11424"}}
                                    }
                                }
                            ]
                        }
                    }
                }
            }
        )

    monkeypatch.setattr(wiki.requests, "get", fake_get)

    assert wiki.is_film("Q204057") is True


def test_is_film_returns_false_for_missing_id_or_non_film(monkeypatch):
    assert wiki.is_film(None) is False

    monkeypatch.setattr(
        wiki.requests,
        "get",
        lambda url, headers, timeout: FakeResponse(
            {
                "entities": {
                    "QNotFilm": {
                        "claims": {
                            "P31": [
                                {
                                    "mainsnak": {
                                        "datavalue": {"value": {"id": "Q5"}}
                                    }
                                }
                            ]
                        }
                    }
                }
            }
        ),
    )

    assert wiki.is_film("QNotFilm") is False


def test_get_image_url_returns_url_and_handles_missing_imageinfo(monkeypatch):
    monkeypatch.setattr(
        wiki.requests,
        "get",
        lambda url, params, headers, timeout: FakeResponse(
            {"query": {"pages": {"1": {"imageinfo": [{"url": "https://img.test/a.jpg"}]}}}}
        ),
    )
    assert wiki.get_image_url("Poster.jpg") == "https://img.test/a.jpg"

    assert wiki.get_image_url(None) is None

    monkeypatch.setattr(
        wiki.requests,
        "get",
        lambda url, params, headers, timeout: FakeResponse(
            {"query": {"pages": {"1": {}}}}
        ),
    )
    assert wiki.get_image_url("NoImageInfo.jpg") is None


def test_get_movie_info_uses_first_candidate_that_is_a_film(monkeypatch):
    calls = []

    monkeypatch.setattr(wiki, "search_wikipedia", lambda title: ["Novel", "Movie"])

    def fake_get_page_data(title):
        calls.append(title)
        pages = {
            "Dune (film)": {
                "title": "Dune (film)",
                "extract": "A film adaptation.",
                "pageprops": {"wikibase_item": "QFilm", "page_image": "Dune.jpg"},
            },
            "Novel": {
                "title": "Novel",
                "extract": "Not a film.",
                "pageprops": {"wikibase_item": "QBook"},
            },
        }
        return pages.get(title)

    monkeypatch.setattr(wiki, "get_page_data", fake_get_page_data)
    monkeypatch.setattr(wiki, "is_film", lambda wikidata_id: wikidata_id == "QFilm")
    monkeypatch.setattr(wiki, "get_image_url", lambda filename: f"https://img/{filename}")

    result = wiki.get_movie_info("Dune")

    assert calls == ["Dune (film)"]
    assert result == {
        "id": "QFilm",
        "title": "Dune (film)",
        "summary": "A film adaptation.",
        "thumbnail": "https://img/Dune.jpg",
        "wikidata_id": "QFilm",
    }


def test_get_movie_info_returns_none_when_no_candidate_is_a_film(monkeypatch):
    monkeypatch.setattr(wiki, "search_wikipedia", lambda title: ["Book"])
    monkeypatch.setattr(
        wiki,
        "get_page_data",
        lambda title: {"title": title, "pageprops": {"wikibase_item": "QBook"}},
    )
    monkeypatch.setattr(wiki, "is_film", lambda wikidata_id: False)

    assert wiki.get_movie_info("Something") is None


def test_format_movie_info_includes_all_cached_fields_and_fallbacks():
    formatted = wiki.format_movie_info(
        {
            "title": "Arrival",
            "search_term": "arrival",
            "wikidata_id": "Q204057",
            "thumbnail": "https://img.test/arrival.jpg",
            "summary": "A linguist works with the military to communicate with aliens.",
        }
    )

    assert "Movie found" in formatted
    assert "Title:       Arrival" in formatted
    assert "Search term: arrival" in formatted
    assert "Wikidata ID: Q204057" in formatted
    assert "Thumbnail:   https://img.test/arrival.jpg" in formatted
    assert "A linguist works" in formatted

    fallback = wiki.format_movie_info({})

    assert "Unknown title" in fallback
    assert "No summary available." in fallback
    assert "No thumbnail available." in fallback
    assert "No Wikidata ID available." in fallback
