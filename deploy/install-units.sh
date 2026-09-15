#!/usr/bin/env bash
# Донести юниты и системные конфиги из репозитория до систем-каталогов VPS.
#
# Зачем отдельный скрипт: обычный деплой делает git pull и рестарт сервисов, но
# файлы юнитов лежат в /etc/systemd/system — правка в repo/deploy туда не
# попадает сама, и сервер молча продолжает жить со старой конфигурацией.
# Ровно на этом обожглись в соседнем проекте (см. all_auto/CLAUDE.md).
#
# Запускать НА СЕРВЕРЕ от root:
#   cd /opt/tg-music-bot && bash deploy/install-units.sh
#
# Идемпотентен: повторный запуск ничего не ломает.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

echo "==> Копирую юниты в /etc/systemd/system"
for unit in deploy/tg-music-*.service deploy/tg-music-*.timer; do
    install -m 644 "$unit" "/etc/systemd/system/$(basename "$unit")"
    echo "    $(basename "$unit")"
done

echo "==> Очередь telegram_channel обслуживает основной воркер — отдельный юнит гасим"
# Иначе очередь разбирают два процесса сразу: лишний интерпретатор на боксе с
# одним ядром и 961 МБ памяти.
systemctl disable --now tg-music-telegram-channel.service 2>/dev/null || true
rm -f /etc/systemd/system/tg-music-telegram-channel.service

echo "==> Массовый YouTube-парсер выключен решением владельца (27.07) — снимаем failed"
systemctl reset-failed tg-music-youtube-scan.service 2>/dev/null || true

# ⚠️ Всё ниже трогается ТОЛЬКО при изменении (цикл 3, 14.09). Скрипт зовётся на
# каждом деплое, и раньше каждый деплой принудительно ротировал логи,
# перезапускал journald и fail2ban — без единой правки в их конфигах.

echo "==> logrotate: syslog/kern.log росли до сотен МБ между ротациями"
if ! cmp -s deploy/logrotate-rsyslog.conf /etc/logrotate.d/rsyslog; then
    install -m 644 deploy/logrotate-rsyslog.conf /etc/logrotate.d/rsyslog
    logrotate -f /etc/logrotate.d/rsyslog || true
fi

echo "==> journald: держим журнал в рамках"
mkdir -p /etc/systemd/journald.conf.d
journald_conf=$(mktemp)
cat >"$journald_conf" <<'EOF'
[Journal]
SystemMaxUse=150M
MaxRetentionSec=7day
EOF
if ! cmp -s "$journald_conf" /etc/systemd/journald.conf.d/limits.conf; then
    install -m 644 "$journald_conf" /etc/systemd/journald.conf.d/limits.conf
    systemctl restart systemd-journald
fi
rm -f "$journald_conf"

echo "==> fail2ban против SSH-брутфорса (btmp был на 114 МБ неудачных входов)"
if ! command -v fail2ban-client >/dev/null 2>&1; then
    apt-get update -qq && apt-get install -y -qq fail2ban
fi
mkdir -p /etc/fail2ban/jail.d
systemctl enable --now fail2ban
if ! cmp -s deploy/fail2ban-sshd.local /etc/fail2ban/jail.d/sshd.local; then
    install -m 644 deploy/fail2ban-sshd.local /etc/fail2ban/jail.d/sshd.local
    systemctl restart fail2ban
fi

echo "==> Redis: потолок памяти"
# 01.08 очередь в Redis разрослась до 651 МБ (644 тысячи задач) и вместе со
# свопом положила бокс. Потолок без вытеснения (noeviction): брокер Celery и
# FSM бота не должны молча терять ключи — при упоре Redis откажет в записи и
# это будет видно в журнале, а не OOM-киллер снесёт всё подряд.
if command -v redis-cli >/dev/null 2>&1; then
    if [ "$(redis-cli config get maxmemory 2>/dev/null | tail -1)" != "268435456" ]; then
        redis-cli config set maxmemory 256mb >/dev/null && redis-cli config rewrite >/dev/null || true
    fi
fi

echo "==> Перечитываю systemd и поднимаю сервисы"
systemctl daemon-reload

echo "==> Сторож здоровья (инцидент 11.08: воркеры стояли в inactive, никто не заметил)"
# chmod тут больше не делаем: он менял режим файла в рабочем дереве, git считал
# это локальной правкой, и следующий `git pull` падал с «Your local changes
# would be overwritten». Исполняемый бит хранится в самом репозитории (100755).
mkdir -p /var/lib/tg-music-health
systemctl enable --now tg-music-health.timer

# Разбор входящих TON-переводов. Нужен только прямому переводу на кошелёк:
# у Crypto Pay есть вебхук, и ему таймер ни к чему.
systemctl enable --now tg-music-ton-check.timer

# Автодеплой: сервер сам забирает main после зелёных тестов (15.09, вместо SSH
# из GitHub Actions, который падал во всех прогонах).
mkdir -p /var/lib/tg-music-deploy
systemctl enable --now tg-music-pull-deploy.timer

# Еженедельный отчёт аналитики владельцу в Telegram (15.09)
systemctl enable --now tg-music-analytics-report.timer
# Только включённые: массовый парсер (tg-music-soundcloud, tg-music-youtube)
# выключен решением владельца 27.07 — поднимать его здесь значило бы тихо
# отменять это решение и занимать 180 МБ из 961 МБ на боксе.
# SKIP_SERVICE_RESTART=1 ставит remote-deploy.sh: он перезапускает сервисы сам и
# следом проверяет здоровье. Без флага каждая выкатка рвала работу ДВАЖДЫ —
# здесь и там, и Celery дважды убивал задачи на середине скачивания.
if [ "${SKIP_SERVICE_RESTART:-0}" != "1" ]; then
    for unit in tg-music-bot tg-music-api tg-music-worker tg-music-youtube-user \
                tg-music-soundcloud tg-music-youtube tg-music-support tg-music-moved; do
        if [ "$(systemctl is-enabled "$unit" 2>/dev/null)" = "enabled" ]; then
            systemctl restart "$unit"
            echo "    перезапущен $unit"
        else
            echo "    пропущен $unit (disabled)"
        fi
    done
else
    echo "    рестарт сервисов делает вызывающий (remote-deploy.sh)"
fi

echo
echo "==> Готово. Состояние:"
systemctl is-active tg-music-bot tg-music-worker tg-music-api tg-music-youtube-user tg-music-soundcloud || true
fail2ban-client status sshd 2>/dev/null || true
