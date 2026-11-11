import { renderIcon } from "../lib/og";
export const GET = () => new Response(renderIcon(120), { headers: { "Content-Type": "image/png" } });
