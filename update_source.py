import re
from datetime import datetime, timedelta
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from extract_job import extract_important_links, clean


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    )
}

CATEGORIES = {
    "RESULT": "https://sarkariresult.com.cm/category/result/",
    "ADMIT_CARD": "https://sarkariresult.com.cm/category/admit-card/",
    "ANSWER_KEY": "https://sarkariresult.com.cm/category/answer-key/",
}

CURRENT_YEAR = datetime.now().year


def _parse_date(text):
    match = re.search(
        r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+\d{1,2},\s+\d{4}\b",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    try:
        return datetime.strptime(match.group(0), "%B %d, %Y")
    except ValueError:
        return None


def _listing_items(url, category):
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    items = []
    seen = set()

    for heading in soup.find_all(["h2", "h3"]):
        anchor = heading.find("a", href=True)
        if not anchor:
            continue

        title = clean(anchor.get_text(" ", strip=True))
        href = urljoin(url, anchor["href"])

        if not title or href in seen:
            continue
        if "sarkariresult.com.cm" not in href:
            continue

        container = heading.parent
        date_text = clean(container.get_text(" ", strip=True)) if container else title
        published = _parse_date(date_text)

        if published is None:
            # Search a small nearby window for the published date.
            sibling_text = ""
            for sibling in heading.find_all_next(limit=4):
                sibling_text += " " + clean(sibling.get_text(" ", strip=True))
            published = _parse_date(sibling_text)

        if published is None:
            continue

        if published.year < CURRENT_YEAR:
            continue

        seen.add(href)
        items.append({
            "title": title,
            "url": href,
            "category": category,
            "published": published.strftime("%Y-%m-%d"),
        })

    return items[:10]


def get_current_updates(max_age_days=2):
    cutoff = datetime.now() - timedelta(days=max_age_days)
    updates = []

    for category, url in CATEGORIES.items():
        try:
            items = _listing_items(url, category)
        except Exception as error:
            print(f"{category} source failed: {error}")
            continue

        for item in items:
            published = datetime.strptime(item["published"], "%Y-%m-%d")
            if published >= cutoff:
                updates.append(item)

    # Newest first, then category.
    updates.sort(key=lambda item: (item["published"], item["category"]), reverse=True)

    return updates


def enrich_update(item):
    response = requests.get(item["url"], headers=HEADERS, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    resources = extract_important_links(soup, item["url"])

    item = dict(item)
    item["resources"] = resources

    # Keep only the resource relevant to the category, but preserve the
    # source page as a safe fallback.
    if item["category"] == "RESULT":
        item["primary_link"] = resources.get("result_link", "")
        item["primary_label"] = "Check Result"
    elif item["category"] == "ADMIT_CARD":
        item["primary_link"] = resources.get("admit_card_link", "")
        item["primary_label"] = "Download Admit Card"
    else:
        item["primary_link"] = resources.get("answer_key_link", "")
        item["primary_label"] = "Download Answer Key"

    return item
