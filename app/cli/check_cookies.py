"""Проверка куки YouTube: подхватились ли, и работают ли на самом деле.

    python -m app.cli.check_cookies

Зачем отдельная команда. Куки — это единственное место, где «настроил» и
«работает» расходятся молча: путь с опечаткой, файл не в том формате, права не
те, сессия протухла — во всех случаях yt-dlp просто идёт без авторизации, а
отказы выглядят как обычный антибот. Команда проверяет всю цепочку сразу и
говорит, на каком шаге сломалось.

Проверяется на возрастном ролике: без авторизации YouTube отвечает «Sign in to
confirm your age», с рабочими куки отдаёт метаданные.
"""
import os
import stat
import sys
from pathlib import Path

from app.config import settings

# Ролик с возрастным ограничением — тест-кейс самого yt-dlp.
AGE_GATED = "https://www.youtube.com/watch?v=HtVdAasjOgU"


def _check_file() -> Path | None:
    configured = settings.youtube_cookies_path
    if not configured:
        print("❌ YOUTUBE_COOKIES_PATH не задан в .env")
        print("   Добавьте строку: YOUTUBE_COOKIES_PATH=/opt/tg-music-bot/youtube-cookies.txt")
        return None

    path = Path(configured)
    print(f"путь: {configured}")
    if not path.exists():
        print("❌ файла нет — YouTube идёт без авторизации")
        return None

    size = path.stat().st_size
    print(f"✅ файл на месте, {size} байт")
    if size < 100:
        print("⚠️  подозрительно мало: похоже, экспорт пустой")

    head = path.read_text(encoding="utf-8", errors="replace")[:200]
    if "# Netscape HTTP Cookie File" not in head and "\t" not in head:
        print("⚠️  не похоже на формат Netscape — yt-dlp такой файл не прочитает")

    if os.name != "nt":
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o077:
            print(f"⚠️  права {oct(mode)} — файл читают посторонние. Нужно: chmod 600 {configured}")
        else:
            print(f"✅ права {oct(mode)}")
    return path


def _check_live() -> bool:
    import yt_dlp

    from app.services.youtube.downloader import youtube_opts

    opts = {**youtube_opts(), "skip_download": True, "quiet": True,
            "no_warnings": True, "ignoreerrors": False}
    print(f"\nпробую возрастной ролик через {opts.get('proxy') or 'прямое соединение'}…")
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(AGE_GATED, download=False)
    except Exception as exc:  # noqa: BLE001 — нам важен текст отказа, а не тип
        text = str(exc).split("\n")[0]
        print(f"❌ не вышло: {text[:130]}")
        if "confirm your age" in text.lower():
            print("   → куки не подхватились или сессия протухла")
        elif "not a bot" in text.lower():
            print("   → упёрлись в антибот, а не в возраст: проверьте YOUTUBE_PROXY")
        return False
    print(f"✅ работает: «{(info or {}).get('title')}»")
    return True


def main() -> int:
    print("=== куки YouTube ===")
    if _check_file() is None:
        return 1
    return 0 if _check_live() else 1


if __name__ == "__main__":
    sys.exit(main())
