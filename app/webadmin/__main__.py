"""Открыть админку на своём компьютере (16.09).

    python -m app.webadmin                    # туннель к проду + браузер
    python -m app.webadmin --local            # локальная БД, без сервера (отладка)
    python -m app.webadmin --no-browser

Что происходит: поднимается SSH-туннель до сервера, где админка слушает только
127.0.0.1:8011, и та же страница открывается у тебя по http://127.0.0.1:8011.
Из интернета админки нет — пропуск это твой SSH-ключ, пароль вводить негде.

⚠️ Порт занят другим процессом — скрипт не станет молча показывать чужую
страницу, а скажет об этом: «админка открылась, а данные чужие» — худший вид
ошибки.
"""
import argparse
import socket
import subprocess
import sys
import time
import webbrowser

SSH_KEY = "C:/Users/Илья/.ssh/id_ed25519"
KNOWN_HOSTS = "C:/Users/Илья/.ssh/known_hosts"
HOST = "root@38.244.213.132"
REMOTE_PORT = 8011
LOCAL_PORT = 8011


def port_busy(port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(0.5)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def run_local(port: int, open_browser: bool) -> int:
    """Админка на локальной БД — для отладки самой страницы, без прода."""
    import uvicorn

    if open_browser:
        webbrowser.open(f"http://127.0.0.1:{port}/")
    uvicorn.run("app.webadmin.server:app", host="127.0.0.1", port=port, log_level="warning")
    return 0


def run_tunnel(port: int, open_browser: bool) -> int:
    if port_busy(port):
        print(f"Порт {port} уже занят. Закрой прошлую админку или укажи --port.")
        return 1
    command = [
        "ssh", "-i", SSH_KEY, "-o", f"UserKnownHostsFile={KNOWN_HOSTS}",
        "-o", "ExitOnForwardFailure=yes", "-N", "-L", f"{port}:127.0.0.1:{REMOTE_PORT}", HOST,
    ]
    print("Поднимаю туннель к серверу…")
    tunnel = subprocess.Popen(command)
    try:
        for _ in range(20):
            if port_busy(port):
                break
            if tunnel.poll() is not None:
                print("Туннель не поднялся: проверь SSH-доступ к серверу.")
                return 1
            time.sleep(0.5)
        else:
            print("Туннель поднялся, но админка не отвечает. На сервере: systemctl status tg-music-webadmin")
            return 1
        url = f"http://127.0.0.1:{port}/"
        print(f"Админка открыта: {url}\nЗакрыть — Ctrl+C в этом окне.")
        if open_browser:
            webbrowser.open(url)
        tunnel.wait()
    except KeyboardInterrupt:
        print("\nЗакрываю туннель.")
    finally:
        tunnel.terminate()
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local", action="store_true", help="локальная БД вместо прода")
    parser.add_argument("--port", type=int, default=LOCAL_PORT)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    runner = run_local if args.local else run_tunnel
    sys.exit(runner(args.port, not args.no_browser))


if __name__ == "__main__":
    main()
