"""Shared module for AI Workspace Agent Suite."""

import os
import sys
from typing import Annotated, Sequence, Any

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict

load_dotenv()


# ── State ────────────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]


# ── LLM factory ──────────────────────────────────────────────────────────────

def create_llm() -> ChatOpenAI:
    provider = os.getenv("LLM_PROVIDER", "openrouter")
    model = os.getenv("LLM_MODEL", "deepseek/deepseek-v4-flash")
    base_url = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")

    if provider == "openai":
        api_key = os.environ["OPENAI_API_KEY"]
        return ChatOpenAI(model=model, api_key=api_key)

    # openrouter or any custom provider
    api_key = os.environ["OPENROUTER_API_KEY"]
    return ChatOpenAI(model=model, base_url=base_url, api_key=api_key)


# ── Graph builder ────────────────────────────────────────────────────────────

def should_continue(state: AgentState) -> str:
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return END


async def build_agent(
    mcp_tools: list,
    system_prompt: str,
    extra_tools: list | None = None,
) -> Any:
    """Build a LangGraph ReAct agent.

    Args:
        mcp_tools: Tools loaded from MCP server.
        system_prompt: The agent's system prompt.
        extra_tools: Additional @tool functions (e.g. CLI tools for Calendar Agent).
    """
    all_tools = list(mcp_tools)
    if extra_tools:
        all_tools.extend(extra_tools)

    llm = create_llm().bind_tools(all_tools)
    sys_msg = SystemMessage(content=system_prompt)

    def agent_node(state: AgentState) -> dict:
        messages = [sys_msg] + list(state["messages"])
        response = llm.invoke(messages)
        return {"messages": [response]}

    tool_node = ToolNode(all_tools, handle_tool_errors=True)

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    return graph.compile()


# ── Interactive chat ─────────────────────────────────────────────────────────

async def run_interactive_chat(agent: Any, kind: str = "generic") -> None:
    from agent_view import live_render

    history: list[BaseMessage] = []
    print("\nAgent ready. Type 'exit' or 'quit' to stop.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if user_input.lower() in ("exit", "quit"):
            print("Bye!")
            break

        if not user_input:
            continue

        history.append(HumanMessage(content=user_input))
        history = await live_render(agent, history, kind=kind)


# ── Env validation ───────────────────────────────────────────────────────────

def validate_env(required_keys: list[str]) -> bool:
    missing = [k for k in required_keys if not os.getenv(k)]
    if missing:
        print(f"\n[ERROR] Missing environment variables: {', '.join(missing)}")
        _print_setup_guide()
        return False
    return True


def _print_setup_guide() -> None:
    guide = """
╔══════════════════════════════════════════════════════════════╗
║                    SETUP GUIDE                               ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  1. Clone & install workspace-mcp:                           ║
║     git clone https://github.com/taylorwilsdon/              ║
║                google_workspace_mcp                          ║
║     cd google_workspace_mcp                                  ║
║     uv tool install .                                        ║
║     pip install workspace-mcp                                ║
║                                                              ║
║  2. Google Cloud Console (console.cloud.google.com):         ║
║     a) Create a new project                                  ║
║     b) Enable: Gmail API + Google Calendar API               ║
║     c) OAuth consent screen → External → add test user       ║
║     d) Scopes: gmail.modify, gmail.send,                     ║
║        calendar, calendar.events                             ║
║     e) Create OAuth 2.0 credentials → Desktop App            ║
║     f) Copy Client ID and Client Secret                      ║
║                                                              ║
║  3. Create .env file:                                        ║
║     LLM_PROVIDER=openrouter                                  ║
║     LLM_MODEL=deepseek/deepseek-v4-flash                    ║
║     LLM_BASE_URL=https://openrouter.ai/api/v1               ║
║     OPENROUTER_API_KEY=sk-or-v1-...                          ║
║     GOOGLE_OAUTH_CLIENT_ID=<your-client-id>                  ║
║     GOOGLE_OAUTH_CLIENT_SECRET=<your-client-secret>          ║
║     OAUTHLIB_INSECURE_TRANSPORT=1                            ║
║                                                              ║
║  4. Verify:                                                  ║
║     workspace-cli list                                       ║
║     workspace-cli call list_calendars                        ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""
    print(guide)
