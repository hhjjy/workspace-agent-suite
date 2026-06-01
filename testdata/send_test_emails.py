"""Reset + inject the 8 test customer-service emails from the testing spec
(Testing_project_2.pdf §2.2 / §2.3) into the mailbox the Refund Agent monitors.

Dataset: 2 REFUND_REQUEST + 2 RETURN_REQUEST + 2 COMPLAINT + 2 OTHER.

DEFAULT BEHAVIOUR = CLEAN then INJECT: first trash any leftover test emails
(originals + agent replies) so the inbox doesn't accumulate across runs, then
send 8 fresh ones. Pass --no-clean to skip the cleanup and only send.

Cleanup needs gmail modify scope (to trash). If that scope/tool isn't
available it is skipped with a note — injection still proceeds.

Auth: uses the SAME workspace-mcp OAuth as the agents — run `auth_setup.py`
once (in an environment WITH A BROWSER for the consent screen) and this works;
no SMTP server, no Gmail App Password. Emails are sent from USER_GOOGLE_EMAIL
to itself (self-send).

    python testdata/send_test_emails.py             # clean + inject (default)
    python testdata/send_test_emails.py --no-clean  # send only
"""

import asyncio
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv(ROOT / ".env")

if hasattr(sys.stdout, "reconfigure") and (sys.stdout.encoding or "").lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SEND_DELAY_SECONDS = 0.5  # avoid Gmail throttling

# Testing_project_2.pdf — §2.3 dataset (2 each of the four categories).
EMAILS = [
    {"category": "REFUND_REQUEST", "subject": "Refund Request for Order #1001",
     "body": "Hello,\n\nI would like to request a refund for Order #1001.\n"
             "The product does not meet my expectations.\n\nThank you."},
    {"category": "REFUND_REQUEST", "subject": "Refund Request for Order #1002",
     "body": "Hello,\n\nThe item arrived damaged.\nPlease process a refund.\n\nRegards."},
    {"category": "RETURN_REQUEST", "subject": "Return Request for Wireless Mouse",
     "body": "Hello,\n\nI would like to return my wireless mouse.\n"
             "Please send return instructions.\n\nThanks."},
    {"category": "RETURN_REQUEST", "subject": "Return Request for Keyboard",
     "body": "Hello,\n\nThe keyboard is incompatible with my system.\n"
             "I would like to return it.\n\nThank you."},
    {"category": "COMPLAINT", "subject": "Very Disappointed",
     "body": "Hello,\n\nYour customer service has been extremely disappointing.\n"
             "I expect a response immediately.\n\nRegards."},
    {"category": "COMPLAINT", "subject": "Poor Service Experience",
     "body": "Hello,\n\nI have contacted support multiple times and nobody helped me.\n\nRegards."},
    {"category": "OTHER", "subject": "Special Summer Promotion",
     "body": "Hello,\n\nCheck out our newest products and discounts.\n\nMarketing Team"},
    {"category": "OTHER", "subject": "Question About Refund Policy",
     "body": "Hello,\n\nBefore purchasing, I would like to know your refund policy.\n\nThank you."},
]

SEND_ARGS = ["workspace-mcp", "--single-user", "--tool-tier", "core",
             "--permissions", "gmail:send"]
# Broader scope for the cleanup phase (needs modify to trash). Best-effort.
CLEAN_ARGS = ["workspace-mcp", "--single-user", "--tool-tier", "extended",
              "--permissions", "gmail:full"]


def _mcp_env() -> dict:
    return {
        "GOOGLE_OAUTH_CLIENT_ID": os.getenv("GOOGLE_OAUTH_CLIENT_ID", ""),
        "GOOGLE_OAUTH_CLIENT_SECRET": os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", ""),
        "USER_GOOGLE_EMAIL": os.getenv("USER_GOOGLE_EMAIL", ""),
        "OAUTHLIB_INSECURE_TRANSPORT": os.getenv("OAUTHLIB_INSECURE_TRANSPORT", "1"),
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "APPDATA": os.environ.get("APPDATA", ""),
        "LOCALAPPDATA": os.environ.get("LOCALAPPDATA", ""),
        "USERPROFILE": os.environ.get("USERPROFILE", ""),
    }


def _props(tool) -> dict:
    return (getattr(tool, "inputSchema", None) or {}).get("properties", {}) or {}


def _pick(props: dict, *candidates: str) -> str | None:
    for c in candidates:
        if c in props:
            return c
    return None


def _find(tools, *exact, contains=()):
    by_name = {t.name: t for t in tools}
    for n in exact:
        if n in by_name:
            return by_name[n]
    for t in tools:
        low = t.name.lower()
        if contains and all(c in low for c in contains):
            return t
    return None


def _text(result) -> str:
    return " ".join((i.text if hasattr(i, "text") else str(i)) for i in result.content)


def _extract_ids(search_text: str) -> list[str]:
    import re
    return re.findall(r"Message ID:\s*([A-Za-z0-9]+)", search_text)


async def clean(email: str) -> None:
    """Best-effort: trash leftover test emails (originals + replies)."""
    subjects = {e["subject"] for e in EMAILS}
    server = StdioServerParameters(command="uvx", args=CLEAN_ARGS, env=_mcp_env())
    try:
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = (await session.list_tools()).tools
                search = _find(tools, "search_gmail_messages", contains=("search", "gmail"))
                trash = _find(tools, "trash_gmail_message", contains=("trash",))
                modify = _find(tools, "modify_gmail_message_labels", contains=("modify", "label"))
                if not search or not (trash or modify):
                    print("[clean] skip — no trash/modify tool available "
                          "(gmail scope is send-only). Injecting fresh anyway.")
                    return

                ids: set[str] = set()
                for subj in subjects:
                    q = f'subject:"{subj}" newer_than:14d'
                    args = {"query": q}
                    if "user_google_email" in _props(search) and email:
                        args["user_google_email"] = email
                    ids.update(_extract_ids(_text(await session.call_tool(search.name, args))))

                if not ids:
                    print("[clean] no leftover test emails found.")
                    return

                trashed = 0
                for mid in ids:
                    try:
                        if trash:
                            tp = _props(trash)
                            a = {(_pick(tp, "message_id", "messageId", "id") or "message_id"): mid}
                            if "user_google_email" in tp and email:
                                a["user_google_email"] = email
                            out = _text(await session.call_tool(trash.name, a))
                        else:
                            mp = _props(modify)
                            a = {(_pick(mp, "message_id", "messageId", "id") or "message_id"): mid,
                                 (_pick(mp, "add_label_ids", "add_labels", "labels_to_add") or "add_label_ids"): ["TRASH"]}
                            if "user_google_email" in mp and email:
                                a["user_google_email"] = email
                            out = _text(await session.call_tool(modify.name, a))
                        if "error" not in out.lower()[:60]:
                            trashed += 1
                    except Exception as e:  # noqa: BLE001
                        print(f"[clean] x error trashing {mid}: {e}")
                print(f"[clean] trashed {trashed}/{len(ids)} leftover test email(s).")
    except Exception as e:  # noqa: BLE001 — never let cleanup block injection
        print(f"[clean] skip — cleanup unavailable ({e}). Injecting fresh anyway.")


async def inject(email: str) -> tuple[int, int]:
    server = StdioServerParameters(command="uvx", args=SEND_ARGS, env=_mcp_env())
    sent = failed = 0
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for idx, mail in enumerate(EMAILS, 1):
                try:
                    out = _text(await session.call_tool("send_gmail_message", {
                        "to": email, "subject": mail["subject"], "body": mail["body"],
                    }))
                    if "error" in out.lower()[:60]:
                        print(f"[{idx}/{len(EMAILS)}] x FAILED {mail['category']}: {mail['subject']} — {out[:100]}")
                        failed += 1
                    else:
                        print(f"[{idx}/{len(EMAILS)}] OK Sent {mail['category']}: {mail['subject']}")
                        sent += 1
                except Exception as e:  # noqa: BLE001
                    print(f"[{idx}/{len(EMAILS)}] x ERROR {mail['category']}: {mail['subject']} — {e}")
                    failed += 1
                time.sleep(SEND_DELAY_SECONDS)
    return sent, failed


async def main() -> None:
    email = os.getenv("USER_GOOGLE_EMAIL", "")
    if not email:
        print("[ERROR] Missing USER_GOOGLE_EMAIL in .env (see .env.example).")
        sys.exit(1)

    do_clean = "--no-clean" not in sys.argv
    print(f"[*] Target: {email} (self-send) | clean={do_clean}")
    if do_clean:
        await clean(email)
    sent, failed = await inject(email)

    print(f"\nDone. {sent} sent, {failed} failed.")
    if sent:
        print("Now run:  python refund_agent.py auto")


if __name__ == "__main__":
    asyncio.run(main())
