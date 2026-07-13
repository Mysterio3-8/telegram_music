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


class PremiumStatusOut(BaseModel):
    active: bool
    until: datetime | None = None
    price_stars: int
    price_rub: int
