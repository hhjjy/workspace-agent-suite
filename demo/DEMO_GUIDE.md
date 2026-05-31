# Project 2 Demo 腳本 — AI Workspace Agent Suite

> 目標:8–10 分鐘內展示兩個自主 AI agent(行事曆 + 退款郵件)。
> 策略:**主打真連線即時跑;若網路/API 出包,立刻切到預錄回放。**

---

## 0. 事前 Checklist(demo 前在家做一次)

```powershell
# 都在 Project2/ 資料夾、用 .venv 的 python

# (1) 確認環境能連(LLM + Google),約 30 秒
.venv\Scripts\python.exe calendar_agent.py demo

# (2) 塞測試行程(讓「找空檔」有東西可算)
.venv\Scripts\python.exe demo\seed_calendar.py

# (3) 寄 4 封測試客服信到自己信箱(退款 demo 用)
.venv\Scripts\python.exe tests\send_test_emails.py

# (4) 重新錄製預錄備案(萬一現場斷網就放這個)
.venv\Scripts\python.exe demo\record_demo.py
```

**檢查點**:`demo\data\calendar.json` 與 `refund.json` 都有更新 → 備案就緒。

⚠️ **螢幕分享時不要開到** `.env`、`client_secret_*.json` — 會洩漏金鑰。

---

## 1. 開場(30 秒)

> 「這是 Project 2:兩個自主式 AI agent,透過 MCP 協議連接**真實的 Google
> 帳號**,用自然語言處理兩件日常雜事——**管理行事曆**和**回覆客服信件**。
> 兩個 agent 共用同一套 ReAct 架構:LLM 推理 → 呼叫工具 → 觀察結果 → 再推理,
> 直到完成。等一下大家會在畫面上看到它每一步呼叫了什麼工具。」

---

## 2. 行事曆 Agent(3–4 分鐘)

啟動:

```powershell
.venv\Scripts\python.exe calendar_agent.py
```

**依序輸入這幾句(打中文人話,不要打工具名):**

| # | 輸入 | 展示重點 |
|---|------|---------|
| 1 | `我有哪些日曆?` | 最基本的讀取,看到 `list_calendars` 被呼叫 |
| 2 | `我 6/2 有哪些時段有空?上班時間 9 點到 18 點。` | **招牌:找空檔**。看到 `query_freebusy` → `find_free_slots` 兩步 |
| 3 | `幫我看接下來 7 天的行程。` | `get_events`,看到剛塞的兩個行程 |
| 4 | `幫我在 6/3 下午 3 點建立一個 1 小時的會議,叫 Demo Sync。` | **寫入**:`manage_event` 建立 |
| 5 | `再看一次接下來 7 天的行程。` | 確認剛剛真的建好了(真連線的證據) |
| 6 | `把 Demo Sync 刪掉,請執行。` | **刪除**:CRUD 完整 |

> 講解詞(在第 2 句時):「注意——它先呼叫 `query_freebusy` 拿到我的**忙碌**
> 時段,再呼叫一個我們自己寫的工具 `find_free_slots`,用程式精準算出**空閒**
> 時段。這就是 ReAct:它會自己決定要連續用哪些工具。」

離開:輸入 `exit`

---

## 3. 退款 Email Agent(3–4 分鐘)

啟動自動模式:

```powershell
.venv\Scripts\python.exe refund_agent.py auto
```

> 講解詞:「這個 agent 全自動跑完 6 步驟:搜尋信箱 → 讀信 → 分類 → 用模板寫
> 回覆 → 寄出 threaded 回信 → 出摘要報告。我事先寄了 4 封測試信:退貨、退款、
> 抱怨、還有一封促銷垃圾信。看它怎麼分類處理。」

**畫面會出現**:
- `── Agent reasoning trace ──` 搜尋兩次、批次讀信、寄出回信
- 最後一份摘要報告表格:每封信的 寄件者 / 主旨 / 分類 / 動作

> 收尾:「促銷信被正確分類成 OTHER、跳過不回;其餘三封都寄了對應模板的
> threaded 回覆。整個過程沒有人介入。」

---

## 4. 出包備案(網路/API 掛掉時)

**不要慌**,直接切預錄回放(不連線、一定能跑):

```powershell
.venv\Scripts\python.exe demo\view_terminal.py calendar
.venv\Scripts\python.exe demo\view_terminal.py refund
```

> 說法:「現場網路不穩,我放一段事先錄好的真實執行結果——這是同一套程式跑出來
> 的。」(畫面有逐步浮現 + 思考動畫,內容跟真連線一樣)

調節奏:`view_terminal.py calendar 1.2`(放慢)、`... 0`(秒出)。

---

## 5. 收尾(30 秒)

> 「總結:兩個 agent 都是真連線、真操作 Google,共用 ReAct + MCP 架構。
> 行事曆能查詢、增刪改、找空檔;退款能自動分類回信。重點是大家看到的每一步
> 工具呼叫,都是 LLM 自己推理決定的。謝謝。」

---

## 速查表(把這段放手邊)

| 用途 | 指令 |
|------|------|
| 行事曆互動 | `.venv\Scripts\python.exe calendar_agent.py` |
| 行事曆快速 demo | `.venv\Scripts\python.exe calendar_agent.py demo` |
| 退款自動跑 | `.venv\Scripts\python.exe refund_agent.py auto` |
| 備案·行事曆 | `.venv\Scripts\python.exe demo\view_terminal.py calendar` |
| 備案·退款 | `.venv\Scripts\python.exe demo\view_terminal.py refund` |

**鐵則**:輸入打**中文人話**(「我有哪些日曆?」),不要打工具名(`list_calendars`)。
