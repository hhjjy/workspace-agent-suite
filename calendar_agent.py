"""Calendar Agent — interactive AI assistant for Google Calendar."""

import asyncio
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.tools import tool
from langchain_mcp_adapters.client import MultiServerMCPClient

from agent_core import (
    AgentState,
    build_agent,
    print_agent_steps,
    print_agent_turn,
    run_interactive_chat,
    validate_env,
)

load_dotenv()

# ── MCP config ───────────────────────────────────────────────────────────────

WORKSPACE_MCP_CONFIG = {
    "workspace": {
        "command": "uvx",
        "args": [
            "workspace-mcp",
            "--single-user",
            "--tool-tier", "extended",
            "--permissions", "calendar:full",
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

TODAY = datetime.now().strftime("%A, %B %d, %Y")

SYSTEM_PROMPT = f"""You are a helpful Calendar Assistant connected to Google Calendar.
Today's date is {TODAY}.

## Available Tools

**MCP tools (use these for all operations):**
- list_calendars — list all calendars the user has
- get_events — list events in a date range, or get a single event by ID
  - For today's events: use time_min/time_max with today's date range
  - For a date range: pass time_min and time_max as ISO timestamps
  - For a single event: pass event_id
- manage_event — create, update, or delete calendar events
  - action: "create", "update", or "delete"
  - For create: pass summary, start, end (ISO format), and optionally attendees, location, description
  - For update: pass event_id and the fields to update
  - For delete: pass event_id
- query_freebusy — returns BUSY time periods for a date range (not free time)
- find_free_slots — computes FREE time slots from busy periods

## Finding free time (IMPORTANT two-step flow)
When the user asks "when am I free", "find a free slot", "什麼時候有空", or similar:
  1. Call query_freebusy with time_min/time_max covering the target day.
  2. Call find_free_slots with date=YYYY-MM-DD and busy_intervals set to the
     busy periods returned by query_freebusy (each as "START to END" ISO strings).
  3. Report the free slots returned by find_free_slots.
Do NOT try to compute free slots yourself — always use find_free_slots for the math.

**CLI tools (fallback, may not always be available):**
- cli_today_events, cli_list_events, cli_list_calendars, cli_get_event, cli_tool_list
- These call workspace-cli as subprocess. Use MCP tools first; only try CLI if MCP fails.

## Output Rules
- Convert ISO timestamps to human-readable format (e.g., "Monday, May 26, 9:00 AM")
- List events chronologically with bullet points
- Include event location or video link if available

## Safety Rules
- Before DELETE or UPDATE operations, confirm with the user first
- Show what will change and ask "Should I proceed?"
"""

# ── CLI subprocess runner ────────────────────────────────────────────────────

def _run_cli(args: list[str], timeout: int = 15) -> dict | str:
    try:
        result = subprocess.run(
            ["workspace-cli"] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ},
        )
        if result.returncode != 0:
            return f"CLI error (exit {result.returncode}): {result.stderr.strip()}"
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return result.stdout.strip()
    except subprocess.TimeoutExpired:
        return f"CLI timeout after {timeout}s"
    except FileNotFoundError:
        return "workspace-cli not found. Run: uv tool install . (in google_workspace_mcp repo)"


# ── CLI @tool functions ──────────────────────────────────────────────────────

@tool
def cli_today_events(calendar_id: str = "primary") -> dict | str:
    """Get today's calendar events. Fast CLI call, no MCP overhead."""
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return _run_cli([
        "call", "list_calendar_events",
        "--calendarId", calendar_id,
        "--timeMin", start.isoformat(),
        "--timeMax", end.isoformat(),
        "--singleEvents", "true",
        "--orderBy", "startTime",
    ])


@tool
def cli_list_events(
    time_min: str = "",
    time_max: str = "",
    max_results: int = 25,
    calendar_id: str = "primary",
) -> dict | str:
    """List calendar events in a date range. Defaults to next 7 days."""
    if not time_min:
        time_min = datetime.now(timezone.utc).isoformat()
    if not time_max:
        time_max = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    return _run_cli([
        "call", "list_calendar_events",
        "--calendarId", calendar_id,
        "--timeMin", time_min,
        "--timeMax", time_max,
        "--maxResults", str(max_results),
        "--singleEvents", "true",
        "--orderBy", "startTime",
    ])


@tool
def cli_list_calendars() -> dict | str:
    """List all calendars the user has access to."""
    return _run_cli(["call", "list_calendars"])


@tool
def cli_get_event(event_id: str, calendar_id: str = "primary") -> dict | str:
    """Get full details of a single calendar event by ID."""
    return _run_cli([
        "call", "get_calendar_event",
        "--calendarId", calendar_id,
        "--eventId", event_id,
    ])


@tool
def cli_tool_list() -> dict | str:
    """List all tools the MCP server exposes. Useful for debugging."""
    return _run_cli(["list"])


# ── Find free slots (MCP query_freebusy → this tool computes the gaps) ─────────

DEFAULT_TZ = "Asia/Taipei"


def _parse_iso(ts: str) -> datetime:
    """Parse an ISO-8601 timestamp (handles trailing 'Z') into an aware datetime."""
    ts = ts.strip()
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _compute_free_slots(
    date: str,
    busy_intervals: list | None,
    work_start: str = "09:00",
    work_end: str = "18:00",
    tz_name: str = DEFAULT_TZ,
) -> list[tuple[str, str]]:
    """Pure function: subtract busy periods from working hours, return free slots.

    All times are resolved in tz_name (local wall-clock). Busy intervals coming
    from query_freebusy are typically UTC; they are converted before subtracting.
    Returns a list of (start "HH:MM", end "HH:MM") tuples.
    """
    tz = ZoneInfo(tz_name)
    y, m, d = (int(x) for x in date.split("-"))
    sh, sm = (int(x) for x in work_start.split(":"))
    eh, em = (int(x) for x in work_end.split(":"))
    day_start = datetime(y, m, d, sh, sm, tzinfo=tz)
    day_end = datetime(y, m, d, eh, em, tzinfo=tz)

    # Parse + clip busy intervals into the working window
    busy: list[tuple[datetime, datetime]] = []
    for item in busy_intervals or []:
        text = item if isinstance(item, str) else str(item)
        found = re.findall(r"\d{4}-\d{2}-\d{2}T[\d:.+\-]+(?:Z)?", text)
        if len(found) < 2:
            continue
        bs = _parse_iso(found[0]).astimezone(tz)
        be = _parse_iso(found[1]).astimezone(tz)
        bs = max(bs, day_start)
        be = min(be, day_end)
        if bs < be:
            busy.append((bs, be))

    # Merge overlapping busy periods
    busy.sort()
    merged: list[tuple[datetime, datetime]] = []
    for bs, be in busy:
        if merged and bs <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], be))
        else:
            merged.append((bs, be))

    # Subtract merged busy from the working window
    free: list[tuple[datetime, datetime]] = []
    cursor = day_start
    for bs, be in merged:
        if bs > cursor:
            free.append((cursor, bs))
        cursor = max(cursor, be)
    if cursor < day_end:
        free.append((cursor, day_end))

    return [(s.strftime("%H:%M"), e.strftime("%H:%M")) for s, e in free]


@tool
def find_free_slots(
    date: str,
    busy_intervals: list[str] | None = None,
    work_start: str = "09:00",
    work_end: str = "18:00",
) -> str:
    """Compute free time slots on a date within working hours.

    IMPORTANT: First call query_freebusy for the date to get the busy periods,
    then call this tool, passing those busy periods as busy_intervals.

    Args:
        date: Target date in YYYY-MM-DD format, e.g. "2026-06-02".
        busy_intervals: Busy periods from query_freebusy. Each item is a string
            containing the start and end ISO timestamps, e.g.
            "2026-06-02T13:00:00Z to 2026-06-02T14:00:00Z". Empty if fully free.
        work_start: Start of working hours "HH:MM" (default "09:00").
        work_end: End of working hours "HH:MM" (default "18:00").
    """
    try:
        slots = _compute_free_slots(date, busy_intervals, work_start, work_end)
    except Exception as e:  # surface a clean message instead of crashing the agent
        return f"Error computing free slots: {e}"
    if not slots:
        return f"No free slots on {date} between {work_start} and {work_end}."
    lines = [f"Free slots on {date} ({work_start}-{work_end}, {DEFAULT_TZ}):"]
    for s, e in slots:
        lines.append(f"  - {s} to {e}")
    return "\n".join(lines)


# ── Tool registry ─────────────────────────────────────────────────────────────

CLI_TOOLS = [cli_today_events, cli_list_events, cli_list_calendars, cli_get_event, cli_tool_list]
EXTRA_TOOLS = CLI_TOOLS + [find_free_slots]

# ── Demo mode ────────────────────────────────────────────────────────────────

DEMO_QUERIES = [
    "What calendars do I have?",
    "What's on my calendar today?",
    "Show me my events for the next 7 days.",
]


async def run_demo(agent) -> None:
    print("\n=== Calendar Agent — Demo Mode ===\n")
    for i, query in enumerate(DEMO_QUERIES, 1):
        print(f"── Query {i}: {query}")
        result = await agent.ainvoke({"messages": [HumanMessage(content=query)]})
        print_agent_steps(result["messages"])
        print_agent_turn(result["messages"])


# ── Interactive mode (extended) ──────────────────────────────────────────────

async def run_calendar_chat(agent) -> None:
    history: list[BaseMessage] = []
    print("\nCalendar Agent ready. Type 'exit'/'quit' to stop, 'demo' to run demo.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if user_input.lower() in ("exit", "quit"):
            print("Bye!")
            break

        if user_input.lower() == "demo":
            await run_demo(agent)
            continue

        if not user_input:
            continue

        history.append(HumanMessage(content=user_input))
        prev_len = len(history)
        result = await agent.ainvoke({"messages": history})
        history = list(result["messages"])

        print_agent_steps(history[prev_len:])
        print_agent_turn(history)


# ── Main ─────────────────────────────────────────────────────────────────────

REQUIRED_ENV = [
    "GOOGLE_OAUTH_CLIENT_ID",
    "GOOGLE_OAUTH_CLIENT_SECRET",
]


async def main() -> None:
    if not validate_env(REQUIRED_ENV):
        sys.exit(1)

    # Need either OPENROUTER_API_KEY or OPENAI_API_KEY
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
    print(f"[OK] Loaded {len(mcp_tools)} MCP tools: {[t.name for t in mcp_tools]}")
    print(f"[OK] + {len(CLI_TOOLS)} CLI tools: {[t.name for t in CLI_TOOLS]}")

    agent = await build_agent(mcp_tools, SYSTEM_PROMPT, extra_tools=EXTRA_TOOLS)

    # Check CLI arg or default to interactive
    if len(sys.argv) > 1 and sys.argv[1] == "demo":
        await run_demo(agent)
    else:
        await run_calendar_chat(agent)


if __name__ == "__main__":
    asyncio.run(main())
