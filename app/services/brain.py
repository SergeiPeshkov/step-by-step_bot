from __future__ import annotations

from pathlib import Path

from app.config import settings

BLOCKS = {
    "concept": "Концепция",
    "principle": "Принцип ролика",
    "language": "Правила языка",
    "exemplars": "Эталоны",
    "storyboard_rules": "Правила раскадровки",
    "style_bible": "Библия стиля",
}


def brain_path(name: str) -> Path:
    return settings.brain_dir / f"{name}.md"


def load_block(name: str) -> str:
    path = brain_path(name)
    return path.read_text(encoding="utf-8") if path.exists() else ""


def save_block(name: str, text: str) -> None:
    path = brain_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")


def dump_all() -> str:
    parts = []
    for key, title in BLOCKS.items():
        parts.append(f"## {title}\n{load_block(key).strip()}")
    return "\n\n".join(parts)


def version_stamp() -> str:
    total = 0
    for key in BLOCKS:
        total += hash(load_block(key)) % 10_000
    return str(abs(total) % 1_000_000)
