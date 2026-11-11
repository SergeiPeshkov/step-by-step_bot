from __future__ import annotations

from pathlib import Path
from typing import Protocol

import httpx
from PIL import Image, ImageDraw, ImageFont

from app.config import settings


class ImageAdapter(Protocol):
    async def generate(self, prompt: str, dest: Path, model: str) -> tuple[Path, float]: ...


class StubImage:
    async def generate(self, prompt: str, dest: Path, model: str) -> tuple[Path, float]:
        dest.parent.mkdir(parents=True, exist_ok=True)
        img = Image.new("RGB", (1080, 1920), (18, 24, 32))
        draw = ImageDraw.Draw(img)
        draw.ellipse((440, 780, 640, 980), fill=(210, 160, 70))
        draw.rectangle((520, 980, 560, 1180), fill=(40, 32, 24))
        draw.polygon([(200, 1600), (540, 900), (880, 1600)], outline=(80, 90, 100))
        try:
            font = ImageFont.truetype(str(settings.font_path), 28)
        except OSError:
            font = ImageFont.load_default()
        draw.text((60, 80), (prompt[:80] + "…") if len(prompt) > 80 else prompt, fill=(180, 190, 200), font=font)
        img.save(dest)
        return dest, 0.0


class OpenAIImage:
    async def generate(self, prompt: str, dest: Path, model: str) -> tuple[Path, float]:
        dest.parent.mkdir(parents=True, exist_ok=True)
        headers = {"Authorization": f"Bearer {settings.image_api_key}"}
        payload = {"model": model or settings.image_model, "prompt": prompt, "size": "1024x1792", "n": 1}
        url = f"{(settings.image_base_url or settings.llm_base_url).rstrip('/')}/images/generations"
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
        b64 = data["data"][0].get("b64_json")
        if b64:
            import base64

            dest.write_bytes(base64.b64decode(b64))
        else:
            img_url = data["data"][0]["url"]
            async with httpx.AsyncClient(timeout=120) as client:
                img = await client.get(img_url)
                dest.write_bytes(img.content)
        cost = 8.0 if model == settings.image_quality_model else 3.0
        return dest, cost


def get_image_adapter() -> ImageAdapter:
    if settings.image_provider == "openai" and settings.image_api_key:
        return OpenAIImage()
    return StubImage()
