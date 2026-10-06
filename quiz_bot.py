from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests

from quiz_parser import parse_quiz_file
from quiz_sender import send_quiz_poll


BOT_TOKEN = os.environ["QUIZ_TELEGRAM_BOT_TOKEN"]
CHANNEL_ID = os.environ["QUIZ_TELEGRAM_CHAT_ID"]
ADMIN_USER_ID = os.environ["QUIZ_ADMIN_USER_ID"]
API = f"https://api.telegram.org/bot{BOT_TOKEN}"

STATE_FILE = Path("quizzes/bot_state.json")
DOWNLOAD_DIR = Path("quizzes/runtime")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)


def api(method: str, **kwargs) -> dict:
    response = requests.post(f"{API}/{method}", timeout=60, **kwargs)
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error: {data}")
    return data


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"offset": 0}
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    STATE_FILE.write_text(
        json.dumps(state, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def send_message(chat_id: int | str, text: str) -> None:
    api("sendMessage", json={"chat_id": chat_id, "text": text})


def download_document(file_id: str, filename: str) -> Path:
    info = api("getFile", json={"file_id": file_id})
    file_path = info["result"]["file_path"]
    safe_name = Path(filename).name or "quiz.txt"
    destination = DOWNLOAD_DIR / safe_name

    response = requests.get(
        f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}",
        timeout=60,
    )
    response.raise_for_status()
    destination.write_bytes(response.content)
    return destination


def handle_document(message: dict) -> None:
    sender = message.get("from", {})
    chat_id = message["chat"]["id"]

    if str(sender.get("id")) != ADMIN_USER_ID:
        send_message(chat_id, "⛔ This bot is private.")
        return

    document = message["document"]
    filename = document.get("file_name", "quiz.txt")

    if not filename.lower().endswith(".txt"):
        send_message(chat_id, "❌ Please send a .txt quiz file.")
        return

    try:
        path = download_document(document["file_id"], filename)
        questions = parse_quiz_file(path)

        for question in questions:
            send_quiz_poll(question)

        send_message(
            chat_id,
            f"✅ Published {len(questions)} quiz poll(s) to the channel.",
        )
    except Exception as exc:
        send_message(
            chat_id,
            "❌ Quiz file could not be published.\n\n"
            f"Error: {exc}",
        )


def handle_update(update: dict) -> None:
    message = update.get("message")
    if not message:
        return

    if "document" in message:
        handle_document(message)
        return

    sender = message.get("from", {})
    if str(sender.get("id")) == ADMIN_USER_ID:
        send_message(
            message["chat"]["id"],
            "📄 Send me a .txt file containing your quiz questions.",
        )


def main() -> None:
    state = load_state()
    offset = int(state.get("offset", 0))

    # Ensure polling works if a webhook was previously configured for this bot.
    api("deleteWebhook", json={"drop_pending_updates": False})

    # We use short polling because GitHub Actions is not a permanent server.
    while True:
        data = api(
            "getUpdates",
            json={
                "offset": offset,
                "timeout": 20,
                "allowed_updates": ["message"],
            },
        )

        updates = data.get("result", [])
        for update in updates:
            offset = update["update_id"] + 1
            handle_update(update)
            state["offset"] = offset
            save_state(state)

        if not updates:
            break


if __name__ == "__main__":
    main()
