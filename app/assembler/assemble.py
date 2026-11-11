"""Сборка ролика по монтажному листу. Без ИИ, только FFmpeg."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.assembler.ffmpeg import ffmpeg_bin, ffprobe_bin


class AssembleError(RuntimeError):
    def __init__(self, message: str, shot: int | None = None):
        super().__init__(message)
        self.shot = shot


def _run(cmd: list[str], shot: int | None = None) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "")[-1500:]
        raise AssembleError(f"FFmpeg ошибка кадра {shot or '-'}: {err}", shot)


def _duration(path: Path) -> float:
    proc = subprocess.run(
        [ffprobe_bin(), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
    )
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return 0.0


def assemble_from_sheet(sheet_path: Path, work_dir: Path, out_path: Path) -> Path:
    sheet = json.loads(sheet_path.read_text(encoding="utf-8"))
    fmt = sheet["format"]
    w, h, fps = fmt["width"], fmt["height"], fmt["fps"]
    shots = sheet["shots"]
    work_dir.mkdir(parents=True, exist_ok=True)

    _validate(sheet)

    segments: list[Path] = []
    for i, shot in enumerate(shots, start=1):
        cached = work_dir / f"seg_{i}_{shot.get('type')}_{shot['start']}_{shot['end']}.mp4"
        if cached.exists() and not shot.get("dirty"):
            segments.append(cached)
            continue
        seg = _prepare_shot(shot, i, cached, w, h, fps)
        segments.append(seg)

    concat_list = work_dir / "concat.txt"
    concat_list.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in segments), encoding="utf-8")
    video_only = work_dir / "video.mp4"
    _run(
        [ffmpeg_bin(), "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(video_only)],
        shot=None,
    )

    mixed = work_dir / "mixed.mp4"
    _mix_audio(sheet, video_only, mixed, work_dir)

    ass = work_dir / "subs.ass"
    _write_ass(sheet, ass)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fontsdir = str((Path(__file__).resolve().parents[2] / "data" / "fonts").as_posix())
    _run(
        [
            ffmpeg_bin(),
            "-y",
            "-i",
            str(mixed),
            "-vf",
            f"ass={ass.as_posix()}:fontsdir={fontsdir}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-r",
            str(fps),
            str(out_path),
        ]
    )
    if _duration(out_path) <= 0:
        raise AssembleError("Итог без длительности")
    return out_path


def _validate(sheet: dict) -> None:
    shots = sheet["shots"]
    if not shots:
        raise AssembleError("Пустой монтажный лист")
    prev_end = 0.0
    for i, s in enumerate(shots, start=1):
        if s["start"] + 0.05 < prev_end:
            raise AssembleError(f"Наложение кадров около {i}", i)
        if s["start"] > prev_end + 0.15:
            raise AssembleError(f"Разрыв перед кадром {i}", i)
        if s["end"] <= s["start"]:
            raise AssembleError(f"Нулевая длина кадра {i}", i)
        if s.get("file") and not Path(s["file"]).exists() and s.get("type") not in ("black", "text"):
            raise AssembleError(f"Нет файла кадра {i}: {s['file']}", i)
        prev_end = s["end"]


def _prepare_shot(shot: dict, index: int, dest: Path, w: int, h: int, fps: int) -> Path:
    duration = max(0.2, float(shot["end"]) - float(shot["start"]))
    stype = shot.get("type")
    if stype in ("black",):
        _run(
            [
                ffmpeg_bin(),
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c=black:s={w}x{h}:d={duration}:r={fps}",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-an",
                str(dest),
            ],
            index,
        )
        return dest
    if stype == "text":
        text = (shot.get("text") or "").replace(":", r"\:").replace("'", "")
        _run(
            [
                ffmpeg_bin(),
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c=0x0b0f14:s={w}x{h}:d={duration}:r={fps}",
                "-vf",
                f"drawtext=text='{text}':fontcolor=white:fontsize=48:x=(w-text_w)/2:y=(h-text_h)/2",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-an",
                str(dest),
            ],
            index,
        )
        return dest

    src = Path(shot["file"])
    effect = shot.get("effect") or "zoom_in"
    if src.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
        frames = max(int(duration * fps), 2)
        if effect == "pan":
            zoom = "zoompan=z=1.08:x='iw*0.04*on/duration':y='ih*0.02':d={frames}:s={w}x{h}:fps={fps}"
        else:
            zoom = f"zoompan=z='min(zoom+0.0008,1.12)':d={frames}:s={w}x{h}:fps={fps}"
        vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},{zoom}"
        _run(
            [
                ffmpeg_bin(),
                "-y",
                "-loop",
                "1",
                "-i",
                str(src),
                "-t",
                f"{duration:.3f}",
                "-vf",
                vf,
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-an",
                str(dest),
            ],
            index,
        )
        return dest

    vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={fps}"
    src_dur = _duration(src)
    if src_dur and src_dur < duration - 0.05:
        speed = max(src_dur / duration, 0.25)
        _run(
            [
                ffmpeg_bin(),
                "-y",
                "-i",
                str(src),
                "-filter:v",
                f"setpts=PTS/{speed},{vf}",
                "-an",
                "-t",
                f"{duration:.3f}",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(dest),
            ],
            index,
        )
    else:
        _run(
            [
                ffmpeg_bin(),
                "-y",
                "-i",
                str(src),
                "-t",
                f"{duration:.3f}",
                "-vf",
                vf,
                "-an",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(dest),
            ],
            index,
        )
    return dest


def _mix_audio(sheet: dict, video: Path, dest: Path, work_dir: Path) -> None:
    voices = sheet.get("voice") or []
    music = sheet.get("music") or {}
    inputs = ["-i", str(video)]
    filters = []
    voice_labels = []
    idx = 1
    for v in voices:
        path = Path(v["file"])
        if not path.exists():
            continue
        inputs += ["-i", str(path)]
        delay_ms = int(float(v.get("start", 0)) * 1000)
        filters.append(f"[{idx}:a]adelay={delay_ms}|{delay_ms},volume=1.0[v{idx}]")
        voice_labels.append(f"[v{idx}]")
        idx += 1

    if not voice_labels:
        _run([ffmpeg_bin(), "-y", "-i", str(video), "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-c:v", "copy", "-c:a", "aac", "-shortest", str(dest)])
        return

    mix_n = len(voice_labels)
    voice_mix = "".join(voice_labels) + f"amix=inputs={mix_n}:normalize=0[voice]"
    filters.append(voice_mix)

    if music.get("file") and Path(music["file"]).exists():
        inputs += ["-i", str(music["file"])]
        vol = float(music.get("volume", 0.15))
        duck = music.get("duck", True)
        if duck:
            filters.append(
                f"[{idx}:a]volume={vol}[m];[m][voice]sidechaincompress=threshold=0.05:ratio=8:attack=20:release=400[bg];"
                f"[bg][voice]amix=inputs=2:duration=first:dropout_transition=2,afade=t=out:st=999:d=2[aout]"
            )
        else:
            filters.append(f"[{idx}:a]volume={vol}[m];[m][voice]amix=inputs=2:duration=first[aout]")
    else:
        filters.append("[voice]anull[aout]")

    fc = ";".join(filters)
    # fix fade using duration of video
    dur = _duration(video)
    fc = fc.replace("st=999", f"st={max(dur - 2, 0):.2f}")
    _run(
        [ffmpeg_bin(), "-y", *inputs, "-filter_complex", fc, "-map", "0:v", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", str(dest)]
    )


def _write_ass(sheet: dict, dest: Path) -> None:
    style = (
        "Style: Default,DejaVu Sans,42,&H00FFFFFF,&H000000FF,&H64000000,&H00000000,"
        "0,0,0,0,100,100,0,0,1,2,0,2,40,40,160,1"
    )
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "WrapStyle: 2",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        style,
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for sub in sheet.get("subtitles") or []:
        start = _ts(sub["start"])
        end = _ts(sub["end"])
        text = sub["text"].replace("\n", "\\N")
        lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")
    dest.write_text("\n".join(lines), encoding="utf-8")


def _ts(sec: float) -> str:
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"
