// Ролик на странице (FR-L02): встраиваем плеер площадки, если умеем, иначе даём ссылки.
import type { VideoLink } from "./articles";

export const PLATFORM_LABEL: Record<string, string> = {
  vk: "VK Видео",
  rutube: "Rutube",
  ok: "Одноклассники",
  youtube: "YouTube",
  dzen: "Дзен",
  telegram: "Telegram",
  instagram: "Instagram",
  max: "MAX",
};

// Порядок, в котором выбираем плеер: сначала российские площадки.
const PRIORITY = ["vk", "rutube", "ok", "youtube"];

export function embedUrl(v: VideoLink): string | null {
  const u = v.url;
  let m: RegExpMatchArray | null;
  switch (v.platform) {
    case "vk":
      m = u.match(/video(-?\d+)_(\d+)/);
      return m ? `https://vk.com/video_ext.php?oid=${m[1]}&id=${m[2]}&hd=2` : null;
    case "rutube":
      m = u.match(/rutube\.ru\/(?:video|shorts)\/([0-9a-f]{20,})/i);
      return m ? `https://rutube.ru/play/embed/${m[1]}` : null;
    case "ok":
      m = u.match(/ok\.ru\/video\/(\d+)/);
      return m ? `https://ok.ru/videoembed/${m[1]}` : null;
    case "youtube":
      m = u.match(/(?:shorts\/|v=|youtu\.be\/|embed\/)([\w-]{11})/);
      return m ? `https://www.youtube.com/embed/${m[1]}` : null;
    default:
      return null;
  }
}

export function pickPlayer(videos: VideoLink[]): string | null {
  const sorted = [...videos].sort((a, b) => rank(a.platform) - rank(b.platform));
  for (const v of sorted) {
    const e = embedUrl(v);
    if (e) return e;
  }
  return null;
}

const rank = (p: string) => {
  const i = PRIORITY.indexOf(p);
  return i === -1 ? 99 : i;
};
