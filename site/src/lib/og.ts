// Картинки 1200×630 для соцсетей и поиска: вопрос крупно в фирменном стиле Г.
// Рисуются при сборке (satori → SVG → PNG), внешних сервисов не нужно.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import satori from "satori";
import { Resvg } from "@resvg/resvg-js";
import { SITE } from "../config";

const C = { bg: "#FBF3E7", text: "#3A2A1F", muted: "#6B5B4C", accent: "#C2582F", green: "#1F4D3A", plate: "#F1DFC8" };

const font = (pkg: string, file: string) => readFileSync(join(process.cwd(), "node_modules", "@fontsource", pkg, "files", file));
let fonts: any[] | null = null;
const loadFonts = () =>
  (fonts ??= [
    { name: "Serif", data: font("pt-serif", "pt-serif-cyrillic-700-normal.woff"), weight: 700, style: "normal" },
    { name: "SerifLatin", data: font("pt-serif", "pt-serif-latin-700-normal.woff"), weight: 700, style: "normal" },
    { name: "Sans", data: font("golos-text", "golos-text-cyrillic-600-normal.woff"), weight: 600, style: "normal" },
    { name: "SansLatin", data: font("golos-text", "golos-text-latin-600-normal.woff"), weight: 600, style: "normal" },
  ]);

const h = (type: string, style: Record<string, unknown>, children?: unknown) => ({ type, props: { style, children } });

const shelf = (w: number, color: string) => h("div", { width: w, height: 14, borderRadius: 4, background: color });

export async function renderOg(opts: { title: string; badge?: string; domain?: string; vertical?: boolean }): Promise<Buffer> {
  const len = opts.title.length;
  const W = opts.vertical ? 720 : 1200;
  const H = opts.vertical ? 1280 : 630;
  const size = opts.vertical ? (len > 90 ? 52 : len > 50 ? 62 : 74) : len > 90 ? 50 : len > 60 ? 58 : len > 35 ? 68 : 80;
  const tree = h(
    "div",
    { width: W, height: H, boxSizing: "border-box", display: "flex", flexDirection: "column", justifyContent: "space-between", background: opts.vertical ? C.plate : C.bg, padding: opts.vertical ? "72px 56px 120px" : "56px 72px", fontFamily: "Sans, SansLatin", color: C.text },
    [
      h("div", { display: "flex", alignItems: "center", gap: 18 }, [
        h("div", { display: "flex", flexDirection: "column", gap: 7 }, [shelf(56, C.text), shelf(36, C.accent), shelf(56, C.text)]),
        h("div", { fontSize: 36, fontWeight: 600 }, SITE.name),
      ]),
      h("div", { display: "flex", flexGrow: 1, alignItems: "center", fontFamily: "Serif, SerifLatin", fontWeight: 700, fontSize: size, lineHeight: 1.15, maxWidth: W - 150 }, opts.title),
      h("div", { display: "flex", alignItems: opts.vertical ? "flex-start" : "center", justifyContent: "space-between", flexDirection: opts.vertical ? "column" : "row", gap: 18 }, [
        opts.badge
          ? h("div", { display: "flex", border: `4px solid ${C.green}`, color: C.green, borderRadius: 14, padding: "8px 20px", fontSize: 28, fontWeight: 600 }, opts.badge)
          : h("div", { display: "flex", fontSize: 28, color: C.muted }, "Законы и правила простыми словами"),
        h("div", { display: "flex", background: C.accent, color: "#fff", borderRadius: 14, padding: "10px 22px", fontSize: 28, fontWeight: 600 }, opts.domain || "Смотреть ролик"),
      ]),
    ],
  );
  const svg = await satori(tree as any, { width: W, height: H, fonts: loadFonts() });
  return new Resvg(svg, { fitTo: { mode: "width", value: W } }).render().asPng();
}

export function renderIcon(size: number): Buffer {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="${size}" height="${size}"><rect width="32" height="32" rx="7" fill="${C.text}"/><rect x="7" y="8" width="18" height="3.5" rx="1.5" fill="${C.bg}"/><rect x="7" y="14.25" width="12" height="3.5" rx="1.5" fill="${C.accent}"/><rect x="7" y="20.5" width="18" height="3.5" rx="1.5" fill="${C.bg}"/></svg>`;
  return new Resvg(svg, { fitTo: { mode: "width", value: size } }).render().asPng();
}
