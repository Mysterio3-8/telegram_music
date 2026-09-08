#!/usr/bin/env bash
# Разовая настройка автодеплоя. Запускать НА СЕРВЕРЕ от root:
#
#   cd /opt/tg-music-bot && bash deploy/autodeploy-setup.sh
#
# Скрипт заводит отдельный SSH-ключ для GitHub и печатает то, что нужно
# вставить в настройки репозитория. Больше ничего делать не придётся.
#
# ⚠️ Ключ намеренно урезан: в authorized_keys он записан с `command=`, то есть
# умеет РОВНО ОДНО — запустить выкатку. Даже если приватная часть утечёт из
# секретов GitHub, ею нельзя ни зайти в консоль, ни прочитать файлы, ни
# пробросить порт. Это главная защита всей конструкции.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KEY_PATH=/root/.ssh/tg-music-deploy
DEPLOY_CMD="bash $REPO_DIR/deploy/remote-deploy.sh"

mkdir -p /root/.ssh
chmod 700 /root/.ssh

if [ -f "$KEY_PATH" ]; then
    echo "Ключ $KEY_PATH уже есть — использую его, новый не создаю."
else
    echo "==> Создаю отдельный ключ для деплоя"
    ssh-keygen -t ed25519 -N "" -C "github-actions-deploy" -f "$KEY_PATH" >/dev/null
fi

PUB=$(cat "${KEY_PATH}.pub")
# Ограничения: только команда деплоя, без консоли, проброса портов и агента.
ENTRY="command=\"$DEPLOY_CMD\",no-agent-forwarding,no-port-forwarding,no-pty,no-user-rc,no-X11-forwarding $PUB"

touch /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
if grep -qF "$PUB" /root/.ssh/authorized_keys; then
    # Запись могла остаться со старыми ограничениями — переписываем.
    grep -vF "$PUB" /root/.ssh/authorized_keys > /root/.ssh/authorized_keys.tmp || true
    mv /root/.ssh/authorized_keys.tmp /root/.ssh/authorized_keys
fi
echo "$ENTRY" >> /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
echo "==> Ключ прописан в /root/.ssh/authorized_keys (только команда деплоя)"

IP=$(curl -s -m 10 https://api.ipify.org 2>/dev/null || hostname -I | awk '{print $1}')

cat <<INSTRUCTIONS

================================================================
 ОСТАЛОСЬ ОДНО: вставить три значения на GitHub
================================================================

Откройте в браузере:

  https://github.com/Mysterio3-8/telegram_music/settings/secrets/actions

Нажмите зелёную кнопку «New repository secret» и заведите ТРИ штуки.
Каждый раз: вписать Name, вставить Secret, нажать «Add secret».

────────────────────────────────────────────────────────────────
 1)  Name:    VPS_HOST
     Secret:  $IP
────────────────────────────────────────────────────────────────
 2)  Name:    VPS_USER
     Secret:  root
────────────────────────────────────────────────────────────────
 3)  Name:    VPS_SSH_KEY
     Secret:  скопируйте ВСЁ, что между линиями ниже,
              вместе со строками BEGIN и END

INSTRUCTIONS

echo "----------------- КОПИРОВАТЬ ОТСЮДА -----------------"
cat "$KEY_PATH"
echo "----------------- КОПИРОВАТЬ ДОСЮДА -----------------"

cat <<'DONE'

================================================================
Всё. После этого каждый раз, когда изменения попадают в main,
GitHub сам прогонит тесты и выкатит их на сервер.
Отчёт придёт вам в Telegram.

Проверить, что работает:
  https://github.com/Mysterio3-8/telegram_music/actions

⚠️ Приватный ключ выше — секрет. Не пересылайте его в чатах и не
   публикуйте. Если случайно засветили, запустите этот скрипт
   заново после удаления /root/.ssh/tg-music-deploy — он выпустит
   новый ключ, а старый перестанет работать.
DONE
