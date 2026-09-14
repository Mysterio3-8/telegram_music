# Забирает журнал ошибок прода на компьютер владельца (решение 14.09: «пока комп
# включён — хоть что-то будет»). Источник — /var/lib/tg-music-health/errors.log,
# его пишет сторож deploy/healthcheck.sh раз в 2 минуты. Запускается задачей
# планировщика Windows «InfinityMusic-PullErrors» раз в 10 минут.
#
# Копия, а не единственное место: основная доставка — сообщение в Telegram.
$ErrorActionPreference = "SilentlyContinue"
$root = Split-Path -Parent $PSScriptRoot
$dest = Join-Path $root "logs\prod"
New-Item -ItemType Directory -Force $dest | Out-Null

$key = "$env:USERPROFILE\.ssh\id_ed25519"
$known = "$env:USERPROFILE\.ssh\known_hosts"
$target = "root@38.244.213.132"

foreach ($name in @("errors.log", "history.log")) {
    scp -q -i $key -o UserKnownHostsFile=$known -o ConnectTimeout=15 -o BatchMode=yes `
        "${target}:/var/lib/tg-music-health/$name" (Join-Path $dest $name)
}
"$(Get-Date -Format s) pull exit=$LASTEXITCODE" | Out-File -Append -Encoding utf8 (Join-Path $dest "pull.log")
