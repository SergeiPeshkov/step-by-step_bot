// Вертикальная обложка 9:16 для плеера: /og/<slug>-v.png
import type { APIContext } from "astro";
import { ARTICLES, formatDate, type Article } from "../../lib/articles";
import { RESERVED } from "../../lib/reserved";
import { renderOg } from "../../lib/og";

export function getStaticPaths() {
  return ARTICLES.filter((a) => !RESERVED.has(a.slug)).map((a) => ({ params: { slug: a.slug }, props: { a } }));
}

export async function GET({ props, site }: APIContext) {
  const a = (props as { a: Article }).a;
  const png = await renderOg({
    vertical: true,
    title: a.title,
    badge: a.actualDate ? `Актуально на ${formatDate(a.actualDate)}` : undefined,
    domain: site && !site.hostname.endsWith("example.ru") ? site.hostname : undefined,
  });
  return new Response(png, { headers: { "Content-Type": "image/png" } });
}
