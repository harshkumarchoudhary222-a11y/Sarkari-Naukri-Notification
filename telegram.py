import html
import os
import re
import requests


TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def _value(value, default="Not specified"):
    if value is None:
        return default
    if isinstance(value, list):
        if not value:
            return default
        return "\n".join(f"• {item}" for item in value)
    if isinstance(value, dict):
        return str(value)
    text = str(value).strip()
    return text or default


def _escape(value):
    return html.escape(str(value), quote=False)


def _link(label, url):
    if not url or str(url).strip() in {"", "Not found", "Not specified"}:
        return ""
    return f'🔗 <a href="{html.escape(str(url), quote=True)}">{_escape(label)}</a>'


def _apply_link(job):
    url = job.get("apply_link")
    if url and str(url).strip() not in {"", "Not found", "Not specified"}:
        return str(url).strip()
    return str(job.get("source_url") or "").strip()


def _format_table_rows(rows):
    if not rows:
        return ""
    lines = []
    for row in rows:
        if isinstance(row, list):
            lines.append("• " + " | ".join(str(x) for x in row if str(x).strip()))
    return "\n".join(lines)


def _short_date(value):
    text = _value(value)
    return text


def _eligibility(job):
    value = job.get("qualification")
    text = _value(value)
    bad = {
        "post name",
        "name of post",
        "education qualification",
        "educational qualification",
        "qualification",
        "eligibility",
        "eligibility criteria",
        "required qualification",
    }
    if text.lower().strip() in bad or text.lower().strip().endswith(":"):
        return "Not specified"
    # Keep Telegram compact; the full qualification will be available in the detailed post.
    return text.replace("\n", " ").strip()


def _hashtags(job):
    title = _value(job.get("title"), "")
    org = _value(job.get("organization"), "")
    tags = ["#SarkariResult", "#SarkariExam"]
    words = re.findall(r"[A-Za-z0-9]+", title + " " + org)
    for word in words:
        if len(word) >= 3 and word.upper() in {"SSC", "UPSC", "RRB", "BPSC", "IBPS", "SBI", "LIC", "DRDO", "ISRO", "NTA", "CTET", "REET"}:
            tag = "#" + word.upper()
            if tag not in tags:
                tags.append(tag)
    tags += ["#sarkariresult2026", "#sarkarinaukri"]
    return " ".join(tags)


def build_new_job_message(job):
    dates = job.get("important_dates", {})

    title = _escape(_value(job.get("title")))
    start_date = _escape(_short_date(dates.get("application_start")))
    last_date = _escape(_short_date(dates.get("application_last_date")))
    exam_date = _escape(_short_date(dates.get("exam_date")))
    eligibility = _escape(_eligibility(job))
    total = _escape(_value(job.get("total_vacancies")))

    parts = [
        "⏳ <b>अंतिम तिथि का इंतजार न करें, आवेदन चल रहे हैं ✅</b>",
        "",
        f"🔥🔥 <b>{title}</b>",
        f"➡️ Application Starts From : {start_date}",
        f"➡️ Last Date : {last_date}",
        f"➡️ Eligibility : {eligibility}",
        f"➡️ Total : {total} Posts",
        f"➡️ Exam Date : {exam_date}",
        "",
        _escape(_hashtags(job)),
        "",
        "📢 <b>Sarkari Naukri Notification</b> 👈",
        "",
        "Click Below Link To Check & Apply 👇",
        "",
        _link("Apply Here", _apply_link(job)),
        "",
        "📌 Detailed recruitment information is available in the full post.",
        "",
        "📢 <b>Join Us:</b> @sarkari_naukri_notification",
    ]

    return "\n".join(part for part in parts if part != "")


def build_update_message(job, update):
    changes = update.get("changes", [])
    lines = []
    for change in changes:
        lines.append(
            f"• <b>{_escape(change.get('label', 'Updated'))}</b>: "
            f"{_escape(change.get('old', 'Not specified'))} → "
            f"{_escape(change.get('new', 'Not specified'))}"
        )

    parts = [
        "🔔 <b>Important Recruitment Update</b>",
        "",
        f"🔥 <b>{_escape(_value(job.get('title')))}</b>",
        "",
        "📢 <b>What Changed:</b>",
        "\n".join(lines) or "• Recruitment details updated.",
        "",
        "Click Below Link To Check & Apply 👇",
        "",
        _link("Apply Here", job.get("apply_link") or job.get("source_url")),
        _link("Official Notification", job.get("notification_link")),
        "",
        "📢 <b>Join Us:</b> @sarkari_naukri_notification",
    ]

    return "\n".join(part for part in parts if part != "")


def send_telegram_message(message):
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "@sarkari_naukri_notification").strip()

    if not token:
        print("Telegram not configured: TELEGRAM_BOT_TOKEN is missing.")
        return False

    response = requests.post(
        TELEGRAM_API.format(token=token),
        data={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=20,
    )

    if not response.ok:
        raise RuntimeError(
            f"Telegram API error {response.status_code}: {response.text[:500]}"
        )

    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram API rejected message: {payload}")

    print("Telegram message sent successfully.")
    return True
