from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, String, func
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
