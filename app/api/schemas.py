from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class TrackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    artist: str
    album: str | None = None
    duration: int
    bitrate: int | None = None
    format: str | None = None
    audio_url: str | None = None  # подписанная ссылка на байты (track_out)


def track_out(track) -> "TrackOut":
    """TrackOut с подписанной аудио-ссылкой — единая точка для всех роутеров."""
    from app.api.security import build_audio_url

    out = TrackOut.model_validate(track)
    out.audio_url = build_audio_url(track.id)
    return out


class InstrumentalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    artist: str
    duration: int


class PlaylistOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    created_at: datetime


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginIn(BaseModel):
    init_data: str


class PlaylistCreateIn(BaseModel):
    title: str


class LyricsOut(BaseModel):
    text: str | None = None
    source: str | None = None
    found: bool


class PlaylistSummaryOut(BaseModel):
    id: int
    title: str
    track_count: int


class AlbumOut(BaseModel):
    name: str
    track_count: int


class LyricsIn(BaseModel):
    text: str


class PremiumStatusOut(BaseModel):
    active: bool
    until: datetime | None = None
    price_stars: int
    price_rub: int
    price_rub_effective: int | None = None  # с учётом реферальной скидки, если есть
    discount_pct: int = 0


class RankOut(BaseModel):
    key: str
    title: str
    emoji: str


class ReferralOut(BaseModel):
    link: str
    invited: int
    rank: RankOut | None = None
    next_rank: RankOut | None = None
    to_next: int


class AchievementOut(BaseModel):
    code: str
    emoji: str
    title: str
    category: str
    unlocked: bool
    progress: int
    target: int


class UserStatsOut(BaseModel):
    listens: int
    listen_hours: float
    streak_days: int
    favorites: int
    playlists: int


class ProfileOut(BaseModel):
    premium: PremiumStatusOut
    referral: ReferralOut
    stats: UserStatsOut
    achievements_unlocked: int
    achievements_total: int
    achievements: list[AchievementOut]
