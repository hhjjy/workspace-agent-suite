"""Send the 8 test customer-service emails from the testing spec
(Testing_project_2.pdf §2.2 / §2.3) to the mailbox the Refund Agent monitors.

Dataset: 2 REFUND_REQUEST + 2 RETURN_REQUEST + 2 COMPLAINT + 2 OTHER.

Auth: uses the SAME workspace-mcp OAuth as the agents — run `auth_setup.py`
once and this works (no SMTP server, no Gmail App Password). Emails are sent
from USER_GOOGLE_EMAIL to itself (self-send), which the Refund Agent then
finds as unread customer-service mail.

    python testdata/send_test_emails.py
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

MCP_ARGS = ["workspace-mcp", "--single-user", "--tool-tier", "core",
            "--permissions", "gmail:send"]


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


async def main() -> None:
    email = os.getenv("USER_GOOGLE_EMAIL", "")
    if not email:
        print("[ERROR] Missing USER_GOOGLE_EMAIL in .env (see .env.example).")
        sys.exit(1)

    server_params = StdioServerParameters(command="uvx", args=MCP_ARGS, env=_mcp_env())

    print(f"[*] Sending {len(EMAILS)} test emails to {email} (self-send) ...")
    sent = failed = 0
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            for idx, mail in enumerate(EMAILS, 1):
                try:
                    result = await session.call_tool("send_gmail_message", {
                        "to": email,
                        "subject": mail["subject"],
                        "body": mail["body"],
                    })
                    text = " ".join(
                        (item.text if hasattr(item, "text") else str(item))
                        for item in result.content
                    )
                    if "error" in text.lower()[:60]:
                        print(f"[{idx}/{len(EMAILS)}] x FAILED {mail['category']}: {mail['subject']} — {text[:120]}")
                        failed += 1
                    else:
                        print(f"[{idx}/{len(EMAILS)}] OK Sent {mail['category']}: {mail['subject']}")
                        sent += 1
                except Exception as e:  # noqa: BLE001 — report and keep going
                    print(f"[{idx}/{len(EMAILS)}] x ERROR {mail['category']}: {mail['subject']} — {e}")
                    failed += 1
                time.sleep(SEND_DELAY_SECONDS)

    print(f"\nDone. {sent} sent, {failed} failed.")
    if sent:
        print("Now run:  python refund_agent.py auto")


if __name__ == "__main__":
    asyncio.run(main())
