#!/usr/bin/env bash
# Выкатка на сервере. Запускается автоматически из GitHub Actions после того,
# как тесты позеленели. Руками звать не нужно, но можно:
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
SERVICES=(tg-music-bot tg-music-api tg-music-worker tg-music-youtube-user)
# Сколько ждать, пока сервисы поднимутся, прежде чем считать деплой неудачным.
HEALTH_WAIT=${HEALTH_WAIT:-20}

cd "$REPO_DIR" || { echo "Нет каталога $REPO_DIR"; exit 1; }

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
git reset --hard "origin/$BRANCH" || { echo "git reset не удался"; exit 1; }
NEW=$(git rev-parse HEAD)
if [ "$NEW" = "$PREVIOUS" ]; then
    say "Изменений нет — деплой не нужен"
    exit 0
fi
echo "Новый коммит: ${NEW:0:8}"
git --no-pager log --oneline "${PREVIOUS}..${NEW}" | head -10

# --- 3. зависимости ---------------------------------------------------------
say "Зависимости"
./.venv/bin/pip install -q -r requirements.txt || {
    echo "pip install не удался"
    notify "🔴 Деплой ${NEW:0:8}: не встали зависимости. Код НЕ тронут, прод жив на ${PREVIOUS:0:8}."
    git reset --hard "$PREVIOUS"
    exit 1
}

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
bash deploy/install-units.sh || echo "⚠️ install-units.sh отработал с ошибкой — смотри вывод выше"

# --- 6. рестарт -------------------------------------------------------------
say "Перезапуск сервисов"
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

if [ ${#failed[@]} -eq 0 ]; then
    say "✅ Деплой ${NEW:0:8} прошёл, все сервисы живы"
    notify "✅ Деплой ${NEW:0:8} прошёл. Сервисы живы."
    exit 0
fi

# --- откат ------------------------------------------------------------------
say "🔴 Не поднялись: ${failed[*]} — откатываю код на ${PREVIOUS:0:8}"
git reset --hard "$PREVIOUS"
./.venv/bin/pip install -q -r requirements.txt || true
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
