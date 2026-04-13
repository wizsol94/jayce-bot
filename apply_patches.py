#!/usr/bin/env python3
"""
JAYCE UPGRADE PATCH SCRIPT v1.0
===============================
Applies all 5 changes to scanner.py:
1. Scoring weights (55/25/20)
2. Remove market cap filter
3. Update alert format with whale fields
4. Add imports for new modules
5. Fix under-fib classification

Run: python3 apply_patches.py
"""

import re
import shutil
from datetime import datetime

SCANNER_PATH = "/opt/jayce/scanner.py"
ENGINES_PATH = "/opt/jayce/engines.py"
UNDERFIB_PATH = "/opt/jayce/setup_validators/under_fib.py"


def backup_file(filepath):
    """Create timestamped backup."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{filepath}.backup_{timestamp}"
    shutil.copy(filepath, backup_path)
    print(f"✅ Backup: {backup_path}")
    return backup_path


def patch_scanner():
    """Apply all scanner.py patches."""
    print("\n📝 Patching scanner.py...")
    
    backup_file(SCANNER_PATH)
    
    with open(SCANNER_PATH, 'r') as f:
        content = f.read()
    
    changes = 0
    
    # CHANGE 1: Update scoring weights
    old_weights = """ENGINE_WEIGHT = float(os.getenv('ENGINE_WEIGHT', 0.4))
VISION_WEIGHT = float(os.getenv('VISION_WEIGHT', 0.4))
PATTERN_WEIGHT = float(os.getenv('PATTERN_WEIGHT', 0.2))"""
    
    new_weights = """ENGINE_WEIGHT = float(os.getenv('ENGINE_WEIGHT', 0.55))
VISION_WEIGHT = float(os.getenv('VISION_WEIGHT', 0.20))
PATTERN_WEIGHT = float(os.getenv('PATTERN_WEIGHT', 0.25))"""
    
    if old_weights in content:
        content = content.replace(old_weights, new_weights)
        print("  ✅ Updated scoring weights: ENGINE=55%, PATTERN=25%, VISION=20%")
        changes += 1
    else:
        print("  ⚠️ Scoring weights pattern not found (may already be updated)")
    
    # CHANGE 2: Disable market cap constant
    old_mc = "MIN_MARKET_CAP = int(os.getenv('MIN_MARKET_CAP', 100000))"
    new_mc = "MIN_MARKET_CAP = 0  # DISABLED - valid setups at any market cap"
    
    if old_mc in content:
        content = content.replace(old_mc, new_mc)
        print("  ✅ Disabled MIN_MARKET_CAP constant")
        changes += 1
    else:
        print("  ⚠️ MIN_MARKET_CAP pattern not found")
    
    # CHANGE 3: Comment out MC filter in passes_basic_filters
    old_mc_check = "if mc < MIN_MARKET_CAP: return (False, \"MC too low\")"
    new_mc_check = "# if mc < MIN_MARKET_CAP: return (False, \"MC too low\")  # DISABLED"
    
    if old_mc_check in content:
        content = content.replace(old_mc_check, new_mc_check)
        print("  ✅ Commented out MC check in passes_basic_filters")
        changes += 1
    
    # CHANGE 4: Add imports for new modules (after existing imports)
    import_marker = "from setup_watch import"
    new_imports = """from setup_watch import check_setup_watch, format_setup_watch_message, clear_old_alerts
from whale_conviction import get_whale_conviction, format_whale_for_alert
from pre_alert import check_pre_alert, format_pre_alert_message"""
    
    if "from whale_conviction import" not in content:
        if import_marker in content:
            # Find the line and replace with extended imports
            old_import = "from setup_watch import check_setup_watch, format_setup_watch_message, clear_old_alerts"
            if old_import in content:
                content = content.replace(old_import, new_imports)
                print("  ✅ Added whale_conviction and pre_alert imports")
                changes += 1
    else:
        print("  ⚠️ New imports already present")
    
    # CHANGE 5: Update whale text in alert format
    # Find and update the alert format section
    old_whale_line = "🐳 Whale Conviction: {whale_text}"
    new_whale_lines = """🐋 Whale Detected: {whale_detected_text}
🐳 Whale Conviction: {whale_conviction_text}"""
    
    if old_whale_line in content and "whale_detected_text" not in content:
        content = content.replace(old_whale_line, new_whale_lines)
        print("  ✅ Updated alert format with whale detected/conviction fields")
        changes += 1
    
    # Write updated content
    with open(SCANNER_PATH, 'w') as f:
        f.write(content)
    
    print(f"\n  📊 Scanner patches applied: {changes} changes")
    return changes


def patch_engines():
    """Update engines.py for under-fib classification."""
    print("\n📝 Patching engines.py (under-fib classification)...")
    
    backup_file(ENGINES_PATH)
    
    with open(ENGINES_PATH, 'r') as f:
        content = f.read()
    
    changes = 0
    
    # Update underfib retracement_min from 40 to 55
    old_underfib = """'underfib': {
        'name': 'Under-Fib Flip Zone',
        'retracement_min': 40,"""
    
    new_underfib = """'underfib': {
        'name': 'Under-Fib Flip Zone',
        'retracement_min': 55,  # Only 618/786 territory (removed under-382/under-50)"""
    
    if "'retracement_min': 40," in content and "'underfib'" in content:
        content = content.replace(old_underfib, new_underfib)
        print("  ✅ Updated underfib retracement_min: 40 → 55 (removes under-382/under-50)")
        changes += 1
    else:
        print("  ⚠️ Underfib config pattern not found")
    
    with open(ENGINES_PATH, 'w') as f:
        f.write(content)
    
    print(f"\n  📊 Engines patches applied: {changes} changes")
    return changes


def main():
    print("=" * 60)
    print("JAYCE UPGRADE PATCH SCRIPT v1.0")
    print("=" * 60)
    print("\nThis will apply:")
    print("  1. Scoring weights: ENGINE=55%, PATTERN=25%, VISION=20%")
    print("  2. Remove market cap filtering")
    print("  3. Update alert format (whale detected + conviction)")
    print("  4. Add imports for whale_conviction and pre_alert")
    print("  5. Fix under-fib classification (remove under-382/under-50)")
    print()
    
    total_changes = 0
    
    try:
        total_changes += patch_scanner()
        total_changes += patch_engines()
        
        print("\n" + "=" * 60)
        print(f"✅ COMPLETE: {total_changes} total changes applied")
        print("=" * 60)
        print("\n⚠️  NEXT STEPS:")
        print("  1. Review the changes")
        print("  2. Restart scanner: systemctl restart jayce-scanner")
        print("  3. Check logs: tail -f /opt/jayce/logs/scanner.log")
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        print("Check file paths and permissions.")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
