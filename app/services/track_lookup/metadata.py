"""Метаданные кандидата живого поиска до скачивания.

Отдельный модуль (цикл 7, 15.09): API Mini App нужна только эта функция, а
`track_lookup.importer` рядом тянет aiogram, yt-dlp и весь импорт.
"""
from app.services.track_lookup.ranking import Candidate


def candidate_metadata(candidate: Candidate) -> tuple[str, str]:
    """(исполнитель, название) кандидата — теми же правилами, что и при импорте.

    Нужна ДО скачивания: по этой паре смотрим, не залит ли трек уже, и экономим
    целую загрузку. После скачивания метаданные пересчитываются по факту файла.
    """
    from app.services.title_parser import parse_title

    fallback = (candidate.artist or "").removesuffix(" - Topic").strip() or "Исполнитель"
    return parse_title(candidate.title, fallback)
