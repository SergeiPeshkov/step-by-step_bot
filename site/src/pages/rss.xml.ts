// RSS-лента: новые и обновлённые вопросы. Её понимают Яндекс, Дзен и читалки.
import type { APIContext } from "astro";
import { ARTICLES, metaDescription } from "../lib/articles";
import { RESERVED } from "../lib/reserved";
import { SITE } from "../config";

const esc = (s: string) => s.replace(/[<>&'"]/g, (c) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", "'": "&apos;", '"': "&quot;" })[c]!);

export function GET({ site }: APIContext) {
  const items = ARTICLES.filter((a) => !RESERVED.has(a.slug) && !a.replacedBy).slice(0, 50);
  const u = (p: string) => new URL(p, site).href;
  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
<title>${esc(SITE.name)}</title>
<link>${u("")}</link>
<description>${esc(SITE.tagline)}</description>
<language>ru</language>
<atom:link href="${u("rss.xml")}" rel="self" type="application/rss+xml"/>
${items
  .map(
    (a) => `<item>
<title>${esc(a.title)}</title>
<link>${u(`${a.slug}/`)}</link>
<guid isPermaLink="true">${u(`${a.slug}/`)}</guid>
<description>${esc(metaDescription(a))}</description>
${a.publishedAt ? `<pubDate>${a.publishedAt.toUTCString()}</pubDate>` : ""}
<enclosure url="${u(`og/${a.slug}.png`)}" type="image/png" length="0"/>
</item>`,
  )
  .join("\n")}
</channel>
</rss>
`;
  return new Response(xml, { headers: { "Content-Type": "application/rss+xml; charset=utf-8" } });
}
