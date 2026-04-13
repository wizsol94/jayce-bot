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
        
        # Screenshot before click
        await page.screenshot(path='/opt/jayce/before_click.png')
        print("Screenshot saved: before_click.png")
        
        rows_before = await page.query_selector_all('a[href*="/solana/"]')
        print(f"Rows before click: {len(rows_before)}")
        
        # Find and click 5M
        print("Clicking 5M column...")
        headers = await page.query_selector_all('th, div, span, button')
        for h in headers:
            try:
                text = await h.inner_text()
                if text.strip() == '5M':
                    await h.click()
                    print("Clicked!")
                    break
            except:
                continue
        
        await asyncio.sleep(8)
        
        # Screenshot after click
        await page.screenshot(path='/opt/jayce/after_click.png')
        print("Screenshot saved: after_click.png")
        
        rows_after = await page.query_selector_all('a[href*="/solana/"]')
        print(f"Rows after click: {len(rows_after)}")
        
        await browser.close()

asyncio.run(test())
