import re
import requests
from urllib.parse import urlparse


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
    )
}

# Known official domains for common Indian government recruiters.
OFFICIAL_DOMAINS = {
    "ssc": ["ssc.gov.in"],
    "staff selection commission": ["ssc.gov.in"],
    "upsc": ["upsc.gov.in"],
    "union public service commission": ["upsc.gov.in"],
    "bpsc": ["bpsc.bihar.gov.in"],
    "railway": ["indianrailways.gov.in", "rrbapply.gov.in", "rrbcdg.gov.in"],
    "rrb": ["indianrailways.gov.in", "rrbapply.gov.in"],
    "isro": ["isro.gov.in"],
    "drdo": ["drdo.gov.in"],
    "india post": ["indiapost.gov.in"],
    "lic": ["licindia.in"],
}


def domain(url):
    try:
        return urlparse(url).netloc.lower().split(":")[0].removeprefix("www.")
    except Exception:
        return ""


def official_domains_for(job):
    text = (
        str(job.get("organization", "")) + " " +
        str(job.get("title", ""))
    ).lower()

    domains = []
    for keyword, values in OFFICIAL_DOMAINS.items():
        if keyword in text:
            domains.extend(values)

    return sorted(set(domains))


def is_official(url, allowed_domains):
    if not url or url in ("Not found", "Not specified"):
        return False

    host = domain(url)

    return any(
        host == item or host.endswith("." + item)
        for item in allowed_domains
    )


def fetch_text(url):
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=25,
            allow_redirects=True
        )
        response.raise_for_status()
        return response.url, response.text
    except Exception as error:
        return "", str(error)


def page_text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip().lower()


def value_present(text, value):
    if not value or value in ("Not specified", "Not found"):
        return None

    numbers = re.findall(r"\d[\d,]*", str(value))
    if numbers:
        return any(number.replace(",", "") in text for number in numbers)

    words = [
        word.lower()
        for word in re.findall(r"[a-zA-Z]{4,}", str(value))
    ]

    if not words:
        return None

    return sum(word in text for word in words) >= max(1, len(words) // 2)


def verify_job(job):
    allowed_domains = official_domains_for(job)

    result = {
        "verification_status": "NEEDS_REVIEW",
        "official_domains_expected": allowed_domains,
        "official_source_checked": False,
        "official_source_url": "",
        "checks": [],
        "verification_notes": []
    }

    candidate_urls = [
        job.get("notification_link", ""),
        job.get("apply_link", ""),
        job.get("official_website", "")
    ]

    official_candidates = [
        url for url in candidate_urls
        if is_official(url, allowed_domains)
    ]

    if not allowed_domains:
        result["verification_notes"].append(
            "Official domain is not known for this organization yet."
        )
        return result

    if not official_candidates:
        result["verification_notes"].append(
            "No known official-domain link was found on the source page."
        )
        return result

    for url in official_candidates:
        final_url, html = fetch_text(url)

        if not final_url:
            result["checks"].append({
                "url": url,
                "status": "UNREACHABLE"
            })
            continue

        text = page_text(html)

        result["official_source_checked"] = True
        result["official_source_url"] = final_url

        checks = {
            "url": final_url,
            "status": "REACHABLE",
            "title_match": None,
            "vacancy_match": value_present(
                text, job.get("total_vacancies", "")
            ),
            "last_date_match": value_present(
                text,
                job.get("important_dates", {}).get(
                    "application_last_date", ""
                )
            )
        }

        title = str(job.get("title", ""))
        title_words = [
            word.lower()
            for word in re.findall(r"[A-Za-z]{4,}", title)
        ]

        if title_words:
            checks["title_match"] = (
                sum(word in text for word in title_words)
                >= max(2, len(title_words) // 3)
            )

        result["checks"].append(checks)

        # Do not require every field to appear on the landing page.
        # A verified status requires an official page plus supporting matches.
        supporting_matches = [
            checks["title_match"],
            checks["vacancy_match"],
            checks["last_date_match"]
        ]

        if (
            checks["title_match"] is True
            and any(value is True for value in supporting_matches[1:])
        ):
            result["verification_status"] = "VERIFIED"
            result["verification_notes"].append(
                "Official-domain source is reachable and supports the job identity plus key details."
            )
            return result

    if result["official_source_checked"]:
        result["verification_notes"].append(
            "Official source was reachable, but the available page did not provide enough matching evidence."
        )

    return result
