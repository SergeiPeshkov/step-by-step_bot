import type { APIContext } from "astro";
import { SITE } from "../../config";
import { renderOg } from "../../lib/og";

export async function GET({ site }: APIContext) {
  const png = await renderOg({ title: SITE.tagline, domain: site && !site.hostname.endsWith("example.ru") ? site.hostname : undefined });
  return new Response(png, { headers: { "Content-Type": "image/png" } });
}
