from datetime import datetime, timedelta

from app.db.models import Playlist, Track, TrackEvent, User, UserLibrary
from app.services.gamification import (
    LIFETIME_DAYS,
    build_achievements,
    collect_user_stats,
    count_referrals,
    grant_referral_milestones,
    grant_referrer_discount,
    referral_link,
    referral_rank,
    register_referral,
)
from app.services.premium import _utcnow, is_premium_active


def test_referral_rank_thresholds():
    assert referral_rank(0).current is None
    assert referral_rank(0).next.title == "Bronze"
    assert referral_rank(0).to_next == 1

    assert referral_rank(1).current.title == "Bronze"
    assert referral_rank(1).next.title == "Silver"
    assert referral_rank(1).to_next == 4

    assert referral_rank(150).current.title == "Legend"
    assert referral_rank(150).next is None
    assert referral_rank(200).current.title == "Legend"


def test_referral_link_format():
    assert referral_link(777, "tgram_music_bot") == "https://t.me/tgram_music_bot?start=ref_777"


async def _add_user(session, telegram_id: int) -> User:
    user = User(telegram_id=telegram_id)
    session.add(user)
    await session.commit()
    return user


async def test_register_referral_binds_and_ignores_invalid(session):
    referrer = await _add_user(session, 100)
    invitee = await _add_user(session, 200)

    assert await register_referral(session, invitee, 100) is True
    assert invitee.referred_by == 100

    # повторная привязка игнорируется
    assert await register_referral(session, invitee, 999) is False
    # самоприглашение игнорируется
    solo = await _add_user(session, 300)
    assert await register_referral(session, solo, 300) is False
    # несуществующий реферер
    another = await _add_user(session, 400)
    assert await register_referral(session, another, 55555) is False

    assert await count_referrals(session, 100) == 1


async def test_referral_milestones_grant_premium_idempotently(session):
    referrer = await _add_user(session, 1)
    # приглашаем 3 пользователей — пороги 1 и 3 дают 3 и 10 дней
    for tid in (10, 11, 12):
        invitee = await _add_user(session, tid)
        await register_referral(session, invitee, 1)

    assert referrer.referral_milestones_claimed == 2  # пороги 1 и 3
    assert is_premium_active(referrer)

    # повторный вызов ничего не выдаёт
    before = referrer.premium_until
    assert await grant_referral_milestones(session, referrer) == 0
    assert referrer.premium_until == before


async def test_referral_lifetime_milestone(session):
    referrer = User(telegram_id=1, referral_milestones_claimed=5)  # достигнуты первые 5 порогов
    session.add(referrer)
    await session.commit()
    for tid in range(1000, 1100):  # 100 приглашённых
        session.add(User(telegram_id=tid, referred_by=1))
    await session.commit()

    await grant_referral_milestones(session, referrer)
    assert referrer.referral_milestones_claimed == 6
    assert referrer.premium_until > _utcnow() + timedelta(days=LIFETIME_DAYS - 1)


async def test_grant_referrer_discount(session):
    referrer = await _add_user(session, 1)
    buyer = await _add_user(session, 2)
    buyer.referred_by = 1
    await session.commit()

    await grant_referrer_discount(session, buyer)
    assert referrer.premium_discount_pct == 50


async def test_collect_stats_and_achievements(session):
    user = await _add_user(session, 1)
    track = Track(title="T", artist="A", duration=3600)
    session.add(track)
    await session.flush()

    # 100 прослушиваний за 3 дня подряд
    base = datetime(2026, 1, 1, 12, 0, 0)
    for day in range(3):
        for _ in range(40):
            session.add(
                TrackEvent(
                    user_id=user.id,
                    track_id=track.id,
                    event="listen",
                    created_at=base + timedelta(days=day),
                )
            )
    session.add(UserLibrary(user_id=user.id, track_id=track.id))
    session.add(Playlist(user_id=user.id, title="P"))
    await session.commit()

    stats = await collect_user_stats(session, user)
    assert stats.listens == 120
    assert stats.streak_days == 3
    assert stats.listen_hours == 120.0  # 120 прослушиваний по 3600 сек
    assert stats.favorites == 1
    assert stats.playlists == 1

    achievements = build_achievements(stats)
    by_code = {a.code: a for a in achievements}
    assert by_code["listen_100"].unlocked is True
    assert by_code["listen_1000"].unlocked is False
    assert by_code["playlist_1"].unlocked is True
    assert by_code["streak_7"].unlocked is False
    assert by_code["streak_7"].progress == 3
