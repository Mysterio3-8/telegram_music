#!/bin/bash
# Мировой каталог (SPEC-КАТАЛОГ §3-4): страны по очереди, затем привязка источников.
# Последовательно — MusicBrainz жёстко требует ≤1 req/sec с IP, параллелить нельзя.
# Запуск: nohup bash deploy/research_world.sh > /var/log/tg-music-research.log 2>&1 &
set -u
cd /opt/tg-music-bot

# ~3000 западных + ~500 мир (RU 1000 идёт отдельным первым прогоном)
COUNTRIES=(
  "US 1200" "GB 500" "DE 300" "FR 300" "SE 150" "IT 150" "ES 150"
  "CA 150" "AU 150" "KR 200" "JP 200" "IN 150" "BR 150" "MX 100"
  "UA 200" "KZ 100" "BY 100"
)

for entry in "${COUNTRIES[@]}"; do
  read -r code limit <<< "$entry"
  echo "=== $(date '+%F %T') research country $code (limit $limit) ==="
  .venv/bin/python -m app.cli.research country "$code" --limit "$limit"
  # источники привязываем после каждой страны — закачка стартует не дожидаясь конца всей очереди
  .venv/bin/python -m app.cli.research attach-sources --limit 10000
done

echo "=== $(date '+%F %T') DONE ==="
.venv/bin/python -m app.cli.research stats
