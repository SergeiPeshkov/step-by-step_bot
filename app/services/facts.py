"""Этап «Факты».

После утверждения сценария ИИ выписывает из него все проверяемые утверждения: цифры, суммы, даты, сроки,
условия. Уже проверенные факты из базы используются повторно. Автор по каждому новому факту решает:
верно, исправить, убрать, указать источник. Пока есть непроверенные факты, ролик дальше не идёт.
Исправления и удаления потом вносятся в сценарий. Дата проверки фактов даёт плашку «Актуально на …».
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.llm import get_writer_adapter
from app.enums import VideoStatus
from app.models import Fact, ScriptVersion, Video, VideoFact
from app.services.pipeline import _extract_json, approved_script, audit, latest_script

KNOWN_LIMIT = 150

EXTRACT_SYSTEM = (
    "ФАКТЫ. Ты помогаешь проверять факты для коротких роликов о законах «По полочкам».\n"
    "Выпиши из сценария все проверяемые утверждения: цифры, суммы, проценты, даты, сроки, возрастные и "
    "другие условия, названия законов и ведомств, если от них зависит смысл. Одно утверждение — один факт, "
    "сформулированный коротко и самостоятельно (понятно без сценария). Общие слова без проверяемого "
    "содержания не выписывай.\n"
    "Если факт уже есть в базе проверенных фактов (тот же смысл и те же цифры), верни только его id. "
    "Иначе верни text и source — где это проверить (закон с номером и статьёй или официальный сайт). "
    "Если источник не знаешь, оставь source пустым — не выдумывай.\n"
    'Ответ — только JSON без markdown: {"facts": [{"id": 12} или {"text": "...", "source": "..."}]}'
)


def _script(video: Video) -> ScriptVersion | None:
    return approved_script(video) or latest_script(video)


def active_links(video: Video) -> list[VideoFact]:
    return [l for l in video.fact_links if l.state == "active"]


def pending_links(video: Video) -> list[VideoFact]:
    return [l for l in active_links(video) if l.fact.status == "pending"]


def summary(video: Video) -> dict:
    active = active_links(video)
    return {
        "total": len(active),
        "confirmed": sum(1 for l in active if l.fact.status == "confirmed"),
        "pending": sum(1 for l in active if l.fact.status == "pending"),
        "removed": sum(1 for l in video.fact_links if l.state == "removed"),
    }


def actual_date(video: Video) -> date | None:
    """Дата для плашки «Актуально на …»: самая ранняя проверка среди фактов ролика."""
    dates = [l.fact.checked_at for l in active_links(video) if l.fact.status == "confirmed" and l.fact.checked_at]
    return min(dates) if dates else None


def known_facts(session: Session) -> list[Fact]:
    q = select(Fact).where(Fact.status == "confirmed").order_by(Fact.checked_at.desc(), Fact.id.desc()).limit(KNOWN_LIMIT)
    return list(session.scalars(q))


async def extract(session: Session, video: Video) -> list[VideoFact]:
    script = _script(video)
    if not script:
        raise RuntimeError("Нет сценария")
    known = known_facts(session)
    known_txt = "\n".join(f"id={f.id}: {f.text} (проверено {f.checked_at:%d.%m.%Y})" for f in known if f.checked_at)
    user = f"База проверенных фактов:\n{known_txt or '(пусто)'}\n\nСценарий:\n{script.text}"
    raw = await get_writer_adapter().complete(EXTRACT_SYSTEM, user)
    items = _extract_json(raw).get("facts") or []
    known_by_id = {f.id: f for f in known}

    video.fact_links.clear()
    session.flush()
    seen: set[int] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        fid = item.get("id")
        fact = known_by_id.get(int(fid)) if str(fid or "").isdigit() else None
        if fact is None:
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            fact = Fact(text=text, source=str(item.get("source") or "").strip(), status="pending")
            session.add(fact)
            session.flush()
        if fact.id in seen:
            continue
        seen.add(fact.id)
        session.add(VideoFact(video_id=video.id, fact_id=fact.id, original=fact.text, applied=True))
    video.status = VideoStatus.FACTS
    audit(session, video, "facts_extracted", f"{len(seen)} фактов")
    session.commit()
    session.refresh(video)
    return active_links(video)


def confirm(session: Session, link: VideoFact) -> None:
    if link.state == "removed":
        # Автор передумал убирать факт: возвращаем его в ролик.
        link.state = "active"
        link.applied = bool(link.original) and link.original == link.fact.text
    link.fact.status = "confirmed"
    link.fact.checked_at = date.today()
    session.commit()


def correct(session: Session, link: VideoFact, new_text: str) -> None:
    """Автор исправил факт. Проверенный факт из базы не трогаем: создаём новый, а старый помечаем устаревшим."""
    fact = link.fact
    if fact.status == "confirmed":
        new = Fact(text=new_text, source=fact.source, status="confirmed", checked_at=date.today())
        session.add(new)
        session.flush()
        fact.status = "outdated"
        fact.replaced_by_id = new.id
        link.fact_id = new.id
        link.fact = new
    else:
        fact.text = new_text
        fact.status = "confirmed"
        fact.checked_at = date.today()
    link.applied = False
    session.commit()


def set_source(session: Session, link: VideoFact, source: str) -> None:
    link.fact.source = source
    session.commit()


def remove(session: Session, link: VideoFact) -> None:
    link.state = "removed"
    link.applied = False
    session.commit()


def add(session: Session, video: Video, text: str) -> VideoFact:
    """Автор добавил факт сам: он проверен автором и должен попасть в сценарий."""
    fact = Fact(text=text, status="confirmed", checked_at=date.today())
    session.add(fact)
    session.flush()
    link = VideoFact(video_id=video.id, fact_id=fact.id, original="", applied=False)
    session.add(link)
    session.commit()
    session.refresh(video)
    return link


def script_changes(video: Video) -> list[str]:
    changes = []
    for l in video.fact_links:
        if l.applied:
            continue
        if l.state == "removed":
            changes.append(f"Убрать из сценария утверждение: «{l.original or l.fact.text}».")
        elif not l.original:
            changes.append(f"Добавить в сценарий факт: «{l.fact.text}».")
        elif l.original != l.fact.text:
            changes.append(f"Было: «{l.original}». Должно быть: «{l.fact.text}».")
    return changes


async def apply_to_script(session: Session, video: Video) -> ScriptVersion | None:
    """Вносит в сценарий исправления, удаления и добавления фактов. Остальной текст не меняется."""
    changes = script_changes(video)
    script = _script(video)
    if not changes or not script:
        for l in video.fact_links:
            l.applied = True
        session.commit()
        return None
    system = (
        "Ты редактор сценариев коротких роликов «По полочкам». Внеси в сценарий только перечисленные правки "
        "фактов. Остальной текст, тон и длину сохрани. Ответ — только итоговый текст сценария, без пояснений."
    )
    user = "Правки:\n" + "\n".join(f"- {c}" for c in changes) + f"\n\nСценарий:\n{script.text}"
    text = (await get_writer_adapter().complete(system, user)).strip()
    for s in video.scripts:
        s.approved = False
    ver = ScriptVersion(video_id=video.id, text=text, note="правка по фактам", approved=True)
    session.add(ver)
    for l in video.fact_links:
        l.applied = True
        if l.original:
            l.original = l.fact.text
    audit(session, video, "script_fixed_by_facts", "; ".join(changes)[:2000])
    session.commit()
    session.refresh(video)
    return ver
