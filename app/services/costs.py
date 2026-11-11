from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import CostEntry, Video


class CostLimitError(RuntimeError):
    pass


def add_cost(session: Session, video: Video, kind: str, amount: float, detail: str = "") -> None:
    if amount <= 0:
        return
    session.add(CostEntry(video_id=video.id, kind=kind, amount=amount, detail=detail))
    video.cost = float(video.cost or 0) + amount


def period_sum(session: Session, since: datetime) -> float:
    val = session.scalar(select(func.coalesce(func.sum(CostEntry.amount), 0)).where(CostEntry.created_at >= since))
    return float(val or 0)


def assert_budget(session: Session) -> None:
    now = datetime.utcnow()
    day = period_sum(session, now - timedelta(days=1))
    month = period_sum(session, now.replace(day=1, hour=0, minute=0, second=0, microsecond=0))
    if day >= settings.daily_cost_limit:
        raise CostLimitError(f"Дневной лимит {settings.daily_cost_limit:.0f} ₽ исчерпан ({day:.0f} ₽).")
    if month >= settings.monthly_cost_limit:
        raise CostLimitError(f"Месячный лимит {settings.monthly_cost_limit:.0f} ₽ исчерпан ({month:.0f} ₽).")
