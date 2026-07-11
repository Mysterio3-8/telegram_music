---
description: Задеплоить текущий main на VPS (git push → pull → миграции → restart)
---
1. Убедись, что тесты зелёные: `.\.venv\Scripts\python.exe -m pytest -q`. Красные — не деплоить.
2. Закоммить и запушь изменения в `origin main` (remote — SSH: git@github.com:Mysterio3-8/telegram_music.git).
3. Обнови сервер:
   ```bash
   ssh news-rewriter-vps "cd /opt/tg-music-bot && git pull && .venv/bin/pip install -q -r requirements.txt && .venv/bin/alembic upgrade head && systemctl restart tg-music-bot tg-music-worker && sleep 5 && systemctl is-active tg-music-bot tg-music-worker && journalctl -u tg-music-bot -n 5 --no-pager"
   ```
4. Проверь в логах строку `Run polling for bot @tgram_music_bot`. Ошибки — покажи и разберись, откатывать через `git revert` + повторный деплой.

Схемой БД управляет Alembic — при изменении моделей сгенерируй миграцию локально
(`alembic revision --autogenerate -m "..."` против пустой временной БД) и закоммить её.
Воркер `tg-music-worker` (Celery) обрабатывает обогащение загруженных треков — если его нет,
загрузки всё равно работают (трек создаётся сразу, отпечаток просто не считается).
