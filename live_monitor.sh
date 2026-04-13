#!/bin/bash
# JAYCE LIVE SCANNER MONITOR
# Shows tokens as they're being scanned in real-time

clear
echo "================================================================================"
echo "  🎯 JAYCE LIVE SCANNER | Press Ctrl+C to exit"
echo "================================================================================"
echo ""

tail -f /opt/jayce/logs/scanner.log | while read line; do
    # Show token discoveries
    if echo "$line" | grep -qE "📊|PSEF PASSED|📐|WIZTHEORY|👁️|🎯|ENGINE:|Scanning"; then
        # Extract and format
        if echo "$line" | grep -q "📊"; then
            # Candle fetch - show token name and candles
            echo "$line" | sed 's/.*INFO - //' 
        elif echo "$line" | grep -q "PSEF PASSED"; then
            echo "  ✅ $(echo "$line" | grep -oE '[A-Za-z0-9_]+: PSEF PASSED')"
        elif echo "$line" | grep -q "📐"; then
            echo "  $(echo "$line" | sed 's/.*INFO - //')"
        elif echo "$line" | grep -q "WIZTHEORY"; then
            echo "  $(echo "$line" | sed 's/.*INFO - //')"
        elif echo "$line" | grep -q "👁️"; then
            echo "  $(echo "$line" | sed 's/.*INFO - //')"
        elif echo "$line" | grep -q "🎯"; then
            echo ""
            echo "  🎯 $(echo "$line" | sed 's/.*INFO - //')"
            echo ""
        elif echo "$line" | grep -q "CYCLE COMPLETE"; then
            echo ""
            echo "================================================================================"
            echo "  $(echo "$line" | sed 's/.*INFO - //')"
            echo "================================================================================"
            echo ""
        fi
    fi
done
