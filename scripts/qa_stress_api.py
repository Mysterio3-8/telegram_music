"""Стресс и злоупотребления против ЛОКАЛЬНОГО API (127.0.0.1:8010, dev_miniapp.db).

⚠️ Только локальный стенд: на прод не направлять (1 ядро, 961 МБ).
Запуск и что ожидать — docs/qa/STRESS-TEST.md. Из корня проекта:
    $env:DATABASE_URL="sqlite+aiosqlite:///dev_miniapp.db"; $env:PYTHONIOENCODING="utf-8"
    .\\.venv\\Scripts\\python.exe scripts\\qa_stress_api.py
"""
import asyncio
import hashlib
import hmac
import json
import os
import sqlite3
import sys
import time
from urllib.parse import urlencode

import aiohttp

sys.path.insert(0, os.getcwd())
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///dev_miniapp.db")
from app.config import settings  # noqa: E402

BASE = "http://127.0.0.1:8010"
RESULTS = []


def rec(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print(("BUG " if not ok else "ok  ") + name + (f" — {detail}" if detail else ""), flush=True)


def init_data(user_id: int, first_name="QA") -> str:
    fields = {
        "auth_date": str(int(time.time())),
        "query_id": "AAE",
        "user": json.dumps({"id": user_id, "first_name": first_name, "language_code": "ru"}),
    }
    dcs = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", settings.bot_token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


async def login(http, uid):
    async with http.post(f"{BASE}/login", json={"init_data": init_data(uid)}) as r:
        body = await r.json()
        return body["access_token"]


def H(tok, ip="10.0.0.1"):
    return {"Authorization": f"Bearer {tok}", "X-Real-IP": ip}


async def main():
    db = sqlite3.connect("dev_miniapp.db")
    async with aiohttp.ClientSession() as http:
        # --- два обычных (не админ) пользователя ---
        u1, u2 = 900000001 + int(time.time()) % 1000, 900002001 + int(time.time()) % 1000
        t1 = await login(http, u1)
        t2 = await login(http, u2)
        # С 14.09 весь API Mini App закрыт пэйволом: u2 — платящий (гоняем на нём
        # проверки прав и границ), u3 — бесплатный (проверяем сам пэйвол).
        db.execute("update users set premium=1, premium_until=datetime('now','+30 days') where telegram_id=?", (u2,))
        db.commit()
        u3 = 900004001 + int(time.time()) % 1000
        t3 = await login(http, u3)
        track_id = db.execute("select id from tracks order by id limit 1").fetchone()[0]

        # 0. Серверный пэйвол: бесплатный не получает API в обход интерфейса
        for method, path in [("GET", "/library/ids"), ("GET", "/tracks"), ("GET", "/search/live?q=a"), ("POST", "/transfer")]:
            async with http.request(method, f"{BASE}{path}", headers=H(t3, "10.0.9.1"), json={"source": "A — B"}) as r:
                rec(f"paywall: {method} {path} без Premium → 402", r.status == 402, f"status={r.status}")
        async with http.get(f"{BASE}/premium/status", headers=H(t3, "10.0.9.2")) as r:
            rec("paywall: статус Premium доступен бесплатному", r.status == 200, f"status={r.status}")

        # 1. Гонка пробного Premium: 10 параллельных нажатий
        async def trial():
            async with http.post(f"{BASE}/premium/trial", headers=H(t1, "10.1.0.1")) as r:
                return r.status
        statuses = await asyncio.gather(*[trial() for _ in range(10)])
        row = db.execute("select premium_until from users where telegram_id=?", (u1,)).fetchone()
        ok_count = statuses.count(200)
        rec("trial race: одна активация из 10", ok_count == 1, f"200×{ok_count}, statuses={sorted(set(statuses))}, until={row}")

        # 2. Текст песни: бесплатный пользователь перезаписывает чужой/общий текст
        async with http.post(f"{BASE}/tracks/{track_id}/lyrics", headers=H(t3, "10.2.0.1"), json={"text": "VANDAL"}) as r:
            rec("lyrics: не-Premium не может писать текст", r.status in (401, 402, 403), f"status={r.status}")
        big = "A" * 5_000_000
        async with http.post(f"{BASE}/tracks/{track_id}/lyrics", headers=H(t2, "10.2.0.2"), json={"text": big}) as r:
            rec("lyrics: текст 5 МБ отклоняется", r.status in (400, 403, 413, 422), f"status={r.status}")

        # 3. Плейлист: название 1 МБ, пустое, пробелы
        async with http.post(f"{BASE}/playlist", headers=H(t2, "10.3.0.1"), json={"title": "x" * 1_000_000}) as r:
            rec("playlist: название 1 МБ отклоняется", r.status in (400, 413, 422), f"status={r.status}")
            pid = (await r.json()).get("id") if r.status == 201 else None
        if pid is None:
            async with http.post(f"{BASE}/playlist", headers=H(t2, "10.3.0.2"), json={"title": "QA"}) as r:
                pid = (await r.json()).get("id")
        # 4. Плейлист: несуществующий трек
        async with http.post(f"{BASE}/playlists/{pid}/tracks/999999999", headers=H(t2, "10.3.0.3")) as r:
            orphan = db.execute("select count(*) from playlist_tracks where playlist_id=? and track_id=999999999", (pid,)).fetchone()[0]
            rec("playlist: несуществующий трек → 404, без сироты", r.status == 404 and orphan == 0, f"status={r.status}, сирот={orphan}")
        # IDOR: чужой плейлист
        async with http.post(f"{BASE}/playlists/{pid}/tracks/{track_id}", headers=H(t1, "10.3.0.4")) as r:
            rec("playlist IDOR: чужой плейлист → 404", r.status == 404, f"status={r.status}")
        async with http.get(f"{BASE}/playlists/{pid}/tracks", headers=H(t1, "10.3.0.5")) as r:
            rec("playlist IDOR: чтение чужого → 404", r.status == 404, f"status={r.status}")

        # 5. Подписка на несуществующего артиста
        async with http.post(f"{BASE}/artists/999999999/follow", headers=H(t2, "10.4.0.1")) as r:
            orphan = db.execute("select count(*) from user_artists where artist_id=999999999").fetchone()[0]
            rec("follow: несуществующий артист → 404, без сироты", r.status == 404 and orphan == 0, f"status={r.status}, сирот={orphan}")

        # 6. Накрутка кликов по каналу
        ch = db.execute("select id, click_count from required_channels order by id limit 1").fetchone()
        if ch:
            for i in range(30):
                async with http.post(f"{BASE}/subscription/click/{ch[0]}", headers=H(t2, f"10.5.{i}.1")):
                    pass
            after = db.execute("select click_count from required_channels where id=?", (ch[0],)).fetchone()[0]
            rec("clicks: один пользователь не накручивает 30 кликов", after - ch[1] <= 1, f"+{after - ch[1]}")
        else:
            rec("clicks: нет каналов в dev-БД", True, "пропуск")

        # 7. Range: суффиксный диапазон bytes=-100
        async with http.get(f"{BASE}/track/{track_id}", headers=H(t1, "10.6.0.1")) as r:
            audio_url = (await r.json())["audio_url"]
        async with http.get(f"{BASE}{audio_url}") as r:
            full = await r.read() if r.status == 200 else b""
        if full:
            async with http.get(f"{BASE}{audio_url}", headers={"Range": "bytes=-100"}) as r:
                part = await r.read()
                rec("Range bytes=-100 отдаёт ПОСЛЕДНИЕ 100 байт", r.status == 206 and part == full[-100:], f"status={r.status}, len={len(part)}, CR={r.headers.get('Content-Range')}")
            for bad in ("bytes=abc", "bytes=10-5", "bytes=0-1,5-6", f"bytes={len(full)}-", "items=0-1"):
                async with http.get(f"{BASE}{audio_url}", headers={"Range": bad}) as r:
                    rec(f"Range «{bad}» → 416", r.status == 416, f"status={r.status}")
        else:
            rec("Range: у трека нет байтов в dev", True, "пропуск")
        async with http.get(f"{BASE}/tracks/{track_id}/audio?exp=99999999999&sig=00") as r:
            rec("audio: поддельная подпись → 403", r.status == 403, f"status={r.status}")

        # 8. search/log: запрос 1 МБ
        async with http.post(f"{BASE}/search/log", headers=H(t2, "10.7.0.1"), json={"query": "q" * 1_000_000}) as r:
            rec("search/log: 1 МБ не пишется", r.status in (204, 413, 422), f"status={r.status}")

        # 9. transfer: 50 000 строк
        text = "\n".join(f"Artist{i} — Title{i}" for i in range(50_000))
        t0 = time.monotonic()
        async with http.post(f"{BASE}/transfer", headers=H(t2, "10.8.0.1"), json={"source": text}) as r:
            body = await r.text()
            rec("transfer: 50 000 строк отклоняется потолком", r.status in (400, 413, 422), f"status={r.status}, {time.monotonic()-t0:.2f}s, {body[:120]}")
        # SSRF: ссылка не на spotify/yandex
        async with http.post(f"{BASE}/transfer", headers=H(t2, "10.8.0.2"), json={"source": "http://127.0.0.1:8010/health?open.spotify.com/playlist/AAAAAAAAAAAAAAAAAAAA"}) as r:
            rec("transfer: ссылка с чужим хостом не ходит на него", r.status in (400,), f"status={r.status} {(await r.text())[:100]}")

        # 10. upload: title/artist пустые/гигантские
        form = aiohttp.FormData()
        form.add_field("title", " ")
        form.add_field("artist", " ")
        form.add_field("file", b"\x00" * 1000, filename="x.mp3", content_type="audio/mpeg")
        async with http.post(f"{BASE}/upload", headers=H(t2, "10.9.0.1"), data=form) as r:
            rec("upload: пустые title/artist отклоняются", r.status in (400, 422), f"status={r.status}")

        # 11. Параллельный toggle библиотеки: POST и DELETE вперемешку
        async def lib(method):
            async with http.request(method, f"{BASE}/library/{track_id}", headers=H(t2, "10.10.0.1")) as r:
                return r.status
        sts = await asyncio.gather(*[lib("POST") for _ in range(8)])
        rows = db.execute("select count(*) from user_library ul join users u on u.id=ul.user_id where u.telegram_id=? and track_id=?", (u2, track_id)).fetchone()[0]
        rec("library: 8 параллельных POST → без 500", 500 not in sts, f"statuses={sorted(set(sts))}, rows={rows}")

        # 12. Параллельный профиль (награды за достижения)
        async def prof():
            async with http.get(f"{BASE}/profile", headers=H(t2, "10.11.0.1")) as r:
                return r.status
        sts = await asyncio.gather(*[prof() for _ in range(6)])
        rec("profile: 6 параллельных → без 500", 500 not in sts, f"statuses={sorted(set(sts))}")

        # 13. Лимитер: 150 запросов с одного IP
        async def health():
            async with http.get(f"{BASE}/premium/status", headers=H(t2, "10.12.0.1")) as r:
                return r.status, r.headers.get("Retry-After")
        res = await asyncio.gather(*[health() for _ in range(150)])
        n429 = sum(1 for s, _ in res if s == 429)
        ra = next((h for s, h in res if s == 429), None)
        rec("ratelimit: 429 после 120/мин", n429 >= 25, f"429×{n429}, Retry-After={ra}")
        rec("ratelimit: у 429 есть Retry-After", ra is not None, f"Retry-After={ra}")

        # 14. Нагрузка: 300 параллельных лёгких запросов с разных IP — задержка
        async def one(i):
            t = time.monotonic()
            async with http.get(f"{BASE}/library/ids", headers=H(t1, f"10.13.{i // 250}.{i % 250}")) as r:
                await r.read()
                return r.status, time.monotonic() - t
        t0 = time.monotonic()
        res = await asyncio.gather(*[one(i) for i in range(300)])
        lat = sorted(d for _, d in res)
        errs = [s for s, _ in res if s != 200]
        rec("load: 300 параллельных /library/ids без ошибок", not errs, f"ошибок={len(errs)} {sorted(set(errs))}, p50={lat[150]*1000:.0f}ms p95={lat[285]*1000:.0f}ms, всего {time.monotonic()-t0:.1f}s")

        # 15. Секционный поиск с запросом 8 КБ
        async with http.get(f"{BASE}/search/all", params={"q": "я" * 4000}, headers=H(t1, "10.14.0.1")) as r:
            rec("search/all: 8 КБ запроса без 500", r.status != 500, f"status={r.status}")
        # 16. Отрицательные/нулевые/огромные id
        for path in ("/track/0", "/track/-999999999", "/track/99999999999999999999", "/library/-5"):
            method = "POST" if path.startswith("/library") else "GET"
            async with http.request(method, f"{BASE}{path}", headers=H(t1, "10.15.0.1")) as r:
                rec(f"{method} {path} → 4xx", 400 <= r.status < 500, f"status={r.status}")
        # 17. premium/pay: неизвестный тариф / отрицательный
        for months in (0, -1, 7, 10**9):
            async with http.post(f"{BASE}/premium/pay", headers=H(t1, "10.16.0.1"), json={"months": months}) as r:
                rec(f"premium/pay months={months} → 4xx/503", r.status in (422, 503), f"status={r.status}")
        # 18. language: мусорный код
        async with http.post(f"{BASE}/language", headers=H(t1, "10.17.0.1"), json={"code": "<script>" * 1000}) as r:
            saved = db.execute("select ui_language from users where telegram_id=?", (u1,)).fetchone()[0]
            rec("language: мусор не сохраняется как есть", saved is None or len(saved) <= 5, f"status={r.status}, saved={str(saved)[:20]}")

    bugs = [r for r in RESULTS if not r[1]]
    print(f"\nИТОГО: {len(RESULTS)} проверок, багов {len(bugs)}")


asyncio.run(main())
