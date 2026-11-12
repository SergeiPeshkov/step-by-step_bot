from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.image import get_image_adapter
from app.adapters.llm import get_llm_adapter
from app.adapters.tts import get_tts_adapter
from app.adapters.video_gen import get_video_adapter
from app.assembler.assemble import assemble_from_sheet
from app import brand
from app.config import settings
from app.enums import ShotType, VideoStatus
from app.models import AuditEvent, MediaFile, ScriptVersion, Shot, Video, VoicePhrase
from app.services.brain import dump_all, load_block, save_block, version_stamp
from app.services.checker import check_script
from app.services.costs import CostLimitError, add_cost, assert_budget


def video_dir(video_id: int) -> Path:
    path = settings.storage_dir / f"video_{video_id}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def audit(session: Session, video: Video | None, action: str, detail: str = "") -> None:
    session.add(AuditEvent(video_id=video.id if video else None, action=action, detail=detail[:2000]))


def latest_script(video: Video) -> ScriptVersion | None:
    if not video.scripts:
        return None
    return max(video.scripts, key=lambda s: s.id)


def approved_script(video: Video) -> ScriptVersion | None:
    for s in sorted(video.scripts, key=lambda x: x.id, reverse=True):
        if s.approved:
            return s
    return None


async def generate_script(session: Session, video: Video, note: str = "") -> ScriptVersion:
    llm = get_llm_adapter()
    topic = video.custom_topic or (video.scene.scene if video.scene else "")
    under = video.scene.under if video.scene else ""
    theme = video.scene.theme if video.scene else ""
    prev = latest_script(video)
    user = (
        f"Тема: {theme}\nСцена: {topic}\nЧто под ней: {under}\n"
        f"Замечание автора: {note or 'нет'}\n"
        f"Предыдущая версия:\n{prev.text if prev else 'нет'}\n"
        "Напиши сценарий целиком, без заголовков и пояснений."
    )
    system = (
        "Ты пишешь сценарии коротких роликов «По полочкам» — короткие ответы на вопросы о законах простыми словами.\n"
        + dump_all()
        + "\nОтвет — только текст сценария."
    )
    text = (await llm.complete(system, user)).strip()
    ver = ScriptVersion(video_id=video.id, text=text, note=note)
    session.add(ver)
    video.brain_version = version_stamp()
    video.status = VideoStatus.SCRIPT
    audit(session, video, "script_generated", note)
    session.commit()
    return ver


async def generate_storyboard(session: Session, video: Video) -> list[Shot]:
    script = approved_script(video) or latest_script(video)
    if not script:
        raise RuntimeError("Нет сценария")
    llm = get_llm_adapter()
    system = (
        "РАСКАДРОВКА. Верни JSON {\"shots\":[...]} без markdown.\n"
        "Поля кадра: ord, start, end, type, voice, description, effect.\n"
        "type: image|video|text|montage|black.\n"
        + load_block("storyboard_rules")
    )
    raw = await llm.complete(system, f"Сценарий:\n{script.text}")
    data = _extract_json(raw)
    return save_shots(session, video, data.get("shots") or [])


def save_shots(session: Session, video: Video, shots_data: list[dict]) -> list[Shot]:
    """Заменяет кадры ролика на новые. Поле prompt необязательно: пустые промпты потом соберёт generate_prompts."""
    video.shots.clear()
    session.flush()
    video_count = 0
    created: list[Shot] = []
    for item in shots_data:
        stype = item.get("type") or "image"
        if stype == "video":
            video_count += 1
            if video_count > settings.max_video_shots:
                stype = "image"
        shot = Shot(
            video_id=video.id,
            ord=int(item.get("ord") or len(created) + 1),
            start=float(item.get("start") or 0),
            end=float(item.get("end") or 0),
            voice_text=item.get("voice") or "",
            description=item.get("description") or "",
            shot_type=stype,
            effect=item.get("effect") or ("zoom_in" if stype == "image" else "none"),
            prompt=item.get("prompt") or "",
        )
        session.add(shot)
        created.append(shot)
    video.status = VideoStatus.STORYBOARD
    video.stale_from = None
    audit(session, video, "storyboard")
    session.commit()
    return created


async def generate_prompts(session: Session, video: Video) -> None:
    bans = "без текста в кадре, без логотипов банков и брендов, без госсимволики, без узнаваемых реальных людей, 9:16"
    for shot in video.shots:
        if shot.shot_type in (ShotType.BLACK, ShotType.TEXT, ShotType.RITUAL):
            shot.prompt = ""
            continue
        if shot.prompt.strip():
            # Промпт уже написал ИИ-сценарист вместе с автором — не трогаем.
            continue
        shot.prompt = f"{shot.description}. {bans}. {brand.IMAGE_PROMPT_TAIL}."
    video.status = VideoStatus.PROMPTS
    audit(session, video, "prompts")
    session.commit()


async def generate_media(session: Session, video: Video, only_shot_id: int | None = None, quality: bool = False) -> None:
    try:
        assert_budget(session)
    except CostLimitError:
        raise
    img = get_image_adapter()
    vid = get_video_adapter()
    folder = video_dir(video.id) / "media"
    shots = [s for s in video.shots if only_shot_id is None or s.id == only_shot_id]
    for shot in shots:
        if shot.shot_type in (ShotType.BLACK, ShotType.TEXT):
            continue
        if shot.shot_type == ShotType.RITUAL:
            ritual = settings.ritual_dir / "intro.mp4"
            if ritual.exists():
                dest = folder / f"shot_{shot.ord}_ritual.mp4"
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(ritual.read_bytes())
                _choose_media(session, shot, dest, "library", "ritual", 0)
            continue
        model = settings.image_quality_model if quality else settings.image_model
        dest = folder / f"shot_{shot.ord}_{shot.shot_type}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        if shot.shot_type == ShotType.VIDEO:
            path, cost = await vid.generate(shot.prompt, dest.with_suffix(".mp4"), settings.video_model, shot.end - shot.start)
            provider = settings.video_provider
        else:
            path, cost = await img.generate(shot.prompt, dest.with_suffix(".png"), model)
            provider = settings.image_provider
        _choose_media(session, shot, path, provider, model, cost)
        add_cost(session, video, "media", cost, f"shot {shot.ord}")
        shot.stale = False
    video.status = VideoStatus.MEDIA
    audit(session, video, "media", f"shot={only_shot_id or 'all'}")
    session.commit()


def _choose_media(session: Session, shot: Shot, path: Path, provider: str, model: str, cost: float) -> None:
    for m in shot.media:
        m.chosen = False
    session.add(MediaFile(shot_id=shot.id, path=str(path), provider=provider, model=model, cost=cost, chosen=True))


async def generate_voice(session: Session, video: Video, only_phrase_id: int | None = None) -> None:
    assert_budget(session)
    tts = get_tts_adapter()
    folder = video_dir(video.id) / "voice"
    if only_phrase_id is None:
        video.phrases.clear()
        session.flush()
        for shot in video.shots:
            if not shot.voice_text.strip():
                continue
            markup = _voice_markup(shot.voice_text)
            phrase = VoicePhrase(
                video_id=video.id,
                shot_id=shot.id,
                start=shot.start,
                text=shot.voice_text,
                markup=markup,
            )
            session.add(phrase)
            session.flush()
            dest = folder / f"phrase_{phrase.id}.mp3"
            path, cost = await tts.speak(shot.voice_text, dest, markup)
            phrase.path = str(path)
            phrase.cost = cost
            add_cost(session, video, "tts", cost, f"phrase {phrase.id}")
    else:
        phrase = session.get(VoicePhrase, only_phrase_id)
        if not phrase:
            return
        dest = folder / f"phrase_{phrase.id}.mp3"
        path, cost = await tts.speak(phrase.text, dest, phrase.markup or _voice_markup(phrase.text))
        phrase.path = str(path)
        phrase.cost = cost
        add_cost(session, video, "tts", cost, f"phrase {phrase.id} redo")
    video.status = VideoStatus.VOICE
    audit(session, video, "voice")
    session.commit()


def _voice_markup(text: str) -> str:
    # Пауза после главной мысли: предложение перед последним.
    parts = re.split(r"(?<=[.!?…])\s+", text.strip())
    if len(parts) >= 2:
        parts[-2] = parts[-2] + " sil<[500]>"
    return " ".join(parts)


def build_sheet(video: Video) -> dict:
    shots = []
    for s in video.shots:
        chosen = next((m for m in s.media if m.chosen), None)
        shots.append(
            {
                "start": s.start,
                "end": s.end,
                "type": s.shot_type,
                "file": chosen.path if chosen else "",
                "effect": s.effect,
                "text": s.description if s.shot_type == ShotType.TEXT else "",
                "dirty": s.stale,
            }
        )
    domain = re.sub(r"^https?://", "", settings.site_url).rstrip("/") if settings.site_url else ""
    outro = settings.outro_path
    if shots and outro and outro.is_file():
        # Фирменная концовка из файла; адрес сайта бот накладывает поверх неё.
        from app.assembler.assemble import _duration

        end = max(float(s["end"]) for s in shots)
        length = min(_duration(outro) or settings.outro_max_seconds, settings.outro_max_seconds)
        shots.append(
            {
                "start": end,
                "end": round(end + length, 2),
                "type": "outro",
                "file": str(outro),
                "effect": "none",
                "text": domain,
                "dirty": True,
            }
        )
    elif settings.site_url and shots:
        # Финальная карточка со ссылкой на сайт: добавляется автоматически, в сценарии её писать не нужно.
        end = max(float(s["end"]) for s in shots)
        shots.append(
            {
                "start": end,
                "end": round(end + settings.site_card_seconds, 2),
                "type": "text",
                "file": "",
                "effect": "none",
                "text": f"{settings.site_card_text} {domain}".strip(),
                "dirty": True,
            }
        )
    voice = [{"start": p.start, "file": p.path} for p in video.phrases if p.path]
    subs = []
    for p in video.phrases:
        end = p.start + max(1.2, len(p.text.split()) / 2.3)
        subs.append({"start": p.start, "end": end, "text": p.text})
    from app.services.facts import actual_date

    checked = actual_date(video)
    music_files = list(settings.music_dir.glob("*"))
    music = {}
    if music_files:
        music = {"file": str(music_files[0]), "volume": 0.15, "duck": True}
    return {
        "format": {"width": 1080, "height": 1920, "fps": 30},
        "shots": shots,
        "voice": voice,
        "music": music,
        "subtitles": subs,
        "badge": f"Актуально на {checked:%d.%m.%Y}" if checked else "",
    }


async def assemble(session: Session, video: Video) -> Path:
    folder = video_dir(video.id)
    sheet = build_sheet(video)
    sheet_path = folder / "sheet.json"
    sheet_path.write_text(json.dumps(sheet, ensure_ascii=False, indent=2), encoding="utf-8")
    out = folder / "result.mp4"
    work = folder / "work"
    assemble_from_sheet(sheet_path, work, out)
    video.assembled_path = str(out)
    video.preview_path = str(out)
    video.status = VideoStatus.ASSEMBLY
    audit(session, video, "assemble")
    session.commit()
    return out


def mark_stale_after_script_change(session: Session, video: Video) -> None:
    for s in video.scripts:
        s.approved = False
    for shot in video.shots:
        shot.stale = True
    video.stale_from = VideoStatus.STORYBOARD
    video.status = VideoStatus.SCRIPT
    audit(session, video, "stale_after_script")
    session.commit()


def add_exemplar(video: Video) -> None:
    script = approved_script(video) or latest_script(video)
    if not script:
        return
    title = video.custom_topic or (video.scene.scene if video.scene else f"ролик {video.id}")
    current = load_block("exemplars")
    save_block("exemplars", current.rstrip() + f"\n\n### {title}\n{script.text}\n")


def title_of(video: Video) -> str:
    if video.scene:
        return f"{video.scene.code} · {video.scene.scene}"
    return video.custom_topic or f"Ролик #{video.id}"


def _extract_json(raw: str) -> dict:
    """Достаёт JSON из ответа модели: снимает ```-обёртку и берёт первый {...}."""
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            return {}
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return {}
    return data if isinstance(data, dict) else {}
