import os
import logging
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
    await update.message.reply_text(
        "🧙‍♂️ **JAYCE EVALUATION**\n\n"
        "Please upload a chart image with `/jayce` or reply to a chart message with `/jayce`.\n\n"
        "I'll analyze structure, validate the setup, and provide execution guidance.",
        parse_mode='Markdown'
    )


async def valid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /valid command - quick validity check"""
    await update.message.reply_text(
        "⚡ **QUICK VALIDITY CHECK**\n\n"
        "Upload a chart or reply to one with `/valid` for a fast YES/NO assessment.",
        parse_mode='Markdown'
    )


async def violent_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /violent command - Violent Mode assessment"""
    await update.message.reply_text(
        "🔥 **VIOLENT MODE CHECK**\n\n"
        "Upload a .786 or Under-Fib chart with `/violent` to check if Violent Mode applies.\n\n"
        "⚠️ Violent Mode only applies to .786 + Flip Zone and Under-Fib setups.",
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


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle natural language triggers like 'hey jayce' and intro requests"""
    text = update.message.text.lower()
    
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
    
    # Check for Jayce mentions (original behavior)
    jayce_triggers = ['jayce', 'hey jayce', 'yo jayce']
    
    if any(trigger in text for trigger in jayce_triggers):
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
    
    # Register text message handler for natural language triggers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    
    # Start the bot with polling (Railway-compatible)
    logger.info("Starting Jayce Bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
