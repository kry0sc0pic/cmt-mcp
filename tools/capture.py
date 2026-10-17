"""Launch a headed browser, let the user log in to Microsoft CMT and browse,
and record every XHR/fetch request + response to captures/session-<ts>.jsonl.

Run: uv run python tools/capture.py [start_url]
Stop: close the browser window or Ctrl+C.
"""
import asyncio, json, sys, time
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
PROFILE = ROOT / ".browser-profile"      # persists login between runs
OUT = ROOT / "captures" / f"session-{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
COOKIES = ROOT / "cookies.json"   # session cookies are live-exported for the MCP server
START = sys.argv[1] if len(sys.argv) > 1 else "https://cmt3.research.microsoft.com/"
CAPTURE_TYPES = {"xhr", "fetch", "document"}
MAX_BODY = 2_000_000


async def main():
    OUT.parent.mkdir(exist_ok=True)
    f = OUT.open("a", buffering=1)
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            str(PROFILE), headless=False, viewport=None, args=["--start-maximized"])

        def save_cookies():
            async def _s():
                cs = [c for c in await ctx.cookies() if "research.microsoft.com" in c["domain"]]
                if cs:
                    COOKIES.write_text(json.dumps(cs, indent=2)); COOKIES.chmod(0o600)
            asyncio.ensure_future(_s())

        async def on_response(resp):
            req = resp.request
            if req.resource_type not in CAPTURE_TYPES:
                return
            try:
                body = await resp.text()
            except Exception:
                body = None
            rec = {
                "t": time.time(),
                "method": req.method,
                "url": req.url,
                "type": req.resource_type,
                "status": resp.status,
                "req_headers": await req.all_headers(),
                "post_data": req.post_data,
                "resp_headers": await resp.all_headers(),
                "body": body[:MAX_BODY] if body else body,
            }
            f.write(json.dumps(rec) + "\n")
            save_cookies()
            print(f"{req.method} {resp.status} {req.resource_type:8} {req.url[:110]}")

        ctx.on("response", lambda r: asyncio.ensure_future(on_response(r)))
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto(START)
        print(f"Recording to {OUT}\nLog in and browse; close the window when done.")
        closed = asyncio.Event()
        ctx.on("close", lambda *_: closed.set())
        await closed.wait()
    f.close()

asyncio.run(main())
