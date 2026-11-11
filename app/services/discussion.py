"""Обсуждение ролика с ИИ-сценаристом.

Этап 1 (script): автор и ИИ договариваются о теме, аудитории, структуре (формуле) именно этого ролика,
тоне и фактах. По кнопке ИИ пишет итоговый сценарий.
Этап 2 (visual): с тем же ИИ обсуждаются раскадровка и промпты. По кнопке ИИ возвращает кадры с промптами,
которые затем уходят в генерацию картинок и видео.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.adapters.llm import get_writer_adapter
from app.enums import VideoStatus
from app.models import DiscussionMessage, ScriptVersion, Shot, Video
from app.services.brain import load_block, version_stamp
from app.services.pipeline import _extract_json, approved_script, audit, latest_script, save_shots

SCRIPT = "script"
VISUAL = "visual"

START_SCRIPT = "Начни обсуждение ролика."
START_VISUAL = "Начни обсуждение раскадровки и промптов."

FINAL_SCRIPT = (
    "Напиши итоговый сценарий по всему, о чём мы договорились. "
    "Только текст для озвучки, без заголовков, пометок и пояснений."
)

FINAL_VISUAL = (
    "Сделай итоговую раскадровку с промптами по всему, о чём мы договорились. "
    'Верни только JSON без markdown: {"shots": [...]}. '
    "Поля кадра: ord, start, end (секунды), type (image|video|text|montage|black), "
    "voice (текст голоса на этом кадре, весь сценарий должен быть разбит по кадрам без пропусков), "
    "description (что в кадре, по-русски; для type=text — сам текст на экране), "
    "prompt (промпт для генерации картинки или видео; для text и black — пустая строка), "
    "effect (zoom_in|pan|none). Кадры идут встык, без разрывов и наложений."
)


def _topic(video: Video) -> str:
    if video.custom_topic:
        return video.custom_topic
    if video.scene:
        parts = [video.scene.theme, video.scene.scene, video.scene.under]
        return "\n".join(p for p in parts if p)
    return f"Ролик #{video.id}"


def _system(video: Video, stage: str) -> str:
    common = (
        "Ты — ИИ-сценарист канала «По полочкам»: короткие вертикальные ролики (обычно 40–55 секунд) "
        "о законах и правилах простыми словами. Ты работаешь вместе с автором канала в Telegram.\n\n"
        f"Тема ролика:\n{_topic(video)}\n\n"
        f"## Концепция канала\n{load_block('concept').strip()}\n\n"
        f"## Правила языка\n{load_block('language').strip()}\n\n"
        f"## Как работаем\n{load_block('principle').strip()}\n"
    )
    if stage == SCRIPT:
        exemplars = load_block("exemplars").strip()
        return (
            common
            + (f"\n## Эталоны (брать ритм и простоту, не копировать)\n{exemplars}\n" if exemplars else "")
            + "\n## Сейчас этап 1: сценарий\n"
            "Обсуди с автором ролик: для кого он, главный вопрос, структуру (формулу) именно для этой темы, "
            "тон, какие факты, цифры и даты назвать. Формула для каждого ролика своя — предлагай 2–3 варианта, "
            "если автор её ещё не задал, и следуй той, что выберет автор. Цифры и даты, в которых не уверен, "
            "помечай «проверить». Отвечай коротко, задавай не больше 2–3 вопросов за раз. "
            "Итоговый сценарий целиком не пиши, пока автор не попросит."
        )
    script = approved_script(video) or latest_script(video)
    return (
        common
        + f"\n## Утверждённый сценарий\n{script.text if script else '(нет)'}\n"
        + f"\n## Правила раскадровки\n{load_block('storyboard_rules').strip()}\n"
        + f"\n## Библия стиля\n{load_block('style_bible').strip()}\n"
        + "\n## Сейчас этап 2: раскадровка и промпты\n"
        "Обсуди с автором визуальный ряд: стиль, что показывать на каждом смысловом куске, где текст или "
        "цифры на экране, где нужен видеокадр, а где хватит картинки. Предлагай варианты и по просьбе автора "
        "показывай черновые промпты. Отвечай коротко. Итоговый JSON не выдавай, пока автор не попросит."
    )


def history(video: Video, stage: str) -> list[DiscussionMessage]:
    return [m for m in video.discussion if m.stage == stage]


def _messages(video: Video, stage: str) -> list[dict]:
    return [{"role": m.role, "content": m.text} for m in history(video, stage)]


async def _ask(session: Session, video: Video, stage: str, user_text: str, save_user: bool = True) -> str:
    writer = get_writer_adapter()
    messages = _messages(video, stage) + [{"role": "user", "content": user_text}]
    answer = (await writer.chat(_system(video, stage), messages)).strip()
    if save_user:
        session.add(DiscussionMessage(video_id=video.id, stage=stage, role="user", text=user_text))
    session.add(DiscussionMessage(video_id=video.id, stage=stage, role="assistant", text=answer))
    session.commit()
    session.refresh(video)
    return answer


async def start(session: Session, video: Video, stage: str) -> str:
    """Первое сообщение ИИ на этапе. Если обсуждение уже было, продолжаем его."""
    if stage == VISUAL and video.status != VideoStatus.VISUAL:
        video.status = VideoStatus.VISUAL
        session.commit()
    previous = history(video, stage)
    if previous:
        return "Продолжаем обсуждение: ИИ-сценарист помнит всё, о чём вы говорили. Напишите, что уточнить или поменять."
    prompt = START_SCRIPT if stage == SCRIPT else START_VISUAL
    return await _ask(session, video, stage, prompt)


async def reply(session: Session, video: Video, stage: str, text: str) -> str:
    return await _ask(session, video, stage, text)


async def write_script(session: Session, video: Video) -> ScriptVersion:
    text = await _ask(session, video, SCRIPT, FINAL_SCRIPT)
    ver = ScriptVersion(video_id=video.id, text=text, note="по итогам обсуждения")
    session.add(ver)
    for shot in video.shots:
        shot.stale = True
    video.brain_version = version_stamp()
    video.status = VideoStatus.SCRIPT
    audit(session, video, "script_from_discussion")
    session.commit()
    session.refresh(video)
    return ver


async def write_storyboard(session: Session, video: Video) -> list[Shot]:
    raw = await _ask(session, video, VISUAL, FINAL_VISUAL)
    data = _extract_json(raw)
    shots = data.get("shots") or []
    if not shots:
        raise RuntimeError("ИИ не вернул раскадровку в нужном формате. Попросите его ещё раз или уточните в обсуждении.")
    created = save_shots(session, video, shots)
    audit(session, video, "storyboard_from_discussion")
    session.commit()
    session.refresh(video)
    return created
