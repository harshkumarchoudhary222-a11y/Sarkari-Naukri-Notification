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

STOP_BUTTON = {
    "inline_keyboard": [
        [{"text": "🛑 Stop bot", "callback_data": "stop_bot"}]
    ]
}


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


def send_message(chat_id: int | str, text: str, with_stop_button: bool = True) -> None:
    payload = {"chat_id": chat_id, "text": text}
    if with_stop_button:
        payload["reply_markup"] = STOP_BUTTON
    api("sendMessage", json=payload)


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


def handle_document(message: dict) -> bool:
    sender = message.get("from", {})
    chat_id = message["chat"]["id"]

    if str(sender.get("id")) != ADMIN_USER_ID:
        send_message(chat_id, "⛔ This bot is private.", with_stop_button=False)
        return False

    document = message["document"]
    filename = document.get("file_name", "quiz.txt")

    if not filename.lower().endswith(".txt"):
        send_message(chat_id, "❌ Please send a .txt quiz file.")
        return False

    try:
        path = download_document(document["file_id"], filename)
        questions = parse_quiz_file(path)

        send_message(
            chat_id,
            f"⏳ Publishing {len(questions)} quiz poll(s)...",
        )

        for question in questions:
            send_quiz_poll(question)

        send_message(
            chat_id,
            f"✅ Published {len(questions)} quiz poll(s) to the channel.\n\n"
            "The bot session has finished automatically.",
        )
    except Exception as exc:
        send_message(
            chat_id,
            "❌ Quiz file could not be published.\n\n"
            f"Error: {exc}",
        )

    # A quiz upload completes the current polling session. The next scheduled
    # GitHub Actions run will wait for the next file.
    return True


def handle_update(update: dict) -> bool:
    callback = update.get("callback_query")
    if callback:
        sender = callback.get("from", {})
        callback_id = callback.get("id")

        if str(sender.get("id")) != ADMIN_USER_ID:
            api(
                "answerCallbackQuery",
                json={
                    "callback_query_id": callback_id,
                    "text": "⛔ This bot is private.",
                    "show_alert": True,
                },
            )
            return False

        if callback.get("data") == "stop_bot":
            api(
                "answerCallbackQuery",
                json={
                    "callback_query_id": callback_id,
                    "text": "Bot session stopped.",
                },
            )
            chat_id = callback.get("message", {}).get("chat", {}).get("id")
            if chat_id is not None:
                send_message(
                    chat_id,
                    "🛑 Bot session stopped.\n\n"
                    "The next scheduled GitHub Actions run will start a fresh session.",
                    with_stop_button=False,
                )
            return True

        return False

    message = update.get("message")
    if not message:
        return False

    if "document" in message:
        return handle_document(message)

    sender = message.get("from", {})
    if str(sender.get("id")) == ADMIN_USER_ID:
        send_message(
            message["chat"]["id"],
            "📄 Send me a .txt file containing your quiz questions.\n\n"
            "Use the button below if you want to stop this bot session.",
        )
    return False


def main() -> None:
    state = load_state()
    offset = int(state.get("offset", 0))

    # Ensure polling works if a webhook was previously configured for this bot.
    api("deleteWebhook", json={"drop_pending_updates": False})

    # Poll during the current GitHub Actions window. If a quiz is received,
    # handle_document returns True and the workflow exits cleanly immediately.
    deadline = time.time() + 280
    while time.time() < deadline:
        data = api(
            "getUpdates",
            json={
                "offset": offset,
                "timeout": 20,
                "allowed_updates": ["message", "callback_query"],
            },
        )

        updates = data.get("result", [])
        print(f"Telegram polling: received {len(updates)} update(s)")

        for update in updates:
            offset = update["update_id"] + 1
            state["offset"] = offset
            save_state(state)

            should_exit = handle_update(update)
            if should_exit:
                return

        if not updates:
            continue


if __name__ == "__main__":
    main()
