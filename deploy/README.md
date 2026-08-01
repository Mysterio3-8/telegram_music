# Деплой на VPS

Прод: `ssh news-rewriter-vps`, код в `/opt/tg-music-bot`.

## Сервисы (systemd)

| Юнит | Роль |
|---|---|
| `tg-music-bot` | Telegram polling |
| `tg-music-worker` | Celery, обогащение загрузок + импорт из Telegram-канала (очереди `celery`, `telegram_channel`) |
| `tg-music-youtube` | Celery, массовые сканы каналов/плейлистов (очередь `youtube`, concurrency=1) |
| `tg-music-youtube-user` | Celery, ссылки от пользователей бота (очередь `youtube_user`, concurrency=2) — отдельно от `tg-music-youtube`, чтобы не ждать за бэклогом массовых сканов |
| `tg-music-youtube-scan.timer` | ежедневная проверка источников на новые видео (§11), заодно дёргает SoundCloud scan-due |
| `tg-music-soundcloud` | Celery, SoundCloud-импорт (очередь `soundcloud`, concurrency=3 — темп 3000/сутки на ротации прокси; без прокси вернуть 1) |
| `tg-music-telegram-channel-scan.timer` | ежедневная проверка канала на новые посты |
| `tg-music-catalog-maintain.timer` | ежедневно в 04:00: привязка треков к артистам, подборки по жанрам, автопродление Premium, сторож диска |

Отдельного юнита `tg-music-telegram-channel` больше нет: его очередь разбирает
`tg-music-worker`. На боксе с одним ядром отдельный интерпретатор под редкую
очередь не окупался.

### ⚠️ Юниты не доезжают обычным деплоем

`git pull` обновляет `deploy/*.service` в репозитории, но systemd читает
`/etc/systemd/system` — сервер продолжит работать по старой конфигурации.
После правки любого юнита **на сервере от root**:

```bash
cd /opt/tg-music-bot && bash deploy/install-units.sh
```

Скрипт идемпотентен: раскладывает юниты, ставит logrotate/journald-лимиты и
fail2ban, гасит слитый `tg-music-telegram-channel`, перезапускает сервисы.

## Обычный деплой

`/deploy` или вручную:
```bash
ssh news-rewriter-vps "cd /opt/tg-music-bot && git pull && .venv/bin/pip install -q -r requirements.txt && .venv/bin/alembic upgrade head && systemctl restart tg-music-bot tg-music-worker tg-music-youtube tg-music-youtube-user tg-music-soundcloud tg-music-telegram-channel"
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

## Мировой каталог (SPEC-КАТАЛОГ)

```bash
.venv/bin/python -m app.cli.genres seed              # дерево жанров (идемпотентно)
.venv/bin/python -m app.cli.research country US --limit 1200   # артисты страны из MusicBrainz
bash deploy/research_world.sh                        # очередь стран целиком (запускать под setsid nohup)
.venv/bin/python -m app.cli.research enrich --limit 500        # дообогатить артистов без mbid
.venv/bin/python -m app.cli.research attach-sources  # SoundCloud/YouTube-источники артистов → в закачку
.venv/bin/python -m app.cli.research stats
```

⚠️ MusicBrainz — 1 req/sec **на IP**: два прогона параллельно запускать нельзя
(троттлинг у каждого процесса свой). Долгие прогоны — только `setsid nohup … &`,
ожидание завершения — по PID (`kill -0`), не по `pgrep` имени команды: pgrep
ловит сам вотчер и цикл не заканчивается никогда.

Обслуживание (то же, что делает таймер):
```bash
.venv/bin/python -m app.cli.artists bind-tracks   # привязать новые треки к артистам
.venv/bin/python -m app.cli.artists unbound       # имена без артиста-сущности — на чистку
.venv/bin/python -m app.cli.genres make-playlists # подборки редакции по жанрам
```

## Системные зависимости
`ffmpeg`, `libchromaprint-tools` (fpcalc), `redis-server`, `yt-dlp` и `telethon` (pip).
