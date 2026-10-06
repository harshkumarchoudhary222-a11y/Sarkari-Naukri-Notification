import html
import os
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


def _format_table_rows(rows):
    if not rows:
        return ""
    lines = []
    for row in rows:
        if isinstance(row, list):
            lines.append("• " + " | ".join(str(x) for x in row if str(x).strip()))
    return "\n".join(lines)


def build_new_job_message(job):
    dates = job.get("important_dates", {})
    events = job.get("event_statuses", {})

    parts = [
        f"🚨 <b>{_escape(_value(job.get('title')))}</b>",
        "",
        f"🏢 <b>Organization:</b> {_escape(_value(job.get('organization')))}",
        f"👥 <b>Total Vacancies:</b> {_escape(_value(job.get('total_vacancies')))}",
    ]

    post_wise = _format_table_rows(job.get("post_wise_vacancies", []))
    if post_wise:
        parts += ["", "📌 <b>Post-wise Vacancies:</b>", _escape(post_wise)]

    category_wise = _format_table_rows(job.get("category_wise_vacancies", []))
    if category_wise:
        parts += ["", "📊 <b>Category-wise Vacancies:</b>", _escape(category_wise)]

    parts += [
        "",
        f"🎓 <b>Qualification:</b> {_escape(_value(job.get('qualification')))}",
        f"🎂 <b>Age Limit:</b> {_escape(_value(job.get('age_limit')))}",
        f"↕️ <b>Age Relaxation:</b> {_escape(_value(job.get('age_relaxation')))}",
        f"💰 <b>Salary/Pay:</b> {_escape(_value(job.get('salary')))}",
        f"💳 <b>Application Fee:</b> {_escape(_value(job.get('application_fee')))}",
        "",
        "📅 <b>Important Dates:</b>",
        f"• Application Start: {_escape(_value(dates.get('application_start')))}",
        f"• Last Date: {_escape(_value(dates.get('application_last_date')))}",
        f"• Fee Payment: {_escape(_value(dates.get('fee_payment_last_date')))}",
        f"• Correction: {_escape(_value(dates.get('correction_date')))}",
        f"• Exam Date: {_escape(_value(dates.get('exam_date')))}",
        "",
        "📝 <b>Selection Process:</b>",
        _escape(_value(job.get("selection_process"))),
    ]

    active_events = []
    for key, label in [
        ("admit_card_status", "Admit Card"),
        ("exam_city_status", "Exam City/Intimation"),
        ("answer_key_status", "Answer Key"),
        ("result_status", "Result"),
    ]:
        status = events.get(key, "Not mentioned")
        if status and status != "Not mentioned":
            active_events.append(f"• {label}: {status}")

    if active_events:
        parts += ["", "📢 <b>Latest Status:</b>", _escape("\n".join(active_events))]

    parts += [
        "",
        _link("Apply Here", job.get("apply_link")),
        _link("Official Notification", job.get("notification_link")),
        _link("Official Website", job.get("official_website")),
        _link("Source / Reference", job.get("source_url")),
        "",
        f"✅ <b>Verification:</b> {_escape(job.get('verification', {}).get('verification_status', 'NEEDS_REVIEW'))}",
        "",
        "📢 <b>Join:</b> @sarkari_naukri_notification",
    ]

    return "\n".join(part for part in parts if part != "")


def build_update_message(job, update):
    changes = update.get("changes", [])
    lines = []
    for change in changes:
        lines.append(
            f"• <b>{_escape(change.get('label', 'Updated'))}</b>\n"
            f"  Old: {_escape(change.get('old', 'Not specified'))}\n"
            f"  New: {_escape(change.get('new', 'Not specified'))}"
        )

    change_text = "\n".join(lines) or "• Recruitment details updated."

    parts = [
        f"🔔 <b>Recruitment Update: {_escape(_value(job.get('title')))}</b>",
        "",
        f"🏢 <b>Organization:</b> {_escape(_value(job.get('organization')))}",
        f"🚨 <b>Update Type:</b> {_escape(update.get('change_type', 'MATERIAL_UPDATE'))}",
        "",
        "📌 <b>What Changed:</b>",
        change_text,
        "",
        _link("Apply Online", job.get("apply_link")),
        _link("Official Notification", job.get("notification_link")),
        _link("Official Website", job.get("official_website")),
        _link("Source / Reference", job.get("source_url")),
        "",
        f"✅ <b>Verification:</b> {_escape(job.get('verification', {}).get('verification_status', 'NEEDS_REVIEW'))}",
        "",
        "📢 <b>Join:</b> @sarkari_naukri_notification",
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
