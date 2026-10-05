import json
import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

SOURCE_URL = "https://sarkariresult.com.cm/latest-jobs/"
SEEN_FILE = "seen_jobs.json"


def load_seen_jobs():
    if not os.path.exists(SEEN_FILE):
        return set()

    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_seen_jobs(seen_jobs):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(seen_jobs), f, indent=2, ensure_ascii=False)


def get_latest_jobs():
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/120 Safari/537.36"
        )
    }

    response = requests.get(
        SOURCE_URL,
        headers=headers,
        timeout=30
    )

    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    jobs = []

    for link in soup.find_all("a", href=True):
        title = link.get_text(" ", strip=True)
        href = urljoin(SOURCE_URL, link["href"])

        if not title:
            continue

        # Ignore navigation links and very short text.
        if len(title) < 15:
            continue

        # Only keep links that look like job/article pages.
        if "sarkariresult.com.cm" not in href:
            continue

        jobs.append({
            "title": title,
            "url": href
        })

    # Remove duplicates while preserving order.
    unique_jobs = []
    seen_urls = set()

    for job in jobs:
        if job["url"] not in seen_urls:
            seen_urls.add(job["url"])
            unique_jobs.append(job)

    return unique_jobs


def main():
    print("Checking SarkariResult...")
    
    seen_jobs = load_seen_jobs()
    jobs = get_latest_jobs()

    print(f"Found {len(jobs)} article links.")

    new_jobs = []

    for job in jobs:
        if job["url"] not in seen_jobs:
            new_jobs.append(job)
            seen_jobs.add(job["url"])

    if new_jobs:
        print(f"\nNEW JOBS FOUND: {len(new_jobs)}")

        for job in new_jobs:
            print("\n------------------------------")
            print("TITLE:", job["title"])
            print("URL:", job["url"])

    else:
        print("No new jobs found.")

    save_seen_jobs(seen_jobs)

    print("\nFinished.")


if __name__ == "__main__":
    main()
