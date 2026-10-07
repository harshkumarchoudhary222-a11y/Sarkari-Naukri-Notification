import json
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse


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

    # Keep action text such as "Apply Online" out of date fields.
    # Source pages sometimes place it immediately after the start date.
    if dates.get("application_start"):
        dates["application_start"] = re.sub(
            r"\s+(?:apply\s+online|online\s+apply)\s*$",
            "",
            dates["application_start"],
            flags=re.IGNORECASE,
        ).strip()

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
    """Read status only from explicitly labelled lines, not whole-page text."""
    statuses = {
        "admit_card_status": "Not mentioned",
        "exam_city_status": "Not mentioned",
        "answer_key_status": "Not mentioned",
        "result_status": "Not mentioned",
    }

    rules = {
        "admit_card_status": re.compile(
            r"^(?:admit\s*card|download\s+admit\s*card|hall\s*ticket)\s*(?:status)?\s*[:\-]\s*(.+)$",
            re.I,
        ),
        "exam_city_status": re.compile(
            r"^(?:exam(?:ination)?\s+city|city\s+intimation)\s*(?:status)?\s*[:\-]\s*(.+)$",
            re.I,
        ),
        "answer_key_status": re.compile(
            r"^(?:answer\s*key|final\s+answer\s*key)\s*(?:status)?\s*[:\-]\s*(.+)$",
            re.I,
        ),
        "result_status": re.compile(
            r"^(?:result|final\s+result)\s*(?:status)?\s*[:\-]\s*(.+)$",
            re.I,
        ),
    }

    labels = {
        "admit_card_status": "Admit Card",
        "exam_city_status": "Exam City",
        "answer_key_status": "Answer Key",
        "result_status": "Result",
    }

    for raw_line in lines:
        line = clean(raw_line)
        if not line:
            continue

        for field, pattern in rules.items():
            match = pattern.match(line)
            if not match:
                continue

            value = clean(match.group(1))
            lower = value.lower()
            if not value or len(value) > 120:
                continue
            if any(phrase in lower for phrase in [
                "not released", "not available", "not out",
                "not issued", "yet to be released",
                "will be updated here",
            ]):
                continue

            statuses[field] = f"{labels[field]}: {value}"

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
        lower = value.strip().lower()
        invalid_fragments = {
            "for the",
            "as per",
            "extra as per",
            "provides age relaxation for the",
        }
        if (
            lower not in invalid_fragments
            and not lower.startswith(("for the ", "as per ", "extra as per "))
            and len(lower.split()) >= 4
        ):
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
    """Extract actual selection stages, never section headings."""
    stage_patterns = [
        r"written\s+(?:examination|exam|test)",
        r"computer\s+based\s+test(?:\s*\([^)]*\))?",
        r"\bcbt(?:[- ]?\d+)?\b",
        r"skill\s+test", r"typing\s+test", r"steno(?:graphy)?\s+test",
        r"physical\s+(?:test|efficiency|standard|measurement)",
        r"\bpet\b", r"\bpmt\b",
        r"interview(?:\s*\([^)]*\))?",
        r"document\s+verification", r"medical\s+(?:test|examination)",
        r"aptitude\s+test", r"descriptive\s+test",
        r"merit\s+list", r"final\s+merit\s+list",
        r"shortlisting[^,.;]*",
    ]

    found = []
    for raw_line in lines:
        line = clean(raw_line)
        if not line:
            continue

        # Remove a page heading such as "Recruitment Name : Mode Of Selection".
        line = re.sub(
            r"^.*?:\s*(?:mode\s+of\s+selection|selection\s+process|selection\s+procedure)\s*$",
            "",
            line,
            flags=re.I,
        ).strip()

        # Also remove a heading prefix when actual stages follow it.
        line = re.sub(
            r"^.*?:\s*(?:mode\s+of\s+selection|selection\s+process|selection\s+procedure)\s*[:\-]?",
            "",
            line,
            flags=re.I,
        ).strip()

        if not line:
            continue

        pieces = re.split(r"\s*\|\s*|\s*→\s*|\s+[-–—]\s+", line)
        for piece in pieces:
            piece = clean(piece.strip(" -–—."))
            if not piece:
                continue
            if not any(re.search(pattern, piece, re.I) for pattern in stage_patterns):
                continue
            if re.fullmatch(
                r"(?:mode\s+of\s+selection|selection\s+process|selection\s+procedure)",
                piece,
                re.I,
            ):
                continue
            if piece not in found:
                found.append(piece)

    return found


def extract_important_links(soup, page_url):
    """Extract real hrefs from the site's 'SOME USEFUL IMPORTANT LINKS' area.

    The visible 'Click Here' text is often just a label. We only accept an
    actual href from the same table/row as the labelled resource.
    """
    result = {
        "apply_link": "",
        "notification_link": "",
        "official_website": "",
        "result_link": "",
        "admit_card_link": "",
        "answer_key_link": "",
    }

    def usable(href):
        if not href:
            return False
        href = urljoin(page_url, href)
        parts = urlparse(href)
        if parts.scheme not in {"http", "https"}:
            return False
        lower = href.lower()
        page_parts = urlparse(page_url)
        if (
            parts.netloc.lower() == page_parts.netloc.lower()
            and (parts.path.rstrip("/") or "/") == (page_parts.path.rstrip("/") or "/")
        ):
            return False
        if any(bad in lower for bad in [
            "play.google.com", "apps.apple.com", "whatsapp.com", "wa.me",
            "t.me", "telegram.me", "facebook.com", "instagram.com",
            "youtube.com", "twitter.com", "x.com", "javascript:", "mailto:"
        ]):
            return False
        return href

    marker = None
    for element in soup.find_all(["h2", "h3", "h4", "h5", "strong", "b", "p", "td"]):
        text = clean(element.get_text(" ", strip=True)).lower()
        if "some useful important links" in text:
            marker = element
            break

    if not marker:
        return result

    # Prefer rows in the table containing the marker. This avoids unrelated
    # "Click Here" links elsewhere on the page.
    table = marker.find_parent("table")
    if not table:
        table = marker.find_next("table")
    rows = table.find_all("tr") if table else []

    for row in rows:
        row_text = clean(row.get_text(" ", strip=True)).lower()
        if not row_text:
            continue

        links = []
        for anchor in row.find_all("a", href=True):
            href = usable(anchor.get("href"))
            if href:
                links.append(href)

        if not links:
            continue

        # For Apply Online, the destination must be an external portal.
        # SarkariResult may place an internal/self link in the same row before
        # the real application href. Never use that internal link as Apply Online.
        page_host = urlparse(page_url).netloc.lower()
        external_links = [
            link for link in links
            if urlparse(link).netloc.lower() != page_host
        ]
        href = external_links[0] if external_links else links[0]

        if (
            not result["apply_link"]
            and external_links
            and any(x in row_text for x in [
                "apply online", "online application", "application link",
                "registration link", "apply now"
            ])
        ):
            result["apply_link"] = href

        if (
            not result["notification_link"]
            and any(x in row_text for x in [
                "official notification", "download notification",
                "notification pdf", "detailed notification",
                "short notice", "advertisement"
            ])
        ):
            result["notification_link"] = href

        if (
            not result["result_link"]
            and re.search(r"\b(result|download result|check result)\b", row_text)
        ):
            result["result_link"] = href

        if (
            not result["admit_card_link"]
            and any(x in row_text for x in [
                "admit card", "download admit card", "hall ticket"
            ])
        ):
            result["admit_card_link"] = href

        if (
            not result["answer_key_link"]
            and any(x in row_text for x in [
                "answer key", "download answer key", "final answer key"
            ])
        ):
            result["answer_key_link"] = href

        if (
            not result["official_website"]
            and any(x in row_text for x in [
                "official website", "official site", "department website"
            ])
        ):
            result["official_website"] = href

    return result


def extract_links(soup, page_url):
    result = {
        "apply_link": "",
        "notification_link": "",
        "official_website": ""
    }

    important = extract_important_links(soup, page_url)
    for key in ("apply_link", "notification_link", "official_website"):
        if important.get(key):
            result[key] = important[key]

    page_parts = urlparse(page_url)
    page_path = page_parts.path.rstrip("/") or "/"

    def is_same_page(href):
        parts = urlparse(href)
        href_path = parts.path.rstrip("/") or "/"
        return (
            parts.netloc.lower() == page_parts.netloc.lower()
            and href_path == page_path
        )

    def is_bad_link(href):
        lower = href.lower()
        if is_same_page(href):
            return True
        if any(domain in lower for domain in [
            "play.google.com", "apps.apple.com", "whatsapp.com", "wa.me",
            "t.me", "telegram.me", "facebook.com", "instagram.com",
            "youtube.com", "twitter.com", "x.com"
        ]):
            return True
        if lower.startswith(("javascript:", "mailto:")):
            return True
        return False

    candidates = []

    for link in soup.find_all("a", href=True):
        text = clean(link.get_text(" ", strip=True))
        href = urljoin(page_url, link["href"])

        if not href.startswith(("http://", "https://")):
            continue

        # Use only the anchor itself for strong link detection. Broad parent
        # context is intentionally avoided because it can contain unrelated
        # words from the whole page (for example "registration" or
        # "advertisement"), causing false links.
        nearby_heading = ""
        heading = link.find_previous(["h1", "h2", "h3", "h4", "h5", "h6"])
        if heading:
            nearby_heading = clean(heading.get_text(" ", strip=True)).lower()

        candidates.append((text.lower(), href, nearby_heading))

    for text, href, nearby_heading in candidates:
        href_lower = href.lower()
        generic_click = text.strip() in {"click here", "click here to download"}

        if not result["apply_link"] and not is_bad_link(href):
            strong_apply_text = any(
                phrase in text
                for phrase in [
                    "apply online",
                    "online application",
                    "apply now",
                    "registration link",
                    "application link",
                ]
            )
            # Never select an Apply link merely because its URL contains
            # "apply"/"registration". Social and promotional URLs can contain
            # those words. Require explicit anchor text or an Apply heading.
            is_external = urlparse(href).netloc.lower() != page_parts.netloc.lower()
            if is_external and strong_apply_text:
                result["apply_link"] = href
            elif is_external and generic_click and "apply" in nearby_heading:
                result["apply_link"] = href

        if not result["notification_link"] and not is_bad_link(href):
            strong_notification_text = any(
                phrase in text
                for phrase in [
                    "official notification",
                    "download notification",
                    "notification pdf",
                    "detailed notification",
                    "advertisement",
                    "short notice",
                ]
            )
            strong_notification_url = (
                "notification" in href_lower
                or "advertisement" in href_lower
                or href_lower.endswith(".pdf")
                or ".pdf?" in href_lower
            )
            if strong_notification_text or strong_notification_url:
                result["notification_link"] = href
            elif generic_click and (
                "official notification" in nearby_heading
                or "check official notification" in nearby_heading
                or "check short notice" in nearby_heading
            ):
                result["notification_link"] = href

        if (
            not result["official_website"]
            and not is_bad_link(href)
            and any(
                phrase in text
                for phrase in [
                    "official website",
                    "official site",
                    "department website",
                ]
            )
        ):
            result["official_website"] = href

    return result



def extract_job(url):
    soup = get_page(url)
    title = clean(soup.title.get_text(" ", strip=True)) if soup.title else ""

    # SarkariResult is our source, not our brand. Remove its site branding
    # from recruitment titles before storing or publishing them.
    title = re.sub(
        r"\s*(?:\||[-–—])\s*sarkari\s*result\s*$",
        "",
        title,
        flags=re.IGNORECASE,
    ).strip()

    lines = []
    for element in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "td", "th"]):
        value = clean(element.get_text(" ", strip=True))
        if value and value not in lines:
            lines.append(value)

    tables = extract_tables(soup)
    vacancies = extract_vacancies(tables)
    dates = extract_dates(lines)
    links = extract_links(soup, url)

    data = {
        "title": title or (lines[0] if lines else "Untitled Recruitment"),
        "source_url": url,
        "organization": extract_organization(title, lines),
        "total_vacancies": vacancies.get("total_posts") or "Not specified",
        "post_wise_vacancies": vacancies.get("post_wise", []),
        "category_wise_vacancies": vacancies.get("category_wise", []),
        "qualification": extract_qualification(lines, tables),
        "age_limit": extract_age(lines) or "Not specified",
        "age_relaxation": extract_age_relaxation(lines),
        "salary": extract_salary(lines, tables) or "Not specified",
        "application_fee": extract_fee(lines) or "Not specified",
        "important_dates": dates,
        "selection_process": extract_selection(lines),
        "event_statuses": extract_event_statuses(lines),
        **links,
    }

    # Keep the real resource links separately so downstream messages can use
    # them without confusing them with the generic notification link.
    resources = extract_important_links(soup, url)
    data.update({
        "result_link": resources.get("result_link", ""),
        "admit_card_link": resources.get("admit_card_link", ""),
        "answer_key_link": resources.get("answer_key_link", ""),
    })

    return data
