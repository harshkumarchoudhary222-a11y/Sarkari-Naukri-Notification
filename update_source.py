import re
from datetime import datetime, timedelta
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from extract_job import extract_important_links, extract_summary, clean


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

    # A single source page can appear in more than one category feed.
    # Prefer the category that matches the actual update title so one event
    # cannot produce duplicate/misclassified Telegram alerts.
    def category_priority(item):
        title = item.get("title", "").lower()
        if re.search(r"\bresult\b|score\s*card|marks|merit\s*list|cut[- ]?off", title):
            return 3  # RESULT
        if re.search(r"answer\s*key", title):
            return 2  # ANSWER_KEY
        if re.search(r"admit\s*card|hall\s*ticket|exam\s*city|intimation", title):
            return 1  # ADMIT_CARD
        return 0

    # De-duplicate by source URL. When the same page is listed under several
    # categories, keep the category whose title best describes the page.
    deduped = {}
    for item in updates:
        key = item.get("url", "").strip()
        if not key:
            continue
        existing = deduped.get(key)
        if existing is None or category_priority(item) > category_priority(existing):
            deduped[key] = item

    updates = list(deduped.values())

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
    item["summary"] = extract_summary(soup, item.get("title", ""))

    # Choose the action that matches the actual update. Exam-city updates
    # should prefer the city/intimation resource; exam-date updates should
    # prefer the date notice. This avoids showing a generic or mismatched
    # action button.
    if item["category"] == "RESULT":
        item["primary_link"] = (
            resources.get("result_link", "")
            or resources.get("score_card_link", "")
        )
        item["primary_label"] = (
            "Check Result" if resources.get("result_link") else "Check Score Card / Marks"
        )
    elif item["category"] == "ADMIT_CARD":
        title_lower = item.get("title", "").lower()

        if re.search(r"interview\s*(?:schedule|letter)|personality\s*test", title_lower):
            item["primary_link"] = (
                resources.get("exam_date_link", "")
                or resources.get("admit_card_link", "")
                or resources.get("exam_city_link", "")
            )
            item["primary_label"] = (
                "📄 Download Interview Schedule"
                if resources.get("exam_date_link")
                else "🔗 Open Interview Update"
            )
            item["update_kind"] = "INTERVIEW"
        elif re.search(r"exam\s*city|city\s*intimation|city\s*slip", title_lower):
            item["primary_link"] = (
                resources.get("exam_city_link", "")
                or resources.get("admit_card_link", "")
                or resources.get("exam_date_link", "")
            )
            if resources.get("exam_city_link"):
                item["primary_label"] = "🏙️ Check Exam City / Intimation"
            elif resources.get("admit_card_link"):
                item["primary_label"] = "🎫 Download Admit Card"
            else:
                item["primary_label"] = "📅 Check Exam Date Notice"
            item["update_kind"] = "EXAM_CITY"
        elif re.search(r"exam\s*date|new\s+exam\s*date|schedule", title_lower):
            item["primary_link"] = (
                resources.get("exam_date_link", "")
                or resources.get("admit_card_link", "")
                or resources.get("exam_city_link", "")
            )
            if resources.get("exam_date_link"):
                item["primary_label"] = "📅 Check Exam Date Notice"
            elif resources.get("admit_card_link"):
                item["primary_label"] = "🎫 Download Admit Card"
            else:
                item["primary_label"] = "🏙️ Check Exam City / Intimation"
            item["update_kind"] = "EXAM_DATE"
        elif re.search(r"application\s*status|application\s*form\s*status", title_lower):
            item["primary_link"] = (
                resources.get("official_website", "")
                or resources.get("exam_date_link", "")
            )
            item["primary_label"] = "🔎 Check Application Status"
            item["update_kind"] = "APPLICATION_STATUS"
        else:
            item["primary_link"] = (
                resources.get("admit_card_link", "")
                or resources.get("exam_city_link", "")
                or resources.get("exam_date_link", "")
            )
            if resources.get("admit_card_link"):
                item["primary_label"] = "🎫 Download Admit Card"
            elif resources.get("exam_city_link"):
                item["primary_label"] = "🏙️ Check Exam City / Intimation"
            else:
                item["primary_label"] = "📅 Check Exam Date Notice"
            item["update_kind"] = "ADMIT_CARD"

    else:
        item["primary_link"] = resources.get("answer_key_link", "")
        item["primary_label"] = "Download Answer Key"

    item["official_website"] = resources.get("official_website", "")
    item["notification_link"] = resources.get("notification_link", "")

    return item
