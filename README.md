# Kodi Movie Scraper

Small Python tool to scrape movie information from Wikipedia and Wikidata, then
cache successful lookups in SQLite.

## Setup

Create and activate a virtual environment, then install the project dependencies:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

For editable project installs with development tools:

```bash
python -m pip install -e ".[dev]"
```

## Usage

Run the interactive movie lookup:

```bash
movie-scraper
```

You can also run the module directly:

```bash
python3.11 -m wiki_page_request.wiki_page_request
```

The script prints the movie title, search term, Wikidata ID, thumbnail URL, and
summary. Cached entries are stored in `wikipedia_cache.db` at the project root.

## Kodi Addon Zip

Build a Kodi-installable addon archive:

```bash
python3.11 build_kodi_addon.py
```

Upload this generated file to Kodi:

```text
build/script.kodimoviescraper.zip
```

## Tests

Run the unit tests:

```bash
python3.11 -m pytest
```

The tests mock HTTP requests, so they do not call Wikipedia or Wikidata.

## Linting And Formatting

Run Ruff checks:

```bash
python3.11 -m ruff check .
```

Format the code:

```bash
python3.11 -m ruff format .
```

## Package Layout

```text
database/
  database.py          SQLite cache class
wiki_page_request/
  wiki_page_request.py Wikipedia/Wikidata requester, MovieInfo model, and CLI
utests/
  test_database.py
  test_wiki_page_request.py
```
