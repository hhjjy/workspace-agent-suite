"""Shared Rich rendering for live agent runs and recorded-demo playback.

Both views speak the SAME ReAct vocabulary — Thought → Action → Observation,
looping until a Final Answer — so the audience can see the ReAct structure
plainly. The live agents (calendar_agent.py / refund_agent.py) stream their
REAL steps through `live_render`; the recorded viewer (demo/view_terminal.py)
replays saved runs through the very same primitives, so live and replay look
identical.
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


# ── ReAct step primitives: Thought → Action → Observation → Final Answer ──────

def react_thought(step: int, text: str) -> None:
    console.print()
    label = f"[bold cyan]🧠 Thought {step}[/]"
    text = str(text).strip()
    if text:
        console.print(f"{label}  [white]{text}[/]")
    else:
        console.print(f"{label}  [dim]決定下一步行動…[/]")


def react_action(step: int, calls: list[dict]) -> None:
    console.print(f"[bold yellow]⚙  Action {step}[/]")
    for c in calls:
        console.print(f"   [yellow]→ {c.get('name') or c.get('tool') or 'tool'}[/]")
        args = c.get("args") or {}
        if args:
            compact = ", ".join(f"{k}={_short(v)}" for k, v in args.items())
            if compact:
                console.print(f"     [dim]{compact}[/]")


def react_observation(step: int, results: list[dict]) -> None:
    console.print(f"[bold green]👁  Observation {step}[/]")
    for r in results:
        name = r.get("name") or "tool"
        text = str(r.get("result", ""))
        if len(text) > MAX_RESULT_CHARS:
            text = text[:MAX_RESULT_CHARS] + " …"
        lines = text.splitlines() or [""]
        console.print(f"   [green]{name}[/] [dim]→ {lines[0]}[/]")
        for ln in lines[1:]:
            console.print(f"     [dim]{ln}[/]")


def react_answer(text: str, label: str = "Final Answer") -> None:
    console.print()
    body = Markdown(str(text)) if str(text).strip() else Text("（已完成操作，無文字回覆）", style="dim")
    console.print(Panel(body, title=f"[bold green]✅ {label}[/]", border_style="green"))
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


def _short(v, n: int = 48) -> str:
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


# ── Live driver: stream a real ReAct run with animated waits ──────────────────

async def live_render(agent, messages, kind: str = "generic", show_query: bool = True) -> list:
    """Stream a real agent run as ReAct steps, animating a spinner during the
    genuine waits. Returns the full updated message list for multi-turn history.

    Falls back to a single ainvoke + static render if streaming is unavailable,
    so a demo never hard-fails on the display layer.
    """
    if show_query:
        for m in reversed(messages):
            if isinstance(m, HumanMessage):
                query_panel(str(m.content))
                break

    try:
        return await _stream(agent, messages, kind)
    except Exception:
        result = await agent.ainvoke({"messages": messages})
        msgs = result["messages"]
        _render_static(msgs[len(messages):])
        _finish(kind, _last_answer(msgs))
        return list(msgs)


async def _stream(agent, messages, kind: str) -> list:
    final = list(messages)
    step = 0
    answer = ""

    status = console.status("[bold yellow]Agent 思考中…[/]", spinner="dots")
    status.start()
    spinning = True
    try:
        async for chunk in agent.astream({"messages": messages}, stream_mode="updates"):
            if not isinstance(chunk, dict):
                continue
            for update in chunk.values():
                new = update.get("messages", []) if isinstance(update, dict) else []
                if not new:
                    continue
                if spinning:
                    status.stop(); spinning = False
                final.extend(new)

                tool_msgs = [m for m in new if isinstance(m, ToolMessage)]
                for m in new:
                    if isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
                        step += 1
                        react_thought(step, m.content)
                        react_action(step, [
                            {"name": tc.get("name", "tool"), "args": tc.get("args")}
                            for tc in m.tool_calls
                        ])
                    elif isinstance(m, AIMessage) and str(m.content).strip():
                        answer = str(m.content)  # content-only message = final answer

                if tool_msgs:
                    react_observation(step, [
                        {"name": m.name, "result": m.content} for m in tool_msgs
                    ])

                status.update("[bold yellow]Agent 思考中…[/]")
                status.start(); spinning = True
    finally:
        if spinning:
            status.stop()

    _finish(kind, answer)
    return final


def _render_static(new_messages: list) -> None:
    """Static ReAct render of a finished turn (streaming-unavailable fallback)."""
    step = 0
    i = 0
    msgs = list(new_messages)
    while i < len(msgs):
        m = msgs[i]
        if isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
            step += 1
            react_thought(step, m.content)
            react_action(step, [
                {"name": tc.get("name", "tool"), "args": tc.get("args")}
                for tc in m.tool_calls
            ])
            obs = []
            j = i + 1
            while j < len(msgs) and isinstance(msgs[j], ToolMessage):
                obs.append({"name": msgs[j].name, "result": msgs[j].content})
                j += 1
            if obs:
                react_observation(step, obs)
            i = j
        else:
            i += 1


def _last_answer(messages: list) -> str:
    for m in reversed(messages):
        if isinstance(m, AIMessage) and not getattr(m, "tool_calls", None) and str(m.content).strip():
            return str(m.content)
    return ""


def _finish(kind: str, answer: str) -> None:
    if kind == "refund":
        rows = parse_summary_table(answer)
        if rows:
            console.print()
            console.print(f"[dim]—— 收件匣處理結果：{len(rows)} 封 ——[/]")
            for i, r in enumerate(rows, 1):
                email_card(i, r["sender"], r["subject"], r["classification"], r["action"])
        react_answer(answer, label="Final Answer — 摘要報告")
    else:
        react_answer(answer)
