from __future__ import annotations

import json
import re
from typing import Protocol

import httpx

from app.config import settings


class LLMAdapter(Protocol):
    async def complete(self, system: str, user: str) -> str: ...


class StubLLM:
    async def complete(self, system: str, user: str) -> str:
        if "РАСКАДРОВКА" in system or "storyboard" in user.lower() or "раскадровку" in user.lower():
            return self._storyboard(user)
        if "ПРОМПТ" in system:
            return json.dumps({"prompts": []}, ensure_ascii=False)
        topic = _extract(user, "Тема") or _extract(user, "Сцена") or "тишина"
        return (
            f"Ты уже слышал это слово: {topic.lower()}. "
            "Обычно за ним прячется не совет, а старая привычка смотреть мимо себя. "
            "Ищущий поднимает фонарь — и видно не вину, а след. "
            "Так бывает: мы несём чужой голос в свою комнату и думаем, что это мы. "
            "Пауза. В этой паузе можно просто постоять. "
            "Гори, гори ясно, чтобы не погасло."
        )

    def _storyboard(self, user: str) -> str:
        script = user
        words = re.findall(r"[А-Яа-яA-Za-zЁё]+", script)
        total = max(42.0, min(55.0, len(words) / 2.4))
        shots = [
            {"ord": 1, "start": 0, "end": 3, "type": "ritual", "voice": "", "description": "Тьма. Загорается фонарь Ищущего.", "effect": "none"},
            {"ord": 2, "start": 3, "end": round(total * 0.35, 1), "type": "image", "voice": " ".join(words[:40]), "description": "Ищущий на ночной дороге, фонарь освещает путь.", "effect": "zoom_in"},
            {"ord": 3, "start": round(total * 0.35, 1), "end": round(total * 0.7, 1), "type": "video", "voice": " ".join(words[40:80]), "description": "Ключевая сцена темы, герои со спины, холодный свет.", "effect": "none"},
            {"ord": 4, "start": round(total * 0.7, 1), "end": round(total - 4, 1), "type": "image", "voice": " ".join(words[80:]), "description": "Ищущий уходит по дороге, фонарь в руке.", "effect": "pan"},
            {"ord": 5, "start": round(total - 4, 1), "end": total, "type": "black", "voice": "Гори, гори ясно, чтобы не погасло.", "description": "Чёрный кадр, тишина.", "effect": "none"},
        ]
        return json.dumps({"shots": shots}, ensure_ascii=False, indent=2)


class OpenAILLM:
    async def complete(self, system: str, user: str) -> str:
        headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
        payload = {
            "model": settings.llm_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.7,
        }
        async with httpx.AsyncClient(timeout=90) as client:
            r = await client.post(f"{settings.llm_base_url.rstrip('/')}/chat/completions", headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
        return data["choices"][0]["message"]["content"]


def _extract(text: str, label: str) -> str:
    m = re.search(rf"{label}:\s*(.+)", text)
    return m.group(1).strip() if m else ""


def get_llm_adapter() -> LLMAdapter:
    if settings.llm_provider == "openai" and settings.llm_api_key:
        return OpenAILLM()
    return StubLLM()
