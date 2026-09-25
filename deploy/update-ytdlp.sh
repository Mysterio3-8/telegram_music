#!/usr/bin/env bash
# Обновляет yt-dlp и перезапускает воркеры, если версия сменилась.
#
# Живой прогон 25.09: yt-dlp на проде был от 04.07 — почти три месяца. YouTube
# отвечал 403 на скачивание, за сутки 84 провала, и запасной источник для
# треков под DRM не работал вовсе. requirements.lock yt-dlp намеренно не
# закрепляет, но деплой ставит пакеты без -U, и версия дня установки оставалась
# навсегда. Воркеры держат модуль в памяти, поэтому без перезапуска новая
# версия не подхватится.
set -u
cd /opt/tg-music-bot || exit 0
before=$(./.venv/bin/yt-dlp --version 2>/dev/null || echo none)
nice ./.venv/bin/pip install -q -U yt-dlp || exit 0
after=$(./.venv/bin/yt-dlp --version 2>/dev/null || echo none)
if [ "$before" != "$after" ]; then
    echo "yt-dlp: $before → $after, перезапускаю воркеры"
    systemctl try-restart tg-music-youtube-user tg-music-worker
else
    echo "yt-dlp: $after — свежий"
fi
