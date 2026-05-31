"""Seed two events on Tue 2026-06-02 (Taipei) so the free-slots demo is meaningful.

Run once before recording the calendar demo:
    python demo/seed_calendar.py
"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient

load_dotenv(ROOT / ".env")
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from calendar_agent import WORKSPACE_MCP_CONFIG

EVENTS = [
    ("Team Lunch", "2026-06-02T13:00:00+08:00", "2026-06-02T14:00:00+08:00"),
    ("Client Call", "2026-06-02T16:00:00+08:00", "2026-06-02T17:30:00+08:00"),
]


async def main():
    client = MultiServerMCPClient(WORKSPACE_MCP_CONFIG)
    tools = {t.name: t for t in await client.get_tools()}
    me = tools["manage_event"]
    for summary, start, end in EVENTS:
        out = await me.ainvoke({
            "action": "create",
            "summary": summary,
            "start_time": start,
            "end_time": end,
            "calendar_id": "primary",
            "timezone": "Asia/Taipei",
        })
        print(f"[CREATE] {summary}: {str(out)[:200]}")
    print("[DONE] seeded")


if __name__ == "__main__":
    asyncio.run(main())
