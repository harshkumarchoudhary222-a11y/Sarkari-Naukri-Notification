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

STATE_FILE = Path(os.getenv("QUIZ_STATE_FILE", "quizzes/bot_state.json"))
DOWNLOAD_DIR = Path(os.getenv("QUIZ_DOWNLOAD_DIR", "quizzes/runtime"))
STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

CONFIRM_BUTTON = {
    "inline_keyboard": [[
        {"text": "✅ Publish quiz", "callback_data": "confirm_quiz"},
        {"text": "❌ Cancel", "callback_data": "cancel_quiz"},
    ]]
}

STOP_BUTTON = {
    "inline_keyboard": [[
        {"text": "🛑 Stop publishing", "callback_data": "stop_bot"}
    ]]
}

CROSS_PROMOTION = (
    "📢 <b>Also Follow Our Sarkari Naukri Channel</b>\n\n"
    "💼 <b>Latest Government Job Notifications</b>\n"
    "🔔 New vacancies • Exam updates • Important dates\n\n"
    "👉 Join: @sarkari_naukri_notification"
)


def api(method: str, **kwargs) -> dict:
    response = requests.post(f"{API}/{method}", timeout=60, **kwargs)
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error: {data}")
    return data


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {
            "offset": 0,
            "processed_messages": [],
            "pending_quiz": None,
        }

    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        state = {}

    state.setdefault("offset", 0)
    state.setdefault("processed_messages", [])
    state.setdefault("pending_quiz", None)
    return state


def save_state(state: dict) -> None:
    state["processed_messages"] = state.get("processed_messages", [])[-500:]
    STATE_FILE.write_text(
        json.dumps(state, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def send_message(
    chat_id: int | str,
    text: str,
    with_stop_button: bool = False,
    reply_markup: dict | None = None,
) -> None:
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    elif with_stop_button:
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


def message_key(message: dict) -> str:
    return f"{message.get('chat', {}).get('id')}:{message.get('message_id')}"


def publish_pending_quiz(state: dict) -> None:
    pending = state.get("pending_quiz")
    if not pending:
        return

    chat_id = pending["chat_id"]
    key = pending["message_key"]
    filename = pending["filename"]
    file_id = pending["file_id"]

    try:
        path = download_document(file_id, filename)
        questions = parse_quiz_file(path)

        send_message(
            chat_id,
            f"⏳ Publishing {len(questions)} quiz poll(s) to {CHANNEL_ID}...",
            with_stop_button=True,
        )

        for index, question in enumerate(questions, start=1):
            send_quiz_poll(question)

            stopped = check_for_stop(state)
            if stopped:
                state["processed_messages"].append(key)
                state["pending_quiz"] = None
                save_state(state)
                send_message(
                    chat_id,
                    f"🛑 Publishing stopped after {index} of {len(questions)} question(s).\n\n"
                    "The bot is still online. Send another .txt file whenever you are ready.",
                )
                return

        # Cross-promote the main Sarkari Naukri channel after every completed quiz.
        send_message(CHANNEL_ID, CROSS_PROMOTION)

        state["processed_messages"].append(key)
        state["pending_quiz"] = None
        save_state(state)

        send_message(
            chat_id,
            f"✅ Published {len(questions)} quiz poll(s) to {CHANNEL_ID}.\n\n"
            "The bot is still online and ready for the next .txt file.",
        )
    except Exception as exc:
        state["pending_quiz"] = None
        save_state(state)
        send_message(
            chat_id,
            "❌ Quiz file could not be published.\n\n"
            f"Error: {exc}",
        )


def handle_document(message: dict, state: dict) -> None:
    sender = message.get("from", {})
    chat_id = message["chat"]["id"]
    key = message_key(message)

    if key in state["processed_messages"]:
        return

    if str(sender.get("id")) != ADMIN_USER_ID:
        send_message(chat_id, "⛔ This bot is private.")
        return

    document = message["document"]
    filename = document.get("file_name", "quiz.txt")

    if not filename.lower().endswith(".txt"):
        send_message(chat_id, "❌ Please send a .txt quiz file.")
        return

    state["pending_quiz"] = {
        "message_key": key,
        "chat_id": chat_id,
        "file_id": document["file_id"],
        "filename": filename,
    }
    save_state(state)

    send_message(
        chat_id,
        f"📄 Received: {filename}\n\n"
        "Do you want me to publish this quiz to the channel?",
        reply_markup=CONFIRM_BUTTON,
    )


def handle_update(update: dict, state: dict) -> None:
    callback = update.get("callback_query")

    if callback:
        sender = callback.get("from", {})
        callback_id = callback.get("id")
        action = callback.get("data")

        if str(sender.get("id")) != ADMIN_USER_ID:
            api(
                "answerCallbackQuery",
                json={
                    "callback_query_id": callback_id,
                    "text": "⛔ This bot is private.",
                    "show_alert": True,
                },
            )
            return

        if action == "confirm_quiz":
            api(
                "answerCallbackQuery",
                json={
                    "callback_query_id": callback_id,
                    "text": "Publishing quiz...",
                },
            )
            publish_pending_quiz(state)
            process_pending_updates(state)
            return

        if action == "cancel_quiz":
            api(
                "answerCallbackQuery",
                json={
                    "callback_query_id": callback_id,
                    "text": "Quiz cancelled.",
                },
            )
            pending = state.get("pending_quiz")
            if pending:
                chat_id = pending["chat_id"]
                state["processed_messages"].append(pending["message_key"])
                state["pending_quiz"] = None
                save_state(state)
                send_message(chat_id, "❌ Quiz cancelled. The file was not published.")
            return

        if action == "stop_bot":
            api(
                "answerCallbackQuery",
                json={
                    "callback_query_id": callback_id,
                    "text": "Stopping after the current question...",
                },
            )
            return

        return

    message = update.get("message")
    if not message:
        return

    sender = message.get("from", {})
    if str(sender.get("id")) != ADMIN_USER_ID:
        return

    if "document" in message:
        handle_document(message, state)
        return

    text = str(message.get("text", "")).strip()
    if text.lower().split()[0] == "/start" if text else False:
        send_message(
            message["chat"]["id"],
            "👋 Welcome to your Telegram Quiz Bot!\n\n"
            "📄 Send me a .txt file containing your quiz questions.\n"
            "✅ I will ask for confirmation before publishing.\n"
            "🛑 You can stop a running quiz without taking the bot offline.\n\n"
            "The bot is now continuously online.",
        )
    else:
        send_message(
            message["chat"]["id"],
            "📄 Send me a .txt file containing your quiz questions.\n\n"
            "You will get a confirmation button before anything is published.",
        )


def check_for_stop(state: dict) -> bool:
    offset = int(state.get("offset", 0))

    data = api(
        "getUpdates",
        json={
            "offset": offset,
            "timeout": 0,
            "allowed_updates": ["message", "callback_query"],
        },
    )

    updates = data.get("result", [])
    stopped = False

    for update in updates:
        state["offset"] = max(state["offset"], update["update_id"] + 1)

        callback = update.get("callback_query")
        if callback and callback.get("data") == "stop_bot":
            sender = callback.get("from", {})
            if str(sender.get("id")) == ADMIN_USER_ID:
                stopped = True
                continue

        state.setdefault("pending_updates", []).append(update)

    state["pending_updates"] = state.get("pending_updates", [])[-100:]
    save_state(state)
    return stopped


def process_pending_updates(state: dict) -> None:
    pending = state.get("pending_updates", [])
    state["pending_updates"] = []
    save_state(state)

    for update in pending:
        handle_update(update, state)


def run_forever() -> None:
    state = load_state()

    api("deleteWebhook", json={"drop_pending_updates": False})

    process_pending_updates(state)

    print("Telegram Quiz Bot is online and waiting for .txt files.")

    while True:
        try:
            offset = int(state.get("offset", 0))

            data = api(
                "getUpdates",
                json={
                    "offset": offset,
                    "timeout": 25,
                    "allowed_updates": ["message", "callback_query"],
                },
            )

            updates = data.get("result", [])

            for update in updates:
                state["offset"] = update["update_id"] + 1
                save_state(state)
                handle_update(update, state)

        except KeyboardInterrupt:
            print("Telegram Quiz Bot stopped.")
            raise
        except Exception as exc:
            print(f"Telegram polling error: {exc}")
            time.sleep(5)


if __name__ == "__main__":
    run_forever()
