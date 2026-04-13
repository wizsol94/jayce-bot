#!/bin/bash
echo "═══════════════════════════════════════════════════════════════"
echo "🎯 JAYCE STATUS - $(date)"
echo "═══════════════════════════════════════════════════════════════"
echo ""
systemctl status jayce-scanner --no-pager | head -3
echo ""
echo "=== TODAY'S ALERTS ==="
grep "WIZTHEORY ALERT" /opt/jayce/logs/scanner.log | grep "$(date +%Y-%m-%d)" | tail -10
echo ""
echo "=== API USAGE ==="
grep "Birdeye ✓" /opt/jayce/logs/scanner.log | tail -1
echo ""
echo "=== LAST CYCLE ==="
tail -5 /opt/jayce/logs/scanner.log | grep -E "CYCLE|Scanned|candidates"
