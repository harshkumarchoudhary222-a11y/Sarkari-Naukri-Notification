import re
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


def get_page(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    return BeautifulSoup(response.text, "html.parser")


def clean(text):
    if not text:
        return ""

    text = re.sub(r"\s+", " ", text)
    return text.strip()


def find_section(soup, heading_text):
    """
    Find a heading containing the requested text
    and collect the content until the next heading.
    """

    heading = None

    for tag in soup.find_all(
        ["h1", "h2", "h3", "h4", "h5", "h6"]
    ):

        text = clean(tag.get_text(" ", strip=True))

        if heading_text.lower() in text.lower():
            heading = tag
            break

    if not heading:
        return ""

    content = []

    for element in heading.find_all_next():

        if element == heading:
            continue

        if element.name in [
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6"
        ]:

            break

        text = clean(element.get_text(" ", strip=True))

        if text and text not in content:
            content.append(text)

    return " ".join(content)


def extract_job(url):

    soup = get_page(url)

    job = {
        "url": url,
        "title": "",
        "post_date": "",
        "organization": "",
        "important_dates": "",
        "application_fee": "",
        "age_limit": "",
        "vacancy": "",
        "eligibility": "",
        "selection_process": "",
        "apply_link": "",
        "notification_link": "",
        "official_website": ""
    }

    # -----------------------------
    # TITLE
    # -----------------------------

    h1 = soup.find("h1")

    if h1:
        job["title"] = clean(
            h1.get_text(" ", strip=True)
        )

    # -----------------------------
    # MAIN PAGE TEXT
    # -----------------------------

    page_text = soup.get_text(
        "\n",
        strip=True
    )

    lines = [
        clean(line)
        for line in page_text.splitlines()
        if clean(line)
    ]

    # -----------------------------
    # POST DATE
    # -----------------------------

    for i, line in enumerate(lines):

        if line.lower().startswith("post date"):

            job["post_date"] = line

            break

    # -----------------------------
    # ORGANIZATION
    # -----------------------------

    organization_patterns = [
        r"released a Notification.*?for the recruitment",
        r"has released.*?for the recruitment"
    ]

    for line in lines:

        if "official website" in line.lower():

            match = re.search(
                r"([A-Za-z .&()'-]+?)\s*\(?(?:SSC|Commission|Department|Board|Corporation)\)?",
                line,
                re.IGNORECASE
            )

            if match:
                job["organization"] = clean(
                    match.group(0)
                )
                break

    # -----------------------------
    # SECTIONS
    # -----------------------------

    job["important_dates"] = find_section(
        soup,
        "Important Dates"
    )

    job["application_fee"] = find_section(
        soup,
        "Application Fee"
    )

    job["age_limit"] = find_section(
        soup,
        "Age Limit"
    )

    job["vacancy"] = find_section(
        soup,
        "Vacancy"
    )

    if not job["vacancy"]:
        job["vacancy"] = find_section(
            soup,
            "Total Post"
        )

    job["eligibility"] = find_section(
        soup,
        "Eligibility"
    )

    if not job["eligibility"]:
        job["eligibility"] = find_section(
            soup,
            "Education Qualification"
        )

    job["selection_process"] = find_section(
        soup,
        "Mode Of Selection"
    )

    # -----------------------------
    # LINKS
    # -----------------------------

    for link in soup.find_all(
        "a",
        href=True
    ):

        text = clean(
            link.get_text(" ", strip=True)
        )

        href = urljoin(
            url,
            link["href"]
        )

        text_lower = text.lower()

        if (
            "apply online" in text_lower
            or "registration" in text_lower
        ):

            if "sarkariresult" not in href.lower():
                job["apply_link"] = href

        if (
            "official notification" in text_lower
            or "download official notification" in text_lower
        ):

            if "sarkariresult" not in href.lower():
                job["notification_link"] = href

        if (
            "official website" in text_lower
            or "official site" in text_lower
        ):

            if "sarkariresult" not in href.lower():
                job["official_website"] = href

    return job


def print_job(job):

    print("\n")
    print("=" * 60)
    print("STRUCTURED JOB DATA")
    print("=" * 60)

    fields = [
        ("Title", "title"),
        ("Post Date", "post_date"),
        ("Organization", "organization"),
        ("Important Dates", "important_dates"),
        ("Application Fee", "application_fee"),
        ("Age Limit", "age_limit"),
        ("Vacancy", "vacancy"),
        ("Eligibility", "eligibility"),
        ("Selection Process", "selection_process"),
        ("Apply Link", "apply_link"),
        ("Notification Link", "notification_link"),
        ("Official Website", "official_website"),
    ]

    for label, key in fields:

        print(f"\n{label}:")
        print(job[key] or "NOT FOUND")

    print("\n")
    print("=" * 60)


if __name__ == "__main__":

    # Test URL
    TEST_URL = (
        "https://sarkariresult.com.cm/"
        "ssc-chsl-sep-2026/"
    )

    print("Extracting job information...")

    job = extract_job(TEST_URL)

    print_job(job)

    print("\nExtraction test completed.")
