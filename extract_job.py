import json
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    )
}


def clean(text):
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def get_page(url):
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def extract_tables(soup):
    tables = []
    for table in soup.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            row = [clean(cell.get_text(" ", strip=True)) for cell in cells]
            row = [cell for cell in row if cell]
            if row:
                rows.append(row)
        if rows:
            tables.append(rows)
    return tables


def table_text(table):
    return clean(" ".join(" ".join(row) for row in table))


def looks_like_category_table(table):
    text = table_text(table).lower()
    category_patterns = [
        "ur", "general", "obc", "ews", "sc", "st",
        "pwbd", "pwd", "ex-servicemen", "category"
    ]
    matches = sum(word in text for word in category_patterns)
    return matches >= 3 and any(
        word in text for word in ["post", "vacancy", "vacancies", "seat"]
    )


def extract_vacancies(tables):
    total_posts = ""
    post_wise = []
    category_wise = []

    for table in tables:
        text = table_text(table).lower()

        has_vacancy_header = (
            "post name" in text
            or "name of post" in text
            or "post" in text
        ) and any(
            word in text
            for word in [
                "no. of post", "no of post", "total post",
                "vacancy", "vacancies", "number of post"
            ]
        )

        if has_vacancy_header:
            post_wise.append(table)

            for row in table:
                row_text = " ".join(row)
                numbers = re.findall(
                    r"(?<![A-Za-z])\d[\d,]*(?![A-Za-z])",
                    row_text
                )

                for number in numbers:
                    value = number.replace(",", "")
                    if value.isdigit() and int(value) > 0:
                        if not total_posts:
                            total_posts = number
                        break

                if total_posts:
                    break

        if looks_like_category_table(table):
            category_wise.append(table)

    return {
        "total_posts": total_posts,
        "post_wise": post_wise,
        "category_wise": category_wise
    }


def extract_labeled_value(lines, labels):
    for index, line in enumerate(lines):
        lower = line.lower()

        for label in labels:
            if label.lower() in lower:
                remainder = re.sub(
                    rf"^{re.escape(label)}\s*[:\-]?\s*",
                    "",
                    line,
                    flags=re.IGNORECASE
                )

                if remainder and remainder.lower() != label.lower():
                    return clean(remainder)

                if index + 1 < len(lines):
                    next_line = clean(lines[index + 1])
                    if next_line:
                        return next_line

    return ""


def extract_dates(lines):
    full_text = clean(" ".join(lines))

    patterns = {
        "application_start": [
            r"(?:online\s+apply\s+)?start\s+date\s*[:\-]\s*(.{1,60}?)(?=\s+(?:online\s+apply\s+)?last\s+date|\s+closing\s+date|$)",
            r"application\s+start\s+date\s*[:\-]\s*(.{1,60})"
        ],
        "application_last_date": [
            r"(?:online\s+apply\s+)?last\s+date\s*[:\-]\s*(.{1,80}?)(?=\s+(?:last\s+date\s+for\s+fee|fee\s+payment|correction|exam\s+date)|$)",
            r"closing\s+date\s*[:\-]\s*(.{1,80})"
        ],
        "fee_payment_last_date": [
            r"last\s+date\s+for\s+fee\s+payment\s*[:\-]\s*(.{1,80}?)(?=\s+correction|\s+exam\s+date|$)"
        ],
        "correction_date": [
            r"correction\s+(?:date|window)\s*[:\-]\s*(.{1,80}?)(?=\s+exam\s+date|$)"
        ],
        "exam_date": [
            r"exam\s+date\s*[:\-]\s*(.{1,100}?)(?=\s+admit\s+card|\s+result|$)",
            r"date\s+of\s+(?:computer\s+based\s+)?examination\s*[:\-]\s*(.{1,100})"
        ],
        "admit_card": [
            r"admit\s+card\s*(?:date)?\s*[:\-]\s*(.{1,80})"
        ],
        "result": [
            r"result(?:\s+declared\s+date)?\s*[:\-]\s*(.{1,100})"
        ]
    }

    dates = {}
    for key, alternatives in patterns.items():
        value = ""
        for pattern in alternatives:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                value = clean(match.group(1))
                break
        dates[key] = value

    if not dates["application_start"]:
        dates["application_start"] = extract_labeled_value(
            lines,
            ["Online Apply Start Date", "Application Start Date", "Start Date"]
        )

    if not dates["application_last_date"]:
        dates["application_last_date"] = extract_labeled_value(
            lines,
            ["Online Apply Last Date", "Application Last Date", "Last Date", "Closing Date"]
        )

    return dates


def extract_fee(lines):
    value = extract_labeled_value(
        lines,
        ["Application Fee", "Exam Fee", "Application/Exam Fee", "Fee Details"]
    )

    if value:
        return value

    full_text = clean(" ".join(lines))
    matches = re.findall(
        r"(?:fee|fees)[^.]{0,180}?(?:₹|Rs\.?|INR)\s*[\d,]+[^.]*",
        full_text,
        re.IGNORECASE
    )

    return clean(matches[0]) if matches else ""


def extract_age(lines):
    full_text = clean(" ".join(lines))

    minimum = re.search(
        r"(?:minimum|lower)\s+age\s*[:\-]?\s*(\d+)\s*(?:years?)?",
        full_text,
        re.IGNORECASE
    )

    maximum = re.search(
        r"(?:maximum|upper)\s+age\s*[:\-]?\s*(\d+)\s*(?:years?)?",
        full_text,
        re.IGNORECASE
    )

    if minimum or maximum:
        parts = []
        if minimum:
            parts.append("Minimum: " + minimum.group(1) + " years")
        if maximum:
            parts.append("Maximum: " + maximum.group(1) + " years")
        return " | ".join(parts)

    return extract_labeled_value(
        lines,
        ["Age Limit", "Age", "Age Criteria", "Age Limit as on"]
    )


def extract_salary(lines, tables):
    value = extract_labeled_value(
        lines,
        [
            "Salary", "Pay Scale", "Pay Level", "Pay Matrix",
            "Salary/Pay", "Remuneration", "Stipend"
        ]
    )

    if value:
        return value

    for table in tables:
        text = table_text(table)
        if re.search(
            r"(salary|pay\s*scale|pay\s*level|pay\s*matrix|remuneration|stipend)",
            text,
            re.IGNORECASE
        ):
            return text

    return ""


def extract_organization(title, lines):
    value = extract_labeled_value(
        lines,
        ["Organization", "Organisation", "Recruiting Authority", "Department"]
    )

    if value:
        return value

    known = [
        ("staff selection commission", "Staff Selection Commission (SSC)"),
        ("ssc", "Staff Selection Commission (SSC)"),
        ("railway", "Indian Railways"),
        ("rrb", "Railway Recruitment Board (RRB)"),
        ("upsc", "Union Public Service Commission (UPSC)"),
        ("bpsc", "Bihar Public Service Commission (BPSC)"),
        ("isro", "Indian Space Research Organisation (ISRO)"),
        ("drdo", "Defence Research and Development Organisation (DRDO)"),
        ("lic", "Life Insurance Corporation of India (LIC)"),
        ("india post", "India Post"),
        ("post office", "India Post")
    ]

    combined = (title + " " + " ".join(lines[:80])).lower()

    for keyword, name in known:
        if keyword in combined:
            return name

    return "Not specified"


def extract_qualification(lines, tables):
    value = extract_labeled_value(
        lines,
        [
            "Educational Qualification",
            "Education Qualification",
            "Qualification",
            "Eligibility Criteria",
            "Eligibility",
            "Essential Qualification"
        ]
    )

    if value:
        return value

    for table in tables:
        text = table_text(table)
        if "qualification" in text.lower() or "eligibility" in text.lower():
            return text

    return "Not specified"



def extract_event_statuses(lines):
    text = clean(" ".join(lines)).lower()

    statuses = {}

    patterns = {
        "admit_card_status": [
            r"admit\s+card[^.]{0,80}\b(released|out|available|issued|download)"
        ],
        "exam_city_status": [
            r"(exam|examination)\s+city[^.]{0,80}\b(released|out|available|issued|intimation)"
        ],
        "answer_key_status": [
            r"answer\s+key[^.]{0,80}\b(released|out|available|issued)"
        ],
        "result_status": [
            r"\bresult\b[^.]{0,80}\b(declared|released|out|available)"
        ]
    }

    for field, alternatives in patterns.items():
        value = ""
        for pattern in alternatives:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                matched = clean(match.group(0))
                negative_phrases = [
                    "not released",
                    "not available",
                    "not out",
                    "not issued",
                    "yet to be released",
                ]
                if any(phrase in matched for phrase in negative_phrases):
                    continue
                value = matched
                break

        statuses[field] = value or "Not mentioned"

    return statuses

def extract_age_relaxation(lines):
    labels = [
        "Age Relaxation",
        "Age Relaxation Details",
        "Relaxation in Upper Age Limit",
        "Age Relaxation as per Rules",
    ]

    value = extract_labeled_value(lines, labels)
    if value:
        return value

    full_text = clean(" ".join(lines))

    patterns = [
        r"age\s+relaxation\s*[:\-]\s*(.{1,250}?)(?=\s+(?:selection|application|important dates|exam|fee)|$)",
        r"upper\s+age\s+relaxation\s*[:\-]\s*(.{1,250}?)(?=\s+(?:selection|application|important dates|exam|fee)|$)",
    ]

    for pattern in patterns:
        match = re.search(pattern, full_text, re.IGNORECASE)
        if match:
            return clean(match.group(1))

    return "As per government rules"


def extract_selection(lines):
    keywords = [
        "selection process", "mode of selection", "selection procedure",
        "written examination", "computer based test", "cbt",
        "skill test", "typing test", "interview", "physical test",
        "document verification"
    ]

    found = []
    for line in lines:
        lower = line.lower()
        if any(keyword in lower for keyword in keywords):
            if line not in found:
                found.append(line)

    return found


def extract_links(soup, page_url):
    result = {
        "apply_link": "",
        "notification_link": "",
        "official_website": ""
    }

    candidates = []

    for link in soup.find_all("a", href=True):
        text = clean(link.get_text(" ", strip=True))
        href = urljoin(page_url, link["href"])

        if href.startswith(("http://", "https://")):
            candidates.append((text.lower(), href))

    for text, href in candidates:
        combined = text + " " + href.lower()

        if (
            not result["apply_link"]
            and any(word in combined for word in [
                "apply online", "online application", "registration", "apply now"
            ])
            and "sarkariresult.com.cm" not in href.lower()
        ):
            result["apply_link"] = href

        if (
            not result["notification_link"]
            and any(word in combined for word in [
                "official notification", "download notification",
                "notification pdf", "advertisement", "detailed notification"
            ])
        ):
            result["notification_link"] = href

        if (
            not result["official_website"]
            and any(word in text for word in [
                "official website", "official site", "department website"
            ])
        ):
            result["official_website"] = href

    return result


def extract_job(url):
    soup = get_page(url)

    for tag in soup.find_all(["script", "style", "noscript"]):
        tag.decompose()

    h1 = soup.find("h1")
    title = clean(h1.get_text(" ", strip=True)) if h1 else ""

    page_text = soup.get_text("\n", strip=True)
    lines = [
        clean(line)
        for line in page_text.splitlines()
        if clean(line)
    ]

    tables = extract_tables(soup)
    vacancies = extract_vacancies(tables)
    dates = extract_dates(lines)
    fee = extract_fee(lines)
    age = extract_age(lines)
    salary = extract_salary(lines, tables)
    links = extract_links(soup, url)
    event_statuses = extract_event_statuses(lines)

    return {
        "title": title or "Not specified",
        "organization": extract_organization(title, lines),
        "total_vacancies": vacancies["total_posts"] or "Not specified",
        "post_wise_vacancies": vacancies["post_wise"],
        "category_wise_vacancies": vacancies["category_wise"],
        "qualification": extract_qualification(lines, tables),
        "age_limit": age or "Not specified",
        "salary": salary or "Not specified",
        "application_fee": fee or "Not specified",
        "important_dates": dates,
        "selection_process": extract_selection(lines),
        "event_statuses": event_statuses,
        "apply_link": links["apply_link"] or "Not found",
        "notification_link": links["notification_link"] or "Not found",
        "official_website": links["official_website"] or "Not found",
        "source_url": url
    }


if __name__ == "__main__":
    TEST_URL = "https://sarkariresult.com.cm/ssc-chsl-sep-2026/"

    print("Creating clean job data...")
    job = extract_job(TEST_URL)

    with open("test_job_data.json", "w", encoding="utf-8") as file:
        json.dump(job, file, indent=2, ensure_ascii=False)

    print("Clean job data created.")
    print("Saved as: test_job_data.json")
