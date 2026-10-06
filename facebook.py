import html
import os
import re

import requests


GRAPH_VERSION = os.getenv("META_GRAPH_VERSION", "v23.0")
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"


def _value(value, default="Not specified"):
    if value is None:
        return default
    if isinstance(value, list):
        if not value:
            return default
        return " ".join(str(item) for item in value)
    text = str(value).strip()
    return text or default


def _clean_text(value):
    text = _value(value)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _hashtags(job):
    title = _clean_text(job.get("title"))
    org = _clean_text(job.get("organization"))
    tags = ["#SarkariResult", "#SarkariExam", "#SarkariNaukri"]
    for word in re.findall(r"[A-Za-z0-9]+", title + " " + org):
        if word.upper() in {"SSC", "UPSC", "RRB", "BPSC", "IBPS", "SBI", "LIC", "DRDO", "ISRO", "NTA", "CTET", "REET"}:
            tag = "#" + word.upper()
            if tag not in tags:
                tags.append(tag)
    return " ".join(tags)


def build_new_facebook_post(job, detail_url=None):
    dates = job.get("important_dates", {})
    title = _clean_text(job.get("title"))
    start = _clean_text(dates.get("application_start"))
    last = _clean_text(dates.get("application_last_date"))
    exam = _clean_text(dates.get("exam_date"))
    qualification = _clean_text(job.get("qualification"))
    total = _clean_text(job.get("total_vacancies"))

    lines = [
        "⏳ अंतिम तिथि का इंतजार न करें, आवेदन चल रहे हैं ✅",
        "",
        f"🔥🔥 {title}",
        f"➡️ Start Date : {start}",
        f"➡️ Last Date : {last}",
        f"➡️ Eligibility : {qualification}",
        f"➡️ Total : {total} Posts",
        f"➡️ Exam Date : {exam}",
        "",
        _hashtags(job),
        "",
        "📢 Sarkari Naukri Notification",
        "",
        "👇 Check Full Details & Apply",
    ]

    if detail_url:
        lines += [detail_url]

    return "\n".join(lines)


def build_update_facebook_post(job, update, detail_url=None):
    title = _clean_text(job.get("title"))
    lines = [
        "🔔 Important Recruitment Update",
        "",
        f"🔥 {title}",
        "",
        "📢 What Changed:",
    ]

    for change in update.get("changes", []):
        label = _clean_text(change.get("label", "Updated"))
        old = _clean_text(change.get("old", "Not specified"))
        new = _clean_text(change.get("new", "Not specified"))
        lines.append(f"➡️ {label}: {old} → {new}")

    if detail_url:
        lines += ["", "👇 Check Full Details & Apply", detail_url]

    lines += ["", _hashtags(job)]
    return "\n".join(lines)


def send_facebook_post(message, link=None):
    page_id = os.getenv("FACEBOOK_PAGE_ID", "").strip()
    page_token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN", "").strip()

    if not page_id or not page_token:
        print("Facebook not configured: FACEBOOK_PAGE_ID or FACEBOOK_PAGE_ACCESS_TOKEN is missing.")
        return False

    url = f"{GRAPH_BASE}/{page_id}/feed"
    data = {
        "message": message,
        "access_token": page_token,
    }

    if link:
        data["link"] = link

    response = requests.post(url, data=data, timeout=30)

    if not response.ok:
        raise RuntimeError(
            f"Facebook Graph API error {response.status_code}: {response.text[:1000]}"
        )

    payload = response.json()

    if "error" in payload:
        raise RuntimeError(f"Facebook rejected post: {payload}")

    print("Facebook post published:", payload.get("id", "unknown"))
    return True
