import requests

WIKI_API_URL = "https://en.wikipedia.org/w/api.php"

HEADERS = {
    "User-Agent": "KodiMovieScraper"
}


def search_wikipedia(title):
    params = {
        "action": "query",
        "format": "json",
        "list": "search",
        "srsearch": title,
        "srlimit": 5
    }

    response = requests.get(WIKI_API_URL, params=params, headers=HEADERS, timeout=10)
    data = response.json()

    results = data.get("query", {}).get("search", [])
    return [r["title"] for r in results]


def get_page_data(title):
    params = {
        "action": "query",
        "format": "json",
        "prop": "extracts|pageimages|pageprops",
        "titles": title,
        "exintro": True,
        "explaintext": True,
        "pithumbsize": 500

    }

    response = requests.get(WIKI_API_URL, params=params, headers=HEADERS, timeout=10)

    if not response.text.strip():
        return None

    data = response.json()
    pages = data["query"]["pages"]
    page = next(iter(pages.values()))

    if "missing" in page:
        return None

    return page


def is_film(wikidata_id):
    if not wikidata_id:
        return False

    url = f"https://www.wikidata.org/wiki/Special:EntityData/{wikidata_id}.json"

    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        data = response.json()

        claims = data["entities"][wikidata_id]["claims"]

        # P31 = instance of
        for claim in claims.get("P31", []):
            value = claim["mainsnak"].get("datavalue", {}).get("value", {})
            if value.get("id") == "Q11424":  # Q11424 is the identifier for films
                return True

    except Exception as e:
        print("Wikidata check failed:", e)

    return False


def get_movie_info(title):
    candidates = [f"{title} (film)"] + search_wikipedia(title)

    for candidate in candidates:
        page = get_page_data(candidate)
        if not page:
            continue

        wikidata_id = page.get("pageprops", {}).get("wikibase_item")

        if is_film(wikidata_id):
            #print(page) #all the data from the request
            return {
                "title": page.get("title"),
                "summary": page.get("extract"),
                "thumbnail": get_image_url(page.get("pageprops").get("page_image")),
                "wikidata_id": wikidata_id
            }

    return None


def get_image_url(filename):
    response = requests.get(
        "https://en.wikipedia.org/w/api.php",
        params={
            "action": "query",
            "format": "json",
            "titles": f"File:{filename}",
            "prop": "imageinfo",
            "iiprop": "url"
        },
        headers={"User-Agent": "KodiMovieScraper"}
    )

    data = response.json()
    page = next(iter(data["query"]["pages"].values()))

    return page["imageinfo"][0]["url"]




if __name__ == "__main__":
    movie_title = input("Enter movie title: ")

    info = get_movie_info(movie_title)

    if not info:
        print("No movie found.")
    else:
        print("\nTitle:", info["title"])
        print("\nSummary:\n", info["summary"][:500], "...")
        print("\nThumbnail:", info["thumbnail"])
        print("\nWikidata ID:", info["wikidata_id"])