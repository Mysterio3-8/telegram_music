"""Какие выходы VPN живы для YouTube — замер по каждому отдельно.

Зачем. С IP сервера YouTube отвечает «Sign in to confirm you're not a bot» на
всех десяти player-клиентах. Работает единственная связка: **прокси плюс
`player_client=tv_embedded`** (замер 14.08, см. docs/tasks/2026-08-14-приоритеты.md).
Но выходы неравноценны: на одном получалось 3 из 4, на ротации — 1 из 6. Пока не
известно, какие именно выходы мёртвые, ротация делает хуже, а не лучше — каждый
заход на мёртвый узел это потерянные секунды у человека, который ждёт трек.

⚠️ **Проба намеренно НЕ скачивает файл.** Массовые скачивания на этом боксе
роняли sshd трижды за 14–15.08: единственное ядро занимает ffmpeg, который
перекодирует opus в mp3. Здесь вместо этого два дешёвых шага, и они проверяют
ровно то, что ломается:

1. извлечь метаданные и ссылку на медиа (`skip_download`);
2. взять **первые 64 КБ** этой ссылки через тот же выход.

Второй шаг обязателен: известный отказ выглядит как «метаданные есть, медиа-URL
отдаёт 403», и проверка одних метаданных засчитала бы мёртвый выход живым.

⚠️ `ignoreerrors` здесь ВЫКЛЮЧЕН осознанно. С ним yt-dlp гасит сетевую ошибку
сам и возвращает пустой результат, а снаружи «пусто» неотличимо от «заблокировано» —
на этом уже один раз построили неверный вывод «VPN не лечит YouTube».

    python -m app.cli.youtube_exits                    # все выходы 10811–10815
    python -m app.cli.youtube_exits --exits 10813,10815
    python -m app.cli.youtube_exits --videos 5         # больше проб на выход
"""
import argparse
import logging
import time

from yt_dlp import YoutubeDL
from yt_dlp.networking import Request

from app.services.youtube.downloader import youtube_opts

logger = logging.getLogger(__name__)

# Сколько байт тянуть с медиа-ссылки. 64 КБ — заведомо больше заголовков
# контейнера и заведомо меньше, чем нужно для заметной нагрузки на канал.
_PROBE_BYTES = 64 * 1024

# Пауза между пробами. Бокс одноядерный; торопиться здесь некуда, а ровный темп
# заодно меньше похож на автоматический обход с точки зрения YouTube.
_PAUSE_SECONDS = 2.0

_DEFAULT_PORTS = (10811, 10812, 10813, 10814, 10815)


def _proxy_for(port: int) -> str:
    return f"socks5://127.0.0.1:{port}"


def _quiet(opts: dict) -> dict:
    """yt-dlp по умолчанию печатает свой прогресс — в таблице он лишний."""
    return {**opts, "quiet": True, "no_warnings": True, "ignoreerrors": False}


def discover_ids(count: int, proxy: str) -> list[str]:
    """Набирает подопытные ролики поиском, а не берёт зашитый список.

    Зашитые идентификаторы протухают (ролик удалили, закрыли по региону), и тогда
    проба показывала бы мёртвыми все выходы разом.
    """
    opts = _quiet({**youtube_opts(proxy=proxy), "extract_flat": True, "skip_download": True})
    with YoutubeDL(opts) as ydl:
        data = ydl.extract_info(f"ytsearch{count}:official music video", download=False)
    entries = [e for e in (data or {}).get("entries") or [] if e and e.get("id")]
    return [e["id"] for e in entries[:count]]


def probe(video_id: str, proxy: str) -> tuple[bool, str, float]:
    """(получилось ли, что случилось, сколько секунд) для одного ролика."""
    began = time.perf_counter()
    try:
        with YoutubeDL(_quiet({**youtube_opts(proxy=proxy), "skip_download": True})) as ydl:
            info = ydl.extract_info(
                f"https://www.youtube.com/watch?v={video_id}", download=False
            )
            audio = [
                f
                for f in (info or {}).get("formats") or []
                if f.get("acodec") not in (None, "none") and f.get("url")
            ]
            if not audio:
                return False, "нет аудиоформатов", time.perf_counter() - began
            # Сеть самого yt-dlp: та же, что и при настоящем скачивании, поэтому
            # проба меряет ровно тот путь, который потом поедет к человеку.
            response = ydl.urlopen(
                Request(audio[-1]["url"], headers={"Range": f"bytes=0-{_PROBE_BYTES - 1}"})
            )
            chunk = response.read(_PROBE_BYTES)
    except Exception as error:  # noqa: BLE001 — нас интересует ЛЮБОЙ отказ выхода
        text = str(error).replace("\n", " ")
        return False, text[:70], time.perf_counter() - began
    if len(chunk) < 1024:
        return False, f"медиа отдало {len(chunk)} байт", time.perf_counter() - began
    return True, f"{len(chunk) // 1024} КБ", time.perf_counter() - began


def _configured_proxies() -> list[str]:
    """Выходы, которыми пользуется прод прямо сейчас, — из настроек, не из догадки."""
    from app.services.proxies import youtube_proxy_chain

    return [p for p in youtube_proxy_chain() if p]


def check() -> int:
    """Ночная проверка: жив ли хоть один из НАСТРОЕННЫХ выходов.

    🔴 Зачем. Замер 16.08: в `.env` стоял выход 10815, а он мёртв — YouTube-фолбэк
    не работал вовсе, и узнать об этом было неоткуда. Отказ молчаливый по своей
    природе: SoundCloud закрывает большинство запросов сам, поэтому в жалобах это
    всплывает не сразу, а как «иногда не находит».

    Один ролик на выход: проверке нужен факт «жив/мёртв», а не статистика.
    """
    proxies = _configured_proxies()
    if not proxies:
        logger.info("YOUTUBE_PROXY пуст — проверять нечего")
        return 0

    try:
        ids = discover_ids(1, proxies[0])
    except Exception:  # noqa: BLE001 — первый выход мог умереть, спросим остальные
        ids = []
    for proxy in proxies[1:] if not ids else []:
        try:
            ids = discover_ids(1, proxy)
            break
        except Exception:  # noqa: BLE001
            continue
    if not ids:
        _alert("YouTube: ни один выход VPN не отдаёт даже поиск — проверь Xray и подписку")
        return 1

    alive = []
    for proxy in proxies:
        ok, note, _ = probe(ids[0], proxy)
        logger.info("%s — %s (%s)", proxy, "жив" if ok else "мёртв", note)
        if ok:
            alive.append(proxy)
        time.sleep(_PAUSE_SECONDS)

    if not alive:
        _alert(
            "YouTube: мертвы ВСЕ настроенные выходы VPN — фолбэк не работает. "
            "Живые ищутся так: python -m app.cli.youtube_exits"
        )
        return 1
    logger.info("Живых выходов: %d из %d", len(alive), len(proxies))
    return 0


def _alert(text: str) -> None:
    import asyncio

    from app.config import settings
    from app.services.telegram_send import send_message

    logger.warning(text)
    chat_id = settings.health_alert_id
    if chat_id is None:
        return
    try:
        asyncio.run(send_message(chat_id, f"🚨 {text}"))
    except Exception:  # noqa: BLE001 — предупреждение не должно ронять обслуживание
        logger.warning("Предупреждение отправить не удалось", exc_info=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Живость выходов VPN для YouTube")
    parser.add_argument(
        "--exits",
        default=",".join(str(p) for p in _DEFAULT_PORTS),
        help="порты socks-входов Xray через запятую",
    )
    parser.add_argument("--videos", type=int, default=3, help="сколько роликов на выход")
    parser.add_argument("--ids", help="конкретные id роликов через запятую (иначе — поиском)")
    parser.add_argument(
        "--check",
        action="store_true",
        help="ночная проверка настроенных выходов: молча, если хоть один жив",
    )
    args = parser.parse_args()

    if args.check:
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        raise SystemExit(check())

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ports = [int(p.strip()) for p in args.exits.split(",") if p.strip()]

    if args.ids:
        ids = [i.strip() for i in args.ids.split(",") if i.strip()]
    else:
        # Список набираем через ПЕРВЫЙ выход: если он мёртв, поиск не пройдёт, и
        # честнее сказать об этом сразу, чем показать пять пустых столбцов.
        print("Набираю подопытные ролики поиском…")
        try:
            ids = discover_ids(args.videos, _proxy_for(ports[0]))
        except Exception as error:  # noqa: BLE001
            raise SystemExit(f"Не удалось набрать ролики через {ports[0]}: {error}")
    if not ids:
        raise SystemExit("Подопытных роликов нет — YouTube не отдал выдачу")
    print(f"Ролики: {', '.join(ids)}\n")

    results: dict[int, tuple[int, float]] = {}
    for port in ports:
        good = 0
        spent_total = 0.0
        for video_id in ids:
            ok, note, spent = probe(video_id, _proxy_for(port))
            spent_total += spent
            good += ok
            print(f"  {port} {video_id} {'OK  ' if ok else 'МИМО'} {spent:5.1f}с  {note}")
            time.sleep(_PAUSE_SECONDS)
        results[port] = (good, spent_total / max(1, len(ids)))
        print(f"  → {port}: {good} из {len(ids)}, в среднем {results[port][1]:.1f}с\n")

    print("Итог по выходам:")
    for port, (good, avg) in sorted(results.items(), key=lambda r: (-r[1][0], r[1][1])):
        print(f"  {port}: {good}/{len(ids)}  {avg:5.1f}с")

    alive = [p for p, (good, _) in sorted(results.items(), key=lambda r: (-r[1][0], r[1][1])) if good]
    if alive:
        print("\nСтрока для .env (живые впереди, мёртвые выброшены):")
        print("YOUTUBE_PROXY=" + ",".join(_proxy_for(p) for p in alive))
    else:
        print("\n⚠️ Живых выходов нет вовсе — дело не в узлах, а в подписке или в Xray")


if __name__ == "__main__":
    main()
