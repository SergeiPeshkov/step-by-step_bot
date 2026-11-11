from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from telegram.ext import ContextTypes

from app.adapters.publishers import get_publishers
from app.db import SessionLocal
from app.enums import VideoStatus
from app.models import Publication, Video
from app.services.pipeline import title_of


async def process_publish_queue(context: ContextTypes.DEFAULT_TYPE) -> None:
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        videos = list(
            db.scalars(
                select(Video).where(Video.status == VideoStatus.QUEUED, Video.publish_at <= now)
            )
        )
        if not videos:
            return
        pubs = get_publishers(context.bot)
        for video in videos:
            path = video.assembled_path
            if not path:
                continue
            from pathlib import Path

            caption = title_of(video)
            tags = "#пополочкам"
            ok_any = False
            for pub in pubs:
                rec = Publication(video_id=video.id, platform=pub.name, caption=caption, hashtags=tags, status="pending")
                db.add(rec)
                try:
                    url = await pub.publish(Path(path), caption, tags)
                    rec.post_url = url
                    rec.status = "published"
                    rec.published_at = now
                    ok_any = True
                except Exception as exc:
                    rec.status = "error"
                    rec.stats_json = str(exc)[:500]
                    if video.card_chat_id:
                        await context.bot.send_message(video.card_chat_id, f"Ошибка {pub.name} для #{video.id}: {exc}")
            if ok_any:
                video.status = VideoStatus.PUBLISHED
                video.published_at = now
                if video.scene_id and video.scene:
                    from app.enums import SceneUse

                    video.scene.use_status = SceneUse.USED
                if video.card_chat_id:
                    await context.bot.send_message(video.card_chat_id, f"Ролик #{video.id} вышел на площадках.")
            db.commit()
    finally:
        db.close()


async def weekly_report(context: ContextTypes.DEFAULT_TYPE) -> None:
    from app.config import settings
    from sqlalchemy import func

    db = SessionLocal()
    try:
        published = db.scalar(select(func.count(Video.id)).where(Video.status == VideoStatus.PUBLISHED)) or 0
        if settings.telegram_owner_id:
            await context.bot.send_message(
                settings.telegram_owner_id,
                f"Недельный отчёт: опубликовано всего {published} роликов. Детали — /stats /costs.",
            )
    finally:
        db.close()
