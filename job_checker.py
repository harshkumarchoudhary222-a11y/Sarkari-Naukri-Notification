import json
import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

SOURCE_URL = "https://sarkariresult.com.cm/latest-jobs/"
SEEN_FILE = "seen_jobs.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    )
}


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
        json.dump(
            sorted(seen_jobs),
            f,
            indent=2,
            ensure_ascii=False
        )


def get_page(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    return BeautifulSoup(response.text, "html.parser")


def get_latest_jobs():
    soup = get_page(SOURCE_URL)

    jobs = []
    seen_urls = set()

    # The Latest Jobs page contains the actual job/article links.
    for link in soup.find_all("a", href=True):

        title = link.get_text(" ", strip=True)
        url = urljoin(SOURCE_URL, link["href"])

        if not title:
            continue

        if "sarkariresult.com.cm" not in url:
            continue

        # Ignore navigation and social links.
        ignored_words = [
            "Home",
            "Latest Job",
            "Admit Card",
            "Result",
            "Admission",
            "Syllabus",
            "Answer Key",
            "Contact Us",
            "Privacy Policy",
            "Disclaimer",
            "Follow Now",
            "Click Here",
        ]

        if title in ignored_words:
            continue

        # Job/article titles normally contain these words.
        job_words = [
            "Online Form",
            "Recruitment",
            "Vacancy",
            "Bharti",
            "Apprentice",
            "Teacher",
            "Constable",
            "Engineer",
            "Officer",
            "Assistant",
            "Technician",
            "Clerk",
            "Post",
        ]

        if not any(word.lower() in title.lower() for word in job_words):
            continue

        if url in seen_urls:
            continue

        seen_urls.add(url)

        jobs.append({
            "title": title,
            "url": url
        })

    return jobs


def extract_job_details(job):
    soup = get_page(job["url"])

    # Get page text
    text = soup.get_text(
        "\n",
        strip=True
    )

    # Clean excessive blank lines
    lines = []

    for line in text.splitlines():
        line = line.strip()

        if line:
            lines.append(line)

    clean_text = "\n".join(lines)

    job["page_text"] = clean_text

    return job


def main():

    print("===================================")
    print("SARKARI NAUKRI JOB CHECKER")
    print("===================================")

    seen_jobs = load_seen_jobs()

    print("\nChecking SarkariResult...")

    jobs = get_latest_jobs()

    print(f"Found {len(jobs)} relevant job links.")

    new_jobs = []

    for job in jobs:

        if job["url"] not in seen_jobs:

            new_jobs.append(job)

            seen_jobs.add(job["url"])

    if not new_jobs:

        print("\nNo new jobs found.")

        save_seen_jobs(seen_jobs)

        print("\nFinished.")
        return

    print(f"\nNEW JOBS FOUND: {len(new_jobs)}")

    for job in new_jobs:

        print("\n===================================")
        print("JOB TITLE:")
        print(job["title"])

        print("\nJOB URL:")
        print(job["url"])

        try:

            detailed_job = extract_job_details(job)

            print("\nJOB PAGE SUCCESSFULLY OPENED")

            print("\nPAGE TEXT PREVIEW:")
            print(detailed_job["page_text"][:3000])

        except Exception as error:

            print("\nERROR READING JOB PAGE:")
            print(error)

    save_seen_jobs(seen_jobs)

    print("\n===================================")
    print("Finished.")
    print("===================================")


if __name__ == "__main__":
    main()
