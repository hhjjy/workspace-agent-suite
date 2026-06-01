"""Hybrid: SMTP-injection (two accounts, spec-style) + MCP-cleanup (idempotent).

對齊規範版的兩帳號 SMTP 寄信流程,但保留夥伴版的工程功能:
  - 寄信走 SMTP/STARTTLS 從 SMTP_SENDER_EMAIL 寄到 SMTP_TARGET_EMAIL
    (兩個不同帳號 — 符合 sendtestemails.py 原規範語意)
  - 清理舊測試信仍走 MCP (因為要刪 TARGET 信箱裡的舊信,需 OAuth)
  - 寄完等 25 秒讓 Gmail 索引完成,Refund Agent 才能完整搜到 8 封
  - 所有設定走 .env,原始碼可 commit

需要的 .env 變數 (見 .env.example):
  SMTP_SENDER_EMAIL    寄件帳號 (另一個個人 Gmail,需開兩階段驗證 + App Password)
  SMTP_APP_PASSWORD    該帳號的 16 碼 App Password (去除空格)
  SMTP_TARGET_EMAIL    接收帳號 (通常 = USER_GOOGLE_EMAIL,留空時 fallback)
  GOOGLE_OAUTH_CLIENT_ID / CLIENT_SECRET / USER_GOOGLE_EMAIL   (清理階段用)

執行:
  python testdata/send_test_emails_smtp.py             # clean + inject (default)
  python testdata/send_test_emails_smtp.py --no-clean  # send only

注:App Password 不支援 Workspace (公司/學校) 帳號 — 寄件人必須是個人 Gmail。
若清理階段 OAuth 不可用,會自動 skip 並繼續注入。
"""

import asyncio
import os
import smtplib
import sys
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv(ROOT / ".env")

if hasattr(sys.stdout, "reconfigure") and (sys.stdout.encoding or "").lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SEND_DELAY_SECONDS = 0.5  # avoid Gmail throttling
INDEX_WAIT_SECONDS = 25  # let Gmail finish indexing before the Refund Agent searches

# Testing_project_2.pdf — §2.3 dataset (2 each of the four categories).
EMAILS = [
    {"category": "REFUND_REQUEST", "subject": "Refund Request for Order #1001",
     "body": "Hello,\n\nI would like to request a refund for Order #1001.\n"
             "The product does not meet my expectations.\n\nThank you."},
    {"category": "REFUND_REQUEST", "subject": "Refund Request for Order #1002",
     "body": "Hello,\n\nThe item arrived damaged.\nPlease process a refund.\n\nRegards."},
    {"category": "RETURN_REQUEST", "subject": "Return Request for Wireless Mouse",
     "body": "Hello,\n\nI would like to return my wireless mouse.\n"
             "Please send return instructions.\n\nThanks."},
    {"category": "RETURN_REQUEST", "subject": "Return Request for Keyboard",
     "body": "Hello,\n\nThe keyboard is incompatible with my system.\n"
             "I would like to return it.\n\nThank you."},
    {"category": "COMPLAINT", "subject": "Very Disappointed",
     "body": "Hello,\n\nYour customer service has been extremely disappointing.\n"
             "I expect a response immediately.\n\nRegards."},
    {"category": "COMPLAINT", "subject": "Poor Service Experience",
     "body": "Hello,\n\nI have contacted support multiple times and nobody helped me.\n\nRegards."},
    {"category": "OTHER", "subject": "Special Summer Promotion",
     "body": "Hello,\n\nCheck out our newest products and discounts.\n\nMarketing Team"},
    {"category": "OTHER", "subject": "Question About Refund Policy",
     "body": "Hello,\n\nBefore purchasing, I would like to know your refund policy.\n\nThank you."},
]

# Cleanup phase uses MCP (needs gmail:full to trash messages in TARGET mailbox).
CLEAN_ARGS = ["workspace-mcp", "--single-user", "--tool-tier", "extended",
              "--permissions", "gmail:full"]


def _mcp_env() -> dict:
    return {
        "GOOGLE_OAUTH_CLIENT_ID": os.getenv("GOOGLE_OAUTH_CLIENT_ID", ""),
        "GOOGLE_OAUTH_CLIENT_SECRET": os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", ""),
        "USER_GOOGLE_EMAIL": os.getenv("USER_GOOGLE_EMAIL", ""),
        "OAUTHLIB_INSECURE_TRANSPORT": os.getenv("OAUTHLIB_INSECURE_TRANSPORT", "1"),
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "APPDATA": os.environ.get("APPDATA", ""),
        "LOCALAPPDATA": os.environ.get("LOCALAPPDATA", ""),
        "USERPROFILE": os.environ.get("USERPROFILE", ""),
    }


def _props(tool) -> dict:
    return (getattr(tool, "inputSchema", None) or {}).get("properties", {}) or {}


def _pick(props: dict, *candidates: str) -> str | None:
    for c in candidates:
        if c in props:
            return c
    return None


def _find(tools, *exact, contains=()):
    by_name = {t.name: t for t in tools}
    for n in exact:
        if n in by_name:
            return by_name[n]
    for t in tools:
        low = t.name.lower()
        if contains and all(c in low for c in contains):
            return t
    return None


def _text(result) -> str:
    return " ".join((i.text if hasattr(i, "text") else str(i)) for i in result.content)


def _extract_ids(search_text: str) -> list[str]:
    import re
    return re.findall(r"Message ID:\s*([A-Za-z0-9]+)", search_text)


async def clean(target_email: str) -> None:
    """Best-effort: trash leftover test emails (originals + replies) in TARGET inbox.

    Uses MCP (OAuth) since SMTP can only send, not delete. If OAuth/scope is
    unavailable, skip silently — injection still proceeds.
    """
    subjects = {e["subject"] for e in EMAILS}
    server = StdioServerParameters(command="uvx", args=CLEAN_ARGS, env=_mcp_env())
    try:
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = (await session.list_tools()).tools
                search = _find(tools, "search_gmail_messages", contains=("search", "gmail"))
                trash = _find(tools, "trash_gmail_message", contains=("trash",))
                modify = _find(tools, "modify_gmail_message_labels", contains=("modify", "label"))
                if not search or not (trash or modify):
                    print("[clean] skip — no trash/modify tool available "
                          "(gmail scope insufficient). Injecting fresh anyway.")
                    return

                ids: set[str] = set()
                for subj in subjects:
                    q = f'subject:"{subj}" newer_than:14d'
                    args = {"query": q}
                    if "user_google_email" in _props(search) and target_email:
                        args["user_google_email"] = target_email
                    ids.update(_extract_ids(_text(await session.call_tool(search.name, args))))

                if not ids:
                    print("[clean] no leftover test emails found.")
                    return

                trashed = 0
                for mid in ids:
                    try:
                        if trash:
                            tp = _props(trash)
                            a = {(_pick(tp, "message_id", "messageId", "id") or "message_id"): mid}
                            if "user_google_email" in tp and target_email:
                                a["user_google_email"] = target_email
                            out = _text(await session.call_tool(trash.name, a))
                        else:
                            mp = _props(modify)
                            a = {(_pick(mp, "message_id", "messageId", "id") or "message_id"): mid,
                                 (_pick(mp, "add_label_ids", "add_labels", "labels_to_add") or "add_label_ids"): ["TRASH"]}
                            if "user_google_email" in mp and target_email:
                                a["user_google_email"] = target_email
                            out = _text(await session.call_tool(modify.name, a))
                        if "error" not in out.lower()[:60]:
                            trashed += 1
                    except Exception as e:  # noqa: BLE001
                        print(f"[clean] x error trashing {mid}: {e}")
                print(f"[clean] trashed {trashed}/{len(ids)} leftover test email(s).")
    except Exception as e:  # noqa: BLE001 — never let cleanup block injection
        print(f"[clean] skip — cleanup unavailable ({e}). Injecting fresh anyway.")


def inject_smtp(sender: str, password: str, target: str) -> tuple[int, int]:
    """SMTP-based injection: send from SENDER to TARGET (two different accounts)."""
    sent = failed = 0
    server = None
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(sender, password)
        print(f"[*] Connected to {SMTP_SERVER}:{SMTP_PORT}  (from {sender} -> {target})\n")

        for idx, mail in enumerate(EMAILS, 1):
            try:
                msg = MIMEMultipart()
                msg["From"] = sender
                msg["To"] = target
                msg["Subject"] = mail["subject"]
                msg.attach(MIMEText(mail["body"], "plain"))
                server.sendmail(sender, target, msg.as_string())
                print(f"[{idx}/{len(EMAILS)}] OK Sent {mail['category']}: {mail['subject']}")
                sent += 1
                time.sleep(SEND_DELAY_SECONDS)
            except smtplib.SMTPException as e:
                print(f"[{idx}/{len(EMAILS)}] x FAILED {mail['category']}: {mail['subject']} — {e}")
                failed += 1
    except smtplib.SMTPAuthenticationError:
        print("[ERROR] SMTP auth failed. Check SMTP_SENDER_EMAIL and SMTP_APP_PASSWORD in .env.")
        print("        App Password: https://myaccount.google.com/apppasswords")
        print("        (Sender account must have 2-Step Verification enabled, personal Gmail only.)")
        return 0, len(EMAILS)
    except smtplib.SMTPConnectError:
        print(f"[ERROR] Could not connect to {SMTP_SERVER}:{SMTP_PORT}. Check network.")
        return 0, len(EMAILS)
    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] SMTP error: {e}")
        return sent, failed + (len(EMAILS) - sent - failed)
    finally:
        if server:
            try:
                server.quit()
            except Exception:
                pass
    return sent, failed


async def main() -> None:
    sender = os.getenv("SMTP_SENDER_EMAIL", "")
    password = os.getenv("SMTP_APP_PASSWORD", "")
    # Default TARGET = USER_GOOGLE_EMAIL (the agent's mailbox) if SMTP_TARGET_EMAIL not set.
    target = os.getenv("SMTP_TARGET_EMAIL", "") or os.getenv("USER_GOOGLE_EMAIL", "")

    missing = []
    if not sender:
        missing.append("SMTP_SENDER_EMAIL")
    if not password:
        missing.append("SMTP_APP_PASSWORD")
    if not target:
        missing.append("SMTP_TARGET_EMAIL (or USER_GOOGLE_EMAIL)")
    if missing:
        print(f"[ERROR] Missing in .env: {', '.join(missing)}")
        print("        See .env.example for setup instructions.")
        sys.exit(1)

    if sender == target:
        print(f"[WARN] SMTP_SENDER_EMAIL == SMTP_TARGET_EMAIL ({sender}). This is technically")
        print("       a self-send, not the two-account scenario from the spec. Proceed anyway.\n")

    do_clean = "--no-clean" not in sys.argv
    print(f"[*] Sender: {sender}")
    print(f"[*] Target: {target}")
    print(f"[*] Clean:  {do_clean}\n")

    if do_clean:
        await clean(target)

    sent, failed = inject_smtp(sender, password, target)
    print(f"\nDone. {sent} sent, {failed} failed.")

    if sent:
        print(f"[*] Waiting {INDEX_WAIT_SECONDS}s for Gmail to index the new messages...")
        await asyncio.sleep(INDEX_WAIT_SECONDS)
        print("Now run:  python refund_agent.py auto")


if __name__ == "__main__":
    asyncio.run(main())
