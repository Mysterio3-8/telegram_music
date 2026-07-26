"""Логика бота поддержки (блок F): категории обращений + мягкий антиспам.

Только чистые функции и лёгкий in-memory rate-limit — без сети и БД, чтобы
логику можно было протестировать отдельно от aiogram.
"""
import time
from collections import defaultdict, deque

# Категории обращений (callback_data → человекочитаемое)
CATEGORIES = {
    "sup:complaint": "Жалоба",
    "sup:review": "Отзыв",
    "sup:idea": "Предложение",
}

MIN_TEXT_LENGTH = 15  # слишком короткий текст просим дополнить (мягко)

# Мягкий антиспам: не больше N обращений за окно с одного пользователя
_RATE_LIMIT = 3
_RATE_WINDOW_SEC = 3600
_recent: dict[int, deque[float]] = defaultdict(deque)


def text_too_short(text: str) -> bool:
    """True — текст короче минимума (просим написать подробнее)."""
    return len(text.strip()) < MIN_TEXT_LENGTH


def rate_limited(user_id: int, now: float | None = None) -> bool:
    """True — пользователь превысил лимит обращений за окно. Иначе фиксирует обращение."""
    current = time.time() if now is None else now
    bucket = _recent[user_id]
    while bucket and current - bucket[0] > _RATE_WINDOW_SEC:
        bucket.popleft()
    if len(bucket) >= _RATE_LIMIT:
        return True
    bucket.append(current)
    return False


def ticket_header(category_label: str, user) -> str:
    """Шапка обращения для владельца: категория + кто написал."""
    username = f"@{user.username}" if getattr(user, "username", None) else "без username"
    name = getattr(user, "full_name", None) or getattr(user, "first_name", "") or "Пользователь"
    return f"🆘 {category_label}\nОт: {name} ({username}, id {user.id})"
