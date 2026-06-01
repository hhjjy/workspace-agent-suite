# AI Workspace Agent Suite

Google Workspace MCP + LangGraph ReAct + Gmail & Calendar APIs

兩個自主式 AI agent,透過 MCP 連接真實 Google Workspace 帳戶,用自然語言處理
退款郵件與行事曆管理。

---

## Agents

### Refund Email Agent (`refund_agent.py`)

自動掃描 Gmail 客服信件、分類、寄出 threaded 回覆。

**流程:** SEARCH → READ → CLASSIFY → DRAFT → SEND → REPORT

| 分類 | 動作 |
|------|------|
| REFUND_REQUEST | 回覆退款核准(3–5 個工作天) |
| RETURN_REQUEST | 回覆退貨步驟 + 預付標籤 |
| COMPLAINT | 同理回覆 + 24 小時內跟進 |
| OTHER | 跳過,不回覆 |

```bash
python refund_agent.py auto    # 自動處理所有客服信
python refund_agent.py         # 互動模式
```

### Calendar Agent (`calendar_agent.py`)

自然語言操作 Google Calendar:查詢、建立 / 修改 / 刪除事件,並能**找出空閒時段**。

```bash
python calendar_agent.py demo  # 跑預設 demo 查詢
python calendar_agent.py       # 互動模式
```

能力對照:

| 能力 | 使用工具 |
|------|---------|
| 列出日曆 | `list_calendars` (MCP) |
| 查詢事件 | `get_events` (MCP) |
| 建立 / 修改 / 刪除 | `manage_event` (MCP) |
| **找空檔** | `query_freebusy` (MCP) → `find_free_slots`(自寫工具,計算空檔) |

---

## Architecture

```
User Input (HumanMessage)
    |
    v
agent_node  ->  LLM 推理,輸出 tool_calls 或純文字
    |
should_continue?
  |                    |
  有 tool_calls        無 tool_calls
  |                    |
  v                    v
tool_node             END
(MCP / CLI / 自寫 @tool)
  |
  └──► 回到 agent_node(迴圈)
```

**共用模組** (`agent_core.py`):

- `AgentState` — TypedDict + `add_messages` reducer
- `create_llm()` — 可切換的 LLM 工廠(OpenRouter / OpenAI,讀 `.env`)
- `build_agent()` — 組裝 LangGraph StateGraph 與 ReAct 迴圈
- `should_continue()` — 條件邊路由
- `run_interactive_chat()` — 多輪對話迴圈

---

## Tech Stack

| 元件 | 技術 |
|------|------|
| 語言 | Python 3.11+ |
| LLM | DeepSeek V4 Flash via OpenRouter(可切換 GPT-4o) |
| Agent 框架 | LangGraph `StateGraph` + `ToolNode` |
| 工具協議 | MCP (Model Context Protocol) |
| MCP 伺服器 | `google_workspace_mcp`(uvx, stdio) |
| 認證 | Google Cloud OAuth 2.0(Desktop App) |
| 終端展示 | Rich |

---

## Setup

### 1. 安裝依賴

```bash
uv sync
```

### 2. Google Cloud Console

1. 於 [console.cloud.google.com](https://console.cloud.google.com) 建立專案
2. 啟用 **Gmail API** 與 **Google Calendar API**
3. OAuth 同意畫面 → External → 把自己的 email 加為 test user
4. 建立 OAuth 2.0 憑證 → Desktop App
5. 複製 Client ID 與 Client Secret

### 3. 設定 `.env`

```env
# LLM
LLM_PROVIDER=openrouter
LLM_MODEL=deepseek/deepseek-v4-flash
LLM_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_API_KEY=sk-or-v1-...

# Google OAuth
GOOGLE_OAUTH_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=GOCSPX-...
USER_GOOGLE_EMAIL=your-email@gmail.com
OAUTHLIB_INSECURE_TRANSPORT=1
```

### 4. 認證(一次性)

```bash
python auth_setup.py
```

依瀏覽器提示完成 Calendar 與 Gmail 的 OAuth。

> ⚠️ **必須在「有瀏覽器」的環境執行** — `auth_setup.py` 會開啟瀏覽器完成 Google OAuth
> 同意畫面。純文字/遠端/無頭環境無法完成授權(會出現 "No authorization code
> received from Google")。授權成功後憑證存於本機,之後的腳本不需再開瀏覽器。

### 5. 執行

```bash
python calendar_agent.py demo   # 測試行事曆
python refund_agent.py auto     # 測試郵件處理
```

---

## Demo(離線展示)

`demo/` 提供一套**不連線**的展示流程:事前錄好真實 agent 執行結果存成 JSON,
demo 當天只讀 JSON、用 Rich 漂亮渲染(含「思考中」動畫),不需網路、零出包風險。

### 事前準備(需連線,跑一次)

```bash
python testdata/create_calendar_events.py  # 塞 10 筆測試事件(對齊 PDF Table 1)
python testdata/send_test_emails.py         # 寄 8 封測試客服信到自己信箱(PDF §2.3)
python demo/record_demo.py                  # 真的跑兩個 agent,結果存到 demo/data/*.json
```

> 完整、對齊老師測試須知的逐步操作見 **`demo/PDF_TEST_RUNSHEET.md`**。

### demo 當天(不連線)

```bash
python demo/view_terminal.py calendar       # 行事曆展示
python demo/view_terminal.py refund         # 退款展示
python demo/view_terminal.py calendar 1.2   # 放慢思考節奏(秒)
python demo/view_terminal.py calendar 0     # 無停頓,快速預覽
```

---

## File Structure

```
Project2/
├── agent_core.py        # 共用 ReAct 迴圈、LLM 工廠、狀態
├── agent_view.py        # 共用 Rich 畫面元件 + 即時串流渲染(真連線/預錄共用)
├── calendar_agent.py    # 行事曆 Agent(含 find_free_slots)
├── refund_agent.py      # 退款 Email Agent
├── auth_setup.py        # 一次性 OAuth 設定
├── app.py               # Gradio UI(選用)
├── pyproject.toml       # uv 專案設定
├── requirements.txt     # pip 備用
├── testdata/            # 測試資料注入(走 MCP 認證,對齊 PDF)
│   ├── create_calendar_events.py  # 塞 10 筆事件(PDF Table 1)
│   └── send_test_emails.py         # 寄 8 封客服信(PDF §2.3)
├── demo/                # 離線展示工具
│   ├── record_demo.py          #   錄製(事前跑,真的呼叫 agent)
│   ├── seed_calendar.py        #   塞測試行程(舊版,選用)
│   ├── view_terminal.py        #   終端機展示器(Rich + 思考動畫)
│   ├── PDF_TEST_RUNSHEET.md    #   對齊測試須知的逐步操作單
│   └── data/                   #   錄好的結果 JSON
├── tests/
│   ├── test_free_slots.py      # find_free_slots 單元測試(離線)
│   ├── test_calendar_crud.py   # 行事曆 CRUD 測試
│   └── test_calendar_advanced.py
└── docs/
    ├── report.md        # 專案報告
    └── spec/            # 作業規格 PDF
```

---

## Security

- OAuth 憑證存於 `.env`,不寫入原始碼;`.env` 與 `client_secret_*.json` 皆 gitignored
- `--permissions` 限制每個 agent 的 MCP 範圍(退款只給 `gmail:send`)
- MCP 伺服器經 stdio 本地執行,資料不離開本機
- `ToolNode(handle_tool_errors=True)` 讓工具錯誤不致程式崩潰
- 行事曆 agent 在刪除 / 修改前要求確認

---

## Switching LLM

切換到 GPT-4o,只需改 `.env`,程式碼不用動:

```env
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
OPENAI_API_KEY=sk-...
```

---

## Testing

```bash
python tests/test_free_slots.py   # 離線單元測試(找空檔邏輯,8 個案例)
```
