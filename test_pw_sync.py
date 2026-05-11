import asyncio
from playwright.sync_api import sync_playwright

async def main():
    try:
        with sync_playwright() as p:
            print("Sync Playwright works")
    except Exception as e:
        print("ERROR:", e)

asyncio.run(main())
