// Цвет полки (заметен в стиле B «Полки», в остальных — едва-едва).
const COLORS: Record<string, string> = {
  nalogi: "#2f6fdb", ip: "#7a4cd9", vyplaty: "#d6336c", zhilyo: "#e8590c", zemlya: "#5c940d",
  zhkh: "#1098ad", shtrafy: "#c92a2a", finansy: "#f08c00", krym: "#0b7285", raznoe: "#868e96",
};
export const shelfColor = (id: string) => COLORS[id] ?? "#868e96";
