import os
import re
import asyncio
import logging
from collections import defaultdict
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Get bot token from environment
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set")

# Store last uploaded image per chat (chat_id -> file_id)
user_images = defaultdict(str)

# ──────────────────────────────────────────────
# Wiz Theory resolution time statistics per setup
# Used in Section 7 of analysis template
# ──────────────────────────────────────────────
RESOLUTION_TIMES = {
    '.382': {
        'median': '~34 min',
        'range': '15 min to 1.5 hours',
    },
    '.50': {
        'median': '~1 hour',
        'range': '30 min to 3 hours',
    },
    '.618': {
        'median': '~1.5 hours',
        'range': '45 min to 4 hours',
    },
    '.786': {
        'median': '~45 min',
        'range': '30 min to 2 hours',
    },
    'under-fib': {
        'median': '~4 hours',
        'range': '1 to 6 hours',
    },
}

# ──────────────────────────────────────────────
# Execution defaults per setup (used in If-Then)
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


# Command Handlers
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
    """Handle /jayce command - full chart evaluation"""
    chat_id = update.effective_chat.id
    image_file_id = None

    # Check 1: Photo in caption (user uploads photo with /jayce in caption)
    if update.message.photo:
        image_file_id = update.message.photo[-1].file_id
        user_images[chat_id] = image_file_id

    # Check 2: Reply to a photo
    elif update.message.reply_to_message and update.message.reply_to_message.photo:
        image_file_id = update.message.reply_to_message.photo[-1].file_id

    # Check 3: Use last uploaded image from this chat
    elif chat_id in user_images and user_images[chat_id]:
        image_file_id = user_images[chat_id]

    # No image found
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

    # Image found - analyze it
    await analyze_chart(update, context, image_file_id, user_plan)


async def analyze_chart(update: Update, context: ContextTypes.DEFAULT_TYPE, image_file_id: str, user_plan: str = ""):
    """
    Analyze chart image and provide Wiz Theory evaluation.

    Full approved template (v2) with 9 sections:
    1. Chart Context Header
    2. Plan Reflection (3-state logic)
    3. Setup Identification
    4. Structure Quality Grade
    5. Momentum Health Check
    6. If-Then Scenario Matrix
    7. Expected Resolution Time
    8. Light Pattern Memory
    9. Strong Closing Summary

    CURRENT STATE: Template/placeholder mode.
    Vision API integration will replace placeholder values later.
    The TEMPLATE FORMAT is final and frozen.
    """

    # Send "thinking" message
    thinking_msg = await update.message.reply_text("🔮 Reading chart…")

    # UX delay — full analysis gets 4-5 seconds
    await asyncio.sleep(4.5)

    # ══════════════════════════════════════════════
    # INPUT LOCK LAYER — Correctness + Discipline
    # ══════════════════════════════════════════════
    # Rule 1: If user states a value, LOCK it. Never override.
    # Rule 2: If a value is missing, mark "Unconfirmed" or ask.
    # Rule 3: No vision yet — all values come from user text only.
    # Rule 4: No guessing. Ever.

    user_text = user_plan.strip()

    # ── Parse setup level from user input ──
    SETUP_PATTERNS = {
        '.382': [r'\.?382', r'38\.2'],
        '.50': [r'\.?50\b', r'\.500'],
        '.618': [r'\.?618', r'61\.8'],
        '.786': [r'\.?786', r'78\.6'],
        'under-fib': [r'under[\s\-]?fib', r'underfib'],
    }

    setup_key = None
    for key, patterns in SETUP_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, user_text, re.IGNORECASE):
                setup_key = key
                break
        if setup_key:
            break

    # ── Parse timeframe from user input ──
    TIMEFRAME_PATTERNS = [
        (r'\b1\s*m\b', '1m'), (r'\b3\s*m\b', '3m'), (r'\b5\s*m\b', '5m'),
        (r'\b15\s*m\b', '15m'), (r'\b30\s*m\b', '30m'),
        (r'\b1\s*h\b', '1H'), (r'\b2\s*h\b', '2H'), (r'\b4\s*h\b', '4H'),
        (r'\b1\s*d\b', '1D'), (r'\bdaily\b', '1D'),
        (r'\b1\s*w\b', '1W'), (r'\bweekly\b', '1W'),
    ]

    timeframe = None
    for pattern, tf_value in TIMEFRAME_PATTERNS:
        if re.search(pattern, user_text, re.IGNORECASE):
            timeframe = tf_value
            break

    # ── Parse pair from user input ──
    pair_match = re.search(
        r'\b([A-Z]{2,10})\s*/\s*([A-Z]{2,10})\b',
        user_plan,  # use original case
        re.IGNORECASE
    )
    pair = pair_match.group(0).upper() if pair_match else None

    # ── Parse target from user input ──
    target_match = re.search(
        r'(?:target|tp|take[\s\-]?profit)[\s:→\-]*([\w\s%.]+)',
        user_text, re.IGNORECASE
    )
    target = target_match.group(1).strip() if target_match else None

    # ── Parse invalidation from user input ──
    invalidation_match = re.search(
        r'(?:invalidat|invalid|stop[\s\-]?loss|sl)[\s:→\-]*([\w\s%.]+)',
        user_text, re.IGNORECASE
    )
    invalidation = invalidation_match.group(1).strip() if invalidation_match else None

    # ── GATE CHECK: Do we have enough to proceed? ──
    # Setup level is REQUIRED — no analysis without it
    if not user_text:
        # STATE 2: No plan at all
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

    if not setup_key:
        # Setup level could not be extracted — ask, don't guess
        await thinking_msg.delete()
        await update.message.reply_text(
            "🧙‍♂️ **JAYCE ANALYSIS**\n\n"
            "📋 **Plan Reflection**\n"
            f"You said: _{user_text}_\n\n"
            "I couldn't identify a setup level from your message.\n\n"
            "Please confirm which setup you're playing:\n"
            "`.382` · `.50` · `.618` · `.786` · `under-fib`\n\n"
            "Example: `/jayce .618 flip zone 1m → target previous high`\n\n"
            "I don't guess levels. Clarity before conviction.",
            parse_mode='Markdown'
        )
        return

    # ── Build setup display name from locked input ──
    setup_name = f"{setup_key} + Flip Zone"

    # ── Build Plan Reflection summary (clean extraction, not full echo) ──
    plan_summary_parts = [f"**Setup:** {setup_name}"]
    if timeframe:
        plan_summary_parts.append(f"**Timeframe:** {timeframe}")
    if target:
        plan_summary_parts.append(f"**Target:** {target}")
    if invalidation:
        plan_summary_parts.append(f"**Invalidation:** {invalidation}")
    plan_summary = "\n".join(plan_summary_parts)

    # ── Values that require vision (locked as Unconfirmed until vision is added) ──
    display_pair = pair if pair else "Unconfirmed"
    display_timeframe = timeframe if timeframe else "Unconfirmed"
    market_state = "Unconfirmed (vision not enabled)"
    structure_grade = "Unconfirmed"
    structure_notes = (
        "Structure grade requires visual confirmation. "
        "Vision is not yet enabled — grade will be assessed once chart reading is live."
    )
    momentum_readable = False
    momentum_text = ""
    pattern_memory = (
        f"Pattern memory for {setup_key} setups will be available once vision is enabled. "
        f"For now, refer to `/explain {setup_key}` for historical context."
    )

    # ── Values derived from LOCKED user input (safe to use) ──
    violent_mode = VIOLENT_ELIGIBLE.get(setup_key, False)

    # ══════════════════════════════════════════════
    # CONFIDENCE GATE — Downgrade certainty when values are unconfirmed
    # ══════════════════════════════════════════════
    unconfirmed_fields = []
    if not timeframe:
        unconfirmed_fields.append("Timeframe")
    if not pair:
        unconfirmed_fields.append("Pair")
    # Market state and structure grade are always unconfirmed without vision
    unconfirmed_fields.append("Market State")
    unconfirmed_fields.append("Structure Grade")
    unconfirmed_fields.append("Momentum")

    confidence_note = (
        f"⚠️ **Confidence Note:** {', '.join(unconfirmed_fields)} "
        f"{'are' if len(unconfirmed_fields) > 1 else 'is'} unconfirmed. "
        f"Vision is not yet enabled — analysis is based on your stated plan "
        f"and Wiz Theory rules only. Treat as framework guidance, not visual confirmation."
    )

    # STATE 1: Plan is clear — proceed with full analysis

    # ── Get setup-specific data ──
    exec_default = EXECUTION_DEFAULTS.get(setup_key, 'Secure on first reaction')
    resolution = RESOLUTION_TIMES.get(setup_key, {'median': 'N/A', 'range': 'N/A'})

    # ── Grade context line ──
    grade_context = {
        'A': 'A = structure supports runner with conviction',
        'B': 'B = standard execution, structure supports reaction',
        'C': 'C = defensive only, secure early and fast',
    }

    # ── Violent Mode line (vision-safe) ──
    if not violent_mode:
        violent_line = (
            f"🔥 **Violent Mode:** Not applicable ({setup_key} excluded from Violent Mode)."
        )
    elif structure_grade == "Unconfirmed":
        violent_line = (
            f"🔥 **Violent Mode:** Eligible ({setup_key} setup). "
            "Cannot confirm activation without structure grade. "
            "Vision required to assess — default to standard execution."
        )
    elif violent_mode and structure_grade == 'A':
        violent_line = (
            f"🔥 **Violent Mode:** Eligible ({setup_key} setup). "
            "If immediate expansion with volume — Violent Mode applies."
        )
    else:
        violent_line = (
            f"🔥 **Violent Mode:** Eligible ({setup_key} setup) but structure grade "
            f"is {structure_grade} — standard execution recommended over Violent Mode."
        )

    # ── Momentum section ──
    if momentum_readable:
        momentum_section = f"📊 **Momentum Health**\n{momentum_text}"
    else:
        momentum_section = (
            "📊 **Momentum Health**\n"
            "I can't confidently read momentum from this chart. "
            "Can you confirm RSI or add an indicator overlay?"
        )

    # ── Build full analysis ──
    analysis = (
        f"🧙‍♂️ **JAYCE ANALYSIS**\n\n"
        # ── Section 1: Chart Context Header (locked from user input) ──
        f"**Pair:** {display_pair}\n"
        f"**Timeframe:** {display_timeframe}\n"
        f"**Market State:** {market_state}\n\n"
        # ── Section 2: Plan Reflection (clean extraction) ──
        f"📋 **Plan Reflection**\n"
        f"{plan_summary}\n"
        f"_Locked from your input. Reviewing below._\n\n"
        # ── Section 3: Setup Identification (locked from user input, vision-safe) ──
        f"🔍 **Setup Identified:** {setup_name}\n"
        f"_I can't visually confirm fib depth yet. Using your stated setup for analysis._\n\n"
        # ── Confidence Gate ──
        f"{confidence_note}\n\n"
        # ── Section 4: Structure Quality Grade ──
        f"🧱 **Structure Grade: {structure_grade}**\n"
        f"{structure_notes}\n\n"
        # ── Section 5: Momentum Health ──
        f"{momentum_section}\n\n"
        # ── Section 6: If-Then Scenario Matrix ──
        f"⚡ **If–Then Scenarios**\n"
        f"**IF** price accepts and holds above the flip zone → "
        f"structure supports continuation. {exec_default} on first reaction.\n"
        f"**IF** price stalls, wicks, or chops at the level → "
        f"secure faster than default. Do not wait for confirmation that isn't coming.\n"
        f"**IF** structure breaks below the flip zone → "
        f"setup is invalidated. Exit without emotion. No second-guessing.\n\n"
        # ── Violent Mode ──
        f"{violent_line}\n\n"
        # ── Section 7: Expected Resolution Time ──
        f"⏱ **Expected Resolution**\n"
        f"{setup_key} setups historically resolve within a median of "
        f"{resolution['median']}, with a normal range of {resolution['range']}. "
        f"This is informational context, not a timer on your trade.\n\n"
        # ── Section 8: Light Pattern Memory ──
        f"🧠 **Pattern Memory**\n"
        f"{pattern_memory}\n\n"
        # ── Section 9: Strong Closing Summary ──
        f"🪄 **Final Word**\n"
        f"You are not trading the outcome. You are executing a process. "
        f"If the setup is valid, trust the structure. If it isn't, walk away clean. "
        f"— Wiz Theory discipline, Mark Douglas mindset."
    )

    # Delete "analyzing" message and send analysis
    await thinking_msg.delete()
    await update.message.reply_text(analysis, parse_mode='Markdown')


async def valid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /valid command - quick validity check"""
    # Check if there's an image to validate
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

    # Thinking line + 2 second delay
    thinking_msg = await update.message.reply_text("🔮 Reading chart…")
    await asyncio.sleep(2)
    await thinking_msg.delete()

    # TODO: Vision API will populate this dynamically
    await update.message.reply_text(
        "⚡ **QUICK VALIDITY CHECK**\n\n"
        "**Setup:** .786 + Flip Zone\n"
        "**Structure:** Clean\n"
        "**Verdict:** ✅ VALID\n\n"
        "Use `/jayce` for full analysis with plan reflection.",
        parse_mode='Markdown'
    )


async def violent_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /violent command - Violent Mode assessment"""
    # Check if there's an image to check
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

    # Thinking line + 3 second delay
    thinking_msg = await update.message.reply_text("🔮 Reading chart…")
    await asyncio.sleep(3)
    await thinking_msg.delete()

    # TODO: Vision API will populate this dynamically
    await update.message.reply_text(
        "🔥 **VIOLENT MODE CHECK**\n\n"
        "**Setup:** .786 + Flip Zone\n"
        "**Structure Grade:** B\n"
        "**Violent Mode:** Eligible but structure grade is B — standard execution recommended over Violent Mode.\n\n"
        "Use `/jayce` for full analysis with if-then scenarios.",
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
    await update.message.reply_text(
        "🧙‍♂️ **JAYCE BOT — Wiz Theory Analysis**\n\n"
        "**Commands:**\n"
        "`/jayce` — Full chart evaluation\n"
        "`/valid` — Quick validity check\n"
        "`/violent` — Violent Mode assessment\n"
        "`/rules [setup]` — Entry rules for a setup\n"
        "`/explain [setup]` — Setup guide\n"
        "`/setups` — List all setups\n"
        "`/help` — This message\n\n"
        "**Supported setups:**\n"
        ".382, .50, .618, .786, Under-Fib Flip Zone\n\n"
        "Upload chart + use command, or just say \"hey jayce\"",
        parse_mode='Markdown'
    )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store uploaded photos and auto-analyze if triggered"""
    chat_id = update.effective_chat.id
    image_file_id = update.message.photo[-1].file_id
    user_images[chat_id] = image_file_id

    # Check if caption contains /jayce or analysis trigger words
    caption = update.message.caption if update.message.caption else ""
    caption_lower = caption.lower()

    # Auto-analyze triggers in caption
    analyze_triggers = ['/jayce', 'analyze', 'what you think', 'thoughts', 'valid']

    if any(trigger in caption_lower for trigger in analyze_triggers):
        await analyze_chart(update, context, image_file_id, caption)
    else:
        # Just acknowledge the image was received
        await update.message.reply_text(
            "📸 Chart received. Send `/jayce` to analyze it.\n\n"
            "Tip: Include your plan for a better analysis.\n"
            "Example: `/jayce .786 flip zone → target previous high`",
            parse_mode='Markdown'
        )


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle natural language triggers like 'hey jayce' and intro requests"""
    text = update.message.text.lower()
    full_text = update.message.text  # preserve original case for plan extraction
    chat_id = update.effective_chat.id

    # Check for intro triggers
    intro_triggers = [
        'introduce yourself',
        'introduce urself',
        'who are you',
        'who is jayce',
        'what can you do'
    ]

    if any(trigger in text for trigger in intro_triggers):
        await intro_command(update, context)
        return

    # Check for analysis request with stored image
    analysis_triggers = [
        'what you think',
        'what do you think',
        'analyze',
        'analyze this',
        'can you analyze',
        'thoughts',
        'your thoughts'
    ]

    if any(trigger in text for trigger in analysis_triggers):
        # Check if there's a stored image
        if chat_id in user_images and user_images[chat_id]:
            await analyze_chart(update, context, user_images[chat_id], full_text)
            return
        else:
            await update.message.reply_text(
                "📸 I need a chart image first. Upload one and I'll analyze it.",
                parse_mode='Markdown'
            )
            return

    # Check for Jayce mentions (original behavior)
    jayce_triggers = ['jayce', 'hey jayce', 'yo jayce']

    if any(trigger in text for trigger in jayce_triggers):
        # If there's a stored image, analyze it
        if chat_id in user_images and user_images[chat_id]:
            await analyze_chart(update, context, user_images[chat_id], full_text)
        else:
            await update.message.reply_text(
                "🧙‍♂️ Hey! I'm here.\n\n"
                "Upload a chart and use:\n"
                "`/jayce` — Full analysis\n"
                "`/valid` — Quick check\n"
                "`/violent` — Violent Mode\n\n"
                "Or use `/help` for all commands",
                parse_mode='Markdown'
            )


# Helper functions for setup rules/explanations
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
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()

    # Register intro command handlers
    application.add_handler(CommandHandler("intro", intro_command))
    application.add_handler(CommandHandler("whoisjayce", intro_command))
    application.add_handler(CommandHandler("aboutjayce", intro_command))
    application.add_handler(CommandHandler("start", intro_command))

    # Register primary command handlers
    application.add_handler(CommandHandler("jayce", jayce_command))
    application.add_handler(CommandHandler("valid", valid_command))
    application.add_handler(CommandHandler("violent", violent_command))
    application.add_handler(CommandHandler("rules", rules_command))
    application.add_handler(CommandHandler("explain", explain_command))
    application.add_handler(CommandHandler("setups", setups_command))
    application.add_handler(CommandHandler("help", help_command))

    # Register photo handler (must come before text handler)
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    # Register text message handler for natural language triggers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    # Start the bot with polling (Railway-compatible)
    logger.info("Starting Jayce Bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
