#!/usr/bin/env python3
"""
Sync flashcards from local data to flashcard folders.
NO LONGER pulls from GitHub - uses local data as source of truth.
"""
import json
import os
import re
from collections import Counter
from datetime import datetime

FLASHCARD_DIR = "/opt/jayce/flashcards"
LOCAL_DATA_PATH = "/opt/jayce/data/jayce_training_dataset.json"

def sanitize_filename(name):
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', name)
    sanitized = re.sub(r'[^\x00-\x7F]+', '', sanitized)
    return sanitized

def sync_local():
    print(f"[{datetime.now()}] Syncing flashcards from local data...")
    
    # Load local data
    with open(LOCAL_DATA_PATH, 'r') as f:
        data = json.load(f)
    
    print(f"✅ Loaded {len(data)} flashcards from local")
    
    # Count by setup
    setups = Counter([d.get('setup_name', 'unknown') for d in data])
    for setup, count in sorted(setups.items()):
        print(f"   📚 {setup}: {count}")
    
    # Update flashcard folders
    setup_mapping = {
        '382 + Flip Zone': '382',
        '50 + Flip Zone': '50',
        '618 + Flip Zone': '618',
        '786 + Flip Zone': '786',
        'Under-Fib Flip Zone': 'Under-Fib'
    }
    
    for setup_name, folder in setup_mapping.items():
        folder_path = os.path.join(FLASHCARD_DIR, folder)
        os.makedirs(folder_path, exist_ok=True)
        
        setup_cards = [d for d in data if d.get('setup_name') == setup_name]
        
        # Clear existing
        for f in os.listdir(folder_path):
            try:
                os.remove(os.path.join(folder_path, f))
            except:
                pass
        
        # Write new
        for i, card in enumerate(setup_cards):
            chart_id = card.get('chart_id', f'card_{i}')
            safe_id = sanitize_filename(chart_id)
            card_file = os.path.join(folder_path, f"{safe_id}.json")
            with open(card_file, 'w') as f:
                json.dump(card, f, indent=2)
        
        print(f"   ✅ {folder}: {len(setup_cards)} flashcards saved")
    
    print(f"\n✅ Sync complete! Total: {len(data)} flashcards")
    return True

if __name__ == "__main__":
    sync_local()
