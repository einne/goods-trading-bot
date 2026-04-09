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
    MessageHandler,
    ContextTypes,
    filters,
)
import configparser
import logging
import os
import uuid
from db import init_db, log_chat
from services.event_service import search_upcoming_events
from services.item_service import delist_item, publish_item, search_active_items
from services.intent_service import load_intents
from services.router_service import route_message

gpt = None
intent_rows = []


def _main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("View Items", callback_data="menu_items"),
                InlineKeyboardButton("View Events", callback_data="menu_events"),
            ],
            [
                InlineKeyboardButton("Publish Item", callback_data="menu_publish"),
                InlineKeyboardButton("Delist Item", callback_data="menu_delist"),
            ],
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
        "/publish title|category|price|condition|description\n"
        "/delist <item_id>\n"
        "/events [keyword]\n"
        "/help"
    )


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
        items = search_active_items(query=None, limit=8)
        await query.edit_message_text(_build_items_reply(items), reply_markup=_back_menu_keyboard())
        return

    if data == "menu_events":
        events = search_upcoming_events(query=None, limit=8)
        await query.edit_message_text(_build_events_reply(events), reply_markup=_back_menu_keyboard())
        return

    if data == "menu_publish":
        await query.edit_message_text(
            "Publish format:\n"
            "/publish title|category|price|condition|description\n\n"
            "Example:\n"
            "/publish iPad 9th|Electronics|1800|Like New|Used for one semester",
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
            "Command help:\n"
            "- /items [keyword]: list active items\n"
            "- /publish ...: publish an item\n"
            "- /delist <item_id>: delist your own item\n"
            "- /events [keyword]: list campus events",
            reply_markup=_back_menu_keyboard(),
        )
        return


async def post_init(app):
    await app.bot.set_my_commands(
        [
            BotCommand("start", "Open main menu"),
            BotCommand("items", "View active items"),
            BotCommand("publish", "Publish item"),
            BotCommand("delist", "Delist item"),
            BotCommand("events", "View events"),
            BotCommand("help", "Help"),
        ]
    )


async def items_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args).strip() or None
    items = search_active_items(query=query, limit=8)
    response = _build_items_reply(items)
    await update.message.reply_text(response)
    log_chat(
        f"/items {' '.join(context.args)}".strip(),
        response,
        request_id=str(uuid.uuid4()),
        telegram_user_id=str(update.effective_user.id) if update.effective_user else None,
        route_mode="items_command",
    )


async def publish_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = " ".join(context.args).strip()
    usage = (
        "Usage:\n"
        "/publish title|category|price|condition|description\n"
        "Example:\n"
        "/publish iPad 9th|Electronics|1800|Like New|Used for one semester"
    )
    if not raw:
        await update.message.reply_text(usage)
        return

    parts = [p.strip() for p in raw.split("|")]
    if len(parts) < 5:
        await update.message.reply_text(usage)
        return

    title, category, price_str, condition = parts[0], parts[1], parts[2], parts[3]
    description = "|".join(parts[4:]).strip()

    try:
        price = float(price_str)
        if price < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Price must be a valid non-negative number.")
        return

    telegram_user_id = str(update.effective_user.id) if update.effective_user else "unknown"
    username = update.effective_user.username if update.effective_user else None
    created = publish_item(
        telegram_user_id=telegram_user_id,
        display_name=_display_name(update),
        username=username,
        title=title,
        category=category,
        price=price,
        condition_level=condition,
        description=description,
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
        f"/publish {raw}",
        response,
        request_id=str(uuid.uuid4()),
        telegram_user_id=telegram_user_id,
        route_mode="publish_command",
    )


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


def main():
    global gpt
    global intent_rows
    
    # Configure logging so you can see initialization and error messages
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                        level=logging.INFO)
    
    # Load the configuration data from file
    logging.info('INIT: Loading configuration...')
    config = configparser.ConfigParser()
    config.read('config.ini')

    gpt = ChatGPT(config)
    intent_rows = load_intents()
    init_db()
    logging.info("INIT: Loaded %s intents from data/intent_seed.csv", len(intent_rows))

    # Create an Application for your bot
    logging.info('INIT: Connecting the Telegram bot...')
    telegram_token = os.getenv("TELEGRAM_ACCESS_TOKEN") or config['TELEGRAM']['ACCESS_TOKEN']
    app = ApplicationBuilder().token(telegram_token).post_init(post_init).build()

    # Register a message handler
    logging.info('INIT: Registering the message handler...')
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("items", items_command))
    app.add_handler(CommandHandler("publish", publish_command))
    app.add_handler(CommandHandler("delist", delist_command))
    app.add_handler(CommandHandler("events", events_command))
    app.add_handler(CallbackQueryHandler(menu_callback, pattern=r"^menu_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, callback))

    # Start the bot
    logging.info('INIT: Initialization done!')
    app.run_polling()

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
        # Fallback to LLM for open-domain or unmatched queries.
        llm_result = gpt.submit_with_meta(user_message)
        response = llm_result["text"]
        logging.info("ROUTE: mode=llm_fallback")
        # Token pricing differs by provider/model. Keep nullable default for report aggregation.
        log_chat(
            user_message,
            response,
            request_id=request_id,
            telegram_user_id=telegram_user_id,
            route_mode="llm_fallback",
            llm_model=llm_result.get("model"),
            llm_estimated_cost=None,
            latency_ms=llm_result.get("latency_ms"),
            is_fallback=True,
        )

    await loading_message.edit_text(response)
    
if __name__ == '__main__':
    main()
