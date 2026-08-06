"""Русский — источник правды. Все ключи заводятся здесь, потом переводятся."""

MESSAGES: dict[str, str] = {
    # --- слова с числом: ru требует трёх форм, остальным языкам хватает .one/.many
    "word.tracks.one": "трек",
    "word.tracks.few": "трека",
    "word.tracks.many": "треков",
    "word.friends.one": "друг",
    "word.friends.few": "друга",
    "word.friends.many": "друзей",
    "word.days.one": "день",
    "word.days.few": "дня",
    "word.days.many": "дней",
    "word.months.one": "месяц",
    "word.months.few": "месяца",
    "word.months.many": "месяцев",
    # --- общее
    "common.back": "◀️ Назад",
    "common.back_arrow": "⬅️ Назад",
    "common.back_to_menu": "◀️ В меню",
    "common.back_menu_long": "◀️ Назад в меню",
    "common.cancel": "◀️ Отмена",
    "common.page": "Страница {page} / {total_pages}",
    "common.updated": "Обновлено",
    "common.no_changes": "Пока без изменений",
    "common.error": "⚠️ Что-то пошло не так. Уже разбираемся — попробуйте ещё раз через минуту.",
    "common.throttled": "⏳ Слишком много запросов. Подождите пару секунд.",
    "common.file_unavailable": "Файл недоступен",
    "common.listen_all": "▶️ Слушать всё",
    "common.listen": "▶️ Слушать",
    "common.mix": "🎲 Микс",
    "common.artist_line": "Исполнитель: {artist}",
    "common.duration_line": "Длительность: {duration}",
    "common.enter_title": "Введите название",
    "common.miniapp_soon": "Mini App находится в разработке.",
    # --- кабинет и главное меню
    "cabinet.greeting": "👋 Привет, <b>{name}</b> · ID: <code>{telegram_id}</code>",
    "cabinet.premium_until": "💎 Premium до {date}",
    "cabinet.free_plan": "Бесплатный тариф",
    "cabinet.library": "🎵 В библиотеке: {count} {tracks_word}",
    "cabinet.hint": (
        "Просто отправьте название песни, исполнителя в чат этого бота — "
        "я моментально найду нужный трек."
    ),
    "cabinet.player_title": "🎧 <b>Открыть плеер</b>",
    "cabinet.player_pitch": (
        "Полноценный музыкальный сервис как VK или Apple Music: миксы, плейлисты, "
        "тексты песен, эквалайзер и офлайн-режим. Удобнее и лучше чем другие сервисы."
    ),
    "cabinet.price": "💎 {price} ₽/месяц • Первый день бесплатно и рефералки в боте и Mini App",
    "menu.player": "🎧 Открыть плеер",
    "menu.upload": "⬆️ Загрузить трек",
    "menu.premium": "💎 Открыть плеер — {price} ₽/мес",
    "menu.referral": "🎁 Реферальная программа",
    "menu.support": "🆘 Поддержка / жалобы / идеи",
    "menu.language": "🌍 Язык · Language",
    # --- язык
    "lang.title": "🌍 <b>Язык интерфейса</b>\n\nВыберите язык — он сохранится за вами.",
    "lang.saved": "Язык сохранён",
    "lang.pending": "Перевод на этот язык ещё готовится — пока интерфейс будет на английском.",
    "lang.back": "⬅️ Назад",
    # --- обязательная подписка
    "gate.text": (
        "🎵 Для использования ТГ Музыки подпишитесь на наши каналы.\n\n"
        "После подписки нажмите «Проверить подписку»."
    ),
    "gate.check": "✅ Проверить подписку",
    "gate.not_subscribed": "Не вижу подписку на все каналы. Подпишитесь и попробуйте снова.",
    "gate.confirmed": "✅ Подписка подтверждена",
    "gate.subscribe_first": "Сначала подпишитесь на каналы",
    # --- переезд на нового бота
    "moved.text": (
        "🎧 <b>Мы переехали</b>\n\n"
        "Этот бот больше не работает. Вся музыка, ваша библиотека и плейлисты "
        "ждут вас в новом боте — @{username}.\n\n"
        "Просто откройте его и нажмите «Начать»."
    ),
    "moved.button": "🎧 Перейти в новый бот",
    # --- библиотека
    "library.empty": (
        "🎵 Библиотека\n\nВсего треков: 0\n\n"
        "Библиотека пуста — добавьте треки через поиск или загрузку."
    ),
    "library.title": "🎵 Библиотека\n\nВсего треков: {count}",
    "library.search_button": "🔍 Найти в библиотеке",
    "library.nothing_found": "Ничего не найдено в вашей библиотеке.",
    "library.found": "Найдено в библиотеке: {count}",
    # --- плейлисты
    "playlists.title": "📂 Плейлисты\n\nВсего: {total}",
    "playlists.empty_hint": "\n\nПлейлистов пока нет — создайте первый.",
    "playlists.view": "Название:\n{title}\n\nВсего треков:\n{total}",
    "playlists.view_empty_hint": "\n\nПлейлист пуст — добавляйте треки из карточки трека.",
    "playlists.enter_title": "Введите название плейлиста",
    "playlists.title_length": "Название должно быть от 1 до {limit} символов. Попробуйте ещё раз.",
    "playlists.free_limit": (
        "На бесплатном тарифе доступно {limit} плейлистов.\n"
        "💎 Premium снимает лимит — раздел «Купить Premium» в меню."
    ),
    "playlists.created": "✅ Плейлист «{title}» создан.",
    "playlists.not_found": "Плейлист не найден",
    "playlists.delete_confirm": (
        "Удалить плейлист «{title}»?\n\nТреки останутся в базе и вашей библиотеке."
    ),
    "playlists.deleted": "Плейлист удалён",
    "playlists.create_button": "➕ Создать плейлист",
    "playlists.delete_button": "🗑 Удалить плейлист",
    "playlists.delete_yes": "🗑 Да, удалить",
    # --- поиск
    "search.nothing": "По запросу «{query}» ничего не найдено.",
    "search.results": "🔍 Результаты по запросу «{query}»\n\nНайдено: {total}",
    "search.enter_track": "Введите название трека",
    "search.searching_web": "🔎 Ищу в сети — пришлю трек через минуту.",
    "search.instrumental_not_found": "Минус не найден",
    "search.instrumental_card": "🎼 {title} (Минус)",
    # --- быстрый поиск
    "quick.nothing": (
        "Ничего не нашли. Попробуйте иначе — например «Kizaru Фейк Айди»: "
        "исполнитель и название вместе находятся точнее всего."
    ),
    "quick.stale": "Список устарел — повторите поиск.",
    "quick.results_title": "🎵 Треки по запросу «{query}»",
    "quick.searching": "🔎 Ищу…",
    "quick.sending": "Отправляю…",
    "quick.busy": "Сервис загрузки занят, попробуйте через минуту",
    "quick.downloading": "Загружаю трек — пришлю сюда",
    # --- карточка трека
    "card.title": "🎧 {title}",
    "card.not_found": "Трек не найден",
    "card.added": "Добавлено в библиотеку",
    "card.already": "Уже в библиотеке",
    "card.removed": "Удалено из библиотеки",
    "card.no_playlists": "У вас пока нет плейлистов — создайте в разделе 📂 Плейлисты",
    "card.added_to_playlist": "Добавлено в «{title}»",
    "card.already_in_playlist": "Трек уже в этом плейлисте",
    "card.removed_from_playlist": "Удалено из плейлиста",
    "card.share_text": "Поделитесь треком «{artist} — {title}»:",
    "card.add_library": "➕ Добавить в библиотеку",
    "card.remove_library": "🗑 Удалить из библиотеки",
    "card.add_playlist": "📂 Добавить в плейлист",
    "card.remove_playlist": "🗑 Удалить из плейлиста",
    "card.download": "⬇️ Скачать",
    "card.share": "📤 Поделиться",
    "card.edit_admin": "✏️ Редактировать (админ)",
    # --- плеер и очередь
    "player.next": "▶️ Дальше",
    "player.stop": "⏹ Остановить",
    "player.library_empty_add": "Библиотека пуста — добавьте треки",
    "player.mix_started": "🎶 Микс запущен",
    "player.mix_continue": "🎲 Продолжить микс",
    "player.library_empty": "Библиотека пуста",
    "player.queue_finished": "✅ Очередь закончилась",
    "player.playing_library": "▶️ Включаю библиотеку",
    "player.playlist_empty": "Плейлист пуст",
    "player.playlist_finished": "✅ Плейлист доигран",
    "player.playing_playlist": "▶️ Включаю «{title}»",
    "player.results_stale": "Результаты устарели — выполните поиск заново",
    "player.nothing_found": "Ничего не найдено",
    "player.results_finished": "✅ Результаты доиграны",
    "player.playing_results": "▶️ Включаю результаты поиска",
    "player.queue_stopped": "⏹ Очередь остановлена",
    # --- загрузка трека
    "upload.intro": (
        "⬆️ <b>Загрузка музыки</b>\n\n"
        "📎 <b>Аудиофайлом</b> — пришлите трек файлом. Столько треков, сколько хотите, "
        "хоть всю коллекцию по очереди — это <b>бесплатно и без лимитов</b>.\n\n"
        "🔗 <b>Ссылкой</b> — YouTube Music или SoundCloud:\n"
        "• один трек — <b>бесплатно</b>;\n"
        "• целый профиль, плейлист или лайки пачкой — <b>💎 Premium</b>.\n\n"
        "⚠️ Указывайте исполнителя — иначе трек станет «Неизвестным».\n\n"
        "Жду файл или ссылку 👇"
    ),
    "upload.confirm_button": "✅ Загрузить",
    "upload.enter_title": "Введите название.",
    "upload.as_audio": "Отправьте файл как аудио (музыку), а не как документ.",
    "upload.premium_bulk": (
        "Загрузка профиля, плейлиста или лайков целиком — только для 💎 Premium.\n"
        "Бесплатно можно загрузить трек по одному — пришлите ссылку на конкретный трек."
    ),
    "upload.reading_playlist": "🔍 Читаю плейлист…",
    "upload.playlist_failed": "Не удалось прочитать плейлист по ссылке. Проверьте её и попробуйте ещё раз.",
    "upload.unavailable": "Импорт сейчас недоступен — попробуйте позже.",
    "upload.queued_videos": (
        "⏳ Принято {queued} видео.\n\n"
        "Музыка появится в вашей библиотеке по мере обработки — без сообщений на каждый трек."
    ),
    "upload.reading_soundcloud": "🔍 Читаю страницу SoundCloud…",
    "upload.soundcloud_failed": "Не удалось прочитать страницу SoundCloud. Проверьте ссылку и попробуйте ещё раз.",
    "upload.queued_soundcloud": (
        "⏳ Принято {queued} треков с SoundCloud.\n\n"
        "Они появятся в вашей библиотеке по мере обработки — без сообщений на каждый трек."
    ),
    "upload.queued_one_soundcloud": "⏳ Принято! Скачаем трек с SoundCloud и пришлём сюда — обычно меньше минуты.",
    "upload.waiting_file": "Жду аудиофайл или ссылку на трек — YouTube Music или SoundCloud 🎵",
    "upload.checking_link": "🔍 Проверяю ссылку…",
    "upload.video_failed": "Не удалось открыть видео по ссылке. Проверьте её и попробуйте ещё раз.",
    "upload.live_stream": "Это прямой эфир — такие не принимаем.",
    "upload.queued_video": (
        "⏳ Принято: «{title}» ({duration}).\n"
        "Скачаем и пришлём трек сюда — обычно это занимает меньше минуты."
    ),
    "upload.title_length": "Название от 1 до 256 символов. Попробуйте ещё раз.",
    "upload.enter_artist": "Введите исполнителя.",
    "upload.artist_length": "Имя исполнителя от 1 до 256 символов. Попробуйте ещё раз.",
    "upload.duplicate_warning": (
        "\n\n⚠️ В базе уже есть «{artist} — {title}».\n"
        "Если это другой трек — вернитесь и поменяйте название "
        "(например, добавьте «(Rex)»). Иначе просто подтвердите."
    ),
    "upload.check_data": "Проверьте данные:\n\nНазвание: {title}\nИсполнитель: {artist}\nДлительность: {duration}",
    "upload.moderation": (
        "⏳ Трек «{artist} — {title}» добавлен в вашу библиотеку "
        "и отправлен на проверку — в общем каталоге появится после одобрения."
    ),
    "upload.done": "✅ Трек «{artist} — {title}» добавлен в общую базу и вашу библиотеку.",
    # --- Premium
    "premium.perks": (
        "🚫 <b>Без рекламы</b> — ни баннеров, ни пауз\n"
        "📥 <b>Офлайн-режим</b> — качайте треки, слушайте без интернета\n"
        "🔄 <b>Перенос пачкой</b> — целые плейлисты из Spotify, Яндекса, ВК, SoundCloud\n"
        "🎼 <b>Без лимитов</b> — сколько угодно плейлистов и своих загрузок\n"
        "🎛 <b>Эквалайзер и таймер сна</b> — 20 пресетов, засыпайте под музыку\n"
        "📝 <b>Тексты песен</b> — добавляйте и редактируйте\n"
        "🎁 <b>Дни в подарок</b> — достижения и друзья приносят ещё Premium"
    ),
    "premium.plan_year": "год",
    "premium.plan_month": "месяц",
    "premium.plan_months": "{months} {months_word}",
    "premium.active": "💎 <b>Premium активен</b> до {date}\n\nМожно продлить заранее — дни суммируются.",
    "premium.offer": (
        "💎 <b>TG Music Premium</b>\n\n"
        "Всего <b>{price} ₽ в месяц</b> — дешевле чашки кофе. "
        "Чем длиннее тариф, тем ниже цена месяца.\n\nВыберите срок:"
    ),
    "premium.invoice_title": "Premium на {label}",
    "premium.invoice_description": "Отключение рекламы, безлимит плейлистов, увеличенный лимит загрузок.",
    "premium.invoice_failed": "Не удалось выставить счёт — попробуйте позже",
    "premium.invoice_failed_card": "Не удалось выставить счёт — попробуйте позже или оплатите Stars",
    "premium.payment_failed": "Не удалось создать платёж — попробуйте позже",
    "premium.pay_intro": (
        "💳 Оплата {price} ₽ — Premium на {label}.\n\n"
        "Нажмите кнопку, оплатите любым удобным способом и вернитесь в бот — "
        "Premium включится автоматически в течение минуты."
    ),
    "premium.pay_button": "Оплатить {price} ₽",
    "premium.card_unavailable": "Оплата картой пока недоступна",
    "premium.bad_payment": "Некорректный платёж — попробуйте оформить заново",
    "premium.activated": "✅ Premium активирован до {date}! Спасибо за поддержку 💛",
    "premium.plan_button": "💳 {label} — {price} ₽{suffix}",
    "premium.per_month": " · {per_month} ₽/мес",
    "premium.discount": " · −{discount}%",
    "premium.month_short": "мес",
    "premium.disable_ads": "💎 Отключить рекламу (Premium)",
    "premium.continue": "Продолжить использование",
    # --- реклама
    "ads.text": (
        "📢 Реклама\n\nЗдесь могла быть ваша реклама.\n\n"
        "Отключите рекламу и получите безлимит с 💎 Premium."
    ),
    # --- рефералка
    "referral.forever": "Premium навсегда",
    "referral.reward_days": "{days} {days_word} Premium",
    "referral.rank": "{emoji} Ранг: <b>{title}</b>",
    "referral.to_next_rank": "До ранга {emoji} {title} — ещё {count} {friends_word}",
    "referral.next_reward": "\n🔥 Ещё {count} {friends_word} — и {reward}\n",
    "referral.title": "🎁 <b>Реферальная программа</b>",
    "referral.promise": (
        "<b>{count} {friends_word} — {reward}.</b> Награда приходит автоматически, "
        "как только друг начнёт слушать музыку по вашей ссылке."
    ),
    "referral.invited": "👥 Приглашено: <b>{count}</b>",
    "referral.your_link": "<b>Ваша ссылка</b> (нажмите, чтобы скопировать):",
    "referral.rewards": "<b>Награды</b>",
    "referral.discount_note": "Когда друг оплачивает подписку, вам падает скидка 50% на следующую покупку.",
    "referral.share_text": (
        "Держи бота, где можно найти и скачать любой трек бесплатно — "
        "просто пишешь название, и он присылает музыку."
    ),
    "referral.invite_button": "📤 Пригласить друга",
    "referral.refresh": "🔄 Обновить",
    # --- перенос из других сервисов
    "transfer.intro": (
        "📥 <b>Перенос музыки из других сервисов</b>\n\n"
        "Пришлите:\n"
        "▪️ ссылку на публичный плейлист <b>Spotify</b> или <b>Яндекс.Музыки</b>;\n"
        "▪️ ссылку на <b>SoundCloud</b> (профиль, лайки, сет);\n"
        "▪️ или просто список текстом, по строке на трек:\n"
        "<code>Kizaru — Fendi\nBig Baby Tape — Gimme the Loot</code>\n\n"
        "Так переносится музыка из ВКонтакте и откуда угодно ещё: скопируйте список "
        "и пришлите сюда.\n\n"
        "Мы найдём эти треки в нашей базе, а чего нет — загрузим."
    ),
    "transfer.button": "📥 Перенести",
    "transfer.cancelled": "Перенос отменён.",
    "transfer.soundcloud_hint": (
        "Ссылки SoundCloud принимает мастер «Загрузить трек» — он скачает "
        "аудио напрямую, без поиска совпадений."
    ),
    "transfer.reading": "Читаю список…",
    "transfer.parse_failed": "Не удалось прочитать список. Попробуйте прислать текстом.",
    "transfer.no_tracks": "Не нашёл треков. Формат строки: <code>Артист — Название</code>.",
    "transfer.more": "\n…и ещё {count}",
    "transfer.found": "Нашёл треков: <b>{count}</b>\n\n{preview}{tail}\n\nПереносим в вашу библиотеку?",
    "transfer.empty_list": "Список пуст — начните заново",
    "transfer.unavailable": "Перенос временно недоступен — фоновые задачи выключены.",
    "transfer.start_failed": "Не удалось запустить перенос — попробуйте позже.",
    "transfer.started": (
        "📥 Переношу {count} треков. Это займёт время — пришлю отчёт, когда закончу.\n\n"
        "Найденное в базе появится в библиотеке сразу."
    ),
    # --- конкурсы
    "contest.already": "Вы уже участвуете — ждём итогов 🍀",
    "contest.joined": "🎉 Вы в списке участников! Удачи в розыгрыше",
    "contest.finished": "Конкурс завершён",
    "contest.requirements": "Условия ещё не выполнены:",
    "contest.need_channel": "• подпишитесь на канал",
    "contest.need_referrals": "• пригласите друзей: {referrals} из {required}",
    "contest.subscribe": "📢 Подписаться на канал",
    "contest.participating": "✅ Вы участвуете",
    "contest.join": "🎉 Участвовать",
    "contest.open_app": "🎧 Открыть TG Music",
    # --- инлайн
    "inline.listen": "🎧 Слушать в TG Music",
    "inline.instrumental": "🎼 Минус",
    "inline.open": "🎧 Открыть TG Music",
}
