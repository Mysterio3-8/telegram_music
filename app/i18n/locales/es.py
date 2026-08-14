"""Español. Los precios se mantienen en ₽ — los pagos se procesan en rublos."""

MESSAGES: dict[str, str] = {
    "word.tracks.one": "pista",
    "word.tracks.many": "pistas",
    "word.friends.one": "amigo",
    "word.friends.many": "amigos",
    "word.days.one": "día",
    "word.days.many": "días",
    "word.months.one": "mes",
    "word.months.many": "meses",
    "common.back": "◀️ Atrás",
    "common.back_arrow": "⬅️ Atrás",
    "common.back_to_menu": "◀️ Al menú",
    "common.back_menu_long": "◀️ Volver al menú",
    "common.cancel": "◀️ Cancelar",
    "common.page": "Página {page} / {total_pages}",
    "common.updated": "Actualizado",
    "common.no_changes": "Todavía sin novedades",
    "common.error": "⚠️ Algo salió mal. Ya lo estamos revisando — inténtalo de nuevo en un minuto.",
    "common.throttled": "⏳ Demasiadas peticiones. Espera un par de segundos.",
    "common.file_unavailable": "Archivo no disponible",
    "common.listen_all": "▶️ Reproducir todo",
    "common.listen": "▶️ Reproducir",
    "common.mix": "🎲 Mix",
    "common.artist_line": "Artista: {artist}",
    "common.duration_line": "Duración: {duration}",
    "common.enter_title": "Escribe un título",
    "common.miniapp_soon": "La Mini App todavía está en desarrollo.",
    "cabinet.greeting": "👋 Hola, <b>{name}</b> · ID: <code>{telegram_id}</code>",
    "cabinet.premium_until": "💎 Premium hasta el {date}",
    "cabinet.free_plan": "Plan gratuito",
    "cabinet.library": "🎵 En tu biblioteca: {count} {tracks_word}",
    "cabinet.hint": (
        "Envía el título de una canción o un artista a este chat — "
        "encontraré la pista al instante."
    ),
    "cabinet.player_title": "🎧 <b>Abrir el reproductor</b>",
    "cabinet.player_pitch": (
        "Un servicio de música completo, como VK o Apple Music: mixes, listas, "
        "letras, ecualizador y modo sin conexión."
    ),
    "cabinet.price": "💎 {price} ₽/mes • Primer día gratis",
    "menu.player": "🎧 Abrir el reproductor",
    "menu.upload": "⬆️ Subir una pista",
    "menu.premium": "💎 Abrir el reproductor — {price} ₽/mes",
    "menu.referral": "🎁 Programa de referidos",
    "menu.playlists": "🗂 Mis listas",
    "menu.support": "🆘 Soporte / quejas / ideas",
    "menu.language": "🌍 Язык · Language",
    "lang.title": "🌍 <b>Idioma de la interfaz</b>\n\nElige un idioma — lo recordaremos.",
    "lang.saved": "Idioma guardado",
    "lang.pending": "Este idioma aún no está traducido — la interfaz seguirá en inglés.",
    "lang.back": "⬅️ Atrás",
    "gate.text": (
        "🎵 Para usar Infinity Music, suscríbete a nuestros canales.\n\n"
        "Cuando lo hayas hecho, pulsa «Comprobar suscripción»."
    ),
    "gate.check": "✅ Comprobar suscripción",
    "gate.not_subscribed": "No te veo en todos los canales. Suscríbete e inténtalo de nuevo.",
    "gate.confirmed": "✅ Suscripción confirmada",
    "gate.subscribe_first": "Primero suscríbete a los canales",
    "moved.text": (
        "🎧 <b>Nos hemos mudado</b>\n\n"
        "Este bot ya no funciona. Toda la música, tu biblioteca y tus listas "
        "te esperan en el nuevo bot — @{username}.\n\n"
        "Ábrelo y pulsa «Iniciar»."
    ),
    "moved.button": "🎧 Ir al nuevo bot",
    "library.empty": (
        "🎵 Biblioteca\n\nPistas: 0\n\n"
        "Tu biblioteca está vacía — añade pistas con la búsqueda o subiéndolas."
    ),
    "library.title": "🎵 Biblioteca\n\nPistas: {count}",
    "library.search_button": "🔍 Buscar en mi biblioteca",
    "library.nothing_found": "No hay nada en tu biblioteca.",
    "library.found": "Encontrado en tu biblioteca: {count}",
    "playlists.title": "📂 Listas\n\nTotal: {total}",
    "playlists.empty_hint": "\n\nTodavía no hay listas — crea la primera.",
    "playlists.view": "Título:\n{title}\n\nPistas:\n{total}",
    "playlists.view_empty_hint": "\n\nEsta lista está vacía — añade pistas desde su ficha.",
    "playlists.enter_title": "Escribe el título de la lista",
    "playlists.title_length": "El título debe tener entre 1 y {limit} caracteres. Inténtalo otra vez.",
    "playlists.free_limit": (
        "El plan gratuito permite {limit} listas.\n"
        "💎 Premium quita el límite — mira «Comprar Premium» en el menú."
    ),
    "playlists.created": "✅ Lista «{title}» creada.",
    "playlists.not_found": "Lista no encontrada",
    "playlists.delete_confirm": (
        "¿Eliminar la lista «{title}»?\n\nLas pistas seguirán en el catálogo y en tu biblioteca."
    ),
    "playlists.deleted": "Lista eliminada",
    "playlists.create_button": "➕ Nueva lista",
    "playlists.delete_button": "🗑 Eliminar lista",
    "playlists.delete_yes": "🗑 Sí, eliminar",
    "search.nothing": "No se encontró nada para «{query}».",
    "search.results": "🔍 Resultados de «{query}»\n\nEncontrados: {total}",
    "search.enter_track": "Escribe el título de la pista",
    "search.searching_web": "🔎 Buscando en la red — te enviaré la pista en un momento.",
    "search.instrumental_not_found": "Instrumental no encontrado",
    "search.instrumental_card": "🎼 {title} (Instrumental)",
    "quick.nothing": (
        "No encontré nada. Prueba de otra forma — «Kizaru Fake ID», por ejemplo: "
        "artista y título juntos dan el mejor resultado."
    ),
    "quick.stale": "Esta lista ha caducado — busca de nuevo.",
    "quick.results_title": "🎵 Pistas para «{query}»",
    "quick.searching": "🔎 Buscando…",
    "quick.sending": "Enviando…",
    "quick.busy": "El servicio de descarga está ocupado, inténtalo en un minuto",
    "quick.downloading": "Descargando la pista — llegará aquí",
    "quick.already_fetching": "Ya estoy descargando esta pista — llegará en unos segundos",
    "quality.note_high": "🎚 Mejor calidad disponible · {format} · {size} MB",
    "quality.note_lossless": "🎚 Original del autor · {format} · {size} MB",
    "quick.preparing_best": "Preparando la mejor calidad — llegará aquí",
    "menu.settings": "⚙️ Ajustes",
    "settings.title": "<b>⚙️ Ajustes</b>",
    "settings.quality_hint": "La calidad en la que llegan las pistas.\n\n<b>Normal</b> — mp3 128 kbps, lo que reciben todos hoy.\n<b>Mejor</b> — el máximo que ofrece la fuente: 160 kbps y, en algunas pistas, el archivo original del autor (WAV o FLAC). Tarda unos segundos más y pesa más.",
    "settings.quality_mp3": "🎵 Normal · mp3 128",
    "settings.quality_best": "🎚 Mejor calidad (Premium)",
    "settings.quality_premium_only": "La mejor calidad está incluida en Premium.",
    "settings.quality_saved_mp3": "Listo: las pistas llegan como antes",
    "settings.quality_saved_best": "Listo. Ahora las pistas llegan con lo mejor que ofrece la fuente: el original del autor donde existe, si no 160 kbps en lugar de 128. Donde no hay ninguno, recibirás el archivo de siempre, sin errores ni esperas.",
    "settings.back": "◀️ Atrás",
    "settings.cover_hint": "<b>La portada</b> ya va incrustada en el archivo y se ve en el reproductor. Actívala como imagen aparte si guardas la música en tu propia biblioteca.",
    "settings.cover_on": "🖼 Portada aparte — activada",
    "settings.cover_off": "🖼 Portada aparte — desactivada",
    "card.title": "🎧 {title}",
    "card.not_found": "Pista no encontrada",
    "card.added": "Añadida a tu biblioteca",
    "card.already": "Ya está en tu biblioteca",
    "card.removed": "Eliminada de tu biblioteca",
    "card.no_playlists": "Todavía no tienes listas — crea una en 📂 Listas",
    "card.added_to_playlist": "Añadida a «{title}»",
    "card.already_in_playlist": "La pista ya está en esta lista",
    "card.removed_from_playlist": "Eliminada de la lista",
    "card.share_text": "Comparte la pista «{artist} — {title}»:",
    "card.add_library": "➕ Añadir a la biblioteca",
    "card.remove_library": "🗑 Quitar de la biblioteca",
    "card.add_playlist": "📂 Añadir a una lista",
    "card.remove_playlist": "🗑 Quitar de la lista",
    "card.download": "⬇️ Descargar",
    "card.share": "📤 Compartir",
    "card.edit_admin": "✏️ Editar (admin)",
    "player.next": "▶️ Siguiente",
    "player.stop": "⏹ Parar",
    "player.library_empty_add": "Tu biblioteca está vacía — añade pistas",
    "player.mix_started": "🎶 Mix iniciado",
    "player.mix_continue": "🎲 Continuar el mix",
    "player.library_empty": "Tu biblioteca está vacía",
    "player.queue_finished": "✅ La cola ha terminado",
    "player.playing_library": "▶️ Reproduciendo tu biblioteca",
    "player.playlist_empty": "La lista está vacía",
    "player.playlist_finished": "✅ Lista terminada",
    "player.playing_playlist": "▶️ Reproduciendo «{title}»",
    "player.results_stale": "Estos resultados han caducado — busca de nuevo",
    "player.nothing_found": "No se encontró nada",
    "player.results_finished": "✅ Resultados terminados",
    "player.playing_results": "▶️ Reproduciendo los resultados",
    "player.queue_stopped": "⏹ Cola detenida",
    "upload.intro": (
        "⬆️ <b>Subir música</b>\n\n"
        "📎 <b>Como archivo</b> — envía la pista como archivo de audio. Tantas como "
        "quieras, toda tu colección una a una — es <b>gratis y sin límites</b>.\n\n"
        "🔗 <b>Por enlace</b> — YouTube Music o SoundCloud:\n"
        "• una sola pista — <b>gratis</b>;\n"
        "• un perfil, lista o «me gusta» enteros — <b>💎 Premium</b>.\n\n"
        "⚠️ Indica el artista — si no, la pista quedará como «Desconocido».\n\n"
        "Envía un archivo o un enlace 👇"
    ),
    "upload.confirm_button": "✅ Subir",
    "upload.enter_title": "Escribe el título.",
    "upload.as_audio": "Envía el archivo como audio (música), no como documento.",
    "upload.premium_bulk": (
        "Subir un perfil, lista o «me gusta» completos es solo para 💎 Premium.\n"
        "Gratis puedes subir de una en una — envía el enlace de una pista concreta."
    ),
    "upload.reading_playlist": "🔍 Leyendo la lista…",
    "upload.playlist_failed": "No pude leer esa lista. Revisa el enlace e inténtalo otra vez.",
    "upload.unavailable": "La importación no está disponible ahora — inténtalo más tarde.",
    "upload.queued_videos": (
        "⏳ Aceptados {queued} vídeos.\n\n"
        "La música irá apareciendo en tu biblioteca — sin un mensaje por cada pista."
    ),
    "upload.reading_soundcloud": "🔍 Leyendo la página de SoundCloud…",
    "upload.soundcloud_failed": "No pude leer esa página de SoundCloud. Revisa el enlace e inténtalo otra vez.",
    "upload.queued_soundcloud": (
        "⏳ Aceptadas {queued} pistas de SoundCloud.\n\n"
        "Irán apareciendo en tu biblioteca — sin un mensaje por cada pista."
    ),
    "upload.queued_one_soundcloud": "⏳ ¡Recibido! Descargaremos la pista de SoundCloud y te la enviaremos aquí — normalmente en menos de un minuto.",
    "upload.waiting_file": "Espero un archivo de audio o un enlace — YouTube Music o SoundCloud 🎵",
    "upload.checking_link": "🔍 Comprobando el enlace…",
    "upload.video_failed": "No pude abrir ese vídeo. Revisa el enlace e inténtalo otra vez.",
    "upload.live_stream": "Eso es una retransmisión en directo — no las aceptamos.",
    "upload.queued_video": (
        "⏳ Aceptado: «{title}» ({duration}).\n"
        "Lo descargaremos y te enviaremos la pista aquí — normalmente en menos de un minuto."
    ),
    "upload.title_length": "El título debe tener entre 1 y 256 caracteres. Inténtalo otra vez.",
    "upload.enter_artist": "Escribe el artista.",
    "upload.artist_length": "El nombre del artista debe tener entre 1 y 256 caracteres. Inténtalo otra vez.",
    "upload.duplicate_warning": (
        "\n\n⚠️ «{artist} — {title}» ya está en el catálogo.\n"
        "Si es una pista distinta, vuelve atrás y cambia el título "
        "(añade «(Rex)», por ejemplo). Si no, simplemente confirma."
    ),
    "upload.check_data": "Revisa los datos:\n\nTítulo: {title}\nArtista: {artist}\nDuración: {duration}",
    "upload.moderation": (
        "⏳ «{artist} — {title}» se añadió a tu biblioteca y pasó a revisión — "
        "aparecerá en el catálogo común cuando se apruebe."
    ),
    "upload.done": "✅ «{artist} — {title}» se añadió al catálogo común y a tu biblioteca.",
    "premium.perks": (
        "🚫 <b>Sin anuncios</b> — ni banners ni pausas\n"
        "📥 <b>Modo sin conexión</b> — descarga pistas y escucha sin internet\n"
        "🔄 <b>Traslado en bloque</b> — listas enteras de Spotify, Yandex, VK, SoundCloud\n"
        "🎼 <b>Sin límites</b> — todas las listas y subidas que quieras\n"
        "🎛 <b>Ecualizador y temporizador</b> — 20 preajustes, duérmete con música\n"
        "📝 <b>Letras</b> — añádelas y edítalas\n"
        "🎁 <b>Días de regalo</b> — los logros y los amigos traen más Premium"
    ),
    "premium.plan_year": "un año",
    "premium.plan_month": "un mes",
    "premium.plan_months": "{months} {months_word}",
    "premium.active": "💎 <b>Premium activo</b> hasta el {date}\n\nPuedes renovar antes — los días se suman.",
    "premium.offer": (
        "💎 <b>Infinity Music Premium</b>\n\n"
        "Solo <b>{price} ₽ al mes</b> — más barato que un café. "
        "Cuanto más largo el plan, menor el precio mensual.\n\nElige un plan:"
    ),
    "premium.invoice_title": "Premium por {label}",
    "premium.invoice_description": "Sin anuncios, listas ilimitadas y un límite de subidas mayor.",
    "premium.invoice_failed": "No se pudo emitir la factura — inténtalo más tarde",
    "premium.invoice_failed_card": "No se pudo emitir la factura — inténtalo más tarde o paga con Stars",
    "premium.payment_failed": "No se pudo crear el pago — inténtalo más tarde",
    "premium.pay_intro": (
        "💳 Pago de {price} ₽ — Premium por {label}.\n\n"
        "Pulsa el botón, paga como prefieras y vuelve al bot — "
        "Premium se activará solo en menos de un minuto."
    ),
    "premium.pay_button": "Pagar {price} ₽",
    "premium.card_unavailable": "El pago con tarjeta todavía no está disponible",
    "premium.bad_payment": "Pago no válido — vuelve a empezar",
    "premium.activated": "✅ ¡Premium activo hasta el {date}! Gracias por el apoyo 💛",
    "premium.plan_button": "{label} — {price} ₽{suffix}",
    "premium.method_title": "<b>Premium por {label}</b>\n\n¿Cómo prefieres pagar?\n\n⭐ <b>{stars} Stars</b> — dentro de Telegram, sin tarjeta\n💳 <b>{price} ₽</b> — tarjeta o SBP",
    "premium.pay_stars": "⭐ Pagar {stars} Stars",
    "premium.pay_rub": "💳 Pagar {price} ₽",
    "premium.per_month": " · {per_month} ₽/mes",
    "premium.discount": " · −{discount}%",
    "premium.month_short": "mes",
    "premium.disable_ads": "💎 Quitar anuncios (Premium)",
    "premium.continue": "Seguir usando el bot",
    "ads.text": (
        "📢 Publicidad\n\nAquí podría estar tu anuncio.\n\n"
        "Quita los anuncios y ve sin límites con 💎 Premium."
    ),
    "referral.forever": "Infinity Premium",
    "referral.reward_days": "{days} {days_word} de Premium",
    "referral.rank": "{emoji} Rango: <b>{title}</b>",
    "referral.to_next_rank": "Para el rango {emoji} {title} — {count} {friends_word} más",
    "referral.next_reward": "\n🔥 {count} {friends_word} más — y recibes {reward}\n",
    "referral.title": "🎁 <b>Programa de referidos</b>",
    "referral.invited": "👥 Invitados: <b>{count}</b>",
    "referral.your_link": "<b>Tu enlace</b> (pulsa para copiar):",
    "referral.rewards": "<b>Recompensas</b>",
    "referral.share_text": (
        "Mira este bot: encuentra y descarga cualquier canción gratis — "
        "solo escribes el título y te envía la música."
    ),
    "referral.invite_button": "📤 Invitar a un amigo",
    "referral.refresh": "🔄 Actualizar",
    "transfer.intro": (
        "📥 <b>Traslada tu música de otros servicios</b>\n\n"
        "Envíame:\n"
        "▪️ un enlace a una lista pública de <b>Spotify</b> o <b>Yandex Music</b>;\n"
        "▪️ un enlace de <b>SoundCloud</b> (perfil, «me gusta», set);\n"
        "▪️ o simplemente una lista en texto, una pista por línea:\n"
        "<code>Kizaru — Fendi\nBig Baby Tape — Gimme the Loot</code>\n\n"
        "Así se traslada la música desde VK y desde cualquier otro sitio: copia la "
        "lista y envíala aquí.\n\n"
        "Buscaremos esas pistas en nuestro catálogo y descargaremos las que falten."
    ),
    "transfer.button": "📥 Trasladar",
    "transfer.cancelled": "Traslado cancelado.",
    "transfer.soundcloud_hint": (
        "Los enlaces de SoundCloud van al asistente «Subir una pista» — descarga "
        "el audio directamente, sin buscar coincidencias."
    ),
    "transfer.reading": "Leyendo la lista…",
    "transfer.parse_failed": "No pude leer la lista. Prueba a enviarla como texto.",
    "transfer.no_tracks": "No encontré pistas. Formato de línea: <code>Artista — Título</code>.",
    "transfer.more": "\n…y {count} más",
    "transfer.found": "Pistas encontradas: <b>{count}</b>\n\n{preview}{tail}\n\n¿Las paso a tu biblioteca?",
    "transfer.empty_list": "La lista está vacía — empieza de nuevo",
    "transfer.unavailable": "El traslado no está disponible — las tareas en segundo plano están apagadas.",
    "transfer.start_failed": "No se pudo iniciar el traslado — inténtalo más tarde.",
    "transfer.started": (
        "📥 Trasladando {count} pistas. Tardará un rato — te enviaré un informe al terminar.\n\n"
        "Lo que ya esté en el catálogo aparecerá en tu biblioteca enseguida."
    ),
    "contest.already": "Ya participas — esperamos los resultados 🍀",
    "contest.joined": "🎉 ¡Estás en la lista! Suerte en el sorteo",
    "contest.finished": "El concurso ha terminado",
    "contest.requirements": "Todavía faltan requisitos:",
    "contest.need_channel": "• suscríbete al canal",
    "contest.need_referrals": "• invita amigos: {referrals} de {required}",
    "contest.subscribe": "📢 Suscribirse al canal",
    "contest.participating": "✅ Ya participas",
    "contest.join": "🎉 Participar",
    "contest.open_app": "🎧 Abrir Infinity Music",
    "inline.listen": "🎧 Escuchar en Infinity Music",
    "inline.instrumental": "🎼 Instrumental",
    "inline.open": "🎧 Abrir Infinity Music",
}
