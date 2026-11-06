# Renders the home page like the user's screen (1280x720 logical at 150% scaling) and looks for thin vertical lines.
import sys, asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(channel="chrome")
        pg = await (await b.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1.5)).new_page()
        await pg.goto("http://localhost:8765/#create"); await pg.wait_for_timeout(2500)
        await pg.screenshot(path=sys.argv[1])
        await b.close()
asyncio.run(main())
