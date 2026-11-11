from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import SceneUse
from app.models import Scene


def list_scenes(session: Session, only_free: bool | None = None) -> list[Scene]:
    q = select(Scene).order_by(Scene.number, Scene.id)
    scenes = list(session.scalars(q))
    if only_free is True:
        return [s for s in scenes if s.use_status == SceneUse.FREE]
    return scenes


def get_by_code_or_number(session: Session, query: str) -> Scene | None:
    q = query.strip()
    scene = session.scalar(select(Scene).where(Scene.code == q))
    if scene:
        return scene
    if q.isdigit():
        return session.scalar(select(Scene).where(Scene.number == int(q)))
    return session.scalar(select(Scene).where(Scene.scene.ilike(f"%{q}%")))


def import_bytes(session: Session, raw: bytes, filename: str) -> int:
    name = filename.lower()
    text = raw.decode("utf-8-sig")
    if name.endswith(".json"):
        data = json.loads(text)
        rows = data if isinstance(data, list) else data.get("scenes") or data.get("items") or []
        return _upsert_rows(session, rows)
    return _upsert_rows(session, _csv_rows(text))


def import_path(session: Session, path: Path) -> int:
    return import_bytes(session, path.read_bytes(), path.name)


def _csv_rows(text: str) -> list[dict]:
    sample = text[:2048]
    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    return list(reader)


def _upsert_rows(session: Session, rows: list[dict]) -> int:
    count = 0
    for i, row in enumerate(rows, start=1):
        number = _int(row.get("number") or row.get("номер") or row.get("n") or i)
        code = str(row.get("code") or row.get("номер_сцены") or row.get("id") or number)
        theme = str(row.get("theme") or row.get("тема") or "")
        scene_text = str(row.get("scene") or row.get("сцена") or row.get("title") or "")
        under = str(row.get("under") or row.get("что под ней") or row.get("underneath") or "")
        rubric = str(row.get("rubric") or row.get("рубрика") or "")
        if not scene_text:
            continue
        existing = session.scalar(select(Scene).where(Scene.code == code))
        if existing:
            existing.number = number
            existing.theme = theme
            existing.scene = scene_text
            existing.under = under
            existing.rubric = rubric
        else:
            session.add(
                Scene(
                    number=number,
                    code=code,
                    theme=theme,
                    scene=scene_text,
                    under=under,
                    rubric=rubric,
                    use_status=SceneUse.FREE,
                )
            )
        count += 1
    session.commit()
    return count


def _int(val) -> int:
    try:
        return int(str(val).split(".")[0])
    except (TypeError, ValueError):
        return 0
