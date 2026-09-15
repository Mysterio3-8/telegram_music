#!/usr/bin/env bash
# Переезд Mini App на новый домен. Запускать на VPS от root:
#   cd /opt/tg-music-bot && bash deploy/migrate-domain.sh --check music-example.ru   # только проверки
#   cd /opt/tg-music-bot && bash deploy/migrate-domain.sh music-example.ru           # переезд
#
# Зачем: keybest.cc получает «Deceptive Website Warning» в Safari и в Telegram на
# iOS (подтверждено владельцем 15.09), хотя Google Safe Browsing показывает домен
# чистым. Профиль фишинг-кита устранён 04.08, предупреждение осталось.
#
# Делает: nginx-сайт под новый домен → сертификат Let's Encrypt → HTTP/2 →
# .env → кнопка Mini App в боте (Bot API) → перезапуск → старый домен 301 на новый.
# Идемпотентен: повторный запуск с тем же доменом ничего не ломает.
#
# ⚠️ Файлы репозитория здесь НЕ правятся: автодеплой делает `git reset --hard`
# и молча откатил бы такие правки. Всё доменное живёт в nginx и .env; упоминания
# в коде убраны (тест tests/test_no_hardcoded_domain.py).
#
# Руками после скрипта (он напомнит): вебхук в ЛК ЮKassa и проверка на iPhone.
set -euo pipefail

CHECK_ONLY=0
if [ "${1:-}" = "--check" ]; then
    CHECK_ONLY=1
    shift
fi
NEW_DOMAIN="${1:-}"
OLD_DOMAIN="${2:-keybest.cc}"
APP_DIR="/opt/tg-music-bot"
ENV_FILE="$APP_DIR/.env"
ENV_BACKUPS="/root/env-backups"
LOCK_FILE="/run/tg-music-deploy.lock"

if [ -z "$NEW_DOMAIN" ]; then
    echo "Использование: bash deploy/migrate-domain.sh [--check] <новый-домен> [старый-домен]" >&2
    exit 1
fi
if ! printf '%s' "$NEW_DOMAIN" | grep -qE '^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$'; then
    echo "«$NEW_DOMAIN» не похоже на домен (только строчные буквы, цифры, дефис, точки)" >&2
    exit 1
fi
if [ "$(id -u)" -ne 0 ]; then
    echo "Нужны права root" >&2
    exit 1
fi

env_value() {
    sed -n "s/^$1=//p" "$ENV_FILE" | tail -n1 | tr -d '\r"' | xargs 2>/dev/null
}

echo "==> Проверяю, что $NEW_DOMAIN указывает на этот сервер"
server_ip="$(curl -sS --max-time 10 https://api.ipify.org)"
domain_ip="$(getent ahostsv4 "$NEW_DOMAIN" | awk '{print $1}' | head -1)"
www_ip="$(getent ahostsv4 "www.$NEW_DOMAIN" | awk '{print $1}' | head -1)"
echo "    сервер $server_ip, $NEW_DOMAIN → ${domain_ip:-<нет>}, www.$NEW_DOMAIN → ${www_ip:-<нет>}"
if [ "$domain_ip" != "$server_ip" ]; then
    echo "A-запись $NEW_DOMAIN должна указывать на $server_ip. Пропиши у регистратора и дождись DNS." >&2
    exit 1
fi
with_www=0
[ "$www_ip" = "$server_ip" ] && with_www=1

echo "==> Порт 80 доступен снаружи (нужен certbot)"
code="$(curl -s -o /dev/null -m 15 -w '%{http_code}' "http://$NEW_DOMAIN/" || true)"
echo "    http://$NEW_DOMAIN/ → $code"
[ "$code" != "000" ] || { echo "http://$NEW_DOMAIN не отвечает — certbot не пройдёт" >&2; exit 1; }

[ -n "$(env_value BOT_TOKEN)" ] || { echo "В .env нет BOT_TOKEN — кнопку Mini App не выставить" >&2; exit 1; }

if [ "$CHECK_ONLY" = "1" ]; then
    echo
    echo "✅ Проверки пройдены. Переезд: bash deploy/migrate-domain.sh $NEW_DOMAIN"
    exit 0
fi

# Автодеплой не должен рестартовать сервисы посреди переезда.
exec 9>"$LOCK_FILE"
flock -w 600 9 || { echo "Идёт деплой дольше 10 минут — повтори позже" >&2; exit 1; }

echo "==> Собираю nginx-сайт для $NEW_DOMAIN"
site="/etc/nginx/sites-available/$NEW_DOMAIN"
if [ ! -f "$site" ]; then
    sed "s/keybest\.cc/$NEW_DOMAIN/g" "$APP_DIR/deploy/nginx-keybest.conf" > "$site"
fi
ln -sf "$site" "/etc/nginx/sites-enabled/$NEW_DOMAIN"
nginx -t
systemctl reload nginx

echo "==> Выпускаю сертификат"
domains=(-d "$NEW_DOMAIN")
[ "$with_www" = "1" ] && domains+=(-d "www.$NEW_DOMAIN")
certbot --nginx --non-interactive --agree-tos --redirect --register-unsafely-without-email "${domains[@]}"

echo "==> HTTP/2 (certbot его не ставит, а без него 50 модулей Mini App идут по шесть)"
# nginx 1.24: http2 — параметр listen; форма `http2 on;` появилась только в 1.25.1.
sed -i -E 's/listen (\[::\]:)?443 ssl;/listen \1443 ssl http2;/; s/listen \[::\]:443 ssl ipv6only=on;/listen [::]:443 ssl http2 ipv6only=on;/' "$site"
nginx -t
systemctl reload nginx

echo "==> Правлю .env (бэкап — в $ENV_BACKUPS, не в каталоге проекта)"
mkdir -p "$ENV_BACKUPS"
chmod 700 "$ENV_BACKUPS"
install -m 600 "$ENV_FILE" "$ENV_BACKUPS/env-before-domain-$(date +%s)"
grep -q '^PUBLIC_BASE_URL=' "$ENV_FILE" || echo "PUBLIC_BASE_URL=" >> "$ENV_FILE"
grep -q '^API_CORS_ORIGINS=' "$ENV_FILE" || echo "API_CORS_ORIGINS=" >> "$ENV_FILE"
sed -i "s|^PUBLIC_BASE_URL=.*|PUBLIC_BASE_URL=https://$NEW_DOMAIN|" "$ENV_FILE"
sed -i "s|^API_CORS_ORIGINS=.*|API_CORS_ORIGINS=https://$NEW_DOMAIN,https://$OLD_DOMAIN|" "$ENV_FILE"
chmod 600 "$ENV_FILE"
grep -E "^(PUBLIC_BASE_URL|API_CORS_ORIGINS)=" "$ENV_FILE"

echo "==> Старый домен $OLD_DOMAIN → 301 на новый"
old_site="/etc/nginx/sites-available/$OLD_DOMAIN"
if [ -f "$old_site" ] && ! grep -q "return 301 https://$NEW_DOMAIN" "$old_site"; then
    mkdir -p /root/nginx-backups
    cp "$old_site" "/root/nginx-backups/$OLD_DOMAIN.before-migration-$(date +%s)"
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
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
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

echo "==> Перезапускаю сервисы, которые читают PUBLIC_BASE_URL"
systemctl restart tg-music-api tg-music-bot tg-music-worker tg-music-youtube-user

echo "==> Кнопка Mini App в меню бота (Bot API, без BotFather)"
token="$(env_value BOT_TOKEN)"
menu="$(curl -sS -m 20 "https://api.telegram.org/bot${token}/setChatMenuButton" \
    -H 'Content-Type: application/json' \
    -d "{\"menu_button\":{\"type\":\"web_app\",\"text\":\"🎧 Плеер\",\"web_app\":{\"url\":\"https://$NEW_DOMAIN\"}}}" || true)"
case "$menu" in
    *'"ok":true'*) echo "    кнопка → https://$NEW_DOMAIN" ;;
    *) echo "    ⚠️ Bot API не принял кнопку — выставить в @BotFather → Menu Button → https://$NEW_DOMAIN" ;;
esac

echo "==> Проверка"
sleep 5
curl -sS -o /dev/null -w "корень           %{http_code} %{http_version}\n" "https://$NEW_DOMAIN/"
curl -sS -o /dev/null -w "несущ. путь      %{http_code} (ожидается 404)\n" "https://$NEW_DOMAIN/wp-login.php"
curl -sS -o /dev/null -w "API /health      %{http_code}\n" "https://$NEW_DOMAIN/api/health"
curl -sS -o /dev/null -w "старый→новый     %{http_code} (ожидается 301)\n" "https://$OLD_DOMAIN/"
systemctl is-active tg-music-api tg-music-bot tg-music-worker tg-music-youtube-user | tr '\n' ' '; echo

cat <<EOF

Готово. Осталось руками:
  1. ЛК ЮKassa → HTTP-уведомления → https://$NEW_DOMAIN/webhook/yookassa
  2. Открыть Mini App на реальном iPhone (Safari и Telegram) — предупреждения быть не должно
  3. Сказать Claude новый домен: он обновит deploy/nginx-keybest.conf и доки коммитом
EOF
