# Деплой на VPS

Прод: `ssh news-rewriter-vps`, код в `/opt/tg-music-bot`.

## Сервисы (systemd)

| Юнит | Роль |
|---|---|
| `tg-music-bot` | Telegram polling |
| `tg-music-worker` | Celery, обогащение загрузок (очередь по умолчанию) |
| `tg-music-youtube` | Celery, YouTube-импорт (очередь `youtube`, лимит параллельности) |
| `tg-music-youtube-scan.timer` | ежедневная проверка источников на новые видео (§11) |
| `tg-music-telegram-channel` | Celery, импорт из личного Telegram-канала (очередь `telegram_channel`, БЕЗ файлов на диске) |
| `tg-music-telegram-channel-scan.timer` | ежедневная проверка канала на новые посты |

Файлы юнитов — в этой папке. Установка нового юнита:
```bash
cp deploy/<unit> /etc/systemd/system/ && systemctl daemon-reload && systemctl enable --now <unit>
```

## Обычный деплой

`/deploy` или вручную:
```bash
ssh news-rewriter-vps "cd /opt/tg-music-bot && git pull && .venv/bin/pip install -q -r requirements.txt && .venv/bin/alembic upgrade head && systemctl restart tg-music-bot tg-music-worker tg-music-youtube tg-music-telegram-channel"
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

## Импорт из личного Telegram-канала (без файлов на диске)

Файл никогда не лежит на сервере: скачивается временно только для отпечатка,
сразу перезаливается через бота (получает свой `tg_file_id`) и байты отбрасываются.

**Один раз перед первым использованием** — вход в личный аккаунт (интерактивно,
номер телефона + код из Telegram/SMS):
```bash
ssh news-rewriter-vps
cd /opt/tg-music-bot
# TELEGRAM_API_ID / TELEGRAM_API_HASH — получить на https://my.telegram.org
.venv/bin/python -m app.cli.telegram_login
```
Сессия сохранится в `TELEGRAM_SESSION_PATH` — держать вне git, права 600 (даёт
доступ к аккаунту, как и сам номер телефона). Дальше вход не требуется.

Управление — всё из бота: `/admin` → 📡 Мой Telegram-канал →
- 🔴/🟢 глобальный выключатель импортёра;
- ➕ Добавить канал (пришлёте @username/ссылку — импорт стартует сам);
- по каждому источнику: проверить сейчас / отключить / удалить.

CLI-эквивалент:
```bash
.venv/bin/python -m app.cli.telegram_channel add <@channel>
.venv/bin/python -m app.cli.telegram_channel list
.venv/bin/python -m app.cli.telegram_channel scan <id|all>
.venv/bin/python -m app.cli.telegram_channel recover
```

## Системные зависимости
`ffmpeg`, `libchromaprint-tools` (fpcalc), `redis-server`, `yt-dlp` и `telethon` (pip).
