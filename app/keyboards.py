from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

from app.enums import VideoStatus
from app.models import Scene, Video
from app.services.brain import BLOCKS

BOT_COMMANDS = [
    BotCommand("start", "Меню и справка"),
    BotCommand("new", "Новый ролик"),
    BotCommand("plan", "Контент-план"),
    BotCommand("videos", "Ролики в работе"),
    BotCommand("queue", "Очередь публикаций"),
    BotCommand("stats", "Статистика"),
    BotCommand("costs", "Расходы и лимиты"),
    BotCommand("facts", "База фактов"),
    BotCommand("articles", "Выгрузка статей для сайта"),
    BotCommand("brain", "Мозг системы"),
    BotCommand("settings", "Настройки"),
]

MENU_NEW = "Новый ролик"
MENU_PLAN = "План"
MENU_VIDEOS = "Ролики"
MENU_QUEUE = "Очередь"
MENU_STATS = "Статистика"
MENU_COSTS = "Расходы"
MENU_BRAIN = "Мозг"
MENU_SETTINGS = "Настройки"

MENU_BUTTONS = {
    MENU_NEW: "new",
    MENU_PLAN: "plan",
    MENU_VIDEOS: "videos",
    MENU_QUEUE: "queue",
    MENU_STATS: "stats",
    MENU_COSTS: "costs",
    MENU_BRAIN: "brain",
    MENU_SETTINGS: "settings",
}

MAIN_KB = ReplyKeyboardMarkup(
    [
        [MENU_NEW, MENU_PLAN, MENU_VIDEOS],
        [MENU_QUEUE, MENU_STATS, MENU_COSTS],
        [MENU_BRAIN, MENU_SETTINGS],
    ],
    resize_keyboard=True,
    is_persistent=True,
)


def scene_list(scenes: list[Scene], page: int = 0, per: int = 8) -> InlineKeyboardMarkup:
    chunk = scenes[page * per : (page + 1) * per]
    rows = [
        [InlineKeyboardButton(f"{'●' if s.use_status != 'free' else '○'} {s.code} {s.scene[:28]}", callback_data=f"sc:{s.id}")]
        for s in chunk
    ]
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("‹", callback_data=f"pl:{page-1}"))
    if (page + 1) * per < len(scenes):
        nav.append(InlineKeyboardButton("›", callback_data=f"pl:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("Своя тема текстом", callback_data="sc:custom")])
    return InlineKeyboardMarkup(rows)


def card_kb(video: Video) -> InlineKeyboardMarkup:
    vid = video.id
    status = video.status
    rows: list[list[InlineKeyboardButton]] = []
    if status == VideoStatus.DRAFT:
        rows = [
            [InlineKeyboardButton("Обсудить ролик", callback_data=f"v:{vid}:ds")],
            [InlineKeyboardButton("Написать сценарий", callback_data=f"v:{vid}:ws")],
        ]
    elif status == VideoStatus.SCRIPT:
        rows = [
            [
                InlineKeyboardButton("Утвердить", callback_data=f"v:{vid}:ok"),
                InlineKeyboardButton("Обсудить ещё", callback_data=f"v:{vid}:ds"),
            ],
            [
                InlineKeyboardButton("Версии", callback_data=f"v:{vid}:vs"),
                InlineKeyboardButton("Свой текст", callback_data=f"v:{vid}:own"),
            ],
            [InlineKeyboardButton("В эталоны", callback_data=f"v:{vid}:ex")],
        ]
    elif status == VideoStatus.FACTS:
        rows = [
            [InlineKeyboardButton("Показать факты", callback_data=f"v:{vid}:fl")],
            [
                InlineKeyboardButton("Добавить факт", callback_data=f"v:{vid}:fa"),
                InlineKeyboardButton("Выписать заново", callback_data=f"v:{vid}:fx"),
            ],
            [InlineKeyboardButton("Факты проверены — дальше", callback_data=f"v:{vid}:fn")],
        ]
    elif status == VideoStatus.VISUAL:
        rows = [
            [InlineKeyboardButton("Обсудить раскадровку", callback_data=f"v:{vid}:dv")],
            [InlineKeyboardButton("Сделать раскадровку и промпты", callback_data=f"v:{vid}:wv")],
        ]
    elif status == VideoStatus.STORYBOARD:
        rows = [
            [
                InlineKeyboardButton("Утвердить", callback_data=f"v:{vid}:ok"),
                InlineKeyboardButton("Обсудить ещё", callback_data=f"v:{vid}:dv"),
            ],
            [
                InlineKeyboardButton("Изменить кадр", callback_data=f"v:{vid}:edshot"),
                InlineKeyboardButton("Промпты", callback_data=f"v:{vid}:pr"),
            ],
        ]
    elif status == VideoStatus.PROMPTS:
        rows = [
            [InlineKeyboardButton("Запустить генерацию", callback_data=f"v:{vid}:gen")],
            [InlineKeyboardButton("Посмотреть промпты", callback_data=f"v:{vid}:pr")],
        ]
    elif status == VideoStatus.MEDIA:
        rows = [
            [
                InlineKeyboardButton("Утвердить", callback_data=f"v:{vid}:ok"),
                InlineKeyboardButton("Перегенерировать кадр", callback_data=f"v:{vid}:rgen"),
            ],
            [InlineKeyboardButton("Сменить модель", callback_data=f"v:{vid}:model")],
        ]
    elif status == VideoStatus.VOICE:
        rows = [
            [
                InlineKeyboardButton("Утвердить", callback_data=f"v:{vid}:ok"),
                InlineKeyboardButton("Переозвучить фразу", callback_data=f"v:{vid}:rvoice"),
            ]
        ]
    elif status == VideoStatus.ASSEMBLY:
        rows = [
            [
                InlineKeyboardButton("Опубликовать", callback_data=f"v:{vid}:pub"),
                InlineKeyboardButton("В очередь", callback_data=f"v:{vid}:queue"),
            ],
            [
                InlineKeyboardButton("Пересобрать", callback_data=f"v:{vid}:asm"),
                InlineKeyboardButton("Вернуться к этапу", callback_data=f"v:{vid}:back"),
            ],
        ]
    elif status == VideoStatus.QUEUED:
        rows = [[InlineKeyboardButton("Снять с очереди", callback_data=f"v:{vid}:unq")]]
    elif status == VideoStatus.PAUSED:
        rows = [[InlineKeyboardButton("Вернуть в работу", callback_data=f"v:{vid}:resume")]]
    if status in (VideoStatus.ASSEMBLY, VideoStatus.QUEUED, VideoStatus.PUBLISHED):
        rows.append([InlineKeyboardButton("Статья для сайта", callback_data=f"v:{vid}:art")])
    rows.append(
        [
            InlineKeyboardButton("Отложить", callback_data=f"v:{vid}:pause"),
            InlineKeyboardButton("Карточка", callback_data=f"v:{vid}:card"),
        ]
    )
    return InlineKeyboardMarkup(rows)


def back_stages(vid: int) -> InlineKeyboardMarkup:
    labels = [
        ("Сценарий", "script"),
        ("Факты", "facts"),
        ("Обсуждение раскадровки", "visual"),
        ("Раскадровка", "storyboard"),
        ("Промпты", "prompts"),
        ("Медиа", "media"),
        ("Озвучка", "voice"),
    ]
    rows = [[InlineKeyboardButton(t, callback_data=f"bk:{vid}:{st}")] for t, st in labels]
    return InlineKeyboardMarkup(rows)


def fact_kb(link_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✓ Верно", callback_data=f"f:{link_id}:ok"),
                InlineKeyboardButton("✎ Исправить", callback_data=f"f:{link_id}:ed"),
            ],
            [
                InlineKeyboardButton("Источник", callback_data=f"f:{link_id}:src"),
                InlineKeyboardButton("✕ Убрать из ролика", callback_data=f"f:{link_id}:rm"),
            ],
        ]
    )


def discussion_kb(video_id: int, stage: str) -> InlineKeyboardMarkup:
    """Кнопки под каждым ответом ИИ-сценариста."""
    if stage == "script":
        finish = InlineKeyboardButton("Написать сценарий", callback_data=f"v:{video_id}:ws")
    else:
        finish = InlineKeyboardButton("Сделать раскадровку и промпты", callback_data=f"v:{video_id}:wv")
    return InlineKeyboardMarkup(
        [[finish], [InlineKeyboardButton("Карточка ролика", callback_data=f"v:{video_id}:card")]]
    )


def brain_kb() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(title, callback_data=f"br:{key}")] for key, title in BLOCKS.items()]
    rows.append([InlineKeyboardButton("Скачать все файлы", callback_data="br:dump")])
    return InlineKeyboardMarkup(rows)


def shot_pick(video: Video, action: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(f"{s.ord}. {s.shot_type} {s.description[:24]}", callback_data=f"sh:{video.id}:{s.id}:{action}")]
        for s in video.shots
    ]
    return InlineKeyboardMarkup(rows)
