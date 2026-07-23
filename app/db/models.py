from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Index, String, Text, UniqueConstraint, func
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
    # Геймификация (доп. ТЗ): рефералы, награды за приглашения, реферальная скидка
    referred_by: Mapped[int | None] = mapped_column(BigInteger, index=True)  # telegram_id пригласившего
    referral_milestones_claimed: Mapped[int] = mapped_column(default=0, server_default="0")
    premium_discount_pct: Mapped[int] = mapped_column(default=0, server_default="0")
    # Рассылка: True — пользователь заблокировал бота (TelegramForbiddenError), больше не шлём
    bot_blocked: Mapped[bool] = mapped_column(default=False, server_default="0")
    # Пробный Premium выдаётся один раз на аккаунт
    trial_used: Mapped[bool] = mapped_column(default=False, server_default="0")


class UserAchievement(Base):
    """Выданная награда за достижение — гарантия, что дни Premium начислены один раз."""

    __tablename__ = "user_achievements"
    __table_args__ = (UniqueConstraint("user_id", "code", name="uq_user_achievement"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(64))
    granted_days: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


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
    # Настроение для рекомендаций (доп. ТЗ): happy|sad|energetic|calm|love. Ставит админ.
    mood: Mapped[str | None] = mapped_column(String(16), index=True)
    # Обложка: URL миниатюры источника (SoundCloud/YouTube) — показывается в Mini App;
    # сама картинка дополнительно вшивается в аудиофайл при импорте (видна в Telegram)
    cover_url: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Artist(Base):
    """Артист как сущность (P4): имя, фото, описание, ссылка на SoundCloud.
    Треки пока связываются по lower(trim(tracks.artist)) — artist_id придёт
    отдельной миграцией после биндинга."""

    __tablename__ = "artists"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(256))
    normalized_name: Mapped[str] = mapped_column(String(256), unique=True)  # lower(trim(name))
    soundcloud_url: Mapped[str | None] = mapped_column(String(512))
    photo_url: Mapped[str | None] = mapped_column(String(512))  # аватар артиста
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Instrumental(Base):
    """Минусы — отдельная от tracks таблица (TZ §9): совпадение title/artist с полноценным
    треком не считается дубликатом, файлы физически разные."""

    __tablename__ = "instrumentals"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(256), index=True)
    artist: Mapped[str] = mapped_column(String(256), index=True)
    duration: Mapped[int]  # секунды
    storage_path: Mapped[str | None] = mapped_column(String(512))
    tg_file_id: Mapped[str | None] = mapped_column(String(256))  # для мгновенной пересылки
    fingerprint: Mapped[str | None] = mapped_column(String(128), index=True)
    source: Mapped[str] = mapped_column(String(32), default="import", server_default="import")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


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
    # Составные индексы под горячие агрегаты статистики (WHERE user_id AND event)
    # и антинакрутный дедуп (WHERE user_id AND track_id AND event) — без них
    # с ростом событий эти запросы делают полный скан.
    __table_args__ = (
        Index("ix_track_events_user_event", "user_id", "event"),
        Index("ix_track_events_user_track_event", "user_id", "track_id", "event"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id"), index=True)
    event: Mapped[str] = mapped_column(String(16))  # listen | download
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Lyrics(Base):
    """Текст песни для трека (доп. ТЗ). Источник: lrclib (автопоиск) | user | admin.
    Один трек — один текст (track_id первичный ключ)."""

    __tablename__ = "lyrics"

    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id"), primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16), default="user")
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())


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
    # Куда складывать аудио: tracks (общая база) | instrumentals (канал с минусами)
    target: Mapped[str] = mapped_column(String(16), default="tracks", server_default="tracks")
    last_checked_at: Mapped[datetime | None]
    last_message_id: Mapped[int] = mapped_column(default=0, server_default="0")
    found_count: Mapped[int] = mapped_column(default=0, server_default="0")
    imported_count: Mapped[int] = mapped_column(default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class SoundcloudSource(Base):
    """SoundCloud-профиль/сет как источник минусов с автопроверкой новых битов.
    Дедуп при повторном скане делает импорт инкрементальным — забираются только новые."""

    __tablename__ = "soundcloud_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String(512), unique=True)
    title: Mapped[str | None] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | disabled
    last_checked_at: Mapped[datetime | None]
    found_count: Mapped[int] = mapped_column(default=0, server_default="0")  # в последнем скане
    imported_count: Mapped[int] = mapped_column(default=0, server_default="0")  # всего
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class SoundcloudImported(Base):
    """Уже обработанные SoundCloud-ссылки (импортированные ИЛИ отклонённые).
    Rescan источника пропускает их без скачивания — не бьём по SoundCloud лишний раз
    (защита от бана IP) и не качаем одно и то же каждый день."""

    __tablename__ = "soundcloud_imported"

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class RequiredChannel(Base):
    """Обязательный канал подписки (TZ §14-17). Управляется из админки; таблица пустая →
    гейт подписки выключен. Бот должен быть админом канала (иначе getChatMember не работает)."""

    __tablename__ = "required_channels"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(String(256), unique=True)  # @handle, -100… или t.me-ссылка бота
    label: Mapped[str] = mapped_column(String(128))  # текст кнопки в гейте
    # channel — подписка проверяется через getChatMember; bot — «запустите бота»:
    # Telegram не даёт проверить запуск чужого бота, кнопка ссылкой без проверки (ОП на ботов)
    kind: Mapped[str] = mapped_column(String(16), default="channel", server_default="channel")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class SubscriptionStatus(Base):
    """Кэш проверки обязательной подписки на каналы (TZ §14-17). TTL — в SubscriptionService."""

    __tablename__ = "subscription_status"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    channel: Mapped[str] = mapped_column(String(256), primary_key=True)
    is_subscribed: Mapped[bool] = mapped_column(default=False)
    checked_at: Mapped[datetime] = mapped_column(server_default=func.now())


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


class SearchQuery(Base):
    """Реальные поисковые запросы Mini App — сырьё для «Популярных запросов» (ТЗ §11)."""

    __tablename__ = "search_queries"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    query: Mapped[str] = mapped_column(String(256), index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
