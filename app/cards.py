from app.enums import STATUS_LABEL, VideoStatus
from app.models import Video
from app.services.checker import check_script
from app.services.pipeline import latest_script, title_of


def card_text(video: Video) -> str:
    title = title_of(video)
    stale = f"\n⚠ Устарело с этапа: {STATUS_LABEL.get(video.stale_from, video.stale_from)}" if video.stale_from else ""
    script = latest_script(video)
    preview = ""
    if script:
        body = script.text[:700] + ("…" if len(script.text) > 700 else "")
        warns = check_script(script.text)
        warn_txt = "\n".join(f"• {w}" for w in warns)
        preview = f"\n\n{body}"
        if warn_txt:
            preview += f"\n\nПредупреждения (решение за вами):\n{warn_txt}"
    talk = ""
    if video.status in (VideoStatus.DRAFT, VideoStatus.VISUAL):
        stage = "script" if video.status == VideoStatus.DRAFT else "visual"
        n = sum(1 for m in video.discussion if m.stage == stage and m.role == "user")
        talk = f"\n\nОбсуждение с ИИ-сценаристом: реплик автора — {n}. Пишите сообщения прямо в чат."
    facts_txt = ""
    if video.fact_links:
        from app.services.facts import actual_date, summary

        s = summary(video)
        checked = actual_date(video)
        facts_txt = (
            f"\n\nФакты: проверено {s['confirmed']} из {s['total']}"
            + (f", ждут проверки {s['pending']}" if s["pending"] else "")
            + (f", убрано {s['removed']}" if s["removed"] else "")
            + (f"\nАктуально на {checked:%d.%m.%Y}" if checked and not s["pending"] else "")
        )
    shots = ""
    if video.shots and video.status in {
        VideoStatus.STORYBOARD,
        VideoStatus.PROMPTS,
        VideoStatus.MEDIA,
        VideoStatus.VOICE,
        VideoStatus.ASSEMBLY,
    }:
        lines = []
        for s in video.shots:
            mark = " *" if s.stale else ""
            lines.append(f"{s.ord}. {s.start:.0f}–{s.end:.0f}с {s.shot_type}{mark}: {s.description[:60]}")
        shots = "\n\nКадры:\n" + "\n".join(lines)
    return (
        f"Ролик #{video.id}\n{title}\n"
        f"Статус: {STATUS_LABEL.get(video.status, video.status)}\n"
        f"Мозг: v{video.brain_version} · расход: {video.cost:.1f} ₽"
        f"{stale}{talk}{facts_txt}{preview}{shots}"
    )
