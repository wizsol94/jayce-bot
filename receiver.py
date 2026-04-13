from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import os
import base64
from datetime import datetime
import threading
import time
import requests

app = Flask(__name__)
CORS(app)

API_KEY = 'jayce_collector_2026_secret_key'
QUEUE_DB = '/opt/jayce/data/queue.db'
SCREENSHOTS_DIR = '/opt/jayce/data/screenshots'
last_heartbeat = datetime.now()
alert_sent = False

# Ensure screenshots directory exists
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

def init_db():
    conn = sqlite3.connect(QUEUE_DB)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS token_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, symbol TEXT,
        pair_address TEXT, contract_address TEXT, source TEXT, rank INTEGER,
        url TEXT, processed INTEGER DEFAULT 0, has_screenshot INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS receiver_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, event TEXT, details TEXT)''')
    conn.commit()
    conn.close()

def log_event(event, details):
    try:
        conn = sqlite3.connect(QUEUE_DB)
        c = conn.cursor()
        c.execute('INSERT INTO receiver_logs (timestamp, event, details) VALUES (?,?,?)',
                  (datetime.now().isoformat(), event, str(details)[:500]))
        conn.commit()
        conn.close()
    except: pass

def send_telegram(msg):
    try:
        token = os.getenv('TELEGRAM_BOT_TOKEN', '')
        chat = os.getenv('TELEGRAM_CHAT_ID', '')
        if token and chat:
            requests.post(f'https://api.telegram.org/bot{token}/sendMessage',
                         data={'chat_id': chat, 'text': msg, 'parse_mode': 'HTML'}, timeout=10)
    except: pass


@app.route('/download/extension', methods=['GET'])
def download_extension():
    """Download the Chrome extension ZIP"""
    import io
    zip_path = '/opt/jayce/chrome-extension.zip'
    if os.path.exists(zip_path):
        with open(zip_path, 'rb') as f:
            return f.read(), 200, {
                'Content-Type': 'application/zip',
                'Content-Disposition': 'attachment; filename=jayce-extension.zip'
            }
    return jsonify({'error': 'Extension not found'}), 404

@app.route('/heartbeat', methods=['POST', 'OPTIONS'])
def heartbeat():
    if request.method == 'OPTIONS':
        return '', 200
    global last_heartbeat, alert_sent
    if request.headers.get('X-API-Key') != API_KEY:
        return jsonify({'error': 'Unauthorized'}), 401
    last_heartbeat = datetime.now()
    alert_sent = False
    return jsonify({'status': 'ok'})

@app.route('/tokens', methods=['POST', 'OPTIONS'])
def receive_tokens():
    if request.method == 'OPTIONS':
        return '', 200
    if request.headers.get('X-API-Key') != API_KEY:
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        data = request.json
        tokens = data.get('tokens', [])
        source_counts = data.get('source_counts', {})
        
        conn = sqlite3.connect(QUEUE_DB)
        c = conn.cursor()
        source = tokens[0].get('source', '') if tokens else ''
        c.execute('DELETE FROM token_queue WHERE processed = 0 AND source = ?', (source,))
        
        for t in tokens:
            c.execute('INSERT INTO token_queue (timestamp,symbol,pair_address,contract_address,source,rank,url,processed,has_screenshot) VALUES (?,?,?,?,?,?,?,0,0)',
                (datetime.now().isoformat(), t.get('symbol',''), t.get('pair_address',''),
                 t.get('contract_address',''), t.get('source',''), t.get('rank',0), t.get('url','')))
        
        conn.commit()
        conn.close()
        
        log_event('tokens_received', f"{len(tokens)} tokens | {source_counts}")
        print(f"[RECEIVER] Got {len(tokens)} tokens: TREND={source_counts.get('TRENDING',0)} 5M={source_counts.get('VOL_5M',0)} 1H={source_counts.get('VOL_1H',0)}")
        
        return jsonify({'status': 'ok', 'received': len(tokens)})
    except Exception as e:
        log_event('error', str(e))
        return jsonify({'error': str(e)}), 500

@app.route('/screenshot', methods=['POST', 'OPTIONS'])
def receive_screenshot():
    if request.method == 'OPTIONS':
        return '', 200
    if request.headers.get('X-API-Key') != API_KEY:
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        data = request.json
        pair_address = data.get('pair_address', '')
        image_data = data.get('image_data', '')
        
        if not pair_address or not image_data:
            return jsonify({'error': 'Missing data'}), 400
        
        # Save screenshot as PNG file
        if image_data.startswith('data:image/png;base64,'):
            image_data = image_data.replace('data:image/png;base64,', '')
        
        image_bytes = base64.b64decode(image_data)
        filepath = os.path.join(SCREENSHOTS_DIR, f"{pair_address}.png")
        
        with open(filepath, 'wb') as f:
            f.write(image_bytes)
        
        # Mark token as having screenshot
        conn = sqlite3.connect(QUEUE_DB)
        c = conn.cursor()
        c.execute('UPDATE token_queue SET has_screenshot = 1 WHERE pair_address = ?', (pair_address,))
        conn.commit()
        conn.close()
        
        log_event('screenshot_received', pair_address[:20])
        print(f"[RECEIVER] Screenshot saved: {pair_address[:20]}...")
        
        return jsonify({'status': 'ok', 'saved': filepath})
    except Exception as e:
        log_event('screenshot_error', str(e))
        return jsonify({'error': str(e)}), 500

@app.route('/queue', methods=['GET'])
def get_queue():
    if request.headers.get('X-API-Key') != API_KEY:
        return jsonify({'error': 'Unauthorized'}), 401
    conn = sqlite3.connect(QUEUE_DB)
    c = conn.cursor()
    c.execute('SELECT id,timestamp,symbol,pair_address,contract_address,source,rank,url,has_screenshot FROM token_queue WHERE processed=0 ORDER BY rank')
    rows = c.fetchall()
    conn.close()
    tokens = [{'id':r[0],'timestamp':r[1],'symbol':r[2],'pair_address':r[3],'contract_address':r[4],'source':r[5],'rank':r[6],'url':r[7],'has_screenshot':r[8]} for r in rows]
    return jsonify({'tokens': tokens, 'count': len(tokens)})

@app.route('/get_screenshot/<pair_address>', methods=['GET'])
def get_screenshot(pair_address):
    filepath = os.path.join(SCREENSHOTS_DIR, f"{pair_address}.png")
    if os.path.exists(filepath):
        with open(filepath, 'rb') as f:
            return f.read(), 200, {'Content-Type': 'image/png'}
    return jsonify({'error': 'Not found'}), 404

@app.route('/status', methods=['GET'])
def status():
    age = (datetime.now() - last_heartbeat).total_seconds()
    screenshot_count = len([f for f in os.listdir(SCREENSHOTS_DIR) if f.endswith('.png')]) if os.path.exists(SCREENSHOTS_DIR) else 0
    return jsonify({
        'status': 'ok', 
        'heartbeat_age': age, 
        'collector_online': age < 180,
        'screenshots_stored': screenshot_count
    })

def monitor():
    global alert_sent
    while True:
        time.sleep(30)
        age = (datetime.now() - last_heartbeat).total_seconds()
        if age > 180 and not alert_sent:
            send_telegram("⚠️ <b>Collector Offline</b>\nNo heartbeat in 3+ min. Check iMac!")
            alert_sent = True
            log_event('alert', 'Collector offline')


# ══════════════════════════════════════════════════════════════════════════════
# WHALE WATCHLIST ENDPOINT
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/whale', methods=['POST', 'OPTIONS'])
def receive_whale():
    if request.method == 'OPTIONS':
        return '', 200
    
    if request.headers.get('X-API-Key') != API_KEY:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.json
    if not data:
        return jsonify({'error': 'No data'}), 400
    
    token_address = data.get('token_address', '')
    pair_address = data.get('pair_address', '')
    symbol = data.get('symbol', '???')
    whale_wallet = data.get('whale_wallet', '')
    buy_amount_sol = data.get('buy_amount_sol', 0)
    
    if not token_address and not pair_address:
        return jsonify({'error': 'Need token_address or pair_address'}), 400
    
    # AUTO-FETCH pair_address if missing
    if token_address and not pair_address:
        try:
            import httpx
            resp = httpx.get(f'https://api.dexscreener.com/latest/dex/tokens/{token_address}', timeout=10)
            if resp.status_code == 200:
                pairs = resp.json().get('pairs', [])
                sol_pairs = [p for p in pairs if p.get('chainId') == 'solana']
                if sol_pairs:
                    sol_pairs.sort(key=lambda x: float(x.get('liquidity', {}).get('usd', 0) or 0), reverse=True)
                    pair_address = sol_pairs[0].get('pairAddress', '')
                    print(f"   🔍 Auto-fetched pair_address for {symbol}: {pair_address[:20]}...")
        except Exception as e:
            print(f"   ⚠️ Could not auto-fetch pair_address: {e}")
    
    try:
        conn = sqlite3.connect(QUEUE_DB)
        c = conn.cursor()
        
        # Check if already in watchlist
        c.execute("SELECT id FROM whale_watchlist WHERE token_address = ? AND expired = 0", (token_address,))
        existing = c.fetchone()
        
        if existing:
            c.execute("""
                UPDATE whale_watchlist 
                SET timestamp = ?, whale_wallet = ?, buy_amount_sol = buy_amount_sol + ?, processed = 0
                WHERE id = ?
            """, (datetime.now().isoformat(), whale_wallet, buy_amount_sol, existing[0]))
            action = 'updated'
        else:
            c.execute("""
                INSERT INTO whale_watchlist 
                (timestamp, token_address, pair_address, symbol, whale_wallet, buy_amount_sol, processed, scan_count, expired)
                VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0)
            """, (datetime.now().isoformat(), token_address, pair_address, symbol, whale_wallet, buy_amount_sol))
            action = 'added'
        
        conn.commit()
        conn.close()
        
        print(f"🐋 WHALE: {symbol} ({token_address[:8]}...) - {whale_wallet[:8]}... bought {buy_amount_sol} SOL [{action}]")
        
        return jsonify({'status': 'ok', 'action': action, 'symbol': symbol}), 200
        
    except Exception as e:
        print(f"Whale endpoint error: {e}")
        return jsonify({'error': str(e)}), 500



# ══════════════════════════════════════════════════════════════════════════════
# TELEGRAM CALLBACK HANDLER - For scan monitor inline buttons
# ══════════════════════════════════════════════════════════════════════════════
@app.route('/telegram_callback', methods=['POST'])
def handle_telegram_callback():
    """Handle Telegram inline button callbacks."""
    try:
        from scan_monitor import handle_callback
        import requests
        
        data = request.get_json()
        callback_query = data.get('callback_query', {})
        
        if not callback_query:
            return jsonify({'status': 'no callback'}), 200
        
        callback_id = callback_query.get('id')
        callback_data = callback_query.get('data', '')
        message = callback_query.get('message', {})
        message_id = message.get('message_id')
        
        # Handle the callback
        success = handle_callback(callback_data, message_id)
        
        # Answer the callback to remove loading state
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        if bot_token and callback_id:
            requests.post(
                f'https://api.telegram.org/bot{bot_token}/answerCallbackQuery',
                json={'callback_query_id': callback_id},
                timeout=5
            )
        
        return jsonify({'status': 'ok', 'handled': success}), 200
        
    except Exception as e:
        print(f"Callback error: {e}")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    init_db()
    print("=" * 50)
    print("JAYCE RECEIVER v2.0")
    print("Listening on port 5000")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000)
