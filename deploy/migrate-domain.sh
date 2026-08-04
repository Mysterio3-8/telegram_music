#!/usr/bin/env bash
# Переезд Mini App на новый домен. Запускать на VPS от root:
#   cd /opt/tg-music-bot && bash deploy/migrate-domain.sh music-example.ru
#
# Делает: nginx-сайт под новый домен → сертификат Let's Encrypt → правит .env →
# перезапускает сервисы → оставляет старый домен с 301 на новый.
# Идемпотентен: повторный запуск с тем же доменом ничего не ломает.
#
# ⚠️ Два шага скрипт сделать не может, их выполняет владелец руками (напомним в конце):
#   1. @BotFather → /setmenubutton → новый URL кнопки Mini App
#   2. ЛК ЮKassa → вебхук на https://<новый-домен>/webhook/yookassa
set -euo pipefail

NEW_DOMAIN="${1:-}"
OLD_DOMAIN="${2:-keybest.cc}"
APP_DIR="/opt/tg-music-bot"
ENV_FILE="$APP_DIR/.env"

if [ -z "$NEW_DOMAIN" ]; then
    echo "Использование: bash deploy/migrate-domain.sh <новый-домен> [старый-домен]" >&2
    exit 1
fi

if [ "$(id -u)" -ne 0 ]; then
    echo "Нужны права root" >&2
    exit 1
fi

echo "==> Проверяю, что $NEW_DOMAIN указывает на этот сервер"
server_ip="$(curl -sS --max-time 10 https://api.ipify.org)"
domain_ip="$(getent hosts "$NEW_DOMAIN" | awk '{print $1}' | head -1)"
if [ "$domain_ip" != "$server_ip" ]; then
    echo "A-запись $NEW_DOMAIN = ${domain_ip:-<нет>}, а сервер = $server_ip." >&2
    echo "Сначала пропиши A-запись у регистратора и дождись обновления DNS." >&2
    exit 1
fi

echo "==> Собираю nginx-сайт для $NEW_DOMAIN"
site="/etc/nginx/sites-available/$NEW_DOMAIN"
sed "s/keybest\.cc/$NEW_DOMAIN/g" "$APP_DIR/deploy/nginx-keybest.conf" > "$site"
ln -sf "$site" "/etc/nginx/sites-enabled/$NEW_DOMAIN"
nginx -t
systemctl reload nginx

echo "==> Выпускаю сертификат"
certbot --nginx --non-interactive --agree-tos --redirect \
    -d "$NEW_DOMAIN" -d "www.$NEW_DOMAIN" \
    --register-unsafely-without-email || \
    certbot --nginx --non-interactive --agree-tos --redirect -d "$NEW_DOMAIN"

echo "==> Правлю .env"
cp "$ENV_FILE" "$ENV_FILE.bak-$(date +%s)"
sed -i "s|^PUBLIC_BASE_URL=.*|PUBLIC_BASE_URL=https://$NEW_DOMAIN|" "$ENV_FILE"
sed -i "s|^API_CORS_ORIGINS=.*|API_CORS_ORIGINS=https://$NEW_DOMAIN,https://$OLD_DOMAIN|" "$ENV_FILE"
grep -E "^(PUBLIC_BASE_URL|API_CORS_ORIGINS)=" "$ENV_FILE"

echo "==> Старый домен $OLD_DOMAIN → 301 на новый"
old_site="/etc/nginx/sites-available/$OLD_DOMAIN"
if [ -f "$old_site" ]; then
    cp "$old_site" "$old_site.bak-$(date +%s)"
    cat > "$old_site" <<EOF
# Старый домен: только редирект. Сертификат оставлен, чтобы HTTPS-ссылки
# из закэшированных Mini App доезжали до нового домена без ошибки TLS.
server {
    listen 80;
    listen [::]:80;
    server_name $OLD_DOMAIN www.$OLD_DOMAIN;
    return 301 https://$NEW_DOMAIN\$request_uri;
}

server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name $OLD_DOMAIN www.$OLD_DOMAIN;

    ssl_certificate /etc/letsencrypt/live/$OLD_DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$OLD_DOMAIN/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/options-ssl-dhparams.pem;

    return 301 https://$NEW_DOMAIN\$request_uri;
}
EOF
    nginx -t
    systemctl reload nginx
fi

echo "==> Перезапускаю сервисы"
systemctl restart tg-music-api tg-music-bot

echo "==> Проверка"
curl -sS -o /dev/null -w "корень      %{http_code}\n" "https://$NEW_DOMAIN/"
curl -sS -o /dev/null -w "несущ. путь %{http_code} (ожидается 404)\n" "https://$NEW_DOMAIN/wp-login.php"
curl -sS -o /dev/null -w "старый→новый %{http_code} (ожидается 301)\n" "https://$OLD_DOMAIN/"

cat <<EOF

Готово. Осталось руками:
  1. @BotFather → /mybots → tgram_music_bot → Bot Settings → Menu Button
     → новый URL: https://$NEW_DOMAIN
  2. ЛК ЮKassa → вебхук: https://$NEW_DOMAIN/webhook/yookassa
  3. Открыть Mini App на реальном iPhone — проверить, что предупреждения нет
  4. Обновить домен в доках: CLAUDE.md, NEXT_SESSION.md, miniapp/README.md
EOF
