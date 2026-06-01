# Demo 操作單 — 對齊 Testing_project_2.pdf

> 給負責 demo 的人:照這張單子跑,內容直接對應老師的測試須知。
> 所有指令在 `Project2/` 資料夾、用 `.venv` 的 python 執行。

---

## 階段 0｜一次性設定(在家做一次,之後不用再弄)

```powershell
copy .env.example .env                    # 填入金鑰(或拿已填好的 .env)
uv sync                                    # 安裝套件
.venv\Scripts\python.exe auth_setup.py     # 跳瀏覽器,授權 Calendar + Gmail
```

> ⚠️ **`auth_setup.py` 必須在「有瀏覽器」的環境跑** — 它會開瀏覽器完成 Google OAuth
> 同意畫面;無頭/純文字環境會失敗。授權成功後憑證存本機,之後的注入腳本不再開瀏覽器。

> 跑完 `auth_setup.py`,**行事曆與郵件的注入腳本就都能用了**——認證只此一次,
> 不需要 token.json、也不需要 Gmail 應用程式密碼。

---

## 階段 1｜事前演練(在家做一次,建議)

正式 demo 前先完整跑一遍確認都正常,順便重錄離線備案:

```powershell
.venv\Scripts\python.exe testdata\create_calendar_events.py   # 清理測試週 + 塞 10 筆事件
.venv\Scripts\python.exe testdata\send_test_emails.py          # 清理舊測試信 + 寄 8 封
.venv\Scripts\python.exe calendar_agent.py demo                # 確認三個 prompt 正常
.venv\Scripts\python.exe refund_agent.py auto                  # 確認退款流程正常
.venv\Scripts\python.exe demo\record_demo.py                   # 重錄離線備案
```

> ✅ **兩支注入腳本預設都「先清理、再注入」**(行事曆清掉測試週舊事件;郵件把舊測試信
> 丟垃圾桶),所以**可以安全重複跑、不會累積重複資料**。只想新增不清理時加 `--no-clean`。

⚠️ **事件日期固定在 2026-06-01～06-05**。PDF 的「coming Friday / this week」是相對
今天算的,所以請在**那一週內** demo;若延期,重跑注入腳本即可。

---

## 階段 2｜當場 demo —— 注入前 → 注入後 對照

> 「先看空的 → 注入 → 再看」的橋段,當場證明 agent **真的在讀寫 Google**,不是套招。
> 建議開**兩個終端視窗**:視窗 A 跑 agent、視窗 B 跑注入腳本。

### 開場白(20 秒)

> 「這是兩個自主 AI agent,用 **ReAct** 架構——**Thought → Action → Observation**
> 迴圈——透過 MCP 真的操作我的 Google 行事曆和 Gmail。畫面每一步都會標出它在想什麼、
> 呼叫什麼工具。」

### 第一幕:行事曆 Agent

**① 開 agent(視窗 A)**
```powershell
.venv\Scripts\python.exe calendar_agent.py
```

**② 注入前 —— 在 agent 裡輸入(打英文原句):**
```
What's on my calendar?
```
> 講:「先看現在行事曆——空的 / 沒幾筆。」

**③ 注入(視窗 B)**
```powershell
.venv\Scripts\python.exe testdata\create_calendar_events.py
```
→ 看到 `OK Created ×10`(§1.2 / §1.3)

**④ 注入後 —— 回 agent 再輸入一次:**
```
What's on my calendar?
```
> 講:「再問一次——**10 筆全出現**,證明它真的在讀我的 Google Calendar。」(§1.4)

**⑤ 建立事件 —— 輸入:**
```
Schedule a team lunch for the coming Friday at noon for 1 hour.
```
→ `🧠 Thought → ⚙ manage_event → ✅` 建立 Team Lunch 週五 12:00–13:00(§1.5)

**⑥ 找空檔(招牌)—— 輸入:**
```
Find a free 30-minute slot for a call with john@example.com this week.
```
→ `⚙ query_freebusy → ⚙ find_free_slots → ✅`,吐出 Mon 10:00–10:30 等(§1.6)
> 講:「注意它**連續兩步**——先拿忙碌時段,再用我們自己寫的工具算空檔。這就是 ReAct:
> 它自己決定下一步用什麼工具。」

**⑦ 離開:** 輸入 `exit`

### 第二幕:退款 Email Agent

**① 注入前 —— 跑一次(視窗 A):**
```powershell
.venv\Scripts\python.exe refund_agent.py auto
```
→ `Found 0 emails`
> 講:「先掃信箱——沒有客服信。」

**② 注入(視窗 B):**
```powershell
.venv\Scripts\python.exe testdata\send_test_emails.py
```
→ `OK Sent ×8`(§2.2 / §2.3)

**③ 注入後 —— 再跑一次:**
```powershell
.venv\Scripts\python.exe refund_agent.py auto
```
→ ReAct 全自動:搜尋 → 讀信 → 分類 → 寄回信(逐封**彩色卡片**)
→ 摘要 `Found 8 ｜ Replied 6 ｜ Skipped 2`(§2.4–2.6)
> 講:「促銷信和政策詢問被分成 **OTHER 跳過不回**,其餘 6 封寄了 threaded 回信,
> 全程沒人介入。」

**④(選用)佐證:** 打開 Gmail 寄件備份,看 6 封 threaded 回信真的寄出。

### 收尾白(15 秒)

> 「兩個 agent 共用同一套 ReAct + MCP 架構,真連線操作 Google。行事曆能查、建、
> 找空檔;退款能分類自動回信。每一步工具呼叫都是 LLM 自己推理決定的。」

> 想走最穩路線:把注入放到階段 1 事前做好,正式只在 agent 打那三句 /
> 跑 `refund_agent.py auto`(`calendar_agent.py demo` 會自動依序跑那三句英文)。

---

## 出包備案(現場斷網時)

```powershell
.venv\Scripts\python.exe demo\view_terminal.py calendar
.venv\Scripts\python.exe demo\view_terminal.py refund
.venv\Scripts\python.exe demo\view_terminal.py calendar 1.2   # 放慢思考節奏
.venv\Scripts\python.exe demo\view_terminal.py calendar 0     # 無停頓快速預覽
```

> 前提:已先跑過 `demo\record_demo.py` 重錄(內容才會跟現場 demo 一致)。
> 真連線與預錄共用同一套畫面元件(`agent_view.py`),外觀完全相同。

---

## 指令小抄(把這段放手邊)

| 用途 | 指令 |
|---|---|
| 一次性授權(需瀏覽器) | `.venv\Scripts\python.exe auth_setup.py` |
| 注入行事曆(清理+10 筆) | `.venv\Scripts\python.exe testdata\create_calendar_events.py` |
| 注入信件(清理+8 封) | `.venv\Scripts\python.exe testdata\send_test_emails.py` |
| 行事曆 agent(互動) | `.venv\Scripts\python.exe calendar_agent.py` |
| 行事曆快速 demo(自動跑三句) | `.venv\Scripts\python.exe calendar_agent.py demo` |
| 退款自動跑 | `.venv\Scripts\python.exe refund_agent.py auto` |
| 重錄離線備案 | `.venv\Scripts\python.exe demo\record_demo.py` |
| 備案·行事曆 | `.venv\Scripts\python.exe demo\view_terminal.py calendar` |
| 備案·退款 | `.venv\Scripts\python.exe demo\view_terminal.py refund` |
| 備案·調節奏 | `... view_terminal.py calendar 1.2`(放慢) / `... 0`(秒出) |

行事曆要打的三句(英文原句):
```
What's on my calendar?
Schedule a team lunch for the coming Friday at noon for 1 hour.
Find a free 30-minute slot for a call with john@example.com this week.
```

**鐵則**:行事曆打 **PDF 的英文原句**;注入腳本可安全重跑(預設先清理)。

---

## 螢幕分享提醒

⚠️ **不要開到** `.env`、`client_secret_*.json`、`.workspace-mcp/` —— 會洩漏金鑰。
