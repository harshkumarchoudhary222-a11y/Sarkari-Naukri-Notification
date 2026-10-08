from __future__ import annotations

import json
import os
import time

import requests


def send_quiz_poll(question: dict) -> dict:
    token = os.environ["QUIZ_TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["QUIZ_TELEGRAM_CHAT_ID"]

    telegram_api = f"https://api.telegram.org/bot{token}/sendPoll"

    options = [str(option).strip() for option in question["options"]]

    if not 1 <= len(options) <= 12:
        raise ValueError("Telegram polls support 1 to 12 options.")

    if any(not option for option in options):
        raise ValueError("Poll options cannot be empty.")

    correct_option_id = int(question["correct_option_id"])

    if not 0 <= correct_option_id < len(options):
        raise ValueError("correct_option_id is outside the option range.")

    # Telegram expects options and correct_option_ids as JSON-serialized
    # values when using form-encoded requests.
    payload = {
        "chat_id": chat_id,
        "question": str(question["question"]).strip(),
        "options": json.dumps(
            [{"text": option} for option in options],
            ensure_ascii=False,
        ),
        "type": "quiz",
        "is_anonymous": "true",
        "correct_option_ids": json.dumps([correct_option_id]),
    }

    if question.get("explanation"):
        payload["explanation"] = str(question["explanation"]).strip()

    while True:
        response = requests.post(
            telegram_api,
            data=payload,
            timeout=30,
        )

        if response.status_code == 429:
            data = response.json()
            retry_after = int(data.get("parameters", {}).get("retry_after", 5))
            time.sleep(retry_after + 1)
            continue

        response.raise_for_status()

        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram API error: {data}")

        # Keep a conservative gap between polls to avoid Telegram rate limits.
        time.sleep(3.2)
        return data["result"]
