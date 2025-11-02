#!/usr/bin/env python3

import json
import os
import sys
import time
from typing import List, Dict, Any

try:
    import requests
except Exception:
    print("[-] Missing 'requests' module. Install with: pip3 install requests")
    sys.exit(1)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
MESSAGE_THREAD_ID = os.environ.get("MESSAGE_THREAD_ID")
COMMIT_URL = os.environ.get("COMMIT_URL")
COMMIT_MESSAGE = os.environ.get("COMMIT_MESSAGE")
RUN_URL = os.environ.get("RUN_URL")
TITLE = os.environ.get("TITLE")
VERSION = os.environ.get("VERSION")

BOT_API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

MSG_TEMPLATE = (
    "**{title}**\n"
    "#ci_{version}\n"
    "```\n{commit_message}\n```\n"
    "[Commit]({commit_url})\n"
    "[Workflow run]({run_url})"
)

CAPTION_MAX = 1024


def _fail(msg: str) -> None:
    print(f"[-] {msg}")
    sys.exit(1)


def build_caption() -> str:
    msg = MSG_TEMPLATE.format(
        title=TITLE or "",
        version=VERSION or "",
        commit_message=COMMIT_MESSAGE or "",
        commit_url=COMMIT_URL or "",
        run_url=RUN_URL or "",
    ).strip()
    if len(msg) > CAPTION_MAX:
        return COMMIT_URL or ""
    return msg


def validate_env() -> Dict[str, Any]:
    if not BOT_TOKEN:
        _fail("Missing BOT_TOKEN")
    if not CHAT_ID:
        _fail("Missing CHAT_ID")
    for k, v in {
        "TITLE": TITLE,
        "VERSION": VERSION,
        "COMMIT_MESSAGE": COMMIT_MESSAGE,
        "COMMIT_URL": COMMIT_URL,
        "RUN_URL": RUN_URL,
    }.items():
        if not v:
            _fail(f"Missing {k}")

    chat: Any = CHAT_ID
    if CHAT_ID.lstrip("-").isdigit():
        chat = int(CHAT_ID)

    thread_id: Any = None
    if MESSAGE_THREAD_ID and MESSAGE_THREAD_ID.isdigit():
        thread_id = int(MESSAGE_THREAD_ID)

    return {"chat_id": chat, "message_thread_id": thread_id}


def post(method: str, data: Dict[str, Any], files: Dict[str, Any] = None) -> dict:
    url = f"{BOT_API_BASE}/{method}"
    try:
        resp = requests.post(url, data=data, files=files, timeout=120)
    except requests.RequestException as e:
        _fail(f"HTTP error calling {method}: {e}")
    if resp.status_code != 200:
        _fail(f"Telegram API HTTP {resp.status_code}: {resp.text[:500]}")
    try:
        js = resp.json()
    except ValueError:
        _fail(f"Non-JSON response from Telegram: {resp.text[:500]}")
    if not js.get("ok"):
        _fail(f"Telegram API error: {js}")
    return js


def send_single(chat_id: Any, message_thread_id: Any, file_path: str, caption: str) -> None:
    data = {
        "chat_id": chat_id,
        "parse_mode": "Markdown",
        "caption": caption,
        "disable_notification": True,
    }
    if message_thread_id:
        data["message_thread_id"] = message_thread_id

    with open(file_path, "rb") as f:
        files = {"document": (os.path.basename(file_path), f)}
        print(f"[+] sendDocument: {file_path}")
        post("sendDocument", data, files)


def send_group(chat_id: Any, message_thread_id: Any, file_paths: List[str], last_caption: str) -> None:
    media = []
    files = {}
    for idx, p in enumerate(file_paths):
        attach_name = f"file{idx}"
        entry = {
            "type": "document",
            "media": f"attach://{attach_name}",
        }
        if idx == len(file_paths) - 1:
            entry["caption"] = last_caption
            entry["parse_mode"] = "Markdown"
        media.append(entry)
        files[attach_name] = (os.path.basename(p), open(p, "rb"))

    data = {
        "chat_id": chat_id,
        "media": json.dumps(media),
        "disable_notification": True,
    }
    if message_thread_id:
        data["message_thread_id"] = message_thread_id

    print(f"[+] sendMediaGroup: {len(file_paths)} files")
    try:
        post("sendMediaGroup", data, files)
    finally:
        # tutup semua file descriptor
        for f in files.values():
            try:
                f[1].close()
            except Exception:
                pass


def main():
    print("[+] Starting Telegram upload (Bot API)")
    ctx = validate_env()

    files = [p for p in sys.argv[1:] if p]
    if not files:
        _fail("No files to upload")
    for p in files:
        if not os.path.isfile(p):
            _fail(f"File not found: {p}")

    caption = build_caption()
    print("[+] Chat:", ctx["chat_id"])
    if ctx["message_thread_id"]:
        print("[+] Topic (message_thread_id):", ctx["message_thread_id"])
    print("[+] Files:", files)
    print("[+] Caption (len={}):\n---\n{}\n---".format(len(caption), caption))

    if len(files) == 1:
        send_single(ctx["chat_id"], ctx["message_thread_id"], files[0], caption)
    else:
        BATCH = 10
        for i in range(0, len(files), BATCH):
            batch = files[i : i + BATCH]
            cap = caption if (i + BATCH) >= len(files) else ""
            send_group(ctx["chat_id"], ctx["message_thread_id"], batch, cap)
            time.sleep(0.7)

    print("[+] Done!")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        _fail(f"Unhandled error: {e}")