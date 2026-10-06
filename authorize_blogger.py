import json
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow


SCOPES = ["https://www.googleapis.com/auth/blogger"]
CLIENT_FILE = Path("client_secret.json")
TOKEN_FILE = Path("blogger_token.json")


def main():
    if not CLIENT_FILE.exists():
        raise SystemExit(
            "Missing client_secret.json. Download your OAuth Desktop App JSON "
            "from Google Cloud and place it beside this script."
        )

    flow = InstalledAppFlow.from_client_secrets_file(
        str(CLIENT_FILE),
        SCOPES,
    )

    credentials = flow.run_local_server(
        port=0,
        access_type="offline",
        prompt="consent",
    )

    TOKEN_FILE.write_text(
        credentials.to_json(),
        encoding="utf-8",
    )

    print()
    print("Blogger authorization successful.")
    print(f"Token saved to: {TOKEN_FILE.resolve()}")
    print()
    print("IMPORTANT: Keep blogger_token.json private.")
    print("Do NOT upload it to GitHub.")
    print("Use its complete contents as the GitHub secret BLOGGER_TOKEN_JSON.")


if __name__ == "__main__":
    main()
