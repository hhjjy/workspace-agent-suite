"""Rich terminal demo viewer — replays pre-recorded agent runs with a
"thinking" feel: spinners pause before tool calls and before the answer,
so it looks like the agent is reasoning in real time.

demo 當天只讀預存 JSON(由 record_demo.py 事先產生),完全不連線、零出包風險。

用法:
    python demo/view_terminal.py calendar          # 預設節奏
    python demo/view_terminal.py refund 1.2        # 放慢(思考久一點)
    python demo/view_terminal.py calendar 0        # 無停頓(快速預覽)

Record format (one list per agent):
[
  {"query": "...", "steps": [{"tool": "name", "result": "..."}], "answer": "..."}
]
"""

import json
import sys
import time
from pathlib import Path

# Windows terminals default to cp950 and cannot encode emoji — force UTF-8.
if hasattr(sys.stdout, "reconfigure") and (sys.stdout.encoding or "").lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

console = Console()


def _think(label: str, seconds: float) -> None:
    """Show an animated spinner for `seconds` to simulate the agent thinking."""
    if seconds <= 0:
        return
    with console.status(f"[bold yellow]{label}[/]", spinner="dots"):
        time.sleep(seconds)


def render_record(record: dict, step_delay: float = 0.7) -> None:
    """Render a single recorded query → (think) → tool calls → (think) → answer."""
    query = record.get("query", "")
    steps = record.get("steps", []) or []
    answer = record.get("answer", "")

    # 1. user query
    console.print()
    console.print(Panel(Text(query, style="bold white"),
                        title="[bold cyan]User[/]",
                        border_style="cyan", expand=False))

    # 2. agent "reads" the request before acting
    _think("Agent 思考中…", step_delay * 1.6)

    # 3. tool calls — each preceded by a short "calling tool" spinner
    if steps:
        console.print("[dim]── Agent reasoning trace ──[/]")
        for st in steps:
            tool = st.get("tool", "?")
            result = st.get("result", "")
            _think(f"呼叫工具 {tool} …", step_delay)
            console.print(f"  [yellow]{tool}[/]")
            if result:
                for ln in str(result).splitlines() or [""]:
                    console.print(f"       [dim]↳ {ln}[/]")
            # agent "observes" the result before the next step
            _think("分析結果…", step_delay * 0.7)

    # 4. compose the final answer
    _think("整理回覆中…", step_delay * 1.4)
    console.print()
    console.print("[bold green]Agent[/]")
    console.print(Markdown(str(answer)))
    console.print()
    console.rule(style="dim")


def _parse_summary_table(answer: str) -> list[dict]:
    """Extract per-email rows from the agent's markdown summary table.

    This only re-arranges the agent's OWN output (the summary table it wrote);
    it does not invent any data.
    Returns a list of {sender, subject, classification, action}.
    """
    rows = []
    for line in answer.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 5:
            continue
        if not cells[0].isdigit():  # skip header + separator rows
            continue
        rows.append({
            "sender": cells[1],
            "subject": cells[2].strip('"'),
            "classification": cells[3].replace("*", "").strip(),
            "action": cells[4],
        })
    return rows


def render_refund(record: dict, step_delay: float = 0.7) -> None:
    """Refund agent: show the inbox being processed one email at a time."""
    query = record.get("query", "")
    answer = record.get("answer", "")
    emails = _parse_summary_table(answer)

    # 1. user request
    console.print()
    console.print(Panel(Text(query, style="bold white"),
                        title="[bold cyan]User[/]", border_style="cyan", expand=False))

    # 2. search the inbox
    _think("搜尋信箱中…", step_delay * 1.6)
    console.print(f"── 收件匣掃描:找到 {len(emails)} 封客服信 ──", style="dim")

    # 3. process each email as its own card
    colour = {
        "REFUND_REQUEST": "green",
        "RETURN_REQUEST": "cyan",
        "COMPLAINT": "yellow",
        "OTHER": "dim",
    }
    for i, em in enumerate(emails, 1):
        _think(f"處理第 {i}/{len(emails)} 封:讀取 → 分類 → 回信…", step_delay * 1.3)
        cls = em["classification"]
        c = colour.get(cls, "white")
        body = Text()
        body.append("寄件者:", style="bold"); body.append(f" {em['sender']}\n")
        body.append("主旨:", style="bold"); body.append(f" {em['subject']}\n")
        body.append("分類:", style="bold"); body.append(f" {cls}\n", style=c)
        body.append("處理:", style="bold"); body.append(f" {em['action']}")
        console.print(Panel(body, title=f"[bold]信件 {i}[/]",
                            border_style=c, expand=False))

    # 4. final summary
    _think("彙整報告中…", step_delay * 1.2)
    console.print()
    console.print("Agent 摘要報告", style="bold green")
    console.print(Markdown(str(answer)))
    console.print()
    console.rule(style="dim")


def render_demo(records: list, title: str = "Agent Demo", step_delay: float = 0.7,
                kind: str = "") -> None:
    """Render a whole recorded session (a list of records)."""
    console.print()
    console.print(Panel(Text(title, style="bold white", justify="center"),
                        border_style="magenta"))
    for rec in records:
        if kind == "refund":
            render_refund(rec, step_delay=step_delay)
        else:
            render_record(rec, step_delay=step_delay)


def load_records(path: str) -> list:
    """Load a recorded-demo JSON file."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path}: expected a JSON list of records")
    return data


# Friendly titles per known data file
TITLES = {
    "calendar": "Calendar Agent — Demo",
    "refund": "Refund Email Agent — Demo",
}

DATA_DIR = Path(__file__).resolve().parent / "data"


def main() -> None:
    """Usage: python demo/view_terminal.py <calendar|refund|path.json> [step_delay]"""
    if len(sys.argv) < 2:
        console.print("[red]Usage:[/] python demo/view_terminal.py <calendar|refund> [step_delay]")
        console.print("  e.g. python demo/view_terminal.py calendar 0.7")
        sys.exit(1)

    arg = sys.argv[1]
    delay = float(sys.argv[2]) if len(sys.argv) > 2 else 0.7

    # Accept a short name (calendar/refund) or a full path to a JSON file.
    path = arg if arg.endswith(".json") else str(DATA_DIR / f"{arg}.json")

    stem = Path(path).stem
    title = TITLES.get(stem, f"{stem} — Demo")

    try:
        records = load_records(path)
    except FileNotFoundError:
        console.print(f"[red]File not found:[/] {path}")
        console.print("[dim]Run demo/record_demo.py first to generate it.[/]")
        sys.exit(1)

    render_demo(records, title=title, step_delay=delay, kind=stem)


if __name__ == "__main__":
    main()
