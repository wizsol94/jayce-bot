# ══════════════════════════════════════════════════════════════════════════════
# JAYCE MONITORING COMMANDS - Owner Only, Private Chat
# ══════════════════════════════════════════════════════════════════════════════

import os
import json
from datetime import datetime
from pathlib import Path

OWNER_USER_ID = os.getenv('OWNER_USER_ID')
DATA_DIR = Path(os.getenv('DATA_DIR', '/opt/jayce/data'))
MONITOR_FILE = DATA_DIR / "monitoring_data.json"

def load_monitor_data() -> dict:
    default = {"debug_mode": False, "missed_setups": [], "daily_stats": {}}
    try:
        if MONITOR_FILE.exists():
            with open(MONITOR_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return default

def save_monitor_data(data: dict):
    try:
        with open(MONITOR_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Error saving monitor data: {e}")

def is_owner(user_id: int) -> bool:
    if not OWNER_USER_ID:
        return False
    return str(user_id) == str(OWNER_USER_ID)

async def daily_command(update, context):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return
    data = load_monitor_data()
    today = datetime.now().strftime("%Y-%m-%d")
    stats = data.get("daily_stats", {}).get(today, {})
    missed = [m for m in data.get("missed_setups", []) if m.get("date") == today]
    report = f"""📊 <b>Daily Report - {today}</b>

<b>Alerts Sent:</b> {stats.get('alerts_sent', 0)}

<b>Missed Setups Logged:</b> {len(missed)}"""
    if missed:
        report += "\n\n<b>Missed:</b>\n"
        for m in missed[-5:]:
            report += f"• {m.get('setup', '?')} - {m.get('token', '?')} ({m.get('time', '')})\n"
    report += f"\n\n<i>Debug: {'ON 🟢' if data.get('debug_mode') else 'OFF 🔴'}</i>"
    await update.message.reply_text(report, parse_mode='HTML')

async def debug_command(update, context):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return
    data = load_monitor_data()
    data["debug_mode"] = not data.get("debug_mode", False)
    save_monitor_data(data)
    status = "ON 🟢" if data["debug_mode"] else "OFF 🔴"
    await update.message.reply_text(f"🔍 <b>Debug Mode: {status}</b>\n\n<i>You'll see scoring details when ON.</i>", parse_mode='HTML')

async def missed_command(update, context):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return
    args = context.args if context.args else []
    if len(args) < 2:
        await update.message.reply_text("📝 <b>Usage:</b> <code>/missed [setup] [token]</code>\n\nExample: <code>/missed 382 SOL</code>", parse_mode='HTML')
        return
    setup_map = {"382": "382 + Flip Zone", "50": "50 + Flip Zone", "618": "618 + Flip Zone", "786": "786 + Flip Zone", "UNDER": "Under-Fib Flip Zone"}
    setup_name = setup_map.get(args[0].upper(), args[0])
    token = args[1].upper()
    data = load_monitor_data()
    entry = {"date": datetime.now().strftime("%Y-%m-%d"), "time": datetime.now().strftime("%H:%M"), "setup": setup_name, "token": token}
    data.setdefault("missed_setups", []).append(entry)
    save_monitor_data(data)
    await update.message.reply_text(f"✅ Logged: {setup_name} - {token}", parse_mode='HTML')

async def monitor_command(update, context):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return
    data = load_monitor_data()
    today = datetime.now().strftime("%Y-%m-%d")
    missed_today = len([m for m in data.get("missed_setups", []) if m.get("date") == today])
    msg = f"""📡 <b>Monitoring Status</b>

🔍 Debug: {'ON 🟢' if data.get('debug_mode') else 'OFF 🔴'}
📝 Missed today: {missed_today}

<b>Commands:</b>
/daily - Daily report
/debug - Toggle debug mode
/missed [setup] [token] - Log missed
/monitor - This screen"""
    await update.message.reply_text(msg, parse_mode='HTML')

def get_debug_mode() -> bool:
    data = load_monitor_data()
    return data.get("debug_mode", False)
