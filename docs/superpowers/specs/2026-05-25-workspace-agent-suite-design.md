# AI Workspace Agent Suite — Design Spec

## Overview

Two autonomous AI agents that connect to a live Google Workspace account via MCP (Model Context Protocol), using a ReAct reasoning loop built with LangGraph StateGraph.

- **Refund Email Agent** (`refund_agent.py`) — monitors Gmail for refund/return emails, classifies them, and sends templated threaded replies automatically.
- **Calendar Agent** (`calendar_agent.py`) — interactive chatbot that reads, creates, updates, and deletes Google Calendar events via natural language.

Google account: `chun24161582@gmail.com`

## Tech Stack

| Component | Choice |
|-----------|--------|
| Language | Python 3.11+ |
| LLM (dev) | DeepSeek V4 Flash via OpenRouter |
| LLM (submission) | Switchable to GPT-4o via `.env` |
| Agent framework | LangGraph `StateGraph` + `ToolNode` |
| Tool protocol | MCP (Model Context Protocol) |
| MCP server | `google_workspace_mcp` (stdio transport) |
| CLI tool | `workspace-cli` (Calendar Agent only) |
| Auth | Google Cloud OAuth 2.0 (Desktop App) |

## File Structure

```
Project2/
├── agent_core.py        # Shared: AgentState, create_llm, build_agent,
│                        #   should_continue, run_interactive_chat, validate_env
├── refund_agent.py      # SYSTEM_PROMPT, MCP config, run_auto_refund, main
├── calendar_agent.py    # SYSTEM_PROMPT, CLI tools, run_demo, main
├── requirements.txt
├── .env                 # LLM_PROVIDER, LLM_MODEL, API keys, OAuth creds
└── .gitignore
```

## Shared Module: `agent_core.py`

### `create_llm() -> ChatOpenAI`

Reads from `.env`:
- `LLM_PROVIDER` — `openrouter` (default) or `openai`
- `LLM_MODEL` — e.g. `deepseek/deepseek-v4-flash` or `gpt-4o`
- `LLM_BASE_URL` — e.g. `https://openrouter.ai/api/v1`

Returns a `ChatOpenAI` instance configured accordingly. When switching providers, only `.env` changes — no code changes needed.

### `AgentState`

```python
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
```

### `build_agent(mcp_client, system_prompt, extra_tools=[]) -> CompiledGraph`

1. Fetch MCP tools via `mcp_client.get_tools()`
2. Filter to relevant tools by name
3. Merge with `extra_tools` (CLI @tool functions for Calendar Agent)
4. Create LLM via `create_llm()` and bind all tools
5. Define `agent_node`, `tool_node`, conditional edges
6. Compile and return the graph

### `should_continue(state) -> str`

Returns `"tools"` if last message has `tool_calls`, otherwise `END`.

### `run_interactive_chat(agent) -> None`

`while True` input loop. Maintains `history` list of `BaseMessage`. Exits on `"exit"` / `"quit"`.

### `validate_env(required_keys) -> bool`

Checks environment variables are set. If missing, calls `_print_setup_guide()` and returns `False`.

### `_print_setup_guide() -> None`

Prints terminal guide: installation, OAuth setup, env var export, verification commands.

## Calendar Agent: `calendar_agent.py`

### MCP Config

```python
WORKSPACE_MCP_CONFIG = {
    "workspace": {
        "command": "uvx",
        "args": ["workspace-mcp", "--single-user", "--tool-tier", "core",
                 "--permissions", "calendar"],
        "transport": "stdio",
        "env": {
            "GOOGLE_OAUTH_CLIENT_ID": os.environ["GOOGLE_OAUTH_CLIENT_ID"],
            "GOOGLE_OAUTH_CLIENT_SECRET": os.environ["GOOGLE_OAUTH_CLIENT_SECRET"],
        }
    }
}
```

### CLI Tools (5 `@tool` functions)

All delegate to `_run_cli(args, timeout=15)` which runs `workspace-cli` as subprocess.

| Tool | Purpose |
|------|---------|
| `cli_today_events(calendar_id)` | Today's events |
| `cli_list_events(time_min, time_max, max_results, calendar_id)` | Events in date range |
| `cli_list_calendars()` | All calendars |
| `cli_get_event(event_id, calendar_id)` | Single event details |
| `cli_tool_list()` | Debug: list MCP tools |

### `_run_cli(args, timeout=15) -> dict|str`

Runs `workspace-cli <args>` via `subprocess.run()`. Parses JSON output, falls back to raw text.

### SYSTEM_PROMPT

Includes:
- Today's date (dynamic)
- CLI vs MCP tool selection guide (read → CLI, write → MCP)
- ISO → human-readable time formatting
- Confirmation required before delete/update operations

### Run Modes

- `run_demo(agent)` — 3 pre-written queries: "What calendars do I have?", "What's on my calendar today?", "Show me my events for the next 7 days."
- `run_interactive_chat(agent)` — from `agent_core.py`, plus `"demo"` command triggers `run_demo`
- `main()` — validate env → start MCP → build agent → route to mode

## Refund Agent: `refund_agent.py`

### MCP Config

Same structure as Calendar Agent but with `--permissions gmail:send`.

### SYSTEM_PROMPT

Defines the 6-step automated workflow:

```
SEARCH inbox → READ each email → CLASSIFY intent →
DRAFT reply from template → SEND threaded reply → REPORT summary
```

Email classifications and actions:

| Class | Action |
|-------|--------|
| `REFUND_REQUEST` | Reply: refund approved, 3-5 business days |
| `RETURN_REQUEST` | Reply: return instructions with prepaid label |
| `COMPLAINT` | Reply: empathetic acknowledgement, 24hr follow-up |
| `OTHER` | Skip — no reply |

Hard rules:
- Always thread replies using `thread_id`
- Never reply to `OTHER` emails
- Direct send via `send_gmail_message`

### Run Modes

- `run_auto_refund_processing(agent)` — fires one fixed HumanMessage, agent executes full 6-step workflow autonomously (10-20 tool calls typical)
- `run_interactive_chat(agent)` — from `agent_core.py`
- `main()` — validate env → start MCP → build agent → route to mode

## ReAct Loop (Both Agents)

```
User Input (HumanMessage)
    ↓
agent_node  →  GPT-4o/DeepSeek reasons, emits tool_calls or text
    ↓
should_continue?
  ├─ has tool_calls → tool_node (execute MCP/CLI) → back to agent_node
  └─ no tool_calls → END
```

## Development Phases

| Phase | Deliverable | Done when |
|-------|-------------|-----------|
| 1 | `agent_core.py` + `calendar_agent.py` skeleton | MCP connects, `list_calendars` works |
| 2 | Calendar Agent full features | Interactive chat, CRUD events, demo mode |
| 3 | `refund_agent.py` | Auto-process Gmail, classify, reply |
| 4 | End-to-end test with DeepSeek | Both agents demo successfully |

## Environment Variables

```env
# LLM
LLM_PROVIDER=openrouter
LLM_MODEL=deepseek/deepseek-v4-flash
LLM_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_API_KEY=sk-or-v1-...

# Google OAuth (chun24161582@gmail.com)
GOOGLE_OAUTH_CLIENT_ID=...
GOOGLE_OAUTH_CLIENT_SECRET=...
OAUTHLIB_INSECURE_TRANSPORT=1
```

## Security

- Secrets in `.env`, never in source code
- `.gitignore` covers `.env` and `client_secret_*.json`
- `--permissions` restricts each agent's MCP scope
- `_run_cli()` enforces 15s timeout
- Calendar Agent requires confirmation before destructive ops
