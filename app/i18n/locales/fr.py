"""Français. Les prix restent en ₽ — les paiements se font en roubles."""

MESSAGES: dict[str, str] = {
    "word.tracks.one": "titre",
    "word.tracks.many": "titres",
    "word.friends.one": "ami",
    "word.friends.many": "amis",
    "word.days.one": "jour",
    "word.days.many": "jours",
    "word.months.one": "mois",
    "word.months.many": "mois",
    "common.back": "◀️ Retour",
    "common.back_arrow": "⬅️ Retour",
    "common.back_to_menu": "◀️ Menu",
    "common.back_menu_long": "◀️ Retour au menu",
    "common.cancel": "◀️ Annuler",
    "common.page": "Page {page} / {total_pages}",
    "common.updated": "Mis à jour",
    "common.no_changes": "Rien de neuf pour l'instant",
    "common.error": "⚠️ Quelque chose a mal tourné. On s'en occupe — réessaie dans une minute.",
    "common.throttled": "⏳ Trop de requêtes. Attends deux secondes.",
    "common.file_unavailable": "Fichier indisponible",
    "common.listen_all": "▶️ Tout écouter",
    "common.listen": "▶️ Écouter",
    "common.mix": "🎲 Mix",
    "common.artist_line": "Artiste : {artist}",
    "common.duration_line": "Durée : {duration}",
    "common.enter_title": "Saisis un titre",
    "common.miniapp_soon": "La Mini App est encore en développement.",
    "cabinet.greeting": "👋 Salut, <b>{name}</b> · ID : <code>{telegram_id}</code>",
    "cabinet.premium_until": "💎 Premium jusqu'au {date}",
    "cabinet.free_plan": "Formule gratuite",
    "cabinet.library": "🎵 Dans ta bibliothèque : {count} {tracks_word}",
    "cabinet.hint": (
        "Envoie simplement un titre ou un artiste dans ce chat — "
        "je trouve le morceau tout de suite."
    ),
    "cabinet.player_title": "🎧 <b>Ouvrir le lecteur</b>",
    "cabinet.player_pitch": (
        "Un vrai service musical, comme VK ou Apple Music : mixes, playlists, "
        "paroles, égaliseur et mode hors ligne."
    ),
    "cabinet.price": "💎 {price} ₽/mois • Premier jour offert",
    "menu.player": "🎧 Ouvrir le lecteur",
    "menu.upload": "⬆️ Envoyer un morceau",
    "menu.premium": "💎 Ouvrir le lecteur — {price} ₽/mois",
    "menu.referral": "🎁 Programme de parrainage",
    "menu.support": "🆘 Support / signalements / idées",
    "menu.language": "🌍 Язык · Language",
    "lang.title": "🌍 <b>Langue de l'interface</b>\n\nChoisis une langue — on s'en souviendra.",
    "lang.saved": "Langue enregistrée",
    "lang.pending": "Cette langue n'est pas encore traduite — l'interface reste en anglais.",
    "lang.back": "⬅️ Retour",
    "gate.text": (
        "🎵 Pour utiliser Infinity Music, abonne-toi à nos chaînes.\n\n"
        "Ensuite, appuie sur « Vérifier l'abonnement »."
    ),
    "gate.check": "✅ Vérifier l'abonnement",
    "gate.not_subscribed": "Je ne te vois pas dans toutes les chaînes. Abonne-toi et réessaie.",
    "gate.confirmed": "✅ Abonnement confirmé",
    "gate.subscribe_first": "Abonne-toi d'abord aux chaînes",
    "moved.text": (
        "🎧 <b>Nous avons déménagé</b>\n\n"
        "Ce bot ne fonctionne plus. Toute la musique, ta bibliothèque et tes playlists "
        "t'attendent dans le nouveau bot — @{username}.\n\n"
        "Ouvre-le et appuie sur « Démarrer »."
    ),
    "moved.button": "🎧 Aller vers le nouveau bot",
    "library.empty": (
        "🎵 Bibliothèque\n\nMorceaux : 0\n\n"
        "Ta bibliothèque est vide — ajoute des morceaux via la recherche ou l'envoi."
    ),
    "library.title": "🎵 Bibliothèque\n\nMorceaux : {count}",
    "library.search_button": "🔍 Chercher dans ma bibliothèque",
    "library.nothing_found": "Rien trouvé dans ta bibliothèque.",
    "library.found": "Trouvé dans la bibliothèque : {count}",
    "playlists.title": "📂 Playlists\n\nTotal : {total}",
    "playlists.empty_hint": "\n\nPas encore de playlist — crée la première.",
    "playlists.view": "Nom :\n{title}\n\nMorceaux :\n{total}",
    "playlists.view_empty_hint": "\n\nCette playlist est vide — ajoute des morceaux depuis leur fiche.",
    "playlists.enter_title": "Saisis le nom de la playlist",
    "playlists.title_length": "Le nom doit faire de 1 à {limit} caractères. Réessaie.",
    "playlists.free_limit": (
        "La formule gratuite permet {limit} playlists.\n"
        "💎 Premium lève la limite — voir « Acheter Premium » dans le menu."
    ),
    "playlists.created": "✅ Playlist « {title} » créée.",
    "playlists.not_found": "Playlist introuvable",
    "playlists.delete_confirm": (
        "Supprimer la playlist « {title} » ?\n\nLes morceaux restent dans le catalogue et ta bibliothèque."
    ),
    "playlists.deleted": "Playlist supprimée",
    "playlists.create_button": "➕ Nouvelle playlist",
    "playlists.delete_button": "🗑 Supprimer la playlist",
    "playlists.delete_yes": "🗑 Oui, supprimer",
    "search.nothing": "Rien trouvé pour « {query} ».",
    "search.results": "🔍 Résultats pour « {query} »\n\nTrouvés : {total}",
    "search.enter_track": "Saisis le titre du morceau",
    "search.searching_web": "🔎 Je cherche sur le web — le morceau arrive.",
    "search.instrumental_not_found": "Instrumental introuvable",
    "search.instrumental_card": "🎼 {title} (Instrumental)",
    "quick.nothing": (
        "Rien trouvé. Essaie autrement — « Kizaru Fake ID » par exemple : "
        "artiste et titre ensemble donnent le meilleur résultat."
    ),
    "quick.stale": "Cette liste est périmée — relance la recherche.",
    "quick.results_title": "🎵 Morceaux pour « {query} »",
    "quick.searching": "🔎 Je cherche…",
    "quick.sending": "Envoi…",
    "quick.busy": "Le service de téléchargement est occupé, réessaie dans une minute",
    "quick.downloading": "Je télécharge le morceau — il arrive ici",
    "quick.already_fetching": "Ce morceau est déjà en téléchargement — il arrive dans quelques secondes",
    "quality.note_high": "🎚 Meilleure qualité disponible · {format} · {size} Mo",
    "quality.note_lossless": "🎚 Original de l'auteur · {format} · {size} Mo",
    "quick.preparing_best": "Je prépare la meilleure qualité — elle arrive ici",
    "menu.settings": "⚙️ Réglages",
    "settings.title": "<b>⚙️ Réglages</b>",
    "settings.quality_hint": "La qualité dans laquelle arrivent les morceaux.\n\n<b>Normale</b> — mp3 128 kbps, ce que tout le monde reçoit aujourd'hui.\n<b>Meilleure</b> — le maximum proposé par la source : 160 kbps, et pour certains morceaux le fichier original de l'auteur (WAV ou FLAC). Quelques secondes de plus et un fichier plus lourd.",
    "settings.quality_mp3": "🎵 Normale · mp3 128",
    "settings.quality_best": "🎚 Meilleure qualité (Premium)",
    "settings.quality_premium_only": "La meilleure qualité fait partie de l'abonnement Premium.",
    "settings.quality_saved_mp3": "C'est fait : les morceaux arrivent comme avant",
    "settings.quality_saved_best": "C'est fait. Les morceaux arrivent désormais au mieux de ce que propose la source : l'original de l'auteur là où il existe, sinon 160 kbps au lieu de 128. À défaut des deux, vous recevez le fichier habituel, sans erreur ni attente.",
    "settings.back": "◀️ Retour",
    "card.title": "🎧 {title}",
    "card.not_found": "Morceau introuvable",
    "card.added": "Ajouté à ta bibliothèque",
    "card.already": "Déjà dans ta bibliothèque",
    "card.removed": "Retiré de ta bibliothèque",
    "card.no_playlists": "Tu n'as pas encore de playlist — crée-en une dans 📂 Playlists",
    "card.added_to_playlist": "Ajouté à « {title} »",
    "card.already_in_playlist": "Le morceau est déjà dans cette playlist",
    "card.removed_from_playlist": "Retiré de la playlist",
    "card.share_text": "Partage le morceau « {artist} — {title} » :",
    "card.add_library": "➕ Ajouter à la bibliothèque",
    "card.remove_library": "🗑 Retirer de la bibliothèque",
    "card.add_playlist": "📂 Ajouter à une playlist",
    "card.remove_playlist": "🗑 Retirer de la playlist",
    "card.download": "⬇️ Télécharger",
    "card.share": "📤 Partager",
    "card.edit_admin": "✏️ Modifier (admin)",
    "player.next": "▶️ Suivant",
    "player.stop": "⏹ Arrêter",
    "player.library_empty_add": "Ta bibliothèque est vide — ajoute des morceaux",
    "player.mix_started": "🎶 Mix lancé",
    "player.mix_continue": "🎲 Continuer le mix",
    "player.library_empty": "Ta bibliothèque est vide",
    "player.queue_finished": "✅ La file est terminée",
    "player.playing_library": "▶️ Je lance ta bibliothèque",
    "player.playlist_empty": "La playlist est vide",
    "player.playlist_finished": "✅ Playlist terminée",
    "player.playing_playlist": "▶️ Je lance « {title} »",
    "player.results_stale": "Ces résultats sont périmés — relance la recherche",
    "player.nothing_found": "Rien trouvé",
    "player.results_finished": "✅ Résultats terminés",
    "player.playing_results": "▶️ Je lance les résultats",
    "player.queue_stopped": "⏹ File arrêtée",
    "upload.intro": (
        "⬆️ <b>Envoyer de la musique</b>\n\n"
        "📎 <b>En fichier</b> — envoie le morceau en fichier audio. Autant que tu veux, "
        "toute ta collection l'une après l'autre — c'est <b>gratuit et sans limite</b>.\n\n"
        "🔗 <b>Par lien</b> — YouTube Music ou SoundCloud :\n"
        "• un seul morceau — <b>gratuit</b> ;\n"
        "• un profil, une playlist ou des favoris entiers — <b>💎 Premium</b>.\n\n"
        "⚠️ Indique l'artiste — sinon le morceau deviendra « Inconnu ».\n\n"
        "J'attends un fichier ou un lien 👇"
    ),
    "upload.confirm_button": "✅ Envoyer",
    "upload.enter_title": "Saisis le titre.",
    "upload.as_audio": "Envoie le fichier en audio (musique), pas en document.",
    "upload.premium_bulk": (
        "Envoyer un profil, une playlist ou des favoris entiers est réservé au 💎 Premium.\n"
        "Gratuitement, c'est un morceau à la fois — envoie le lien d'un morceau précis."
    ),
    "upload.reading_playlist": "🔍 Je lis la playlist…",
    "upload.playlist_failed": "Je n'ai pas pu lire cette playlist. Vérifie le lien et réessaie.",
    "upload.unavailable": "L'import est indisponible pour l'instant — réessaie plus tard.",
    "upload.queued_videos": (
        "⏳ {queued} vidéos acceptées.\n\n"
        "La musique apparaîtra dans ta bibliothèque au fur et à mesure — sans message par morceau."
    ),
    "upload.reading_soundcloud": "🔍 Je lis la page SoundCloud…",
    "upload.soundcloud_failed": "Je n'ai pas pu lire cette page SoundCloud. Vérifie le lien et réessaie.",
    "upload.queued_soundcloud": (
        "⏳ {queued} morceaux acceptés depuis SoundCloud.\n\n"
        "Ils apparaîtront dans ta bibliothèque au fur et à mesure — sans message par morceau."
    ),
    "upload.queued_one_soundcloud": "⏳ C'est noté ! On récupère le morceau sur SoundCloud et on l'envoie ici — moins d'une minute en général.",
    "upload.waiting_file": "J'attends un fichier audio ou un lien — YouTube Music ou SoundCloud 🎵",
    "upload.checking_link": "🔍 Je vérifie le lien…",
    "upload.video_failed": "Je n'ai pas pu ouvrir cette vidéo. Vérifie le lien et réessaie.",
    "upload.live_stream": "C'est un direct — on ne les prend pas.",
    "upload.queued_video": (
        "⏳ Accepté : « {title} » ({duration}).\n"
        "On le télécharge et on l'envoie ici — moins d'une minute en général."
    ),
    "upload.title_length": "Le titre doit faire de 1 à 256 caractères. Réessaie.",
    "upload.enter_artist": "Saisis l'artiste.",
    "upload.artist_length": "Le nom de l'artiste doit faire de 1 à 256 caractères. Réessaie.",
    "upload.duplicate_warning": (
        "\n\n⚠️ « {artist} — {title} » existe déjà dans le catalogue.\n"
        "Si c'est un autre morceau, reviens en arrière et change le titre "
        "(ajoute « (Rex) » par exemple). Sinon, confirme simplement."
    ),
    "upload.check_data": "Vérifie les infos :\n\nTitre : {title}\nArtiste : {artist}\nDurée : {duration}",
    "upload.moderation": (
        "⏳ « {artist} — {title} » a été ajouté à ta bibliothèque et envoyé en validation — "
        "il apparaîtra dans le catalogue commun une fois approuvé."
    ),
    "upload.done": "✅ « {artist} — {title} » a été ajouté au catalogue commun et à ta bibliothèque.",
    "premium.perks": (
        "🚫 <b>Sans publicité</b> — ni bannières ni coupures\n"
        "📥 <b>Mode hors ligne</b> — télécharge et écoute sans internet\n"
        "🔄 <b>Transfert groupé</b> — playlists entières depuis Spotify, Yandex, VK, SoundCloud\n"
        "🎼 <b>Sans limites</b> — autant de playlists et d'envois que tu veux\n"
        "🎛 <b>Égaliseur et minuteur</b> — 20 préréglages, endors-toi en musique\n"
        "📝 <b>Paroles</b> — ajoute-les et modifie-les\n"
        "🎁 <b>Jours offerts</b> — les succès et les amis rapportent du Premium"
    ),
    "premium.plan_year": "un an",
    "premium.plan_month": "un mois",
    "premium.plan_months": "{months} {months_word}",
    "premium.active": "💎 <b>Premium actif</b> jusqu'au {date}\n\nTu peux prolonger à l'avance — les jours s'additionnent.",
    "premium.offer": (
        "💎 <b>Infinity Music Premium</b>\n\n"
        "Seulement <b>{price} ₽ par mois</b> — moins cher qu'un café. "
        "Plus la formule est longue, plus le mois coûte peu.\n\nChoisis une durée :"
    ),
    "premium.invoice_title": "Premium pour {label}",
    "premium.invoice_description": "Sans publicité, playlists illimitées, limite d'envoi augmentée.",
    "premium.invoice_failed": "Impossible d'émettre la facture — réessaie plus tard",
    "premium.invoice_failed_card": "Impossible d'émettre la facture — réessaie plus tard ou paie en Stars",
    "premium.payment_failed": "Impossible de créer le paiement — réessaie plus tard",
    "premium.pay_intro": (
        "💳 Paiement de {price} ₽ — Premium pour {label}.\n\n"
        "Appuie sur le bouton, paie comme tu veux et reviens dans le bot — "
        "le Premium s'activera tout seul en moins d'une minute."
    ),
    "premium.pay_button": "Payer {price} ₽",
    "premium.card_unavailable": "Le paiement par carte n'est pas encore disponible",
    "premium.bad_payment": "Paiement invalide — recommence",
    "premium.activated": "✅ Premium actif jusqu'au {date} ! Merci pour le soutien 💛",
    "premium.plan_button": "💳 {label} — {price} ₽{suffix}",
    "premium.per_month": " · {per_month} ₽/mois",
    "premium.discount": " · −{discount} %",
    "premium.month_short": "mois",
    "premium.disable_ads": "💎 Couper la publicité (Premium)",
    "premium.continue": "Continuer à utiliser le bot",
    "ads.text": (
        "📢 Publicité\n\nVotre publicité pourrait être ici.\n\n"
        "Coupe la publicité et passe sans limites avec 💎 Premium."
    ),
    "referral.forever": "Infinity Premium",
    "referral.reward_days": "{days} {days_word} de Premium",
    "referral.rank": "{emoji} Rang : <b>{title}</b>",
    "referral.to_next_rank": "Jusqu'au rang {emoji} {title} — encore {count} {friends_word}",
    "referral.next_reward": "\n🔥 Encore {count} {friends_word} — et tu reçois {reward}\n",
    "referral.title": "🎁 <b>Programme de parrainage</b>",
    "referral.invited": "👥 Invités : <b>{count}</b>",
    "referral.your_link": "<b>Ton lien</b> (appuie pour copier) :",
    "referral.rewards": "<b>Récompenses</b>",
    "referral.share_text": (
        "Tiens, un bot qui trouve et télécharge n'importe quel morceau gratuitement — "
        "tu tapes le titre et il t'envoie la musique."
    ),
    "referral.invite_button": "📤 Inviter un ami",
    "referral.refresh": "🔄 Actualiser",
    "transfer.intro": (
        "📥 <b>Transférer ta musique depuis d'autres services</b>\n\n"
        "Envoie-moi :\n"
        "▪️ un lien vers une playlist publique <b>Spotify</b> ou <b>Yandex Music</b> ;\n"
        "▪️ un lien <b>SoundCloud</b> (profil, favoris, set) ;\n"
        "▪️ ou simplement une liste en texte, un morceau par ligne :\n"
        "<code>Kizaru — Fendi\nBig Baby Tape — Gimme the Loot</code>\n\n"
        "C'est comme ça que la musique arrive de VK ou d'ailleurs : copie la liste "
        "et envoie-la ici.\n\n"
        "On cherchera ces morceaux dans notre catalogue et on téléchargera ce qui manque."
    ),
    "transfer.button": "📥 Transférer",
    "transfer.cancelled": "Transfert annulé.",
    "transfer.soundcloud_hint": (
        "Les liens SoundCloud passent par l'assistant « Envoyer un morceau » — il "
        "télécharge l'audio directement, sans chercher de correspondance."
    ),
    "transfer.reading": "Je lis la liste…",
    "transfer.parse_failed": "Je n'ai pas pu lire la liste. Essaie de l'envoyer en texte.",
    "transfer.no_tracks": "Aucun morceau trouvé. Format de ligne : <code>Artiste — Titre</code>.",
    "transfer.more": "\n…et {count} de plus",
    "transfer.found": "Morceaux trouvés : <b>{count}</b>\n\n{preview}{tail}\n\nOn les met dans ta bibliothèque ?",
    "transfer.empty_list": "La liste est vide — recommence",
    "transfer.unavailable": "Le transfert est indisponible — les tâches de fond sont coupées.",
    "transfer.start_failed": "Impossible de lancer le transfert — réessaie plus tard.",
    "transfer.started": (
        "📥 Je transfère {count} morceaux. Ça prend du temps — je t'enverrai un rapport à la fin.\n\n"
        "Ce qui est déjà dans le catalogue arrive tout de suite dans ta bibliothèque."
    ),
    "contest.already": "Tu participes déjà — on attend les résultats 🍀",
    "contest.joined": "🎉 Tu es sur la liste ! Bonne chance pour le tirage",
    "contest.finished": "Le concours est terminé",
    "contest.requirements": "Il manque encore des conditions :",
    "contest.need_channel": "• abonne-toi à la chaîne",
    "contest.need_referrals": "• invite des amis : {referrals} sur {required}",
    "contest.subscribe": "📢 S'abonner à la chaîne",
    "contest.participating": "✅ Tu participes",
    "contest.join": "🎉 Participer",
    "contest.open_app": "🎧 Ouvrir Infinity Music",
    "inline.listen": "🎧 Écouter dans Infinity Music",
    "inline.instrumental": "🎼 Instrumental",
    "inline.open": "🎧 Ouvrir Infinity Music",
}
