from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), default="По полочкам")
    language: Mapped[str] = mapped_column(String(8), default="ru")
    brain_version: Mapped[str] = mapped_column(String(32), default="1")
    settings_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Scene(Base):
    __tablename__ = "scenes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), default=1)
    number: Mapped[int] = mapped_column(Integer, index=True)
    code: Mapped[str] = mapped_column(String(16), index=True)
    theme: Mapped[str] = mapped_column(String(200))
    scene: Mapped[str] = mapped_column(Text)
    under: Mapped[str] = mapped_column(Text, default="")
    rubric: Mapped[str] = mapped_column(String(80), default="")
    use_status: Mapped[str] = mapped_column(String(20), default="free")


class LibraryVideo(Base):
    """Каталог роликов: какие темы есть и какие уже сняты."""

    __tablename__ = "library_videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(300), default="")
    shelf: Mapped[str] = mapped_column(String(120), default="", index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    legal_act: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    # not_created | in_progress | created
    status: Mapped[str] = mapped_column(String(20), default="not_created", index=True)
    video_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), default=1)
    scene_id: Mapped[Optional[int]] = mapped_column(ForeignKey("scenes.id"), nullable=True)
    custom_topic: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="draft", index=True)
    brain_version: Mapped[str] = mapped_column(String(32), default="1")
    cost: Mapped[float] = mapped_column(Float, default=0.0)
    card_chat_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    card_message_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    stale_from: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    edit_list_json: Mapped[str] = mapped_column(Text, default="{}")
    assembled_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    preview_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    publish_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    scene: Mapped[Optional["Scene"]] = relationship()
    scripts: Mapped[list["ScriptVersion"]] = relationship(back_populates="video", cascade="all, delete-orphan")
    shots: Mapped[list["Shot"]] = relationship(back_populates="video", cascade="all, delete-orphan", order_by="Shot.ord")
    phrases: Mapped[list["VoicePhrase"]] = relationship(back_populates="video", cascade="all, delete-orphan")
    publications: Mapped[list["Publication"]] = relationship(back_populates="video", cascade="all, delete-orphan")
    costs: Mapped[list["CostEntry"]] = relationship(back_populates="video", cascade="all, delete-orphan")
    events: Mapped[list["AuditEvent"]] = relationship(back_populates="video", cascade="all, delete-orphan")
    discussion: Mapped[list["DiscussionMessage"]] = relationship(
        back_populates="video", cascade="all, delete-orphan", order_by="DiscussionMessage.id"
    )


class DiscussionMessage(Base):
    """Переписка автора с ИИ-сценаристом. stage: script — сценарий, visual — раскадровка и промпты."""

    __tablename__ = "discussion_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"), index=True)
    stage: Mapped[str] = mapped_column(String(16), default="script")
    role: Mapped[str] = mapped_column(String(16))  # user | assistant
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    video: Mapped["Video"] = relationship(back_populates="discussion")


class ScriptVersion(Base):
    __tablename__ = "script_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"))
    text: Mapped[str] = mapped_column(Text)
    note: Mapped[str] = mapped_column(Text, default="")
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    video: Mapped["Video"] = relationship(back_populates="scripts")


class Shot(Base):
    __tablename__ = "shots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"))
    ord: Mapped[int] = mapped_column(Integer)
    start: Mapped[float] = mapped_column(Float, default=0)
    end: Mapped[float] = mapped_column(Float, default=0)
    voice_text: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    shot_type: Mapped[str] = mapped_column(String(20), default="image")
    prompt: Mapped[str] = mapped_column(Text, default="")
    effect: Mapped[str] = mapped_column(String(32), default="zoom_in")
    stale: Mapped[bool] = mapped_column(Boolean, default=False)

    video: Mapped["Video"] = relationship(back_populates="shots")
    media: Mapped[list["MediaFile"]] = relationship(back_populates="shot", cascade="all, delete-orphan")


class MediaFile(Base):
    __tablename__ = "media_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shot_id: Mapped[int] = mapped_column(ForeignKey("shots.id"))
    path: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(80))
    cost: Mapped[float] = mapped_column(Float, default=0)
    chosen: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    shot: Mapped["Shot"] = relationship(back_populates="media")


class VoicePhrase(Base):
    __tablename__ = "voice_phrases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"))
    shot_id: Mapped[Optional[int]] = mapped_column(ForeignKey("shots.id"), nullable=True)
    start: Mapped[float] = mapped_column(Float, default=0)
    text: Mapped[str] = mapped_column(Text)
    markup: Mapped[str] = mapped_column(Text, default="")
    path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cost: Mapped[float] = mapped_column(Float, default=0)

    video: Mapped["Video"] = relationship(back_populates="phrases")


class Publication(Base):
    __tablename__ = "publications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"))
    platform: Mapped[str] = mapped_column(String(24))
    post_url: Mapped[str] = mapped_column(Text, default="")
    caption: Mapped[str] = mapped_column(Text, default="")
    hashtags: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    stats_json: Mapped[str] = mapped_column(Text, default="{}")
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    video: Mapped["Video"] = relationship(back_populates="publications")


class Ritual(Base):
    __tablename__ = "rituals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(24))
    path: Mapped[str] = mapped_column(Text)
    note: Mapped[str] = mapped_column(Text, default="")


class CostEntry(Base):
    __tablename__ = "cost_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"))
    kind: Mapped[str] = mapped_column(String(24))
    amount: Mapped[float] = mapped_column(Float)
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    video: Mapped["Video"] = relationship(back_populates="costs")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_id: Mapped[Optional[int]] = mapped_column(ForeignKey("videos.id"), nullable=True)
    actor: Mapped[str] = mapped_column(String(40), default="owner")
    action: Mapped[str] = mapped_column(String(80))
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    video: Mapped[Optional["Video"]] = relationship(back_populates="events")


class UserState(Base):
    __tablename__ = "user_state"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    awaiting: Mapped[str] = mapped_column(String(32), default="none")
    extra: Mapped[str] = mapped_column(Text, default="")
