"""Статьи для сайта.

По утверждённому сценарию и проверенным фактам ИИ пишет статью простым текстом. Источники и ссылки на ролик
бот добавляет сам из базы фактов и публикаций, поэтому ИИ не может выдумать ссылку. Форматирование делает сайт.
"""

from __future__ import annotations

import json
import re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.llm import get_writer_adapter
from app.models import Article, Video
from app.services.facts import active_links, actual_date
from app.services.pipeline import approved_script, audit, latest_script

PLATFORM_LABEL = {
    "telegram": "Telegram",
    "vk": "VK",
    "youtube": "YouTube",
    "ok": "Одноклассники",
    "instagram": "Instagram",
    "dzen": "Дзен",
}

SYSTEM = (
    "Ты пишешь статьи для сайта «По полочкам»: законы и правила простыми словами. "
    "Статья сопровождает короткий ролик на ту же тему и раскрывает её подробнее.\n"
    "Правила:\n"
    "- Цифры, суммы, даты, сроки и условия бери только из списка проверенных фактов. "
    "Других цифр и дат не добавляй. Если чего-то нет в фактах, не утверждай этого.\n"
    "- Объясняй, а не советуй. Без названий банков, без оценок «выгодно».\n"
    "- Простые слова, короткие абзацы, обращение на «вы».\n"
    "- Только простой текст без разметки: без #, *, списков с символами и ссылок. "
    "Абзацы разделяй пустой строкой. Подзаголовок — отдельная короткая строка.\n"
    "- Обычно 300–700 слов.\n"
    "- Не пиши заголовок статьи, раздел источников, ссылки и дату актуальности — их добавит система.\n"
    "Ответ — только текст статьи."
)

_TRANSLIT = dict(
    zip(
        "абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
        ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t",
         "u", "f", "kh", "ts", "ch", "sh", "shch", "", "y", "", "e", "yu", "ya"],
    )
)


def slugify(title: str) -> str:
    text = "".join(_TRANSLIT.get(ch, ch) for ch in title.lower())
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:120] or "statya"


def _plain(text: str) -> str:
    """Убирает остатки markdown, если модель всё же их добавила."""
    text = re.sub(r"^\s*#{1,6}\s*", "", text, flags=re.M)
    text = re.sub(r"\*\*|__|`", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _title(video: Video) -> str:
    return (video.custom_topic or (video.scene.scene if video.scene else f"Ролик {video.id}")).strip()


def _sources(video: Video) -> list[dict]:
    seen, out = set(), []
    for link in active_links(video):
        fact = link.fact
        if fact.status != "confirmed" or fact.id in seen:
            continue
        seen.add(fact.id)
        out.append({"fact": fact.text, "source": fact.source})
    return out


def _videos(video: Video) -> list[dict]:
    return [
        {"platform": p.platform, "url": p.post_url}
        for p in video.publications
        if p.status == "published" and p.post_url
    ]


async def generate(session: Session, video: Video) -> Article:
    script = approved_script(video) or latest_script(video)
    if not script:
        raise RuntimeError("Нет сценария — статью писать не из чего")
    sources = _sources(video)
    facts_txt = "\n".join(f"- {s['fact']}" for s in sources) or "(проверенных фактов нет — не называй конкретных цифр и дат)"
    user = f"Тема: {_title(video)}\n\nПроверенные факты:\n{facts_txt}\n\nСценарий ролика:\n{script.text}"
    body = (await get_writer_adapter().complete(SYSTEM, user)).strip()
    body = _plain(body)

    article = session.scalar(select(Article).where(Article.video_id == video.id))
    title = _title(video)
    if article is None:
        article = Article(video_id=video.id, title=title, slug=slugify(title), body=body)
        session.add(article)
    article.title = title
    article.body = body
    article.sources_json = json.dumps(sources, ensure_ascii=False)
    article.videos_json = json.dumps(_videos(video), ensure_ascii=False)
    article.actual_date = actual_date(video)
    article.updated_at = datetime.utcnow()
    audit(session, video, "article")
    session.commit()
    session.refresh(article)
    return article


def refresh_links(session: Session, video: Video, article: Article) -> None:
    """Ссылки на ролик появляются после публикации — обновляем их без переписывания текста."""
    article.videos_json = json.dumps(_videos(video), ensure_ascii=False)
    session.commit()


def as_text(article: Article) -> str:
    """Статья простым текстом: заголовок, текст, ролик, источники, дата."""
    parts = [article.title, article.body]
    videos = json.loads(article.videos_json or "[]")
    if videos:
        parts.append("Смотреть ролик:\n" + "\n".join(f"{PLATFORM_LABEL.get(v['platform'], v['platform'])}: {v['url']}" for v in videos))
    sources = json.loads(article.sources_json or "[]")
    if sources:
        parts.append("Источники:\n" + "\n".join(f"{s['fact']} — {s['source'] or 'источник не указан'}" for s in sources))
    tail = []
    if article.actual_date:
        tail.append(f"Актуально на {article.actual_date:%d.%m.%Y}.")
    tail.append("Материал носит справочный характер и не является юридической консультацией.")
    parts.append(" ".join(tail))
    return "\n\n".join(p.strip() for p in parts if p and p.strip()) + "\n"


def as_dict(article: Article) -> dict:
    return {
        "id": article.id,
        "video_id": article.video_id,
        "title": article.title,
        "slug": article.slug,
        "body": article.body,
        "videos": json.loads(article.videos_json or "[]"),
        "sources": json.loads(article.sources_json or "[]"),
        "actual_date": article.actual_date.isoformat() if article.actual_date else None,
        "updated_at": article.updated_at.isoformat() if article.updated_at else None,
    }


def missing_sources(article: Article) -> int:
    return sum(1 for s in json.loads(article.sources_json or "[]") if not s.get("source"))


def export_all(session: Session) -> str:
    items = [as_dict(a) for a in session.scalars(select(Article).order_by(Article.id))]
    return json.dumps({"articles": items}, ensure_ascii=False, indent=2)
