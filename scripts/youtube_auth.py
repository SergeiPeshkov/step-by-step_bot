"""Один раз получить YOUTUBE_REFRESH_TOKEN для публикации в YouTube.

1. В Google Cloud Console создайте проект, включите «YouTube Data API v3»,
   создайте OAuth Client ID типа «Desktop app».
2. Впишите YOUTUBE_CLIENT_ID и YOUTUBE_CLIENT_SECRET в .env.
3. Запустите: python scripts/youtube_auth.py
   Откроется браузер: войдите в Google-аккаунт канала и разрешите доступ.
4. Скрипт напечатает YOUTUBE_REFRESH_TOKEN — впишите его в .env.
"""

from __future__ import annotations

import http.server
import secrets
import sys
import urllib.parse
import webbrowser
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import settings  # noqa: E402

PORT = 8765
REDIRECT = f"http://127.0.0.1:{PORT}/"
SCOPE = "https://www.googleapis.com/auth/youtube.upload"


def main() -> None:
    if not settings.youtube_client_id or not settings.youtube_client_secret:
        sys.exit("Сначала впишите YOUTUBE_CLIENT_ID и YOUTUBE_CLIENT_SECRET в .env")
    state = secrets.token_urlsafe(16)
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(
        {
            "client_id": settings.youtube_client_id,
            "redirect_uri": REDIRECT,
            "response_type": "code",
            "scope": SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
    )
    result: dict = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            result.update({k: v[0] for k, v in q.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("Готово, можно закрыть вкладку и вернуться в консоль.".encode("utf-8"))

        def log_message(self, *args):
            pass

    print("Открываю браузер. Если не открылся, перейдите по ссылке:\n" + url)
    webbrowser.open(url)
    with http.server.HTTPServer(("127.0.0.1", PORT), Handler) as server:
        while "code" not in result and "error" not in result:
            server.handle_request()
    if result.get("state") != state or "code" not in result:
        sys.exit(f"Не получилось: {result.get('error', 'неверный ответ')}")
    r = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": result["code"],
            "client_id": settings.youtube_client_id,
            "client_secret": settings.youtube_client_secret,
            "redirect_uri": REDIRECT,
            "grant_type": "authorization_code",
        },
        timeout=60,
    )
    r.raise_for_status()
    token = r.json().get("refresh_token")
    if not token:
        sys.exit("Google не вернул refresh token. Удалите доступ приложения в аккаунте Google и запустите снова.")
    print("\nВпишите в .env:\nYOUTUBE_REFRESH_TOKEN=" + token)


if __name__ == "__main__":
    main()
