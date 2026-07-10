---
description: Запустить бота локально (polling)
---
1. Проверь, что `.env` существует и `BOT_TOKEN` заполнен. Если нет — скажи пользователю скопировать `.env.example` в `.env` и вписать токен от @BotFather.
2. Запусти в фоне: `.\.venv\Scripts\python.exe -m app.main`
3. Следи за логами: polling должен стартовать без ошибок. Ошибку `TokenValidationError` объясни как неверный токен.
