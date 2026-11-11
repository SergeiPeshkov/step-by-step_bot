from __future__ import annotations

import re

# Советы вместо объяснений, оценки выгоды, призывы.
BANNED = [
    r"\bвыгодн",
    r"\bрекомендуем\b",
    r"\bсоветуем\b",
    r"\bлучше возьмите\b",
    r"\bлучше выбрать\b",
    r"\bгарантир",
    r"\bподписывайтесь\b",
    r"\bподписывайся\b",
    r"\bставьте лайк\b",
    r"\bставь лайк\b",
]

# Названия банков: в роликах их не упоминаем.
BANKS = [
    r"\bсбер",
    r"\bвтб\b",
    r"\bальфа[- ]?банк",
    r"\bт[- ]?банк",
    r"\bтинькофф",
    r"\bгазпромбанк",
    r"\bдом\.?рф\b",
    r"\bрайффайзен",
    r"\bсовкомбанк",
    r"\bпочта банк",
    r"\bрнкб\b",
    r"\bгенбанк",
    r"\bпсб\b",
    r"\bозон банк",
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
            warnings.append(f"Похоже на совет, оценку или призыв: «{pat}».")
    for pat in BANKS:
        if re.search(pat, low, re.I):
            warnings.append(f"Название банка в тексте: «{pat}». Объясняем без названий банков.")
    return warnings


def word_duration(text: str) -> float:
    words = re.findall(r"[А-Яа-яA-Za-zЁё\-]+", text)
    return len(words) / 2.4
