import os
import requests

from bs4 import BeautifulSoup
from urllib.parse import urljoin


SOURCE_URL = (
    "https://sarkariresult.com.cm/"
    "latest-jobs/"
)


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    )
}


def get_latest_jobs_source():

    response = requests.get(
        SOURCE_URL,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    jobs = []

    seen_urls = set()

    # Words that commonly appear
    # in genuine recruitment titles.
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
        "Selection"
    ]

    for link in soup.find_all(
        "a",
        href=True
    ):

        title = link.get_text(
            " ",
            strip=True
        )

        url = urljoin(
            SOURCE_URL,
            link["href"]
        )

        if not title:
            continue

        if (
            "sarkariresult.com.cm"
            not in url
        ):
            continue

        # Ignore very short/navigation text.
        if len(title) < 15:
            continue

        # Keep likely recruitment articles.
        if not any(
            word.lower()
            in title.lower()
            for word in job_words
        ):
            continue

        if url in seen_urls:
            continue

        seen_urls.add(url)

        jobs.append(
            {
                "title": title,
                "url": url
            }
        )

    return jobs
