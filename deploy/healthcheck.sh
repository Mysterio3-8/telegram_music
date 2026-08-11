#!/usr/bin/env bash
# Сторож: раз в 2 минуты проверяет, что прод жив, и поднимает то, что легло.
#
# Зачем: 11.08 бот принимал запросы, а треки не приходили больше трёх минут —
# оба Celery-воркера стояли в inactive при NRestarts=0, то есть их остановили
# руками (похоже, при разборе инцидента 07.08) и не подняли обратно. Restart=always
# от этого не спасает: systemd перезапускает упавшее, но остановленное командой
# оставляет остановленным — это же явное распоряжение администратора. Заметить
# такое было некому, задачи копились в Redis, человек ждал.
#
# Второй случай, который сторож ловит: воркер жив, но очередь не убывает
# (завис на сетевом вызове, кончилась память, брокер недоступен). Снаружи это
# неотличимо от «бот не отвечает», а systemd считает юнит здоровым.
#
# Запускать не руками — таймером tg-music-health.timer.
set -uo pipefail

REPO_DIR=/opt/tg-music-bot
STATE_DIR=/var/lib/tg-music-health
# Не чаще одного одинакового сообщения в полчаса: сторож, спамящий владельца,
# перестают читать через день, и следующая настоящая поломка проходит мимо.
ALERT_COOLDOWN=1800
# Очередь поискового парсера. Порог с запасом: несколько задач в моменте — это
# норма (одна закачка ~8 сек), а вот десяток, не убывающий две проверки подряд,
# уже означает, что разбирать некому.
QUEUE_NAME=youtube_user
QUEUE_STALL_LIMIT=10

CRITICAL_UNITS=(redis-server tg-music-bot tg-music-api tg-music-worker tg-music-youtube-user)

mkdir -p "$STATE_DIR"

# --- уведомление владельцу -------------------------------------------------
# Токен и админов берём из того же .env, что и бот: второй источник правды
# разъехался бы при следующей смене токена (а она уже была 05.08).
env_value() {
    local key="$1"
    [ -f "$REPO_DIR/.env" ] || return 0
    sed -n "s/^${key}=//p" "$REPO_DIR/.env" | tail -n1 | tr -d '\r"' | xargs 2>/dev/null
}

notify() {
    local key="$1" text="$2"
    local stamp_file="$STATE_DIR/alert-$key"
    local now; now=$(date +%s)

    if [ -f "$stamp_file" ]; then
        local last; last=$(cat "$stamp_file" 2>/dev/null || echo 0)
        if [ $(( now - last )) -lt "$ALERT_COOLDOWN" ]; then
            return 0
        fi
    fi
    echo "$now" >"$stamp_file"

    logger -t tg-music-health "$text"
    echo "$(date -Is) $text" >>"$STATE_DIR/history.log"

    local token; token=$(env_value BOT_TOKEN)
    local admins; admins=$(env_value ADMIN_IDS)
    [ -n "$token" ] && [ -n "$admins" ] || return 0

    local host; host=$(hostname)
    local IFS=','
    for admin in $admins; do
        admin=$(echo "$admin" | xargs)
        [ -n "$admin" ] || continue
        curl -s -m 10 -o /dev/null \
            "https://api.telegram.org/bot${token}/sendMessage" \
            -d "chat_id=${admin}" \
            -d "text=🚨 ${host}: ${text}" || true
    done
}

# --- 1. Сервисы ------------------------------------------------------------
for unit in "${CRITICAL_UNITS[@]}"; do
    # disabled — осознанное решение владельца (так выключен массовый парсер),
    # его сторож не отменяет.
    [ "$(systemctl is-enabled "$unit" 2>/dev/null)" = "enabled" ] || continue
    systemctl is-active --quiet "$unit" && continue

    logger -t tg-music-health "$unit лежит — поднимаю"
    systemctl reset-failed "$unit" 2>/dev/null || true
    systemctl start "$unit" 2>/dev/null || true
    sleep 5

    if systemctl is-active --quiet "$unit"; then
        notify "down-$unit" "$unit лежал, сторож поднял. Проверь, почему остановился: journalctl -u $unit -n 50"
    else
        notify "fail-$unit" "$unit НЕ ПОДНИМАЕТСЯ. Прод частично мёртв: systemctl status $unit"
    fi
done

# --- 2. Очередь не убывает -------------------------------------------------
# Юнит может быть active, а работа стоять: тогда systemd доволен, а треки не
# приходят. Смотрим на длину очереди в двух соседних проверках.
redis_db=0
broker=$(env_value CELERY_BROKER_URL)
[ -n "$broker" ] || broker=$(env_value REDIS_URL)
case "$broker" in
    */[0-9]*) redis_db="${broker##*/}" ;;
esac
[[ "$redis_db" =~ ^[0-9]+$ ]] || redis_db=0

depth=$(redis-cli -n "$redis_db" llen "$QUEUE_NAME" 2>/dev/null | tr -dc '0-9')
if [ -n "$depth" ]; then
    prev_file="$STATE_DIR/queue-$QUEUE_NAME"
    prev=$(cat "$prev_file" 2>/dev/null | tr -dc '0-9')
    prev=${prev:-0}
    echo "$depth" >"$prev_file"

    # Растёт или стоит на месте выше порога — работа не движется.
    if [ "$depth" -ge "$QUEUE_STALL_LIMIT" ] && [ "$depth" -ge "$prev" ] && [ "$prev" -ge "$QUEUE_STALL_LIMIT" ]; then
        logger -t tg-music-health "очередь $QUEUE_NAME стоит на $depth — перезапускаю воркер"
        systemctl restart tg-music-youtube-user 2>/dev/null || true
        notify "stall-$QUEUE_NAME" "Очередь $QUEUE_NAME стоит на $depth задачах — воркер жив, но не разбирает. Перезапустил tg-music-youtube-user."
    fi
fi

# --- 3. Память -------------------------------------------------------------
# Ранний сигнал: на этом боксе 961 МБ, и все прошлые инциденты начинались с
# того, что доступная память уходила к нулю.
avail=$(awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo)
if [ -n "$avail" ] && [ "$avail" -lt 60 ]; then
    notify "lowmem" "Свободно всего ${avail} МБ памяти. Смотри, кто её ест: systemd-cgtop -1 -n1, redis-cli info memory"
fi

# --- 4. Диск ---------------------------------------------------------------
# 26.07 переполнение диска заблокировало запись в Redis и уронило бота целиком.
free_pct=$(df --output=pcent / | tail -1 | tr -dc '0-9')
if [ -n "$free_pct" ] && [ "$free_pct" -ge 90 ]; then
    notify "lowdisk" "Диск заполнен на ${free_pct}%. При 100% Redis перестаёт писать и бот падает — чисти /tmp, journal, бэкапы."
fi

exit 0
