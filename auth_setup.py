"""One-time OAuth setup — authenticates both Calendar and Gmail in one flow."""

import asyncio
import os
import re
import sys

from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


async def auth_service(service_name: str, permissions: list[str], test_tool: str, test_args: dict):
    """Authenticate a single service by starting MCP server and triggering OAuth."""
    email = os.getenv("USER_GOOGLE_EMAIL", "")
    env = {
        "GOOGLE_OAUTH_CLIENT_ID": os.getenv("GOOGLE_OAUTH_CLIENT_ID", ""),
        "GOOGLE_OAUTH_CLIENT_SECRET": os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", ""),
        "USER_GOOGLE_EMAIL": email,
        "OAUTHLIB_INSECURE_TRANSPORT": os.getenv("OAUTHLIB_INSECURE_TRANSPORT", "1"),
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "APPDATA": os.environ.get("APPDATA", ""),
        "LOCALAPPDATA": os.environ.get("LOCALAPPDATA", ""),
        "USERPROFILE": os.environ.get("USERPROFILE", ""),
    }

    args = ["workspace-mcp", "--single-user"] + permissions

    server_params = StdioServerParameters(command="uvx", args=args, env=env)

    print(f"\n{'='*60}")
    print(f"  {service_name} Authentication")
    print(f"{'='*60}")
    print(f"[*] Starting MCP server for {service_name}...")

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            tool_names = [t.name for t in tools.tools]
            print(f"[OK] Tools: {tool_names}")

            print(f"[*] Calling {test_tool} to test auth...")
            result = await session.call_tool(test_tool, test_args)

            for item in result.content:
                text = item.text if hasattr(item, "text") else str(item)
                if "accounts.google.com" in text:
                    urls = re.findall(r'https://accounts\.google\.com/o/oauth2/auth\S+', text)
                    if urls:
                        url = urls[0].rstrip(")").rstrip("]")
                        print(f"\n[!] Open this URL in your browser:\n")
                        print(url)
                        print(f"\n  1. Log in with {email}")
                        print(f"  2. If 'app not verified' -> Advanced -> Go to (unsafe)")
                        print(f"  3. Grant all {service_name} permissions")
                        print(f"  4. Wait for 'success' in browser\n")
                        input(">>> Press Enter AFTER you see success... ")

                        print(f"[*] Retrying {test_tool}...")
                        result2 = await session.call_tool(test_tool, test_args)
                        for item2 in result2.content:
                            t2 = item2.text if hasattr(item2, "text") else str(item2)
                            if "error" not in t2.lower()[:30]:
                                print(f"[OK] {t2[:300]}")
                        return True
                elif "error" in text.lower()[:30]:
                    print(f"[WARN] {text[:300]}")
                else:
                    print(f"[OK] {text[:300]}")
                    return True

    return True


async def main():
    email = os.getenv("USER_GOOGLE_EMAIL", "")
    if not email:
        print("[ERROR] Set USER_GOOGLE_EMAIL in .env")
        sys.exit(1)

    print(f"AI Workspace Agent Suite — OAuth Setup")
    print(f"Account: {email}\n")

    # Auth Calendar (all scopes in one flow)
    await auth_service(
        "Google Calendar",
        [],  # no restrictions = all scopes
        "list_calendars",
        {},
    )

    # Auth Gmail
    await auth_service(
        "Google Gmail",
        ["--tool-tier", "core", "--permissions", "gmail:send"],
        "search_gmail_messages",
        {"query": "is:unread"},
    )

    print(f"\n{'='*60}")
    print("  Setup Complete!")
    print(f"{'='*60}")
    print("You can now run:")
    print("  python calendar_agent.py       # interactive mode")
    print("  python calendar_agent.py demo  # demo mode")
    print("  python refund_agent.py         # interactive mode")
    print("  python refund_agent.py auto    # auto-process emails")


if __name__ == "__main__":
    asyncio.run(main())
