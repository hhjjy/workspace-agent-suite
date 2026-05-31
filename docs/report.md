# 專案完成報告：AI Workspace Agent Suite

---

## 一、專案概述

本專案為「大語言模型」課程 Project 2，實作兩個自主式 AI Agent，透過 MCP（Model Context Protocol）連接真實的 Google Workspace 帳戶，處理 Gmail 退款郵件與 Google Calendar 行事曆管理。

- **帳戶**：chun24161582@gmail.com
- **LLM**：DeepSeek V4 Flash（透過 OpenRouter，可切換至 GPT-4o）
- **框架**：LangGraph StateGraph + ToolNode（ReAct 推理迴圈）

---

## 二、檔案結構

```
Project2/
├── agent_core.py           # 共用模組：狀態管理、LLM 工廠、ReAct 迴圈
├── calendar_agent.py       # 日曆 Agent：MCP + CLI 工具、demo/互動模式
├── refund_agent.py         # 退款 Agent：Gmail 自動分類回覆、auto/互動模式
├── auth_setup.py           # 一次性 OAuth 認證腳本（Calendar + Gmail）
├── pyproject.toml          # uv 專案設定
├── requirements.txt        # pip 備用
├── README.md               # 完整英文文件
├── .env                    # 機密設定（已 gitignore）
├── .gitignore
└── tests/
    ├── send_test_emails.py         # 寄送 4 種測試信
    ├── test_calendar_crud.py       # 測試日曆 CRUD 流程
    └── test_calendar_advanced.py   # 測試進階日曆功能
```

---

## 三、技術架構

```
使用者輸入（HumanMessage）
    │
    ▼
agent_node → LLM 推理，發出 tool_calls 或純文字回應
    │
should_continue?（條件路由）
    ├── 有 tool_calls → tool_node（執行 MCP 或 CLI 工具）→ 回到 agent_node
    └── 無 tool_calls → END（結束）
```

| 元件 | 技術 |
|------|------|
| 語言 | Python 3.11+（實際使用 3.14） |
| LLM | DeepSeek V4 Flash via OpenRouter |
| Agent 框架 | LangGraph `StateGraph` + `ToolNode` |
| 工具協議 | MCP（Model Context Protocol） |
| MCP 伺服器 | `google_workspace_mcp`（stdio 傳輸） |
| 認證 | Google Cloud OAuth 2.0（Desktop App） |
| 套件管理 | uv |

---

## 四、功能驗證結果

### 4.1 退款郵件 Agent（refund_agent.py）

| 測試項目 | 狀態 | 說明 |
|---------|------|------|
| 搜尋 Gmail | 通過 | 雙重搜尋：`refund OR return` + `complaint OR disappointed OR terrible` |
| REFUND_REQUEST 分類 | 通過 | David Lin "Refund request for Order #5501" → 正確分類 → 已回覆 |
| RETURN_REQUEST 分類 | 通過 | Emily Wu "Want to return my shoes" → 正確分類 → 已回覆 |
| COMPLAINT 分類 | 通過 | Frank Huang "Very disappointed with your service" → 正確分類 → 已回覆 |
| COMPLAINT 分類 | 通過 | Carol Liu "Terrible customer service experience" → 正確分類 → 已回覆 |
| OTHER 跳過 | 通過 | 促銷信、已回覆信件 → 正確識別為 OTHER → 已跳過 |
| Threaded Reply | 通過 | 所有回覆都使用 thread_id 串在原始對話中 |
| 摘要報告 | 通過 | 輸出格式包含寄件者、主旨、分類、處理結果 |
| 錯誤處理 | 通過 | `handle_tool_errors=True` 防止工具錯誤導致程式崩潰 |

**Auto 模式輸出範例：**
```
Found 8 unread emails matching customer service query.
- chun24161582@gmail.com - "Want to return my shoes" → RETURN_REQUEST → Replied
- chun24161582@gmail.com - "Refund request for Order #5501" → REFUND_REQUEST → Replied
- chun24161582@gmail.com - "Very disappointed with your service" → COMPLAINT → Replied
- chun24161582@gmail.com - "Terrible customer service experience" → COMPLAINT → Replied
- chun24161582@gmail.com - "Re: Refund for Order #9921" → OTHER → Skipped
- chun24161582@gmail.com - "Re: I want to return my headphones" → OTHER → Skipped

Summary:
- 4 emails processed and replied to (1 RETURN, 1 REFUND, 2 COMPLAINTS)
- 4 emails skipped (already-replied threads or outgoing sent messages)
```

### 4.2 日曆 Agent（calendar_agent.py）

| 測試項目 | 狀態 | 說明 |
|---------|------|------|
| 列出日曆 | 通過 | 正確回傳 1 個日曆（chun24161582@gmail.com） |
| 查詢今天事件 | 通過 | 正確顯示「無事件」 |
| 查詢未來 7 天事件 | 通過 | 正確列出日期範圍內的事件 |
| 建立事件 | 通過 | 成功建立 "Test Meeting" / "Project Review" |
| 刪除事件 | 通過 | 成功刪除指定事件 |
| 多輪對話 | 通過 | 4 輪對話維持完整 history 上下文 |
| 工具錯誤自動重試 | 通過 | 缺少 timezone 時 agent 自動修正參數重試成功 |
| Demo 模式 | 通過 | 3 個預設查詢全部正常回應 |

**MCP 工具清單：**
- `list_calendars` — 列出所有日曆
- `get_events` — 查詢事件（支援日期範圍、單一事件 ID）
- `manage_event` — 建立/更新/刪除事件

**CLI 工具（@tool 裝飾器）：** 5 個函數已實作於程式碼中，因 stdio 傳輸模式限制，Agent 優先使用 MCP 工具。

### 4.3 共用模組（agent_core.py）

| 元件 | 說明 |
|------|------|
| `AgentState` | TypedDict + `add_messages` reducer |
| `create_llm()` | 可透過 `.env` 切換 OpenRouter / OpenAI |
| `build_agent()` | 組裝 LangGraph StateGraph，支援額外 CLI 工具 |
| `should_continue()` | 條件路由：有 tool_calls → 繼續，無 → 結束 |
| `run_interactive_chat()` | 多輪對話迴圈，支援 exit/quit |
| `validate_env()` | 環境變數驗證 + 設定指南 |
| `ToolNode` | 設定 `handle_tool_errors=True` 防止崩潰 |

---

## 五、安全設計

| 項目 | 實作方式 |
|------|---------|
| OAuth 憑證 | 存於 `.env`，永不寫入原始碼 |
| 憑證檔案 | `.gitignore` 涵蓋 `.env` 和 `client_secret_*.json` |
| 權限範圍 | `--permissions` 限制每個 Agent 只載入需要的工具 |
| 資料隔離 | MCP 伺服器透過 stdio 本地執行，資料不離開本機 |
| 工具錯誤 | `handle_tool_errors=True` 優雅處理錯誤 |
| 破壞性操作 | Calendar Agent 刪除/更新前要求使用者確認 |

---

## 六、Git 提交紀錄

| 提交 | 說明 |
|------|------|
| `4858247` | 初始版本：兩個 Agent 骨架 + MCP 連線 + 基本功能 |
| `9684406` | 完善版：錯誤處理、擴大搜尋範圍、README、檔案整理 |
| `13adead` | 測試腳本：進階日曆測試 + 更新測試郵件 |

---

## 七、執行方式

```bash
# 安裝依賴
uv sync

# 一次性 OAuth 認證（首次使用）
python auth_setup.py

# 日曆 Agent
python calendar_agent.py          # 互動模式
python calendar_agent.py demo     # Demo 模式

# 退款 Agent
python refund_agent.py            # 互動模式
python refund_agent.py auto       # 自動處理模式
```

---

## 八、LLM 切換

如需切換至 GPT-4o，只需修改 `.env`：

```env
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
OPENAI_API_KEY=sk-...
```

不需修改任何程式碼。

---

## 九、關鍵學習概念

| 概念 | 定義 | 程式碼位置 |
|------|------|-----------|
| ReAct 模式 | Reason → Act → Observe 迴圈 | 兩個 Agent |
| LangGraph StateGraph | 有向圖，節點是函數，邊有類型 | `build_agent()` |
| MCP 協議 | JSON-RPC 標準，供 AI 存取工具 | `WORKSPACE_MCP_CONFIG` |
| Tool Binding | 將工具 schema 綁定到 LLM | `llm.bind_tools()` |
| stdio 傳輸 | MCP 透過 stdin/stdout 通訊 | MCP 設定 |
| TypedDict | Python 固定鍵值字典的型別提示 | `AgentState` |
| `add_messages` reducer | LangGraph 輔助函數，追加而非替換訊息 | `AgentState` |
| 條件邊 | 動態選擇下一個節點 | `should_continue()` |
| OAuth 2.0 | 委派存取，有範圍的權限 | Google Cloud 設定 |
| Thread ID | Gmail 標識符，將訊息歸入同一對話 | `send_gmail_message` |
| `@tool` 裝飾器 | LangChain 裝飾器，將函數轉為 LLM 可呼叫工具 | CLI 工具 |

---

## 十、備註

- **RSVP / suggest_meeting_time**：這兩個功能需要 workspace-mcp 的更高 tool tier，`--tool-tier core` 只載入 3 個核心日曆工具。如需此功能可移除 `--tool-tier core` 限制。
- **CLI 工具**：程式碼中保留 5 個 `@tool` CLI 函數符合規格要求。因 stdio 傳輸模式下 `workspace-cli` 無法使用，Agent 已設定優先使用 MCP 工具。
- **Windows 相容性**：已加入 `sys.stdout.reconfigure(encoding="utf-8")` 解決 cp950 編碼無法顯示 emoji 的問題。
- **Token 費用估算**：整個開發過程 DeepSeek API 花費約 $0.05-0.10 USD，若使用 GPT-4o 約 $2-4 USD（貴 40-50 倍）。
