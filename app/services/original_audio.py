"""Лучшее доступное качество — то, что продаётся за подписку.

**Почему не «оригинал автора», как задумывалось.** Спека 13.08 исходила из того,
что SoundCloud отдаёт исходный файл автора (WAV/FLAC) при `downloadable` +
`has_downloads_left`. Замер на проде это опроверг: из 601 трека по 12 запросам
скачивание разрешено у **шести — это 1%**, и ни одного у Kizaru, Big Baby Tape,
The Weeknd, Morgenshtern, Miyagi, Scriptonite. Разрешают только любительские
загрузки. Продавать функцию, которая срабатывает раз на сотню, нечестно.

**Что есть на самом деле.** У каждого не-DRM трека в формат-листе лежит
`hls_aac_160k` — 160 kbps AAC, тогда как мы жёстко брали `http_mp3_128`. Замер
одного трека на проде: mp3 128 — 6.59 сек и 1.91 МБ, AAC 160 — 7.25 сек и
2.41 МБ. Полсекунды и полмегабайта за честный шаг вверх, доступный практически
на всём каталоге. Это и стало содержанием платного качества; оригинал автора
остался первой ступенью лестницы и берётся там, где он всё-таки есть.

Три решения, определившие устройство модуля:

1. **Одно сообщение, а не два.** Человек, выбравший лучшее качество, получает
   ОДИН файл — тот самый. Присылать ему следом ту же песню в 128 kbps значит
   удваивать шум ради нулевой пользы.
2. **Копия для подписчиков отдельная от каталога** (решение владельца). В
   `tracks.tg_file_id` остаётся mp3 128 для всех, повышенное качество живёт в
   `hq_file_id`. Иначе первый же подписчик улучшал бы каталог всем бесплатно, и
   продавать было бы нечего.
3. **Провал всегда откатывается на mp3.** DRM, сбой сети, слишком большой файл —
   человек получает обычный трек и ни одного сообщения об ошибке.

⚠️ `hq_file_id` — идентификатор документа ТОЛЬКО для WAV/FLAC: в плеере Telegram
играют лишь mp3 и m4a, остальное уходит вложением. Поэтому отправка ветвится по
формату, и пересылать такой id надо тем же методом, каким он получен.
"""
import asyncio
import logging

from aiogram import Bot
from aiogram.types import BufferedInputFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Track, User
from app.services.track_meta import build_filename

logger = logging.getLogger(__name__)

QUALITY_MP3 = "mp3"
QUALITY_BEST = "best"

HQ_READY = "ready"
HQ_NONE = "none"

# Форматы, которые Bot API показывает в музыкальном плеере. Остальное — вложение.
PLAYABLE_FORMATS = frozenset({"mp3", "m4a"})


def wants_best_quality(user: User) -> bool:
    """Нужно ли этому человеку повышенное качество.

    Проверка Premium живёт здесь, а не только в интерфейсе, сознательно: выбор
    хранится в БД и переживает окончание подписки. Без неё человек, купивший
    один месяц, продолжал бы получать платное качество бесплатно.
    """
    from app.services.premium import is_premium_active

    return user.audio_quality == QUALITY_BEST and is_premium_active(user)


def size_mb(size: int | None) -> str:
    """«38.4» — размер для подписи. До десятых: «38» выглядит подозрительно
    ровным, а три знака после запятой человеку не нужны."""
    return f"{(size or 0) / (1024 * 1024):.1f}"


def is_lossless(file_format: str | None) -> bool:
    return (file_format or "").lower() in {"wav", "flac", "aiff", "aif"}


async def _mark_unavailable(session: AsyncSession, track: Track) -> None:
    """Запоминаем, что повышенного качества у трека нет.

    ⚠️ Ставится ТОЛЬКО по ответу источника «нечего скачивать» и по «не влез в
    лимит». Сетевые сбои сюда не попадают: они временные, и следующий человек
    должен попробовать снова, а не упереться в вечный отказ из-за одной секунды
    без сети.
    """
    track.hq_status = HQ_NONE
    await session.commit()


async def deliver_best_quality(
    session: AsyncSession,
    bot: Bot,
    track: Track,
    chat_id: int,
    source_url: str | None = None,
    caption: str | None = None,
) -> bool:
    """Присылает трек в лучшем доступном качестве. False — не вышло, зовите mp3.

    source_url — ссылка источника, если у трека своей ещё нет (треки, заведённые
    до появления `tracks.source_url`, живут без неё).
    """
    if track.hq_file_id:
        # Уже минтили — уходит мгновенно, ровно как mp3 по своему file_id
        await _send(bot, chat_id, track, track.hq_file_id, caption)
        return True
    if track.hq_status == HQ_NONE:
        return False

    url = track.source_url or source_url
    if not url or "soundcloud.com" not in url:
        # У YouTube своей лестницы качества нет: там всегда перекодированный
        # поток, и «лучшее» совпадает с обычным. Статус не ставим — трек может
        # приехать с SoundCloud позже.
        return False

    data, file_format = await _download_best(url)
    if data is None:
        return False  # временный сбой: статус не трогаем
    if not data:
        await _mark_unavailable(session, track)
        return False
    if len(data) > settings.original_max_size_mb * 1024 * 1024:
        logger.info(
            "Лучшее качество track=%s весит %s МБ — больше лимита Bot API",
            track.id, size_mb(len(data)),
        )
        await _mark_unavailable(session, track)
        return False

    minted_id = await _mint(bot, track, data, file_format)
    if minted_id is None:
        return False

    track.hq_file_id = minted_id
    track.hq_format = file_format
    track.hq_size = len(data)
    track.hq_status = HQ_READY
    await session.commit()
    logger.info("Лучшее качество track=%s: %s, %s МБ", track.id, file_format, size_mb(len(data)))

    if chat_id != settings.effective_archive_chat_id:
        await _send(bot, chat_id, track, minted_id, caption)
    return True


async def _mint(bot: Bot, track: Track, data: bytes, file_format: str) -> str | None:
    """Кладёт файл в архивный чат и возвращает его file_id.

    Минт — это реальная отправка через Bot API: другого способа получить file_id
    нет. Отправляем тем же методом, каким потом будем пересылать, иначе id не
    подойдёт.
    """
    file = BufferedInputFile(data, filename=build_filename(track.artist, track.title, file_format))
    if file_format in PLAYABLE_FORMATS:
        sent = await bot.send_audio(
            settings.effective_archive_chat_id,
            file,
            title=track.title,
            performer=track.artist,
            duration=track.duration or None,
        )
        return sent.audio.file_id if sent.audio else None
    sent = await bot.send_document(settings.effective_archive_chat_id, file)
    return sent.document.file_id if sent.document else None


async def _send(bot: Bot, chat_id: int, track: Track, file_id: str, caption: str | None) -> None:
    """Пересылает готовый файл человеку. Подпись дополняем пометкой о качестве —
    иначе разницу между обычным треком и платным не видно вообще."""
    text = "\n".join(filter(None, (caption, quality_note(track))))
    if (track.hq_format or "") in PLAYABLE_FORMATS:
        await bot.send_audio(chat_id, file_id, caption=text or None)
    else:
        await bot.send_document(chat_id, file_id, caption=text or None)


def quality_note(track: Track) -> str:
    from app.i18n import t

    key = "quality.note_lossless" if is_lossless(track.hq_format) else "quality.note_high"
    return t(key, format=(track.hq_format or "").upper(), size=size_mb(track.hq_size))


async def _download_best(url: str) -> tuple[bytes | None, str]:
    """(байты, формат) лучшего доступного файла. (None, '') — временный сбой,
    статус не менять; (b'', '') — источнику нечего отдать (DRM, приватный трек)."""
    from app.services.disk import enough_free_disk
    from app.services.soundcloud import download_soundcloud_audio

    if not enough_free_disk():
        # Состояние сервера, а не свойство трека — помечать трек нельзя
        logger.warning("Лучшее качество: мало места на диске, пропускаю %s", url)
        return None, ""
    try:
        result = await asyncio.to_thread(download_soundcloud_audio, url, False, True)
    except Exception:  # noqa: BLE001 — сеть/бан: временно, пробуем в другой раз
        logger.warning("Лучшее качество: скачивание %s не удалось", url, exc_info=True)
        return None, ""
    if result is None:
        return b"", ""
    audio, _ = result
    return audio.data, audio.file_format
