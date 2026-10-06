from __future__ import annotations

import os
import time

import requests


def send_quiz_poll(question: dict) -> dict:
    token = os.environ["QUIZ_TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["QUIZ_TELEGRAM_CHAT_ID"]

    telegram_api = f"https://api.telegram.org/bot{token}/sendPoll"

    payload = {
        "chat_id": chat_id,
        "question": question["question"],
        "options": [
            {"text": option} for option in question["options"]
        ],
        "type": "quiz",
        "is_anonymous": True,
        "correct_option_id": question["correct_option_id"],
    }

    if question.get("explanation"):
        payload["explanation"] = question["explanation"]

    while True:
        response = requests.post(telegram_api, json=payload, timeout=30)

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
