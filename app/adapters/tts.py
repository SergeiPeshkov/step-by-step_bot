from __future__ import annotations

import math
import struct
import wave
from pathlib import Path
from typing import Protocol

import httpx

from app.config import settings


class TTSAdapter(Protocol):
    async def speak(self, text: str, dest: Path, markup: str = "") -> tuple[Path, float]: ...


class StubTTS:
    async def speak(self, text: str, dest: Path, markup: str = "") -> tuple[Path, float]:
        dest.parent.mkdir(parents=True, exist_ok=True)
        words = max(1, len(text.split()))
        duration = max(1.2, words / 2.3)
        rate = 24000
        n = int(rate * duration)
        dest_wav = dest.with_suffix(".wav")
        with wave.open(str(dest_wav), "w") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            frames = bytearray()
            for i in range(n):
                t = i / rate
                env = min(1.0, t * 8) * min(1.0, (duration - t) * 8)
                val = int(700 * env * math.sin(2 * math.pi * 180 * t))
                frames += struct.pack("<h", val)
            w.writeframes(frames)
        return dest_wav, 0.0


class YandexTTS:
    async def speak(self, text: str, dest: Path, markup: str = "") -> tuple[Path, float]:
        dest.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "text": markup or text,
            "lang": "ru-RU",
            "voice": settings.tts_voice,
            "folderId": settings.yandex_folder_id,
            "format": "mp3",
        }
        headers = {"Authorization": f"Api-Key {settings.tts_api_key}"}
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post("https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize", headers=headers, data=payload)
            r.raise_for_status()
            dest.write_bytes(r.content)
        return dest, round(0.02 * max(1, len(text.split())), 2)


def get_tts_adapter() -> TTSAdapter:
    if settings.tts_provider == "yandex" and settings.tts_api_key:
        return YandexTTS()
    return StubTTS()
