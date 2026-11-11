from __future__ import annotations

import logging
from datetime import time

from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal, init_db
from app.handlers import register
from app.handlers.jobs import process_publish_queue, weekly_report
from app.models import Channel
from app.services.brain import version_stamp

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s %(message)s", level=logging.INFO)
log = logging.getLogger("sg")


def bootstrap() -> None:
    init_db()
    db = SessionLocal()
    try:
        if not db.scalar(select(Channel).limit(1)):
            db.add(Channel(name="По полочкам", brain_version=version_stamp()))
            db.commit()
    finally:
        db.close()


def main() -> None:
    if not settings.telegram_bot_token:
        raise SystemExit("Заполните TELEGRAM_BOT_TOKEN в .env")
    bootstrap()
    from telegram import MenuButtonCommands
    from telegram.ext import Application

    from app.keyboards import BOT_COMMANDS

    async def post_init(application: Application) -> None:
        await application.bot.set_my_commands(BOT_COMMANDS)
        await application.bot.set_chat_menu_button(MenuButtonCommands())

    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .concurrent_updates(True)
        .post_init(post_init)
        .build()
    )
    register(app)
    jq = app.job_queue
    jq.run_repeating(process_publish_queue, interval=60, first=15, name="publish-queue")
    jq.run_daily(weekly_report, time=time(hour=10, minute=0), days=(0,), name="weekly-stats")
    log.info("Бот запущен, владелец=%s", settings.telegram_owner_id or "не задан (отвечает всем — задайте TELEGRAM_OWNER_ID)")
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
