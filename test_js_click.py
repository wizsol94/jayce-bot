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
        
        print("Loading trending page...")
        await page.goto(BASE_URL, wait_until='networkidle', timeout=60000)
        await asyncio.sleep(5)
        
        rows = await page.query_selector_all('a[href*="/solana/"]')
        print(f"Before click: {len(rows)} rows")
        
        # Get first 3 symbols before
        for i, row in enumerate(rows[:3]):
            text = await row.inner_text()
            symbol = [l.strip() for l in text.split('\n') if l.strip()][0]
            print(f"  {i+1}. {symbol}")
        
        # Try JavaScript click on 1H column
        print("\nClicking 1H column via JavaScript...")
        result = await page.evaluate('''() => {
            // Find all column headers
            const headers = document.querySelectorAll('th, [role="columnheader"], button, div, span');
            for (const h of headers) {
                if (h.textContent.trim() === '1H' || h.textContent.trim() === '1H ▼' || h.textContent.trim() === '1H ▲') {
                    h.click();
                    return "clicked 1H";
                }
            }
            // Try finding by partial match
            for (const h of headers) {
                if (h.textContent.includes('1H')) {
                    h.click();
                    return "clicked element containing 1H: " + h.textContent.trim();
                }
            }
            return "not found";
        }''')
        print(f"Result: {result}")
        
        # Wait for re-render
        await asyncio.sleep(5)
        
        rows = await page.query_selector_all('a[href*="/solana/"]')
        print(f"\nAfter click: {len(rows)} rows")
        
        if len(rows) > 0:
            # Get first 5 symbols after
            for i, row in enumerate(rows[:5]):
                text = await row.inner_text()
                lines = [l.strip() for l in text.split('\n') if l.strip()]
                symbol = '???'
                for line in lines:
                    if not line.startswith('#') and len(line) >= 2 and '$' not in line and '%' not in line:
                        symbol = line.split('/')[0].strip()
                        break
                print(f"  {i+1}. {symbol}")
        
        await page.screenshot(path='/opt/jayce/js_click_test.png')
        print("\nScreenshot saved: js_click_test.png")
        
        await browser.close()

asyncio.run(test())
