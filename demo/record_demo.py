"""Recorder — runs both agents for real once, saves results as JSON for demo.

事前執行一次(需要連線):
    python record_demo.py            # 錄製兩個 agent
    python record_demo.py calendar   # 只錄行事曆
    python record_demo.py refund     # 只錄退款

輸出:demo_data/calendar.json, demo_data/refund.json
demo 當天用 demo_view.py(終端機)或 demo_html.py(網頁)讀這些檔(不連線)。
"""

import asyncio
import json
import sys
from pathlib import Path

# Make the project root importable (this file lives in demo/).
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_mcp_adapters.client import MultiServerMCPClient

load_dotenv(ROOT / ".env")

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from agent_core import build_agent
from agent_view import _clean_observation

DATA_DIR = Path(__file__).resolve().parent / "data"
MAX_RESULT_CHARS = 600

# 行事曆以多輪對話錄製;退款跑 auto 一次。
# 與官方測試 Testing_project_2.pdf §1.4–1.6 對齊,讓預錄備案內容 = 現場 demo。
CALENDAR_QUERIES = [
    "What's on my calendar?",
    "Schedule a team lunch for the coming Friday at noon for 1 hour.",
    "Find a free 30-minute slot for a call with john@example.com this week.",
]


def extract_record(messages: list, query: str) -> dict:
    """Turn a run's message list into a ReAct record:
    {query, react: [{thought, actions, observations}], answer}.

    Mirrors the live renderer so the recorded view shows the same
    Thought → Action → Observation loop.
    """
    react: list[dict] = []
    current: dict | None = None
    for msg in messages:
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            current = {
                "thought": str(msg.content or ""),
                "actions": [{"tool": tc.get("name", "tool"), "args": tc.get("args")}
                            for tc in msg.tool_calls],
                "observations": [],
            }
            react.append(current)
        elif isinstance(msg, ToolMessage):
            result = _clean_observation(str(msg.content))
            if len(result) > MAX_RESULT_CHARS:
                result = result[:MAX_RESULT_CHARS] + " …"
            if current is not None:
                current["observations"].append({"tool": msg.name or "tool", "result": result})

    # 最終答案 = 最後一則「沒有 tool_calls」的 AIMessage(真正的回覆,不是中途思考)
    answer = ""
    for m in reversed(messages):
        if isinstance(m, AIMessage) and not getattr(m, "tool_calls", None) and str(m.content).strip():
            answer = str(m.content)
            break

    return {"query": query, "react": react, "answer": answer}


async def record_calendar() -> None:
    from calendar_agent import WORKSPACE_MCP_CONFIG, SYSTEM_PROMPT, EXTRA_TOOLS

    print("[*] Recording Calendar Agent ...")
    client = MultiServerMCPClient(WORKSPACE_MCP_CONFIG)
    mcp_tools = await client.get_tools()
    print(f"[OK] Loaded {len(mcp_tools)} MCP tools: {[t.name for t in mcp_tools]}")
    agent = await build_agent(mcp_tools, SYSTEM_PROMPT, extra_tools=EXTRA_TOOLS)

    records = []
    history = []  # 跨輪保留對話脈絡
    for q in CALENDAR_QUERIES:
        print(f"    Q: {q}")
        prev_len = len(history)
        history.append(HumanMessage(content=q))
        result = await agent.ainvoke({"messages": history})
        new_messages = result["messages"]
        turn_messages = new_messages[prev_len:]  # 只取本輪新增的訊息
        records.append(extract_record(turn_messages, q))
        history = list(new_messages)

    _save("calendar", records)


async def record_refund() -> None:
    from refund_agent import WORKSPACE_MCP_CONFIG, SYSTEM_PROMPT, AUTO_PROMPT

    print("[*] Recording Refund Agent (auto mode) ...")
    client = MultiServerMCPClient(WORKSPACE_MCP_CONFIG)
    mcp_tools = await client.get_tools()
    print(f"[OK] Loaded {len(mcp_tools)} MCP tools: {[t.name for t in mcp_tools]}")
    agent = await build_agent(mcp_tools, SYSTEM_PROMPT)

    q = "Process all customer service emails (auto)."
    print(f"    Q: {q}")
    result = await agent.ainvoke({"messages": [HumanMessage(content=AUTO_PROMPT)]})
    record = extract_record(result["messages"], q)
    _save("refund", [record])


def _save(name: str, records: list) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / f"{name}.json"
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    total_steps = sum(len(r.get("react", [])) for r in records)
    print(f"[SAVED] {path}  ({len(records)} records, {total_steps} ReAct steps)")


async def main() -> None:
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if which in ("all", "calendar"):
        await record_calendar()
    if which in ("all", "refund"):
        await record_refund()
    print("\n[DONE] Recording complete. View with:")
    print("    python demo/view_terminal.py calendar   # 終端機展示")
    print("    python demo/view_terminal.py refund")


if __name__ == "__main__":
    asyncio.run(main())
