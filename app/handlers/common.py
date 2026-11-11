from __future__ import annotations

from telegram import Message
from telegram.ext import ContextTypes

from app.db import SessionLocal
from app.keyboards import card_kb, discussion_kb, fact_kb
from app.cards import card_text
from app.models import UserState, Video


def session():
    return SessionLocal()


def state_of(user_id: int) -> UserState:
    db = SessionLocal()
    try:
        st = db.get(UserState, user_id)
        if not st:
            st = UserState(user_id=user_id)
            db.add(st)
            db.commit()
            db.refresh(st)
        return st
    finally:
        db.close()


def set_await(user_id: int, kind: str, video_id: int | None = None, extra: str = "") -> None:
    db = SessionLocal()
    try:
        st = db.get(UserState, user_id)
        if not st:
            st = UserState(user_id=user_id)
            db.add(st)
        st.awaiting = kind
        if video_id is not None:
            st.video_id = video_id
        st.extra = extra
        db.commit()
    finally:
        db.close()


async def send_card(message: Message, video: Video, context: ContextTypes.DEFAULT_TYPE | None = None) -> None:
    db = SessionLocal()
    try:
        v = db.get(Video, video.id)
        if not v:
            return
        _ = v.scene
        _ = v.scripts
        _ = v.shots
        _ = v.discussion
        for link in v.fact_links:
            _ = link.fact
        text = card_text(v)
        kb = card_kb(v)
        sent = await message.reply_text(text[:3900], reply_markup=kb)
        v.card_chat_id = sent.chat_id
        v.card_message_id = sent.message_id
        db.commit()
    finally:
        db.close()


async def send_discussion(message: Message, video_id: int, stage: str, text: str) -> None:
    """Ответ ИИ-сценариста: длинный текст режется на части, кнопки — под последней."""
    text = text or "…"
    chunks = [text[i : i + 3900] for i in range(0, len(text), 3900)]
    for i, chunk in enumerate(chunks):
        last = i == len(chunks) - 1
        await message.reply_text(chunk, reply_markup=discussion_kb(video_id, stage) if last else None)


FACT_STATUS = {"pending": "ждёт проверки", "confirmed": "проверен", "outdated": "устарел"}


def fact_text(link) -> str:
    fact = link.fact
    if link.state == "removed":
        status = "убран из ролика"
    else:
        status = FACT_STATUS.get(fact.status, fact.status)
        if fact.status == "confirmed" and fact.checked_at:
            status += f" {fact.checked_at:%d.%m.%Y}"
    lines = [f"Факт: {fact.text}", f"Источник: {fact.source or 'не указан'}", f"Статус: {status}"]
    if link.original and link.original != fact.text:
        lines.append(f"В сценарии сейчас: {link.original}")
    return "\n".join(lines)


async def send_facts(message: Message, video: Video, only_pending: bool = False) -> None:
    """Каждый факт — отдельным сообщением с кнопками. Уже проверенные факты из базы — одним списком."""
    links = [l for l in video.fact_links if l.state == "active"]
    known = [l for l in links if l.fact.status == "confirmed" and l.applied and l.original == l.fact.text]
    todo = [l for l in links if l not in known] if only_pending else [l for l in video.fact_links if l not in known]
    if not links and not todo:
        await message.reply_text("Фактов в сценарии не найдено. Можно добавить свой или идти дальше.")
        return
    if known:
        await message.reply_text(
            "Уже проверены раньше (взяты из базы):\n"
            + "\n".join(f"• {l.fact.text} — {l.fact.checked_at:%d.%m.%Y}" for l in known if l.fact.checked_at)
        )
    for l in todo:
        await message.reply_text(fact_text(l), reply_markup=fact_kb(l.id))


async def refresh_card(context: ContextTypes.DEFAULT_TYPE, video: Video) -> None:
    if not video.card_chat_id or not video.card_message_id:
        return
    try:
        await context.bot.edit_message_text(
            chat_id=video.card_chat_id,
            message_id=video.card_message_id,
            text=card_text(video)[:3900],
            reply_markup=card_kb(video),
        )
    except Exception:
        pass
