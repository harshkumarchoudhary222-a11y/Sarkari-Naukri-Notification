import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

SOURCE_URL = "https://sarkariresult.com.cm/latest-jobs/"

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


def find_first_job():

    soup = get_page(SOURCE_URL)

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

    for link in soup.find_all("a", href=True):

        title = link.get_text(" ", strip=True)
        url = urljoin(SOURCE_URL, link["href"])

        if not title:
            continue

        if "sarkariresult.com.cm" not in url:
            continue

        if any(
            word.lower() in title.lower()
            for word in job_words
        ):
            return title, url

    return None, None


def extract_details(url):

    soup = get_page(url)

    print("\n===================================")
    print("JOB DETAILS TEST")
    print("===================================")

    print("\nURL:")
    print(url)

    # Page title
    if soup.title:
        print("\nPAGE TITLE:")
        print(soup.title.get_text(" ", strip=True))

    # Extract headings
    print("\nIMPORTANT SECTIONS FOUND:")

    headings = soup.find_all(
        ["h1", "h2", "h3", "h4", "strong", "b"]
    )

    found = set()

    keywords = [
        "Important Date",
        "Application Fee",
        "Age Limit",
        "Vacancy",
        "Eligibility",
        "Qualification",
        "Selection",
        "Salary",
        "Pay",
        "Apply",
        "Notification",
        "Exam Date",
    ]

    for heading in headings:

        text = heading.get_text(
            " ",
            strip=True
        )

        if not text:
            continue

        for keyword in keywords:

            if keyword.lower() in text.lower():

                if text not in found:

                    print(" -", text)
                    found.add(text)

    # Full page text preview
    print("\n===================================")
    print("PAGE TEXT PREVIEW")
    print("===================================")

    text = soup.get_text(
        "\n",
        strip=True
    )

    lines = []

    for line in text.splitlines():

        line = line.strip()

        if line:
            lines.append(line)

    clean_text = "\n".join(lines)

    print(clean_text[:5000])

    print("\n===================================")
    print("TEST FINISHED")
    print("===================================")


def main():

    print("Finding an existing job...")

    title, url = find_first_job()

    if not url:

        print("Could not find a job.")
        return

    print("\nTEST JOB:")
    print(title)

    extract_details(url)


if __name__ == "__main__":
    main()
