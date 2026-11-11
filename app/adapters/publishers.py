from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Protocol

import httpx
from telegram import Bot

from app.config import settings


class ManualPublish(Exception):
    """Площадка без API: бот отправил автору файл и текст, загрузить нужно вручную."""


class Publisher(Protocol):
    name: str

    async def publish(self, video_path: Path, title: str, description: str, hashtags: str) -> str: ...


def _text(description: str, hashtags: str) -> str:
    return f"{description}\n\n{hashtags}".strip()


class TelegramPublisher:
    name = "telegram"

    def __init__(self, bot: Bot):
        self.bot = bot

    async def publish(self, video_path: Path, title: str, description: str, hashtags: str) -> str:
        if not settings.telegram_channel_id:
            raise RuntimeError("Не задан TELEGRAM_CHANNEL_ID")
        with video_path.open("rb") as f:
            msg = await self.bot.send_video(
                chat_id=settings.telegram_channel_id,
                video=f,
                caption=_text(description, hashtags)[:1024] or None,
                supports_streaming=True,
            )
        chat = str(settings.telegram_channel_id)
        if chat.startswith("@"):
            return f"https://t.me/{chat[1:]}/{msg.message_id}"
        if chat.startswith("-100"):
            chat = chat[len("-100") :]
        return f"https://t.me/c/{chat}/{msg.message_id}"


class VKPublisher:
    name = "vk"

    async def publish(self, video_path: Path, title: str, description: str, hashtags: str) -> str:
        if not settings.vk_access_token or not settings.vk_group_id:
            raise RuntimeError("VK не настроен: нужны VK_ACCESS_TOKEN и VK_GROUP_ID")
        async with httpx.AsyncClient(timeout=300) as client:
            r = await client.get(
                "https://api.vk.com/method/video.save",
                params={
                    "access_token": settings.vk_access_token,
                    "v": settings.vk_api_version,
                    "group_id": settings.vk_group_id,
                    "name": title[:128] or "По полочкам",
                    "description": _text(description, hashtags),
                    "wallpost": 1,
                },
            )
            data = r.json()
            if "error" in data:
                raise RuntimeError(data["error"].get("error_msg", str(data["error"])))
            resp = data["response"]
            with video_path.open("rb") as f:
                up = await client.post(resp["upload_url"], files={"video_file": f})
                up.raise_for_status()
            return f"https://vk.com/video-{settings.vk_group_id}_{resp.get('video_id', '')}"


class YouTubePublisher:
    """YouTube Shorts через YouTube Data API v3. Вертикальное видео до 60 с YouTube сам считает Shorts.

    Нужны YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET и YOUTUBE_REFRESH_TOKEN
    (refresh token выдаёт скрипт scripts/youtube_auth.py, один раз).
    """

    name = "youtube"

    async def _access_token(self, client: httpx.AsyncClient) -> str:
        r = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": settings.youtube_client_id,
                "client_secret": settings.youtube_client_secret,
                "refresh_token": settings.youtube_refresh_token,
                "grant_type": "refresh_token",
            },
        )
        if r.status_code >= 400:
            raise RuntimeError(f"YouTube: не удалось обновить доступ ({r.text[:300]}). Запустите scripts/youtube_auth.py заново.")
        return r.json()["access_token"]

    async def publish(self, video_path: Path, title: str, description: str, hashtags: str) -> str:
        async with httpx.AsyncClient(timeout=600) as client:
            token = await self._access_token(client)
            meta = {
                "snippet": {
                    "title": f"{title[:90]} #shorts".strip(),
                    "description": _text(description, hashtags)[:4900],
                    "categoryId": "27",  # Образование
                    "defaultLanguage": "ru",
                },
                "status": {
                    "privacyStatus": settings.youtube_privacy,
                    "selfDeclaredMadeForKids": False,
                    "containsSyntheticMedia": True,  # пометка ИИ-контента
                },
            }
            size = video_path.stat().st_size
            start = await client.post(
                "https://www.googleapis.com/upload/youtube/v3/videos",
                params={"uploadType": "resumable", "part": "snippet,status"},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json; charset=UTF-8",
                    "X-Upload-Content-Type": "video/mp4",
                    "X-Upload-Content-Length": str(size),
                },
                content=json.dumps(meta, ensure_ascii=False).encode("utf-8"),
            )
            if start.status_code >= 400:
                raise RuntimeError(f"YouTube: {start.text[:500]}")
            upload_url = start.headers["Location"]
            up = await client.put(
                upload_url,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "video/mp4"},
                content=video_path.read_bytes(),
            )
            if up.status_code >= 400:
                raise RuntimeError(f"YouTube: {up.text[:500]}")
            return f"https://youtube.com/shorts/{up.json()['id']}"


class OKPublisher:
    """Одноклассники через API OK: загрузка видео в группу и пост в ленте группы.

    Нужны OK_APP_KEY (публичный ключ приложения), OK_APP_SECRET (секретный ключ),
    OK_ACCESS_TOKEN (вечный токен из настроек приложения) и OK_GROUP_ID.
    Права приложения: VIDEO_CONTENT, VALUABLE_ACCESS, GROUP_CONTENT.
    """

    name = "ok"
    api = "https://api.ok.ru/fb.do"

    def _signed(self, method: str, params: dict) -> dict:
        p = {"application_key": settings.ok_app_key, "format": "json", "method": method, **params}
        secret = hashlib.md5((settings.ok_access_token + settings.ok_app_secret).encode()).hexdigest()
        base = "".join(f"{k}={p[k]}" for k in sorted(p))
        p["sig"] = hashlib.md5((base + secret).encode("utf-8")).hexdigest()
        p["access_token"] = settings.ok_access_token
        return p

    async def _call(self, client: httpx.AsyncClient, method: str, **params) -> object:
        r = await client.post(self.api, data=self._signed(method, {k: str(v) for k, v in params.items()}))
        data = r.json() if r.content else None
        if isinstance(data, dict) and data.get("error_code"):
            raise RuntimeError(f"OK {method}: {data.get('error_msg') or data}")
        return data

    async def publish(self, video_path: Path, title: str, description: str, hashtags: str) -> str:
        if not (settings.ok_app_key and settings.ok_app_secret and settings.ok_access_token and settings.ok_group_id):
            raise RuntimeError("OK не настроен: нужны OK_APP_KEY, OK_APP_SECRET, OK_ACCESS_TOKEN, OK_GROUP_ID")
        gid = settings.ok_group_id
        async with httpx.AsyncClient(timeout=600) as client:
            up = await self._call(
                client,
                "video.getUploadUrl",
                gid=gid,
                file_name=video_path.name,
                file_size=video_path.stat().st_size,
                post_form="true",
            )
            vid = up["video_id"]
            with video_path.open("rb") as f:
                r = await client.post(up["upload_url"], files={"data": (video_path.name, f, "video/mp4")})
                r.raise_for_status()
            await self._call(client, "video.update", vid=vid, title=title[:200], description=_text(description, hashtags)[:3000])
            attachment = {
                "media": [
                    {"type": "text", "text": _text(description, hashtags)[:3000]},
                    {"type": "movie", "list": [{"id": str(vid)}]},
                ]
            }
            await self._call(
                client,
                "mediatopic.post",
                gid=gid,
                type="GROUP_THEME",
                attachment=json.dumps(attachment, ensure_ascii=False, separators=(",", ":")),
            )
        return f"https://ok.ru/video/{vid}"


class InstagramPublisher:
    """Instagram Reels через Instagram Graph API (аккаунт «Автор» или «Бизнес», связанный со страницей Facebook).

    Нужны INSTAGRAM_USER_ID и INSTAGRAM_ACCESS_TOKEN (долгоживущий токен с правом instagram_content_publish).
    Видео загружается напрямую (resumable upload), отдельный хостинг не нужен.
    """

    name = "instagram"
    graph = "https://graph.facebook.com/v21.0"

    async def publish(self, video_path: Path, title: str, description: str, hashtags: str) -> str:
        import asyncio

        token = settings.instagram_access_token
        uid = settings.instagram_user_id
        caption = _text(description, hashtags)[:2200]
        async with httpx.AsyncClient(timeout=600) as client:
            r = await client.post(
                f"{self.graph}/{uid}/media",
                data={"media_type": "REELS", "upload_type": "resumable", "caption": caption, "share_to_feed": "true", "access_token": token},
            )
            data = r.json()
            if "error" in data:
                raise RuntimeError(f"Instagram: {data['error'].get('message', data['error'])}")
            container = data["id"]
            upload_uri = data.get("uri") or f"https://rupload.facebook.com/ig-api-upload/v21.0/{container}"
            body = video_path.read_bytes()
            up = await client.post(
                upload_uri,
                headers={"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(len(body))},
                content=body,
            )
            if up.status_code >= 400:
                raise RuntimeError(f"Instagram загрузка: {up.text[:300]}")
            for _ in range(60):  # до 5 минут ждём обработку
                st = (await client.get(f"{self.graph}/{container}", params={"fields": "status_code,status", "access_token": token})).json()
                code = st.get("status_code")
                if code == "FINISHED":
                    break
                if code == "ERROR":
                    raise RuntimeError(f"Instagram не принял видео: {st.get('status')}")
                await asyncio.sleep(5)
            else:
                raise RuntimeError("Instagram слишком долго обрабатывает видео")
            pub = (await client.post(f"{self.graph}/{uid}/media_publish", data={"creation_id": container, "access_token": token})).json()
            if "error" in pub:
                raise RuntimeError(f"Instagram: {pub['error'].get('message', pub['error'])}")
            link = (await client.get(f"{self.graph}/{pub['id']}", params={"fields": "permalink", "access_token": token})).json()
            return link.get("permalink") or f"instagram media {pub['id']}"


class ManualPublisher:
    """Площадка без API (или пока без ключей): бот присылает автору файл и готовый текст для ручной загрузки."""

    def __init__(self, bot: Bot, name: str, label: str, hint: str):
        self.bot = bot
        self.name = name
        self.label = label
        self.hint = hint

    async def publish(self, video_path: Path, title: str, description: str, hashtags: str) -> str:
        if not settings.telegram_owner_id:
            raise RuntimeError(f"Не задан TELEGRAM_OWNER_ID — некому отправить файл для {self.label}")
        with video_path.open("rb") as f:
            await self.bot.send_document(
                chat_id=settings.telegram_owner_id,
                document=f,
                filename=f"{title[:60] or 'rolik'}.mp4",
                caption=f"Для {self.label}: {self.hint} Текст — следующим сообщением."[:1024],
            )
        await self.bot.send_message(
            settings.telegram_owner_id,
            f"Текст для {self.label}\n\nНазвание:\n{title[:100]}\n\nОписание:\n{_text(description, hashtags)}"[:4000],
        )
        raise ManualPublish(f"Файл и текст для {self.label} отправлены вам в бот — загрузите вручную.")


def get_publishers(bot: Bot) -> list[Publisher]:
    pubs: list[Publisher] = []
    if settings.telegram_channel_id:
        pubs.append(TelegramPublisher(bot))
    if settings.vk_access_token:
        pubs.append(VKPublisher())
    if settings.youtube_refresh_token:
        pubs.append(YouTubePublisher())
    if settings.ok_access_token:
        pubs.append(OKPublisher())
    if settings.instagram_access_token and settings.instagram_user_id:
        pubs.append(InstagramPublisher())
    elif settings.instagram_manual:
        pubs.append(ManualPublisher(bot, "instagram", "Instagram", "загрузите как Reels в приложении Instagram."))
    if settings.dzen_manual:
        # Открытого API для загрузки видео в Дзен нет.
        pubs.append(ManualPublisher(bot, "dzen", "Дзена", "загрузите в Дзен Студии как ролик (можно отложенно)."))
    return pubs
