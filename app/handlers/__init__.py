from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from app.handlers.callbacks import on_callback
from app.handlers.commands import (
    cmd_brain,
    cmd_costs,
    cmd_articles,
    cmd_facts,
    cmd_menu,
    cmd_new,
    cmd_plan,
    cmd_queue,
    cmd_settings,
    cmd_site,
    cmd_start,
    cmd_stats,
    cmd_videos,
)
from app.handlers.messages import on_document, on_menu_button, on_text_or_voice
from app.keyboards import MENU_BUTTONS


def register(app: Application) -> None:
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("new", cmd_new))
    app.add_handler(CommandHandler("plan", cmd_plan))
    app.add_handler(CommandHandler("videos", cmd_videos))
    app.add_handler(CommandHandler("queue", cmd_queue))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("costs", cmd_costs))
    app.add_handler(CommandHandler("facts", cmd_facts))
    app.add_handler(CommandHandler("articles", cmd_articles))
    app.add_handler(CommandHandler("site", cmd_site))
    app.add_handler(CommandHandler("brain", cmd_brain))
    app.add_handler(CommandHandler("settings", cmd_settings))
    app.add_handler(MessageHandler(filters.Text(list(MENU_BUTTONS)), on_menu_button))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.Document.ALL, on_document))
    app.add_handler(MessageHandler(filters.TEXT | filters.VOICE | filters.AUDIO, on_text_or_voice))
