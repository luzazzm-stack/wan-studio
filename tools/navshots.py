# Screenshots of the four menu styles.
import sys, asyncio
from playwright.async_api import async_playwright
OUT = sys.argv[1]
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(channel="chrome")
        pg = await (await b.new_context(viewport={"width": 1440, "height": 820})).new_page()
        pg.on("pageerror", lambda e: print("JS ERROR:", e))
        await pg.goto("http://localhost:8765/#create"); await pg.wait_for_timeout(2500)
        for n in "abcd":
            await pg.evaluate("n => { document.documentElement.dataset.nav = n; document.querySelectorAll('#navPick button[data-nav]').forEach(b => b.classList.toggle('on', b.dataset.nav === n)); }", n)
            await pg.wait_for_timeout(500)
            await pg.screenshot(path=f"{OUT}/nav-{n}.png")
        await b.close()
asyncio.run(main())
