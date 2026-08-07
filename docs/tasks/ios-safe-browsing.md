# iOS: «Deceptive Website Warning»

**Статус:** 🔴 не решено, ждёт проверки на живом iPhone
**Из чек-листа:** [CHECKLIST.md](../../CHECKLIST.md) → «Болит сейчас»

## Симптом

На iPhone вместо Mini App — красный экран Safari. Подтверждено 21.07: у всех, не
только у владельца. iOS-аудитория отрезана от плеера, это блокер выручки.

## Что уже сделано (04.08)

Две прошлые сессии искали в контенте Mini App и в базах Google — всё чисто.
Искать надо было в поведении сервера: `try_files $uri /index.html` отдавал
**200 OK и HTML на любой путь**. В логах 2014 уникальных путей с 200:
`/apple-id/verify`, `/paypal`, `/.env`, `/.git/config`, полторы тысячи вебшеллов.
Плюс пустой `<div id="app">` без JS при бренде Telegram — профиль клоакинга.

Исправлено: несуществующий путь → 404, в `#app` описание сервиса, robots.txt,
security.txt, nosniff. Регрессия проверена на всех 2014 исторических путях.

Чисто: Search Console, Transparency Report, Spamhaus DBL/SURBL/URIBL, ZEN, SpamCop.
Домен создан 27.04.2026 — прошлого владельца не было.

## Что делать дальше

**Шаг 1 (за владельцем, 5 минут).** Открыть на iPhone `https://keybest.cc` в Safari
напрямую, потом через кнопку в боте.

| Результат | Значит | Действие |
|---|---|---|
| Ругается везде | Safe Browsing / WebKit | Шаг 2, потом переезд |
| Только в Telegram | Проверка Telegram | Писать @BotSupport |
| Нигде не ругается | Помогло | Закрываем |

**Шаг 2.** Апелляция: `https://safebrowsing.google.com/safebrowsing/report_error/?url=https://keybest.cc`
Текст обращения — в NEXT_SESSION.md.

**Шаг 3.** Переезд на `.ru`/`.com`/`.app` одной командой:
`bash deploy/migrate-domain.sh новый-домен.ru`

⚠️ Домены `.click` и `.xyz` не годятся — те же дешёвые зоны с плохой репутацией.
