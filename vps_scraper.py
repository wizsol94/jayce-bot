"""
VPS DEXSCREENER SCRAPER v3.3
- Fixed symbol extraction (skip rank numbers like #1, #2)
- TRENDING: 200 tokens
- 5M/1H: 50 tokens each
"""

import asyncio
import sqlite3
import logging
from datetime import datetime
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

QUEUE_DB = '/opt/jayce/data/queue.db'

PROXY = {
    'server': 'http://p.webshare.io:80',
    'username': 'rojdumou-rotate',
    'password': 'uu0axi9wjxic'
}

URLS = {
    'TRENDING': {
        'url': 'https://dexscreener.com/?rankBy=trendingScoreH6&order=desc&chainIds=solana&dexIds=pumpswap,pumpfun&minLiq=10000&minMarketCap=100000&minAge=1&profile=1&launchpads=1',
        'max': 200
    },
    'VOL_5M': {
        'url': 'https://dexscreener.com/?rankBy=priceChangeM5&order=desc&chainIds=solana&dexIds=pumpswap,pumpfun&minLiq=10000&minMarketCap=100000&minAge=1&profile=1&launchpads=1',
        'max': 50
    },
    'VOL_1H': {
        'url': 'https://dexscreener.com/?rankBy=priceChangeH1&order=desc&chainIds=solana&dexIds=pumpswap,pumpfun&minLiq=10000&minMarketCap=100000&minAge=1&profile=1&launchpads=1',
        'max': 50
    }
}

SCRAPE_INTERVAL = 300

async def scroll_and_load(page, target_count):
    for _ in range(20):
        rows = await page.query_selector_all('a[href*="/solana/"]')
        if len(rows) >= target_count:
            break
        await page.evaluate('window.scrollBy(0, 1000)')
        await asyncio.sleep(0.5)
    return len(await page.query_selector_all('a[href*="/solana/"]'))

async def extract_tokens(page, source, max_tokens):
    tokens = []
    rows = await page.query_selector_all('a[href*="/solana/"]')
    seen = set()
    rank = 0
    
    for row in rows:
        try:
            href = await row.get_attribute('href')
            if not href or '/solana/' not in href:
                continue
            parts = href.split('/solana/')
            if len(parts) < 2:
                continue
            pair_address = parts[1].split('?')[0].split('/')[0]
            if len(pair_address) < 30 or pair_address in seen:
                continue
            seen.add(pair_address)
            rank += 1
            
            text = await row.inner_text()
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            symbol = '???'
            
            for line in lines:
                clean = line.split('/')[0].split(' ')[0].strip()
                # Skip rank numbers like #1, #2, etc
                if clean.startswith('#') and clean[1:].isdigit():
                    continue
                # Skip pure numbers
                if clean.replace(',', '').replace('.', '').isdigit():
                    continue
                # Skip common non-symbol text
                if clean in ['SOL', 'USD', '/', '']:
                    continue
                # Valid symbol check
                if 2 <= len(clean) <= 20 and '$' not in clean and '%' not in clean:
                    symbol = clean
                    break
            
            tokens.append({
                'symbol': symbol,
                'pair_address': pair_address,
                'source': source,
                'rank': rank,
                'url': f'https://dexscreener.com/solana/{pair_address}'
            })
            if rank >= max_tokens:
                break
        except:
            continue
    return tokens

def save_tokens(tokens, source):
    if not tokens:
        return
    try:
        conn = sqlite3.connect(QUEUE_DB)
        c = conn.cursor()
        c.execute('DELETE FROM token_queue WHERE source = ? AND processed = 0', (source,))
        for t in tokens:
            c.execute('INSERT INTO token_queue (timestamp, symbol, pair_address, contract_address, source, rank, url, processed, has_screenshot) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0)',
                (datetime.now().isoformat(), t['symbol'], t['pair_address'], '', source, t['rank'], t['url']))
        conn.commit()
        conn.close()
        logger.info(f"[SCRAPER] Saved {len(tokens)} {source} tokens")
    except Exception as e:
        logger.error(f"[SCRAPER] DB error: {e}")

async def scrape_source(browser, source, config):
    try:
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            proxy={'server': PROXY['server'], 'username': PROXY['username'], 'password': PROXY['password']}
        )
        page = await context.new_page()
        
        logger.info(f"[SCRAPER] === {source} ({config['max']}) ===")
        response = await page.goto(config['url'], wait_until='domcontentloaded', timeout=45000)
        logger.info(f"[SCRAPER] {source}: Status {response.status if response else '?'}")
        
        await asyncio.sleep(8)
        loaded = await scroll_and_load(page, config['max'])
        logger.info(f"[SCRAPER] {source}: Loaded {loaded} rows")
        
        tokens = await extract_tokens(page, source, config['max'])
        if tokens:
            save_tokens(tokens, source)
        logger.info(f"[SCRAPER] {source}: {len(tokens)} tokens")
        
        await context.close()
        return len(tokens)
    except Exception as e:
        logger.error(f"[SCRAPER] Error {source}: {e}")
        return 0

async def scrape_all():
    logger.info("[SCRAPER] ═══════════════════════════════════════════")
    logger.info("[SCRAPER] Starting cycle (v3.3)...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'])
        
        total = 0
        for source, config in URLS.items():
            count = await scrape_source(browser, source, config)
            total += count
            await asyncio.sleep(5)
        
        await browser.close()
    
    logger.info(f"[SCRAPER] Cycle complete: {total} tokens")
    logger.info("[SCRAPER] ═══════════════════════════════════════════")
    return total

async def run_loop():
    logger.info("[SCRAPER] VPS Scraper v3.3 starting...")
    while True:
        try:
            await scrape_all()
        except Exception as e:
            logger.error(f"[SCRAPER] Error: {e}")
        await asyncio.sleep(SCRAPE_INTERVAL)

def run_once():
    asyncio.run(scrape_all())

if __name__ == '__main__':
    asyncio.run(run_loop())
