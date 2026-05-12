"""
ticker_collision.py — Phase 1
==============================

Detects ticker collision between memecoins (same ticker, different contracts).
NEVER trade the copycat. Define OG as the OLDEST contract age.

Decision tree for an alert about to fire on $X:
  1. Search DexScreener for all Solana pairs with EXACT ticker == X, >= $10k liq.
  2. If only one match found  → fire normally (no collision).
  3. If this token IS the OG  → fire normally with "OG verified ✅" tag.
  4. If this token is a copycat:
     a. Run OG through PSEF + setup detection.
     b. OG has a valid setup → SKIP the copycat alert, send a "check OG manually" notice.
     c. OG has no valid setup → fire copycat alert with "newer of two" tag.

Phase 1 scope (this file):
  - Skip copycats when OG has setup
  - Tag OG-verified alerts
  - Send "check $X manually" Telegram notice
  - NO automatic OG-redirect alert generation (that is Phase 2)

Safety:
  - Wrapped in try/except by the caller. If anything in this module raises,
    the caller fires the original alert unchanged. Never causes silence.
  - Toggle COLLISION_CHECK_ENABLED below to instantly disable.
  - All decisions logged to /opt/jayce/logs/ticker_collision.log.
"""

import logging
import asyncio
from typing import Optional, Dict, Any, List
import httpx

# ----------------------------------------------------------------------------
# Toggle — flip to True after testing
# ----------------------------------------------------------------------------
COLLISION_CHECK_ENABLED = False

# ----------------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------------
MIN_LIQUIDITY_USD = 10_000           # Same as scanner's filter
DEXSCREENER_SEARCH_URL = "https://api.dexscreener.com/latest/dex/search"
ALLOWED_DEXES = {"pumpfun", "pumpswap"}  # Match your scanner's dex filter
HTTP_TIMEOUT = 15

# ----------------------------------------------------------------------------
# Decision return values
# ----------------------------------------------------------------------------
DECISION_FIRE_NORMAL = "fire_normal"
DECISION_FIRE_OG_VERIFIED = "fire_og_verified"
DECISION_SKIP_COPYCAT = "skip_copycat"
DECISION_FIRE_COPYCAT_TAG = "fire_copycat_newer_tag"
DECISION_ERROR = "error"

# ----------------------------------------------------------------------------
# Logger — separate file so it doesn't pollute scanner.log
# ----------------------------------------------------------------------------
_logger = logging.getLogger("jayce.ticker_collision")
if not _logger.handlers:
    _logger.setLevel(logging.INFO)
    try:
        fh = logging.FileHandler("/opt/jayce/logs/ticker_collision.log")
    except (FileNotFoundError, PermissionError):
        fh = logging.FileHandler("ticker_collision.log")
    fh.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    _logger.addHandler(fh)
    _logger.propagate = False


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def _safe_float(v, default=0.0) -> float:
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _exact_symbol_match(pair_symbol: str, target_symbol: str) -> bool:
    """Case-insensitive exact match. UFO == UFO. UFO != UFOAI."""
    if not pair_symbol or not target_symbol:
        return False
    return pair_symbol.strip().upper() == target_symbol.strip().upper()


async def _fetch_pairs_with_ticker(symbol: str) -> List[Dict[str, Any]]:
    """
    Search DexScreener for all Solana pairs with this exact ticker.
    Returns only pairs that:
      - Are on Solana
      - Have exact symbol match (case-insensitive)
      - Are on an allowed DEX
      - Have >= MIN_LIQUIDITY_USD liquidity
    """
    pairs_out: List[Dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            resp = await client.get(
                f"{DEXSCREENER_SEARCH_URL}?q={symbol}",
                headers={"Accept": "application/json"},
            )
            if resp.status_code != 200:
                _logger.warning(
                    "DexScreener search returned %s for %s", resp.status_code, symbol
                )
                return []
            data = resp.json() or {}
            pairs = data.get("pairs", []) or []
    except Exception as e:
        _logger.warning("DexScreener search failed for %s: %s", symbol, e)
        return []

    for p in pairs:
        if p.get("chainId") != "solana":
            continue
        dex_id = (p.get("dexId") or "").lower()
        if dex_id not in ALLOWED_DEXES:
            continue
        base = p.get("baseToken") or {}
        if not _exact_symbol_match(base.get("symbol", ""), symbol):
            continue
        liq_usd = _safe_float((p.get("liquidity") or {}).get("usd"))
        if liq_usd < MIN_LIQUIDITY_USD:
            continue

        pairs_out.append(
            {
                "address": base.get("address", ""),
                "symbol": base.get("symbol", ""),
                "pair_address": p.get("pairAddress", ""),
                "pair_created_at_ms": _safe_float(p.get("pairCreatedAt"), 0),
                "market_cap": _safe_float(p.get("marketCap"), 0),
                "liquidity_usd": liq_usd,
                "dex_id": dex_id,
            }
        )

    return pairs_out


def _identify_og(pairs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The OG is the pair with the oldest pair_created_at_ms (smallest non-zero value)."""
    candidates = [p for p in pairs if p.get("pair_created_at_ms", 0) > 0]
    if not candidates:
        return None
    return min(candidates, key=lambda p: p["pair_created_at_ms"])


async def _og_has_active_setup(og_pair: Dict[str, Any]) -> bool:
    """
    Run the OG through PSEF + setup detection.

    Returns True if OG would qualify for an alert (has a tradeable setup).
    Returns False if OG is dead/setupless.

    Import lazily so this module loads even if those modules aren't present.
    Any failure in this check is treated as "no setup" — conservative: when in
    doubt we'd rather not skip a copycat than skip incorrectly.
    """
    try:
        from candle_provider import fetch_candles  # type: ignore
        from psef import run_psef  # type: ignore
        from impulse_detector import detect_impulse  # type: ignore
    except Exception as e:
        _logger.warning("OG setup check: import failed: %s", e)
        return False

    try:
        candles = await fetch_candles(
            og_pair.get("pair_address", ""),
            og_pair.get("symbol", "???"),
            og_pair.get("address", ""),
        )
    except Exception as e:
        _logger.warning(
            "OG setup check: candle fetch failed for %s: %s", og_pair.get("symbol"), e
        )
        return False

    if not candles or len(candles) < 20:
        _logger.info(
            "OG %s: insufficient candles (%d) — treating as no setup",
            og_pair.get("symbol"),
            len(candles) if candles else 0,
        )
        return False

    try:
        psef_result = run_psef(candles)
        if not psef_result.get("passed", False):
            _logger.info(
                "OG %s: PSEF failed (%s) — no setup",
                og_pair.get("symbol"),
                psef_result.get("failed_gate", "?"),
            )
            return False
    except Exception as e:
        _logger.warning("OG setup check: PSEF crash for %s: %s", og_pair.get("symbol"), e)
        return False

    try:
        impulse_result = detect_impulse(candles)
        setup_detected = bool(impulse_result.get("setup_detected", False))
        _logger.info(
            "OG %s: setup_detected=%s type=%s",
            og_pair.get("symbol"),
            setup_detected,
            impulse_result.get("setup_type", "?"),
        )
        return setup_detected
    except Exception as e:
        _logger.warning(
            "OG setup check: impulse detector crash for %s: %s",
            og_pair.get("symbol"),
            e,
        )
        return False


async def _send_manual_check_notice(
    bot,
    chat_id,
    skipped_symbol: str,
    og_pair: Dict[str, Any],
) -> None:
    """Send a Telegram notice that a copycat alert was skipped — check OG manually."""
    try:
        from telegram.constants import ParseMode
    except Exception:
        ParseMode = None  # type: ignore

    og_address = og_pair.get("address", "")
    og_mc = og_pair.get("market_cap", 0)
    og_pair_addr = og_pair.get("pair_address", "")
    dex_link = (
        f"https://dexscreener.com/solana/{og_pair_addr}" if og_pair_addr else ""
    )

    msg = (
        f"⚠️ <b>Copycat skipped — OG has active setup</b>\n\n"
        f"Skipped copycat: <b>${skipped_symbol}</b>\n"
        f"OG exists and looks tradeable.\n\n"
        f"OG details:\n"
        f"  • MC: ${og_mc:,.0f}\n"
        f"  • Liquidity: ${og_pair.get('liquidity_usd', 0):,.0f}\n"
    )
    if dex_link:
        msg += f"  • Chart: <a href=\"{dex_link}\">DexScreener</a>\n"
    msg += "\n👉 Check OG manually before entering."

    try:
        if ParseMode is not None:
            await bot.send_message(
                chat_id=chat_id,
                text=msg,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        else:
            await bot.send_message(chat_id=chat_id, text=msg)
    except Exception as e:
        _logger.warning("Failed to send manual-check notice: %s", e)


# ----------------------------------------------------------------------------
# Main entry point — called from scanner.py at the alert-fire point
# ----------------------------------------------------------------------------
async def check_collision_and_route(
    token: Dict[str, Any],
    bot=None,
    chat_id=None,
) -> Dict[str, Any]:
    """
    The single function scanner.py calls. Returns a decision dict:

    {
        "decision": one of DECISION_*,
        "should_fire_original": bool,    # True = fire the original alert
        "extra_tag": str | None,         # tag to add to alert message
        "reason": str,                   # human-readable reason
    }

    Hardened: never raises. If anything goes wrong, returns "fire_normal" so
    the original alert always fires.
    """
    default_result = {
        "decision": DECISION_FIRE_NORMAL,
        "should_fire_original": True,
        "extra_tag": None,
        "reason": "default",
    }

    if not COLLISION_CHECK_ENABLED:
        default_result["reason"] = "collision check disabled"
        return default_result

    symbol = (token.get("symbol") or "").strip()
    my_address = (token.get("address") or "").strip().lower()

    if not symbol or not my_address:
        _logger.info("Missing symbol/address — skipping collision check.")
        return default_result

    try:
        pairs = await _fetch_pairs_with_ticker(symbol)
    except Exception as e:
        _logger.warning("Pair fetch failed for %s: %s — defaulting to fire normal", symbol, e)
        return default_result

    if len(pairs) <= 1:
        _logger.info("[%s] No collision (matches=%d). Fire normal.", symbol, len(pairs))
        return default_result

    og = _identify_og(pairs)
    if og is None:
        _logger.info(
            "[%s] %d pairs but no usable pairCreatedAt timestamps. Fire normal.",
            symbol,
            len(pairs),
        )
        return default_result

    og_address = (og.get("address") or "").strip().lower()
    is_og = og_address == my_address

    if is_og:
        result = {
            "decision": DECISION_FIRE_OG_VERIFIED,
            "should_fire_original": True,
            "extra_tag": "✅ OG verified",
            "reason": f"This token is the OG among {len(pairs)} matches.",
        }
        _logger.info("[%s] OG verified. %d total matches.", symbol, len(pairs))
        return result

    # This token is a copycat. Check whether OG has an active setup.
    try:
        og_active = await _og_has_active_setup(og)
    except Exception as e:
        _logger.warning(
            "[%s] OG setup check crashed: %s — defaulting to fire copycat with tag",
            symbol,
            e,
        )
        og_active = False

    if og_active:
        _logger.info(
            "[%s] COPYCAT skipped. OG (address=%s, MC=$%s) has active setup.",
            symbol,
            og.get("address", "?")[:12],
            f"{og.get('market_cap', 0):,.0f}",
        )
        # Fire the manual-check notice (best effort)
        if bot is not None and chat_id is not None:
            try:
                await _send_manual_check_notice(bot, chat_id, symbol, og)
            except Exception as e:
                _logger.warning("Manual-check notice failed: %s", e)
        return {
            "decision": DECISION_SKIP_COPYCAT,
            "should_fire_original": False,
            "extra_tag": None,
            "reason": "OG has active setup — copycat alert suppressed.",
        }

    # OG exists but is dead (no setup). Fire the copycat alert with a tag.
    _logger.info(
        "[%s] Copycat fires with newer-of-two tag. OG (address=%s) has no active setup.",
        symbol,
        og.get("address", "?")[:12],
    )
    return {
        "decision": DECISION_FIRE_COPYCAT_TAG,
        "should_fire_original": True,
        "extra_tag": "ℹ️ Newer of two — older OG has no setup",
        "reason": "OG exists but is dead/setupless. Trading newer.",
    }
