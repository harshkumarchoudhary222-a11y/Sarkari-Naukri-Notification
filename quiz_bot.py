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

CONFIRM_BUTTON = {
    "inline_keyboard": [
        [
            {"text": "✅ Publish quiz", "callback_data": "confirm_quiz"},
            {"text": "❌ Cancel", "callback_data": "cancel_quiz"},
        ]
    ]
}

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
        return {
            "offset": 0,
            "processed_messages": [],
            "pending_updates": [],
            "pending_quiz": None,
        }

    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    state.setdefault("processed_messages", [])
    state.setdefault("pending_updates", [])
    state.setdefault("pending_quiz", None)
    return state


def save_state(state: dict) -> None:
    state["processed_messages"] = state.get("processed_messages", [])[-200:]
    state["pending_updates"] = state.get("pending_updates", [])[-50:]
    STATE_FILE.write_text(
        json.dumps(state, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def send_message(
    chat_id: int | str,
    text: str,
    with_stop_button: bool = True,
    reply_markup: dict | None = None,
) -> None:
    payload = {"chat_id": chat_id, "text": text}
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


def publish_pending_quiz(state: dict) -> bool:
    pending = state.get("pending_quiz")
    if not pending:
        return False

    chat_id = pending["chat_id"]
    key = pending["message_key"]
    filename = pending["filename"]
    file_id = pending["file_id"]

    try:
        path = download_document(file_id, filename)
        questions = parse_quiz_file(path)

        send_message(
            chat_id,
            f"⏳ Publishing {len(questions)} quiz poll(s)...",
        )

        for index, question in enumerate(questions, start=1):
            send_quiz_poll(question)

            stopped, _ = check_for_stop(state)
            if stopped:
                state["processed_messages"].append(key)
                state["pending_quiz"] = None
                save_state(state)
                send_message(
                    chat_id,
                    f"🛑 Publishing stopped after {index} of {len(questions)} question(s).\n\n"
                    "This upload will not resume automatically. Send a new file when you are ready.",
                    with_stop_button=False,
                )
                return True

        state["processed_messages"].append(key)
        state["pending_quiz"] = None
        save_state(state)

        send_message(
            chat_id,
            f"✅ Published {len(questions)} quiz poll(s) to the channel.\n\n"
            "The bot session has finished automatically.",
            with_stop_button=False,
        )
    except Exception as exc:
        state["pending_quiz"] = None
        save_state(state)
        send_message(
            chat_id,
            "❌ Quiz file could not be published.\n\n"
            f"Error: {exc}",
            with_stop_button=False,
        )

    return True


def handle_document(message: dict, state: dict) -> bool:
    sender = message.get("from", {})
    chat_id = message["chat"]["id"]
    key = message_key(message)

    if key in state["processed_messages"]:
        print(f"Skipping already processed message: {key}")
        return False

    if str(sender.get("id")) != ADMIN_USER_ID:
        send_message(chat_id, "⛔ This bot is private.", with_stop_button=False)
        return False

    document = message["document"]
    filename = document.get("file_name", "quiz.txt")

    if not filename.lower().endswith(".txt"):
        send_message(chat_id, "❌ Please send a .txt quiz file.", with_stop_button=False)
        return False

    if state.get("pending_quiz"):
        old_pending = state["pending_quiz"]
        old_key = old_pending.get("message_key")

        # If an earlier scheduled runner left a stale confirmation behind,
        # allow the newest upload from the authorized admin to replace it.
        if old_key != key:
            state["processed_messages"].append(old_key)
            state["pending_quiz"] = None
            save_state(state)
            send_message(
                chat_id,
                "♻️ Previous pending quiz replaced with the new file.",
                with_stop_button=False,
            )

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
        with_stop_button=False,
        reply_markup=CONFIRM_BUTTON,
    )
    return False


def handle_update(update: dict, state: dict) -> bool:
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

        action = callback.get("data")

        if action == "confirm_quiz":
            api(
                "answerCallbackQuery",
                json={
                    "callback_query_id": callback_id,
                    "text": "Publishing quiz...",
                },
            )
            return publish_pending_quiz(state)

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
                send_message(
                    chat_id,
                    "❌ Quiz cancelled. The file was not published.",
                    with_stop_button=False,
                )
            return False

        if action == "stop_bot":
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
        return handle_document(message, state)

    sender = message.get("from", {})
    if str(sender.get("id")) == ADMIN_USER_ID:
        text = str(message.get("text", "")).strip()

        if text.lower().split()[0] == "/start" if text else False:
            send_message(
                message["chat"]["id"],
                "👋 Welcome to your Telegram Quiz Bot!\n\n"
                "📄 Send me a .txt file containing your quiz questions.\n"
                "✅ I will ask for confirmation before publishing.\n"
                "🛑 You can stop a running quiz with the Stop button.\n\n"
                "Send /start anytime to see these instructions again.",
                with_stop_button=False,
            )
        else:
            send_message(
                message["chat"]["id"],
                "📄 Send me a .txt file containing your quiz questions.\n\n"
                "You will get a confirmation button before anything is published.",
            )
    return False


def check_for_stop(state: dict) -> tuple[bool, int | None]:
    """
    Check Telegram between quiz polls so the Stop button can interrupt
    a running batch. Non-callback updates are queued for the next session
    instead of being discarded.
    """
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
    if not updates:
        return False, offset

    stopped = False

    for update in updates:
        offset = max(offset, update["update_id"] + 1)

        callback = update.get("callback_query")
        if callback and callback.get("data") == "stop_bot":
            sender = callback.get("from", {})
            if str(sender.get("id")) == ADMIN_USER_ID:
                api(
                    "answerCallbackQuery",
                    json={
                        "callback_query_id": callback.get("id"),
                        "text": "Stopping after the current question...",
                    },
                )
                stopped = True
                continue

        state["pending_updates"].append(update)

    state["offset"] = offset
    save_state(state)
    return stopped, offset


def main() -> None:
    state = load_state()
    offset = int(state.get("offset", 0))

    api("deleteWebhook", json={"drop_pending_updates": False})

    pending = state.get("pending_updates", [])
    state["pending_updates"] = []
    save_state(state)

    for update in pending:
        offset = max(offset, update["update_id"] + 1)
        state["offset"] = offset
        save_state(state)

        if handle_update(update, state):
            return

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

            if handle_update(update, state):
                return

        if not updates:
            continue


if __name__ == "__main__":
    main()
