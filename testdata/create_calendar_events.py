"""Reset + inject the test calendar events from the testing spec
(Testing_project_2.pdf §1.2, Table 1).

DEFAULT BEHAVIOUR = CLEAN then INJECT: first delete every event in the test
window (Jun 1–5, 2026) so re-runs never pile up duplicates, then create the
10 events fresh. Pass --no-clean to skip the cleanup and only add.

Auth: uses the SAME workspace-mcp OAuth as the agents — run `auth_setup.py`
once and this works (no token.json). It finds the right MCP tools and adapts
to their parameter names, so it stays robust across workspace-mcp versions.

    python testdata/create_calendar_events.py            # clean + inject (default)
    python testdata/create_calendar_events.py --no-clean # inject only
"""

import asyncio
import os
import re
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

# Test window (local time) used for cleanup — covers the whole spec week.
WINDOW_MIN = "2026-06-01T00:00:00" + TZ_OFFSET
WINDOW_MAX = "2026-06-06T00:00:00" + TZ_OFFSET

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
    for c in candidates:
        if c in props:
            return c
    return None


def _props(tool) -> dict:
    return (getattr(tool, "inputSchema", None) or {}).get("properties", {}) or {}


def _find_tool(tools, *exact_names, contains=()):
    by_name = {t.name: t for t in tools}
    for name in exact_names:
        if name in by_name:
            return by_name[name]
    for t in tools:
        n = t.name.lower()
        if all(c in n for c in contains):
            return t
    return None


def _text(result) -> str:
    return " ".join((i.text if hasattr(i, "text") else str(i)) for i in result.content)


def _create_args(tool, event: dict, email: str) -> dict:
    props = _props(tool)
    summary_k = _pick(props, "summary", "title") or "summary"
    start_k = _pick(props, "start_time", "start", "startTime", "start_datetime") or "start_time"
    end_k = _pick(props, "end_time", "end", "endTime", "end_datetime") or "end_time"
    tz_k = _pick(props, "timezone", "time_zone", "tz")
    cal_k = _pick(props, "calendar_id", "calendarId")

    if tz_k:
        start_v, end_v = event["start"], event["end"]
    else:
        start_v, end_v = event["start"] + TZ_OFFSET, event["end"] + TZ_OFFSET

    args = {summary_k: event["summary"], start_k: start_v, end_k: end_v}
    if tz_k:
        args[tz_k] = TIMEZONE
    if cal_k:
        args[cal_k] = "primary"
    if "action" in props:
        args["action"] = "create"
    if "user_google_email" in props and email:
        args["user_google_email"] = email
    return args


async def clean_window(session, tools, email: str) -> int:
    """Delete every event in the test window. Returns count deleted."""
    get_tool = _find_tool(tools, "get_events", contains=("event",))
    manage = _find_tool(tools, "manage_event", "delete_event", contains=("event",))
    if not get_tool or not manage:
        print("[clean] skip — no get/delete event tool found.")
        return 0

    gp = _props(get_tool)
    tmin_k = _pick(gp, "time_min", "timeMin", "start_time") or "time_min"
    tmax_k = _pick(gp, "time_max", "timeMax", "end_time") or "time_max"
    args = {tmin_k: WINDOW_MIN, tmax_k: WINDOW_MAX}
    if _pick(gp, "calendar_id", "calendarId"):
        args[_pick(gp, "calendar_id", "calendarId")] = "primary"
    if "max_results" in gp:
        args["max_results"] = 100
    if "user_google_email" in gp and email:
        args["user_google_email"] = email

    listing = _text(await session.call_tool(get_tool.name, args))
    ids = re.findall(r"ID:\s*([A-Za-z0-9_@.-]+)", listing)
    if not ids:
        print("[clean] window already empty.")
        return 0

    mp = _props(manage)
    id_k = _pick(mp, "event_id", "eventId", "id") or "event_id"
    deleted = 0
    for eid in ids:
        dargs = {id_k: eid}
        if "action" in mp:
            dargs["action"] = "delete"
        if _pick(mp, "calendar_id", "calendarId"):
            dargs[_pick(mp, "calendar_id", "calendarId")] = "primary"
        if "user_google_email" in mp and email:
            dargs["user_google_email"] = email
        try:
            out = _text(await session.call_tool(manage.name, dargs))
            if "error" in out.lower()[:60]:
                print(f"[clean] x failed to delete {eid}: {out[:80]}")
            else:
                deleted += 1
        except Exception as e:  # noqa: BLE001
            print(f"[clean] x error deleting {eid}: {e}")
    print(f"[clean] deleted {deleted} existing event(s) in {WINDOW_MIN[:10]}–{WINDOW_MAX[:10]}.")
    return deleted


async def inject(session, tools, email: str) -> tuple[int, int]:
    create_tool = _find_tool(tools, "create_event", "create_calendar_event", "manage_event",
                             contains=("event",))
    if not create_tool:
        raise RuntimeError(f"No create-event tool. Available: {[t.name for t in tools]}")
    print(f"[inject] using MCP tool: {create_tool.name}")

    created = failed = 0
    for idx, event in enumerate(EVENTS, 1):
        try:
            out = _text(await session.call_tool(create_tool.name, _create_args(create_tool, event, email)))
            if "error" in out.lower()[:60]:
                print(f"[{idx}/{len(EVENTS)}] x FAILED: {event['summary']} — {out[:100]}")
                failed += 1
            else:
                print(f"[{idx}/{len(EVENTS)}] OK Created: {event['summary']}")
                created += 1
        except Exception as e:  # noqa: BLE001
            print(f"[{idx}/{len(EVENTS)}] x ERROR: {event['summary']} — {e}")
            failed += 1
    return created, failed


async def main() -> None:
    if not os.getenv("GOOGLE_OAUTH_CLIENT_ID"):
        print("[ERROR] Missing GOOGLE_OAUTH_CLIENT_ID in .env (see .env.example).")
        sys.exit(1)

    do_clean = "--no-clean" not in sys.argv
    email = os.getenv("USER_GOOGLE_EMAIL", "")
    server_params = StdioServerParameters(command="uvx", args=MCP_ARGS, env=_mcp_env())

    print(f"[*] Target: {email or 'primary'} | clean={do_clean}")
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools

            if do_clean:
                await clean_window(session, tools, email)
            created, failed = await inject(session, tools, email)

    print(f"\nDone. {created} created, {failed} failed.")
    if created:
        print("Verify in Google Calendar, then run the calendar demo prompts.")


if __name__ == "__main__":
    asyncio.run(main())
