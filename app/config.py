from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    telegram_bot_token: str = ""
    telegram_owner_id: int = 0
    telegram_channel_id: str = ""

    llm_provider: str = "stub"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"

    # ИИ-сценарист: отдельная модель для обсуждения сценария, раскадровки и промптов.
    # Пустые поля берутся из LLM_*.
    writer_provider: str = ""
    writer_api_key: str = ""
    writer_base_url: str = ""
    writer_model: str = ""
    writer_temperature: float = 0.8

    image_provider: str = "stub"
    image_api_key: str = ""
    image_base_url: str = ""
    image_model: str = "cheap"
    image_quality_model: str = "quality"

    video_provider: str = "stub"
    video_api_key: str = ""
    video_base_url: str = ""
    video_model: str = "kling-turbo"

    tts_provider: str = "stub"
    tts_api_key: str = ""
    tts_voice: str = "filipp"
    yandex_folder_id: str = ""

    vk_access_token: str = ""
    vk_group_id: str = ""
    vk_api_version: str = "5.199"
    youtube_client_secrets: str = ""

    daily_cost_limit: float = 500
    monthly_cost_limit: float = 6000
    keep_files_days: int = 30

    database_url: str = f"sqlite:///{(ROOT / 'data' / 'db.sqlite3').as_posix()}"
    storage_dir: Path = ROOT / "data" / "storage"
    brain_dir: Path = ROOT / "brain"
    music_dir: Path = ROOT / "data" / "music"
    ritual_dir: Path = ROOT / "data" / "rituals"
    font_path: Path = (
        ROOT / "data" / "fonts" / "DejaVuSans.ttf"
        if (ROOT / "data" / "fonts" / "DejaVuSans.ttf").exists()
        else Path(r"C:\Windows\Fonts\arial.ttf")
    )
    max_video_shots: int = 1
    default_publish_hour: int = 10
    default_publish_minute: int = 0


settings = Settings()
settings.storage_dir.mkdir(parents=True, exist_ok=True)
settings.music_dir.mkdir(parents=True, exist_ok=True)
settings.ritual_dir.mkdir(parents=True, exist_ok=True)
(ROOT / "data" / "fonts").mkdir(parents=True, exist_ok=True)
