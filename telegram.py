import html
import os
import re
import requests
from io import BytesIO
from urllib.parse import urlparse


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
    url = str(job.get("apply_link") or "").strip()
    if not url or url in {"Not found", "Not specified"}:
        return ""

    # Defense in depth: an Apply Online button must never point back to the
    # SarkariResult source domain. The extractor is already required to find
    # an external application portal, and Telegram rejects any legacy/internal
    # URL that may still exist in an older saved job record.
    source = str(job.get("source_url") or "").strip()
    if source:
        try:
            if urlparse(url).netloc.lower() == urlparse(source).netloc.lower():
                return ""
        except ValueError:
            return ""

    return url


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


def _display_title(value):
    """Remove source-site branding accidentally included in scraped titles."""
    text = str(value or "").strip()
    text = re.sub(r"\s*\|\s*Sarkari\s*Result\s*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*[-–—]\s*Sarkari\s*Result\s*$", "", text, flags=re.IGNORECASE)
    return text.strip() or "Government Recruitment"


def _summary(job):
    text = str(job.get("summary") or "").strip()
    if not text:
        return ""

    # Keep the Telegram post compact while preserving the useful introductory
    # context from the source page.
    text = re.sub(r"\s+", " ", text)
    if len(text) > 420:
        text = text[:417].rsplit(" ", 1)[0] + "..."
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

    title = _escape(_display_title(job.get("title")))
    start_date = _escape(_short_date(dates.get("application_start")))
    last_date = _escape(_short_date(dates.get("application_last_date")))
    exam_date = _escape(_short_date(dates.get("exam_date")))
    eligibility = _escape(_eligibility(job))
    total = _escape(_value(job.get("total_vacancies")))

    links = []
    apply = _apply_link(job)
    official = job.get("official_website", "")

    if apply:
        links.append(_link("📝 Apply Online", apply))
    if official:
        links.append(_link("🌐 Official Website", official))

    summary = _summary(job)

    info_block = "\n".join([
        f"➡️ <b>Application Starts:</b> {start_date}",
        f"➡️ <b>Last Date:</b> {last_date}",
        f"➡️ <b>Eligibility:</b> {eligibility}",
        f"➡️ <b>Total Posts:</b> {total}",
        f"➡️ <b>Exam Date:</b> {exam_date}",
    ])

    parts = [
        "⏳ <b>अंतिम तिथि का इंतजार न करें, आवेदन चल रहे हैं ✅</b>",
        "",
        f"🔥 <b>{title}</b>",
        "",
    ]

    if summary:
        parts.extend([
            "📌 <b>About:</b>",
            _escape(summary),
            "",
        ])

    parts.extend([
        "📅 <b>Important Dates</b>",
        info_block,
        "",
        _escape(_hashtags(job)),
        "",
        "📌 <b>Important Links</b>",
        "",
        "\n".join(links) if links else _link("🌐 Official Website", job.get("official_website", "")),
        "",
    ])

    if job.get("notification_link"):
        parts.extend([
            "📄 <b>Official Notification</b>",
            "👇 PDF/document attached below",
            "",
        ])

    parts.extend([
        "📢 <b>Sarkari Naukri Notification</b>",
        "👉 @sarkari_naukri_notification",
        "",
        "━━━━━━━━━━━━━━━━━━",
        "📚 <b>DAILY EXAM QUIZ</b>",
        "SSC • UPSC • BPSC • BANKING",
        "📝 PYQs + Practice Questions",
        "👉 Join Now: @upsc_ssc_bpsc_bank",
        "━━━━━━━━━━━━━━━━━━",
    ])

    return "\n".join(part for part in parts if part != "")


def _safe_change_value(change, side):
    value = change.get(side, "Not specified")
    field = str(change.get("field", "")).lower()
    text = str(value or "").strip()
    lower = text.lower()

    # Never expose known app-store/social/promotional URLs in a public
    # recruitment update, even if they exist in an older saved job snapshot.
    blocked = (
        "play.google.com", "apps.apple.com", "whatsapp.com", "wa.me",
        "t.me", "telegram.me", "facebook.com", "instagram.com",
        "youtube.com", "twitter.com", "x.com"
    )
    if field.endswith("apply_link") and any(item in lower for item in blocked):
        return "Not available"

    return text or "Not specified"


def build_update_message(job, update):
    changes = update.get("changes", [])
    lines = []
    for change in changes:
        lines.append(
            f"• <b>{_escape(change.get('label', 'Updated'))}</b>: "
            f"{_escape(_safe_change_value(change, 'old'))} → "
            f"{_escape(_safe_change_value(change, 'new'))}"
        )

    links = []
    apply = job.get("apply_link")
    notification = job.get("notification_link")
    if apply:
        links.append(_link("📝 Apply Online", apply))
    if notification:
        links.append(_link("📄 Official Notification", notification))

    parts = [
        "🔔 <b>Important Recruitment Update</b>",
        "",
        f"🔥 <b>{_escape(_display_title(job.get('title')))}</b>",
        "",
        "📢 <b>What Changed:</b>",
        "",
        "\n\n".join(lines) or "• Recruitment details updated.",
        "",
        "📌 <b>Important Links</b>",
        "",
        "\n\n".join(links) if links else "",
        "",
        "📢 <b>Join Us:</b>",
        "@sarkari_naukri_notification",
        "",
        "━━━━━━━━━━━━━━━━━━",
        "📚 <b>DAILY EXAM QUIZ</b>",
        "SSC • UPSC • BPSC • BANKING",
        "📝 PYQs + Practice Questions",
        "👉 Join Now: @upsc_ssc_bpsc_bank",
        "━━━━━━━━━━━━━━━━━━",
    ]

    return "\n".join(part for part in parts if part != "")


def build_update_alert_message(item):
    category = item.get("category", "")
    title = _display_title(item.get("title", "Government Exam Update"))
    title_lower = title.lower()

    if "interview" in title_lower or "personality test" in title_lower:
        icon, heading = "🎤", "INTERVIEW SCHEDULE"
    elif "exam city" in title_lower or "city intimation" in title_lower:
        icon, heading = "🏙️", "EXAM CITY UPDATE"
    elif "exam date" in title_lower or "schedule" in title_lower:
        icon, heading = "📅", "EXAM DATE UPDATE"
    elif "application status" in title_lower:
        icon, heading = "🔎", "APPLICATION STATUS"
    else:
        labels = {
            "RESULT": ("🏆", "RESULT DECLARED"),
            "ADMIT_CARD": ("🎫", "ADMIT CARD UPDATE"),
            "ANSWER_KEY": ("📝", "ANSWER KEY RELEASED"),
        }
        icon, heading = labels.get(category, ("🔔", "IMPORTANT UPDATE"))

    primary = item.get("primary_link")
    primary_label = item.get("primary_label", "Open Update")
    official = item.get("official_website")

    # Do not copy the source site's long historical paragraph into Telegram.
    # The title and the action link already tell users what changed.
    action_hint = ""
    if "interview" in title_lower or "personality test" in title_lower:
        action_hint = "UPSC has released the interview/personality-test schedule. Check your roll number and interview date in the official schedule."
    elif "exam city" in title_lower or "city intimation" in title_lower:
        action_hint = "Exam City / Intimation details are available. Check your allotted city using the official link."
    elif "exam date" in title_lower or "schedule" in title_lower:
        action_hint = "The exam schedule/date has been updated. Check the official notice for the latest date and instructions."
    elif "application status" in title_lower:
        action_hint = "Application status has been updated. Check your application using the official portal."
    elif category == "RESULT":
        action_hint = "The result has been released. Check your result using the official link."
    elif category == "ANSWER_KEY":
        action_hint = "The answer key has been released. Check the official link for the latest version."
    else:
        action_hint = "The latest exam update is available. Check the official link for details."

    parts = [
        f"{icon} <b>{heading}</b>",
        "",
        f"🔥 <b>{_escape(title)}</b>",
        "",
        f"📅 <b>Updated:</b> {_escape(item.get('published', 'Today'))}",
        "",
        "📌 <b>UPDATE</b>",
        _escape(action_hint),
        "",
    ]

    if primary:
        parts.extend([
            _link(primary_label, primary),
            "",
        ])

    if official:
        parts.extend([
            _link("🌐 Official Website", official),
            "",
        ])

    if not primary:
        parts.extend([
            "⚠️ Direct action link was not found. Please use the official website above.",
            "",
        ])

    parts.extend([
        "⚠️ Verify dates and instructions on the official authority website.",
        "",
        "📢 <b>Sarkari Naukri Notification</b>",
        "@sarkari_naukri_notification",
        "",
        "━━━━━━━━━━━━━━━━━━",
        "📚 <b>DAILY EXAM QUIZ</b>",
        "SSC • UPSC • BPSC • BANKING",
        "📝 PYQs + Practice Questions",
        "👉 Join Now: @upsc_ssc_bpsc_bank",
        "━━━━━━━━━━━━━━━━━━",
    ])

    return "\n".join(part for part in parts if part != "")


def send_telegram_document(document_url, title="Official Notification"):
    """Download a notification PDF/image and upload it directly to Telegram."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "@sarkari_naukri_notification").strip()

    if not token or not document_url:
        return False

    max_size = 50 * 1024 * 1024

    try:
        response = requests.get(
            document_url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0 Safari/537.36"
                )
            },
            timeout=45,
            allow_redirects=True,
            stream=True,
        )
        response.raise_for_status()

        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > max_size:
            print("Notification file is larger than Telegram's 50 MB limit.")
            return False

        chunks = []
        total = 0
        for chunk in response.iter_content(chunk_size=1024 * 256):
            if not chunk:
                continue
            total += len(chunk)
            if total > max_size:
                print("Notification file exceeds Telegram's 50 MB limit.")
                return False
            chunks.append(chunk)

        content = b"".join(chunks)
        content_type = response.headers.get("Content-Type", "").lower()

        # Reject HTML/login/error pages even when the URL ends in .pdf.
        is_pdf = content.startswith(b"%PDF-")
        is_image = (
            content.startswith(b"\\xff\\xd8\\xff") or
            content.startswith(b"\\x89PNG\\r\\n\\x1a\\n") or
            content.startswith(b"GIF87a") or
            content.startswith(b"GIF89a") or
            content.startswith(b"RIFF") and b"WEBP" in content[:16]
        )

        if not (is_pdf or is_image):
            print(
                "Notification link did not return a PDF/image. "
                f"Content-Type: {content_type}"
            )
            return False

        path_name = urlparse(response.url).path.rsplit("/", 1)[-1]
        filename = re.sub(r"[^A-Za-z0-9._-]+", "_", path_name).strip("._-")

        if not filename:
            filename = "official-notification.pdf" if is_pdf else "official-notification.jpg"

        if is_pdf and not filename.lower().endswith(".pdf"):
            filename += ".pdf"

        if is_image and not re.search(r"\\.(?:jpg|jpeg|png|gif|webp)$", filename, re.I):
            filename += ".jpg"

        caption = (
            f"📄 <b>{_escape(title)}</b>\\n"
            "Official notification document"
        )

        api_url = TELEGRAM_API.format(token=token).replace(
            "/sendMessage", "/sendDocument"
        )

        upload = requests.post(
            api_url,
            data={
                "chat_id": chat_id,
                "caption": caption,
                "parse_mode": "HTML",
            },
            files={
                "document": (
                    filename,
                    BytesIO(content),
                    "application/pdf" if is_pdf else content_type.split(";")[0] or "application/octet-stream",
                )
            },
            timeout=60,
        )

        if not upload.ok:
            print(
                f"Telegram document upload failed: "
                f"{upload.status_code}: {upload.text[:500]}"
            )
            return False

        payload = upload.json()
        if not payload.get("ok"):
            print(f"Telegram document rejected: {payload}")
            return False

        print("Official notification document sent successfully.")
        return True

    except Exception as error:
        print(f"Official notification download/send failed: {error}")
        return False

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
