// Карта сайта для Яндекса и других поисковиков.
import type { APIContext } from "astro";
import { ARTICLES, HAS_SHELVES, usedShelves } from "../lib/articles";
import { RESERVED } from "../lib/reserved";

export function GET({ site }: APIContext) {
  const u = (p: string) => new URL(p, site).href;
  const rows: { loc: string; lastmod?: string }[] = [
    { loc: u("") },
    ...(HAS_SHELVES ? [{ loc: u("polka/") }] : []),
    { loc: u("voprosy/") },
    { loc: u("izmeneniya/") },
    ...usedShelves().map((s) => ({ loc: u(`polka/${s.id}/`) })),
    ...ARTICLES.filter((a) => !RESERVED.has(a.slug) && !a.replacedBy).map((a) => ({
      loc: u(`${a.slug}/`),
      lastmod: (a.updatedAt ?? a.publishedAt)?.toISOString().slice(0, 10),
    })),
  ];
  const xml =
    `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n` +
    rows.map((r) => `  <url><loc>${r.loc}</loc>${r.lastmod ? `<lastmod>${r.lastmod}</lastmod>` : ""}</url>`).join("\n") +
    `\n</urlset>\n`;
  return new Response(xml, { headers: { "Content-Type": "application/xml; charset=utf-8" } });
}
