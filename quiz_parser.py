from __future__ import annotations

import re
from pathlib import Path


class QuizFormatError(ValueError):
    pass


def parse_quiz_file(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8-sig")
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Accept Q:, Question 1:, 1., etc. as question starts.
    # The current Q: format remains fully supported.
    blocks = re.split(
        r"(?im)^\s*(?:Q\s*:\s*|QUESTION\s*\d*\s*:\s*|\d+\s*[.)]\s+)",
        text,
    )
    questions = []

    for raw in blocks:
        raw = raw.strip()
        if not raw:
            continue

        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        question = lines[0]
        options = []
        answer = None
        explanation = ""

        for line in lines[1:]:
            # Accept A:, A), (A), A. and similar option markers.
            match = re.match(r"^\(?([A-J])\)?\s*(?:[:.)]|[-])\s*(.+)$", line, re.I)
            if match:
                options.append((match.group(1).upper(), match.group(2).strip()))
                continue

            match = re.match(r"^(?:ANSWER|ANS|CORRECT\s*ANSWER)\s*[:=-]\s*\(?([A-J])\)?\s*$", line, re.I)
            if match:
                answer = match.group(1).upper()
                continue

            match = re.match(r"^EXPLANATION\s*[:=-]\s*(.*)$", line, re.I)
            if match:
                explanation = match.group(1).strip()

        if not question:
            raise QuizFormatError(f"{path}: question text is missing")
        if len(options) < 2:
            raise QuizFormatError(
                f"{path}: question '{question[:80]}' has {len(options)} recognized options; "
                "use A:, B:, C:, D: (or A), B), C), D))."
            )
        if len(options) > 10:
            raise QuizFormatError(f"{path}: Telegram supports at most 10 options")
        labels = [label for label, _ in options]
        if len(labels) != len(set(labels)):
            raise QuizFormatError(f"{path}: duplicate option labels")
        if answer not in labels:
            raise QuizFormatError(
                f"{path}: ANSWER must match one of the option labels: {', '.join(labels)}"
            )

        questions.append(
            {
                "question": question,
                "options": [text for _, text in options],
                "correct_option_id": labels.index(answer),
                "explanation": explanation,
            }
        )

    if not questions:
        raise QuizFormatError(f"{path}: no questions found")
    return questions
