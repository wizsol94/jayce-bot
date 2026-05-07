#!/bin/bash
LOG_FILE="/opt/jayce/logs/watchdog.log"
SCANNER_LOG="/opt/jayce/logs/scanner.log"
SCANNER_MAX_SILENCE_SEC=900
SCRAPER_MAX_SILENCE_SEC=900

mkdir -p /opt/jayce/logs

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOG_FILE"
}

check_scanner() {
    local active
    active=$(systemctl is-active jayce-scanner)
    if [ "$active" != "active" ]; then
        log "[SCANNER] systemd says: $active. Restarting."
        systemctl restart jayce-scanner
        return
    fi
    if [ ! -f "$SCANNER_LOG" ]; then
        log "[SCANNER] Log file missing. Skipping silence check."
        return
    fi
    local last_modified now age
    last_modified=$(stat -c %Y "$SCANNER_LOG")
    now=$(date +%s)
    age=$((now - last_modified))
    if [ "$age" -gt "$SCANNER_MAX_SILENCE_SEC" ]; then
        log "[SCANNER] FROZEN - log silent for ${age}s. Restarting."
        systemctl restart jayce-scanner
    fi
}

check_scraper() {
    local active
    active=$(systemctl is-active jayce-scraper)
    if [ "$active" != "active" ]; then
        log "[SCRAPER] systemd says: $active. Restarting."
        systemctl restart jayce-scraper
        return
    fi
    local last_log_ts now age
    last_log_ts=$(journalctl -u jayce-scraper -n 1 --no-pager --output=short-unix 2>/dev/null | tail -1 | awk '{print $1}' | cut -d. -f1)
    if [ -z "$last_log_ts" ] || ! [[ "$last_log_ts" =~ ^[0-9]+$ ]]; then
        log "[SCRAPER] Could not parse last log timestamp. Skipping silence check."
        return
    fi
    now=$(date +%s)
    age=$((now - last_log_ts))
    if [ "$age" -gt "$SCRAPER_MAX_SILENCE_SEC" ]; then
        log "[SCRAPER] FROZEN - journalctl silent for ${age}s. Restarting."
        systemctl restart jayce-scraper
    fi
}

check_scanner
check_scraper

