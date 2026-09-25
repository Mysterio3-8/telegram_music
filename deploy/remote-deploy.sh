#!/usr/bin/env bash
# Выкатка на сервере. Запускается автоматически таймером tg-music-pull-deploy
# (deploy/pull-deploy.sh), когда тесты по коммиту позеленели. Руками звать не
# нужно, но можно:
#   cd /opt/tg-music-bot && bash deploy/remote-deploy.sh
#
# Порядок шагов не случаен и меняться не должен:
#   1. запомнить текущий коммит  — без него некуда откатываться;
#   2. подтянуть код;
#   3. зависимости;
#   4. миграции;
#   5. юниты (git pull их НЕ доносит — systemd читает /etc/systemd/system);
#   6. рестарт;
#   7. проверка здоровья, и если плохо — откат кода на шаг 1.
#
# ⚠️ Миграции НЕ откатываются автоматически. `alembic downgrade` умеет удалять
# колонки вместе с данными, и делать это без человека, ночью, по факту упавшего
# healthcheck — опаснее самой поломки. Откатывается только код; если он не
# заводится со свежей схемой, дежурному приходит тревога.
set -uo pipefail

REPO_DIR=${REPO_DIR:-/opt/tg-music-bot}
BRANCH=${DEPLOY_BRANCH:-main}
# Сервисы, которые несут код и потому перезапускаются. Массовый парсер сюда не
# входит намеренно — он выключен решением владельца, и деплой не должен его
# воскрешать.
SERVICES=(tg-music-bot tg-music-api tg-music-worker tg-music-youtube-user tg-music-webadmin)
# Сколько ждать, пока сервисы поднимутся, прежде чем считать деплой неудачным.
HEALTH_WAIT=${HEALTH_WAIT:-20}

cd "$REPO_DIR" || { echo "Нет каталога $REPO_DIR"; exit 1; }

# Один деплой за раз: таймер автодеплоя (pull-deploy.sh) и ручной запуск делят
# один git-каталог. pull-deploy.sh держит замок сам и зовёт нас с DEPLOY_LOCK_HELD=1.
if [ "${DEPLOY_LOCK_HELD:-0}" != "1" ]; then
    exec 9>"${DEPLOY_LOCK_FILE:-/run/tg-music-deploy.lock}"
    flock -n 9 || { echo "Уже идёт другой деплой — дождись его конца"; exit 1; }
fi
# Что выкатывать. Автодеплой передаёт ТОЧНЫЙ коммит с зелёными тестами: за время
# прогона тестов main мог уйти вперёд на непроверенный коммит.
TARGET=${DEPLOY_REF:-origin/$BRANCH}

say() { printf '\n==> %s\n' "$*"; }

env_value() {
    [ -f "$REPO_DIR/.env" ] || return 0
    sed -n "s/^$1=//p" "$REPO_DIR/.env" | tail -n1 | tr -d '\r"' | xargs 2>/dev/null
}

notify() {
    local text="$1"
    local token; token=$(env_value BOT_TOKEN)
    local chat; chat=$(env_value HEALTH_ALERT_CHAT)
    [ -n "$chat" ] || chat=$(env_value ADMIN_IDS | cut -d, -f1)
    [ -n "$token" ] && [ -n "$chat" ] || return 0
    curl -s -m 10 -o /dev/null \
        "https://api.telegram.org/bot${token}/sendMessage" \
        -d "chat_id=${chat}" -d "text=${text}" || true
}

# --- 1. точка возврата ------------------------------------------------------
PREVIOUS=$(git rev-parse HEAD)
say "Текущий коммит: ${PREVIOUS:0:8} — сюда откатимся, если что-то пойдёт не так"

# --- 2. код -----------------------------------------------------------------
say "Забираю код из $BRANCH"
git fetch --quiet origin "$BRANCH" || { echo "git fetch не удался"; exit 1; }
git reset --hard "$TARGET" || { echo "git reset не удался"; exit 1; }
NEW=$(git rev-parse HEAD)
if [ "$NEW" = "$PREVIOUS" ]; then
    say "Изменений нет — деплой не нужен"
    exit 0
fi
echo "Новый коммит: ${NEW:0:8}"
git --no-pager log --oneline "${PREVIOUS}..${NEW}" | head -10

# --- 3. зависимости ---------------------------------------------------------
say "Зависимости"
# Снимок версий ДО установки: откат кода без отката пакетов оставлял бы старый
# код на новых библиотеках — сочетание, которое никто не тестировал.
PIP_BEFORE=/root/pip-before-deploy.txt
./.venv/bin/pip freeze >"$PIP_BEFORE" 2>/dev/null || true
LOCK_ARGS=()
[ -f requirements.lock ] && LOCK_ARGS=(-c requirements.lock)
./.venv/bin/pip install -q -r requirements.txt "${LOCK_ARGS[@]}" || {
    echo "pip install не удался"
    notify "🔴 Деплой ${NEW:0:8}: не встали зависимости. Код НЕ тронут, прод жив на ${PREVIOUS:0:8}."
    git reset --hard "$PREVIOUS"
    exit 1
}
# yt-dlp замок не закрепляет, а без -U он навсегда оставался версии дня
# установки (25.09: от 04.07, YouTube отвечал 403). Сбой не валит деплой.
./.venv/bin/pip install -q -U yt-dlp || echo "yt-dlp не обновился — остаётся прежний"

# --- 4. миграции ------------------------------------------------------------
# Идут ДО рестарта: код после рестарта уже ожидает новую схему.
say "Миграции"
if ! ./.venv/bin/python -m alembic upgrade head; then
    echo "alembic upgrade провалился"
    # Схема могла остаться посередине — сюда нужен человек, а не автомат.
    notify "🔴 Деплой ${NEW:0:8}: МИГРАЦИЯ УПАЛА. Схема могла остаться в промежуточном виде — нужен человек. Код откатываю на ${PREVIOUS:0:8}."
    git reset --hard "$PREVIOUS"
    exit 1
fi

# --- 5. юниты ---------------------------------------------------------------
# git pull их не доносит: systemd читает /etc/systemd/system.
say "Юниты и системные конфиги"
SKIP_SERVICE_RESTART=1 bash deploy/install-units.sh || echo "⚠️ install-units.sh отработал с ошибкой — смотри вывод выше"

# --- 6. рестарт -------------------------------------------------------------
say "Перезапуск сервисов"
RESTART_TS=$(date +%s)
ACCESS_LOG=/var/log/nginx/access.log
ACCESS_OFFSET=$(stat -c %s "$ACCESS_LOG" 2>/dev/null || echo 0)
for unit in "${SERVICES[@]}"; do
    [ "$(systemctl is-enabled "$unit" 2>/dev/null)" = "enabled" ] || {
        echo "$unit не enabled — пропускаю (осознанно выключён)"
        continue
    }
    # reset-failed обязателен: после серии падений systemd упирается в лимит
    # старта и молча отказывается запускать юнит.
    systemctl reset-failed "$unit" 2>/dev/null || true
    systemctl restart "$unit" && echo "$unit перезапущен" || echo "⚠️ $unit не перезапустился"
done

# --- 7. проверка здоровья ---------------------------------------------------
say "Жду ${HEALTH_WAIT} сек и проверяю"
sleep "$HEALTH_WAIT"

failed=()
for unit in "${SERVICES[@]}"; do
    [ "$(systemctl is-enabled "$unit" 2>/dev/null)" = "enabled" ] || continue
    systemctl is-active --quiet "$unit" || failed+=("$unit")
done

# Юнит active ещё не значит, что API отвечает: uvicorn может висеть на импорте.
if [ "$(curl -s -m 10 -o /dev/null -w '%{http_code}' http://127.0.0.1:8010/health)" != "200" ]; then
    failed+=("tg-music-api(/health)")
fi

# --- 8. наблюдение: ошибки, которые видят люди ------------------------------
# Решение владельца 14.09: деплой идёт без него. Сервисы живы, а человек ловит
# 500 — такой деплой тоже откатывается. До включения за сутки на проде было
# 0 ошибок и 0 ответов 5xx, поэтому порог в несколько штук — уже сигнал.
DEPLOY_WATCH=${DEPLOY_WATCH:-90}
DEPLOY_ERROR_LIMIT=${DEPLOY_ERROR_LIMIT:-5}
if [ ${#failed[@]} -eq 0 ] && [ "$DEPLOY_WATCH" -gt 0 ]; then
    say "Наблюдаю ${DEPLOY_WATCH} сек за ошибками пользователей"
    sleep "$DEPLOY_WATCH"
    unit_args=()
    for unit in "${SERVICES[@]}"; do unit_args+=(-u "$unit"); done
    # Сбои сети источников (yt-dlp пишет их уровнем ERROR) не относятся к выкатке:
    # SoundCloud, оборвавший соединение, не повод откатывать код. Список — как
    # в healthcheck.sh.
    SOURCE_NOISE='Unable to download|Connection reset|timed out|HTTP Error [0-9]+|Sign in to confirm|DRM protected|Unable to extract|Temporary failure in name resolution'
    journal_errors=$(journalctl "${unit_args[@]}" --since "@$RESTART_TS" --no-pager -o cat 2>/dev/null \
        | grep -E "ERROR|Traceback|CRITICAL" | grep -vcE "$SOURCE_NOISE" || true)
    http_errors=0
    if [ -r "$ACCESS_LOG" ]; then
        size=$(stat -c %s "$ACCESS_LOG")
        [ "$ACCESS_OFFSET" -le "$size" ] || ACCESS_OFFSET=0
        http_errors=$(tail -c +"$(( ACCESS_OFFSET + 1 ))" "$ACCESS_LOG" | awk '$9 ~ /^5[0-9][0-9]$/' | wc -l)
    fi
    echo "Ошибок в журнале: ${journal_errors:-0}, ответов 5xx: ${http_errors:-0} (порог $DEPLOY_ERROR_LIMIT)"
    if [ $(( ${journal_errors:-0} + ${http_errors:-0} )) -ge "$DEPLOY_ERROR_LIMIT" ]; then
        failed+=("ошибки пользователей: журнал ${journal_errors:-0}, 5xx ${http_errors:-0}")
    fi
fi

if [ ${#failed[@]} -eq 0 ]; then
    say "✅ Деплой ${NEW:0:8} прошёл, все сервисы живы"
    notify "✅ Деплой ${NEW:0:8} прошёл. Сервисы живы."
    exit 0
fi

# --- откат ------------------------------------------------------------------
say "🔴 Не поднялись: ${failed[*]} — откатываю код на ${PREVIOUS:0:8}"
git reset --hard "$PREVIOUS"
if [ -s "$PIP_BEFORE" ]; then
    ./.venv/bin/pip install -q -r "$PIP_BEFORE" || true
else
    ./.venv/bin/pip install -q -r requirements.txt || true
fi
for unit in "${SERVICES[@]}"; do
    [ "$(systemctl is-enabled "$unit" 2>/dev/null)" = "enabled" ] || continue
    systemctl reset-failed "$unit" 2>/dev/null || true
    systemctl restart "$unit" 2>/dev/null || true
done
sleep "$HEALTH_WAIT"

still_dead=()
for unit in "${SERVICES[@]}"; do
    [ "$(systemctl is-enabled "$unit" 2>/dev/null)" = "enabled" ] || continue
    systemctl is-active --quiet "$unit" || still_dead+=("$unit")
done

if [ ${#still_dead[@]} -eq 0 ]; then
    notify "🔴 Деплой ${NEW:0:8} сломал ${failed[*]}. Откатил на ${PREVIOUS:0:8}, прод снова жив. ⚠️ Миграции НЕ откатывались."
    echo "Откат удался"
else
    notify "🔴🔴 Деплой ${NEW:0:8} сломал ${failed[*]}, и откат на ${PREVIOUS:0:8} НЕ помог: ${still_dead[*]} лежат. Нужен человек: bash deploy/triage.sh"
    echo "Откат не помог — нужен человек"
fi
exit 1
