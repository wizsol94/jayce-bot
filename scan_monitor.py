"""
TELEGRAM SCAN MONITOR v3.1

Shows FULL scan details directly - no buttons needed.
3 separate messages for each source with complete token lists.

Does NOT modify scanner logic.
"""

import os
import requests
from datetime import datetime
from typing import List, Dict

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
SCAN_MONITOR_CHAT_ID = os.getenv('HEARTBEAT_CHAT_ID', os.getenv('TELEGRAM_CHAT_ID'))


def send_telegram_message(text: str) -> bool:
    """Send a Telegram message."""
    if not TELEGRAM_BOT_TOKEN or not SCAN_MONITOR_CHAT_ID:
        return False
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    try:
        resp = requests.post(url, json={
            'chat_id': SCAN_MONITOR_CHAT_ID,
            'text': text,
            'parse_mode': 'HTML'
        }, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print(f"Scan monitor send error: {e}")
        return False


def send_rotation_monitor(
    rotation: str,
    scanned_tokens: List[str],
    candidates: List[Dict],
    alerts: List[Dict],
    filter_stats: Dict,
    is_source_specific: bool = False
):
    """
    Send FULL rotation scan monitor directly.
    Splits into multiple messages if needed.
    """
    if not scanned_tokens:
        return
    
    timestamp = datetime.now().strftime('%H:%M:%S UTC')
    total_scanned = len(scanned_tokens)
    
    # Provenance label
    provenance = "" if is_source_specific else " (matched from merged pool)"
    
    # Build header
    header = f"""🔄 <b>JAYCE SCAN CYCLE</b>

<b>Rotation:</b> {rotation}
<b>Time:</b> {timestamp}
<b>Scanned:</b> {total_scanned}

<b>Coins Scanned:</b>
"""
    
    # Build candidates section
    candidates_section = f"\n<b>Candidates{provenance}:</b>\n"
    if candidates:
        for c in candidates:
            sym = c.get('symbol', '???')
            reason = str(c.get('reason', 'potential'))[:25]
            candidates_section += f"• {sym} — {reason}\n"
    else:
        candidates_section += "• None\n"
    
    # Build alerts section
    alerts_section = f"\n<b>Alerts{provenance}:</b>\n"
    if alerts:
        for a in alerts:
            sym = a.get('symbol', '???')
            setup = a.get('setup', 'Setup')
            alerts_section += f"• {sym} — {setup}\n"
    else:
        alerts_section += "• None\n"
    
    # Build filter summary
    summary_section = f"""
<b>Filter Summary:</b>
- Total scanned: {filter_stats.get('total', total_scanned)}
- Passed filters: {filter_stats.get('passed_filters', 0)}
- Candidates: {filter_stats.get('candidates', len(candidates))}
- Alerts: {filter_stats.get('alerts', len(alerts))}"""
    
    footer = candidates_section + alerts_section + summary_section
    
    # Build coin list
    coin_lines = [f"{i}. {token}" for i, token in enumerate(scanned_tokens, 1)]
    
    MAX_MSG_LEN = 3800
    
    # Try single message first
    full_coins = "\n".join(coin_lines)
    full_message = header + full_coins + footer
    
    if len(full_message) <= MAX_MSG_LEN:
        send_telegram_message(full_message)
    else:
        # Split: coins in chunks, footer at end
        current_msg = header
        messages_to_send = []
        
        for line in coin_lines:
            if len(current_msg) + len(line) + 2 > MAX_MSG_LEN:
                messages_to_send.append(current_msg)
                current_msg = "<b>Coins (continued):</b>\n" + line + "\n"
            else:
                current_msg += line + "\n"
        
        # Add footer to last chunk or send separately
        if len(current_msg) + len(footer) <= MAX_MSG_LEN:
            current_msg += footer
            messages_to_send.append(current_msg)
        else:
            messages_to_send.append(current_msg)
            messages_to_send.append(footer.strip())
        
        for msg in messages_to_send:
            send_telegram_message(msg)


def send_all_rotation_monitors(
    raw_top100: List[str],
    raw_5m_vol: List[str],
    raw_1h_vol: List[str],
    candidates_by_source: Dict[str, List[Dict]],
    alerts_by_source: Dict[str, List[Dict]],
    total_passed_filters: int,
    merged_candidates: List[Dict] = None,
    merged_alerts: List[Dict] = None
):
    """Send SEPARATE Telegram messages for each rotation source."""
    
    has_source_specific = bool(candidates_by_source or alerts_by_source)
    
    # TOP 1-100
    if raw_top100:
        top_candidates = candidates_by_source.get('TOP_100', candidates_by_source.get('TRENDING', []))
        top_alerts = alerts_by_source.get('TOP_100', alerts_by_source.get('TRENDING', []))
        
        if not top_candidates and merged_candidates:
            top_symbols = set(raw_top100)
            top_candidates = [c for c in merged_candidates if c.get('symbol', '') in top_symbols]
        
        if not top_alerts and merged_alerts:
            top_symbols = set(raw_top100)
            top_alerts = [a for a in merged_alerts if a.get('symbol', '') in top_symbols]
        
        send_rotation_monitor(
            rotation="TOP 1–100",
            scanned_tokens=raw_top100,
            candidates=top_candidates,
            alerts=top_alerts,
            filter_stats={
                'total': len(raw_top100),
                'passed_filters': total_passed_filters,
                'candidates': len(top_candidates),
                'alerts': len(top_alerts)
            },
            is_source_specific=has_source_specific or bool(top_candidates)
        )
    
    # 5M MOVERS
    if raw_5m_vol:
        vol5m_candidates = candidates_by_source.get('5M_VOL', candidates_by_source.get('VOL_5M', []))
        vol5m_alerts = alerts_by_source.get('5M_VOL', alerts_by_source.get('VOL_5M', []))
        
        if not vol5m_candidates and merged_candidates:
            vol5m_symbols = set(raw_5m_vol)
            vol5m_candidates = [c for c in merged_candidates if c.get('symbol', '') in vol5m_symbols]
        
        if not vol5m_alerts and merged_alerts:
            vol5m_symbols = set(raw_5m_vol)
            vol5m_alerts = [a for a in merged_alerts if a.get('symbol', '') in vol5m_symbols]
        
        send_rotation_monitor(
            rotation="5M MOVERS 1–50",
            scanned_tokens=raw_5m_vol,
            candidates=vol5m_candidates,
            alerts=vol5m_alerts,
            filter_stats={
                'total': len(raw_5m_vol),
                'passed_filters': total_passed_filters,
                'candidates': len(vol5m_candidates),
                'alerts': len(vol5m_alerts)
            },
            is_source_specific=has_source_specific or bool(vol5m_candidates)
        )
    
    # 1H MOVERS
    if raw_1h_vol:
        vol1h_candidates = candidates_by_source.get('1H_VOL', candidates_by_source.get('VOL_1H', []))
        vol1h_alerts = alerts_by_source.get('1H_VOL', alerts_by_source.get('VOL_1H', []))
        
        if not vol1h_candidates and merged_candidates:
            vol1h_symbols = set(raw_1h_vol)
            vol1h_candidates = [c for c in merged_candidates if c.get('symbol', '') in vol1h_symbols]
        
        if not vol1h_alerts and merged_alerts:
            vol1h_symbols = set(raw_1h_vol)
            vol1h_alerts = [a for a in merged_alerts if a.get('symbol', '') in vol1h_symbols]
        
        send_rotation_monitor(
            rotation="1H MOVERS 1–50",
            scanned_tokens=raw_1h_vol,
            candidates=vol1h_candidates,
            alerts=vol1h_alerts,
            filter_stats={
                'total': len(raw_1h_vol),
                'passed_filters': total_passed_filters,
                'candidates': len(vol1h_candidates),
                'alerts': len(vol1h_alerts)
            },
            is_source_specific=has_source_specific or bool(vol1h_candidates)
        )


def send_scan_monitor_simple(
    rotation: str,
    scanned_tokens: List[str],
    candidates: List[Dict],
    alerts: List[Dict],
    filter_stats: Dict,
    source_breakdown: Dict = None
):
    """Backward compatible function."""
    if source_breakdown:
        merged_candidates = []
        for c in (candidates or []):
            if isinstance(c, dict):
                sym = c.get('token', {}).get('symbol', c.get('symbol', '???'))
                reason = c.get('watchlist_setup', c.get('reason', 'potential'))
                merged_candidates.append({'symbol': sym, 'reason': str(reason)[:25]})
        
        send_all_rotation_monitors(
            raw_top100=source_breakdown.get('TOP_100', []),
            raw_5m_vol=source_breakdown.get('5M_VOL', []),
            raw_1h_vol=source_breakdown.get('1H_VOL', []),
            candidates_by_source={},
            alerts_by_source={},
            total_passed_filters=filter_stats.get('passed_filters', 0),
            merged_candidates=merged_candidates,
            merged_alerts=alerts or []
        )
    else:
        send_rotation_monitor(
            rotation=rotation,
            scanned_tokens=scanned_tokens,
            candidates=candidates or [],
            alerts=alerts or [],
            filter_stats=filter_stats,
            is_source_specific=False
        )
