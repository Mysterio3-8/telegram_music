"""Совместимость: логика разбора названия переехала в app.services.title_parser
(она не специфична для YouTube — используется и импортом из Telegram-канала)."""
from app.services.title_parser import parse_title

__all__ = ["parse_title"]
