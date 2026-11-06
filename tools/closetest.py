import asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(channel="chrome")
        pg = await (await b.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1.5)).new_page()
        await pg.goto("http://localhost:8765/#gallery"); await pg.wait_for_timeout(2500)
        await pg.click("#galGrid .thumb"); await pg.wait_for_timeout(800)
        print("viewer open:", await pg.is_visible("#viewer"))
        await pg.click("#viewer .x iconify-icon"); await pg.wait_for_timeout(500)
        print("after clicking the X icon, viewer open:", await pg.is_visible("#viewer"))
        await b.close()
asyncio.run(main())
