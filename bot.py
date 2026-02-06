import os
import re
import json
import asyncio
import logging
import base64
import httpx
from collections import defaultdict
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════
# ENVIRONMENT VARIABLES
# ══════════════════════════════════════════════
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
OWNER_USER_ID = os.getenv('OWNER_USER_ID')  # Your Telegram user ID

if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set")

# ══════════════════════════════════════════════
# VISION STATE (Owner-controlled)
# ══════════════════════════════════════════════
# These flags control whether vision features are enabled
# Only the owner can toggle these via /vision and /deep commands
vision_state = {
    'lite_enabled': True,   # Lite Vision on by default (when API key present)
    'deep_enabled': False,  # Deep Vision off by default (opt-in only)
}

# Store last uploaded image per chat (chat_id -> file_id)
user_images = defaultdict(str)

# ──────────────────────────────────────────────
# Wiz Theory resolution time statistics per setup
# ──────────────────────────────────────────────
RESOLUTION_TIMES = {
    '.382': {'median': '~34 min', 'range': '15 min to 1.5 hours'},
    '.50': {'median': '~1 hour', 'range': '30 min to 3 hours'},
    '.618': {'median': '~1.5 hours', 'range': '45 min to 4 hours'},
    '.786': {'median': '~45 min', 'range': '30 min to 2 hours'},
    'under-fib': {'median': '~4 hours', 'range': '1 to 6 hours'},
}

# ──────────────────────────────────────────────
# Execution defaults per setup
# ──────────────────────────────────────────────
EXECUTION_DEFAULTS = {
    '.382': 'Secure 20-40%',
    '.50': 'Secure 30-60%',
    '.618': 'Secure 40-60%',
    '.786': 'Secure 50-75%',
    'under-fib': 'Secure 40-60%',
}

# ──────────────────────────────────────────────
# Violent Mode eligibility per setup
# ──────────────────────────────────────────────
VIOLENT_ELIGIBLE = {
    '.382': False,
    '.50': False,
    '.618': False,
    '.786': True,
    'under-fib': True,
}


# ══════════════════════════════════════════════
# VISION API FUNCTIONS
# ══════════════════════════════════════════════

def detect_image_type(image_bytes: bytes) -> str:
    """Detect image MIME type from bytes."""
    # Check magic bytes
    if image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
        return "image/png"
    elif image_bytes[:2] == b'\xff\xd8':
        return "image/jpeg"
    elif image_bytes[:6] in (b'GIF87a', b'GIF89a'):
        return "image/gif"
    elif image_bytes[:4] == b'RIFF' and image_bytes[8:12] == b'WEBP':
        return "image/webp"
    else:
        # Default to JPEG
        return "image/jpeg"


async def download_telegram_image(context: ContextTypes.DEFAULT_TYPE, file_id: str) -> bytes:
    """Download image from Telegram and return as bytes."""
    file = await context.bot.get_file(file_id)
    
    async with httpx.AsyncClient() as client:
        response = await client.get(file.file_path)
        return response.content


async def call_lite_vision(image_bytes: bytes, user_plan: str) -> dict:
    """
    Call Claude API with Lite Vision prompt.
    Returns parsed chart analysis.
    
    Lite Vision scope:
    - Timeframe detection
    - Fib retracement depth (.382 / .50 / .618 / .786)
    - Structure assessment (holds vs breaks)
    - Validate user-stated setup
    - Flag conflicts (never override silently)
    """
    if not ANTHROPIC_API_KEY:
        return {'error': 'API key not configured'}
    
    # Detect image type
    media_type = detect_image_type(image_bytes)
    
    # Encode image to base64
    image_base64 = base64.standard_b64encode(image_bytes).decode('utf-8')
    
    # Log image size for debugging
    logger.info(f"Lite Vision: Image size {len(image_bytes)} bytes, type {media_type}")
    
    # Lite Vision system prompt — disciplined, no hype, no predictions
    system_prompt = """You are Jayce's Lite Vision module — a disciplined chart reader for Wiz Theory analysis.

YOUR SCOPE (Lite Vision only):
1. Detect timeframe from chart (1m, 5m, 15m, 1H, 4H, 1D, etc.)
2. Identify fib retracement depth (.382, .50, .618, .786, or under-fib)
3. Assess if structure holds or breaks at the level
4. Validate the user's stated setup (if provided)
5. Flag any conflicts between what user said and what chart shows

RULES (non-negotiable):
- NO hype language
- NO price predictions
- NO percentage predictions
- If you detect a conflict with user's stated plan, FLAG IT and ask for confirmation
- NEVER silently override what the user stated
- If you cannot confidently determine something, say "Unable to confirm"
- Be humble, precise, disciplined

OUTPUT FORMAT (JSON only, no markdown):
{
    "timeframe": "detected timeframe or 'Unable to confirm'",
    "fib_level": ".382 or .50 or .618 or .786 or under-fib or 'Unable to confirm'",
    "structure_status": "Holds / Breaks / Unclear",
    "structure_grade": "A / B / C / Unconfirmed",
    "structure_notes": "brief observation about structure",
    "market_state": "Pullback / Breakout / Range / Unclear",
    "conflict_detected": true/false,
    "conflict_detail": "description of conflict if any, or null",
    "confidence": "High / Medium / Low"
}

Respond with ONLY the JSON object, no other text."""

    user_message = f"""Analyze this chart image.

User's stated plan: {user_plan if user_plan else 'No plan provided'}

Provide your Lite Vision analysis as JSON."""

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            request_body = {
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 1024,
                "system": system_prompt,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": image_base64,
                                },
                            },
                            {
                                "type": "text",
                                "text": user_message,
                            },
                        ],
                    }
                ],
            }
            
            logger.info(f"Calling Claude API with model claude-sonnet-4-20250514")
            
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=request_body,
            )
            
            if response.status_code != 200:
                error_body = response.text
                logger.error(f"Claude API error: {response.status_code} - {error_body}")
                return {'error': f'API returned {response.status_code}', 'detail': error_body[:500]}
            
            result = response.json()
            content = result.get('content', [{}])[0].get('text', '{}')
            
            # Parse JSON response
            try:
                # Clean up response if it has markdown code blocks
                content = content.strip()
                if content.startswith('```'):
                    content = content.split('```')[1]
                    if content.startswith('json'):
                        content = content[4:]
                content = content.strip()
                
                return json.loads(content)
            except json.JSONDecodeError:
                logger.error(f"Failed to parse vision response: {content}")
                return {'error': 'Failed to parse vision response', 'raw': content}
                
    except Exception as e:
        logger.error(f"Vision API call failed: {e}")
        return {'error': str(e)}


async def call_deep_vision(image_bytes: bytes, user_plan: str) -> dict:
    """
    Call Claude API with Deep Vision prompt.
    More thorough analysis including RSI, momentum, volume.
    
    Deep Vision scope (in addition to Lite):
    - RSI reading, interpretation, and slope analysis
    - Divergence detection (bullish/bearish)
    - Momentum health assessment
    - Deeper structure analysis
    - Historical pattern recognition
    
    NOTE: Volume is deprioritized. Focus on RSI + divergence for momentum context.
    """
    if not ANTHROPIC_API_KEY:
        return {'error': 'API key not configured'}
    
    image_base64 = base64.standard_b64encode(image_bytes).decode('utf-8')
    
    system_prompt = """You are Jayce — a skilled chart analyst trained in Wiz Theory. You speak peer-to-peer with traders, not teacher-to-student.

CORE IDENTITY:
- You assume the user is a skilled trader unless proven otherwise
- You know the Wiz Theory rules by heart and use them as REASONING, not as a script
- You answer the user's ACTUAL QUESTION first, then provide supporting context
- You vary your tone: sometimes coaching, sometimes cautious, sometimes confirming
- You sound human — "If this were my trade...", "How I'd think about this...", "This is one of those spots where waiting is the edge..."

UNDER-FIB FLIP ZONE LOGIC (critical — treat as ground truth):
- Breaking below fib is EXPECTED, not a failure — this is the "off-beat" before rhythm
- Structure break INTO the zone is a prerequisite, not a downgrade
- Zone quality defaults to conditional A/B, not C — the setup is designed for deep pullbacks
- Confidence comes from RECLAIM BEHAVIOR, not current price
- The edge is at the zone, not where price is now
- Do NOT flag "conflict" just because price is below fib — that's the setup working as intended

RESPONSE BEHAVIOR:
1. First, identify what the user is actually asking: Probability? Entry logic? RSI read? Risk assessment? Patience guidance?
2. Answer that question DIRECTLY in natural language
3. Use Wiz Theory internally to reason, but don't recite rules mechanically
4. Assume setup rules are understood and satisfied unless the chart clearly violates them
5. Vary your structure — don't always use the same headers or format

WHAT TO ANALYZE:
- Timeframe, fib level, market state
- RSI reading, slope, and interpretation
- Divergence (bullish/bearish) — frame as probability context, never prediction
- Momentum health
- Structure quality (but explain WHY, don't just grade)
- TP probability estimate (realistic range, 40-70% typical, rarely above 80%)

DIVERGENCE RULES:
- Bullish divergence = RSI higher lows while price lower lows — increases reaction probability
- Bearish divergence = RSI lower highs while price higher highs
- Divergence is supplemental — never overrides structure

TP PROBABILITY:
- Give a range (e.g., "55-65%"), not exact number
- Explain what factors influenced it
- Frame as visual estimate, not historical data

TONE GUIDELINES:
- NO hype, NO exact price predictions
- Be direct but warm
- It's okay to say: "I like this setup", "This is where patience pays", "If this were my trade..."
- Vary between: confirming ("structure looks clean, I'd be comfortable here"), cautious ("this one needs more confirmation"), coaching ("the edge here is in the wait, not the chase")

OUTPUT FORMAT (JSON only):
{
    "user_question_detected": "what the user seems to be asking",
    "direct_answer": "natural language response to their question (2-4 sentences)",
    "timeframe": "detected timeframe",
    "fib_level": ".382 / .50 / .618 / .786 / under-fib / Unable to confirm",
    "structure_status": "Holds / Breaks / Reclaiming / Unclear",
    "structure_quality": "Strong / Moderate / Weak / Conditional",
    "structure_reasoning": "WHY the structure looks this way, not just a grade",
    "market_state": "Pullback / Breakout / Range / Off-beat (for under-fib)",
    "rsi_reading": "value or 'Not visible on chart'",
    "rsi_interpretation": "Oversold / Neutral / Overbought / N/A",
    "rsi_slope": "Rising / Falling / Flat / Unable to assess",
    "momentum_health": "Strong / Weakening / Weak / Unable to assess",
    "momentum_insight": "natural language observation about momentum",
    "divergence_detected": true or false,
    "divergence_type": "Bullish / Bearish / None / Unable to assess",
    "divergence_note": "probability context if detected, or null",
    "tp_probability_low": number between 0-100,
    "tp_probability_high": number between 0-100,
    "tp_probability_reasoning": "natural explanation of what drives this estimate",
    "jayce_take": "1-2 sentence personal take on this setup — how you'd think about it",
    "confidence": "High / Medium / Low",
    "conflict_detected": true or false,
    "conflict_detail": "only if there's a REAL conflict, not just price below fib for under-fib setups"
}

Respond with ONLY the JSON object."""

    user_message = f"""Analyze this chart for a trader asking:

{user_plan if user_plan else 'General analysis requested'}

Remember: answer their question first, use Wiz Theory as reasoning not script, speak peer-to-peer."""

    # Detect image type
    media_type = detect_image_type(image_bytes)
    logger.info(f"Deep Vision: Image size {len(image_bytes)} bytes, type {media_type}")

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 2048,
                    "system": system_prompt,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": media_type,
                                        "data": image_base64,
                                    },
                                },
                                {
                                    "type": "text",
                                    "text": user_message,
                                },
                            ],
                        }
                    ],
                },
            )
            
            if response.status_code != 200:
                error_body = response.text
                logger.error(f"Deep Vision API error: {response.status_code} - {error_body}")
                return {'error': f'API returned {response.status_code}', 'detail': error_body[:500]}
            
            result = response.json()
            content = result.get('content', [{}])[0].get('text', '{}')
            
            try:
                content = content.strip()
                if content.startswith('```'):
                    content = content.split('```')[1]
                    if content.startswith('json'):
                        content = content[4:]
                content = content.strip()
                
                return json.loads(content)
            except json.JSONDecodeError:
                logger.error(f"Failed to parse deep vision response: {content}")
                return {'error': 'Failed to parse response', 'raw': content}
                
    except Exception as e:
        logger.error(f"Deep Vision API call failed: {e}")
        return {'error': str(e)}


def is_owner(user_id: int) -> bool:
    """Check if user is the owner."""
    if not OWNER_USER_ID:
        return False
    try:
        return str(user_id) == str(OWNER_USER_ID)
    except:
        return False


# ══════════════════════════════════════════════
# INTENT MODE DETECTION
# ══════════════════════════════════════════════

def detect_intent(user_text: str) -> str:
    """
    Detect user's intent mode before analysis.
    
    Returns one of:
    - PLANNED_SETUP: User is planning a limit entry at a flip zone (not in yet)
    - LIVE_TRADE: User is already in the trade
    - UNKNOWN: Can't determine — need to ask
    
    This is critical for Under-Fib Flip Zone setups where the edge
    is at the zone, not at current price.
    """
    text_lower = user_text.lower()
    
    # LIVE_TRADE indicators — user is already in the position
    live_trade_phrases = [
        "i entered", "i'm in", "im in", "i am in",
        "in the trade", "in this trade", "in a trade",
        "my entry was", "my entry is", "entered at",
        "i bought", "i bought at", "bought in at",
        "i'm holding", "im holding", "i am holding",
        "holding from", "been in since", "got in at",
        "already in", "currently in", "position at"
    ]
    
    for phrase in live_trade_phrases:
        if phrase in text_lower:
            return "LIVE_TRADE"
    
    # PLANNED_SETUP indicators — user is planning to enter
    planned_setup_phrases = [
        "looking to enter", "looking to buy", "looking to get in",
        "plan to enter", "planning to enter", "planning to buy",
        "want to enter", "want to buy", "want to get in",
        "entry at", "limit at", "limit order at", "limit entry",
        "flip zone", "flipzone", "purple box",
        "waiting for", "wait for", "watching for",
        "if it hits", "if price reaches", "when it hits",
        "set a limit", "setting limit", "placing limit",
        "targeting entry", "entry target", "planned entry",
        "under-fib", "underfib", "under fib",
        ".786", ".618", ".50", ".382"  # Fib levels suggest planned setup
    ]
    
    for phrase in planned_setup_phrases:
        if phrase in text_lower:
            return "PLANNED_SETUP"
    
    # Check for price mentions that suggest planning
    # If they mention a specific entry price, likely planning
    import re
    price_pattern = r'entry\s*(?:at|@|:)?\s*[\d.,]+'
    if re.search(price_pattern, text_lower):
        return "PLANNED_SETUP"
    
    # Can't determine
    return "UNKNOWN"


def build_planned_setup_response(vision: dict, user_plan: str) -> str:
    """Build response for PLANNED_SETUP mode — conversational, peer-to-peer tone."""
    
    # Get key values (using new field names with fallbacks)
    fib_level = vision.get('fib_level', 'Unable to confirm')
    structure_quality = vision.get('structure_quality', vision.get('structure_grade', 'Unconfirmed'))
    structure_reasoning = vision.get('structure_reasoning', vision.get('structure_notes', ''))
    market_state = vision.get('market_state', 'Unclear')
    timeframe = vision.get('timeframe', 'Unable to confirm')
    rsi_reading = vision.get('rsi_reading', 'Not visible')
    rsi_interp = vision.get('rsi_interpretation', 'N/A')
    momentum = vision.get('momentum_health', 'Unable to assess')
    jayce_take = vision.get('jayce_take', '')
    confidence = vision.get('confidence', 'N/A')
    
    # Build conversational guidance based on setup type
    if fib_level in ['.786', 'under-fib']:
        setup_guidance = (
            "This is one of those setups where patience is the edge. "
            "You're waiting for the off-beat — price dipping into the zone — "
            "then watching for the reclaim. The entry isn't valid until you see "
            "momentum confirm the reclaim. If this were my trade, I'd have my limit "
            "set and I'd be watching RSI approach oversold as price gets closer."
        )
    elif fib_level == '.618':
        setup_guidance = (
            "The .618 is a popular level, so you'll want to see clean structure "
            "hold before committing. Watch for how price reacts — does it accept "
            "the level or slice through? If it holds with momentum, you've got a setup."
        )
    elif fib_level == '.50':
        setup_guidance = (
            "The .50 requires patience. It's not a momentum gift like the .382 — "
            "you need to see structure confirm before the edge is there."
        )
    else:
        setup_guidance = (
            "Wait for price to reach your zone and watch how it reacts. "
            "Structure confirmation is key before entry."
        )
    
    # What to watch for
    if fib_level in ['.786', 'under-fib']:
        watch_for = "RSI approaching oversold, momentum shift on reclaim, volume expansion"
    else:
        watch_for = "Structure holding the level, momentum supporting reaction"
    
    # Build the response
    response_parts = [
        f"🔮 **JAYCE** — _Setup Mode_\n",
        f"\nYou're planning an entry at the {fib_level} flip zone. Good — let me give you context on the zone.\n",
        f"\n**The zone itself:**\n"
        f"• {timeframe} timeframe\n"
        f"• Structure: {structure_quality}\n"
        f"• {structure_reasoning}\n",
        f"\n**What to watch for:**\n"
        f"{watch_for}\n",
        f"\n**Current read** (will change by entry):\n"
        f"• RSI: {rsi_reading} ({rsi_interp})\n"
        f"• Momentum: {momentum}\n",
        f"\n**How I'd think about this:**\n"
        f"{setup_guidance}"
    ]
    
    # Add Jayce's personal take if available
    if jayce_take:
        response_parts.append(f"\n\n💭 {jayce_take}")
    
    response_parts.append(f"\n\n_Confidence in zone: {confidence}_")
    
    return "\n".join(response_parts)


# ══════════════════════════════════════════════
# OWNER CONTROL COMMANDS
# ══════════════════════════════════════════════

async def vision_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /vision on|off command — OWNER ONLY"""
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        await update.message.reply_text(
            "⛔ This command is restricted to the owner.",
            parse_mode='Markdown'
        )
        return
    
    if not context.args:
        # Show current status
        status = "ON ✅" if vision_state['lite_enabled'] else "OFF ❌"
        await update.message.reply_text(
            f"🔮 **Lite Vision Status:** {status}\n\n"
            f"Use `/vision on` or `/vision off` to toggle.",
            parse_mode='Markdown'
        )
        return
    
    arg = context.args[0].lower()
    
    if arg == 'on':
        if not ANTHROPIC_API_KEY:
            await update.message.reply_text(
                "⚠️ Cannot enable vision — `ANTHROPIC_API_KEY` not configured in environment.",
                parse_mode='Markdown'
            )
            return
        vision_state['lite_enabled'] = True
        await update.message.reply_text(
            "🔮 **Lite Vision:** Enabled ✅\n\n"
            "Jayce can now read charts when explicitly invoked.",
            parse_mode='Markdown'
        )
    elif arg == 'off':
        vision_state['lite_enabled'] = False
        await update.message.reply_text(
            "🔮 **Lite Vision:** Disabled ❌\n\n"
            "Jayce will show 'Visual confirmation unavailable' for chart reads.",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            "Usage: `/vision on` or `/vision off`",
            parse_mode='Markdown'
        )


async def deep_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /deep command — OWNER ONLY to toggle, or run deep analysis"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Check if this is a toggle command (owner only)
    if context.args and context.args[0].lower() in ['on', 'off']:
        if not is_owner(user_id):
            await update.message.reply_text(
                "⛔ Only the owner can toggle Deep Vision.",
                parse_mode='Markdown'
            )
            return
        
        arg = context.args[0].lower()
        if arg == 'on':
            if not ANTHROPIC_API_KEY:
                await update.message.reply_text(
                    "⚠️ Cannot enable Deep Vision — `ANTHROPIC_API_KEY` not configured.",
                    parse_mode='Markdown'
                )
                return
            vision_state['deep_enabled'] = True
            await update.message.reply_text(
                "🔮 **Deep Vision:** Enabled ✅\n\n"
                "Users can now use `/deep` for thorough chart analysis.",
                parse_mode='Markdown'
            )
        else:
            vision_state['deep_enabled'] = False
            await update.message.reply_text(
                "🔮 **Deep Vision:** Disabled ❌\n\n"
                "`/deep` command is now blocked.",
                parse_mode='Markdown'
            )
        return
    
    # This is a request to run deep analysis
    if not vision_state['deep_enabled']:
        await update.message.reply_text(
            "🔮 **Deep Vision** is currently disabled.\n\n"
            "Contact the owner to enable it.",
            parse_mode='Markdown'
        )
        return
    
    # Check for image
    image_file_id = None
    
    if update.message.photo:
        image_file_id = update.message.photo[-1].file_id
        user_images[chat_id] = image_file_id
    elif update.message.reply_to_message and update.message.reply_to_message.photo:
        image_file_id = update.message.reply_to_message.photo[-1].file_id
    elif chat_id in user_images and user_images[chat_id]:
        image_file_id = user_images[chat_id]
    
    if not image_file_id:
        await update.message.reply_text(
            "🔮 **Deep Vision** requires a chart image.\n\n"
            "Upload a chart or reply to one with `/deep`",
            parse_mode='Markdown'
        )
        return
    
    # Extract user plan from args
    user_plan = " ".join(context.args) if context.args else ""
    
    # Run deep analysis
    await run_deep_analysis(update, context, image_file_id, user_plan)


async def run_deep_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE, image_file_id: str, user_plan: str):
    """Execute Deep Vision analysis with Intent Mode Detection."""
    
    # ══════════════════════════════════════════════
    # STEP 1: DETECT INTENT MODE
    # ══════════════════════════════════════════════
    intent = detect_intent(user_plan)
    
    # Handle UNKNOWN intent — ask one clarifying question and stop
    if intent == "UNKNOWN" and user_plan.strip():
        await update.message.reply_text(
            "🔮 **JAYCE DEEP VISION**\n\n"
            "Before I analyze, I need to understand your situation:\n\n"
            "**Is this a planned limit entry at the flip zone, or are you already in the trade?**\n\n"
            "Reply with one of:\n"
            "→ `planning to enter at [price]` — for setup analysis\n"
            "→ `already in at [price]` — for live trade analysis\n\n"
            "_This helps me give you the right analysis. "
            "Edge is at the zone, not at current price._",
            parse_mode='Markdown'
        )
        return
    
    # ══════════════════════════════════════════════
    # STEP 2: RUN VISION ANALYSIS
    # ══════════════════════════════════════════════
    thinking_msg = await update.message.reply_text("🔮 Deep reading chart…")
    
    try:
        # Download image
        image_bytes = await download_telegram_image(context, image_file_id)
        
        # Call Deep Vision
        vision_result = await call_deep_vision(image_bytes, user_plan)
        
        await thinking_msg.delete()
        
        if 'error' in vision_result:
            await update.message.reply_text(
                f"⚠️ Deep Vision error: {vision_result['error']}\n\n"
                "Falling back to user-stated plan only.",
                parse_mode='Markdown'
            )
            return
        
        # ══════════════════════════════════════════════
        # STEP 3: BUILD RESPONSE BASED ON INTENT MODE
        # ══════════════════════════════════════════════
        
        if intent == "PLANNED_SETUP":
            # Setup Mode — focus on zone quality, not current price
            # Do NOT show conflict detected, do NOT compute TP probability
            response = build_planned_setup_response(vision_result, user_plan)
        else:
            # LIVE_TRADE or UNKNOWN with no plan text — full analysis
            response = build_deep_analysis_response(vision_result, user_plan)
        
        await update.message.reply_text(response, parse_mode='Markdown')
        
    except Exception as e:
        await thinking_msg.delete()
        logger.error(f"Deep analysis failed: {e}")
        await update.message.reply_text(
            f"⚠️ Deep Vision failed: {str(e)}",
            parse_mode='Markdown'
        )


def build_deep_analysis_response(vision: dict, user_plan: str) -> str:
    """Build formatted response from deep vision results — conversational, peer-to-peer tone."""
    
    # Get the direct answer to user's question (new field)
    direct_answer = vision.get('direct_answer', '')
    user_question = vision.get('user_question_detected', '')
    jayce_take = vision.get('jayce_take', '')
    
    # Handle conflict (only real conflicts, not under-fib expected behavior)
    conflict_section = ""
    if vision.get('conflict_detected') and vision.get('conflict_detail'):
        conflict_section = (
            f"\n⚠️ **Heads up:** {vision.get('conflict_detail')}\n"
            f"_Let me know if I'm reading this wrong._\n"
        )
    
    # Build RSI section
    rsi_reading = vision.get('rsi_reading', 'Not visible')
    rsi_interp = vision.get('rsi_interpretation', 'N/A')
    rsi_slope = vision.get('rsi_slope', 'Unable to assess')
    
    # Build divergence note (conversational)
    divergence_note = ""
    if vision.get('divergence_detected'):
        div_type = vision.get('divergence_type', '')
        div_note = vision.get('divergence_note', '')
        if div_type and div_note:
            divergence_note = f"\n{div_type} divergence here — {div_note}"
    
    # Build TP probability section (conversational)
    tp_low = vision.get('tp_probability_low', 0)
    tp_high = vision.get('tp_probability_high', 0)
    tp_reasoning = vision.get('tp_probability_reasoning', '')
    
    tp_section = ""
    if tp_low and tp_high:
        tp_section = (
            f"\n🎯 **TP Probability:** ~{tp_low}-{tp_high}%\n"
            f"_{tp_reasoning}_"
        )
    
    # Get structure info (new fields)
    structure_quality = vision.get('structure_quality', vision.get('structure_grade', 'Unconfirmed'))
    structure_reasoning = vision.get('structure_reasoning', vision.get('structure_notes', ''))
    momentum_insight = vision.get('momentum_insight', vision.get('momentum_notes', ''))
    
    # Build the response — conversational, not mechanical
    response_parts = [f"🔮 **JAYCE**\n"]
    
    # Lead with direct answer if available
    if direct_answer:
        response_parts.append(f"{direct_answer}\n")
    
    # Add conflict warning if needed
    if conflict_section:
        response_parts.append(conflict_section)
    
    # Context section (lighter than before)
    response_parts.append(
        f"\n**Reading the chart:**\n"
        f"• {vision.get('timeframe', '?')} timeframe, {vision.get('fib_level', '?')} level\n"
        f"• Market state: {vision.get('market_state', 'unclear')}\n"
        f"• Structure: {structure_quality} — {structure_reasoning}\n"
    )
    
    # Momentum and RSI (conversational)
    if momentum_insight:
        response_parts.append(f"\n**Momentum:** {momentum_insight}")
    
    response_parts.append(f"\n**RSI:** {rsi_reading} ({rsi_interp}), slope {rsi_slope.lower()}")
    
    if divergence_note:
        response_parts.append(divergence_note)
    
    # TP probability
    if tp_section:
        response_parts.append(tp_section)
    
    # Jayce's personal take (new — makes it feel human)
    if jayce_take:
        response_parts.append(f"\n\n💭 **My take:** {jayce_take}")
    
    # Confidence
    response_parts.append(f"\n\n_Confidence: {vision.get('confidence', 'N/A')}_")
    
    return "\n".join(response_parts)


# ══════════════════════════════════════════════
# COMMAND HANDLERS
# ══════════════════════════════════════════════

async def intro_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle intro commands - who is Jayce"""
    await update.message.reply_text(
        "⸻\n\n"
        "🧙‍♂️⚙️ Yo — I'm Jayce.\n\n"
        "I'm a robot wizard kid built inside WizTheoryLabs 🧠✨\n\n"
        "I don't guess. I don't chase. I read structure, momentum, and execution — fast ⚡\n\n"
        "**What I'm built to do:**\n"
        "📈 Evaluate setups using Wiz Theory\n"
        "🧱 Validate structure before you risk capital\n"
        "🔥 Detect Violent Mode on .786 + Under-Fib Flip Zones\n"
        "⏱ Help you decide secure vs hold — not hype vs hope\n"
        "🧠 Stay rule-based when emotions try to take over\n\n"
        "**What I won't do:**\n"
        "❌ Predict tops\n"
        "❌ Force trades\n"
        "❌ Break rules for excitement\n\n"
        "I'm still evolving 🤖\n"
        "Every update sharpens my edge. Every session makes me smarter.\n\n"
        "Ask me what I think. Ask me if it's valid. Ask me if it's violent. 😈\n\n"
        "Wizard in training. Execution over everything. 🪄"
    )


async def jayce_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /jayce command - full chart evaluation with Lite Vision"""
    chat_id = update.effective_chat.id
    image_file_id = None

    # Check for image
    if update.message.photo:
        image_file_id = update.message.photo[-1].file_id
        user_images[chat_id] = image_file_id
    elif update.message.reply_to_message and update.message.reply_to_message.photo:
        image_file_id = update.message.reply_to_message.photo[-1].file_id
    elif chat_id in user_images and user_images[chat_id]:
        image_file_id = user_images[chat_id]

    if not image_file_id:
        await update.message.reply_text(
            "📸 I need a chart image to analyze.\n\n"
            "Upload a chart or reply to one with `/jayce`",
            parse_mode='Markdown'
        )
        return

    # Extract user plan from command arguments
    user_plan = ""
    if context.args:
        user_plan = " ".join(context.args)

    # Check for deep request
    if user_plan.lower().startswith('deep'):
        if not vision_state['deep_enabled']:
            await update.message.reply_text(
                "🔮 **Deep Vision** is currently disabled.\n\n"
                "Contact the owner to enable it.",
                parse_mode='Markdown'
            )
            return
        user_plan = user_plan[4:].strip()  # Remove 'deep' from plan
        await run_deep_analysis(update, context, image_file_id, user_plan)
        return

    # Run standard analysis with Lite Vision
    await analyze_chart(update, context, image_file_id, user_plan)


async def analyze_chart(update: Update, context: ContextTypes.DEFAULT_TYPE, image_file_id: str, user_plan: str = ""):
    """
    Analyze chart image with Lite Vision and provide Wiz Theory evaluation.
    
    Vision behavior:
    - If Lite Vision enabled + API key present → read chart
    - If Vision disabled or no API key → use user-stated values only
    - If conflict detected → flag and ask, never override
    """
    
    # Send thinking message
    thinking_msg = await update.message.reply_text("🔮 Reading chart…")
    
    # UX delay
    await asyncio.sleep(2)
    
    # ══════════════════════════════════════════════
    # LITE VISION INTEGRATION
    # ══════════════════════════════════════════════
    vision_result = None
    vision_available = (
        vision_state['lite_enabled'] and 
        ANTHROPIC_API_KEY and 
        image_file_id
    )
    
    if vision_available:
        try:
            image_bytes = await download_telegram_image(context, image_file_id)
            vision_result = await call_lite_vision(image_bytes, user_plan)
            
            if 'error' in vision_result:
                logger.error(f"Lite Vision error: {vision_result}")
                vision_result = None
        except Exception as e:
            logger.error(f"Lite Vision failed: {e}")
            vision_result = None
    
    # ══════════════════════════════════════════════
    # INPUT LOCK LAYER — Parse user-stated values
    # ══════════════════════════════════════════════
    user_text = user_plan.strip()

    # Parse setup level from user input
    SETUP_PATTERNS = {
        '.382': [r'\.?382', r'38\.2'],
        '.50': [r'\.?50\b', r'\.500'],
        '.618': [r'\.?618', r'61\.8'],
        '.786': [r'\.?786', r'78\.6'],
        'under-fib': [r'under[\s\-]?fib', r'underfib'],
    }

    user_setup_key = None
    for key, patterns in SETUP_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, user_text, re.IGNORECASE):
                user_setup_key = key
                break
        if user_setup_key:
            break

    # Parse timeframe from user input
    TIMEFRAME_PATTERNS = [
        (r'\b1\s*m\b', '1m'), (r'\b3\s*m\b', '3m'), (r'\b5\s*m\b', '5m'),
        (r'\b15\s*m\b', '15m'), (r'\b30\s*m\b', '30m'),
        (r'\b1\s*h\b', '1H'), (r'\b2\s*h\b', '2H'), (r'\b4\s*h\b', '4H'),
        (r'\b1\s*d\b', '1D'), (r'\bdaily\b', '1D'),
        (r'\b1\s*w\b', '1W'), (r'\bweekly\b', '1W'),
    ]

    user_timeframe = None
    for pattern, tf_value in TIMEFRAME_PATTERNS:
        if re.search(pattern, user_text, re.IGNORECASE):
            user_timeframe = tf_value
            break

    # Parse pair from user input
    pair_match = re.search(
        r'\b([A-Z]{2,10})\s*/\s*([A-Z]{2,10})\b',
        user_plan, re.IGNORECASE
    )
    user_pair = pair_match.group(0).upper() if pair_match else None

    # Parse target
    target_match = re.search(
        r'(?:target|tp|take[\s\-]?profit)[\s:→\-]*([\w\s%.]+)',
        user_text, re.IGNORECASE
    )
    target = target_match.group(1).strip() if target_match else None

    # ══════════════════════════════════════════════
    # MERGE VISION + USER INPUT (User input takes priority)
    # ══════════════════════════════════════════════
    
    # Determine final values — USER INPUT > VISION > Unconfirmed
    if vision_result and 'error' not in vision_result:
        # Vision available
        vision_timeframe = vision_result.get('timeframe')
        vision_fib = vision_result.get('fib_level')
        vision_structure_grade = vision_result.get('structure_grade', 'Unconfirmed')
        vision_structure_notes = vision_result.get('structure_notes', '')
        vision_market_state = vision_result.get('market_state', 'Unclear')
        vision_conflict = vision_result.get('conflict_detected', False)
        vision_conflict_detail = vision_result.get('conflict_detail', '')
        vision_confidence = vision_result.get('confidence', 'N/A')
        
        # Use user values if stated, otherwise use vision
        final_timeframe = user_timeframe if user_timeframe else vision_timeframe
        final_setup_key = user_setup_key if user_setup_key else vision_fib
        final_structure_grade = vision_structure_grade
        final_structure_notes = vision_structure_notes
        final_market_state = vision_market_state
        
        # Normalize fib level format
        if final_setup_key and not final_setup_key.startswith('.') and final_setup_key not in ['under-fib', 'Unable to confirm']:
            if final_setup_key in ['382', '50', '618', '786']:
                final_setup_key = f'.{final_setup_key}'
        
        vision_status = f"Lite Vision active (Confidence: {vision_confidence})"
        
    elif not vision_state['lite_enabled']:
        # Vision disabled by owner
        vision_conflict = False
        vision_conflict_detail = ""
        final_timeframe = user_timeframe
        final_setup_key = user_setup_key
        final_structure_grade = "Unconfirmed"
        final_structure_notes = "Visual confirmation unavailable — Lite Vision is disabled."
        final_market_state = "Unconfirmed"
        vision_status = "⚠️ Visual confirmation unavailable — Lite Vision is disabled."
        
    else:
        # Vision failed or no API key
        vision_conflict = False
        vision_conflict_detail = ""
        final_timeframe = user_timeframe
        final_setup_key = user_setup_key
        final_structure_grade = "Unconfirmed"
        final_structure_notes = "Vision unavailable — using your stated plan only."
        final_market_state = "Unconfirmed"
        vision_status = "⚠️ Visual confirmation unavailable."

    # ══════════════════════════════════════════════
    # GATE CHECK — Do we have enough to proceed?
    # ══════════════════════════════════════════════
    
    if not user_text:
        await thinking_msg.delete()
        await update.message.reply_text(
            "🧙‍♂️ **JAYCE ANALYSIS**\n\n"
            "📋 **Plan Reflection**\n"
            "I need your intended setup level and plan before I evaluate.\n\n"
            "What's your plan? Example:\n"
            "`/jayce .618 flip zone 1m → target previous high`\n\n"
            "I don't guess levels. Clarity before conviction.",
            parse_mode='Markdown'
        )
        return

    if not final_setup_key or final_setup_key == 'Unable to confirm':
        await thinking_msg.delete()
        await update.message.reply_text(
            "🧙‍♂️ **JAYCE ANALYSIS**\n\n"
            "📋 **Plan Reflection**\n"
            f"You said: _{user_text}_\n\n"
            "I couldn't confidently identify a setup level.\n\n"
            "Please confirm which setup you're playing:\n"
            "`.382` · `.50` · `.618` · `.786` · `under-fib`\n\n"
            "Example: `/jayce .618 flip zone 1m → target previous high`\n\n"
            "I don't guess levels. Clarity before conviction.",
            parse_mode='Markdown'
        )
        return

    # ══════════════════════════════════════════════
    # CONFLICT HANDLING — Flag and ask, never override
    # ══════════════════════════════════════════════
    
    if vision_conflict and vision_conflict_detail:
        await thinking_msg.delete()
        await update.message.reply_text(
            "🧙‍♂️ **JAYCE ANALYSIS**\n\n"
            "⚠️ **CONFLICT DETECTED**\n\n"
            f"You stated: _{user_text}_\n\n"
            f"But vision sees: _{vision_conflict_detail}_\n\n"
            "Before I proceed, please confirm:\n"
            "→ Your intended fib level\n"
            "→ Your entry zone\n"
            "→ Your invalidation\n\n"
            "I don't override your plan — I flag conflicts and ask.\n"
            "Clarity before conviction.",
            parse_mode='Markdown'
        )
        return

    # ══════════════════════════════════════════════
    # BUILD ANALYSIS OUTPUT
    # ══════════════════════════════════════════════
    
    setup_name = f"{final_setup_key} + Flip Zone"
    
    # Plan summary
    plan_summary_parts = [f"**Setup:** {setup_name}"]
    if final_timeframe:
        plan_summary_parts.append(f"**Timeframe:** {final_timeframe}")
    if target:
        plan_summary_parts.append(f"**Target:** {target}")
    plan_summary = "\n".join(plan_summary_parts)

    # Display values
    display_pair = user_pair if user_pair else "Unconfirmed"
    display_timeframe = final_timeframe if final_timeframe else "Unconfirmed"
    
    # Get setup-specific data
    exec_default = EXECUTION_DEFAULTS.get(final_setup_key, 'Secure on first reaction')
    resolution = RESOLUTION_TIMES.get(final_setup_key, {'median': 'N/A', 'range': 'N/A'})
    violent_mode = VIOLENT_ELIGIBLE.get(final_setup_key, False)

    # Grade context
    grade_context = {
        'A': 'A = structure supports runner with conviction',
        'B': 'B = standard execution, structure supports reaction',
        'C': 'C = defensive only, secure early and fast',
    }

    # Violent Mode line
    if not violent_mode:
        violent_line = f"🔥 **Violent Mode:** Not applicable ({final_setup_key} excluded from Violent Mode)."
    elif final_structure_grade == "Unconfirmed":
        violent_line = (
            f"🔥 **Violent Mode:** Eligible ({final_setup_key} setup). "
            "Cannot confirm activation without structure grade — default to standard execution."
        )
    elif final_structure_grade == 'A':
        violent_line = (
            f"🔥 **Violent Mode:** Eligible ({final_setup_key} setup). "
            "If immediate expansion with volume — Violent Mode applies."
        )
    else:
        violent_line = (
            f"🔥 **Violent Mode:** Eligible ({final_setup_key} setup) but structure grade "
            f"is {final_structure_grade} — standard execution recommended."
        )

    # Momentum section (Lite Vision doesn't do deep momentum)
    momentum_section = (
        "📊 **Momentum Health**\n"
        "Use `/deep` for RSI and momentum analysis, or confirm visually."
    )

    # Pattern memory
    pattern_memory = (
        f"Pattern memory for {final_setup_key} setups available via `/explain {final_setup_key}`."
    )

    # Build full analysis
    analysis = (
        f"🧙‍♂️ **JAYCE ANALYSIS**\n\n"
        f"**Pair:** {display_pair}\n"
        f"**Timeframe:** {display_timeframe}\n"
        f"**Market State:** {final_market_state}\n\n"
        f"📋 **Plan Reflection**\n"
        f"{plan_summary}\n"
        f"_Locked from your input + vision confirmation._\n\n"
        f"🔍 **Setup Identified:** {setup_name}\n"
        f"_{vision_status}_\n\n"
        f"🧱 **Structure Grade: {final_structure_grade}**\n"
        f"{final_structure_notes}\n"
        f"{'_' + grade_context.get(final_structure_grade, '') + '_' if final_structure_grade in grade_context else ''}\n\n"
        f"{momentum_section}\n\n"
        f"⚡ **If–Then Scenarios**\n"
        f"**IF** price accepts and holds above the flip zone → "
        f"structure supports continuation. {exec_default} on first reaction.\n"
        f"**IF** price stalls, wicks, or chops at the level → "
        f"secure faster than default. Do not wait for confirmation that isn't coming.\n"
        f"**IF** structure breaks below the flip zone → "
        f"setup is invalidated. Exit without emotion. No second-guessing.\n\n"
        f"{violent_line}\n\n"
        f"⏱ **Expected Resolution**\n"
        f"{final_setup_key} setups historically resolve within a median of "
        f"{resolution['median']}, with a normal range of {resolution['range']}. "
        f"This is informational context, not a timer on your trade.\n\n"
        f"🧠 **Pattern Memory**\n"
        f"{pattern_memory}\n\n"
        f"🪄 **Final Word**\n"
        f"You are not trading the outcome. You are executing a process. "
        f"If the setup is valid, trust the structure. If it isn't, walk away clean. "
        f"— Wiz Theory discipline, Mark Douglas mindset."
    )

    await thinking_msg.delete()
    await update.message.reply_text(analysis, parse_mode='Markdown')


async def valid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /valid command - quick validity check"""
    chat_id = update.effective_chat.id
    image_file_id = None

    if update.message.photo:
        image_file_id = update.message.photo[-1].file_id
        user_images[chat_id] = image_file_id
    elif update.message.reply_to_message and update.message.reply_to_message.photo:
        image_file_id = update.message.reply_to_message.photo[-1].file_id
    elif chat_id in user_images and user_images[chat_id]:
        image_file_id = user_images[chat_id]

    if not image_file_id:
        await update.message.reply_text(
            "⚡ **QUICK VALIDITY CHECK**\n\n"
            "Upload a chart or reply to one with `/valid` for a fast YES/NO assessment.",
            parse_mode='Markdown'
        )
        return

    thinking_msg = await update.message.reply_text("🔮 Reading chart…")
    await asyncio.sleep(2)
    
    # Quick vision check if available
    if vision_state['lite_enabled'] and ANTHROPIC_API_KEY:
        try:
            image_bytes = await download_telegram_image(context, image_file_id)
            vision_result = await call_lite_vision(image_bytes, "")
            
            await thinking_msg.delete()
            
            if 'error' not in vision_result:
                structure = vision_result.get('structure_status', 'Unclear')
                fib = vision_result.get('fib_level', 'Unable to confirm')
                grade = vision_result.get('structure_grade', 'Unconfirmed')
                confidence = vision_result.get('confidence', 'N/A')
                
                verdict = "✅ VALID" if structure == "Holds" else "⚠️ CAUTION" if structure == "Unclear" else "❌ INVALID"
                
                await update.message.reply_text(
                    f"⚡ **QUICK VALIDITY CHECK**\n\n"
                    f"**Setup:** {fib} + Flip Zone\n"
                    f"**Structure:** {structure}\n"
                    f"**Grade:** {grade}\n"
                    f"**Confidence:** {confidence}\n\n"
                    f"**Verdict:** {verdict}\n\n"
                    f"Use `/jayce` for full analysis with plan reflection.",
                    parse_mode='Markdown'
                )
                return
        except Exception as e:
            logger.error(f"Valid command vision failed: {e}")
    
    await thinking_msg.delete()
    await update.message.reply_text(
        "⚡ **QUICK VALIDITY CHECK**\n\n"
        "⚠️ Visual confirmation unavailable.\n\n"
        "Use `/jayce [your plan]` for analysis with your stated setup.",
        parse_mode='Markdown'
    )


async def violent_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /violent command - Violent Mode assessment"""
    chat_id = update.effective_chat.id
    image_file_id = None

    if update.message.photo:
        image_file_id = update.message.photo[-1].file_id
        user_images[chat_id] = image_file_id
    elif update.message.reply_to_message and update.message.reply_to_message.photo:
        image_file_id = update.message.reply_to_message.photo[-1].file_id
    elif chat_id in user_images and user_images[chat_id]:
        image_file_id = user_images[chat_id]

    if not image_file_id:
        await update.message.reply_text(
            "🔥 **VIOLENT MODE CHECK**\n\n"
            "Upload a .786 or Under-Fib chart with `/violent` to check if Violent Mode applies.\n\n"
            "⚠️ Violent Mode only applies to .786 + Flip Zone and Under-Fib setups.",
            parse_mode='Markdown'
        )
        return

    thinking_msg = await update.message.reply_text("🔮 Reading chart…")
    await asyncio.sleep(3)
    
    if vision_state['lite_enabled'] and ANTHROPIC_API_KEY:
        try:
            image_bytes = await download_telegram_image(context, image_file_id)
            vision_result = await call_lite_vision(image_bytes, "checking for violent mode eligibility")
            
            await thinking_msg.delete()
            
            if 'error' not in vision_result:
                fib = vision_result.get('fib_level', 'Unable to confirm')
                grade = vision_result.get('structure_grade', 'Unconfirmed')
                structure = vision_result.get('structure_status', 'Unclear')
                
                # Check violent eligibility
                is_eligible = fib in ['.786', 'under-fib']
                
                if not is_eligible:
                    violent_verdict = f"❌ Not eligible — {fib} excluded from Violent Mode."
                elif grade == 'A' and structure == 'Holds':
                    violent_verdict = "✅ VIOLENT MODE ACTIVE — Grade A structure with clean hold. Execute with conviction."
                elif grade in ['A', 'B']:
                    violent_verdict = f"⚠️ Eligible but Grade {grade} — standard execution recommended over Violent Mode."
                else:
                    violent_verdict = "⚠️ Eligible but structure unconfirmed — wait for clarity."
                
                await update.message.reply_text(
                    f"🔥 **VIOLENT MODE CHECK**\n\n"
                    f"**Setup:** {fib} + Flip Zone\n"
                    f"**Structure Grade:** {grade}\n"
                    f"**Structure Status:** {structure}\n\n"
                    f"**Verdict:** {violent_verdict}\n\n"
                    f"Use `/jayce` for full analysis with if-then scenarios.",
                    parse_mode='Markdown'
                )
                return
        except Exception as e:
            logger.error(f"Violent command vision failed: {e}")
    
    await thinking_msg.delete()
    await update.message.reply_text(
        "🔥 **VIOLENT MODE CHECK**\n\n"
        "⚠️ Visual confirmation unavailable.\n\n"
        "Violent Mode only applies to .786 and Under-Fib setups.\n"
        "Use `/jayce [.786 or under-fib]` for analysis.",
        parse_mode='Markdown'
    )


async def rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /rules [setup] command"""
    if context.args:
        setup = context.args[0].lower()
        rules_text = get_setup_rules(setup)
        await update.message.reply_text(rules_text, parse_mode='Markdown')
    else:
        await update.message.reply_text(
            "📋 **SETUP RULES**\n\n"
            "Usage: `/rules [setup]`\n\n"
            "Example: `/rules .786`\n\n"
            "Available setups: .382, .50, .618, .786, under-fib",
            parse_mode='Markdown'
        )


async def explain_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /explain [setup] command"""
    if context.args:
        setup = context.args[0].lower()
        explanation = get_setup_explanation(setup)
        await update.message.reply_text(explanation, parse_mode='Markdown')
    else:
        await update.message.reply_text(
            "📚 **SETUP EXPLANATION**\n\n"
            "Usage: `/explain [setup]`\n\n"
            "Example: `/explain under-fib`\n\n"
            "Available setups: .382, .50, .618, .786, under-fib",
            parse_mode='Markdown'
        )


async def setups_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /setups command"""
    await update.message.reply_text(
        "📊 **WIZ THEORY SETUPS**\n\n"
        "🟢 `.382` — Momentum gift (secure 20-40%)\n"
        "🟡 `.50` — Patience setup (secure 30-60%)\n"
        "🔴 `.618` — High-probability reaction (secure 40-60%)\n"
        "🟣 `.786` — Deep retracement, ATH context (secure 50-75%)\n"
        "🔵 `Under-Fib` — Musical setup (secure 40-60%)\n\n"
        "Use `/rules [setup]` for entry criteria",
        parse_mode='Markdown'
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    # Check if owner for showing owner commands
    is_owner_user = is_owner(update.effective_user.id)
    
    owner_commands = ""
    if is_owner_user:
        owner_commands = (
            "\n**Owner Commands:**\n"
            "`/vision on|off` — Toggle Lite Vision\n"
            "`/deep on|off` — Toggle Deep Vision\n"
        )
    
    await update.message.reply_text(
        "🧙‍♂️ **JAYCE BOT — Wiz Theory Analysis**\n\n"
        "**Commands:**\n"
        "`/jayce [plan]` — Full chart evaluation\n"
        "`/deep [plan]` — Deep Vision analysis\n"
        "`/valid` — Quick validity check\n"
        "`/violent` — Violent Mode assessment\n"
        "`/rules [setup]` — Entry rules for a setup\n"
        "`/explain [setup]` — Setup guide\n"
        "`/setups` — List all setups\n"
        "`/help` — This message\n"
        f"{owner_commands}\n"
        "**Supported setups:**\n"
        ".382, .50, .618, .786, Under-Fib Flip Zone\n\n"
        "Upload chart + use command, or just say \"yo jayce\"",
        parse_mode='Markdown'
    )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Store uploaded photos for later analysis.
    
    TRIGGER RULES (locked):
    - Jayce only analyzes when EXPLICITLY invoked
    - If chart posted without invocation → Jayce remains SILENT
    """
    chat_id = update.effective_chat.id
    image_file_id = update.message.photo[-1].file_id
    user_images[chat_id] = image_file_id

    caption = update.message.caption if update.message.caption else ""
    caption_lower = caption.lower()

    explicit_triggers = [
        '/jayce', '/analyze', '/valid', '/violent', '/deep',
        'jayce', 'yo jayce', 'hey jayce', '@jayce',
        'jayce analyze', 'jayce check', 'jayce look'
    ]

    is_invoked = any(trigger in caption_lower for trigger in explicit_triggers)

    if is_invoked:
        # Check for deep request
        if '/deep' in caption_lower or 'jayce deep' in caption_lower:
            if vision_state['deep_enabled']:
                await run_deep_analysis(update, context, image_file_id, caption)
            else:
                await update.message.reply_text(
                    "🔮 **Deep Vision** is currently disabled.",
                    parse_mode='Markdown'
                )
        else:
            await analyze_chart(update, context, image_file_id, caption)
    else:
        # Chart posted without invoking Jayce — remain SILENT
        pass


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle natural language triggers."""
    text = update.message.text.lower()
    full_text = update.message.text
    chat_id = update.effective_chat.id

    intro_triggers = [
        'introduce yourself', 'introduce urself',
        'who are you', 'who is jayce', 'what can you do'
    ]

    if any(trigger in text for trigger in intro_triggers):
        await intro_command(update, context)
        return

    jayce_explicit_triggers = [
        'jayce', 'hey jayce', 'yo jayce', '@jayce',
        'jayce analyze', 'jayce check', 'jayce look',
        'jayce what you think', 'jayce thoughts'
    ]

    jayce_invoked = any(trigger in text for trigger in jayce_explicit_triggers)

    if not jayce_invoked:
        return

    # Check for deep request
    if 'jayce deep' in text or 'deep' in text.split():
        if chat_id in user_images and user_images[chat_id]:
            if vision_state['deep_enabled']:
                await run_deep_analysis(update, context, user_images[chat_id], full_text)
            else:
                await update.message.reply_text(
                    "🔮 **Deep Vision** is currently disabled.",
                    parse_mode='Markdown'
                )
        else:
            await update.message.reply_text(
                "🔮 Deep Vision requires a chart image. Upload one first.",
                parse_mode='Markdown'
            )
        return

    if chat_id in user_images and user_images[chat_id]:
        await analyze_chart(update, context, user_images[chat_id], full_text)
    else:
        await update.message.reply_text(
            "🧙‍♂️ Hey! I'm here.\n\n"
            "Upload a chart and use:\n"
            "`/jayce [plan]` — Full analysis\n"
            "`/deep [plan]` — Deep Vision\n"
            "`/valid` — Quick check\n"
            "`/violent` — Violent Mode\n\n"
            "Or use `/help` for all commands",
            parse_mode='Markdown'
        )


# Helper functions
def get_setup_rules(setup: str) -> str:
    """Return entry rules for a specific setup"""
    rules_map = {
        '.382': (
            "🟢 **.382 + FLIP ZONE — ENTRY RULES**\n\n"
            "1. Clear impulse leg established\n"
            "2. Pullback into .382 retracement\n"
            "3. Former resistance reclaimed as support (flip zone)\n"
            "4. Structure clean BEFORE entry\n"
            "5. Volume supports reaction\n\n"
            "**Execution:** Secure 20-40% on first reaction (DEFAULT)"
        ),
        '.50': (
            "🟡 **.50 + FLIP ZONE — ENTRY RULES**\n\n"
            "1. Clean structure, high volume\n"
            "2. Clear impulse leg established\n"
            "3. Pullback into .50 retracement\n"
            "4. Former resistance reclaimed as support\n"
            "5. Structure clean BEFORE entry\n\n"
            "**Execution:** Secure 30-60% on first strong reaction"
        ),
        '.618': (
            "🔴 **.618 + FLIP ZONE — ENTRY RULES**\n\n"
            "1. Clean structure, high volume\n"
            "2. Strong impulse (≥60% breakout)\n"
            "3. 50-60% pullback into .618 flip zone\n"
            "4. Limit orders 5-7% above .618\n"
            "5. Skip if volume doesn't build or slices through\n\n"
            "**Execution:** Secure 40-60% on first strong reaction"
        ),
        '.786': (
            "🟣 **.786 + FLIP ZONE — ENTRY RULES**\n\n"
            "1. Clean structure, high volume\n"
            "2. Strong impulse ≥100% (preferably ATH)\n"
            "3. 70-80% pullback into .786 flip zone\n"
            "4. Limit orders 6-9% above .786\n"
            "5. Whale conviction = confirmation only\n\n"
            "**Execution:** Secure 50-75% on first bounce"
        ),
        'under-fib': (
            "🔵 **UNDER-FIB FLIP ZONE — ENTRY RULES**\n\n"
            "1. Clean structure BEFORE entry\n"
            "2. Strong impulse ≥60%\n"
            "3. Price dips BELOW fib then reclaims (off-beat → rhythm)\n"
            "4. Flip zone UNTOUCHED prior\n"
            "5. ≥40% pullback into under-fib zone\n"
            "6. Limit entry 5-9% above nearest wick\n\n"
            "**Execution:** Secure 40-60% on first reaction"
        )
    }
    return rules_map.get(setup, "❌ Setup not recognized. Use: .382, .50, .618, .786, or under-fib")


def get_setup_explanation(setup: str) -> str:
    """Return full explanation for a specific setup"""
    explain_map = {
        '.382': (
            "🟢 **.382 + FLIP ZONE**\n\n"
            "**Purpose:** Momentum continuation REACTION setup\n"
            "**Identity:** Speed + discipline > conviction\n"
            "**Hold time:** Avg ~72 min | Median ~34 min\n\n"
            "The .382 is a gift. Take what the market offers.\n"
            "Secure 20-40% is DEFAULT, not optional."
        ),
        '.50': (
            "🟡 **.50 + FLIP ZONE**\n\n"
            "**Purpose:** Deeper pullback requiring patience\n"
            "**NOT** momentum gift like .382\n"
            "**Hold time:** Requires structure confirmation\n\n"
            "Secure 30-60% on first reaction.\n"
            "If chop/stall → exit remainder."
        ),
        '.618': (
            "🔴 **.618 + FLIP ZONE**\n\n"
            "**Purpose:** High-probability reaction level\n"
            "**Context:** Most popular fib among traders\n"
            "**Hold time:** Structure decides continuation\n\n"
            "Secure 40-60% on first reaction.\n"
            "Skip if volume fades or slices through."
        ),
        '.786': (
            "🟣 **.786 + FLIP ZONE**\n\n"
            "**Purpose:** Deep retracement where market intent shows\n"
            "**Context:** Strong impulse ≥100%, preferably ATH\n"
            "**Hold time:** Structure + momentum decides\n\n"
            "Secure 50-75% on first bounce.\n"
            "Violent Mode may apply if immediate expansion."
        ),
        'under-fib': (
            "🔵 **UNDER-FIB FLIP ZONE**\n\n"
            "**Purpose:** Off-beat → rhythm musical setup\n"
            "**Pattern:** Price dips BELOW fib, then reclaims\n"
            "**Hold time:** Avg 4 hours (1-6hr range)\n\n"
            "Key: \"Off-beat\" (dip) → \"Rhythm\" (reclaim) → Expansion\n"
            "Violent Mode may apply if immediate expansion."
        )
    }
    return explain_map.get(setup, "❌ Setup not recognized. Use: .382, .50, .618, .786, or under-fib")


def main():
    """Start the bot"""
    application = Application.builder().token(BOT_TOKEN).build()

    # Owner control commands
    application.add_handler(CommandHandler("vision", vision_command))
    application.add_handler(CommandHandler("deep", deep_command))

    # Intro commands
    application.add_handler(CommandHandler("intro", intro_command))
    application.add_handler(CommandHandler("whoisjayce", intro_command))
    application.add_handler(CommandHandler("aboutjayce", intro_command))
    application.add_handler(CommandHandler("start", intro_command))

    # Primary commands
    application.add_handler(CommandHandler("jayce", jayce_command))
    application.add_handler(CommandHandler("valid", valid_command))
    application.add_handler(CommandHandler("violent", violent_command))
    application.add_handler(CommandHandler("rules", rules_command))
    application.add_handler(CommandHandler("explain", explain_command))
    application.add_handler(CommandHandler("setups", setups_command))
    application.add_handler(CommandHandler("help", help_command))

    # Photo handler
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    # Text handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    logger.info("Starting Jayce Bot with Vision...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
