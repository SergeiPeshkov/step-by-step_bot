from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Protocol

from app.config import settings
from app.assembler.ffmpeg import ffmpeg_bin


class VideoAdapter(Protocol):
    async def generate(self, prompt: str, dest: Path, model: str, duration: float) -> tuple[Path, float]: ...


class StubVideo:
    async def generate(self, prompt: str, dest: Path, model: str, duration: float) -> tuple[Path, float]:
        dest.parent.mkdir(parents=True, exist_ok=True)
        color = "0x121820"
        cmd = [
            ffmpeg_bin(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s=1080x1920:d={max(duration, 1):.2f}:r=30",
            "-f",
            "lavfi",
            "-i",
            f"anoisesrc=d={max(duration, 1):.2f}:c=pink:a=0.01",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(dest),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return dest, 0.0


def get_video_adapter() -> VideoAdapter:
    return StubVideo()
