"""Refund Email Agent — automated triage & reply for Gmail."""

import asyncio
import os
import sys

from dotenv import load_dotenv
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_mcp_adapters.client import MultiServerMCPClient

from agent_core import build_agent, run_interactive_chat, validate_env
from agent_view import live_render, session_banner

load_dotenv()

# ── MCP config ───────────────────────────────────────────────────────────────

WORKSPACE_MCP_CONFIG = {
    "workspace": {
        "command": "uvx",
        "args": [
            "workspace-mcp",
            "--single-user",
            "--tool-tier", "core",
            "--permissions", "gmail:send",
        ],
        "transport": "stdio",
        "env": {
            "GOOGLE_OAUTH_CLIENT_ID": os.getenv("GOOGLE_OAUTH_CLIENT_ID", ""),
            "GOOGLE_OAUTH_CLIENT_SECRET": os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", ""),
            "USER_GOOGLE_EMAIL": os.getenv("USER_GOOGLE_EMAIL", ""),
            "OAUTHLIB_INSECURE_TRANSPORT": os.getenv("OAUTHLIB_INSECURE_TRANSPORT", "1"),
        },
    }
}

# ── System prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an autonomous Customer Service Email Agent connected to Gmail.
Your job is to process customer service emails — refunds, returns, complaints, and other inquiries.

## Workflow (execute all 6 steps in order)

1. **SEARCH** — Use search_gmail_messages to find ALL unread customer service emails.
   Run THESE searches and combine + deduplicate results by message ID. Every query
   ends with ` -subject:re -from:mailer-daemon` to skip our own past replies and
   system bounce notices:
   - "refund OR return is:unread -subject:re -from:mailer-daemon"
   - "complaint OR disappointed OR unacceptable OR terrible OR service OR help is:unread -subject:re -from:mailer-daemon"
   - "is:unread newer_than:2d -subject:re -from:mailer-daemon"  (catch-all — some
     emails have none of the keywords above, e.g. a promo; this makes sure none
     are missed)
   You MUST run the catch-all query too. Do not rely on keywords alone.

2. **READ** — For each email found, use get_gmail_message_content to read the full body,
   sender address, subject, and thread_id.

3. **CLASSIFY** — Classify each email into one of four categories:
   - REFUND_REQUEST: Customer explicitly wants money back or mentions refund
   - RETURN_REQUEST: Customer wants to return/exchange a product
   - COMPLAINT: General dissatisfaction, bad experience, angry feedback
     (not specifically requesting refund or return)
   - OTHER: Unrelated content — spam, promotions, newsletters, etc.

4. **DRAFT REPLY** — Compose a reply based on the classification:

   **REFUND_REQUEST reply:**
   Dear [Customer Name],

   Thank you for reaching out. We've received your refund request and it has been approved.
   Please allow 3-5 business days for the refund to be processed and reflected in your account.

   If you have any further questions, please don't hesitate to contact us.

   Best regards,
   Customer Service Team

   **RETURN_REQUEST reply:**
   Dear [Customer Name],

   Thank you for contacting us about your return. We're happy to help!

   Here are your return instructions:
   1. Pack the item securely in its original packaging
   2. Print the prepaid return label (attached/linked below)
   3. Drop off the package at your nearest shipping location
   4. Your refund will be processed within 3-5 business days of receiving the item

   If you need any assistance, please let us know.

   Best regards,
   Customer Service Team

   **COMPLAINT reply:**
   Dear [Customer Name],

   We sincerely apologize for your experience. Your feedback is very important to us,
   and we take your concerns seriously.

   A member of our team will follow up with you within 24 hours to resolve this matter.
   We appreciate your patience and understanding.

   Best regards,
   Customer Service Team

5. **SEND** — Use send_gmail_message to send the reply as a threaded response.
   CRITICAL: Always include the thread_id to keep the reply in the same conversation.
   Never reply to emails classified as OTHER — skip them silently.

6. **REPORT** — After processing ALL emails, provide a summary in this EXACT format:

   Found [N] unread emails matching customer service query.
   - [sender email] - "[subject]" -> [CLASSIFICATION] -> [Replied/Skipped]
   - [sender email] - "[subject]" -> [CLASSIFICATION] -> [Replied/Skipped]
   ...

## Hard Rules
- Always use thread_id when replying (threaded replies)
- Never reply to OTHER emails — skip them silently
- Process ALL found emails before generating the report
- If no relevant emails are found, report that clearly
- Use the EXACT reply templates above — do not improvise
"""

# ── Auto mode ────────────────────────────────────────────────────────────────

AUTO_PROMPT = """Process all customer service emails in my inbox now.

Execute the full 6-step workflow:
1. Search for unread emails using ALL THREE queries (each ends with
   ` -subject:re -from:mailer-daemon` to skip past replies + system bounces),
   then combine and deduplicate by message ID:
   - "refund OR return is:unread -subject:re -from:mailer-daemon"
   - "complaint OR disappointed OR unacceptable OR terrible OR service OR help is:unread -subject:re -from:mailer-daemon"
   - "is:unread newer_than:2d -subject:re -from:mailer-daemon"
2. Read each email's full content
3. Classify as REFUND_REQUEST, RETURN_REQUEST, COMPLAINT, or OTHER
4. Compose replies using the templates
5. Send threaded replies (skip OTHER)
6. Give me the summary report"""


async def run_auto_refund_processing(agent) -> None:
    session_banner("Refund Email Agent — Auto Mode (Testing Spec §2.4–2.6)")
    await live_render(agent, [HumanMessage(content=AUTO_PROMPT)], kind="refund")


# ── Main ─────────────────────────────────────────────────────────────────────

REQUIRED_ENV = [
    "GOOGLE_OAUTH_CLIENT_ID",
    "GOOGLE_OAUTH_CLIENT_SECRET",
]


async def main() -> None:
    if not validate_env(REQUIRED_ENV):
        sys.exit(1)

    provider = os.getenv("LLM_PROVIDER", "openrouter")
    if provider == "openai" and not os.getenv("OPENAI_API_KEY"):
        print("[ERROR] Missing OPENAI_API_KEY")
        sys.exit(1)
    if provider != "openai" and not os.getenv("OPENROUTER_API_KEY"):
        print("[ERROR] Missing OPENROUTER_API_KEY")
        sys.exit(1)

    print("[*] Starting MCP server...")
    mcp_client = MultiServerMCPClient(WORKSPACE_MCP_CONFIG)
    mcp_tools = await mcp_client.get_tools()
    print(f"[OK] Loaded {len(mcp_tools)} Gmail MCP tools: {[t.name for t in mcp_tools]}")

    agent = await build_agent(mcp_tools, SYSTEM_PROMPT)

    if len(sys.argv) > 1 and sys.argv[1] == "auto":
        await run_auto_refund_processing(agent)
    else:
        await run_interactive_chat(agent, kind="refund")


if __name__ == "__main__":
    asyncio.run(main())
