#!/usr/bin/env python3
"""
Setup Matcher Adapter — bridges Jayce's engine to the WizTheory ChartSetupMatcher.

Architecture:
  Jayce engine classifies setup (e.g. "618")
  → adapter.match_setup(chart_bytes, '618')
  → returns top matches from BOTH libraries:
      - /opt/trade-matcher/library/CLAUDE618/  (curated matcher library)
      - /opt/jayce/flashcards/618/             (active operational library)
  → STRICT per-setup separation. A 618 setup ONLY sees 618 examples.

Signatures are cached to disk at /opt/jayce/data/matcher_signatures.pkl.
Cache auto-invalidates per-file when source mtime changes.

PHASE 1 GOAL:
  Standalone module. NOT integrated into scanner.py yet.
  Test via: python3 /opt/jayce/setup_matcher_adapter.py --self-test
"""

from __future__ import annotations

import io
import os
import pickle
import sys
import time
import logging
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add trade-matcher to import path
sys.path.insert(0, '/opt/trade-matcher')

try:
    from chart_matcher import make_signature, compare, Signature
except ImportError as e:
    raise ImportError(
        f"Cannot import chart_matcher from /opt/trade-matcher: {e}\n"
        f"Is the trade-matcher service deployed?"
    )

from PIL import Image

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ════════════════════════════════════════════════════════════════════

CACHE_PATH = Path('/opt/jayce/data/matcher_signatures.pkl')
CACHE_VERSION = 1

# Canonical setup names → folder paths in each library
# STRICT: a setup compares ONLY against its matching folders.
SETUP_LIBRARIES: Dict[str, List[Path]] = {
    '382': [
        Path('/opt/trade-matcher/library/CLAUDE382'),
        Path('/opt/jayce/flashcards/382'),
    ],
    '50': [
        Path('/opt/trade-matcher/library/CLAUDE50'),
        Path('/opt/jayce/flashcards/50'),
    ],
    '618': [
        Path('/opt/trade-matcher/library/CLAUDE618'),
        Path('/opt/jayce/flashcards/618'),
    ],
    '786': [
        Path('/opt/trade-matcher/library/CLAUDE786'),
        Path('/opt/jayce/flashcards/786'),
    ],
    'underfib': [
        Path('/opt/trade-matcher/library/claudeuf'),
        Path('/opt/jayce/flashcards/Under-Fib'),
    ],
}

# Setup-name normalization (engine outputs many forms; we map them all to canonical)
SETUP_ALIASES = {
    '382': '382', '382 + flip zone': '382', '382fz': '382',
    '50': '50', '50 + flip zone': '50', '50fz': '50',
    '618': '618', '618 + flip zone': '618', '618fz': '618',
    '786': '786', '786 + flip zone': '786', '786fz': '786',
    'underfib': 'underfib', 'under-fib': 'underfib', 'under-fib flip zone': 'underfib',
    'uf': 'underfib', 'ufib': 'underfib', 'under_fib': 'underfib',
}

IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}


# ════════════════════════════════════════════════════════════════════
# SIGNATURE CACHE
# ════════════════════════════════════════════════════════════════════

def _normalize_setup(setup_name: str) -> Optional[str]:
    """Normalize any setup form to canonical key, or None if unknown."""
    if not setup_name:
        return None
    key = setup_name.strip().lower().replace('_', ' ').strip()
    return SETUP_ALIASES.get(key)


def _load_cache() -> dict:
    """Load signature cache from disk. Empty dict if missing/corrupt."""
    if not CACHE_PATH.exists():
        return {'cache_version': CACHE_VERSION, 'setups': {}}
    try:
        with open(CACHE_PATH, 'rb') as f:
            data = pickle.load(f)
        if data.get('cache_version') != CACHE_VERSION:
            logger.info(f"[MATCHER-CACHE] Version mismatch, rebuilding")
            return {'cache_version': CACHE_VERSION, 'setups': {}}
        return data
    except Exception as e:
        logger.warning(f"[MATCHER-CACHE] Load failed ({e}), starting fresh")
        return {'cache_version': CACHE_VERSION, 'setups': {}}


def _save_cache(cache: dict) -> None:
    """Save cache to disk atomically."""
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_PATH.with_suffix('.pkl.tmp')
    with open(tmp, 'wb') as f:
        pickle.dump(cache, f)
    tmp.replace(CACHE_PATH)


def _iter_setup_files(setup_key: str) -> List[Path]:
    """Yield every image file across both libraries for one setup."""
    files = []
    for folder in SETUP_LIBRARIES.get(setup_key, []):
        if not folder.exists():
            continue
        for p in folder.iterdir():
            if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS:
                files.append(p)
    return files


def _ensure_signatures(setup_key: str) -> Tuple[Dict[Path, Signature], dict]:
    """
    For a given setup, ensure all source charts have cached signatures.
    Returns (signatures dict, full cache dict). Saves cache if anything changed.
    """
    cache = _load_cache()
    setup_cache = cache['setups'].get(setup_key, {})
    files = _iter_setup_files(setup_key)
    new_signatures: Dict[Path, Signature] = {}
    recomputed = 0

    for fp in files:
        mtime = fp.stat().st_mtime
        cached_entry = setup_cache.get(str(fp))
        if cached_entry and cached_entry.get('mtime') == mtime:
            new_signatures[fp] = cached_entry['signature']
        else:
            try:
                sig = make_signature(fp, crop='auto', region=None)
                new_signatures[fp] = sig
                setup_cache[str(fp)] = {'mtime': mtime, 'signature': sig}
                recomputed += 1
            except Exception as e:
                logger.warning(f"[MATCHER-CACHE] Failed to sign {fp}: {e}")

    # Drop entries for files that no longer exist
    valid_paths = {str(fp) for fp in files}
    setup_cache = {k: v for k, v in setup_cache.items() if k in valid_paths}

    cache['setups'][setup_key] = setup_cache
    if recomputed > 0:
        logger.info(f"[MATCHER-CACHE] {setup_key}: {recomputed} new signatures computed, {len(files)} total")
        _save_cache(cache)
    return new_signatures, cache


# ════════════════════════════════════════════════════════════════════
# MAIN MATCH FUNCTION
# ════════════════════════════════════════════════════════════════════

def match_setup(chart_bytes: bytes, setup_name: str, top_n: int = 5) -> dict:
    """
    Compare a live chart against the matching setup's library.
    
    Args:
        chart_bytes: PNG/JPEG bytes of the live chart
        setup_name: setup name (any form: '618', '618 + Flip Zone', 'underfib', etc.)
        top_n: how many top matches to return
    
    Returns:
        dict with top_matches, avg_similarity_pct, top_match_pct,
        pattern_confidence, structure_quality, library sizes, timing.
    """
    t_start = time.time()
    setup_key = _normalize_setup(setup_name)
    
    if not setup_key:
        return {
            'success': False,
            'error': f"Unknown setup: {setup_name!r}",
            'setup_type': setup_name,
        }
    
    if setup_key not in SETUP_LIBRARIES:
        return {
            'success': False,
            'error': f"No library configured for setup: {setup_key}",
            'setup_type': setup_key,
        }
    
    # Build / load signatures for this setup
    try:
        library_sigs, _ = _ensure_signatures(setup_key)
    except Exception as e:
        return {
            'success': False,
            'error': f"Library load failed: {e}",
            'setup_type': setup_key,
        }
    
    if not library_sigs:
        return {
            'success': False,
            'error': f"No library entries found for setup {setup_key}",
            'setup_type': setup_key,
        }
    
    # Compute signature for the live chart
    tmp_path = Path(f'/tmp/jayce_matcher_live_{os.getpid()}_{int(time.time()*1000)}.png')
    try:
        with open(tmp_path, 'wb') as f:
            f.write(chart_bytes)
        live_sig = make_signature(tmp_path, crop='auto', region=None)
    except Exception as e:
        return {
            'success': False,
            'error': f"Live signature failed: {e}",
            'setup_type': setup_key,
        }
    finally:
        if tmp_path.exists():
            try: tmp_path.unlink()
            except: pass
    
    # Compare against every library entry
    matches = []
    for lib_path, lib_sig in library_sigs.items():
        try:
            score, shape, structure, candle = compare(live_sig, lib_sig)
            source = 'matcher' if 'trade-matcher' in str(lib_path) else 'jayce'
            matches.append({
                'name': lib_path.name,
                'path': str(lib_path),
                'similarity_pct': int(round(score * 100)),
                'shape': round(shape, 3),
                'structure': round(structure, 3),
                'candle': round(candle, 3),
                'source': source,
            })
        except Exception as e:
            logger.warning(f"[MATCHER] Compare failed for {lib_path.name}: {e}")
    
    matches.sort(key=lambda m: m['similarity_pct'], reverse=True)
    top_matches = matches[:top_n]
    
    if not matches:
        return {
            'success': False,
            'error': "All comparisons failed",
            'setup_type': setup_key,
        }
    
    top_pct = top_matches[0]['similarity_pct']
    avg_pct = int(round(sum(m['similarity_pct'] for m in top_matches) / len(top_matches)))
    
    # Confidence and quality grading
    if avg_pct >= 75:
        confidence = 'HIGH'
    elif avg_pct >= 40:
        confidence = 'MEDIUM'
    else:
        confidence = 'LOW'
    
    if top_pct >= 85:   quality = 'A'
    elif top_pct >= 70: quality = 'B'
    elif top_pct >= 50: quality = 'C'
    else:               quality = 'D'
    
    matcher_count = sum(1 for m in matches if m['source'] == 'matcher')
    jayce_count = sum(1 for m in matches if m['source'] == 'jayce')
    
    return {
        'success': True,
        'setup_type': setup_key,
        'top_matches': top_matches,
        'avg_similarity_pct': avg_pct,
        'top_match_pct': top_pct,
        'pattern_confidence': confidence,
        'structure_quality': quality,
        'library_size': len(matches),
        'matcher_used': matcher_count,
        'jayce_used': jayce_count,
        'compute_time_ms': int((time.time() - t_start) * 1000),
    }


# ════════════════════════════════════════════════════════════════════
# OUTPUT FORMATTERS
# ════════════════════════════════════════════════════════════════════

def format_for_telegram(result: dict) -> str:
    """Telegram-style multi-line output matching existing matcher style."""
    if not result.get('success'):
        return f"🔮 Setup Matcher Error: {result.get('error', 'unknown')}"
    
    setup_label = {
        '382': '382 + Flip Zone',
        '50': '50 + Flip Zone',
        '618': '618 + Flip Zone',
        '786': '786 + Flip Zone',
        'underfib': 'Under-Fib Flip Zone',
    }.get(result['setup_type'], result['setup_type'])
    
    lines = [f"🔮 Setup Matcher — {setup_label}", ""]
    for i, m in enumerate(result['top_matches'], 1):
        lines.append(f"{i}. {m['name']} → {m['similarity_pct']}%")
    lines += [
        "",
        f"Average Similarity: {result['avg_similarity_pct']}%",
        f"Top Match: {result['top_match_pct']}%",
        f"Structure Quality: {result['structure_quality']}",
        f"Pattern Confidence: {result['pattern_confidence']}",
        f"Library size: {result['library_size']} (matcher: {result['matcher_used']}, jayce: {result['jayce_used']})",
        f"Compute time: {result['compute_time_ms']}ms",
    ]
    return "\n".join(lines)


def format_for_log(result: dict) -> str:
    """One-line log format for scanner.log."""
    if not result.get('success'):
        return f"[MATCHER] error={result.get('error')}"
    return (
        f"[MATCHER] {result['setup_type']}: "
        f"top={result['top_match_pct']}% avg={result['avg_similarity_pct']}% "
        f"quality={result['structure_quality']} confidence={result['pattern_confidence']} "
        f"library={result['library_size']} time={result['compute_time_ms']}ms"
    )


# ════════════════════════════════════════════════════════════════════
# SELF-TEST
# ════════════════════════════════════════════════════════════════════

def self_test():
    print("="*72)
    print("SETUP MATCHER ADAPTER — SELF-TEST")
    print("="*72)
    
    # Verify libraries exist
    print("\n[1/4] Library inventory:")
    for setup_key, folders in SETUP_LIBRARIES.items():
        counts = []
        for f in folders:
            n = sum(1 for p in f.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS) if f.exists() else 0
            counts.append(f"{f.name}:{n}")
        print(f"  {setup_key:10s} → {' + '.join(counts)} = {sum(int(c.split(':')[1]) for c in counts)} total")
    
    # Warm cache for all setups
    print("\n[2/4] Warming signature cache (first run = slow, then fast):")
    for setup_key in SETUP_LIBRARIES.keys():
        t0 = time.time()
        sigs, _ = _ensure_signatures(setup_key)
        print(f"  {setup_key:10s} → {len(sigs)} sigs in {(time.time()-t0):.1f}s")
    
    # Run a real comparison using one of the library charts as the "live" chart
    print("\n[3/4] Test match (using a 618 chart as live input, should match itself near 100%):")
    test_charts = list(Path('/opt/trade-matcher/library/CLAUDE618').iterdir())
    test_charts = [p for p in test_charts if p.suffix.lower() in IMAGE_EXTENSIONS]
    if test_charts:
        test_chart = test_charts[0]
        chart_bytes = test_chart.read_bytes()
        result = match_setup(chart_bytes, '618', top_n=5)
        print(format_for_telegram(result))
    
    # Cache hit speed test
    print("\n[4/4] Cache hit speed test (should be <500ms total now):")
    if test_charts:
        t0 = time.time()
        result2 = match_setup(chart_bytes, '618', top_n=5)
        elapsed = (time.time() - t0) * 1000
        print(f"  Cached run: {elapsed:.0f}ms (was {result['compute_time_ms']}ms cold)")
    
    print("\n✅ Self-test complete.")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        print("Usage: python3 setup_matcher_adapter.py --self-test")
