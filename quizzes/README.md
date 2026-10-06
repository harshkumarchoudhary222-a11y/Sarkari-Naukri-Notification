# Telegram Quiz Channel

Add quiz files to `quizzes/inbox/`. The GitHub Actions workflow will parse each new TXT file and publish each question as a Telegram Quiz Poll.

## Format

```
Q: Question text
A: Option A
B: Option B
C: Option C
D: Option D
ANSWER: B
EXPLANATION: Optional explanation shown after the poll.
```

Rules:
- Each question needs one `Q:`, 2–10 options labelled A, B, C...
- `ANSWER:` must point to one option.
- `EXPLANATION:` is optional.
- One TXT file may contain multiple questions.
- Keep files in `quizzes/inbox/`.
- The workflow records posted files in `quizzes/posted.json` to prevent duplicates.
