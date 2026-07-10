---
description: Задеплоить текущий main на VPS (git push → pull → restart)
---
1. Убедись, что тесты зелёные: `.\.venv\Scripts\python.exe -m pytest -q`. Красные — не деплоить.
2. Закоммить и запушь изменения в `origin main` (remote — SSH: git@github.com:Mysterio3-8/telegram_music.git).
3. Обнови сервер:
   ```bash
   ssh news-rewriter-vps "cd /opt/tg-music-bot && git pull && systemctl restart tg-music-bot && sleep 5 && systemctl is-active tg-music-bot && journalctl -u tg-music-bot -n 5 --no-pager"
   ```
4. Проверь в логах строку `Run polling for bot @tgram_music_bot`. Ошибки — покажи и разберись, откатывать через `git revert` + повторный деплой.

Если менялись зависимости — перед restart добавь `.venv/bin/pip install -q -r requirements.txt`.
