import re
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    )
}


def clean(text):
    if not text:
        return ""

    text = re.sub(r"\s+", " ", text)
    return text.strip()


def get_page(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    return BeautifulSoup(response.text, "html.parser")


def get_section_text(soup, keywords):

    for heading in soup.find_all(
        ["h1", "h2", "h3", "h4", "h5", "h6"]
    ):

        heading_text = clean(
            heading.get_text(" ", strip=True)
        )

        if not any(
            keyword.lower() in heading_text.lower()
            for keyword in keywords
        ):
            continue

        collected = []

        # Read following elements until the next heading.
        for element in heading.find_all_next():

            if element == heading:
                continue

            if element.name in [
                "h1", "h2", "h3",
                "h4", "h5", "h6"
            ]:
                break

            # Don't repeatedly collect nested elements.
            if element.name not in [
                "p", "li", "tr", "div"
            ]:
                continue

            text = clean(
                element.get_text(" ", strip=True)
            )

            if text and text not in collected:
                collected.append(text)

        return " ".join(collected)

    return ""


def extract_tables(soup):

    tables = []

    for table in soup.find_all("table"):

        rows = []

        for tr in table.find_all("tr"):

            cells = tr.find_all(
                ["th", "td"]
            )

            row = [
                clean(cell.get_text(" ", strip=True))
                for cell in cells
            ]

            row = [
                cell for cell in row
                if cell
            ]

            if row:
                rows.append(row)

        if rows:
            tables.append(rows)

    return tables


def classify_vacancy_tables(tables):

    vacancy_tables = []

    vacancy_keywords = [
        "vacancy",
        "vacancies",
        "no. of post",
        "number of post",
        "total post",
        "ur",
        "obc",
        "ews",
        "sc",
        "st",
        "pwbd",
        "post name"
    ]

    for table in tables:

        table_text = " ".join(
            " ".join(row)
            for row in table
        ).lower()

        matches = sum(
            1
            for keyword in vacancy_keywords
            if keyword in table_text
        )

        # Only keep tables that look like vacancy tables.
        if matches >= 2:

            vacancy_tables.append(table)

    return vacancy_tables


def extract_links(soup, page_url):

    result = {
        "apply_link": "",
        "notification_link": "",
        "official_website": ""
    }

    for link in soup.find_all(
        "a",
        href=True
    ):

        text = clean(
            link.get_text(" ", strip=True)
        )

        href = urljoin(
            page_url,
            link["href"]
        )

        lower = text.lower()

        if (
            "apply online" in lower
            or "registration" in lower
        ):

            if "sarkariresult" not in href.lower():
                result["apply_link"] = href

        if (
            "official notification" in lower
            or "download official notification" in lower
        ):

            if "sarkariresult" not in href.lower():
                result["notification_link"] = href

        if (
            "official website" in lower
            or "official site" in lower
        ):

            if "sarkariresult" not in href.lower():
                result["official_website"] = href

    return result


def extract_basic_info(soup):

    job = {}

    # Title
    h1 = soup.find("h1")

    if h1:
        job["title"] = clean(
            h1.get_text(" ", strip=True)
        )
    else:
        job["title"] = ""

    # Full text
    page_text = soup.get_text(
        "\n",
        strip=True
    )

    lines = [
        clean(line)
        for line in page_text.splitlines()
        if clean(line)
    ]

    # Post date
    job["post_date"] = ""

    for line in lines:

        if line.lower().startswith("post date"):

            job["post_date"] = line
            break

    # Important sections
    job["important_dates"] = get_section_text(
        soup,
        ["Important Dates"]
    )

    job["application_fee"] = get_section_text(
        soup,
        ["Application Fee"]
    )

    job["age_limit"] = get_section_text(
        soup,
        ["Age Limit"]
    )

    job["eligibility"] = get_section_text(
        soup,
        [
            "Eligibility",
            "Education Qualification",
            "Educational Qualification"
        ]
    )

    job["selection_process"] = get_section_text(
        soup,
        [
            "Mode Of Selection",
            "Selection Process",
            "Selection Procedure"
        ]
    )

    job["salary"] = get_section_text(
        soup,
        [
            "Salary",
            "Pay Scale",
            "Pay Level"
        ]
    )

    return job


def extract_job(url):

    soup = get_page(url)

    job = extract_basic_info(soup)

    tables = extract_tables(soup)

    vacancy_tables = classify_vacancy_tables(
        tables
    )

    job["vacancy_tables"] = vacancy_tables

    links = extract_links(
        soup,
        url
    )

    job.update(links)

    job["source_url"] = url

    return job


def print_vacancy_tables(tables):

    if not tables:

        print("No category/post vacancy table found.")

        return

    print("\nVACANCY TABLES FOUND")
    print("=" * 60)

    for number, table in enumerate(
        tables,
        start=1
    ):

        print(f"\nTable {number}:")

        for row in table:

            print(" | ".join(row))


def print_job(job):

    print("\n")
    print("=" * 60)
    print("STRUCTURED JOB DATA")
    print("=" * 60)

    fields = [
        ("Title", "title"),
        ("Post Date", "post_date"),
        ("Important Dates", "important_dates"),
        ("Application Fee", "application_fee"),
        ("Age Limit", "age_limit"),
        ("Salary / Pay", "salary"),
        ("Eligibility", "eligibility"),
        ("Selection Process", "selection_process"),
        ("Apply Link", "apply_link"),
        ("Notification Link", "notification_link"),
        ("Official Website", "official_website"),
        ("Source URL", "source_url"),
    ]

    for label, key in fields:

        print(f"\n{label}:")

        value = job.get(key, "")

        if value:
            print(value)
        else:
            print("NOT FOUND")

    print_vacancy_tables(
        job.get("vacancy_tables", [])
    )

    print("\n")
    print("=" * 60)


if __name__ == "__main__":

    # Current test recruitment page.
    TEST_URL = (
        "https://sarkariresult.com.cm/"
        "ssc-chsl-sep-2026/"
    )

    print("Extracting job information...")

    job = extract_job(TEST_URL)

    print_job(job)

    # Save structured data for later processing.
    with open(
        "test_job_data.json",
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            job,
            f,
            indent=2,
            ensure_ascii=False
        )

    print("\nStructured data saved to test_job_data.json")
    print("Extraction test completed.")
