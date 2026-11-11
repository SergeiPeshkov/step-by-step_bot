"""Сборка и выкладка сайта «По полочкам» прямо из бота.

Бот пишет статьи из базы в site/src/data/articles.json, запускает `npm run build`
и, если задана SITE_DEPLOY_CMD, выполняет её (например, rsync или scp папки dist на хостинг).
GitHub для этого не нужен: всё происходит на машине, где работает бот.
"""

from __future__ import annotations

import asyncio
import json
import time
import logging
import os
import shutil
from dataclasses import dataclass
from datetime import timezone
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assembler.ffmpeg import ffmpeg_bin
from app.config import settings
from app.models import Article, Video
from app.services.articles import as_dict

log = logging.getLogger(__name__)

_lock = asyncio.Lock()


@dataclass
class SiteResult:
    ok: bool
    text: str


async def _run(cmd: list[str] | str, env: dict[str, str], shell: bool = False, timeout: int = 600) -> tuple[int, str]:
    if shell:
        proc = await asyncio.create_subprocess_shell(
            cmd, cwd=settings.site_dir, env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
    else:
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=settings.site_dir, env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return 1, "Превышено время ожидания"
    return proc.returncode or 0, out.decode("utf-8", errors="replace")


def _tail(text: str, lines: int = 15) -> str:
    return "\n".join(text.strip().splitlines()[-lines:])


async def _media_for(video: Video, slug: str, env: dict[str, str]) -> dict | None:
    """Ролик для сайта: mp4 720p с быстрым стартом и обложка. Пересобирается, только если исходник новее."""
    src = Path(video.assembled_path or "")
    if not video.assembled_path or not src.exists():
        return None
    out_dir = settings.site_dir / "public" / "video"
    out_dir.mkdir(parents=True, exist_ok=True)
    mp4, jpg = out_dir / f"{slug}.mp4", out_dir / f"{slug}.jpg"
    if not mp4.exists() or mp4.stat().st_mtime < src.stat().st_mtime:
        tmp = out_dir / f"{slug}.tmp.mp4"
        code, out = await _run(
            [ffmpeg_bin(), "-y", "-i", str(src), "-vf", "scale=-2:1280", "-c:v", "libx264", "-preset", "slow",
             "-crf", "26", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(tmp)],
            env,
        )
        if code:
            log.warning("site video %s failed: %s", slug, _tail(out))
            tmp.unlink(missing_ok=True)
            return None
        os.replace(tmp, mp4)
        jpg.unlink(missing_ok=True)
    if not jpg.exists():
        await _run([ffmpeg_bin(), "-y", "-ss", "1", "-i", str(mp4), "-frames:v", "1", "-q:v", "3", str(jpg)], env)
    base = settings.site_media_url.rstrip("/")
    prefix = f"{base}/" if base else ""
    return {
        "video_file": f"{prefix}video/{mp4.name}",
        "poster": f"{prefix}video/{jpg.name}" if jpg.exists() else None,
    }


async def write_articles(session: Session, env: dict[str, str]) -> int:
    items = []
    for article in session.scalars(select(Article).order_by(Article.id)):
        item = as_dict(article)
        video = session.get(Video, article.video_id)
        media = await _media_for(video, article.slug, env) if video and settings.site_own_video else None
        if media:
            item.update(media)
        items.append(item)
    data = json.dumps({"articles": items}, ensure_ascii=False, indent=2)
    # Отдельный файл, которого нет в git: примеры в articles.json не трогаем.
    target = settings.site_dir / "src" / "data" / "articles.bot.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(data, encoding="utf-8")
    os.replace(tmp, target)
    return len(items)


async def build_and_deploy(session: Session, deploy: bool = True) -> SiteResult:
    """Обновляет статьи, собирает сайт и (если настроено) выкладывает его."""
    if not (settings.site_dir / "package.json").exists():
        return SiteResult(False, f"Папка сайта не найдена: {settings.site_dir}")
    npm = shutil.which("npm")
    if not npm:
        return SiteResult(False, "Не найден npm. Установите Node.js 22 (nodejs.org) и перезапустите бота.")

    async with _lock:
        env = dict(os.environ)
        if settings.site_url:
            env["SITE_URL"] = settings.site_url
        if settings.indexnow_key:
            env["INDEXNOW_KEY"] = settings.indexnow_key
        count = await write_articles(session, env)

        if not (settings.site_dir / "node_modules").exists():
            code, out = await _run([npm, "ci"], env)
            if code:
                return SiteResult(False, "Не удалось установить зависимости сайта:\n" + _tail(out))

        code, out = await _run([npm, "run", "build"], env)
        if code:
            return SiteResult(False, "Сборка сайта не удалась:\n" + _tail(out))

        dist = settings.site_dir / "dist"
        msg = f"Сайт собран: статей {count}. Папка: {dist}"
        if deploy and settings.site_deploy_cmd:
            env["SITE_DIST"] = str(dist)
            code, out = await _run(settings.site_deploy_cmd, env, shell=True)
            if code:
                return SiteResult(False, msg + "\nВыкладка не удалась:\n" + _tail(out))
            msg += "\nВыложен на хостинг."
            pinged = await ping_indexnow(session)
            if pinged:
                msg += f"\nЯндекс уведомлён о страницах: {pinged}."
        elif deploy:
            msg += "\nКоманда выкладки (SITE_DEPLOY_CMD) не задана — загрузите папку dist на хостинг сами."
        return SiteResult(True, msg)


async def ping_indexnow(session: Session) -> int:
    """Сообщает Яндексу (IndexNow) о страницах, изменившихся с прошлой выкладки."""
    if not (settings.indexnow_key and settings.site_url):
        return 0
    state = settings.site_dir / ".indexnow-state"
    last = float(state.read_text()) if state.exists() else 0.0
    site = settings.site_url.rstrip("/")
    urls = [
        f"{site}/{a.slug}/"
        for a in session.scalars(select(Article))
        # updated_at хранится в UTC без часового пояса
        if a.updated_at and a.updated_at.replace(tzinfo=timezone.utc).timestamp() > last
    ]
    if not urls:
        return 0
    urls += [f"{site}/", f"{site}/voprosy/", f"{site}/izmeneniya/"]
    host = site.split("://", 1)[-1].split("/", 1)[0]
    payload = {"host": host, "key": settings.indexnow_key, "keyLocation": f"{site}/indexnow.txt", "urlList": urls[:10000]}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post("https://yandex.com/indexnow", json=payload)
        if r.status_code >= 300:
            log.warning("IndexNow %s: %s", r.status_code, r.text[:300])
            return 0
    except httpx.HTTPError as e:
        log.warning("IndexNow failed: %s", e)
        return 0
    state.write_text(str(time.time()))
    return len(urls)


async def auto_update(session: Session) -> SiteResult | None:
    """Вызывается после изменения статьи. Ничего не делает, если SITE_AUTO_BUILD выключен."""
    if not settings.site_auto_build:
        return None
    try:
        return await build_and_deploy(session)
    except Exception as e:  # сайт не должен ломать работу бота
        log.exception("site auto update failed")
        return SiteResult(False, f"Не удалось обновить сайт: {e}")
