import sys, asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(channel="chrome")
        pg = await (await b.new_context(viewport={"width": 1440, "height": 900})).new_page()
        pg.on("pageerror", lambda e: print("JS ERROR:", e))
        await pg.goto("http://localhost:8765/#enhance"); await pg.wait_for_timeout(2000)
        await pg.set_input_files("#vfile", [sys.argv[1], sys.argv[2]])
        await pg.wait_for_timeout(6000)
        await pg.click('#enhSize button[data-s="2k"]'); await pg.check("#enhSmooth", force=True); await pg.wait_for_timeout(500)
        await pg.screenshot(path=sys.argv[3])
        await b.close()
asyncio.run(main())
