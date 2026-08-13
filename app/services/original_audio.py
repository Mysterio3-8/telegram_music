"""Оригинальное качество: исходный файл автора вместо потока 128 kbps.

SoundCloud хранит рядом с потоковой версией тот файл, который автор загрузил сам
— часто WAV или FLAC. Отдаёт его, если автор разрешил скачивание и не выбрана
месячная квота. Мы про этот путь не знали и всегда брали поток; именно на
качестве конкуренты строят платные тарифы, поэтому оригинал — Premium-функция.

Три вещи, которые определили устройство модуля:

1. **Оригинал приходит ВТОРЫМ сообщением, mp3 остаётся первым.** Так человек
   получает трек за прежние секунды и слушает его в плеере Telegram, пока
   докачивается сорокамегабайтный файл. Заменить mp3 на WAV было бы регрессом:
   плеер Bot API рисует только mp3 и m4a, остальное — молчаливый файл-вложение.
2. **WAV/FLAC уходят документом, а не аудио.** Из того же ограничения Bot API.
   Значит и `file_id` у оригинала документный: `send_audio` с ним не сработает.
3. **Ни одного сообщения об ошибке.** Автор не разрешил скачивание, файл не влез
   в 50 МБ, источник промолчал — человек просто остаётся с mp3. Он ничего не
   сделал неправильно, и сообщать ему не о чем.
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
QUALITY_ORIGINAL = "original"

HQ_READY = "ready"
HQ_NONE = "none"


def wants_original(user: User) -> bool:
    """Нужен ли этому человеку оригинал вместо mp3.

    Проверка Premium живёт здесь, а не только в интерфейсе, сознательно: выбор
    хранится в БД и переживает окончание подписки. Без этой проверки человек,
    один раз купивший месяц, продолжал бы занимать единственное ядро и канал
    Telegram сорокамегабайтными закачками бесплатно.
    """
    from app.services.premium import is_premium_active

    return user.audio_quality == QUALITY_ORIGINAL and is_premium_active(user)


def size_mb(size: int | None) -> str:
    """«38.4» — размер для подписи. Округление до десятых: «38» выглядит
    подозрительно ровным, а три знака после запятой человеку не нужны."""
    return f"{(size or 0) / (1024 * 1024):.1f}"


async def _mark_unavailable(session: AsyncSession, track: Track) -> None:
    """Запоминаем, что оригинала нет, чтобы не качать это повторно каждому.

    ⚠️ Ставится ТОЛЬКО по ответу источника «файла нет» или «не влез». Сетевые
    сбои сюда не попадают: они временные, и следующий человек должен попробовать
    снова, а не упереться в вечное «оригинала нет» из-за одной секунды без сети.
    """
    track.hq_status = HQ_NONE
    await session.commit()


async def deliver_original(
    session: AsyncSession,
    bot: Bot,
    track: Track,
    chat_id: int,
    source_url: str | None = None,
    hq_available: bool = False,
) -> bool:
    """Присылает оригинал трека в чат. False — оригинала нет, человек остаётся с mp3.

    source_url — ссылка источника, если у трека своей ещё нет (треки, заведённые
    до появления `tracks.source_url`, живут без неё).
    hq_available — что сказала выдача поиска. Нужен, чтобы не ходить в сеть за
    заведомо отсутствующим файлом: у большинства треков скачивание закрыто.
    """
    if track.hq_file_id:
        # Уже минтили — уходит мгновенно, как и mp3 по своему file_id
        await bot.send_document(chat_id, track.hq_file_id, caption=_caption(track))
        return True
    if track.hq_status == HQ_NONE:
        return False

    url = track.source_url or source_url
    if not url or "soundcloud.com" not in url:
        # YouTube исходников не отдаёт в принципе, там всегда перекодированный
        # поток. Статус не ставим: трек может приехать с SoundCloud позже.
        return False
    if not hq_available:
        return False

    data, file_format = await _download_original(url)
    if data is None:
        return False
    if not data:
        await _mark_unavailable(session, track)
        return False
    if len(data) > settings.original_max_size_mb * 1024 * 1024:
        logger.info(
            "Оригинал track=%s весит %s МБ — больше лимита Bot API, остаёмся на mp3",
            track.id, size_mb(len(data)),
        )
        await _mark_unavailable(session, track)
        return False

    filename = build_filename(track.artist, track.title, file_format)
    minted = await bot.send_document(
        settings.effective_archive_chat_id,
        BufferedInputFile(data, filename=filename),
    )
    if minted.document is None:
        return False

    track.hq_file_id = minted.document.file_id
    track.hq_format = file_format
    track.hq_size = len(data)
    track.hq_status = HQ_READY
    await session.commit()
    logger.info(
        "Оригинал track=%s: %s, %s МБ", track.id, file_format, size_mb(len(data))
    )

    if chat_id != settings.effective_archive_chat_id:
        await bot.send_document(chat_id, track.hq_file_id, caption=_caption(track))
    return True


async def _download_original(url: str) -> tuple[bytes | None, str]:
    """(байты, формат) оригинала. (None, '') — временный сбой, статус не менять;
    (b'', '') — источник ответил, что оригинала нет."""
    from app.services.disk import enough_free_disk
    from app.services.soundcloud import download_soundcloud_audio

    if not enough_free_disk():
        # Диск почти полон. Это состояние сервера, а не свойство трека —
        # помечать трек «без оригинала» из-за него нельзя.
        logger.warning("Оригинал: мало места на диске, пропускаю %s", url)
        return None, ""
    try:
        result = await asyncio.to_thread(
            download_soundcloud_audio, url, False, True
        )
    except Exception:  # noqa: BLE001 — сеть/бан: временно, пробуем в другой раз
        logger.warning("Оригинал: скачивание %s не удалось", url, exc_info=True)
        return None, ""
    if result is None:
        return b"", ""
    audio, _ = result
    return audio.data, audio.file_format


def _caption(track: Track) -> str:
    from app.i18n import t

    return t(
        "original.caption",
        format=(track.hq_format or "").upper(),
        size=size_mb(track.hq_size),
    )
