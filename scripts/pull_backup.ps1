# Забирает свежий снимок базы с сервера на этот компьютер (16.09).
#
# Запускается задачей планировщика Windows «InfinityMusic — бэкап базы» раз в день
# и при входе в систему; пропущенный запуск (компьютер был выключен) догоняется сам.
# Копии — в «Документы\InfinityMusic\backups», хранится 7 последних.
# Восстановление — docs/БЭКАП.md.
$ErrorActionPreference = "Stop"

$root = Join-Path ([Environment]::GetFolderPath("MyDocuments")) "InfinityMusic"
$dest = Join-Path $root "backups"
New-Item -ItemType Directory -Force $dest | Out-Null
$log = Join-Path $root "pull.log"

$key = Join-Path $env:USERPROFILE ".ssh\id_ed25519"
$known = Join-Path $env:USERPROFILE ".ssh\known_hosts"
$server = "root@38.244.213.132"
# BatchMode: без интерактивных вопросов — задача планировщика ответить не сможет
$sshOpts = @("-i", $key, "-o", "UserKnownHostsFile=$known", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20")

try {
    $latest = (& ssh @sshOpts $server "ls -t /opt/tg-music-bot/backups/db-*.sqlite | head -1").Trim()
    if (-not $latest) { throw "на сервере нет снимков" }
    $name = Split-Path $latest -Leaf
    $target = Join-Path $dest $name
    if (Test-Path $target) {
        "$(Get-Date -Format s) уже есть $name" | Add-Content -Encoding utf8 $log
        exit 0
    }
    & scp @sshOpts "${server}:$latest" $target
    if (-not (Test-Path $target)) { throw "scp не скопировал $name" }
    Get-ChildItem $dest -Filter "db-*.sqlite" | Sort-Object LastWriteTime -Descending | Select-Object -Skip 7 | Remove-Item
    $size = [math]::Round((Get-Item $target).Length / 1MB, 1)
    "$(Get-Date -Format s) скопирован $name ($size МБ)" | Add-Content -Encoding utf8 $log
} catch {
    "$(Get-Date -Format s) ОШИБКА: $_" | Add-Content -Encoding utf8 $log
    exit 1
}
