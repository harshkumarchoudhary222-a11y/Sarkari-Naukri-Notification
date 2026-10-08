from __future__ import annotations

import os
import time

import requests


def send_quiz_poll(question: dict) -> dict:
    token = os.environ["QUIZ_TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["QUIZ_TELEGRAM_CHAT_ID"]

    telegram_api = f"https://api.telegram.org/bot{token}/sendPoll"

    options = [str(option).strip() for option in question["options"]]

    if not 2 <= len(options) <= 12:
        raise ValueError("Telegram polls require 2 to 12 options.")

    if any(not option for option in options):
        raise ValueError("Poll options cannot be empty.")

    if any(len(option) > 100 for option in options):
        raise ValueError("Each poll option must be 100 characters or fewer.")

    poll_question = str(question["question"]).strip()
    if not 1 <= len(poll_question) <= 300:
        raise ValueError("Poll question must be 1 to 300 characters.")

    correct_option_id = int(question["correct_option_id"])
    if not 0 <= correct_option_id < len(options):
        raise ValueError("correct_option_id is outside the option range.")

    payload = {
        "chat_id": chat_id,
        "question": poll_question,
        "options": [{"text": option} for option in options],
        "is_anonymous": True,
        "type": "quiz",
        "correct_option_ids": [correct_option_id],
    }

    if question.get("explanation"):
        explanation = str(question["explanation"]).strip()
        if len(explanation) > 200:
            explanation = explanation[:200]
        payload["explanation"] = explanation

    while True:
        response = requests.post(
            telegram_api,
            json=payload,
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

        time.sleep(3.2)
        return data["result"]
