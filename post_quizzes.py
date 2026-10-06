from __future__ import annotations

import json
from pathlib import Path

from quiz_parser import parse_quiz_file
from quiz_sender import send_quiz_poll


INBOX = Path("quizzes/inbox")
STATE_FILE = Path("quizzes/posted.json")


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"files": {}}
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    STATE_FILE.write_text(
        json.dumps(state, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    state = load_state()
    posted = state.setdefault("files", {})

    files = sorted(INBOX.glob("*.txt"))
    if not files:
        print("No quiz TXT files found.")
        return

    for path in files:
        key = str(path.as_posix())
        if key in posted:
            continue

        print(f"Processing {key}")
        questions = parse_quiz_file(path)

        for index, question in enumerate(questions, start=1):
            print(f"Posting question {index}/{len(questions)}")
            result = send_quiz_poll(question)
            print(f"Posted Telegram poll {result.get('message_id')}")

        posted[key] = {
            "questions": len(questions),
            "posted_at": __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ).isoformat(),
        }
        save_state(state)


if __name__ == "__main__":
    main()
