"""
VOLUME SCRAPER v3.0 - FULL VPS ROTATION
Now includes TRENDING - no extension needed!
"""
import asyncio
import logging
import sqlite3
from datetime import datetime
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s',
    handlers=[logging.FileHandler('/opt/jayce/logs/volume_scraper.log'), logging.StreamHandler()])
logger = logging.getLogger(__name__)

QUEUE_DB = '/opt/jayce/data/queue.db'
PROXY = "http://p.webshare.io:9999"
BASE_FILTERS = "chainIds=solana&dexIds=pumpswap,pumpfun,raydium&minLiq=10000&minMarketCap=100000&minAge=1&profile=0&launchpads=1"

URLS = {
    'TRENDING': f'https://dexscreener.com/?rankBy=trendingScoreH6&order=desc&{BASE_FILTERS}',
    'VOL_5M': f'https://dexscreener.com/?rankBy=volume5m&order=desc&{BASE_FILTERS}',
    'VOL_1H': f'https://dexscreener.com/?rankBy=volume1h&order=desc&{BASE_FILTERS}',
}

LIMITS = {
    'TRENDING': 100,
    'VOL_5M': 50,
    'VOL_1H': 50,
}

CYCLE_COUNT = 0

def init_db():
    conn = sqlite3.connect(QUEUE_DB)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS token_queue (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, symbol TEXT, pair_address TEXT, contract_address TEXT, source TEXT, rank INTEGER, url TEXT, processed INTEGER DEFAULT 0, has_screenshot INTEGER DEFAULT 0)")
    conn.commit()
    conn.close()

def save_tokens(tokens, source):
    conn = sqlite3.connect(QUEUE_DB)
    c = conn.cursor()
    c.execute("DELETE FROM token_queue WHERE source=?", (source,))
    for t in tokens:
        c.execute("INSERT INTO token_queue (timestamp, symbol, pair_address, contract_address, source, rank, url, processed) VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
            (datetime.now().isoformat(), t['symbol'], t['pair_address'], '', source, t['rank'], t['url']))
    conn.commit()
    conn.close()

async def scrape_single_page(url, source, limit=50):
    stats = {'source': source, 'raw': 0, 'cpmm_clmm': 0, 'final': 0, 'tokens': []}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, proxy={"server": PROXY}, args=['--disable-blink-features=AutomationControlled'])
        context = await browser.new_context(user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36', viewport={'width': 1920, 'height': 1080})
        stealth = Stealth()
        await stealth.apply_stealth_async(context)
        page = await context.new_page()
        try:
            logger.info(f"    [{source}] Loading DexScreener...")
            await page.goto(url, timeout=90000)
            await asyncio.sleep(15)
            
            # Scroll more for TRENDING to load 100 tokens
            scroll_count = 10 if source == 'TRENDING' else 5
            for _ in range(scroll_count):
                await page.evaluate('window.scrollBy(0, 1000)')
                await asyncio.sleep(0.5)
            await asyncio.sleep(3)
            
            rows = await page.query_selector_all('a[href^="/solana/"]')
            stats['raw'] = len(rows)
            tokens = []
            seen = set()
            rank = 0
            for row in rows:
                if len(tokens) >= limit:
                    break
                try:
                    href = await row.get_attribute('href')
                    if not href or '/solana/' not in href:
                        continue
                    pair = href.split('/solana/')[-1].split('?')[0].split('/')[0]
                    if pair in seen or len(pair) < 30:
                        continue
                    text = await row.inner_text()
                    text_lower = text.lower()
                    if 'cpmm' in text_lower or 'clmm' in text_lower:
                        stats['cpmm_clmm'] += 1
                        continue
                    seen.add(pair)
                    lines = text.strip().split('\n')
                    symbol = lines[0] if lines else '???'
                    if symbol.startswith('#'):
                        symbol = lines[1] if len(lines) > 1 else '???'
                    symbol = symbol[:20]
                    rank += 1
                    tokens.append({'symbol': symbol, 'pair_address': pair, 'rank': rank, 'url': f'https://dexscreener.com/solana/{pair}'})
                except:
                    continue
            stats['final'] = len(tokens)
            stats['tokens'] = tokens
            logger.info(f"    [{source}] Raw: {stats['raw']} | CPMM/CLMM removed: {stats['cpmm_clmm']} | Final: {stats['final']}")
            if tokens:
                logger.info(f"    [{source}] Top tokens: {', '.join([t['symbol'] for t in tokens[:10]])}")
                save_tokens(tokens, source)
        except Exception as e:
            logger.error(f"    [{source}] Error: {e}")
        finally:
            await browser.close()
    return stats

async def run_scraper_cycle():
    global CYCLE_COUNT
    CYCLE_COUNT += 1
    
    logger.info("")
    logger.info("=" * 70)
    logger.info(f"  ROTATION CYCLE #{CYCLE_COUNT} — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 70)
    
    init_db()
    
    # 1. TRENDING (100 tokens)
    logger.info("")
    logger.info(f"  [1/3] TRENDING (H6 Score)")
    stats_trending = await scrape_single_page(URLS['TRENDING'], 'TRENDING', LIMITS['TRENDING'])
    await asyncio.sleep(3)
    
    # 2. 5M VOLUME (50 tokens)
    logger.info("")
    logger.info(f"  [2/3] 5M VOLUME MOVERS")
    stats_5m = await scrape_single_page(URLS['VOL_5M'], 'VOL_5M', LIMITS['VOL_5M'])
    await asyncio.sleep(3)
    
    # 3. 1H VOLUME (50 tokens)
    logger.info("")
    logger.info(f"  [3/3] 1H VOLUME MOVERS")
    stats_1h = await scrape_single_page(URLS['VOL_1H'], 'VOL_1H', LIMITS['VOL_1H'])
    
    total = stats_trending['final'] + stats_5m['final'] + stats_1h['final']
    
    logger.info("")
    logger.info("-" * 70)
    logger.info(f"  ROTATION COMPLETE")
    logger.info(f"    TRENDING:  {stats_trending['final']}")
    logger.info(f"    5M VOLUME: {stats_5m['final']}")
    logger.info(f"    1H VOLUME: {stats_1h['final']}")
    logger.info(f"    TOTAL:     {total} tokens ready for scanner")
    logger.info("-" * 70)
    logger.info("")
    
    return stats_trending, stats_5m, stats_1h

async def main():
    logger.info("")
    logger.info("*" * 70)
    logger.info("  JAYCE VOLUME SCRAPER v3.0 - FULL VPS ROTATION")
    logger.info("  Rotation: TRENDING -> 5M Volume -> 1H Volume -> repeat")
    logger.info("  No extension needed - all on VPS!")
    logger.info("*" * 70)
    while True:
        try:
            await run_scraper_cycle()
        except Exception as e:
            logger.error(f"Cycle error: {e}")
        logger.info("  Next rotation in 5 minutes...")
        await asyncio.sleep(300)

if __name__ == '__main__':
    asyncio.run(main())
