from __future__ import annotations

import os
import requests


TELEGRAM_API = "https://api.telegram.org/bot{token}/sendPoll"


def send_quiz_poll(question: dict) -> dict:
    token = os.environ["QUIZ_TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["QUIZ_TELEGRAM_CHAT_ID"]

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

    response = requests.post(TELEGRAM_API, json=payload, timeout=30)
    response.raise_for_status()

    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error: {data}")

    return data["result"]
