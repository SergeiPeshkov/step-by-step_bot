// Маленький поисковый индекс для страницы «Поиск». Собирается вместе с сайтом.
import { ARTICLES } from "../lib/articles";
import { RESERVED } from "../lib/reserved";

export function GET() {
  const items = ARTICLES.filter((a) => !RESERVED.has(a.slug)).map((a) => ({
    s: a.slug,
    t: a.title,
    l: a.lead,
    h: a.shelf.id === "raznoe" ? "" : a.shelf.title,
    a: a.audience,
    x: [a.summary?.essence, a.summary?.todo, a.plain.slice(0, 3000)].filter(Boolean).join(" "),
    c: a.ruleChanged ? 1 : 0,
  }));
  return new Response(JSON.stringify(items), { headers: { "Content-Type": "application/json; charset=utf-8" } });
}
