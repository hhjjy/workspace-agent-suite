"""Gradio dashboard UI for AI Workspace Agent Suite."""

import asyncio
import json
import os

import gradio as gr
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_mcp_adapters.client import MultiServerMCPClient

load_dotenv()

from agent_core import build_agent  # noqa: E402
from datetime import datetime

# ── MCP configs ──────────────────────────────────────────────────────────────

MCP_ENV = {
    "GOOGLE_OAUTH_CLIENT_ID": os.getenv("GOOGLE_OAUTH_CLIENT_ID", ""),
    "GOOGLE_OAUTH_CLIENT_SECRET": os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", ""),
    "USER_GOOGLE_EMAIL": os.getenv("USER_GOOGLE_EMAIL", ""),
    "OAUTHLIB_INSECURE_TRANSPORT": os.getenv("OAUTHLIB_INSECURE_TRANSPORT", "1"),
}

CALENDAR_MCP = {
    "workspace": {
        "command": "uvx",
        "args": ["workspace-mcp", "--single-user", "--tool-tier", "core",
                 "--permissions", "calendar:full"],
        "transport": "stdio", "env": MCP_ENV,
    }
}

GMAIL_MCP = {
    "workspace": {
        "command": "uvx",
        "args": ["workspace-mcp", "--single-user", "--tool-tier", "core",
                 "--permissions", "gmail:send"],
        "transport": "stdio", "env": MCP_ENV,
    }
}

# ── Prompts ──────────────────────────────────────────────────────────────────

TODAY = datetime.now().strftime("%A, %B %d, %Y")

CALENDAR_PROMPT = f"""You are a helpful Calendar Assistant. Today is {TODAY}.
Tools: list_calendars, get_events, manage_event.
- Convert ISO timestamps to human-readable format.
- Before DELETE/UPDATE, confirm with user.
"""

REFUND_PROMPT = """You are a Customer Service Email Agent connected to Gmail.
Classify emails as REFUND_REQUEST/RETURN_REQUEST/COMPLAINT/OTHER.
Use templates for replies. Always use thread_id. Never reply to OTHER.
"""

SCAN_PROMPT = """Search for ALL unread emails using these queries:
1. "refund OR return is:unread"
2. "complaint OR disappointed OR unacceptable OR terrible is:unread"
Then read each email's content. For EACH email, output EXACTLY this format (one per line):
SENDER | SUBJECT | CATEGORY | SNIPPET

Categories: REFUND_REQUEST, RETURN_REQUEST, COMPLAINT, OTHER
SNIPPET: first 50 chars of body.
Do NOT reply to any emails. Just list them."""

PROCESS_PROMPT = """Process all customer service emails now.
Search using BOTH queries:
- "refund OR return is:unread"
- "complaint OR disappointed OR unacceptable OR terrible is:unread"
Read, classify, send threaded replies (skip OTHER), and give a summary:
For each email: SENDER | SUBJECT | CLASSIFICATION | ACTION (Replied/Skipped)"""

EVENTS_TODAY_PROMPT = f"Show me all events on my calendar today ({TODAY}). List each with time, title, and location."
EVENTS_WEEK_PROMPT = f"Show me all events for the next 7 days starting from today ({TODAY})."


# ── Agent helpers ────────────────────────────────────────────────────────────

async def build_agent_async(agent_type: str):
    config = CALENDAR_MCP if agent_type == "calendar" else GMAIL_MCP
    prompt = CALENDAR_PROMPT if agent_type == "calendar" else REFUND_PROMPT
    mcp_client = MultiServerMCPClient(config)
    mcp_tools = await mcp_client.get_tools()
    return await build_agent(mcp_tools, prompt)


async def run_query(agent_type: str, query: str):
    agent = await build_agent_async(agent_type)
    result = await agent.ainvoke({"messages": [HumanMessage(content=query)]})
    reply = result["messages"][-1].content
    trace = extract_trace(result["messages"])
    return reply, trace


async def run_chat(agent_type: str, message: str, history: list):
    agent = await build_agent_async(agent_type)
    messages = []
    for h in history:
        if h["role"] == "user":
            messages.append(HumanMessage(content=h["content"]))
        else:
            messages.append(AIMessage(content=h["content"]))
    messages.append(HumanMessage(content=message))
    result = await agent.ainvoke({"messages": messages})
    reply = result["messages"][-1].content
    trace = extract_trace(result["messages"])
    return reply, trace


def extract_trace(messages) -> str:
    parts = []
    for msg in messages:
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                args_str = json.dumps(tc.get("args", {}), indent=2, ensure_ascii=False)
                parts.append(f"**Tool: {tc['name']}**\n```json\n{args_str}\n```")
        elif isinstance(msg, ToolMessage):
            try:
                content = json.loads(str(msg.content))
                pretty = json.dumps(content, indent=2, ensure_ascii=False)
            except (ValueError, TypeError):
                pretty = str(msg.content)
            parts.append(f"**Result: {msg.name}**\n```\n{pretty[:1500]}\n```")
    return "\n\n".join(parts) if parts else "*No tool calls.*"


# ── Gradio UI ────────────────────────────────────────────────────────────────

EMAIL = os.getenv("USER_GOOGLE_EMAIL", "")

with gr.Blocks(title="AI Workspace Agent Suite") as demo:
    gr.Markdown(f"""
# AI Workspace Agent Suite
**Google Workspace MCP + LangGraph ReAct** | Account: `{EMAIL}` | LLM: DeepSeek V4 Flash
""")

    with gr.Tabs():
        # ═══════════════════════════════════════════════════════════════
        # REFUND AGENT TAB
        # ═══════════════════════════════════════════════════════════════
        with gr.Tab("Refund Email Agent"):
            gr.Markdown("### Inbox Scanner & Auto-Reply")

            with gr.Row():
                scan_btn = gr.Button("Scan Inbox", variant="secondary", scale=1)
                process_btn = gr.Button("Auto-Process & Reply", variant="primary", scale=1)

            with gr.Row():
                with gr.Column(scale=3):
                    inbox_display = gr.Markdown(
                        value="Click **Scan Inbox** to see unread customer service emails.",
                        label="Inbox",
                    )
                with gr.Column(scale=2):
                    refund_trace = gr.Markdown(
                        value="*Processing trace will appear here.*",
                        label="Agent Trace",
                    )

            gr.Markdown("---")
            gr.Markdown("### Processing Results")
            results_display = gr.Markdown(
                value="Click **Auto-Process & Reply** to classify and reply to all emails.",
            )

            gr.Markdown("---")
            gr.Markdown("### Interactive Chat")
            with gr.Row():
                with gr.Column(scale=3):
                    ref_chatbot = gr.Chatbot(label="Chat", height=300)
                    ref_input = gr.Textbox(placeholder="e.g. Search for refund emails...", label="Message")
                    with gr.Row():
                        ref_send = gr.Button("Send", variant="primary")
                        ref_clear = gr.Button("Clear Chat")
                with gr.Column(scale=2):
                    ref_chat_trace = gr.Markdown(value="*Chat trace.*")

            # Handlers
            async def scan_inbox():
                reply, trace = await run_query("refund", SCAN_PROMPT)
                return f"### Inbox Overview\n\n{reply}", trace

            async def process_emails():
                reply, trace = await run_query("refund", PROCESS_PROMPT)
                return f"### Processing Complete\n\n{reply}", trace

            async def ref_respond(message, history):
                if not message.strip():
                    return history, "", "*No input.*"
                reply, trace = await run_chat("refund", message, history)
                history.append({"role": "user", "content": message})
                history.append({"role": "assistant", "content": reply})
                return history, "", trace

            scan_btn.click(scan_inbox, [], [inbox_display, refund_trace])
            process_btn.click(process_emails, [], [results_display, refund_trace])
            ref_send.click(ref_respond, [ref_input, ref_chatbot], [ref_chatbot, ref_input, ref_chat_trace])
            ref_input.submit(ref_respond, [ref_input, ref_chatbot], [ref_chatbot, ref_input, ref_chat_trace])
            ref_clear.click(lambda: ([], "", "*Cleared.*"), [], [ref_chatbot, ref_input, ref_chat_trace])

        # ═══════════════════════════════════════════════════════════════
        # CALENDAR AGENT TAB
        # ═══════════════════════════════════════════════════════════════
        with gr.Tab("Calendar Agent"):
            gr.Markdown("### Calendar Overview")

            with gr.Row():
                today_btn = gr.Button("Today's Events", variant="secondary", scale=1)
                week_btn = gr.Button("This Week", variant="secondary", scale=1)

            with gr.Row():
                with gr.Column(scale=3):
                    events_display = gr.Markdown(
                        value="Click **Today's Events** or **This Week** to view your schedule.",
                        label="Events",
                    )
                with gr.Column(scale=2):
                    cal_trace = gr.Markdown(
                        value="*Agent trace will appear here.*",
                        label="Agent Trace",
                    )

            gr.Markdown("---")
            gr.Markdown("### Interactive Chat")
            with gr.Row():
                with gr.Column(scale=3):
                    cal_chatbot = gr.Chatbot(label="Chat", height=300)
                    cal_input = gr.Textbox(
                        placeholder="e.g. Create a meeting tomorrow at 2pm for 1 hour",
                        label="Message",
                    )
                    with gr.Row():
                        cal_send = gr.Button("Send", variant="primary")
                        cal_clear = gr.Button("Clear Chat")
                with gr.Column(scale=2):
                    cal_chat_trace = gr.Markdown(value="*Chat trace.*")

            # Handlers
            async def show_today():
                reply, trace = await run_query("calendar", EVENTS_TODAY_PROMPT)
                return f"### Today ({TODAY})\n\n{reply}", trace

            async def show_week():
                reply, trace = await run_query("calendar", EVENTS_WEEK_PROMPT)
                return f"### This Week\n\n{reply}", trace

            async def cal_respond(message, history):
                if not message.strip():
                    return history, "", "*No input.*"
                reply, trace = await run_chat("calendar", message, history)
                history.append({"role": "user", "content": message})
                history.append({"role": "assistant", "content": reply})
                return history, "", trace

            today_btn.click(show_today, [], [events_display, cal_trace])
            week_btn.click(show_week, [], [events_display, cal_trace])
            cal_send.click(cal_respond, [cal_input, cal_chatbot], [cal_chatbot, cal_input, cal_chat_trace])
            cal_input.submit(cal_respond, [cal_input, cal_chatbot], [cal_chatbot, cal_input, cal_chat_trace])
            cal_clear.click(lambda: ([], "", "*Cleared.*"), [], [cal_chatbot, cal_input, cal_chat_trace])


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
