// Ключ IndexNow: по нему Яндекс проверяет, что сообщения о новых страницах шлёт владелец сайта.
// Ключ задаётся переменной INDEXNOW_KEY при сборке (бот передаёт свой из .env).
export const GET = () => new Response(process.env.INDEXNOW_KEY ?? "", { headers: { "Content-Type": "text/plain; charset=utf-8" } });
