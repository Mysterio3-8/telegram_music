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
