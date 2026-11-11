from __future__ import annotations

import re

BANNED = [
    r"\bсделай\b",
    r"\bтебе нужно\b",
    r"\bпопробуй\b",
    r"\bдиагноз\b",
    r"\bдепресс",
    r"\bтревожн(ое|ое расстройств)",
    r"\bлечи\b",
    r"\bты должен\b",
    r"\bты должна\b",
    r"\bподписывайся\b",
    r"\bставь лайк\b",
]


def check_script(text: str) -> list[str]:
    warnings: list[str] = []
    words = re.findall(r"[А-Яа-яA-Za-zЁё\-]+", text)
    # ~2.4 слова/с → 40–55 с ≈ 96–132 слова
    duration = len(words) / 2.4
    if duration < 40 or duration > 55:
        warnings.append(f"Длительность по словам ≈ {duration:.0f} с (нужно 40–55). Слов: {len(words)}.")
    low = text.lower()
    for pat in BANNED:
        if re.search(pat, low, re.I):
            warnings.append(f"Похоже на совет/призыв/термин: «{pat}».")
    return warnings


def word_duration(text: str) -> float:
    words = re.findall(r"[А-Яа-яA-Za-zЁё\-]+", text)
    return len(words) / 2.4
