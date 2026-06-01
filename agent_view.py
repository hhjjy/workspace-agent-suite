"""Shared Rich rendering for live agent runs and recorded-demo playback.

The live agents (calendar_agent.py / refund_agent.py) stream their REAL ReAct
steps through `live_render`: a spinner animates during the genuine waits, and
each tool call / result is printed the moment it actually happens. The
recorded-demo viewer (demo/view_terminal.py) reuses the SAME visual primitives
(query panel, tool trace, email cards, answer block) so the live view and the
replayed view look identical — that is why this module exists in one place.
"""

import sys

# Windows terminals default to cp950 and cannot encode emoji/box chars — force UTF-8.
if hasattr(sys.stdout, "reconfigure") and (sys.stdout.encoding or "").lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

console = Console()

MAX_RESULT_CHARS = 600

# Per-category colour for the refund email cards.
CATEGORY_COLOUR = {
    "REFUND_REQUEST": "green",
    "RETURN_REQUEST": "cyan",
    "COMPLAINT": "yellow",
    "OTHER": "dim",
}


# ── Visual primitives (shared by live + recorded views) ───────────────────────

def session_banner(title: str) -> None:
    console.print()
    console.print(Panel(Text(title, style="bold white", justify="center"),
                        border_style="magenta"))


def query_panel(text: str) -> None:
    console.print()
    console.print(Panel(Text(text, style="bold white"),
                        title="[bold cyan]User[/]", border_style="cyan", expand=False))


def trace_header() -> None:
    console.print("[dim]── Agent reasoning trace ──[/]")


def tool_call_line(name: str, args: dict | None = None) -> None:
    console.print(f"  [bold yellow]➜ {name}[/]")
    if args:
        compact = ", ".join(f"{k}={_short(v)}" for k, v in args.items())
        if compact:
            console.print(f"       [dim]{compact}[/]")


def tool_result_block(name: str, result) -> None:
    text = str(result)
    if len(text) > MAX_RESULT_CHARS:
        text = text[:MAX_RESULT_CHARS] + " …"
    for ln in text.splitlines() or [""]:
        console.print(f"       [dim]↳ {ln}[/]")


def answer_block(text: str, label: str = "Agent") -> None:
    console.print()
    console.print(f"[bold green]{label}[/]")
    if str(text).strip():
        console.print(Markdown(str(text)))
    else:
        console.print("[dim](已完成操作，無文字回覆)[/]")
    console.print()
    console.rule(style="dim")


def email_card(index: int, sender: str, subject: str, classification: str, action: str) -> None:
    colour = CATEGORY_COLOUR.get(classification, "white")
    body = Text()
    body.append("寄件者：", style="bold"); body.append(f" {sender}\n")
    body.append("主旨：", style="bold"); body.append(f" {subject}\n")
    body.append("分類：", style="bold"); body.append(f" {classification}\n", style=colour)
    body.append("處理：", style="bold"); body.append(f" {action}")
    console.print(Panel(body, title=f"[bold]信件 {index}[/]",
                        border_style=colour, expand=False))


def _short(v, n: int = 40) -> str:
    s = str(v).replace("\n", " ")
    return s if len(s) <= n else s[:n] + "…"


# ── Refund summary table → per-email rows ─────────────────────────────────────

def parse_summary_table(answer: str) -> list[dict]:
    """Extract per-email rows from the agent's OWN markdown summary table.

    Re-arranges the agent's output only; invents no data.
    Returns a list of {sender, subject, classification, action}.
    """
    rows = []
    for line in answer.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 5 or not cells[0].isdigit():
            continue
        rows.append({
            "sender": cells[1],
            "subject": cells[2].strip('"'),
            "classification": cells[3].replace("*", "").strip(),
            "action": cells[4],
        })
    return rows


# ── Live driver: stream a real agent run with animated waits ──────────────────

async def live_render(agent, messages, kind: str = "generic", show_query: bool = True) -> list:
    """Stream a real agent run, animating a spinner during the genuine waits and
    printing each step as it happens. Returns the full updated message list so
    the caller can keep multi-turn history.

    Falls back to a single ainvoke + static pretty-render if streaming is
    unavailable, so a demo never hard-fails on the display layer.
    """
    if show_query:
        for m in reversed(messages):
            if isinstance(m, HumanMessage):
                query_panel(str(m.content))
                break

    try:
        return await _stream(agent, messages, kind)
    except Exception:
        # Safety net: run once, render the result statically.
        result = await agent.ainvoke({"messages": messages})
        msgs = result["messages"]
        _render_static(msgs[len(messages):])
        _finish(msgs, kind)
        return list(msgs)


async def _stream(agent, messages, kind: str) -> list:
    final = list(messages)
    answer = ""
    trace_started = False

    status = console.status("[bold yellow]Agent 思考中…[/]", spinner="dots")
    status.start()
    spinning = True
    try:
        async for chunk in agent.astream({"messages": messages}, stream_mode="updates"):
            if not isinstance(chunk, dict):
                continue
            for update in chunk.values():
                new = update.get("messages", []) if isinstance(update, dict) else []
                for m in new:
                    final.append(m)
                    if isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
                        if spinning:
                            status.stop(); spinning = False
                        if not trace_started:
                            trace_header(); trace_started = True
                        for tc in m.tool_calls:
                            tool_call_line(tc.get("name", "tool"), tc.get("args"))
                        status.update("[bold yellow]呼叫工具中…[/]")
                        status.start(); spinning = True
                    elif isinstance(m, ToolMessage):
                        if spinning:
                            status.stop(); spinning = False
                        tool_result_block(m.name or "tool", m.content)
                        status.update("[bold yellow]分析結果…[/]")
                        status.start(); spinning = True
                    elif isinstance(m, AIMessage) and str(m.content).strip():
                        answer = str(m.content)
    finally:
        if spinning:
            status.stop()

    _finish(final, kind, answer)
    return final


def _render_static(new_messages: list) -> None:
    """Static fallback render of a finished turn's tool steps."""
    steps = [m for m in new_messages if isinstance(m, (AIMessage, ToolMessage))]
    printed = False
    for m in steps:
        if isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
            if not printed:
                trace_header(); printed = True
            for tc in m.tool_calls:
                tool_call_line(tc.get("name", "tool"), tc.get("args"))
        elif isinstance(m, ToolMessage):
            if not printed:
                trace_header(); printed = True
            tool_result_block(m.name or "tool", m.content)


def _finish(messages: list, kind: str, answer: str = "") -> None:
    if not answer:
        for m in reversed(messages):
            if isinstance(m, AIMessage) and str(m.content).strip():
                answer = str(m.content)
                break
    if kind == "refund":
        rows = parse_summary_table(answer)
        if rows:
            console.print()
            console.print(f"[dim]—— 收件匣處理結果：{len(rows)} 封 ——[/]")
            for i, r in enumerate(rows, 1):
                email_card(i, r["sender"], r["subject"], r["classification"], r["action"])
        answer_block(answer, label="Agent 摘要報告")
    else:
        answer_block(answer)
