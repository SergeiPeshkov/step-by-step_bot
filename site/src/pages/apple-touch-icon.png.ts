import { renderIcon } from "../lib/og";
export const GET = () => new Response(renderIcon(180), { headers: { "Content-Type": "image/png" } });
