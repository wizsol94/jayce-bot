import asyncio
from playwright.async_api import async_playwright

PROXY = {
    'server': 'http://p.webshare.io:80',
    'username': 'rojdumou-rotate',
    'password': 'uu0axi9wjxic'
}

BASE_URL = 'https://dexscreener.com/?rankBy=trendingScoreH6&order=desc&chainIds=solana&dexIds=pumpswap,pumpfun&minLiq=10000&minMarketCap=100000&minAge=1&profile=1&launchpads=1'

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            proxy={'server': PROXY['server'], 'username': PROXY['username'], 'password': PROXY['password']}
        )
        page = await context.new_page()
        
        print("Loading page...")
        await page.goto(BASE_URL, wait_until='domcontentloaded', timeout=45000)
        await asyncio.sleep(10)
        
        rows_before = await page.query_selector_all('a[href*="/solana/"]')
        print(f"Rows before click: {len(rows_before)}")
        
        # Find and click 5M
        print("Clicking 5M column...")
        clicked = await page.click('text="5M"')
        print("Clicked 5M!")
        
        # Wait longer and check every second
        for i in range(15):
            await asyncio.sleep(1)
            rows = await page.query_selector_all('a[href*="/solana/"]')
            print(f"After {i+1}s: {len(rows)} rows")
            if len(rows) > 50:
                break
        
        await page.screenshot(path='/opt/jayce/after_wait.png')
        print("Screenshot saved: after_wait.png")
        
        await browser.close()

asyncio.run(test())
