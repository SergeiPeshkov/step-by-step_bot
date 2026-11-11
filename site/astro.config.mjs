// Настройки сборки сайта «По полочкам».
// Адрес сайта задаётся переменной SITE_URL (например, https://popolochkam.ru),
// поэтому, когда домен будет выбран, код менять не нужно.
import { defineConfig } from "astro/config";

export default defineConfig({
  site: process.env.SITE_URL || "https://example.ru",
  trailingSlash: "always",
  build: { format: "directory" },
});
