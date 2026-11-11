from __future__ import annotations

import os
import shutil
from pathlib import Path


def ffmpeg_bin() -> str:
    found = shutil.which("ffmpeg")
    if found:
        return found
    for candidate in (
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "ffmpeg" / "bin" / "ffmpeg.exe",
        Path(r"C:\ffmpeg\bin\ffmpeg.exe"),
    ):
        if candidate.exists():
            return str(candidate)
    return "ffmpeg"


def ffprobe_bin() -> str:
    found = shutil.which("ffprobe")
    if found:
        return found
    ff = Path(ffmpeg_bin())
    probe = ff.with_name("ffprobe.exe" if ff.suffix == ".exe" else "ffprobe")
    return str(probe) if probe.exists() else "ffprobe"
