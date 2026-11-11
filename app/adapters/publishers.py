from __future__ import annotations

from pathlib import Path
from typing import Protocol

import httpx
from telegram import Bot

from app.config import settings


class Publisher(Protocol):
    name: str

    async def publish(self, video_path: Path, caption: str, hashtags: str) -> str: ...


class TelegramPublisher:
    name = "telegram"

    def __init__(self, bot: Bot):
        self.bot = bot

    async def publish(self, video_path: Path, caption: str, hashtags: str) -> str:
        if not settings.telegram_channel_id:
            raise RuntimeError("Не задан TELEGRAM_CHANNEL_ID")
        text = f"{caption}\n\n{hashtags}".strip()
        with video_path.open("rb") as f:
            msg = await self.bot.send_video(
                chat_id=settings.telegram_channel_id,
                video=f,
                caption=text[:1024] or None,
                supports_streaming=True,
                has_spoiler=False,
            )
        return f"https://t.me/c/{str(settings.telegram_channel_id).lstrip('-100')}/{msg.message_id}"


class VKPublisher:
    name = "vk"

    async def publish(self, video_path: Path, caption: str, hashtags: str) -> str:
        if not settings.vk_access_token or not settings.vk_group_id:
            raise RuntimeError("VK не настроен: нужны VK_ACCESS_TOKEN и VK_GROUP_ID")
        text = f"{caption}\n{hashtags}".strip()
        async with httpx.AsyncClient(timeout=180) as client:
            r = await client.get(
                "https://api.vk.com/method/video.save",
                params={
                    "access_token": settings.vk_access_token,
                    "v": settings.vk_api_version,
                    "group_id": settings.vk_group_id,
                    "name": caption[:128] or "Смотри глубже",
                    "description": text,
                    "wallpost": 1,
                },
            )
            data = r.json()
            if "error" in data:
                raise RuntimeError(data["error"].get("error_msg", str(data["error"])))
            upload_url = data["response"]["upload_url"]
            with video_path.open("rb") as f:
                up = await client.post(upload_url, files={"video_file": f})
                up.raise_for_status()
            resp = data["response"]
            return f"https://vk.com/video-{settings.vk_group_id}_{resp.get('video_id', '')}"


class YouTubePublisher:
    name = "youtube"

    async def publish(self, video_path: Path, caption: str, hashtags: str) -> str:
        raise RuntimeError("YouTube Shorts: положите client secrets и завершите OAuth (этап 5 БТ)")


def get_publishers(bot: Bot) -> list[Publisher]:
    pubs: list[Publisher] = [TelegramPublisher(bot)]
    if settings.vk_access_token:
        pubs.append(VKPublisher())
    if settings.youtube_client_secrets:
        pubs.append(YouTubePublisher())
    return pubs
