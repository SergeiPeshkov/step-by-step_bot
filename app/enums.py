from enum import StrEnum


class VideoStatus(StrEnum):
    DRAFT = "draft"
    SCRIPT = "script"
    VISUAL = "visual"  # обсуждение раскадровки и промптов с ИИ-сценаристом
    STORYBOARD = "storyboard"
    PROMPTS = "prompts"
    MEDIA = "media"
    VOICE = "voice"
    ASSEMBLY = "assembly"
    QUEUED = "queued"
    PUBLISHED = "published"
    PAUSED = "paused"


class ShotType(StrEnum):
    IMAGE = "image"
    VIDEO = "video"
    RITUAL = "ritual"
    TEXT = "text"
    MONTAGE = "montage"
    BLACK = "black"


class SceneUse(StrEnum):
    FREE = "free"
    USED = "used"
    IN_PROGRESS = "in_progress"


class AwaitKind(StrEnum):
    NONE = "none"
    SCRIPT_FEEDBACK = "script_feedback"
    SCRIPT_OWN = "script_own"
    SHOT_EDIT = "shot_edit"
    PROMPT_EDIT = "prompt_edit"
    NEW_TOPIC = "new_topic"
    BRAIN_EDIT = "brain_edit"
    SETTINGS = "settings"
    REGEN_NOTE = "regen_note"
    DISCUSS_SCRIPT = "discuss_script"
    DISCUSS_VISUAL = "discuss_visual"


STATUS_LABEL = {
    VideoStatus.DRAFT: "Обсуждение ролика",
    VideoStatus.SCRIPT: "Сценарий",
    VideoStatus.VISUAL: "Обсуждение раскадровки",
    VideoStatus.STORYBOARD: "Раскадровка",
    VideoStatus.PROMPTS: "Промпты",
    VideoStatus.MEDIA: "Медиа",
    VideoStatus.VOICE: "Озвучка",
    VideoStatus.ASSEMBLY: "Сборка",
    VideoStatus.QUEUED: "В очереди",
    VideoStatus.PUBLISHED: "Опубликован",
    VideoStatus.PAUSED: "Отложен",
}

STAGE_ORDER = [
    VideoStatus.DRAFT,
    VideoStatus.SCRIPT,
    VideoStatus.VISUAL,
    VideoStatus.STORYBOARD,
    VideoStatus.PROMPTS,
    VideoStatus.MEDIA,
    VideoStatus.VOICE,
    VideoStatus.ASSEMBLY,
    VideoStatus.QUEUED,
    VideoStatus.PUBLISHED,
]
