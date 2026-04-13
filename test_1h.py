import asyncio
from playwright.async_api import async_playwright

PROXY = {
    'server': 'http://p.webshare.io:80',
    'username': 'rojdumou-rotate',
    'password': 'uu0axi9wjxic'
}

URL_1H = 'https://dexscreener.com/?rankBy=priceChangeH1&order=desc&chainIds=solana&dexIds=pumpswap,pumpfun&minLiq=10000&minMarketCap=100000&minAge=1&profile=1&launchpads=1'

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            proxy={'server': PROXY['server'], 'username': PROXY['username'], 'password': PROXY['password']}
        )
        page = await context.new_page()
        
        print("Loading 1H page...")
        await page.goto(URL_1H, wait_until='domcontentloaded', timeout=45000)
        await asyncio.sleep(10)
        
        await page.screenshot(path='/opt/jayce/test_1h.png')
        print("Screenshot saved: test_1h.png")
        
        rows = await page.query_selector_all('a[href*="/solana/"]')
        print(f"Found {len(rows)} rows")
        
        for i, row in enumerate(rows[:5]):
            text = await row.inner_text()
            lines = [l.strip() for l in text.split('\n') if l.strip()][:3]
            print(f"Row {i+1}: {lines}")
        
        await browser.close()

asyncio.run(test())
