from __future__ import annotations

import json
import re
from typing import Protocol

import httpx

from app.config import settings


class LLMAdapter(Protocol):
    async def complete(self, system: str, user: str) -> str: ...

    async def chat(self, system: str, messages: list[dict]) -> str: ...


class StubLLM:
    async def complete(self, system: str, user: str) -> str:
        if "РАСКАДРОВКА" in system or "storyboard" in user.lower() or "раскадровку" in user.lower():
            return self._storyboard(user)
        if "ПРОМПТ" in system:
            return json.dumps({"prompts": []}, ensure_ascii=False)
        topic = _extract(user, "Тема") or _extract(user, "Сцена") or "вычет"
        return (
            f"Вы столкнулись с вопросом: {topic.lower()}. "
            "Многие не знают, что здесь есть важная деталь, и теряют деньги. "
            "Что сделать: проверьте условия, соберите документы и подайте заявление. "
            "Срок и статус можно посмотреть на Госуслугах. "
            "Все ответы — на сайте «По полочкам»."
        )

    async def chat(self, system: str, messages: list[dict]) -> str:
        last = messages[-1]["content"] if messages else ""
        if "JSON" in last:
            return self._storyboard(last)
        if "итоговый сценарий" in last.lower():
            return await self.complete(system, last)
        if "Начни обсуждение раскадровки" in last:
            return "(заглушка ИИ-сценариста) Обсудим визуальный ряд: какой стиль картинок и где показать цифры?"
        if "Начни обсуждение" in last:
            return (
                "(заглушка ИИ-сценариста) Давайте обсудим ролик. "
                "Для кого он, какую структуру выберем и какие факты обязательно назвать?"
            )
        return f"(заглушка ИИ-сценариста) Принято: «{last[:200]}». Что ещё уточним?"

    def _storyboard(self, user: str) -> str:
        script = user
        words = re.findall(r"[А-Яа-яA-Za-zЁё]+", script)
        total = max(42.0, min(55.0, len(words) / 2.4))
        shots = [
            {"ord": 1, "start": 0, "end": 3, "type": "text", "voice": "", "description": "Вопрос ролика", "effect": "none"},
            {"ord": 2, "start": 3, "end": round(total * 0.35, 1), "type": "image", "voice": " ".join(words[:40]), "description": "Человек за столом с документами и телефоном.", "effect": "zoom_in"},
            {"ord": 3, "start": round(total * 0.35, 1), "end": round(total * 0.7, 1), "type": "video", "voice": " ".join(words[40:80]), "description": "Ключевая сцена темы, люди со спины, светлый интерьер.", "effect": "none"},
            {"ord": 4, "start": round(total * 0.7, 1), "end": round(total - 4, 1), "type": "image", "voice": " ".join(words[80:]), "description": "Документы на столе, рядом телефон с открытым приложением.", "effect": "pan"},
            {"ord": 5, "start": round(total - 4, 1), "end": total, "type": "text", "voice": "Все ответы — на сайте «По полочкам».", "description": "Все ответы — на сайте «По полочкам»", "effect": "none"},
        ]
        return json.dumps({"shots": shots}, ensure_ascii=False, indent=2)


class OpenAILLM:
    """Любой OpenAI-совместимый шлюз: OpenAI, OpenRouter, GigaChat-прокси, локальная модель."""

    def __init__(self, api_key: str, base_url: str, model: str, temperature: float = 0.7):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature

    async def complete(self, system: str, user: str) -> str:
        return await self.chat(system, [{"role": "user", "content": user}])

    async def chat(self, system: str, messages: list[dict]) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "temperature": self.temperature,
        }
        async with httpx.AsyncClient(timeout=180) as client:
            r = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
        return data["choices"][0]["message"]["content"]


def _extract(text: str, label: str) -> str:
    m = re.search(rf"{label}:\s*(.+)", text)
    return m.group(1).strip() if m else ""


def get_llm_adapter() -> LLMAdapter:
    if settings.llm_provider == "openai" and settings.llm_api_key:
        return OpenAILLM(settings.llm_api_key, settings.llm_base_url, settings.llm_model)
    return StubLLM()


def get_writer_adapter() -> LLMAdapter:
    """ИИ-сценарист. Если WRITER_* не заданы, используется основная модель (LLM_*)."""
    provider = settings.writer_provider or settings.llm_provider
    api_key = settings.writer_api_key or settings.llm_api_key
    if provider == "openai" and api_key:
        return OpenAILLM(
            api_key,
            settings.writer_base_url or settings.llm_base_url,
            settings.writer_model or settings.llm_model,
            settings.writer_temperature,
        )
    return StubLLM()
