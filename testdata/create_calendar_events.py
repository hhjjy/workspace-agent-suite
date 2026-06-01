"""Inject the test calendar events from the testing spec (Testing_project_2.pdf
§1.2, Table 1) into the user's Google Calendar.

Auth: uses the SAME workspace-mcp OAuth as the agents — run `auth_setup.py`
once and this works (no token.json, no extra setup). It starts the MCP server,
finds the create-event tool, and adapts to whatever parameter names that tool
exposes, so it stays robust across workspace-mcp versions.

    python testdata/create_calendar_events.py
"""

import asyncio
import os
import sys
from pathlib import Path

# Allow running from anywhere; load the project .env.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv(ROOT / ".env")

if hasattr(sys.stdout, "reconfigure") and (sys.stdout.encoding or "").lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TIMEZONE = "Asia/Taipei"
TZ_OFFSET = "+08:00"

# Testing_project_2.pdf — Table 1: Existing Calendar Events (verbatim).
EVENTS = [
    {"summary": "Team Standup",                   "start": "2026-06-01T09:00:00", "end": "2026-06-01T10:00:00"},
    {"summary": "Research Meeting",               "start": "2026-06-01T14:00:00", "end": "2026-06-01T15:00:00"},
    {"summary": "Project Review",                 "start": "2026-06-02T10:00:00", "end": "2026-06-02T11:00:00"},
    {"summary": "Student Advising",               "start": "2026-06-02T15:00:00", "end": "2026-06-02T16:00:00"},
    {"summary": "Faculty Meeting",                "start": "2026-06-03T09:00:00", "end": "2026-06-03T10:30:00"},
    {"summary": "PhD Progress Review",            "start": "2026-06-03T14:00:00", "end": "2026-06-03T15:00:00"},
    {"summary": "Industry Collaboration Meeting", "start": "2026-06-04T11:00:00", "end": "2026-06-04T12:00:00"},
    {"summary": "Lab Weekly Meeting",             "start": "2026-06-04T15:00:00", "end": "2026-06-04T16:00:00"},
    {"summary": "Grant Proposal Discussion",      "start": "2026-06-05T09:00:00", "end": "2026-06-05T10:00:00"},
    {"summary": "Research Seminar",               "start": "2026-06-05T15:00:00", "end": "2026-06-05T16:00:00"},
]

MCP_ARGS = ["workspace-mcp", "--single-user", "--tool-tier", "extended",
            "--permissions", "calendar:full"]


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


def _pick(props: dict, *candidates: str) -> str | None:
    """Return the first candidate key that exists in the tool's schema."""
    for c in candidates:
        if c in props:
            return c
    return None


def _find_create_tool(tools) -> object:
    """Locate the calendar create-event tool, tolerating naming differences."""
    by_name = {t.name: t for t in tools}
    for exact in ("create_event", "create_calendar_event", "manage_event"):
        if exact in by_name:
            return by_name[exact]
    for t in tools:
        n = t.name.lower()
        if "event" in n and ("create" in n or "add" in n or "insert" in n):
            return t
    raise RuntimeError(
        f"No create-event tool found. Available: {[t.name for t in tools]}"
    )


def _build_args(tool, event: dict, email: str) -> dict:
    props = (getattr(tool, "inputSchema", None) or {}).get("properties", {}) or {}

    summary_k = _pick(props, "summary", "title") or "summary"
    start_k = _pick(props, "start_time", "start", "startTime", "start_datetime") or "start_time"
    end_k = _pick(props, "end_time", "end", "endTime", "end_datetime") or "end_time"
    tz_k = _pick(props, "timezone", "time_zone", "tz")
    cal_k = _pick(props, "calendar_id", "calendarId")

    # If the tool takes a separate timezone field, send naive local times; else
    # bake the +08:00 offset into the timestamp.
    if tz_k:
        start_v, end_v = event["start"], event["end"]
    else:
        start_v, end_v = event["start"] + TZ_OFFSET, event["end"] + TZ_OFFSET

    args = {summary_k: event["summary"], start_k: start_v, end_k: end_v}
    if tz_k:
        args[tz_k] = TIMEZONE
    if cal_k:
        args[cal_k] = "primary"
    # manage_event variants need an explicit action.
    if "action" in props:
        args["action"] = "create"
    if "user_google_email" in props and email:
        args["user_google_email"] = email
    return args


async def main() -> None:
    if not os.getenv("GOOGLE_OAUTH_CLIENT_ID"):
        print("[ERROR] Missing GOOGLE_OAUTH_CLIENT_ID in .env (see .env.example).")
        sys.exit(1)

    email = os.getenv("USER_GOOGLE_EMAIL", "")
    server_params = StdioServerParameters(command="uvx", args=MCP_ARGS, env=_mcp_env())

    print(f"[*] Creating {len(EVENTS)} test events on {email or 'primary'} ...")
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            tool = _find_create_tool(tools)
            print(f"[OK] Using MCP tool: {tool.name}\n")

            created = failed = 0
            for idx, event in enumerate(EVENTS, 1):
                args = _build_args(tool, event, email)
                try:
                    result = await session.call_tool(tool.name, args)
                    text = " ".join(
                        (item.text if hasattr(item, "text") else str(item))
                        for item in result.content
                    )
                    if "error" in text.lower()[:60]:
                        print(f"[{idx}/{len(EVENTS)}] x FAILED: {event['summary']} — {text[:120]}")
                        failed += 1
                    else:
                        print(f"[{idx}/{len(EVENTS)}] OK Created: {event['summary']}")
                        created += 1
                except Exception as e:  # noqa: BLE001 — report and keep going
                    print(f"[{idx}/{len(EVENTS)}] x ERROR: {event['summary']} — {e}")
                    failed += 1

    print(f"\nDone. {created} created, {failed} failed.")
    if created:
        print("Verify in Google Calendar, then run the calendar demo prompts.")


if __name__ == "__main__":
    asyncio.run(main())
