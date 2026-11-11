from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.access import guard
from app.enums import AwaitKind, SceneUse, VideoStatus
from app.handlers.common import send_card, send_discussion, session, set_await, state_of
from app.keyboards import fact_kb
from app.models import VideoFact
from app.services import discussion, facts
from app.models import Scene, ScriptVersion, Shot, Video, VoicePhrase
from app.services.brain import BLOCKS, save_block, version_stamp
from app.handlers.commands import (
    cmd_brain,
    cmd_costs,
    cmd_new,
    cmd_plan,
    cmd_queue,
    cmd_settings,
    cmd_stats,
    cmd_videos,
)
from app.keyboards import MENU_BUTTONS
from app.services.plan import import_bytes
from app.services.pipeline import add_exemplar, generate_script, mark_stale_after_script_change, title_of

_MENU_HANDLERS = {
    "new": cmd_new,
    "plan": cmd_plan,
    "videos": cmd_videos,
    "queue": cmd_queue,
    "stats": cmd_stats,
    "costs": cmd_costs,
    "brain": cmd_brain,
    "settings": cmd_settings,
}


async def on_menu_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    label = (update.message.text or "").strip()
    cmd = MENU_BUTTONS.get(label)
    handler = _MENU_HANDLERS.get(cmd or "")
    if handler:
        await handler(update, context)


async def on_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update, context):
        return
    doc = update.message.document
    if not doc or not doc.file_name:
        return
    name = doc.file_name.lower()
    st = state_of(update.effective_user.id)
    tg_file = await doc.get_file()
    raw = await tg_file.download_as_bytearray()
    if st.awaiting.startswith("brain") or name.endswith(".md"):
        block = st.extra if st.awaiting == AwaitKind.BRAIN_EDIT else name.replace(".md", "")
        if block in BLOCKS:
            save_block(block, raw.decode("utf-8"))
            set_await(update.effective_user.id, AwaitKind.NONE)
            await update.message.reply_text(f"Блок «{BLOCKS[block]}» обновлён. Мозг v{version_stamp()}.")
            return
    if name.endswith((".csv", ".json", ".tsv", ".txt")):
        db = session()
        try:
            n = import_bytes(db, bytes(raw), doc.file_name)
            await update.message.reply_text(f"Импортировано сцен: {n}. Смотрите /plan")
        except Exception as exc:
            await update.message.reply_text(f"Не удалось прочитать план: {exc}")
        finally:
            db.close()
        return
    await update.message.reply_text("Нужен CSV/JSON для плана или .md для блока мозга.")


async def on_text_or_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update, context):
        return
    if update.message.text and update.message.text.startswith("/"):
        return
    user_id = update.effective_user.id
    st = state_of(user_id)
    text = (update.message.text or "").strip()
    if update.message.voice or update.message.audio:
        text = text or await _transcribe(update, context)
        if not text:
            await update.message.reply_text("Голос принят, но распознать не удалось. Напишите тему текстом.")
            return

    if st.awaiting == AwaitKind.NEW_TOPIC or st.awaiting == "new_topic":
        await _new_from_topic(update, context, text)
        return
    if st.awaiting in (AwaitKind.DISCUSS_SCRIPT, AwaitKind.DISCUSS_VISUAL) and st.video_id:
        stage = discussion.SCRIPT if st.awaiting == AwaitKind.DISCUSS_SCRIPT else discussion.VISUAL
        db = session()
        try:
            video = db.get(Video, st.video_id)
            if not video:
                set_await(user_id, AwaitKind.NONE)
                return
            await context.bot.send_chat_action(update.effective_chat.id, "typing")
            answer = await discussion.reply(db, video, stage, text)
            await send_discussion(update.message, video.id, stage, answer)
        except Exception as exc:
            await update.message.reply_text(f"ИИ-сценарист не ответил: {exc}")
        finally:
            db.close()
        return
    if st.awaiting in (AwaitKind.FACT_EDIT, AwaitKind.FACT_SOURCE, AwaitKind.FACT_ADD) and st.video_id:
        from app.handlers.common import fact_text

        db = session()
        try:
            if st.awaiting == AwaitKind.FACT_ADD:
                video = db.get(Video, st.video_id)
                link = facts.add(db, video, text)
                await update.message.reply_text("Факт добавлен и попадёт в сценарий.")
            else:
                link = db.get(VideoFact, int(st.extra or 0))
                if not link:
                    set_await(user_id, AwaitKind.NONE)
                    return
                if st.awaiting == AwaitKind.FACT_EDIT:
                    facts.correct(db, link, text)
                else:
                    facts.set_source(db, link, text)
                db.refresh(link)
            set_await(user_id, AwaitKind.NONE)
            await update.message.reply_text(fact_text(link), reply_markup=fact_kb(link.id))
        finally:
            db.close()
        return
    if st.awaiting == AwaitKind.BRAIN_EDIT:
        save_block(st.extra, text)
        set_await(user_id, AwaitKind.NONE)
        await update.message.reply_text(f"Блок «{BLOCKS.get(st.extra, st.extra)}» сохранён.")
        return
    if st.awaiting in (AwaitKind.SCRIPT_FEEDBACK, AwaitKind.SCRIPT_OWN) and st.video_id:
        db = session()
        try:
            video = db.get(Video, st.video_id)
            if not video:
                return
            if st.awaiting == AwaitKind.SCRIPT_OWN:
                db.add(ScriptVersion(video_id=video.id, text=text, note="свой текст"))
                mark_stale_after_script_change(db, video)
                video.status = VideoStatus.SCRIPT
                db.commit()
                db.refresh(video)
                set_await(user_id, AwaitKind.NONE)
                await send_card(update.message, video, context)
            else:
                await update.message.reply_text("Пишу новую версию…")
                await generate_script(db, video, note=text)
                mark_stale_after_script_change(db, video)
                video.status = VideoStatus.SCRIPT
                db.commit()
                db.refresh(video)
                set_await(user_id, AwaitKind.NONE)
                await send_card(update.message, video, context)
        finally:
            db.close()
        return
    if st.awaiting == AwaitKind.SHOT_EDIT and st.video_id:
        db = session()
        try:
            shot = db.get(Shot, int(st.extra or 0))
            if shot:
                shot.description = text
                shot.stale = True
                db.commit()
                await update.message.reply_text(f"Кадр {shot.ord} обновлён.")
            set_await(user_id, AwaitKind.NONE)
        finally:
            db.close()
        return
    if st.awaiting == AwaitKind.PROMPT_EDIT and st.video_id:
        db = session()
        try:
            shot = db.get(Shot, int(st.extra or 0))
            if shot:
                shot.prompt = text
                db.commit()
                await update.message.reply_text("Промпт сохранён.")
            set_await(user_id, AwaitKind.NONE)
        finally:
            db.close()
        return
    if st.awaiting == AwaitKind.REGEN_NOTE and st.video_id:
        db = session()
        try:
            shot = db.get(Shot, int(st.extra or 0))
            if shot and text:
                shot.prompt = text
                db.commit()
            set_await(user_id, AwaitKind.NONE)
            await update.message.reply_text("Ок. Нажмите перегенерацию кадра ещё раз или откройте карточку.")
        finally:
            db.close()
        return
    await update.message.reply_text("Команды: /new /plan /videos. Или откройте карточку ролика.")


async def _new_from_topic(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    db = session()
    try:
        from app.services.brain import version_stamp

        video = Video(custom_topic=text, status=VideoStatus.DRAFT, brain_version=version_stamp())
        db.add(video)
        db.commit()
        db.refresh(video)
        set_await(update.effective_user.id, AwaitKind.DISCUSS_SCRIPT, video.id)
        await update.message.reply_text(
            "Ролик создан. Обсуждаем его с ИИ-сценаристом: пишите сообщения прямо в чат (можно голосом), "
            "когда договоритесь — нажмите «Написать сценарий»."
        )
        answer = await discussion.start(db, video, discussion.SCRIPT)
        await send_discussion(update.message, video.id, discussion.SCRIPT, answer)
    finally:
        db.close()


async def _transcribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    from app.config import settings
    import httpx

    if settings.llm_provider != "openai" or not settings.llm_api_key:
        return ""
    media = update.message.voice or update.message.audio
    tg_file = await context.bot.get_file(media.file_id)
    data = await tg_file.download_as_bytearray()
    url = f"{settings.llm_base_url.rstrip('/')}/audio/transcriptions"
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            url,
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            files={"file": ("voice.ogg", bytes(data), "audio/ogg")},
            data={"model": "whisper-1"},
        )
        if r.status_code >= 400:
            return ""
        return r.json().get("text") or ""
