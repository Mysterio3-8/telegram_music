from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))
    language: Mapped[str | None] = mapped_column(String(8))
    premium: Mapped[bool] = mapped_column(default=False)
    premium_until: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_login: Mapped[datetime | None]


class Track(Base):
    __tablename__ = "tracks"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(256), index=True)
    artist: Mapped[str] = mapped_column(String(256), index=True)
    album: Mapped[str | None] = mapped_column(String(256))
    duration: Mapped[int]  # секунды
    bitrate: Mapped[int | None]  # kbps
    file_size: Mapped[int | None]  # байты
    format: Mapped[str | None] = mapped_column(String(8))
    storage_path: Mapped[str | None] = mapped_column(String(512))  # архивная копия (local://, s3://)
    tg_file_id: Mapped[str | None] = mapped_column(String(256))  # для мгновенной пересылки в Telegram
    # True — tg_file_id указывает на файл с актуальными ID3-тегами и именем «Исполнитель — Название».
    # Сбрасывается при правке метаданных; выставляется после перетегированной переотправки.
    meta_synced: Mapped[bool] = mapped_column(default=False, server_default="0")
    fingerprint: Mapped[str | None] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Instrumental(Base):
    __tablename__ = "instrumentals"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(256), index=True)
    artist: Mapped[str] = mapped_column(String(256), index=True)
    duration: Mapped[int]  # секунды
    storage_path: Mapped[str | None] = mapped_column(String(512))
    fingerprint: Mapped[str | None] = mapped_column(String(128), index=True)


class Playlist(Base):
    __tablename__ = "playlists"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class PlaylistTrack(Base):
    __tablename__ = "playlist_tracks"

    playlist_id: Mapped[int] = mapped_column(ForeignKey("playlists.id"), primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id"), primary_key=True)
    position: Mapped[int]


class UserLibrary(Base):
    __tablename__ = "user_library"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id"), primary_key=True)
    added_at: Mapped[datetime] = mapped_column(server_default=func.now())


class PremiumSubscription(Base):
    __tablename__ = "premium"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    status: Mapped[str] = mapped_column(String(16))
    type: Mapped[str] = mapped_column(String(16))
    start_date: Mapped[datetime]
    end_date: Mapped[datetime]
    payment_id: Mapped[str | None] = mapped_column(String(128))


class TrackEvent(Base):
    """События прослушивания/скачивания — сырьё для статистики админ-панели."""

    __tablename__ = "track_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id"), index=True)
    event: Mapped[str] = mapped_column(String(16), index=True)  # listen | download
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Upload(Base):
    __tablename__ = "uploads"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id"))
    upload_date: Mapped[datetime] = mapped_column(server_default=func.now())


class AppSetting(Base):
    """Рантайм-настройки, переключаемые из админки (не из .env). Ключ-значение."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(256))


class YoutubeSource(Base):
    """YouTube-канал или плейлист как источник автоимпорта (доп. ТЗ, §2, §17)."""

    __tablename__ = "youtube_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String(512))
    title: Mapped[str | None] = mapped_column(String(256))  # имя канала для отображения
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | disabled
    last_checked_at: Mapped[datetime | None]
    found_count: Mapped[int] = mapped_column(default=0, server_default="0")
    imported_count: Mapped[int] = mapped_column(default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class YoutubeImport(Base):
    """Задача импорта одной YouTube-публикации (доп. ТЗ, §10, §13, §16)."""

    __tablename__ = "youtube_imports"
    __table_args__ = (UniqueConstraint("source_id", "video_id", name="uq_source_video"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("youtube_sources.id"), index=True)
    video_id: Mapped[str] = mapped_column(String(32), index=True)
    video_title: Mapped[str | None] = mapped_column(String(512))  # исходное имя видео
    detected_title: Mapped[str | None] = mapped_column(String(256))
    detected_artist: Mapped[str | None] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    track_id: Mapped[int | None] = mapped_column(ForeignKey("tracks.id"))
    attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(String(512))
    discovered_at: Mapped[datetime] = mapped_column(server_default=func.now())
    imported_at: Mapped[datetime | None]


class TelegramChannelSource(Base):
    """Личный Telegram-канал как источник автоимпорта (без хранения файлов на диске)."""

    __tablename__ = "telegram_channel_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(String(256))  # @username, invite-ссылка или id
    title: Mapped[str | None] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | disabled
    last_checked_at: Mapped[datetime | None]
    last_message_id: Mapped[int] = mapped_column(default=0, server_default="0")
    found_count: Mapped[int] = mapped_column(default=0, server_default="0")
    imported_count: Mapped[int] = mapped_column(default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class TelegramChannelImport(Base):
    """Задача импорта одного аудиопоста из канала. Файл никогда не лежит на диске —
    скачивается временно только для отпечатка, сразу отправляется через бота
    (получает свой tg_file_id) и байты отбрасываются."""

    __tablename__ = "telegram_channel_imports"
    __table_args__ = (UniqueConstraint("source_id", "message_id", name="uq_tgchan_source_message"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("telegram_channel_sources.id"), index=True)
    message_id: Mapped[int] = mapped_column(index=True)
    original_title: Mapped[str | None] = mapped_column(String(512))  # как было в посте
    detected_title: Mapped[str | None] = mapped_column(String(256))
    detected_artist: Mapped[str | None] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    track_id: Mapped[int | None] = mapped_column(ForeignKey("tracks.id"))
    attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(String(512))
    discovered_at: Mapped[datetime] = mapped_column(server_default=func.now())
    imported_at: Mapped[datetime | None]
