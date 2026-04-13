import asyncio
import httpx
import os
import json

async def scrape_dex():
    BROWSERLESS_API_KEY = os.getenv('BROWSERLESS_API_KEY', '')
    
    url = f"https://chrome.browserless.io/scrape?token={BROWSERLESS_API_KEY}&stealth=true&blockAds=true"
    
    payload = {
        "url": "https://dexscreener.com/?rankBy=trendingScoreH6&order=desc&chainIds=solana",
        "elements": [{"selector": "a"}],
        "waitForSelector": {"selector": "body", "timeout": 30000}
    }
    
    async with httpx.AsyncClient(timeout=120) as client:
        print("Trying stealth + blockAds...")
        resp = await client.post(url, json=payload, headers={"Content-Type": "application/json"})
        
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            all_text = json.dumps(data)
            
            if 'cloudflare' in all_text.lower():
                print("❌ Still hitting Cloudflare block")
            else:
                print("✅ Got past Cloudflare!")
                
            import re
            matches = re.findall(r'/solana/([A-Za-z0-9]{32,50})', all_text)
            print(f"Solana addresses found: {len(set(matches))}")
        else:
            print(f"Error: {resp.text[:300]}")

if __name__ == '__main__':
    with open('/opt/jayce/.env', 'r') as f:
        for line in f:
            if line.startswith('BROWSERLESS_API_KEY='):
                os.environ['BROWSERLESS_API_KEY'] = line.strip().split('=', 1)[1]
    asyncio.run(scrape_dex())
