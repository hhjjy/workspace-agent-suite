"""Test Calendar Agent CRUD via interactive queries."""

import asyncio
import os
import sys

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langchain_mcp_adapters.client import MultiServerMCPClient

from agent_core import build_agent

load_dotenv()

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from calendar_agent import WORKSPACE_MCP_CONFIG, SYSTEM_PROMPT, CLI_TOOLS

CRUD_QUERIES = [
    "Create a meeting called 'Test Meeting' tomorrow at 2pm for 1 hour",
    "Show me my events for the next 7 days",
    "Delete the 'Test Meeting' event you just created. Yes, proceed.",
    "Show me my events for the next 7 days to confirm it's deleted",
]


async def main():
    print("[*] Starting MCP server...")
    mcp_client = MultiServerMCPClient(WORKSPACE_MCP_CONFIG)
    mcp_tools = await mcp_client.get_tools()
    print(f"[OK] Loaded {len(mcp_tools)} MCP tools")

    agent = await build_agent(mcp_tools, SYSTEM_PROMPT, extra_tools=CLI_TOOLS)

    history = []
    for i, query in enumerate(CRUD_QUERIES, 1):
        print(f"\n{'='*60}")
        print(f"Query {i}: {query}")
        print('='*60)
        history.append(HumanMessage(content=query))
        result = await agent.ainvoke({"messages": history})
        history = list(result["messages"])
        print(f"Agent: {history[-1].content}")

    print("\n[DONE] CRUD test complete!")


if __name__ == "__main__":
    asyncio.run(main())
