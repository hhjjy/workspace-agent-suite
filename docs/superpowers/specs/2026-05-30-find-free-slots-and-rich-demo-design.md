# 設計文件：找空檔功能 + Rich 終端機展示器

日期：2026-05-30
範圍：Project 2（AI Workspace Agent Suite）的 demo 強化

---

## 1. 背景與目標

Project 2 的成績只靠一場 **25 分鐘的 live demo**（與 Project 1 共用時間，P2 實際約 8–10 分鐘）。
本次工作有兩個目的：

1. **補規格缺口** —— 規格（`Project2.pdf` Project B）列出 Calendar Agent 應能「找空檔（check for free time slots）」，目前未實作。
2. **讓 demo 又快又穩又有畫面感** —— 不重做網頁 UI（現有 Gradio 又醜又卡），改用 **Rich** 套件把終端機輸出做得漂亮，且 demo 全程**只讀預先錄製好的結果**，不在台上連線，零出包風險。

**非目標（這次不做）**：
- 不重做 / 不修 Gradio UI（`app.py` 這次完全不碰）
- 不做 RSVP（安裝的 workspace-mcp 此版本無對應工具）
- 不做 CLI 雙工具策略的修復

---

## 2. 整體架構

工作拆成三個獨立部分：

| 部分 | 內容 | 動到的檔案 |
|------|------|-----------|
| **A. 找空檔** | 行事曆 agent 真的會找空檔 | `calendar_agent.py` |
| **B. Rich 展示器** | 兩個 agent 共用的漂亮終端機輸出（只讀預存結果、逐步浮現） | 新檔 `demo_view.py` + 兩個 agent |
| **C. 錄製腳本** | demo 前真跑一次 agent，把結果存成 JSON | 新檔 `record_demo.py` + `demo_data/*.json` |

**關鍵設計原則**：展示器（B）與 agent **解耦** —— 展示器只負責「把一筆結果畫漂亮」，不在乎結果是現跑的還是讀檔的。demo 當天只走「讀 JSON → Rich 渲染」這條路，完全不連線。

**demo 的兩個階段**：
1. **事前準備（在家做一次）**：跑 `record_demo.py` → 真的呼叫兩個 agent → 把結果（含工具 trace）存成 JSON。
2. **demo 當天（台上）**：跑展示器 → 讀同一份 JSON → Rich 漂亮渲染、逐步浮現。永遠讀同一份預存結果，穩定。

---

## 3. Part A — 找空檔功能（`calendar_agent.py`）

### 3.1 載入 freebusy 工具
- 把 MCP 啟動參數的 `--tool-tier core` 改為 `--tool-tier extended`。
- 已實測：`extended` 為累加，原本 `list_calendars / get_events / manage_event` 都還在，並新增 `query_freebusy`（查忙碌時段）等工具。

### 3.2 新增自寫工具 `find_free_slots`
規格要的是「找空檔」，但 `query_freebusy` 只回**忙碌**時段。需要一層把忙碌反推成空閒的邏輯，由**自寫 Python 工具**精確計算（而非交給 LLM 心算，避免時間算錯）。

```
@tool
def find_free_slots(date: str, work_start: str = "09:00", work_end: str = "18:00") -> ...:
    """找出指定日期在上班時段內的空閒時段。"""
    # 1. 呼叫 query_freebusy 拿該日忙碌時段
    # 2. 在 [work_start, work_end] 區間內，扣掉忙碌區段
    # 3. 回傳剩下的空閒時段清單
```

- 預設上班時段 09:00–18:00（使用者可在問句中覆寫）。
- 此工具會被掛進 `extra_tools`（與既有 CLI_TOOLS 並列），透過 `bind_tools` 註冊給 LLM。

### 3.3 更新 prompt
在 `SYSTEM_PROMPT` 的工具說明加入 `find_free_slots`，並加一條規則：使用者問「何時有空 / 找空檔 / free slot」時，使用 `find_free_slots`。

---

## 4. Part B — Rich 展示器（新檔 `demo_view.py`）

一個與 agent 無關的純展示模組。

### 4.1 介面
```
def render_demo(records: list[dict], step_delay: float = 0.6) -> None:
    """把一串預存的 demo 結果用 Rich 漂亮渲染、逐步浮現。"""
```
- 對每一筆 record：
  1. 印出標題框（顯示 query）
  2. 逐行浮現每個工具呼叫（`🔧 工具名 → 結果`），每行之間停頓 `step_delay` 秒
  3. 印分隔線
  4. 逐行浮現最終答案
- 使用 Rich 的 `Panel`、顏色、`Console`；逐步浮現用簡單的逐行印出 + 短停頓達成（節奏由 `step_delay` 控制，demo 時看得清楚）。

### 4.2 兩個 agent 共用
行事曆與退款的 demo 入口都呼叫 `render_demo`，讀各自的預存 JSON，整場 demo 風格一致。

---

## 5. Part C — 錄製腳本（新檔 `record_demo.py`）

事前執行一次，產生預存結果。

- 對每個 agent，跑一組預先定好的 demo 問句，真的 `agent.ainvoke`。
- 從回傳的 messages 萃取：query、每個工具呼叫（名稱 + 結果摘要）、最終答案。
- 存成 JSON 到 `demo_data/calendar.json` 與 `demo_data/refund.json`。
- demo 當天不需要這支腳本。

### demo 問句（初版，可再調）
- **行事曆**：「我有哪些日曆？」「我下週二有哪些時段有空?」（觸發 find_free_slots）「幫我看這週的行程」
- **退款**：跑 `auto` 流程，分類 + 回覆事先寄好的 4 封測試信，出摘要

---

## 6. 資料格式（JSON）

每個 agent 一個檔，內容是一個 record 陣列：

```json
[
  {
    "query": "我下週二有哪些時段有空?",
    "steps": [
      {"tool": "query_freebusy",  "result": "忙碌:13:00-14:00"},
      {"tool": "find_free_slots", "result": "3 段空檔"}
    ],
    "answer": "你下週二(6/2)的空檔:\n• 09:00–11:00\n• 14:00–17:30"
  }
]
```

---

## 7. 檔案異動總覽

| 動作 | 檔案 | 說明 |
|------|------|------|
| ✏️ 改 | `calendar_agent.py` | tier→extended、新增 `find_free_slots`、更新 prompt、加 Rich demo 入口 |
| ✏️ 改 | `refund_agent.py` | 加 Rich demo 入口 |
| 🆕 新 | `demo_view.py` | Rich 渲染（`render_demo`） |
| 🆕 新 | `record_demo.py` | 事前錄製，產生 JSON |
| 🆕 新 | `demo_data/calendar.json`、`demo_data/refund.json` | 預存結果 |
| ➕ 依賴 | `pyproject.toml` / `requirements.txt` | 加入 `rich` |

`app.py`（Gradio）本次不動。

---

## 8. 測試與驗證

- **找空檔**：在測試 Google Calendar 塞 2–3 個假行程，跑行事曆 agent 問「下週二哪有空」，確認 `find_free_slots` 被呼叫且算出的空檔正確（人工核對忙碌時段反推）。
- **展示器**：用一份手寫的小 JSON 餵 `render_demo`，確認顏色、框線、逐步浮現正常（這步離線、不需 agent）。
- **錄製腳本**：跑一次 `record_demo.py`，確認 JSON 成功產生、欄位齊全。
- **整條 demo**：讀真正錄好的 JSON 跑展示器，確認兩個 agent 畫面都漂亮、節奏適合 demo。

---

## 9. 風險與緩解

| 風險 | 緩解 |
|------|------|
| demo 當天連線/API 掛掉 | 全程讀預存 JSON，不連線 |
| `find_free_slots` 時間算錯 | 用 Python 精確計算而非 LLM 心算；事前驗證 |
| 錄製時 agent 沒呼叫到 find_free_slots | 調整 prompt / 問句措辭，重錄 |
| demo 內容被質疑是假的 | 錄製腳本是真跑 agent 的結果（非手編）；必要時可現場補跑 record_demo 證明 |
