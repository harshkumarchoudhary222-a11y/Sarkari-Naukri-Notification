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


def _first_positive_number(text):
    numbers = re.findall(r"(?<![A-Za-z])\d[\d,]*(?![A-Za-z])", text)
    for number in numbers:
        value = number.replace(",", "")
        if value.isdigit() and int(value) > 0:
            return int(value)
    return None


def extract_vacancies(tables):
    total_posts = ""
    post_wise = []
    category_wise = []

    vacancy_headers = [
        "no. of post", "no of post", "number of post", "total post",
        "no. of posts", "no of posts", "vacancy", "vacancies",
        "total vacancy", "total vacancies"
    ]

    def find_vacancy_header(table):
        for index, row in enumerate(table[:4]):
            for col, cell in enumerate(row):
                cell_lower = cell.lower()
                if any(header in cell_lower for header in vacancy_headers):
                    return index, col
        return None, None

    for table in tables:
        text = table_text(table).lower()

        if looks_like_category_table(table):
            category_wise.append(table)

        header_index, vacancy_col = find_vacancy_header(table)

        # A table is a post-wise vacancy table only when its actual header
        # contains a vacancy/post-count column. This prevents FAQ tables
        # from being mistaken for vacancy tables.
        if vacancy_col is None or header_index is None:
            continue

        post_wise.append(table)

        # Prefer an explicit Total/Grand Total row.
        for row in table:
            row_text = " ".join(row)
            if re.search(r"\b(grand\s+total|total)\b", row_text, re.IGNORECASE):
                number = _first_positive_number(row_text)
                if number is not None:
                    total_posts = str(number)
                    break

        if total_posts:
            break

        # Otherwise sum the actual vacancy column.
        total = 0
        found = False
        for row in table[header_index + 1:]:
            row_text = " ".join(row)
            if re.search(r"\b(grand\s+total|total)\b", row_text, re.IGNORECASE):
                continue
            if vacancy_col < len(row):
                number = _first_positive_number(row[vacancy_col])
                if number is not None:
                    total += number
                    found = True

        if found:
            total_posts = str(total)
            break

    return {
        "total_posts": total_posts,
        "post_wise": post_wise,
        "category_wise": category_wise
    }


def extract_labeled_value(lines, labels):
    heading_only = {
        "education qualification", "educational qualification", "qualification",
        "eligibility", "eligibility criteria", "essential qualification", "post name", "name of post", "post-wise vacancy",
        "vacancy details", "details of post", "details of vacancies",
        "start date", "online apply start date", "application start date",
        "last date", "online apply last date", "application last date",
        "closing date", "exam date", "admit card", "result"
    }

    for index, line in enumerate(lines):
        lower = line.lower().strip()

        for label in labels:
            label_lower = label.lower()
            if label_lower not in lower:
                continue

            remainder = re.sub(
                rf"^.*?{re.escape(label)}\s*[:\-]?\s*",
                "",
                line,
                count=1,
                flags=re.IGNORECASE
            ).strip()

            # Some SarkariResult pages put a title before the label and then
            # place a small table header on the same line.
            remainder = re.sub(
                r"^(?:post\s+name|name\s+of\s+post)\s+"
                r"(?:eligibility|qualification)\s*[:\-]?\s*",
                "",
                remainder,
                flags=re.IGNORECASE
            ).strip()

            if remainder and remainder.lower() != label_lower and remainder.lower() not in heading_only:
                # Do not return table/navigation fragments such as 'for Apply Online'.
                if not re.fullmatch(r"(?:for\s+)?(?:apply|online|fee|payment)\s*(?:online)?", remainder, re.IGNORECASE):
                    return clean(remainder)

            # If the label is a heading, inspect the following lines for the actual value.
            for next_index in range(index + 1, min(index + 4, len(lines))):
                next_line = clean(lines[next_index])
                if not next_line:
                    continue
                next_lower = next_line.lower()
                if next_lower in heading_only:
                    continue
                if any(next_lower.startswith(item.lower()) for item in labels):
                    continue
                if re.fullmatch(r"(?:for\s+)?(?:apply|online|fee|payment)\s*(?:online)?", next_line, re.IGNORECASE):
                    continue
                return next_line

    return ""


def _clean_date_value(value):
    value = clean(value)
    if not value:
        return ""
    bad = {
        "not specified", "not available", "not mentioned", "notify soon",
        "to be notified", "to be announced", "tba", "coming soon",
        "for apply online", "to pay exam fee", "application", "online"
    }
    if value.lower() in bad:
        return "Not Announced" if value.lower() in {"notify soon", "to be notified", "to be announced", "tba", "coming soon"} else ""
    return value


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

    for key in ("application_start", "application_last_date", "fee_payment_last_date", "correction_date", "exam_date", "admit_card", "result"):
        raw_value = dates.get(key, "")
        value = _clean_date_value(raw_value)
        if value:
            dates[key] = value
        elif str(raw_value).strip():
            dates[key] = "Not mentioned"
        else:
            dates[key] = "Not mentioned"

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
        ("cuh", "Central University of Haryana (CUH)"),
        ("lic", "Life Insurance Corporation of India (LIC)"),
        ("india post", "India Post"),
        ("post office", "India Post")
    ]

    title_lower = title.lower()
    combined = (title + " " + " ".join(lines[:80])).lower()

    for keyword, name in known:
        if re.search(r"(?<![a-z])" + re.escape(keyword) + r"(?![a-z])", combined):
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
        bad = {
            "education qualification",
            "educational qualification",
            "qualification",
            "eligibility",
            "eligibility criteria",
            "essential qualification",
        }
        if value.strip().lower() not in bad and not value.strip().lower().endswith("qualification"):
            return value

    for table in tables:
        text = table_text(table)
        if "qualification" in text.lower() or "eligibility" in text.lower():
            if text.strip().lower() not in {
                "education qualification",
                "educational qualification",
                "qualification",
                "eligibility",
                "eligibility criteria",
                "post name",
                "name of post",
                "vacancy details",
            } and not text.strip().lower().endswith("qualification"):
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

    for index, (text, href) in enumerate(candidates):
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

        # SarkariResult often uses a generic "Click Here" anchor under a
        # heading such as "Check Official Notification". Look at nearby
        # anchors in the page order and use a PDF/document URL when it is
        # clearly associated with that section.
        if not result["notification_link"] and text.strip().lower() in {"click here", "click here to download"}:
            nearby = " ".join(
                item[0].lower() for item in candidates[max(0, index - 3):index]
            )
            href_lower = href.lower()
            if (
                "official notification" in nearby
                or "notification" in href_lower
                or href_lower.endswith(".pdf")
                or ".pdf?" in href_lower
            ):
                result["notification_link"] = href

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
    age_relaxation = extract_age_relaxation(lines)
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
        "age_relaxation": age_relaxation,
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
