"""Test Calendar Agent advanced features: create event with attendee, then RSVP."""

import asyncio
import os
import sys

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langchain_mcp_adapters.client import MultiServerMCPClient

load_dotenv()

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent_core import build_agent
from calendar_agent import WORKSPACE_MCP_CONFIG, SYSTEM_PROMPT, CLI_TOOLS

QUERIES = [
    "Create a meeting called 'Project Review' this Friday at 3pm for 30 minutes",
    "Show me my events for this week",
    "Delete the 'Project Review' event. Yes, proceed.",
]


async def main():
    print("[*] Starting MCP server...")
    mcp_client = MultiServerMCPClient(WORKSPACE_MCP_CONFIG)
    mcp_tools = await mcp_client.get_tools()
    print(f"[OK] Loaded {len(mcp_tools)} MCP tools")

    agent = await build_agent(mcp_tools, SYSTEM_PROMPT, extra_tools=CLI_TOOLS)

    history = []
    for i, query in enumerate(QUERIES, 1):
        print(f"\n{'='*60}")
        print(f"Query {i}: {query}")
        print('='*60)
        history.append(HumanMessage(content=query))
        result = await agent.ainvoke({"messages": history})
        history = list(result["messages"])
        print(f"Agent: {history[-1].content}")

    print("\n[DONE] Advanced calendar test complete!")


if __name__ == "__main__":
    asyncio.run(main())
