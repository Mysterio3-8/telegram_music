# Деплой на VPS

Прод: `ssh news-rewriter-vps`, код в `/opt/tg-music-bot`.

## Сервисы (systemd)

| Юнит | Роль |
|---|---|
| `tg-music-bot` | Telegram polling |
| `tg-music-worker` | Celery, обогащение загрузок (очередь по умолчанию) |
| `tg-music-youtube` | Celery, YouTube-импорт (очередь `youtube`, лимит параллельности) |
| `tg-music-youtube-scan.timer` | ежедневная проверка источников на новые видео (§11) |

Файлы юнитов — в этой папке. Установка нового юнита:
```bash
cp deploy/<unit> /etc/systemd/system/ && systemctl daemon-reload && systemctl enable --now <unit>
```

## Обычный деплой

`/deploy` или вручную:
```bash
ssh news-rewriter-vps "cd /opt/tg-music-bot && git pull && .venv/bin/pip install -q -r requirements.txt && .venv/bin/alembic upgrade head && systemctl restart tg-music-bot tg-music-worker tg-music-youtube"
```

## Управление YouTube-источниками

Всё из бота: `/admin` → 🎬 YouTube-источники →
- 🔴/🟢 глобальный выключатель импортёра (флаг в БД, переживает рестарт);
- ➕ Добавить канал (прислать ссылку — импорт стартует сам);
- по каждому источнику: проверить сейчас / отключить / удалить.

CLI (эквивалент, если нужно с сервера):
```bash
.venv/bin/python -m app.cli.youtube add <url>     # добавить + запустить импорт
.venv/bin/python -m app.cli.youtube list          # статус источников
.venv/bin/python -m app.cli.youtube scan <id|all> # пересканировать
.venv/bin/python -m app.cli.youtube recover       # вернуть оборванные задачи
```

## Системные зависимости
`ffmpeg`, `libchromaprint-tools` (fpcalc), `redis-server`, `yt-dlp` (pip).
