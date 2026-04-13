"""
VISION AUDIT SYSTEM
===================
Tracks all Vision calls for analysis without modifying Vision logic.
"""

import json
import os
from datetime import datetime
from typing import Dict, Optional

AUDIT_LOG = '/opt/jayce/logs/vision_audit.jsonl'
AUDIT_SUMMARY = '/opt/jayce/logs/vision_audit_summary.txt'

def log_vision_call(
    token: str,
    address: str,
    setup_type: str,
    similarity: float,
    confidence: str,
    bonus_added: int,
    top_matches: list,
    notes: str,
    outcome: str = "pending"  # pending, alerted, rejected
):
    """Log a Vision call to the audit file."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "token": token,
        "address": address[:12] + "..." if len(address) > 12 else address,
        "setup_type": setup_type,
        "similarity": round(similarity, 1),
        "confidence": confidence,
        "bonus_added": bonus_added,
        "top_matches": top_matches[:3] if top_matches else [],
        "notes": notes[:200] if notes else "",
        "outcome": outcome
    }
    
    # Append to JSONL file
    with open(AUDIT_LOG, 'a') as f:
        f.write(json.dumps(entry) + '\n')
    
    return entry

def update_outcome(token: str, setup_type: str, outcome: str):
    """Update the outcome of a Vision call (alerted or rejected)."""
    if not os.path.exists(AUDIT_LOG):
        return
    
    lines = []
    updated = False
    
    with open(AUDIT_LOG, 'r') as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                # Update the most recent matching entry
                if entry['token'] == token and entry['setup_type'] == setup_type and entry['outcome'] == 'pending':
                    entry['outcome'] = outcome
                    updated = True
                lines.append(json.dumps(entry))
            except:
                lines.append(line.strip())
    
    if updated:
        with open(AUDIT_LOG, 'w') as f:
            f.write('\n'.join(lines) + '\n')

def generate_summary():
    """Generate a human-readable summary of Vision activity."""
    if not os.path.exists(AUDIT_LOG):
        return "No Vision audit data yet."
    
    entries = []
    with open(AUDIT_LOG, 'r') as f:
        for line in f:
            try:
                entries.append(json.loads(line.strip()))
            except:
                pass
    
    if not entries:
        return "No Vision audit data yet."
    
    # Stats
    total_calls = len(entries)
    by_setup = {}
    by_confidence = {"high": 0, "medium": 0, "low": 0}
    by_outcome = {"alerted": 0, "rejected": 0, "pending": 0}
    high_similarity = []  # >= 70%
    low_similarity = []   # < 40%
    bonus_given = 0
    
    for e in entries:
        setup = e.get('setup_type', 'unknown')
        by_setup[setup] = by_setup.get(setup, 0) + 1
        
        conf = e.get('confidence', 'low').lower()
        if conf in by_confidence:
            by_confidence[conf] += 1
        
        outcome = e.get('outcome', 'pending')
        if outcome in by_outcome:
            by_outcome[outcome] += 1
        
        sim = e.get('similarity', 0)
        if sim >= 70:
            high_similarity.append(e)
        elif sim < 40:
            low_similarity.append(e)
        
        if e.get('bonus_added', 0) > 0:
            bonus_given += 1
    
    # Build summary
    lines = [
        "=" * 60,
        "VISION AUDIT SUMMARY",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        f"TOTAL VISION CALLS: {total_calls}",
        "",
        "BY SETUP TYPE:",
    ]
    for setup, count in sorted(by_setup.items(), key=lambda x: -x[1]):
        lines.append(f"  {setup}: {count}")
    
    lines.extend([
        "",
        "BY CONFIDENCE:",
        f"  High: {by_confidence['high']}",
        f"  Medium: {by_confidence['medium']}",
        f"  Low: {by_confidence['low']}",
        "",
        "BY OUTCOME:",
        f"  Alerted: {by_outcome['alerted']}",
        f"  Rejected: {by_outcome['rejected']}",
        f"  Pending: {by_outcome['pending']}",
        "",
        f"BONUS SCORE GIVEN: {bonus_given} times",
        "",
    ])
    
    if high_similarity:
        lines.append("HIGH SIMILARITY SETUPS (≥70%):")
        for e in high_similarity[-10:]:  # Last 10
            lines.append(f"  {e['timestamp'][:16]} | {e['token']} | {e['setup_type']} | {e['similarity']}% | {e['outcome']}")
    else:
        lines.append("HIGH SIMILARITY SETUPS (≥70%): None yet")
    
    lines.append("")
    
    if low_similarity:
        lines.append(f"LOW SIMILARITY SETUPS (<40%): {len(low_similarity)} total")
        for e in low_similarity[-5:]:  # Last 5
            lines.append(f"  {e['timestamp'][:16]} | {e['token']} | {e['setup_type']} | {e['similarity']}%")
    
    lines.extend([
        "",
        "=" * 60,
        "RECENT VISION CALLS (last 15):",
        "=" * 60,
    ])
    
    for e in entries[-15:]:
        bonus_str = f"+{e['bonus_added']}" if e.get('bonus_added', 0) > 0 else "+0"
        lines.append(
            f"{e['timestamp'][11:16]} | {e['token'][:12]:<12} | {e['setup_type']:<10} | "
            f"{e['similarity']:>5.1f}% | {e['confidence']:<6} | {bonus_str} | {e['outcome']}"
        )
    
    lines.append("")
    lines.append("=" * 60)
    
    summary = '\n'.join(lines)
    
    # Write to file
    with open(AUDIT_SUMMARY, 'w') as f:
        f.write(summary)
    
    return summary

if __name__ == '__main__':
    print(generate_summary())
