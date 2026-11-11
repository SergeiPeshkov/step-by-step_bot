from datetime import datetime, timedelta

from sqlalchemy import func, select
from telegram import InputFile, Update
from telegram.ext import ContextTypes

from app.access import guard
from app.adapters.publishers import get_publishers
from app.config import settings
from app.enums import STATUS_LABEL, SceneUse, VideoStatus
from app.handlers.common import send_card, session, set_await
from app.keyboards import MAIN_KB, brain_kb, scene_list
from app.models import CostEntry, Publication, Scene, Video
from app.services.brain import dump_all, version_stamp
from app.services.costs import period_sum
from app.services.plan import list_scenes
from app.services.pipeline import title_of


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update, context):
        return
    await update.message.reply_text(
        "По полочкам — пульт автора.\n"
        "Команды — в меню слева от поля ввода (кнопка /) и на клавиатуре внизу.\n\n"
        "/new — новый ролик\n"
        "/plan — контент-план (свой CSV/JSON)\n"
        "/videos — ролики в работе\n"
        "/queue — очередь публикаций\n"
        "/stats — статистика\n"
        "/costs — расходы\n"
        "/facts — база фактов\n"
        "/brain — мозг системы\n"
        "/settings — настройки",
        reply_markup=MAIN_KB,
    )


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, context)


async def cmd_new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update, context):
        return
    db = session()
    try:
        scenes = list_scenes(db)
    finally:
        db.close()
    if not scenes:
        set_await(update.effective_user.id, "new_topic")
        await update.message.reply_text(
            "План пока пуст. Напишите тему текстом или голосом — или пришлите файл плана в /plan."
        )
        return
    await update.message.reply_text("Выберите сцену или свою тему:", reply_markup=scene_list(scenes))


async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update, context):
        return
    db = session()
    try:
        scenes = list_scenes(db)
        free = sum(1 for s in scenes if s.use_status == SceneUse.FREE)
        used = len(scenes) - free
        lines = [f"{'○' if s.use_status == SceneUse.FREE else '●'} {s.code} · {s.scene}" for s in scenes[:40]]
        extra = "" if len(scenes) <= 40 else f"\n… ещё {len(scenes) - 40}"
        text = (
            f"Контент-план: {len(scenes)} сцен, свободно {free}, занято {used}.\n"
            "Свой план: пришлите CSV или JSON "
            "(колонки number, code, theme, scene, under, rubric).\n\n"
            + ("\n".join(lines) if lines else "Пусто — загрузите файл.")
            + extra
        )
        kb = scene_list(scenes) if scenes else None
        await update.message.reply_text(text[:3900], reply_markup=kb)
    finally:
        db.close()


async def cmd_videos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update, context):
        return
    db = session()
    try:
        videos = list(db.scalars(select(Video).order_by(Video.id.desc()).limit(20)))
        if not videos:
            await update.message.reply_text("Роликов ещё нет. /new")
            return
        for v in videos:
            await send_card(update.message, v, context)
    finally:
        db.close()


async def cmd_queue(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update, context):
        return
    db = session()
    try:
        videos = list(db.scalars(select(Video).where(Video.status == VideoStatus.QUEUED).order_by(Video.publish_at)))
        if not videos:
            await update.message.reply_text("Очередь пуста.")
            return
        lines = [f"#{v.id} {title_of(v)} — {v.publish_at}" for v in videos]
        await update.message.reply_text("Очередь публикаций:\n" + "\n".join(lines))
    finally:
        db.close()


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update, context):
        return
    db = session()
    try:
        pubs = list(db.scalars(select(Publication).order_by(Publication.id.desc()).limit(15)))
        published = db.scalar(select(func.count(Video.id)).where(Video.status == VideoStatus.PUBLISHED)) or 0
        if not pubs:
            await update.message.reply_text(f"Опубликовано роликов: {published}. Статистики площадок пока нет.")
            return
        lines = [f"{p.platform}: {p.status} {p.post_url or ''} {p.stats_json}" for p in pubs]
        await update.message.reply_text(f"Опубликовано: {published}\n" + "\n".join(lines)[:3500])
    finally:
        db.close()


async def cmd_costs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update, context):
        return
    db = session()
    try:
        now = datetime.utcnow()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        day = period_sum(db, now - timedelta(days=1))
        month = period_sum(db, month_start)
        videos = list(db.scalars(select(Video).order_by(Video.id.desc()).limit(10)))
        lines = [f"#{v.id} {title_of(v)} — {v.cost:.1f} ₽ ({STATUS_LABEL.get(v.status, v.status)})" for v in videos]
        await update.message.reply_text(
            f"Сутки: {day:.1f} / {settings.daily_cost_limit:.0f} ₽\n"
            f"Месяц: {month:.1f} / {settings.monthly_cost_limit:.0f} ₽\n\n" + "\n".join(lines)
        )
    finally:
        db.close()


async def cmd_brain(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update, context):
        return
    await update.message.reply_text(
        f"Мозг v{version_stamp()}. Выберите блок — пришлите новый текст или .md файл.",
        reply_markup=brain_kb(),
    )


async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update, context):
        return
    await update.message.reply_text(
        "Провайдеры задаются в .env (без ключей в чате).\n"
        f"Текст: {settings.llm_provider} / {settings.llm_model}\n"
        f"Картинки: {settings.image_provider} / {settings.image_model}\n"
        f"Видео: {settings.video_provider}\n"
        f"Голос: {settings.tts_provider} / {settings.tts_voice}\n"
        f"Площадки: {', '.join(p.name for p in get_publishers(context.bot)) or 'не настроены'}\n"
        f"Ссылка на сайт: {settings.site_url or 'нет'}\n"
        f"Публикация по умолчанию: {settings.default_publish_hour:02d}:{settings.default_publish_minute:02d}\n"
        f"Лимит видеокадров: {settings.max_video_shots}\n"
        f"Лимиты: {settings.daily_cost_limit:.0f} ₽/день, {settings.monthly_cost_limit:.0f} ₽/мес"
    )


async def cmd_facts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update, context):
        return
    from app.models import Fact

    db = session()
    try:
        confirmed = db.scalar(select(func.count(Fact.id)).where(Fact.status == "confirmed")) or 0
        outdated = db.scalar(select(func.count(Fact.id)).where(Fact.status == "outdated")) or 0
        last = list(
            db.scalars(select(Fact).where(Fact.status == "confirmed").order_by(Fact.checked_at.desc(), Fact.id.desc()).limit(20))
        )
        lines = [f"• {f.text} — {f.checked_at:%d.%m.%Y}" + (f"\n  {f.source}" if f.source else "") for f in last if f.checked_at]
        await update.message.reply_text(
            (f"База фактов: проверено {confirmed}, устарело {outdated}.\n\nПоследние проверенные:\n" + "\n".join(lines))[:3900]
            if lines
            else "База фактов пока пуста. Факты появляются после утверждения сценария."
        )
    finally:
        db.close()
