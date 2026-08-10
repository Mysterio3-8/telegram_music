"""Deutsch. Preise bleiben in ₽ — Zahlungen laufen in Rubel."""

MESSAGES: dict[str, str] = {
    "word.tracks.one": "Titel",
    "word.tracks.many": "Titel",
    "word.friends.one": "Freund",
    "word.friends.many": "Freunde",
    "word.days.one": "Tag",
    "word.days.many": "Tage",
    "word.months.one": "Monat",
    "word.months.many": "Monate",
    "common.back": "◀️ Zurück",
    "common.back_arrow": "⬅️ Zurück",
    "common.back_to_menu": "◀️ Zum Menü",
    "common.back_menu_long": "◀️ Zurück zum Menü",
    "common.cancel": "◀️ Abbrechen",
    "common.page": "Seite {page} / {total_pages}",
    "common.updated": "Aktualisiert",
    "common.no_changes": "Noch nichts Neues",
    "common.error": "⚠️ Da ist etwas schiefgelaufen. Wir kümmern uns darum — versuch es gleich noch mal.",
    "common.throttled": "⏳ Zu viele Anfragen. Warte ein paar Sekunden.",
    "common.file_unavailable": "Datei nicht verfügbar",
    "common.listen_all": "▶️ Alles abspielen",
    "common.listen": "▶️ Abspielen",
    "common.mix": "🎲 Mix",
    "common.artist_line": "Interpret: {artist}",
    "common.duration_line": "Länge: {duration}",
    "common.enter_title": "Titel eingeben",
    "common.miniapp_soon": "Die Mini App ist noch in Arbeit.",
    "cabinet.greeting": "👋 Hallo, <b>{name}</b> · ID: <code>{telegram_id}</code>",
    "cabinet.premium_until": "💎 Premium bis {date}",
    "cabinet.free_plan": "Kostenloser Tarif",
    "cabinet.library": "🎵 In deiner Bibliothek: {count} {tracks_word}",
    "cabinet.hint": (
        "Schick einfach einen Songtitel oder einen Interpreten in diesen Chat — "
        "ich finde den Titel sofort."
    ),
    "cabinet.player_title": "🎧 <b>Player öffnen</b>",
    "cabinet.player_pitch": (
        "Ein vollwertiger Musikdienst wie VK oder Apple Music: Mixe, Playlists, "
        "Songtexte, Equalizer und Offline-Modus."
    ),
    "cabinet.price": "💎 {price} ₽/Monat • Erster Tag gratis",
    "menu.player": "🎧 Player öffnen",
    "menu.upload": "⬆️ Titel hochladen",
    "menu.premium": "💎 Player öffnen — {price} ₽/Mon.",
    "menu.referral": "🎁 Empfehlungsprogramm",
    "menu.support": "🆘 Support / Beschwerden / Ideen",
    "menu.language": "🌍 Язык · Language",
    "lang.title": "🌍 <b>Sprache der Oberfläche</b>\n\nWähle eine Sprache — wir merken sie uns.",
    "lang.saved": "Sprache gespeichert",
    "lang.pending": "Diese Sprache ist noch nicht übersetzt — die Oberfläche bleibt auf Englisch.",
    "lang.back": "⬅️ Zurück",
    "gate.text": (
        "🎵 Um Infinity Music zu nutzen, abonniere bitte unsere Kanäle.\n\n"
        "Danach tippe auf «Abo prüfen»."
    ),
    "gate.check": "✅ Abo prüfen",
    "gate.not_subscribed": "Ich sehe dich nicht in allen Kanälen. Abonniere sie und versuch es erneut.",
    "gate.confirmed": "✅ Abo bestätigt",
    "gate.subscribe_first": "Abonniere bitte zuerst die Kanäle",
    "moved.text": (
        "🎧 <b>Wir sind umgezogen</b>\n\n"
        "Dieser Bot läuft nicht mehr. Die ganze Musik, deine Bibliothek und deine "
        "Playlists warten im neuen Bot — @{username}.\n\n"
        "Öffne ihn einfach und tippe auf «Start»."
    ),
    "moved.button": "🎧 Zum neuen Bot",
    "library.empty": (
        "🎵 Bibliothek\n\nTitel: 0\n\n"
        "Deine Bibliothek ist leer — füge Titel über die Suche oder den Upload hinzu."
    ),
    "library.title": "🎵 Bibliothek\n\nTitel: {count}",
    "library.search_button": "🔍 In meiner Bibliothek suchen",
    "library.nothing_found": "In deiner Bibliothek nichts gefunden.",
    "library.found": "In der Bibliothek gefunden: {count}",
    "playlists.title": "📂 Playlists\n\nGesamt: {total}",
    "playlists.empty_hint": "\n\nNoch keine Playlists — leg die erste an.",
    "playlists.view": "Titel:\n{title}\n\nTitel insgesamt:\n{total}",
    "playlists.view_empty_hint": "\n\nDiese Playlist ist leer — füge Titel über die Titelkarte hinzu.",
    "playlists.enter_title": "Namen der Playlist eingeben",
    "playlists.title_length": "Der Name muss 1 bis {limit} Zeichen haben. Versuch es noch mal.",
    "playlists.free_limit": (
        "Im kostenlosen Tarif sind {limit} Playlists möglich.\n"
        "💎 Premium hebt das Limit auf — siehe «Premium kaufen» im Menü."
    ),
    "playlists.created": "✅ Playlist «{title}» erstellt.",
    "playlists.not_found": "Playlist nicht gefunden",
    "playlists.delete_confirm": (
        "Playlist «{title}» löschen?\n\nDie Titel bleiben im Katalog und in deiner Bibliothek."
    ),
    "playlists.deleted": "Playlist gelöscht",
    "playlists.create_button": "➕ Neue Playlist",
    "playlists.delete_button": "🗑 Playlist löschen",
    "playlists.delete_yes": "🗑 Ja, löschen",
    "search.nothing": "Für «{query}» wurde nichts gefunden.",
    "search.results": "🔍 Ergebnisse für «{query}»\n\nGefunden: {total}",
    "search.enter_track": "Titel eingeben",
    "search.searching_web": "🔎 Ich suche im Netz — der Titel kommt gleich.",
    "search.instrumental_not_found": "Instrumental nicht gefunden",
    "search.instrumental_card": "🎼 {title} (Instrumental)",
    "quick.nothing": (
        "Nichts gefunden. Probier es anders — zum Beispiel «Kizaru Fake ID»: "
        "Interpret und Titel zusammen treffen am genauesten."
    ),
    "quick.stale": "Diese Liste ist veraltet — such noch mal.",
    "quick.results_title": "🎵 Titel zu «{query}»",
    "quick.searching": "🔎 Ich suche…",
    "quick.sending": "Wird gesendet…",
    "quick.busy": "Der Download-Dienst ist ausgelastet, versuch es in einer Minute",
    "quick.downloading": "Ich lade den Titel — er kommt hierher",
    "card.title": "🎧 {title}",
    "card.not_found": "Titel nicht gefunden",
    "card.added": "Zur Bibliothek hinzugefügt",
    "card.already": "Schon in der Bibliothek",
    "card.removed": "Aus der Bibliothek entfernt",
    "card.no_playlists": "Du hast noch keine Playlists — leg eine unter 📂 Playlists an",
    "card.added_to_playlist": "Zu «{title}» hinzugefügt",
    "card.already_in_playlist": "Der Titel ist schon in dieser Playlist",
    "card.removed_from_playlist": "Aus der Playlist entfernt",
    "card.share_text": "Teile den Titel «{artist} — {title}»:",
    "card.add_library": "➕ Zur Bibliothek",
    "card.remove_library": "🗑 Aus der Bibliothek",
    "card.add_playlist": "📂 Zur Playlist",
    "card.remove_playlist": "🗑 Aus der Playlist",
    "card.download": "⬇️ Herunterladen",
    "card.share": "📤 Teilen",
    "card.edit_admin": "✏️ Bearbeiten (Admin)",
    "player.next": "▶️ Weiter",
    "player.stop": "⏹ Stopp",
    "player.library_empty_add": "Deine Bibliothek ist leer — füge Titel hinzu",
    "player.mix_started": "🎶 Mix gestartet",
    "player.mix_continue": "🎲 Mix fortsetzen",
    "player.library_empty": "Deine Bibliothek ist leer",
    "player.queue_finished": "✅ Die Warteschlange ist zu Ende",
    "player.playing_library": "▶️ Ich spiele deine Bibliothek",
    "player.playlist_empty": "Die Playlist ist leer",
    "player.playlist_finished": "✅ Playlist zu Ende",
    "player.playing_playlist": "▶️ Ich spiele «{title}»",
    "player.results_stale": "Diese Ergebnisse sind veraltet — such noch mal",
    "player.nothing_found": "Nichts gefunden",
    "player.results_finished": "✅ Ergebnisse zu Ende",
    "player.playing_results": "▶️ Ich spiele die Suchergebnisse",
    "player.queue_stopped": "⏹ Warteschlange gestoppt",
    "upload.intro": (
        "⬆️ <b>Musik hochladen</b>\n\n"
        "📎 <b>Als Datei</b> — schick den Titel als Audiodatei. So viele du willst, "
        "die ganze Sammlung nacheinander — <b>gratis und ohne Limit</b>.\n\n"
        "🔗 <b>Per Link</b> — YouTube Music oder SoundCloud:\n"
        "• ein einzelner Titel — <b>gratis</b>;\n"
        "• ein ganzes Profil, eine Playlist oder Likes am Stück — <b>💎 Premium</b>.\n\n"
        "⚠️ Gib den Interpreten an — sonst heißt der Titel «Unbekannt».\n\n"
        "Ich warte auf Datei oder Link 👇"
    ),
    "upload.confirm_button": "✅ Hochladen",
    "upload.enter_title": "Gib den Titel ein.",
    "upload.as_audio": "Schick die Datei als Audio (Musik), nicht als Dokument.",
    "upload.premium_bulk": (
        "Ein ganzes Profil, eine Playlist oder Likes hochzuladen ist nur mit 💎 Premium möglich.\n"
        "Gratis geht es einzeln — schick den Link zu einem konkreten Titel."
    ),
    "upload.reading_playlist": "🔍 Ich lese die Playlist…",
    "upload.playlist_failed": "Diese Playlist konnte ich nicht lesen. Prüf den Link und versuch es noch mal.",
    "upload.unavailable": "Der Import ist gerade nicht verfügbar — versuch es später.",
    "upload.queued_videos": (
        "⏳ {queued} Videos angenommen.\n\n"
        "Die Musik erscheint nach und nach in deiner Bibliothek — ohne Meldung pro Titel."
    ),
    "upload.reading_soundcloud": "🔍 Ich lese die SoundCloud-Seite…",
    "upload.soundcloud_failed": "Diese SoundCloud-Seite konnte ich nicht lesen. Prüf den Link und versuch es noch mal.",
    "upload.queued_soundcloud": (
        "⏳ {queued} Titel von SoundCloud angenommen.\n\n"
        "Sie erscheinen nach und nach in deiner Bibliothek — ohne Meldung pro Titel."
    ),
    "upload.queued_one_soundcloud": "⏳ Angenommen! Wir holen den Titel von SoundCloud und schicken ihn hierher — meist unter einer Minute.",
    "upload.waiting_file": "Ich warte auf eine Audiodatei oder einen Link — YouTube Music oder SoundCloud 🎵",
    "upload.checking_link": "🔍 Ich prüfe den Link…",
    "upload.video_failed": "Dieses Video konnte ich nicht öffnen. Prüf den Link und versuch es noch mal.",
    "upload.live_stream": "Das ist ein Livestream — den nehmen wir nicht.",
    "upload.queued_video": (
        "⏳ Angenommen: «{title}» ({duration}).\n"
        "Wir laden ihn herunter und schicken ihn hierher — meist unter einer Minute."
    ),
    "upload.title_length": "Der Titel muss 1 bis 256 Zeichen haben. Versuch es noch mal.",
    "upload.enter_artist": "Gib den Interpreten ein.",
    "upload.artist_length": "Der Name des Interpreten muss 1 bis 256 Zeichen haben. Versuch es noch mal.",
    "upload.duplicate_warning": (
        "\n\n⚠️ «{artist} — {title}» gibt es schon im Katalog.\n"
        "Wenn das ein anderer Titel ist, geh zurück und ändere den Namen "
        "(zum Beispiel «(Rex)» anhängen). Sonst bestätige einfach."
    ),
    "upload.check_data": "Prüf die Angaben:\n\nTitel: {title}\nInterpret: {artist}\nLänge: {duration}",
    "upload.moderation": (
        "⏳ «{artist} — {title}» wurde deiner Bibliothek hinzugefügt und zur Prüfung "
        "geschickt — im gemeinsamen Katalog erscheint der Titel nach der Freigabe."
    ),
    "upload.done": "✅ «{artist} — {title}» wurde in den gemeinsamen Katalog und deine Bibliothek aufgenommen.",
    "premium.perks": (
        "🚫 <b>Keine Werbung</b> — keine Banner, keine Unterbrechungen\n"
        "📥 <b>Offline-Modus</b> — Titel laden und ohne Internet hören\n"
        "🔄 <b>Übertragung am Stück</b> — ganze Playlists von Spotify, Yandex, VK, SoundCloud\n"
        "🎼 <b>Ohne Limits</b> — beliebig viele Playlists und eigene Uploads\n"
        "🎛 <b>Equalizer und Sleeptimer</b> — 20 Presets, schlaf zur Musik ein\n"
        "📝 <b>Songtexte</b> — hinzufügen und bearbeiten\n"
        "🎁 <b>Geschenktage</b> — Erfolge und Freunde bringen mehr Premium"
    ),
    "premium.plan_year": "ein Jahr",
    "premium.plan_month": "einen Monat",
    "premium.plan_months": "{months} {months_word}",
    "premium.active": "💎 <b>Premium ist aktiv</b> bis {date}\n\nDu kannst früher verlängern — die Tage summieren sich.",
    "premium.offer": (
        "💎 <b>Infinity Music Premium</b>\n\n"
        "Nur <b>{price} ₽ im Monat</b> — günstiger als ein Kaffee. "
        "Je länger der Tarif, desto niedriger der Monatspreis.\n\nWähle einen Zeitraum:"
    ),
    "premium.invoice_title": "Premium für {label}",
    "premium.invoice_description": "Keine Werbung, unbegrenzte Playlists, höheres Upload-Limit.",
    "premium.invoice_failed": "Rechnung konnte nicht erstellt werden — versuch es später",
    "premium.invoice_failed_card": "Rechnung konnte nicht erstellt werden — versuch es später oder zahl mit Stars",
    "premium.payment_failed": "Zahlung konnte nicht angelegt werden — versuch es später",
    "premium.pay_intro": (
        "💳 Zahlung über {price} ₽ — Premium für {label}.\n\n"
        "Tippe auf den Button, zahl wie du magst und komm zurück in den Bot — "
        "Premium schaltet sich innerhalb einer Minute von selbst frei."
    ),
    "premium.pay_button": "{price} ₽ zahlen",
    "premium.card_unavailable": "Kartenzahlung ist noch nicht verfügbar",
    "premium.bad_payment": "Ungültige Zahlung — bitte neu starten",
    "premium.activated": "✅ Premium ist aktiv bis {date}! Danke für die Unterstützung 💛",
    "premium.plan_button": "💳 {label} — {price} ₽{suffix}",
    "premium.per_month": " · {per_month} ₽/Mon.",
    "premium.discount": " · −{discount}%",
    "premium.month_short": "Mon.",
    "premium.disable_ads": "💎 Werbung abschalten (Premium)",
    "premium.continue": "Weiter nutzen",
    "ads.text": (
        "📢 Werbung\n\nHier könnte deine Werbung stehen.\n\n"
        "Schalt die Werbung ab und geh mit 💎 Premium ohne Limits."
    ),
    "referral.forever": "Infinity Premium",
    "referral.reward_days": "{days} {days_word} Premium",
    "referral.rank": "{emoji} Rang: <b>{title}</b>",
    "referral.to_next_rank": "Bis Rang {emoji} {title} — noch {count} {friends_word}",
    "referral.next_reward": "\n🔥 Noch {count} {friends_word} — und du bekommst {reward}\n",
    "referral.title": "🎁 <b>Empfehlungsprogramm</b>",
    "referral.invited": "👥 Eingeladen: <b>{count}</b>",
    "referral.your_link": "<b>Dein Link</b> (zum Kopieren antippen):",
    "referral.rewards": "<b>Belohnungen</b>",
    "referral.share_text": (
        "Schau mal, dieser Bot findet und lädt jeden Song gratis — "
        "du tippst einfach den Titel und er schickt dir die Musik."
    ),
    "referral.invite_button": "📤 Freund einladen",
    "referral.refresh": "🔄 Aktualisieren",
    "transfer.intro": (
        "📥 <b>Musik aus anderen Diensten übernehmen</b>\n\n"
        "Schick mir:\n"
        "▪️ einen Link zu einer öffentlichen <b>Spotify</b>- oder <b>Yandex Music</b>-Playlist;\n"
        "▪️ einen <b>SoundCloud</b>-Link (Profil, Likes, Set);\n"
        "▪️ oder einfach eine Textliste, ein Titel pro Zeile:\n"
        "<code>Kizaru — Fendi\nBig Baby Tape — Gimme the Loot</code>\n\n"
        "So kommt die Musik aus VK und von überall sonst herüber: Liste kopieren "
        "und hierher schicken.\n\n"
        "Wir suchen die Titel in unserem Katalog und laden nach, was fehlt."
    ),
    "transfer.button": "📥 Übernehmen",
    "transfer.cancelled": "Übernahme abgebrochen.",
    "transfer.soundcloud_hint": (
        "SoundCloud-Links nimmt der Assistent «Titel hochladen» — er lädt das Audio "
        "direkt, ohne nach Treffern zu suchen."
    ),
    "transfer.reading": "Ich lese die Liste…",
    "transfer.parse_failed": "Die Liste konnte ich nicht lesen. Schick sie als Text.",
    "transfer.no_tracks": "Keine Titel gefunden. Zeilenformat: <code>Interpret — Titel</code>.",
    "transfer.more": "\n…und {count} weitere",
    "transfer.found": "Gefundene Titel: <b>{count}</b>\n\n{preview}{tail}\n\nIn deine Bibliothek übernehmen?",
    "transfer.empty_list": "Die Liste ist leer — fang neu an",
    "transfer.unavailable": "Die Übernahme ist vorübergehend nicht möglich — Hintergrundaufgaben sind aus.",
    "transfer.start_failed": "Die Übernahme konnte nicht gestartet werden — versuch es später.",
    "transfer.started": (
        "📥 Ich übernehme {count} Titel. Das dauert etwas — ich melde mich, wenn es fertig ist.\n\n"
        "Was schon im Katalog ist, erscheint sofort in deiner Bibliothek."
    ),
    "contest.already": "Du bist schon dabei — wir warten auf die Ergebnisse 🍀",
    "contest.joined": "🎉 Du stehst auf der Liste! Viel Glück bei der Verlosung",
    "contest.finished": "Das Gewinnspiel ist beendet",
    "contest.requirements": "Es fehlen noch Voraussetzungen:",
    "contest.need_channel": "• abonniere den Kanal",
    "contest.need_referrals": "• lade Freunde ein: {referrals} von {required}",
    "contest.subscribe": "📢 Kanal abonnieren",
    "contest.participating": "✅ Du bist dabei",
    "contest.join": "🎉 Mitmachen",
    "contest.open_app": "🎧 Infinity Music öffnen",
    "inline.listen": "🎧 In Infinity Music hören",
    "inline.instrumental": "🎼 Instrumental",
    "inline.open": "🎧 Infinity Music öffnen",
}
