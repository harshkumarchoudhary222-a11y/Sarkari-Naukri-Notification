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
    """Clean repeated whitespace."""

    if not text:
        return ""

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def unique(items):
    """Remove duplicate strings while preserving order."""

    result = []
    seen = set()

    for item in items:

        item = clean(item)

        if not item:
            continue

        if item not in seen:

            seen.add(item)
            result.append(item)

    return result


def get_page(url):

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


# ---------------------------------------------------------
# TABLE EXTRACTION
# ---------------------------------------------------------

def extract_tables(soup):

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


# ---------------------------------------------------------
# FIND TABLE BY KEYWORDS
# ---------------------------------------------------------

def find_tables(tables, keywords):

    results = []

    for table in tables:

        table_text = " ".join(
            " ".join(row)
            for row in table
        ).lower()

        matches = 0

        for keyword in keywords:

            if keyword.lower() in table_text:
                matches += 1

        if matches >= 1:

            results.append(table)

    return results


# ---------------------------------------------------------
# VACANCY TABLES
# ---------------------------------------------------------

def extract_vacancy_data(tables):

    post_tables = []

    category_tables = []

    total_posts = ""

    for table in tables:

        text = " ".join(
            " ".join(row)
            for row in table
        ).lower()

        # Total post table
        if (
            "post name" in text
            and (
                "no. of post" in text
                or "no of post" in text
                or "total post" in text
            )
        ):

            post_tables.append(table)

        # Category vacancy table
        category_words = [
            "ur",
            "obc",
            "ews",
            "sc",
            "st"
        ]

        category_matches = sum(
            1
            for word in category_words
            if word in text
        )

        if (
            category_matches >= 3
            and "post" in text
        ):

            category_tables.append(table)

    # Find total number of posts
    for table in post_tables:

        for row in table:

            row_text = " ".join(row)

            numbers = re.findall(
                r"\b\d[\d,]*\b",
                row_text
            )

            for number in numbers:

                value = number.replace(
                    ",",
                    ""
                )

                try:

                    number_value = int(value)

                    if number_value >= 1:

                        total_posts = number

                        break

                except ValueError:

                    pass

            if total_posts:
                break

        if total_posts:
            break

    return {
        "total_posts": total_posts,
        "post_wise": post_tables,
        "category_wise": category_tables
    }


# ---------------------------------------------------------
# TEXT SEARCH
# ---------------------------------------------------------

def find_line(lines, keywords):

    for line in lines:

        lower = line.lower()

        for keyword in keywords:

            if keyword.lower() in lower:

                return line

    return ""


# ---------------------------------------------------------
# IMPORTANT DATES
# ---------------------------------------------------------

def extract_dates(lines):

    dates = {}

    patterns = {
        "apply_start": [
            "online apply start date",
            "application start date",
            "start date"
        ],

        "apply_last_date": [
            "online apply last date",
            "last date for online application",
            "last date"
        ],

        "fee_payment_last_date": [
            "last date for fee payment",
            "fee payment last date"
        ],

        "correction_date": [
            "correction date",
            "correction window"
        ],

        "exam_date": [
            "exam date",
            "examination date"
        ],

        "admit_card": [
            "admit card"
        ],

        "result": [
            "result declared date",
            "result date"
        ]
    }

    # Convert all page text into one clean string.
    full_text = " ".join(lines)

    full_text = clean(full_text)

    for field, keywords in patterns.items():

        value = ""

        for keyword in keywords:

            pattern = (
                re.escape(keyword)
                + r"\s*:\s*"
                + r"(.{1,100}?)"
                + r"(?=\s+[A-Z][A-Za-z ]{2,40}\s*:|$)"
            )

            match = re.search(
                pattern,
                full_text,
                re.IGNORECASE
            )

            if match:

                value = clean(
                    match.group(1)
                )

                break

        dates[field] = value

    return dates


# ---------------------------------------------------------
# APPLICATION FEE
# ---------------------------------------------------------

def extract_fee(lines):

    full_text = " ".join(lines)

    full_text = clean(full_text)

    match = re.search(
        r"Application Fee\s*(.*?)(?=\s+SSC\s+10\+2|\s+Age Limits|\s+Total Post|$)",
        full_text,
        re.IGNORECASE
    )

    if match:

        return clean(
            match.group(1)
        )

    return ""


# ---------------------------------------------------------
# AGE
# ---------------------------------------------------------

def extract_age(lines):

    full_text = " ".join(lines)

    minimum = re.search(
        r"Minimum Age\s*:\s*([0-9]+)",
        full_text,
        re.IGNORECASE
    )

    maximum = re.search(
        r"Maximum Age\s*:\s*([0-9]+)",
        full_text,
        re.IGNORECASE
    )

    result = []

    if minimum:

        result.append(
            "Minimum Age: "
            + minimum.group(1)
            + " Years"
        )

    if maximum:

        result.append(
            "Maximum Age: "
            + maximum.group(1)
            + " Years"
        )

    return " | ".join(result)


# ---------------------------------------------------------
# LINKS
# ---------------------------------------------------------

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

        lower_text = text.lower()

        # Direct external link
        if (
            "apply" in lower_text
            or "registration" in lower_text
        ):

            if (
                "sarkariresult" not in
                href.lower()
            ):

                if not result["apply_link"]:

                    result["apply_link"] = href

        if (
            "notification" in lower_text
            or "advertisement" in lower_text
        ):

            if (
                "sarkariresult" not in
                href.lower()
            ):

                if not result["notification_link"]:

                    result["notification_link"] = href

        if (
            "official website" in lower_text
            or "official site" in lower_text
        ):

            if (
                "sarkariresult" not in
                href.lower()
            ):

                if not result["official_website"]:

                    result["official_website"] = href

    return result


# ---------------------------------------------------------
# MAIN EXTRACTION
# ---------------------------------------------------------

def extract_job(url):

    soup = get_page(url)

    # Remove unnecessary page elements.
    for tag in soup.find_all(
        [
            "script",
            "style",
            "noscript"
        ]
    ):

        tag.decompose()

    # Title
    h1 = soup.find("h1")

    title = ""

    if h1:

        title = clean(
            h1.get_text(
                " ",
                strip=True
            )
        )

    # Page lines
    page_text = soup.get_text(
        "\n",
        strip=True
    )

    lines = unique(
        page_text.splitlines()
    )

    # Tables
    tables = extract_tables(
        soup
    )

    vacancy = extract_vacancy_data(
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

    # Eligibility
    eligibility = ""

    for table in tables:

        table_text = " ".join(
            " ".join(row)
            for row in table
        )

        if (
            "eligibility criteria"
            in table_text.lower()
        ):

            eligibility = table_text

            break

    # Selection
    selection = find_line(
        lines,
        [
            "Mode Of Selection",
            "Selection Process",
            "Selection Procedure"
        ]
    )

    # Salary
    salary = find_line(
        lines,
        [
            "Pay Level",
            "Pay Scale",
            "Salary"
        ]
    )

    job = {

        "title": title,

        "organization": "Not specified",

        "post_date": find_line(
            lines,
            ["Post Date"]
        ),

        "total_posts":
            vacancy["total_posts"]
            or "Not specified",

        "post_wise_vacancies":
            vacancy["post_wise"],

        "category_wise_vacancies":
            vacancy["category_wise"],

        "qualification":
            eligibility
            or "Not specified",

        "age_limit":
            age
            or "Not specified",

        "salary":
            salary
            or "Not specified",

        "application_fee":
            fee
            or "Not specified",

        "important_dates":
            dates,

        "selection_process":
            selection
            or "Not specified",

        "apply_link":
            links["apply_link"]
            or "Not found",

        "notification_link":
            links["notification_link"]
            or "Not found",

        "official_website":
            links["official_website"]
            or "https://ssc.gov.in/",

        "source_url":
            url
    }

    # SSC-specific organization detection
    if "ssc" in title.lower():

        job["organization"] = (
            "Staff Selection Commission (SSC)"
        )

    return job


# ---------------------------------------------------------
# PRINT
# ---------------------------------------------------------

def print_table(table):

    for row in table:

        print(
            " | ".join(row)
        )


def print_job(job):

    print("\n")
    print("=" * 70)
    print("CLEAN STRUCTURED JOB DATA")
    print("=" * 70)

    print("\nTITLE:")
    print(job["title"])

    print("\nORGANIZATION:")
    print(job["organization"])

    print("\nTOTAL POSTS:")
    print(job["total_posts"])

    print("\nPOST-WISE VACANCIES:")

    if job["post_wise_vacancies"]:

        for table in job[
            "post_wise_vacancies"
        ]:

            print_table(table)

    else:

        print("Not specified")

    print("\nCATEGORY-WISE VACANCIES:")

    if job["category_wise_vacancies"]:

        for table in job[
            "category_wise_vacancies"
        ]:

            print_table(table)

    else:

        print("Not specified")

    print("\nQUALIFICATION:")
    print(job["qualification"])

    print("\nAGE LIMIT:")
    print(job["age_limit"])

    print("\nSALARY:")
    print(job["salary"])

    print("\nAPPLICATION FEE:")
    print(job["application_fee"])

    print("\nIMPORTANT DATES:")

    for key, value in job[
        "important_dates"
    ].items():

        if value:

            print(
                key + ": " + value
            )

    print("\nSELECTION PROCESS:")
    print(job["selection_process"])

    print("\nAPPLY LINK:")
    print(job["apply_link"])

    print("\nNOTIFICATION:")
    print(job["notification_link"])

    print("\nOFFICIAL WEBSITE:")
    print(job["official_website"])

    print("\nSOURCE:")
    print(job["source_url"])

    print("\n")
    print("=" * 70)


# ---------------------------------------------------------
# TEST
# ---------------------------------------------------------

if __name__ == "__main__":

    TEST_URL = (
        "https://sarkariresult.com.cm/"
        "ssc-chsl-sep-2026/"
    )

    print(
        "Extracting job information..."
    )

    job = extract_job(
        TEST_URL
    )

    print_job(
        job
    )

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
        "\nStructured data saved."
    )

    print(
        "Extraction test completed."
    )
