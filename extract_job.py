import json
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin


# --------------------------------------------------
# BASIC SETTINGS
# --------------------------------------------------

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    )
}


# --------------------------------------------------
# HELPER FUNCTIONS
# --------------------------------------------------

def clean(text):
    """Remove unnecessary spaces."""

    if not text:
        return ""

    return re.sub(r"\s+", " ", text).strip()


def get_page(url):
    """Download a webpage."""

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    return BeautifulSoup(
        response.text,
        "html.parser"
    )


def extract_tables(soup):
    """Find tables on the webpage."""

    tables = []

    for table in soup.find_all("table"):

        rows = []

        for tr in table.find_all("tr"):

            cells = tr.find_all(
                ["th", "td"]
            )

            row = []

            for cell in cells:

                text = clean(
                    cell.get_text(
                        " ",
                        strip=True
                    )
                )

                if text:
                    row.append(text)

            if row:
                rows.append(row)

        if rows:
            tables.append(rows)

    return tables


# --------------------------------------------------
# VACANCY INFORMATION
# --------------------------------------------------

def extract_vacancies(tables):

    total_posts = ""
    post_wise = []
    category_wise = []

    for table in tables:

        table_text = " ".join(
            " ".join(row)
            for row in table
        ).lower()

        # Look for the main vacancy table
        if (
            "post name" in table_text
            and (
                "no. of post" in table_text
                or "total post" in table_text
            )
        ):

            post_wise.append(table)

            # Find total number
            for row in table:

                for cell in row:

                    numbers = re.findall(
                        r"\b\d[\d,]*\b",
                        cell
                    )

                    for number in numbers:

                        value = number.replace(
                            ",",
                            ""
                        )

                        if value.isdigit():

                            if int(value) > 0:

                                total_posts = number

                                break

                    if total_posts:
                        break

                if total_posts:
                    break

        # Look for category-wise tables
        category_words = [
            "ur",
            "obc",
            "ews",
            "sc",
            "st"
        ]

        matches = sum(
            1
            for word in category_words
            if word in table_text
        )

        if (
            matches >= 3
            and "post" in table_text
        ):

            category_wise.append(table)

    return {
        "total_posts": total_posts,
        "post_wise": post_wise,
        "category_wise": category_wise
    }


# --------------------------------------------------
# IMPORTANT DATES
# --------------------------------------------------

def extract_dates(lines):

    dates = {}

    full_text = clean(
        " ".join(lines)
    )

    patterns = {

        "application_start": (
            r"Online Apply Start Date\s*:\s*"
            r"(.{1,50}?)"
            r"(?=\s+Online Apply Last Date)"
        ),

        "application_last_date": (
            r"Online Apply Last Date\s*:\s*"
            r"(.{1,50}?)"
            r"(?=\s+Last Date For Fee Payment)"
        ),

        "fee_payment_last_date": (
            r"Last Date For Fee Payment\s*:\s*"
            r"(.{1,50}?)"
            r"(?=\s+Correction Date)"
        ),

        "correction_date": (
            r"Correction Date\s*:\s*"
            r"(.{1,50}?)"
            r"(?=\s+Exam Date)"
        ),

        "exam_date": (
            r"Exam Date\s*:\s*"
            r"(.{1,80}?)"
            r"(?=\s+Admit Card)"
        ),

        "admit_card": (
            r"Admit Card\s*:\s*"
            r"(.{1,50}?)"
            r"(?=\s+Result Declared Date)"
        ),

        "result": (
            r"Result Declared Date\s*:\s*"
            r"(.{1,80}?)"
            r"(?=\s+Candidates are advised)"
        )
    }

    for key, pattern in patterns.items():

        match = re.search(
            pattern,
            full_text,
            re.IGNORECASE
        )

        if match:

            dates[key] = clean(
                match.group(1)
            )

        else:

            dates[key] = ""

    return dates


# --------------------------------------------------
# APPLICATION FEE
# --------------------------------------------------

def extract_fee(lines):

    full_text = clean(
        " ".join(lines)
    )

    pattern = (
        r"Application Fee\s*"
        r"(.*?)"
        r"SSC 10\+2 CHSL Notification"
    )

    match = re.search(
        pattern,
        full_text,
        re.IGNORECASE
    )

    if match:

        return clean(
            match.group(1)
        )

    return ""


# --------------------------------------------------
# AGE
# --------------------------------------------------

def extract_age(lines):

    full_text = clean(
        " ".join(lines)
    )

    minimum = re.search(
        r"Minimum Age\s*:\s*(\d+)",
        full_text,
        re.IGNORECASE
    )

    maximum = re.search(
        r"Maximum Age\s*:\s*(\d+)",
        full_text,
        re.IGNORECASE
    )

    result = ""

    if minimum:

        result += (
            "Minimum: "
            + minimum.group(1)
            + " years"
        )

    if maximum:

        if result:
            result += " | "

        result += (
            "Maximum: "
            + maximum.group(1)
            + " years"
        )

    return result


# --------------------------------------------------
# LINKS
# --------------------------------------------------

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
            link.get_text(
                " ",
                strip=True
            )
        )

        href = urljoin(
            page_url,
            link["href"]
        )

        text_lower = text.lower()

        # Apply link
        if (
            "apply online" in text_lower
            or "registration" in text_lower
        ):

            if (
                "sarkariresult.com.cm"
                not in href.lower()
            ):

                if not result["apply_link"]:

                    result["apply_link"] = href

        # Notification link
        if (
            "official notification"
            in text_lower
            or "download official notification"
            in text_lower
        ):

            if not result["notification_link"]:

                result["notification_link"] = href

        # Official website
        if (
            "official website"
            in text_lower
            or "official site"
            in text_lower
        ):

            if not result["official_website"]:

                result["official_website"] = href

    return result


# --------------------------------------------------
# MAIN EXTRACTION
# --------------------------------------------------

def extract_job(url):

    soup = get_page(url)

    # Remove unnecessary elements
    for tag in soup.find_all(
        ["script", "style", "noscript"]
    ):

        tag.decompose()

    # Page title
    h1 = soup.find("h1")

    title = ""

    if h1:

        title = clean(
            h1.get_text(
                " ",
                strip=True
            )
        )

    # All visible text
    page_text = soup.get_text(
        "\n",
        strip=True
    )

    lines = [
        clean(line)
        for line in page_text.splitlines()
        if clean(line)
    ]

    tables = extract_tables(
        soup
    )

    vacancies = extract_vacancies(
        tables
    )

    dates = extract_dates(
        lines
    )

    fee = extract_fee(
        lines
    )

    age = extract_age(
        lines
    )

    links = extract_links(
        soup,
        url
    )

    # Organization
    organization = "Not specified"

    if "ssc" in title.lower():

        organization = (
            "Staff Selection Commission (SSC)"
        )

    # Qualification
    qualification = "Not specified"

    for table in tables:

        table_text = " ".join(
            " ".join(row)
            for row in table
        )

        if (
            "eligibility criteria"
            in table_text.lower()
        ):

            qualification = table_text

            break

    # Selection
    selection = []

    for line in lines:

        if (
            "Tier-I Exam"
            in line
            or "Tier-II Exam"
            in line
        ):

            if line not in selection:

                selection.append(line)

    job = {

        "title": title,

        "organization": organization,

        "total_vacancies":
            vacancies["total_posts"]
            or "Not specified",

        "post_wise_vacancies":
            vacancies["post_wise"],

        "category_wise_vacancies":
            vacancies["category_wise"],

        "qualification":
            qualification,

        "age_limit":
            age
            or "Not specified",

        "salary":
            "Not specified",

        "application_fee":
            fee
            or "Not specified",

        "important_dates":
            dates,

        "selection_process":
            selection,

        "apply_link":
            links["apply_link"]
            or "Not found",

        "notification_link":
            links["notification_link"]
            or "Not found",

        "official_website":
            links["official_website"]
            or "Not found",

        "source_url":
            url
    }

    return job


# --------------------------------------------------
# TEST
# --------------------------------------------------

if __name__ == "__main__":

    TEST_URL = (
        "https://sarkariresult.com.cm/"
        "ssc-chsl-sep-2026/"
    )

    print(
        "Creating clean job data..."
    )

    job = extract_job(
        TEST_URL
    )

    # Save clean JSON
    with open(
        "test_job_data.json",
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            job,
            file,
            indent=2,
            ensure_ascii=False
        )

    print(
        "Clean job data created."
    )

    print(
        "Saved as: test_job_data.json"
    )
