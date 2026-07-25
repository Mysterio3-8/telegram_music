#!/bin/bash
# Автономный дискавери артистов для массового парсера SoundCloud (блок C, цель
# владельца: 10k артистов / 1M треков, топ → андеграунд, без участия владельца).
#
# Что делает: перебирает страны (топовые артисты) и жанровые сиды (уходит вглубь,
# в андеграунд), после каждого прогона привязывает SoundCloud-источники — они
# уходят в ежедневную закачку (youtube scan-due). Крутится бесконечно: MusicBrainz
# содержит куда больше 10k артистов, каждый проход добавляет новых.
#
# MusicBrainz жёстко требует ≤1 req/sec с IP (троттлинг вшит в клиент) —
# параллелить НЕЛЬЗЯ, только последовательно.
#
# Запуск: setsid bash deploy/discover_loop.sh > /var/log/tg-music-discover.log 2>&1 &
set -u
cd /opt/tg-music-bot
PY=.venv/bin/python

# Топ-чарты по странам (популярное — вперёд)
COUNTRIES=(
  "US 1500" "RU 1500" "GB 800" "DE 500" "FR 500" "KR 400" "JP 400"
  "SE 300" "IT 300" "ES 300" "CA 300" "AU 300" "BR 300" "IN 300"
  "UA 300" "KZ 200" "BY 200" "PL 200" "NL 200" "MX 200" "TR 200"
)

# Жанровые сиды — уводят в андеграунд за пределы страновых чартов
GENRE_SEEDS=(
  "phonk" "drift phonk" "hip hop" "trap" "cloud rap" "hyperpop" "drill"
  "russian rap" "grime" "lo-fi" "ambient" "techno" "house" "dnb"
  "hardstyle" "shoegaze" "post punk" "indie rock" "metalcore" "k-pop"
  "reggaeton" "afrobeats" "jersey club" "breakcore" "witch house"
)

pass=0
while true; do
  pass=$((pass + 1))
  echo "=== $(date '+%F %T') PASS $pass — страны ==="
  for entry in "${COUNTRIES[@]}"; do
    read -r code limit <<< "$entry"
    echo "--- $(date '+%F %T') country $code (limit $limit) ---"
    $PY -m app.cli.research country "$code" --limit "$limit" || true
    $PY -m app.cli.research attach-sources --limit 20000 || true
  done

  echo "=== $(date '+%F %T') PASS $pass — жанры (андеграунд) ==="
  for seed in "${GENRE_SEEDS[@]}"; do
    echo "--- $(date '+%F %T') search '$seed' ---"
    $PY -m app.cli.research search "$seed" --limit 500 || true
    $PY -m app.cli.research attach-sources --limit 20000 || true
  done

  echo "=== $(date '+%F %T') PASS $pass DONE ==="
  $PY -m app.cli.research stats || true
  # пауза между полными проходами — не молотим MusicBrainz без остановки
  sleep 3600
done
