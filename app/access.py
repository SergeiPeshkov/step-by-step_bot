from telegram import Update
from telegram.ext import ContextTypes

from app.config import settings


def is_owner(update: Update) -> bool:
    user = update.effective_user
    if not user:
        return False
    if not settings.telegram_owner_id:
        return True
    return user.id == settings.telegram_owner_id


async def guard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if is_owner(update):
        return True
    if update.message:
        await update.message.reply_text("Бот отвечает только владельцу.")
    elif update.callback_query:
        await update.callback_query.answer("Нет доступа", show_alert=True)
    return False
