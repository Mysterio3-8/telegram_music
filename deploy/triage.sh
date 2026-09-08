#!/usr/bin/env bash
# Разбор «бот упал»: собирает картину и, по просьбе, поднимает прод.
#
# Зачем отдельный скрипт, если есть healthcheck.sh: сторож работает по таймеру и
# лечит ОДИН класс поломок — юнит остановлен или очередь стоит. Когда он не
# справился (а если бот лежит долго, значит не справился), нужен разбор причины,
# и собирать его руками по десятку команд в момент, когда прод лежит, — плохое
# время для творчества. Здесь собран порядок проверок из всех прошлых инцидентов:
# 26.07 (диск 100% → Redis не пишет → бот падает на каждой команде),
# 01.08 (OOM-петля воркера, 10261 рестарт), 03.08 (очередь Redis на 177к задач),
# 07.08 (петля маршрутизации у хостера), 11.08 (воркеры остановлены руками),
# 16.08 (отозванный токен → падение на старте).
#
# По умолчанию только СМОТРИТ и ничего не трогает.
#   bash deploy/triage.sh            # диагностика
#   bash deploy/triage.sh --recover  # диагностика + поднять то, что лежит
set -uo pipefail

REPO_DIR=/opt/tg-music-bot
RECOVER=0
[ "${1:-}" = "--recover" ] && RECOVER=1

UNITS=(redis-server tg-music-bot tg-music-api tg-music-worker tg-music-youtube-user)

say() { printf '\n=== %s ===\n' "$*"; }

env_value() {
    local key="$1"
    [ -f "$REPO_DIR/.env" ] || return 0
    sed -n "s/^${key}=//p" "$REPO_DIR/.env" | tail -n1 | tr -d '\r"' | xargs 2>/dev/null
}

# --- 1. Ресурсы: с них начинались ВСЕ прошлые падения -----------------------
say "Диск"
df -h / | tail -1
free_pct=$(df --output=pcent / | tail -1 | tr -dc '0-9')
if [ "${free_pct:-0}" -ge 90 ]; then
    echo "🔴 Диск ${free_pct}% — это причина №1. При 100% Redis не может писать RDB,"
    echo "   включает stop-writes-on-bgsave-error, и бот падает на КАЖДОЙ команде (26.07)."
    echo "   Что чистить: du -xh / --max-depth=2 2>/dev/null | sort -rh | head -20"
    echo "   Обычные виновники: /tmp (yt-dlp), journal, старые бэкапы в /opt/tg-music-bot/backups"
fi

say "Память"
free -m | head -2
avail=$(awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo)
[ "${avail:-999}" -lt 100 ] && echo "🔴 Свободно ${avail} МБ — бокс 961 МБ, смотри кто ест: systemd-cgtop -1 -n1"

say "Нагрузка (чужой проект на этой же машине умеет занять ядро)"
uptime
ps -eo pcpu,rss,args --sort=-pcpu | head -8

# --- 2. Юниты --------------------------------------------------------------
say "Состояние сервисов"
for unit in "${UNITS[@]}"; do
    active=$(systemctl is-active "$unit" 2>/dev/null)
    enabled=$(systemctl is-enabled "$unit" 2>/dev/null)
    nrestarts=$(systemctl show "$unit" -p NRestarts --value 2>/dev/null)
    printf '%-26s %-10s %-10s рестартов=%s\n' "$unit" "$active" "$enabled" "${nrestarts:-?}"
    # Много рестартов = крутится петля. Она не «просто падает», она ЖРЁТ ядро:
    # каждый заход это полный импорт Python с aiogram (замер 16.08 — 23% CPU).
    if [ "${nrestarts:-0}" -gt 50 ] 2>/dev/null; then
        echo "   ⚠️  $nrestarts рестартов — петля. Причина в журнале ниже, само не пройдёт."
    fi
done

say "Почему упал бот (последние 40 строк)"
journalctl -u tg-music-bot -n 40 --no-pager 2>/dev/null | tail -40

say "Ошибки за сутки по всем сервисам"
for unit in tg-music-bot tg-music-api tg-music-worker; do
    n=$(journalctl -u "$unit" --since -24h -p err --no-pager 2>/dev/null | wc -l)
    echo "$unit: $n строк уровня error"
done

# --- 3. Redis: и брокер, и FSM-хранилище бота ------------------------------
say "Redis"
if redis-cli ping >/dev/null 2>&1; then
    redis-cli info memory 2>/dev/null | grep -E "used_memory_human|used_memory_rss_human"
    # ⚠️ ps про Redis врёт, когда память выдавлена в своп (01.08): rss был 5.88 МБ
    # при used_memory 724 МБ. Смотреть надо именно сюда.
    err=$(redis-cli config get stop-writes-on-bgsave-error 2>/dev/null | tail -1)
    echo "stop-writes-on-bgsave-error: $err"
    [ "$err" = "yes" ] && echo "   ⚠️  При неудачном снимке Redis ЗАПРЕТИТ запись — бот ляжет целиком."
    echo "Очереди:"
    for q in youtube_user youtube soundcloud telegram_channel celery; do
        printf '  %-18s %s\n' "$q" "$(redis-cli llen "$q" 2>/dev/null)"
    done
else
    echo "🔴 Redis не отвечает. Бот с ним связан через Requires= — без Redis он НЕ СТАРТУЕТ."
    echo "   systemctl status redis-server; journalctl -u redis-server -n 30"
fi

# --- 4. Токен: 16.08 отозванный токен положил старого бота ------------------
say "Токен бота"
token=$(env_value BOT_TOKEN)
if [ -z "$token" ]; then
    echo "🔴 BOT_TOKEN пуст в $REPO_DIR/.env"
else
    resp=$(curl -s -m 10 "https://api.telegram.org/bot${token}/getMe")
    if echo "$resp" | grep -q '"ok":true'; then
        echo "✅ токен живой: $(echo "$resp" | grep -oP '"username":"\K[^"]+')"
    else
        echo "🔴 Telegram не принял токен — бот будет падать на старте в петле:"
        echo "   $resp"
    fi
fi

# --- 5. Восстановление -----------------------------------------------------
if [ "$RECOVER" = "1" ]; then
    say "Поднимаю"
    # reset-failed обязателен: после серии падений systemd упирается в лимит
    # старта и молча отказывается запускать юнит, сколько его ни зови.
    for unit in "${UNITS[@]}"; do
        [ "$(systemctl is-enabled "$unit" 2>/dev/null)" = "enabled" ] || continue
        systemctl is-active --quiet "$unit" && continue
        echo "поднимаю $unit"
        systemctl reset-failed "$unit" 2>/dev/null || true
        systemctl start "$unit" 2>/dev/null || true
    done
    sleep 8
    say "Что получилось"
    for unit in "${UNITS[@]}"; do
        printf '%-26s %s\n' "$unit" "$(systemctl is-active "$unit" 2>/dev/null)"
    done
    echo
    echo "Если бот снова inactive/failed — причина в журнале выше, рестартом не лечится."
fi

exit 0
