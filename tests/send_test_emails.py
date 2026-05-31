"""Send test emails to trigger Refund Agent classification (all 4 types)."""

import asyncio
import os
import sys

from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TEST_EMAILS = [
    {
        "subject": "Refund request for Order #5501",
        "body": "Hi, I ordered a tablet last week but it has a cracked screen. I need a full refund. Order #5501. Thanks, David Lin",
    },
    {
        "subject": "Want to return my shoes - Order #5502",
        "body": "Hello, the shoes I ordered are the wrong size. I'd like to return them and get the correct size. Order #5502. - Emily Wu",
    },
    {
        "subject": "Very disappointed with your service",
        "body": "I am extremely disappointed with how my complaint was handled. Nobody responded to my emails for over a week. This is terrible and unacceptable service. I expect better. - Frank Huang",
    },
    {
        "subject": "Win a free vacation! Limited time offer",
        "body": "Congratulations! You've been selected for our exclusive vacation giveaway. Click here to claim your prize! This is a limited time offer.",
    },
]


async def main():
    email = os.getenv("USER_GOOGLE_EMAIL", "chun24161582@gmail.com")

    env = {
        "GOOGLE_OAUTH_CLIENT_ID": os.getenv("GOOGLE_OAUTH_CLIENT_ID", ""),
        "GOOGLE_OAUTH_CLIENT_SECRET": os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", ""),
        "USER_GOOGLE_EMAIL": email,
        "OAUTHLIB_INSECURE_TRANSPORT": os.getenv("OAUTHLIB_INSECURE_TRANSPORT", "1"),
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "APPDATA": os.environ.get("APPDATA", ""),
        "LOCALAPPDATA": os.environ.get("LOCALAPPDATA", ""),
        "USERPROFILE": os.environ.get("USERPROFILE", ""),
    }

    server_params = StdioServerParameters(
        command="uvx",
        args=["workspace-mcp", "--single-user", "--tool-tier", "core",
              "--permissions", "gmail:send"],
        env=env,
    )

    print(f"[*] Sending {len(TEST_EMAILS)} test emails to {email}...")
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            for i, mail in enumerate(TEST_EMAILS, 1):
                print(f"  [{i}/{len(TEST_EMAILS)}] Sending: {mail['subject']}")
                result = await session.call_tool("send_gmail_message", {
                    "to": email,
                    "subject": mail["subject"],
                    "body": mail["body"],
                })
                for item in result.content:
                    text = item.text if hasattr(item, "text") else str(item)
                    if "error" in text.lower():
                        print(f"    [ERROR] {text[:200]}")
                    else:
                        print(f"    [OK] Sent")

    print(f"\n[DONE] {len(TEST_EMAILS)} test emails sent. Now run: python refund_agent.py auto")


if __name__ == "__main__":
    asyncio.run(main())
