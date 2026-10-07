import re
from copy import deepcopy


NOT_MENTIONED = {
    "",
    "not specified",
    "not found",
    "not mentioned",
    "not available",
    "not announced",
    "as per government rules",
    "for",
    "before exam",
    "after exam",
    "will be updated here soon",
    "will be updated soon",
    "to be updated",
}


TRACKED_FIELDS = {
    "total_vacancies": "Vacancy",
    "qualification": "Qualification",
    "age_limit": "Age limit",
    "age_relaxation": "Age relaxation",
    "salary": "Salary / pay scale",
    "application_fee": "Application fee",
    "apply_link": "Apply link",
    "notification_link": "Official notification link",
    "official_website": "Official website"
}


DATE_FIELDS = {
    "application_start": "Application start date",
    "application_last_date": "Last date",
    "fee_payment_last_date": "Fee payment last date",
    "correction_date": "Correction window",
    "exam_date": "Exam date",
    "admit_card": "Admit card",
    "result": "Result"
}


def normalize(value):
    if value is None:
        return ""
    if isinstance(value, list):
        return " | ".join(normalize(item) for item in value)
    if isinstance(value, dict):
        return " | ".join(
            f"{key}:{normalize(value[key])}"
            for key in sorted(value)
        )
    text = re.sub(r"\s+", " ", str(value)).strip().lower()
    text = re.sub(r"[^a-z0-9₹:/.%+\- ]+", "", text)
    return text


def canonical_missing(value):
    normalized = normalize(value)
    if normalized in NOT_MENTIONED | {"n/a", "na", "-"}:
        return ""
    return normalized


def meaningful(value):
    return canonical_missing(value) != ""


def compare_jobs(old, new):
    changes = []

    for field, label in TRACKED_FIELDS.items():
        before = old.get(field)
        after = new.get(field)

        before_norm = canonical_missing(before)
        after_norm = canonical_missing(after)

        # "Not mentioned", "Not available", "Not Announced", etc. all mean
        # that no usable update was extracted.
        # update was extracted. Do not alert users for this wording change.
        missing_values = NOT_MENTIONED | {"n/a", "na", "-"}
        if before_norm in missing_values and after_norm in missing_values:
            continue

        # Do not report a truncated qualification as a real update.
        # Ignore incomplete/heading-only old values created by the scraper.
        placeholder_prefixes = (
            "qualification", "eligibility", "education qualification",
            "educational qualification", "mode of selection",
            "selection process", "for"
        )
        if field in {"qualification", "application_fee"} and (
            before_norm in missing_values
            or before_norm in placeholder_prefixes
            or before_norm.endswith("eligibility criteria")
            or before_norm.endswith("mode of selection")
        ):
            if meaningful(after) and before_norm != after_norm:
                # A scraper correction is not itself a recruitment update.
                continue

        if (
            field == "qualification"
            and before_norm
            and after_norm
            and len(after_norm) < len(before_norm)
            and before_norm.startswith(after_norm)
        ):
            continue

        if before_norm != after_norm:
            if meaningful(before) or meaningful(after):
                changes.append({
                    "field": field,
                    "label": label,
                    "old": before or "Not mentioned",
                    "new": after or "Not mentioned"
                })

    old_dates = old.get("important_dates", {}) or {}
    new_dates = new.get("important_dates", {}) or {}

    for field, label in DATE_FIELDS.items():
        before = old_dates.get(field, "")
        after = new_dates.get(field, "")

        if normalize(before) != normalize(after):
            if meaningful(before) or meaningful(after):
                changes.append({
                    "field": f"important_dates.{field}",
                    "label": label,
                    "old": before or "Not mentioned",
                    "new": after or "Not mentioned"
                })

    old_events = old.get("event_statuses", {}) or {}
    new_events = new.get("event_statuses", {}) or {}

    event_labels = {
        "admit_card_status": "Admit card status",
        "exam_city_status": "Exam city/intimation status",
        "answer_key_status": "Answer key status",
        "result_status": "Result status"
    }

    for field, label in event_labels.items():
        before = old_events.get(field, "")
        after = new_events.get(field, "")

        before_norm = canonical_missing(before)
        after_norm = canonical_missing(after)

        # A status disappearing is usually an extraction problem. Only alert
        # when a previously absent status becomes a real status.
        if after_norm in {"", "not mentioned", "not specified", "not announced"}:
            continue
        if before_norm == after_norm:
            continue

        # Generic placeholders such as "Before Exam" are not real status
        # changes. Only alert when the new value contains a concrete date,
        # release state, or meaningful exam/update information.
        placeholder_statuses = NOT_MENTIONED | {
            "before exam", "after exam", "will be updated here soon",
            "will be updated soon", "to be updated", "soon"
        }

        # Source pages often store the label inside the value, e.g.
        # "Admit Card: Before Exam". Compare the meaningful part only.
        status_text = re.sub(
            r"^(admit card|exam city|exam city/intimation|answer key|result)"
            r"(?:\s+status)?\s*:\s*",
            "",
            after_norm,
        ).strip()

        if status_text in placeholder_statuses:
            continue

        changes.append({
            "field": f"event_statuses.{field}",
            "label": label,
            "old": before or "Not mentioned",
            "new": after or "Not mentioned"
        })

    # Selection-process extraction is intentionally not used as an alert
    # signal yet; source-page headings frequently reformat without a real
    # recruitment change.
    
    # Post/category tables can be reformatted by the source page without
    # changing the actual vacancy count. Treat the total vacancy field as the
    # authoritative change signal to avoid noisy false updates from FAQ tables.
    old_total = normalize(old.get("total_vacancies", ""))
    new_total = normalize(new.get("total_vacancies", ""))

    old_posts = normalize(old.get("post_wise_vacancies", []))
    new_posts = normalize(new.get("post_wise_vacancies", []))

    if old_total == new_total and old_posts != new_posts:
        pass

    old_categories = normalize(old.get("category_wise_vacancies", []))
    new_categories = normalize(new.get("category_wise_vacancies", []))

    if old_total == new_total and old_categories != new_categories:
        pass

    return changes


def classify_change(changes):
    fields = {item["field"] for item in changes}

    if any(
        field in fields
        for field in [
            "important_dates.exam_date",
            "important_dates.admit_card",
            "important_dates.result",
            "event_statuses.admit_card_status",
            "event_statuses.exam_city_status",
            "event_statuses.answer_key_status",
            "event_statuses.result_status"
        ]
    ):
        return "HIGH_PRIORITY"

    if any(
        field in fields
        for field in [
            "important_dates.application_last_date",
            "total_vacancies",
            "post_wise_vacancies",
            "category_wise_vacancies",
            "application_fee",
            "qualification",
            "apply_link",
            "notification_link"
        ]
    ):
        return "MATERIAL_UPDATE"

    if changes:
        return "UPDATE"

    return "NO_CHANGE"


def detect_update(old, new):
    changes = compare_jobs(old, new)
    return {
        "has_material_update": bool(changes),
        "change_type": classify_change(changes),
        "changes": changes
    }
