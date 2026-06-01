"""Rich terminal demo viewer — replays pre-recorded agent runs as ReAct steps
(Thought → Action → Observation → Final Answer), with a "thinking" feel:
spinners pause between steps so it looks like the agent is reasoning live.

demo 當天只讀預存 JSON(由 record_demo.py 事先產生),完全不連線、零出包風險。
畫面元件與真連線共用 agent_view.py,兩者外觀一致(都是 ReAct 結構)。

用法:
    python demo/view_terminal.py calendar          # 預設節奏
    python demo/view_terminal.py refund 1.2         # 放慢(思考久一點)
    python demo/view_terminal.py calendar 0         # 無停頓(快速預覽)

Record format (one list per agent):
[
  {"query": "...",
   "react": [{"thought": "...", "actions": [{"tool": "x", "args": {...}}],
              "observations": [{"tool": "x", "result": "..."}]}],
   "answer": "..."}
]
(也相容舊格式: {"query","steps":[{"tool","result"}],"answer"})
"""

import json
import sys
import time
from pathlib import Path

# Make the project root importable (this file lives in demo/).
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent_view import (  # noqa: E402
    console,
    email_card,
    parse_summary_table,
    query_panel,
    react_action,
    react_answer,
    react_observation,
    react_thought,
    session_banner,
)


def _think(label: str, seconds: float) -> None:
    """Animated spinner for `seconds` to simulate the agent thinking."""
    if seconds <= 0:
        return
    with console.status(f"[bold yellow]{label}[/]", spinner="dots"):
        time.sleep(seconds)


def _react_steps(record: dict) -> list[dict]:
    """Return the record's ReAct steps, upgrading the legacy {steps:[...]} shape."""
    if record.get("react"):
        return record["react"]
    # Legacy: one tool+result per step, no captured thought.
    return [
        {"thought": "", "actions": [{"tool": s.get("tool", "tool")}],
         "observations": [{"tool": s.get("tool", "tool"), "result": s.get("result", "")}]}
        for s in record.get("steps", []) or []
    ]


def render_record(record: dict, step_delay: float = 0.7) -> None:
    """Replay one query as ReAct steps."""
    query_panel(record.get("query", ""))

    for i, st in enumerate(_react_steps(record), 1):
        _think("Agent 思考中…", step_delay * 1.6)
        react_thought(i, st.get("thought", ""))
        react_action(i, st.get("actions", []))
        obs = [{"name": o.get("tool"), "result": o.get("result", "")}
               for o in st.get("observations", []) or []]
        if obs:
            _think("呼叫工具中…", step_delay)
            react_observation(i, obs)
        _think("分析結果…", step_delay * 0.7)

    _think("整理回覆中…", step_delay * 1.4)
    react_answer(record.get("answer", ""))


def render_refund(record: dict, step_delay: float = 0.7) -> None:
    """Refund agent: show the inbox being processed one email at a time."""
    answer = record.get("answer", "")
    emails = parse_summary_table(answer)

    query_panel(record.get("query", ""))
    _think("搜尋信箱中…", step_delay * 1.6)
    console.print(f"[dim]—— 收件匣掃描:找到 {len(emails)} 封客服信 ——[/]")

    for i, em in enumerate(emails, 1):
        _think(f"處理第 {i}/{len(emails)} 封:讀取 → 分類 → 回信…", step_delay * 1.3)
        email_card(i, em["sender"], em["subject"], em["classification"], em["action"])

    _think("彙整報告中…", step_delay * 1.2)
    react_answer(answer, label="Final Answer — 摘要報告")


def render_demo(records: list, title: str, step_delay: float, kind: str) -> None:
    session_banner(title)
    for rec in records:
        if kind == "refund":
            render_refund(rec, step_delay=step_delay)
        else:
            render_record(rec, step_delay=step_delay)


TITLES = {
    "calendar": "Calendar Agent — Demo (ReAct)",
    "refund": "Refund Email Agent — Demo (ReAct)",
}

DATA_DIR = Path(__file__).resolve().parent / "data"


def load_records(path: str) -> list:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path}: expected a JSON list of records")
    return data


def main() -> None:
    """Usage: python demo/view_terminal.py <calendar|refund|path.json> [step_delay]"""
    if len(sys.argv) < 2:
        console.print("[red]Usage:[/] python demo/view_terminal.py <calendar|refund> [step_delay]")
        console.print("  e.g. python demo/view_terminal.py calendar 0.7")
        sys.exit(1)

    arg = sys.argv[1]
    delay = float(sys.argv[2]) if len(sys.argv) > 2 else 0.7
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
