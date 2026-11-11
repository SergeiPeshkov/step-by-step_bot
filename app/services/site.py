"""Сборка и выкладка сайта «По полочкам» прямо из бота.

Бот пишет статьи из базы в site/src/data/articles.json, запускает `npm run build`
и, если задана SITE_DEPLOY_CMD, выполняет её (например, rsync или scp папки dist на хостинг).
GitHub для этого не нужен: всё происходит на машине, где работает бот.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config import settings
from app.services.articles import export_all

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


def write_articles(session: Session) -> int:
    data = export_all(session)
    # Отдельный файл, которого нет в git: примеры в articles.json не трогаем.
    target = settings.site_dir / "src" / "data" / "articles.bot.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(data, encoding="utf-8")
    os.replace(tmp, target)
    return data.count('"slug"')


async def build_and_deploy(session: Session, deploy: bool = True) -> SiteResult:
    """Обновляет статьи, собирает сайт и (если настроено) выкладывает его."""
    if not (settings.site_dir / "package.json").exists():
        return SiteResult(False, f"Папка сайта не найдена: {settings.site_dir}")
    npm = shutil.which("npm")
    if not npm:
        return SiteResult(False, "Не найден npm. Установите Node.js 22 (nodejs.org) и перезапустите бота.")

    async with _lock:
        count = write_articles(session)
        env = dict(os.environ)
        if settings.site_url:
            env["SITE_URL"] = settings.site_url

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
        elif deploy:
            msg += "\nКоманда выкладки (SITE_DEPLOY_CMD) не задана — загрузите папку dist на хостинг сами."
        return SiteResult(True, msg)


async def auto_update(session: Session) -> SiteResult | None:
    """Вызывается после изменения статьи. Ничего не делает, если SITE_AUTO_BUILD выключен."""
    if not settings.site_auto_build:
        return None
    try:
        return await build_and_deploy(session)
    except Exception as e:  # сайт не должен ломать работу бота
        log.exception("site auto update failed")
        return SiteResult(False, f"Не удалось обновить сайт: {e}")
