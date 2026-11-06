# Screenshots of the app (desktop + phone) with headless Chrome, and reports JS errors.
import sys, asyncio
from playwright.async_api import async_playwright
OUT = sys.argv[1]
PAGES = sys.argv[2].split(",") if len(sys.argv) > 2 else ["create", "templates", "gallery", "queue", "settings", "help"]
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(channel="chrome")
        for name, vp in (("desk", {"width": 1440, "height": 900}), ("phone", {"width": 390, "height": 844})):
            ctx = await b.new_context(viewport=vp, device_scale_factor=1)
            pg = await ctx.new_page()
            pg.on("pageerror", lambda e: print("JS ERROR:", e))
            pg.on("console", lambda m: m.type == "error" and print("CONSOLE:", m.text))
            for page in PAGES:
                await pg.goto(f"http://localhost:8765/#{page}")
                await pg.wait_for_timeout(2500)
                await pg.screenshot(path=f"{OUT}/{name}-{page}.png", full_page=(name == "phone" and page == "create"))
            await ctx.close()
        await b.close()
asyncio.run(main())
