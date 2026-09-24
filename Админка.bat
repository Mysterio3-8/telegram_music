@echo off
chcp 65001 >nul
title Infinity Music - админка
cd /d "%~dp0"

rem Ярлык на рабочий стол: запускает админку только с этого компьютера.
rem Пропуск в три рубежа — SSH-ключ этой машины, пароль и код в Telegram.
rem Из интернета админки нет: на сервере она слушает только 127.0.0.1.

if not exist ".venv\Scripts\python.exe" (
  echo Не нашёл .venv в %CD%
  echo Положи этот файл рядом с проектом или создай окружение.
  pause
  exit /b 1
)

echo Поднимаю туннель к серверу и открываю админку...
".venv\Scripts\python.exe" -m app.webadmin
echo.
echo Админка закрыта.
pause
