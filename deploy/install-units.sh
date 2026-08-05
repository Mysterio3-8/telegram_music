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

echo "==> logrotate: syslog/kern.log росли до сотен МБ между ротациями"
install -m 644 deploy/logrotate-rsyslog.conf /etc/logrotate.d/rsyslog
logrotate -f /etc/logrotate.d/rsyslog || true

echo "==> journald: держим журнал в рамках"
mkdir -p /etc/systemd/journald.conf.d
cat >/etc/systemd/journald.conf.d/limits.conf <<'EOF'
[Journal]
SystemMaxUse=150M
MaxRetentionSec=7day
EOF
systemctl restart systemd-journald

echo "==> fail2ban против SSH-брутфорса (btmp был на 114 МБ неудачных входов)"
if ! command -v fail2ban-client >/dev/null 2>&1; then
    apt-get update -qq && apt-get install -y -qq fail2ban
fi
mkdir -p /etc/fail2ban/jail.d
install -m 644 deploy/fail2ban-sshd.local /etc/fail2ban/jail.d/sshd.local
systemctl enable --now fail2ban
systemctl restart fail2ban

echo "==> Перечитываю systemd и поднимаю сервисы"
systemctl daemon-reload
# Только включённые: массовый парсер (tg-music-soundcloud, tg-music-youtube)
# выключен решением владельца 27.07 — поднимать его здесь значило бы тихо
# отменять это решение и занимать 180 МБ из 961 МБ на боксе.
for unit in tg-music-bot tg-music-api tg-music-worker tg-music-youtube-user \
            tg-music-soundcloud tg-music-youtube tg-music-support tg-music-moved; do
    if [ "$(systemctl is-enabled "$unit" 2>/dev/null)" = "enabled" ]; then
        systemctl restart "$unit"
        echo "    перезапущен $unit"
    else
        echo "    пропущен $unit (disabled)"
    fi
done

echo
echo "==> Готово. Состояние:"
systemctl is-active tg-music-bot tg-music-worker tg-music-api tg-music-youtube-user tg-music-soundcloud || true
fail2ban-client status sshd 2>/dev/null || true
