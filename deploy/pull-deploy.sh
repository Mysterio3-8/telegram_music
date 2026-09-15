#!/usr/bin/env bash
# Автодеплой «сервер сам забирает код» (15.09). Таймер tg-music-pull-deploy,
# раз в 2 минуты.
#
# 🔴 Зачем. Прежний автодеплой шёл из GitHub Actions на сервер по SSH, и шаг
# «Выкатка на VPS» падал во ВСЕХ 25 прогонах с 08.09 при зелёных тестах — все
# выкатки делались руками. Входящий SSH с раннеров GitHub ненадёжен по природе:
# их адреса меняются, у хостера бывает петля маршрутизации, на сервере fail2ban
# со 130 банами. Здесь наоборот: сервер сам ходит наружу по HTTPS, ни ключей,
# ни секретов, ни входящих соединений.
#
# Порядок решения:
#   1. main на GitHub не отличается от прода — выходим молча (обычный тик);
#   2. этот коммит уже падал на выкатке — не повторяем (иначе петля деплой →
#      откат → деплой каждые 2 минуты);
#   3. прод впереди main (ручная выкатка) — не откатываемся назад;
#   4. тесты GitHub Actions по ЭТОМУ коммиту не зелёные — ждём или отказываем;
#   5. выкатка deploy/remote-deploy.sh ИЗ НОВОГО КОММИТА: проверка здоровья,
#      наблюдение за ошибками людей и откат — там.
#
# Руками: bash deploy/pull-deploy.sh            (PULL_DEPLOY_DRY=1 — только решение)
set -uo pipefail

REPO_DIR=${REPO_DIR:-/opt/tg-music-bot}
BRANCH=${DEPLOY_BRANCH:-main}
GITHUB_REPO=${GITHUB_REPO:-Mysterio3-8/telegram_music}
STATE_DIR=${STATE_DIR:-/var/lib/tg-music-deploy}
LOCK_FILE=${DEPLOY_LOCK_FILE:-/run/tg-music-deploy.lock}
# Тесты, не пришедшие за это время, — повод написать дежурному (один раз).
PENDING_ALERT_SEC=${PENDING_ALERT_SEC:-3600}
DRY=${PULL_DEPLOY_DRY:-0}

mkdir -p "$STATE_DIR"
cd "$REPO_DIR" || { echo "Нет каталога $REPO_DIR"; exit 1; }

log() { printf '%s %s\n' "$(date '+%F %T')" "$*" | tee -a "$STATE_DIR/history.log"; }

env_value() {
    [ -f "$REPO_DIR/.env" ] || return 0
    sed -n "s/^$1=//p" "$REPO_DIR/.env" | tail -n1 | tr -d '\r"' | xargs 2>/dev/null
}

notify() {
    local token chat
    token=$(env_value BOT_TOKEN)
    chat=$(env_value HEALTH_ALERT_CHAT)
    [ -n "$chat" ] || chat=$(env_value ADMIN_IDS | cut -d, -f1)
    [ -n "$token" ] && [ -n "$chat" ] || return 0
    curl -s -m 10 -o /dev/null "https://api.telegram.org/bot${token}/sendMessage" \
        -d "chat_id=${chat}" --data-urlencode "text=$1" || true
}

# Один деплой за раз: ручной remote-deploy.sh берёт тот же замок.
exec 9>"$LOCK_FILE"
flock -n 9 || { echo "Идёт другой деплой — пропускаю тик"; exit 0; }

# --- 1. есть ли что выкатывать ----------------------------------------------
remote=$(timeout 30 git ls-remote origin "refs/heads/$BRANCH" 2>/dev/null | awk '{print $1}')
if [ -z "$remote" ]; then
    echo "GitHub не ответил — пропускаю тик"  # сеть моргнула; через 2 минуты повторим
    exit 0
fi
head=$(git rev-parse HEAD)
[ "$remote" = "$head" ] && exit 0
short=${remote:0:8}

# --- 2. уже падал -----------------------------------------------------------
if grep -qx "$remote" "$STATE_DIR/failed" 2>/dev/null; then
    exit 0
fi

# --- 3. прод впереди --------------------------------------------------------
timeout 120 git fetch --quiet origin "$BRANCH" || { echo "git fetch не удался — пропускаю тик"; exit 0; }
if git merge-base --is-ancestor "$remote" "$head" 2>/dev/null; then
    exit 0  # на проде уже этот коммит или новее — назад не катимся
fi

# --- 4. тесты ---------------------------------------------------------------
answer=$(curl -fsS -m 20 -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/$GITHUB_REPO/commits/$remote/check-runs?check_name=tests&per_page=50") || {
    echo "API GitHub недоступен — пропускаю тик"
    exit 0
}
tests=$(printf '%s' "$answer" | python3 "$REPO_DIR/deploy/ci_verdict.py")

case "$tests" in
    pending)
        first_seen=""
        read -r pending_sha first_seen 2>/dev/null <"$STATE_DIR/pending" || true
        if [ "${pending_sha:-}" != "$remote" ]; then
            echo "$remote $(date +%s)" >"$STATE_DIR/pending"
            log "$short: жду тесты GitHub Actions"
        elif [ -n "$first_seen" ] && [ $(( $(date +%s) - first_seen )) -ge "$PENDING_ALERT_SEC" ]; then
            if [ ! -f "$STATE_DIR/pending.alerted" ] || [ "$(cat "$STATE_DIR/pending.alerted")" != "$remote" ]; then
                echo "$remote" >"$STATE_DIR/pending.alerted"
                log "$short: тестов нет больше часа"
                notify "⚠️ Автодеплой: тесты по коммиту $short не пришли за час — коммит НЕ выкачен. Проверь вкладку Actions."
            fi
        fi
        exit 0
        ;;
    failure)
        echo "$remote" >>"$STATE_DIR/failed"
        log "$short: тесты красные — НЕ выкатываю"
        notify "🔴 Автодеплой: тесты по коммиту $short красные — на прод НЕ поехал. Прод на ${head:0:8}."
        exit 0
        ;;
    success) ;;
    *)
        echo "Непонятный вердикт тестов «$tests» — пропускаю тик"
        exit 0
        ;;
esac

if [ "$DRY" = "1" ]; then
    echo "DRY: выкатил бы $short (прод ${head:0:8}), тесты зелёные"
    exit 0
fi

# --- 5. выкатка -------------------------------------------------------------
# Скрипт выкатки берётся из НОВОГО коммита: bash читает файл по ходу исполнения,
# и копия из рабочего дерева — это прошлая версия (грабля цикла 3: правка
# remote-deploy.sh вступала в силу только со следующего деплоя).
script="$STATE_DIR/remote-deploy.sh"
git show "$remote:deploy/remote-deploy.sh" >"$script" || { log "$short: нет deploy/remote-deploy.sh в коммите"; exit 1; }
rm -f "$STATE_DIR/pending" "$STATE_DIR/pending.alerted"
log "$short: тесты зелёные — выкатываю (прод ${head:0:8})"

DEPLOY_REF="$remote" DEPLOY_LOCK_HELD=1 REPO_DIR="$REPO_DIR" bash "$script"
rc=$?
if [ "$rc" -eq 0 ]; then
    log "$short: выкачен"
else
    # remote-deploy.sh уже откатил код и написал дежурному. Здесь — только чтобы
    # этот коммит не выкатывался по кругу. Исправление приедет новым коммитом.
    echo "$remote" >>"$STATE_DIR/failed"
    log "$short: выкатка не удалась (код $rc) — коммит больше не повторяю"
fi
exit "$rc"
