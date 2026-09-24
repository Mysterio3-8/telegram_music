"""Строка WEBADMIN_PASSWORD_HASH для .env.

    python -m app.cli.webadmin_password

Пароль спрашивается скрытым вводом и никуда не пишется: в .env уезжает только
pbkdf2-хеш с солью. Даже получив файл настроек, пароль из него не достать
перебором за разумное время — раундов 200 тысяч.
"""
import getpass
import sys

from app.webadmin.auth import hash_password


def main() -> None:
    first = getpass.getpass("Новый пароль админки: ")
    if len(first) < 8:
        print("Слишком короткий пароль — нужно хотя бы 8 символов.")
        sys.exit(1)
    if first != getpass.getpass("Повторите: "):
        print("Пароли не совпали.")
        sys.exit(1)
    print("\nВставь эту строку в .env на сервере:\n")
    print(f"WEBADMIN_PASSWORD_HASH={hash_password(first)}")
    print("\nПосле правки .env: systemctl restart tg-music-webadmin")


if __name__ == "__main__":
    main()
