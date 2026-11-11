from __future__ import annotations

import json
from datetime import datetime, timedelta
from io import BytesIO

from sqlalchemy import select
from telegram import InputFile, Update
from telegram.ext import ContextTypes

from app.access import guard
from app.config import settings
from app.enums import AwaitKind, SceneUse, VideoStatus
from app.handlers.common import fact_text, refresh_card, send_card, send_discussion, send_facts, session, set_await
from app.keyboards import fact_kb
from app.models import VideoFact
from app.services import articles, discussion, facts
from app.keyboards import back_stages, brain_kb, card_kb, scene_list, shot_pick
from app.models import Scene, ScriptVersion, Shot, Video, VoicePhrase
from app.services.brain import BLOCKS, dump_all, load_block, version_stamp
from app.services.costs import CostLimitError
from app.services.pipeline import (
    add_exemplar,
    approved_script,
    assemble,
    generate_media,
    generate_prompts,
    generate_script,
    generate_storyboard,
    generate_voice,
    latest_script,
    mark_stale_after_script_change,
    title_of,
)
from app.cards import card_text
from app.services.plan import list_scenes


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update, context):
        return
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    try:
        if data.startswith("pl:"):
            page = int(data.split(":")[1])
            db = session()
            try:
                scenes = list_scenes(db)
            finally:
                db.close()
            await q.edit_message_reply_markup(reply_markup=scene_list(scenes, page))
            return
        if data == "sc:custom":
            set_await(q.from_user.id, AwaitKind.NEW_TOPIC)
            await q.message.reply_text("Напишите тему или пришлите голос.")
            return
        if data.startswith("sc:"):
            await _pick_scene(q, context, int(data.split(":")[1]))
            return
        if data.startswith("br:"):
            await _brain(q, context, data.split(":", 1)[1])
            return
        if data.startswith("bk:"):
            _, vid, st = data.split(":")
            db = session()
            try:
                video = db.get(Video, int(vid))
                video.status = st
                db.commit()
                await refresh_card(context, video)
                await q.message.reply_text(f"Вернулись к этапу: {st}")
            finally:
                db.close()
            return
        if data.startswith("sh:"):
            _, vid, sid, action = data.split(":")
            await _shot_action(q, context, int(vid), int(sid), action)
            return
        if data.startswith("f:"):
            _, lid, action = data.split(":")
            await _fact_action(q, context, int(lid), action)
            return
        if data.startswith("v:"):
            _, vid, action = data.split(":")
            await _video_action(q, context, int(vid), action)
            return
    except CostLimitError as exc:
        await q.message.reply_text(str(exc))
    except Exception as exc:
        await q.message.reply_text(f"Ошибка: {exc}")


async def _pick_scene(q, context, scene_id: int) -> None:
    db = session()
    try:
        scene = db.get(Scene, scene_id)
        if not scene:
            await q.message.reply_text("Сцена не найдена.")
            return
        scene.use_status = SceneUse.IN_PROGRESS
        video = Video(scene_id=scene.id, status=VideoStatus.DRAFT, brain_version=version_stamp())
        db.add(video)
        db.commit()
        db.refresh(video)
        set_await(q.from_user.id, AwaitKind.DISCUSS_SCRIPT, video.id)
        await q.message.reply_text(
            f"Ролик по сцене {scene.code}. Обсуждаем с ИИ-сценаристом: пишите сообщения прямо в чат, "
            "когда договоритесь — нажмите «Написать сценарий»."
        )
        answer = await discussion.start(db, video, discussion.SCRIPT)
        await send_discussion(q.message, video.id, discussion.SCRIPT, answer)
    finally:
        db.close()


async def _brain(q, context, key: str) -> None:
    if key == "dump":
        buf = BytesIO(dump_all().encode("utf-8"))
        buf.name = "brain.md"
        await q.message.reply_document(document=buf, filename="brain.md")
        return
    if key not in BLOCKS:
        return
    text = load_block(key)
    set_await(q.from_user.id, AwaitKind.BRAIN_EDIT, extra=key)
    await q.message.reply_text(
        f"{BLOCKS[key]} (v{version_stamp()}):\n\n{text[:3500]}\n\nПришлите новый текст или .md файл.",
        reply_markup=brain_kb(),
    )


async def _shot_action(q, context, vid: int, sid: int, action: str) -> None:
    db = session()
    try:
        video = db.get(Video, vid)
        shot = db.get(Shot, sid)
        if action == "edit":
            set_await(q.from_user.id, AwaitKind.SHOT_EDIT, vid, str(sid))
            await q.message.reply_text(f"Кадр {shot.ord} сейчас:\n{shot.description}\n\nПришлите новое описание.")
        elif action == "prompt":
            set_await(q.from_user.id, AwaitKind.PROMPT_EDIT, vid, str(sid))
            await q.message.reply_text(f"Промпт кадра {shot.ord}:\n{shot.prompt[:3000]}\n\nПришлите новый.")
        elif action == "regen":
            await q.message.reply_text(f"Перегенерирую кадр {shot.ord}…")
            await generate_media(db, video, only_shot_id=sid)
            await _send_media_album(q, context, video)
            await refresh_card(context, db.get(Video, vid))
        elif action == "model":
            await generate_media(db, video, only_shot_id=sid, quality=True)
            await q.message.reply_text(f"Кадр {shot.ord} — качественная модель.")
            await _send_media_album(q, context, db.get(Video, vid))
        elif action == "voice":
            phrase = next((p for p in video.phrases if p.shot_id == sid), None)
            if phrase:
                await generate_voice(db, video, only_phrase_id=phrase.id)
                if phrase.path:
                    await q.message.reply_audio(audio=open(phrase.path, "rb"), caption=f"Фраза кадра {shot.ord}")
        db.commit()
    finally:
        db.close()


async def _video_action(q, context, vid: int, action: str) -> None:
    db = session()
    try:
        video = db.get(Video, vid)
        if not video:
            await q.message.reply_text("Ролик не найден")
            return
        if action == "card":
            await send_card(q.message, video, context)
            return
        if action == "ds":
            set_await(q.from_user.id, AwaitKind.DISCUSS_SCRIPT, vid)
            answer = await discussion.start(db, video, discussion.SCRIPT)
            await send_discussion(q.message, vid, discussion.SCRIPT, answer)
            return
        if action == "ws":
            await q.message.reply_text("ИИ-сценарист пишет сценарий по итогам обсуждения…")
            await discussion.write_script(db, video)
            set_await(q.from_user.id, AwaitKind.NONE, vid)
            await send_card(q.message, video, context)
            return
        if action == "dv":
            set_await(q.from_user.id, AwaitKind.DISCUSS_VISUAL, vid)
            answer = await discussion.start(db, video, discussion.VISUAL)
            await send_discussion(q.message, vid, discussion.VISUAL, answer)
            return
        if action == "wv":
            await q.message.reply_text("ИИ-сценарист собирает раскадровку и промпты…")
            await discussion.write_storyboard(db, video)
            set_await(q.from_user.id, AwaitKind.NONE, vid)
            await send_card(q.message, video, context)
            return
        if action == "fl":
            await send_facts(q.message, video)
            return
        if action == "fa":
            set_await(q.from_user.id, AwaitKind.FACT_ADD, vid)
            await q.message.reply_text("Напишите факт, который нужно добавить в ролик (например, «первый взнос — от 20%»).")
            return
        if action == "fx":
            await q.message.reply_text("ИИ заново выписывает факты из сценария…")
            await facts.extract(db, video)
            await send_facts(q.message, video)
            await send_card(q.message, video, context)
            return
        if action == "fn":
            pending = facts.pending_links(video)
            if pending:
                await q.message.reply_text(
                    f"Дальше пока нельзя: {len(pending)} факт(ов) ждут проверки. Отметьте каждый: верно, исправить или убрать."
                )
                await send_facts(q.message, video, only_pending=True)
                return
            if facts.script_changes(video):
                await q.message.reply_text("Вношу исправленные факты в сценарий…")
                ver = await facts.apply_to_script(db, video)
                if ver:
                    await q.message.reply_text(f"Сценарий поправлен под факты:\n\n{ver.text[:3800]}")
            else:
                await facts.apply_to_script(db, video)
            await _start_visual(q, db, video)
            await send_card(q.message, video, context)
            return
        if action == "art":
            await q.message.reply_text("Пишу статью для сайта по сценарию и проверенным фактам…")
            art = await articles.generate(db, video)
            await _send_article(q.message, art)
            from app.services.site import auto_update

            res = await auto_update(db)
            if res:
                await q.message.reply_text(("🌐 " if res.ok else "⚠️ ") + res.text[:3900])
            return
        if action == "gs":
            await q.message.reply_text("Пишу сценарий…")
            await generate_script(db, video)
        elif action == "ok":
            await _approve(q, context, db, video)
        elif action == "nv":
            set_await(q.from_user.id, AwaitKind.SCRIPT_FEEDBACK, vid)
            await q.message.reply_text("Напишите замечание свободным текстом («глубже», «концовка сложная»).")
            return
        elif action == "own":
            set_await(q.from_user.id, AwaitKind.SCRIPT_OWN, vid)
            await q.message.reply_text("Пришлите свой текст целиком — он станет новой версией.")
            return
        elif action == "vs":
            lines = []
            for s in video.scripts:
                mark = "✓" if s.approved else "·"
                lines.append(f"{mark} v{s.id} {s.created_at:%d.%m %H:%M} {s.note[:40]}\n{s.text[:200]}")
            await q.message.reply_text("\n\n".join(lines)[:3900] or "Версий нет")
            return
        elif action == "ex":
            add_exemplar(video)
            await q.message.reply_text("Сценарий добавлен в эталоны.")
            return
        elif action == "redo":
            await q.message.reply_text("Собираю раскадровку заново…")
            await generate_storyboard(db, video)
        elif action == "edshot":
            await q.message.reply_text("Какой кадр изменить?", reply_markup=shot_pick(video, "edit"))
            return
        elif action == "pr":
            text = "\n\n".join(f"{s.ord}. {s.prompt}" for s in video.shots if s.prompt) or "Промптов нет"
            await q.message.reply_text(text[:3900])
            return
        elif action == "gen":
            await q.message.reply_text("Генерирую кадры… Это может занять время.")
            await generate_media(db, video)
            db.refresh(video)
            await _send_media_album(q, context, video)
        elif action == "rgen":
            await q.message.reply_text("Какой кадр перегенерировать?", reply_markup=shot_pick(video, "regen"))
            return
        elif action == "model":
            await q.message.reply_text("Качественная модель для какого кадра?", reply_markup=shot_pick(video, "model"))
            return
        elif action == "rvoice":
            await q.message.reply_text("Какую фразу переозвучить?", reply_markup=shot_pick(video, "voice"))
            return
        elif action == "pub":
            await _publish_now(q, context, db, video)
        elif action == "queue":
            when = datetime.utcnow().replace(
                hour=settings.default_publish_hour, minute=settings.default_publish_minute, second=0, microsecond=0
            )
            if when <= datetime.utcnow():
                when += timedelta(days=1)
            video.publish_at = when
            video.status = VideoStatus.QUEUED
            db.commit()
            await q.message.reply_text(f"В очереди на {when:%d.%m %H:%M} UTC.")
        elif action == "unq":
            video.status = VideoStatus.ASSEMBLY
            video.publish_at = None
            db.commit()
        elif action == "asm":
            await q.message.reply_text("Собираю ролик на сервере…")
            path = await assemble(db, video)
            await q.message.reply_video(video=open(path, "rb"), caption="Превью")
        elif action == "back":
            await q.message.reply_text("Куда вернуться?", reply_markup=back_stages(vid))
            return
        elif action == "pause":
            video.status = VideoStatus.PAUSED
            db.commit()
        elif action == "resume":
            video.status = VideoStatus.SCRIPT if latest_script(video) else VideoStatus.DRAFT
            db.commit()
        db.refresh(video)
        await refresh_card(context, video)
        try:
            await q.edit_message_text(card_text(video)[:3900], reply_markup=card_kb(video))
        except Exception:
            await send_card(q.message, video, context)
    finally:
        db.close()


async def _approve(q, context, db, video: Video) -> None:
    st = video.status
    if st == VideoStatus.SCRIPT:
        script = latest_script(video)
        if script:
            script.approved = True
        await q.message.reply_text("Сценарий утверждён. Проверка фактов: ИИ выписывает из сценария цифры, даты и условия…")
        await facts.extract(db, video)
        await send_facts(q.message, video)
        await q.message.reply_text(
            "Отметьте каждый факт: «Верно», «Исправить» или «Убрать». Источник можно указать или поправить. "
            "Когда всё проверено — «Факты проверены — дальше» в карточке."
        )
    elif st == VideoStatus.STORYBOARD:
        await generate_prompts(db, video)
        await q.message.reply_text("Промпты готовы. Можно сразу генерировать или посмотреть.")
    elif st == VideoStatus.MEDIA:
        await q.message.reply_text("Озвучиваю…")
        await generate_voice(db, video)
        db.refresh(video)
        for p in video.phrases:
            if p.path:
                await q.message.reply_audio(audio=open(p.path, "rb"), caption=p.text[:80])
    elif st == VideoStatus.VOICE:
        await q.message.reply_text("Собираю ролик…")
        path = await assemble(db, video)
        await q.message.reply_video(video=open(path, "rb"), supports_streaming=True, caption="Превью. Публикация только по вашей кнопке.")
    db.commit()


async def _start_visual(q, db, video: Video) -> None:
    set_await(q.from_user.id, AwaitKind.DISCUSS_VISUAL, video.id)
    await q.message.reply_text(
        "Факты проверены. Этап 2: обсуждаем с ИИ-сценаристом раскадровку и промпты. "
        "Пишите прямо в чат, когда договоритесь — нажмите «Сделать раскадровку и промпты»."
    )
    answer = await discussion.start(db, video, discussion.VISUAL)
    await send_discussion(q.message, video.id, discussion.VISUAL, answer)


async def _fact_action(q, context, link_id: int, action: str) -> None:
    db = session()
    try:
        link = db.get(VideoFact, link_id)
        if not link:
            await q.message.reply_text("Факт не найден. Откройте карточку ролика.")
            return
        if action == "ok":
            facts.confirm(db, link)
        elif action == "rm":
            facts.remove(db, link)
        elif action == "ed":
            set_await(q.from_user.id, AwaitKind.FACT_EDIT, link.video_id, str(link.id))
            await q.message.reply_text(f"Сейчас: {link.fact.text}\n\nНапишите верный вариант факта.")
            return
        elif action == "src":
            set_await(q.from_user.id, AwaitKind.FACT_SOURCE, link.video_id, str(link.id))
            await q.message.reply_text(
                f"Источник сейчас: {link.fact.source or 'не указан'}\n\nПришлите ссылку или название документа."
            )
            return
        db.refresh(link)
        try:
            await q.edit_message_text(fact_text(link), reply_markup=fact_kb(link.id))
        except Exception:
            pass
        video = db.get(Video, link.video_id)
        left = len(facts.pending_links(video))
        if left == 0 and action == "ok":
            await q.message.reply_text("Все факты проверены. Нажмите «Факты проверены — дальше» в карточке.")
            await send_card(q.message, video, context)
    finally:
        db.close()


async def _send_article(message, art) -> None:
    text = articles.as_text(art)
    buf = BytesIO(text.encode("utf-8"))
    buf.name = f"{art.slug}.txt"
    note = f"Статья «{art.title}». Адрес страницы: {art.slug}"
    tags = articles.hashtags(art)
    if tags:
        note += f"\nХэштеги для постов: {tags}"
    missing = articles.missing_sources(art)
    if missing:
        note += f"\n⚠ У {missing} факт(ов) нет источника — добавьте его на этапе «Факты» и пересоздайте статью."
    if not json.loads(art.videos_json or "[]"):
        note += "\nСсылок на ролик пока нет: они добавятся, если создать статью после публикации."
    await message.reply_document(document=buf, filename=f"{art.slug}.txt", caption=note[:1024])


async def _publish_now(q, context, db, video: Video) -> None:
    video.publish_at = datetime.utcnow()
    video.status = VideoStatus.QUEUED
    db.commit()
    from app.handlers.jobs import process_publish_queue

    await process_publish_queue(context)
    await q.message.reply_text("Публикация запущена.")


async def _send_media_album(q, context, video: Video) -> None:
    from telegram import InputMediaPhoto, InputMediaVideo

    media = []
    for shot in video.shots:
        chosen = next((m for m in shot.media if m.chosen), None)
        if not chosen:
            continue
        cap = f"{shot.ord}. {shot.shot_type}"
        if chosen.path.endswith(".mp4"):
            media.append(InputMediaVideo(media=open(chosen.path, "rb"), caption=cap))
        else:
            media.append(InputMediaPhoto(media=open(chosen.path, "rb"), caption=cap))
        if len(media) == 10:
            break
    if media:
        await q.message.reply_media_group(media)
    else:
        await q.message.reply_text("Кадровых файлов нет (чёрные/текстовые кадры без файла).")
