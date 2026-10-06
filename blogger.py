import json
import os
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


BLOG_ID = os.getenv("BLOGGER_BLOG_ID", "724475884736848260")
TOKEN_FILE = Path("blogger_token.json")
SCOPES = ["https://www.googleapis.com/auth/blogger"]


def _credentials():
    raw = os.getenv("BLOGGER_TOKEN_JSON", "").strip()

    if raw:
        info = json.loads(raw)
        return Credentials.from_authorized_user_info(info, SCOPES)

    if TOKEN_FILE.exists():
        return Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    raise RuntimeError(
        "Blogger authorization is not configured. Add BLOGGER_TOKEN_JSON to GitHub Secrets."
    )


def _service():
    return build("blogger", "v3", credentials=_credentials(), cache_discovery=False)


def create_draft(title, html_content, labels=None):
    service = _service()

    body = {
        "title": title,
        "content": html_content,
    }

    if labels:
        body["labels"] = labels

    result = (
        service.posts()
        .insert(blogId=BLOG_ID, body=body, isDraft=True)
        .execute()
    )

    print(f"Blogger draft created: {result.get('id')}")
    return result


def update_post(post_id, title, html_content, labels=None, publish=False):
    service = _service()

    body = {
        "id": str(post_id),
        "blog": {"id": BLOG_ID},
        "title": title,
        "content": html_content,
    }

    if labels:
        body["labels"] = labels

    result = (
        service.posts()
        .update(
            blogId=BLOG_ID,
            postId=str(post_id),
            body=body,
            publish=publish,
        )
        .execute()
    )

    print(f"Blogger post updated: {result.get('id')}")
    return result


def publish_post(post_id):
    service = _service()

    result = (
        service.posts()
        .publish(blogId=BLOG_ID, postId=str(post_id))
        .execute()
    )

    print(f"Blogger post published: {result.get('url')}")
    return result


def find_post(query):
    service = _service()

    result = (
        service.posts()
        .search(blogId=BLOG_ID, q=query, fetchBodies=False)
        .execute()
    )

    return result.get("items", [])


if __name__ == "__main__":
    print("Blogger integration module is ready.")
