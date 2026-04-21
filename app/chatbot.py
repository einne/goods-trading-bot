'''
This program requires the following modules:
- python-telegram-bot==22.5
- urllib3==2.6.2
'''
from ChatGPT_HKBU import ChatGPT
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
import configparser
import logging
import os
import re
import uuid
from pathlib import Path
from db import init_db, log_chat
from services.event_service import search_upcoming_events
from services.item_service import delist_item, list_user_items, publish_item, search_active_items
from services.intent_service import load_intents
from services.qa_service import answer_with_ai_and_db
from services.router_service import route_message

gpt = None
intent_rows = []
PUBLISH_TITLE, PUBLISH_CATEGORY, PUBLISH_PRICE, PUBLISH_CONDITION, PUBLISH_DESCRIPTION, PUBLISH_CONFIRM = range(6)
PUBLISH_DRAFT_KEY = "publish_draft"
DOTENV_PATH = Path(".env")


def _load_dotenv(path: Path = DOTENV_PATH) -> None:
    """Load local .env file for manual EC2 runs without systemd EnvironmentFile."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _get_setting(
    config: configparser.ConfigParser,
    *,
    env_key: str,
    section: str,
    option: str,
    required: bool = False,
    default: str | None = None,
) -> str | None:
    value = os.getenv(env_key)
    if value:
        return value.strip()
    if config.has_option(section, option):
        cfg = config.get(section, option).strip()
        if cfg:
            return cfg
    if default is not None:
        return default
    if required:
        raise RuntimeError(
            f"Missing required setting `{env_key}` or `{section}.{option}`. "
            "Please configure .env or config.ini before startup."
        )
    return None


def _main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("View Items", callback_data="menu_items"),
                InlineKeyboardButton("View Events", callback_data="menu_events"),
            ],
            [
                InlineKeyboardButton("My Items", callback_data="menu_myitems"),
                InlineKeyboardButton("Publish Item", callback_data="menu_publish"),
            ],
            [InlineKeyboardButton("Delist Item", callback_data="menu_delist")],
            [InlineKeyboardButton("Help", callback_data="menu_help")],
        ]
    )


def _back_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Back To Main Menu", callback_data="menu_home")]]
    )


def _start_page_text() -> str:
    return (
        "SmartSupport Campus 2nd-hand Bot\n\n"
        "Quick actions are available below. Tap a button to run.\n\n"
        "Available commands:\n"
        "/items [keyword]\n"
        "/myitems\n"
        "/publish (guided flow)\n"
        "/cancel (exit guided flow)\n"
        "/delist <item_id>\n"
        "/events [keyword]\n"
        "/help"
    )


def _extract_help_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Parse /help questions from both '/help xxx' and '/help+xxx' styles."""
    question = " ".join(context.args).strip()
    if question:
        return question

    raw_text = (update.message.text or "").strip() if update.message else ""
    if not raw_text:
        return ""

    matched = re.match(r"^/\w+(?:@\w+)?", raw_text)
    if matched:
        raw_text = raw_text[matched.end():]

    return raw_text.lstrip(" +:：-").strip()


def _display_name(update: Update) -> str | None:
    if update.effective_user is None:
        return None
    full_name = " ".join(
        part for part in [update.effective_user.first_name, update.effective_user.last_name] if part
    ).strip()
    return full_name or None


def _build_items_reply(items):
    if not items:
        return "No active items found. Use /publish to post your item."
    lines = ["Latest active items:"]
    for item in items:
        lines.append(
            f"#{item['id']} | {item['title']} | HKD {item['price']} | "
            f"{item['condition_level']} | {item['category']}"
        )
    return "\n".join(lines)


def _build_user_items_reply(items):
    if not items:
        return "You have not posted any items yet. Use /publish to create one."
    lines = ["Your posted items:"]
    for item in items:
        lines.append(
            f"#{item['id']} | {item['title']} | HKD {item['price']} | "
            f"{item['condition_level']} | {item['category']} | {item['status']}"
        )
    return "\n".join(lines)


def _build_events_reply(events):
    if not events:
        return "No upcoming events found."
    lines = ["Upcoming campus events:"]
    for event in events:
        starts_at = event.get("starts_at") or "TBD"
        lines.append(
            f"#{event['id']} | {event['title']} | {event['event_type']} | "
            f"{starts_at} | {event['location']}"
        )
    return "\n".join(lines)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(_start_page_text(), reply_markup=_main_menu_keyboard())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(_start_page_text(), reply_markup=_main_menu_keyboard())


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is None:
        return
    await query.answer()

    data = query.data or ""

    if data == "menu_home":
        await query.edit_message_text(_start_page_text(), reply_markup=_main_menu_keyboard())
        return

    if data == "menu_items":
        items = search_active_items(query=None, limit=20)
        await query.edit_message_text(_build_items_reply(items), reply_markup=_back_menu_keyboard())
        return

    if data == "menu_events":
        events = search_upcoming_events(query=None, limit=8)
        await query.edit_message_text(_build_events_reply(events), reply_markup=_back_menu_keyboard())
        return

    if data == "menu_myitems":
        telegram_user_id = str(update.effective_user.id) if update.effective_user else "unknown"
        items = list_user_items(telegram_user_id=telegram_user_id, limit=50)
        await query.edit_message_text(_build_user_items_reply(items), reply_markup=_back_menu_keyboard())
        return

    if data == "menu_publish":
        await query.edit_message_text(
            "Guided publishing is enabled.\n"
            "Send /publish to start step-by-step input.\n"
            "You can use /cancel anytime to exit.",
            reply_markup=_back_menu_keyboard(),
        )
        return

    if data == "menu_delist":
        await query.edit_message_text(
            "Delist format:\n/delist <item_id>\n\n"
            "Example:\n/delist 12",
            reply_markup=_back_menu_keyboard(),
        )
        return

    if data == "menu_help":
        await query.edit_message_text(
            "AI FAQ is ready.\n"
            "Please ask directly in chat, or use:\n"
            "/help <your question>\n\n"
            "Examples:\n"
            "/help can I pay with paypal?\n"
            "/help I want electronics items\n"
            "/help when is the next market event?",
            reply_markup=_back_menu_keyboard(),
        )
        return


async def post_init(app):
    # Polling mode should clear stale updates to avoid startup message flooding.
    try:
        await app.bot.delete_webhook(drop_pending_updates=True)
    except Exception as exc:
        logging.warning("INIT: delete_webhook skipped: %s", exc)
    await app.bot.set_my_commands(
        [
            BotCommand("start", "Open main menu"),
            BotCommand("items", "View active items"),
            BotCommand("myitems", "View my posted items"),
            BotCommand("publish", "Publish item (guided)"),
            BotCommand("cancel", "Cancel guided flow"),
            BotCommand("delist", "Delist item"),
            BotCommand("events", "View events"),
            BotCommand("help", "AI FAQ help"),
        ]
    )


async def items_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args).strip() or None
    items = search_active_items(query=query, limit=20)
    response = _build_items_reply(items)
    await update.message.reply_text(response)
    log_chat(
        f"/items {' '.join(context.args)}".strip(),
        response,
        request_id=str(uuid.uuid4()),
        telegram_user_id=str(update.effective_user.id) if update.effective_user else None,
        route_mode="items_command",
    )


async def myitems_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_user_id = str(update.effective_user.id) if update.effective_user else "unknown"
    items = list_user_items(telegram_user_id=telegram_user_id, limit=50)
    response = _build_user_items_reply(items)
    await update.message.reply_text(response)
    log_chat(
        "/myitems",
        response,
        request_id=str(uuid.uuid4()),
        telegram_user_id=telegram_user_id,
        route_mode="myitems_command",
    )


async def publish_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data[PUBLISH_DRAFT_KEY] = {}
    await update.message.reply_text(
        "Let's publish your item.\n"
        "Step 1/5: Please enter item title.\n"
        "You can send /cancel anytime."
    )
    return PUBLISH_TITLE


async def publish_title_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = (update.message.text or "").strip()
    if not title:
        await update.message.reply_text("Title cannot be empty. Please enter item title.")
        return PUBLISH_TITLE
    context.user_data[PUBLISH_DRAFT_KEY]["title"] = title
    await update.message.reply_text("Step 2/5: Enter category (e.g. Books, Electronics, Home).")
    return PUBLISH_CATEGORY


async def publish_category_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    category = (update.message.text or "").strip()
    if not category:
        await update.message.reply_text("Category cannot be empty. Please enter category.")
        return PUBLISH_CATEGORY
    context.user_data[PUBLISH_DRAFT_KEY]["category"] = category
    await update.message.reply_text("Step 3/5: Enter price in HKD (e.g. 1800 or 199.5).")
    return PUBLISH_PRICE


async def publish_price_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    price_str = (update.message.text or "").strip()
    try:
        price = float(price_str)
        if price < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Price must be a non-negative number. Please try again.")
        return PUBLISH_PRICE
    context.user_data[PUBLISH_DRAFT_KEY]["price"] = price
    await update.message.reply_text("Step 4/5: Enter condition (e.g. Like New, Good, Acceptable).")
    return PUBLISH_CONDITION


async def publish_condition_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    condition = (update.message.text or "").strip()
    if not condition:
        await update.message.reply_text("Condition cannot be empty. Please enter condition.")
        return PUBLISH_CONDITION
    context.user_data[PUBLISH_DRAFT_KEY]["condition_level"] = condition
    await update.message.reply_text("Step 5/5: Enter item description.")
    return PUBLISH_DESCRIPTION


async def publish_description_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    description = (update.message.text or "").strip()
    if not description:
        await update.message.reply_text("Description cannot be empty. Please enter description.")
        return PUBLISH_DESCRIPTION
    context.user_data[PUBLISH_DRAFT_KEY]["description"] = description

    draft = context.user_data[PUBLISH_DRAFT_KEY]
    await update.message.reply_text(
        "Please confirm publication:\n"
        f"Title: {draft['title']}\n"
        f"Category: {draft['category']}\n"
        f"Price: HKD {draft['price']}\n"
        f"Condition: {draft['condition_level']}\n"
        f"Description: {draft['description']}\n\n"
        "Reply yes to publish, or no to cancel."
    )
    return PUBLISH_CONFIRM


async def publish_confirm_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    decision = (update.message.text or "").strip().lower()
    if decision not in {"yes", "y", "no", "n"}:
        await update.message.reply_text("Please reply yes or no.")
        return PUBLISH_CONFIRM

    if decision in {"no", "n"}:
        context.user_data.pop(PUBLISH_DRAFT_KEY, None)
        await update.message.reply_text("Publishing canceled.")
        return ConversationHandler.END

    draft = context.user_data.get(PUBLISH_DRAFT_KEY, {})
    telegram_user_id = str(update.effective_user.id) if update.effective_user else "unknown"
    username = update.effective_user.username if update.effective_user else None
    created = publish_item(
        telegram_user_id=telegram_user_id,
        display_name=_display_name(update),
        username=username,
        title=draft["title"],
        category=draft["category"],
        price=draft["price"],
        condition_level=draft["condition_level"],
        description=draft["description"],
    )
    response = (
        "Item published successfully.\n"
        f"ID: {created['id']}\n"
        f"Title: {created['title']}\n"
        f"Price: HKD {created['price']}\n"
        f"Status: {created['status']}"
    )
    await update.message.reply_text(response)
    log_chat(
        "/publish (guided)",
        response,
        request_id=str(uuid.uuid4()),
        telegram_user_id=telegram_user_id,
        route_mode="publish_conversation",
    )
    context.user_data.pop(PUBLISH_DRAFT_KEY, None)
    return ConversationHandler.END


async def publish_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if PUBLISH_DRAFT_KEY in context.user_data:
        context.user_data.pop(PUBLISH_DRAFT_KEY, None)
        await update.message.reply_text("Publishing canceled.")
    else:
        await update.message.reply_text("No active publish flow.")
    return ConversationHandler.END


async def delist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /delist <item_id>")
        return
    try:
        item_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Item ID must be an integer.")
        return

    telegram_user_id = str(update.effective_user.id) if update.effective_user else "unknown"
    ok, message = delist_item(telegram_user_id=telegram_user_id, item_id=item_id)
    await update.message.reply_text(message)
    log_chat(
        f"/delist {item_id}",
        message,
        request_id=str(uuid.uuid4()),
        telegram_user_id=telegram_user_id,
        route_mode="delist_command",
        is_fallback=not ok,
    )


async def events_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args).strip() or None
    events = search_upcoming_events(query=query, limit=8)
    response = _build_events_reply(events)
    await update.message.reply_text(response)
    log_chat(
        f"/events {' '.join(context.args)}".strip(),
        response,
        request_id=str(uuid.uuid4()),
        telegram_user_id=str(update.effective_user.id) if update.effective_user else None,
        route_mode="events_command",
    )


async def faq_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question = _extract_help_question(update, context)
    if not question:
        await update.message.reply_text(
            "AI FAQ bot is ready.\n"
            "Ask directly in chat, or use:\n"
            "/help <your question>\n\n"
            "Examples:\n"
            "/help can I pay with paypal?\n"
            "/help I want electronics items\n"
            "/help when is the next market event?"
        )
        return

    result = answer_with_ai_and_db(question, gpt)
    response = result.get("text", "Sorry, I cannot answer now.")
    await update.message.reply_text(response)
    log_chat(
        f"/help {question}",
        response,
        request_id=str(uuid.uuid4()),
        telegram_user_id=str(update.effective_user.id) if update.effective_user else None,
        route_mode=str(result.get("mode", "help_ai_faq")),
        llm_model=result.get("model"),
        latency_ms=result.get("latency_ms"),
    )


def main():
    global gpt
    global intent_rows
    
    # Configure logging so you can see initialization and error messages
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                        level=logging.INFO)
    
    # Load the configuration data from file
    logging.info('INIT: Loading configuration...')
    _load_dotenv()
    config = configparser.ConfigParser()
    config.read('config.ini')

    gpt = ChatGPT(config)
    intent_rows = load_intents()
    init_db()
    logging.info("INIT: Loaded %s intents from data/intent_seed.csv", len(intent_rows))

    # Create an Application for your bot
    logging.info('INIT: Connecting the Telegram bot...')
    telegram_token = _get_setting(
        config,
        env_key="TELEGRAM_ACCESS_TOKEN",
        section="TELEGRAM",
        option="ACCESS_TOKEN",
        required=True,
    )
    app = ApplicationBuilder().token(telegram_token).post_init(post_init).build()

    # Register a message handler
    logging.info('INIT: Registering the message handler...')
    publish_conversation = ConversationHandler(
        entry_points=[CommandHandler("publish", publish_start)],
        states={
            PUBLISH_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, publish_title_step)],
            PUBLISH_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, publish_category_step)],
            PUBLISH_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, publish_price_step)],
            PUBLISH_CONDITION: [MessageHandler(filters.TEXT & ~filters.COMMAND, publish_condition_step)],
            PUBLISH_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, publish_description_step)],
            PUBLISH_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, publish_confirm_step)],
        },
        fallbacks=[CommandHandler("cancel", publish_cancel)],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", faq_help_command))
    app.add_handler(CommandHandler("items", items_command))
    app.add_handler(CommandHandler("myitems", myitems_command))
    app.add_handler(publish_conversation)
    app.add_handler(CommandHandler("cancel", publish_cancel))
    app.add_handler(CommandHandler("delist", delist_command))
    app.add_handler(CommandHandler("events", events_command))
    app.add_handler(CallbackQueryHandler(menu_callback, pattern=r"^menu_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, callback))

    # Start the bot
    logging.info('INIT: Initialization done!')
    app.run_polling(drop_pending_updates=True)

async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("UPDATE: " + str(update))
    loading_message = await update.message.reply_text('Thinking...')
    user_message = update.message.text
    request_id = str(uuid.uuid4())
    telegram_user_id = str(update.effective_user.id) if update.effective_user else None

    # First route using project seed data (intent + faq + escalation).
    routed = route_message(user_message, intent_rows)
    if routed is not None:
        response = routed["response"]
        logging.info(
            "ROUTE: mode=%s intent=%s faq_id=%s",
            routed.get("mode"),
            routed.get("intent"),
            routed.get("faq_id"),
        )
        log_chat(
            user_message,
            response,
            request_id=request_id,
            telegram_user_id=telegram_user_id,
            detected_intent=routed.get("intent"),
            route_mode=routed.get("mode"),
            faq_id=int(routed["faq_id"]) if routed.get("faq_id") else None,
            rule_id=int(routed["rule_id"]) if routed.get("rule_id") else None,
            is_fallback=False,
        )
    else:
        # Fallback to AI FAQ bot with SQL retrieval context.
        llm_result = answer_with_ai_and_db(user_message, gpt)
        response = llm_result.get("text", "")
        mode = str(llm_result.get("mode", "ai_faq_sql"))
        logging.info("ROUTE: mode=%s", mode)
        log_chat(
            user_message,
            response,
            request_id=request_id,
            telegram_user_id=telegram_user_id,
            route_mode=mode,
            llm_model=llm_result.get("model"),
            llm_estimated_cost=None,
            latency_ms=llm_result.get("latency_ms"),
            is_fallback=True,
        )

    await loading_message.edit_text(response)
    
if __name__ == '__main__':
    main()
