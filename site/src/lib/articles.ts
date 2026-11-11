// Чтение articles.json, который выгружает бот командой /articles.
// Обязательные поля бот уже отдаёт: title, slug, body, videos, sources, actual_date, updated_at.
// Необязательные поля сайт понимает заранее, бот начнёт их отдавать позже:
//   shelf        — полка (id из config.ts или её название)
//   audience     — для кого: ["people", "ip", "selfemployed", "business"]
//   summary      — { essence, todo, deadline }: короткий текст на один экран
//   replaced_by  — slug новой версии, если правило изменилось
//   rule_changed — true, если правило изменилось, а новой версии ещё нет
//   published_at — дата первой публикации
import raw from "../data/articles.json";
import { AUDIENCES, OTHER_SHELF, SHELVES } from "../config";

export type Source = { fact: string; source?: string | null };
export type VideoLink = { platform: string; url: string };
export type Block = { kind: "h" | "p"; text: string };

export type Article = {
  id: number;
  slug: string;
  title: string;
  blocks: Block[];
  plain: string;
  videos: VideoLink[];
  sources: Source[];
  actualDate: Date | null;
  updatedAt: Date | null;
  publishedAt: Date | null;
  shelf: { id: string; title: string; hint: string };
  audience: string[];
  summary: { essence: string; todo: string; deadline: string } | null;
  lead: string;
  replacedBy: string | null;
  ruleChanged: boolean;
};

const toDate = (v: unknown): Date | null => {
  if (!v || typeof v !== "string") return null;
  const d = new Date(v);
  return isNaN(d.getTime()) ? null : d;
};

const findShelf = (v: unknown) => {
  const s = String(v ?? "").trim().toLowerCase();
  if (!s) return OTHER_SHELF;
  return SHELVES.find((x) => x.id === s || x.title.toLowerCase() === s) ?? OTHER_SHELF;
};

const audienceIds = (v: unknown): string[] => {
  const list = Array.isArray(v) ? v : v ? [v] : [];
  return list
    .map((a) => String(a).trim().toLowerCase())
    .map((a) => AUDIENCES.find((x) => x.id === a || x.title.toLowerCase() === a)?.id)
    .filter((a): a is string => Boolean(a));
};

// Бот пишет простой текст: абзацы через пустую строку, подзаголовок — короткая отдельная строка.
function parseBody(body: string): Block[] {
  return body
    .replace(/\r\n/g, "\n")
    .split(/\n\s*\n/)
    .map((p) => p.trim())
    .filter(Boolean)
    .map((p) => {
      const oneLine = !p.includes("\n");
      const looksLikeHeading = oneLine && p.length <= 80 && !/[.!?…:;,]$/.test(p);
      return { kind: looksLikeHeading ? "h" : "p", text: p.replace(/\n/g, " ") } as Block;
    });
}

function normalize(a: any): Article {
  const blocks = parseBody(String(a.body ?? ""));
  const firstPara = blocks.find((b) => b.kind === "p")?.text ?? "";
  const s = a.summary;
  return {
    id: Number(a.id),
    slug: String(a.slug),
    title: String(a.title ?? "").trim(),
    blocks,
    plain: blocks.map((b) => b.text).join(" "),
    videos: Array.isArray(a.videos) ? a.videos.filter((v: any) => v?.url) : [],
    sources: Array.isArray(a.sources) ? a.sources : [],
    actualDate: toDate(a.actual_date),
    updatedAt: toDate(a.updated_at),
    publishedAt: toDate(a.published_at) ?? toDate(a.updated_at),
    shelf: findShelf(a.shelf),
    audience: audienceIds(a.audience),
    summary: s && (s.essence || s.todo || s.deadline) ? { essence: s.essence ?? "", todo: s.todo ?? "", deadline: s.deadline ?? "" } : null,
    lead: firstPara.length > 260 ? firstPara.slice(0, 257).replace(/\s+\S*$/, "") + "…" : firstPara,
    replacedBy: a.replaced_by ? String(a.replaced_by) : null,
    ruleChanged: Boolean(a.rule_changed || a.replaced_by),
  };
}

const list: any[] = Array.isArray((raw as any)?.articles) ? (raw as any).articles : [];

export const ARTICLES: Article[] = list
  .filter((a) => a && a.slug && a.title)
  .map(normalize)
  .sort((x, y) => (y.publishedAt?.getTime() ?? 0) - (x.publishedAt?.getTime() ?? 0));

export const bySlug = (slug: string) => ARTICLES.find((a) => a.slug === slug) ?? null;

export const onShelf = (shelfId: string) => ARTICLES.filter((a) => a.shelf.id === shelfId);

export function related(article: Article, limit = 4): Article[] {
  return ARTICLES.filter((a) => a.shelf.id === article.shelf.id && a.slug !== article.slug && !a.replacedBy).slice(0, limit);
}

export function usedShelves() {
  const all = [...SHELVES, OTHER_SHELF];
  return all
    .map((s) => ({ ...s, count: onShelf(s.id).length }))
    .filter((s) => s.count > 0 || s.id !== OTHER_SHELF.id);
}

export const formatDate = (d: Date | null) =>
  d ? d.toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric", timeZone: "Europe/Moscow" }) : "";

export const audienceTitle = (id: string) => AUDIENCES.find((a) => a.id === id)?.title ?? id;
