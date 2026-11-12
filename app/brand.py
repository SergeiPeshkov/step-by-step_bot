"""Фирменный стиль «По полочкам» (вариант Г «Тёплый с коричневым»).

Цвета и шрифты для сборки роликов. Тот же набор использует сайт,
поэтому менять палитру лучше здесь и там одновременно.
"""

BG = "#FBF3E7"  # кремовый фон
INK = "#3A2A1F"  # тёмно-коричневый, основной текст
MUTED = "#6B5B4C"  # вторичный текст
ACCENT = "#C2582F"  # терракота: плашки, акценты
GREEN = "#1F4D3A"  # глубокий зелёный: кадры с цифрами
SOFT = "#F1DFC8"  # подложка
CARD = "#FFFDF8"  # светлый текст на тёмном и на картинках

HEADING_FONT = "PT Serif"
HEADING_FONT_FILE = "PTSerif-Bold.ttf"
TEXT_FONT = "Golos Text"
TEXT_FONT_FILE = "GolosText.ttf"


def ff(color: str) -> str:
    """#RRGGBB в формат FFmpeg: 0xRRGGBB."""
    return "0x" + color.lstrip("#").upper()


def ass(color: str, alpha: int = 0) -> str:
    """#RRGGBB в формат субтитров ASS: &HAABBGGRR."""
    c = color.lstrip("#").upper()
    return f"&H{alpha:02X}{c[4:6]}{c[2:4]}{c[0:2]}"

# Хвост промпта картинки, если ИИ-сценарист не написал свой промпт.
IMAGE_PROMPT_TAIL = (
    "paper cut-out illustration, gouache texture, warm soft light, "
    "cream #FBF3E7, dark brown #3A2A1F, terracotta #C2582F and deep green #1F4D3A accents, "
    "cozy everyday scene, no faces, no text, no watermark, no logos, vertical 9:16"
)
