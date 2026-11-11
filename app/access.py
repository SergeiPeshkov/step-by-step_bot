from telegram import Update
from telegram.ext import ContextTypes

from app.config import settings


def is_owner(update: Update) -> bool:
    user = update.effective_user
    if not user:
        return False
    if not settings.telegram_owner_id:
        # Без TELEGRAM_OWNER_ID бот никого не слушает, чтобы чужие не тратили деньги на генерацию.
        return False
    return user.id == settings.telegram_owner_id


async def guard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if is_owner(update):
        return True
    if update.message:
        if not settings.telegram_owner_id:
            await update.message.reply_text(
                f"Бот отвечает только владельцу. Укажите в .env TELEGRAM_OWNER_ID={update.effective_user.id if update.effective_user else ''} и перезапустите бота."
            )
        else:
            await update.message.reply_text("Бот отвечает только владельцу.")
    elif update.callback_query:
        await update.callback_query.answer("Нет доступа", show_alert=True)
    return False
