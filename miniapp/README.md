# TG Music — Mini App

Telegram Mini App поверх публичного API бота (`app/api`). Ванильный JS (ES-modules),
без сборки: nginx отдаёт эту папку как статику.

## Прод (keybest.cc)

- nginx: статика из `/opt/tg-music-bot/miniapp`, `/api/ → uvicorn :8010` (конфиг — `deploy/nginx-keybest.conf`)
- API-сервис: `deploy/tg-music-api.service` (`systemctl {status,restart} tg-music-api`)
- Авторизация: Telegram WebApp `initData` → `POST /login` → JWT
- Аудио: `GET /tracks/{id}/audio?exp=…&sig=…` — HMAC-подпись вместо JWT
  (тег `<audio>` не умеет слать заголовки), поддержан Range для перемотки

## Dev-стенд локально

```powershell
# 1) БД + 8 треков с настоящими WAV (2 сек) — автоплей проверяется по-настоящему
Remove-Item dev_miniapp.db -ea 0
$env:DATABASE_URL="sqlite+aiosqlite:///dev_miniapp.db"
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe <scratchpad>\seed_dev.py

# 2) API с CORS на дев-порт статики
$env:API_CORS_ORIGINS="http://localhost:5500,http://127.0.0.1:5500"
.\.venv\Scripts\python.exe -m uvicorn app.api.app:app --port 8010

# 3) Статика (или preview_start miniapp из .claude/launch.json)
python -m http.server 5500 --directory miniapp
```

В браузере нет Telegram `initData`, поэтому dev-вход — готовый JWT в
`localStorage["tgmusic-dev-token"]` (см. `api.js: login`). Сгенерировать:

```powershell
.\.venv\Scripts\python.exe -c "from app.api.security import create_access_token; print(create_access_token(5852263277))"
```

## Архитектура

- `src/api.js` — HTTP-клиент: login, каталог, библиотека, premium, оплата
- `src/state.js` — стор + плеер на реальном `<audio>`; `ended` → следующий трек;
  прогресс идёт через отдельный канал `subscribeProgress` (полный re-render
  каждые 250 мс был источником лагов — структура перерисовывается только
  на смену экрана/трека)
- `src/screens/*` — экраны, `src/components/*` — переиспользуемые куски
- `src/styles/tokens.css` — палитра Premium Black Amethyst (тёмная + светлая),
  все цвета только через токены
