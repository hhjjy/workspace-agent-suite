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

> 這個「先看空的 → 注入 → 再看」的橋段,當場證明 agent 是**真的在讀寫 Google**,
> 不是套招。兩個 agent 走一樣的節奏。建議開**兩個終端視窗**:一個跑 agent、一個跑注入。

### A. 行事曆 Agent

開 agent:`.venv\Scripts\python.exe calendar_agent.py`

| 步驟 | 動作 | 老師看到 | 對應 |
|---|---|---|---|
| 1️⃣ 注入前 | 在 agent 打 `What's on my calendar?` | 行事曆空的 / 沒幾筆 | — |
| 2️⃣ 注入 | 另一視窗跑 `testdata\create_calendar_events.py` | `OK Created ×10` | §1.2/1.3 |
| 3️⃣ 注入後 | 回 agent 再打 `What's on my calendar?` | **10 筆全冒出來**(對比!) | §1.4 |
| 4️⃣ 任務 | `Schedule a team lunch for the coming Friday at noon for 1 hour.` | 建立 Team Lunch 週五 12:00–13:00 | §1.5 |
| 5️⃣ 任務 | `Find a free 30-minute slot for a call with john@example.com this week.` | 算出空檔(看到 `query_freebusy → find_free_slots` 兩步) | §1.6 |

打完輸入 `exit` 離開。

> 講解詞:「我先問它行事曆有什麼——空的。現在注入測試資料……再問一次,10 筆全出現,
> 證明它每次都真的去讀我的 Google Calendar。」

### B. 退款 Email Agent

| 步驟 | 動作 | 老師看到 | 對應 |
|---|---|---|---|
| 1️⃣ 注入前 | `.venv\Scripts\python.exe refund_agent.py auto` | `Found 0 emails` / 無信可處理 | — |
| 2️⃣ 注入 | `testdata\send_test_emails.py` | `OK Sent ×8` | §2.2/2.3 |
| 3️⃣ 注入後 | 再跑 `refund_agent.py auto` | 逐封**彩色卡片**:讀取→分類→回信 | §2.4–2.5 |
| 4️⃣ 結果 | (同一次跑完的摘要) | `Processed 8 ｜ Replied 6 ｜ Skipped 2` | §2.6 |
| 5️⃣ 佐證(選用) | 打開 Gmail 看寄件備份 | 6 封 threaded 回信真的寄出 | — |

> 講解詞:「先跑一次——沒有客服信。注入 8 封……再跑一次,它自動分類、該回的回、
> 促銷信跳過,最後 8 封處理、6 回、2 略。」

> 想走最穩路線:把注入放到階段 1 事前做好,正式只在 agent 打 §1.4–1.6 的 prompt /
> 跑 `refund_agent.py auto`(`calendar_agent.py demo` 會自動依序跑那三句)。

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

## 螢幕分享提醒

⚠️ **不要開到** `.env`、`client_secret_*.json`、`.workspace-mcp/` —— 會洩漏金鑰。
