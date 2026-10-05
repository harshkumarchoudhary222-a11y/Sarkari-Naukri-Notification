import re
from copy import deepcopy


NOT_MENTIONED = {
    "",
    "not specified",
    "not found",
    "not mentioned",
    "not available"
}


TRACKED_FIELDS = {
    "total_vacancies": "Vacancy",
    "qualification": "Qualification",
    "age_limit": "Age limit",
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


def meaningful(value):
    return normalize(value) not in NOT_MENTIONED


def compare_jobs(old, new):
    changes = []

    for field, label in TRACKED_FIELDS.items():
        before = old.get(field)
        after = new.get(field)

        if normalize(before) != normalize(after):
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

        if normalize(before) != normalize(after):
            if meaningful(before) or meaningful(after):
                changes.append({
                    "field": f"event_statuses.{field}",
                    "label": label,
                    "old": before or "Not mentioned",
                    "new": after or "Not mentioned"
                })

    old_selection = normalize(old.get("selection_process", []))
    new_selection = normalize(new.get("selection_process", []))

    if old_selection != new_selection and (old_selection or new_selection):
        changes.append({
            "field": "selection_process",
            "label": "Selection process",
            "old": old.get("selection_process", []) or "Not mentioned",
            "new": new.get("selection_process", []) or "Not mentioned"
        })

    old_posts = normalize(old.get("post_wise_vacancies", []))
    new_posts = normalize(new.get("post_wise_vacancies", []))

    if old_posts != new_posts and (old_posts or new_posts):
        changes.append({
            "field": "post_wise_vacancies",
            "label": "Post-wise vacancies",
            "old": old.get("post_wise_vacancies", []) or "Not mentioned",
            "new": new.get("post_wise_vacancies", []) or "Not mentioned"
        })

    old_categories = normalize(old.get("category_wise_vacancies", []))
    new_categories = normalize(new.get("category_wise_vacancies", []))

    if old_categories != new_categories and (old_categories or new_categories):
        changes.append({
            "field": "category_wise_vacancies",
            "label": "Category-wise vacancies",
            "old": old.get("category_wise_vacancies", []) or "Not mentioned",
            "new": new.get("category_wise_vacancies", []) or "Not mentioned"
        })

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
