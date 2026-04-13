"""
FLASHCARD IMAGE RECOVERY SCRIPT
===============================
Safely recovers flashcard images from Telegram.

SAFETY GUARANTEES:
- Does NOT modify any JSON files
- Does NOT delete anything
- Only ADDS missing .jpg files
- Logs all actions
- Can be re-run safely (skips existing files)
"""

import os
import json
import asyncio
import httpx
from datetime import datetime
from dotenv import load_dotenv

load_dotenv('/opt/jayce/.env')

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
FLASHCARD_DIR = '/opt/jayce/flashcards'
TRAINING_DATA = '/opt/jayce/data/jayce_training_dataset.json'
LOG_FILE = '/opt/jayce/flashcard_recovery.log'

# Setup folder mapping
SETUP_FOLDERS = {
    '382': '382',
    '50': '50',
    '618': '618',
    '786': '786',
    'Under-Fib': 'Under-Fib',
    'UNDER_FIB': 'Under-Fib'
}

def log(msg):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, 'a') as f:
        f.write(line + '\n')

async def download_image(client, file_id, save_path):
    """Download image from Telegram using file_id."""
    try:
        # Get file path
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile?file_id={file_id}"
        resp = await client.get(url, timeout=30)
        data = resp.json()
        
        if not data.get('ok'):
            return False, f"getFile failed: {data.get('description', 'unknown')}"
        
        file_path = data['result']['file_path']
        
        # Download file
        download_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
        file_resp = await client.get(download_url, timeout=60)
        
        if file_resp.status_code != 200:
            return False, f"Download failed: HTTP {file_resp.status_code}"
        
        # Save file
        with open(save_path, 'wb') as f:
            f.write(file_resp.content)
        
        return True, len(file_resp.content)
    
    except Exception as e:
        return False, str(e)

async def recover_all_images(dry_run=False):
    """Recover all missing flashcard images."""
    
    log("=" * 60)
    log("FLASHCARD IMAGE RECOVERY STARTED")
    log(f"Dry run: {dry_run}")
    log("=" * 60)
    
    # Load training data
    with open(TRAINING_DATA, 'r') as f:
        cards = json.load(f)
    
    log(f"Total flashcards in training data: {len(cards)}")
    
    stats = {
        'total': len(cards),
        'already_exists': 0,
        'downloaded': 0,
        'failed': 0,
        'no_fingerprint': 0,
        'by_setup': {},
        'failures': []
    }
    
    async with httpx.AsyncClient() as client:
        for i, card in enumerate(cards):
            chart_id = card.get('chart_id', '')
            fib_depth = card.get('fib_depth', '')
            file_id = card.get('screenshot_fingerprint_id', '')
            token = card.get('token', '???')
            
            # Track by setup type
            if fib_depth not in stats['by_setup']:
                stats['by_setup'][fib_depth] = {'total': 0, 'downloaded': 0, 'exists': 0, 'failed': 0}
            stats['by_setup'][fib_depth]['total'] += 1
            
            if not file_id:
                log(f"  SKIP {chart_id}: No fingerprint ID")
                stats['no_fingerprint'] += 1
                continue
            
            # Determine save path
            folder = SETUP_FOLDERS.get(fib_depth, fib_depth)
            folder_path = f"{FLASHCARD_DIR}/{folder}"
            file_name = chart_id.replace('/', '_') + '.jpg'
            save_path = f"{folder_path}/{file_name}"
            
            # Check if already exists
            if os.path.exists(save_path):
                stats['already_exists'] += 1
                stats['by_setup'][fib_depth]['exists'] += 1
                continue
            
            # Ensure folder exists
            os.makedirs(folder_path, exist_ok=True)
            
            if dry_run:
                log(f"  [DRY RUN] Would download: {fib_depth}/{token} -> {file_name}")
                stats['downloaded'] += 1
                stats['by_setup'][fib_depth]['downloaded'] += 1
                continue
            
            # Download
            success, result = await download_image(client, file_id, save_path)
            
            if success:
                log(f"  ✅ {fib_depth}/{token}: {result:,} bytes -> {file_name}")
                stats['downloaded'] += 1
                stats['by_setup'][fib_depth]['downloaded'] += 1
            else:
                log(f"  ❌ {fib_depth}/{token}: {result}")
                stats['failed'] += 1
                stats['by_setup'][fib_depth]['failed'] += 1
                stats['failures'].append({'chart_id': chart_id, 'token': token, 'fib_depth': fib_depth, 'error': result})
            
            # Rate limit: avoid hitting Telegram limits
            if (i + 1) % 10 == 0:
                log(f"  Progress: {i + 1}/{len(cards)}")
                await asyncio.sleep(1)
            else:
                await asyncio.sleep(0.2)
    
    log("=" * 60)
    log("RECOVERY COMPLETE")
    log(f"  Total cards: {stats['total']}")
    log(f"  Already existed: {stats['already_exists']}")
    log(f"  Downloaded: {stats['downloaded']}")
    log(f"  Failed: {stats['failed']}")
    log(f"  No fingerprint: {stats['no_fingerprint']}")
    log("")
    log("BY SETUP TYPE:")
    for setup, data in sorted(stats['by_setup'].items()):
        log(f"  {setup}: {data['downloaded']} downloaded, {data['exists']} existed, {data['failed']} failed (total: {data['total']})")
    
    if stats['failures']:
        log("")
        log("FAILED ENTRIES:")
        for f in stats['failures']:
            log(f"  - {f['chart_id']}: {f['error']}")
    
    log("=" * 60)
    
    return stats

if __name__ == '__main__':
    import sys
    dry_run = '--dry-run' in sys.argv
    asyncio.run(recover_all_images(dry_run=dry_run))
