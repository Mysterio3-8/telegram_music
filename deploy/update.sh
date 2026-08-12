#!/usr/bin/env bash
# Обновить прод до последнего коммита из GitHub. Запускать НА СЕРВЕРЕ от root:
#
#   cd /opt/tg-music-bot && bash deploy/update.sh
#
# Делает всё, что нужно, в правильном порядке, и останавливается на первой
# ошибке — половина обновления хуже, чем никакого.
set -euo pipefail

cd /opt/tg-music-bot

echo "==> Забираю код"
# Локальные правки на сервере ломали git pull («Your local changes would be
# overwritten»). Прод — не место для правок: источник правды это GitHub.
if ! git diff --quiet; then
    echo "    на сервере есть изменённые файлы, откатываю их к версии из GitHub:"
    git diff --name-only | sed 's/^/      /'
    git checkout -- .
fi
git pull

echo "==> Зависимости"
.venv/bin/pip install -q -r requirements.txt

echo "==> Миграции базы"
.venv/bin/alembic upgrade head

echo "==> Юниты, сторож, перезапуск сервисов"
bash deploy/install-units.sh

# Кэш выдачи живёт 3 часа и хранит СОБРАННЫЕ старым кодом списки: пока он не
# протухнет, правки поиска не видны, и деплой выглядит «не доехавшим». Дважды
# за вечер 11.08 это съело время на диагностику совершенно исправного деплоя.
echo "==> Сбрасываю кэш выдачи поиска"
deleted=$(redis-cli --scan --pattern 'livesearch:*' | xargs -r redis-cli del || echo 0)
echo "    удалено записей: ${deleted:-0}"

echo
echo "==> Готово. Проверь, что всё живо:"
systemctl is-active tg-music-bot tg-music-worker tg-music-youtube-user tg-music-api || true
