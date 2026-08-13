"""English. Prices stay in ₽ — payments are processed in roubles."""

MESSAGES: dict[str, str] = {
    "word.tracks.one": "track",
    "word.tracks.many": "tracks",
    "word.friends.one": "friend",
    "word.friends.many": "friends",
    "word.days.one": "day",
    "word.days.many": "days",
    "word.months.one": "month",
    "word.months.many": "months",
    "common.back": "◀️ Back",
    "common.back_arrow": "⬅️ Back",
    "common.back_to_menu": "◀️ Menu",
    "common.back_menu_long": "◀️ Back to menu",
    "common.cancel": "◀️ Cancel",
    "common.page": "Page {page} / {total_pages}",
    "common.updated": "Updated",
    "common.no_changes": "Nothing new yet",
    "common.error": "⚠️ Something went wrong. We're on it — try again in a minute.",
    "common.throttled": "⏳ Too many requests. Give it a couple of seconds.",
    "common.file_unavailable": "File unavailable",
    "common.listen_all": "▶️ Play all",
    "common.listen": "▶️ Play",
    "common.mix": "🎲 Mix",
    "common.artist_line": "Artist: {artist}",
    "common.duration_line": "Length: {duration}",
    "common.enter_title": "Type a title",
    "common.miniapp_soon": "The Mini App is still in development.",
    "cabinet.greeting": "👋 Hi, <b>{name}</b> · ID: <code>{telegram_id}</code>",
    "cabinet.premium_until": "💎 Premium until {date}",
    "cabinet.free_plan": "Free plan",
    "cabinet.library": "🎵 In your library: {count} {tracks_word}",
    "cabinet.hint": (
        "Just send a song title or an artist to this chat — I'll find the track right away."
    ),
    "cabinet.player_title": "🎧 <b>Open the player</b>",
    "cabinet.player_pitch": (
        "A full music service like VK or Apple Music: mixes, playlists, "
        "lyrics, an equalizer and offline mode."
    ),
    "cabinet.price": "💎 {price} ₽/month • First day free",
    "menu.player": "🎧 Open the player",
    "menu.upload": "⬆️ Upload a track",
    "menu.premium": "💎 Open the player — {price} ₽/mo",
    "menu.referral": "🎁 Referral program",
    "menu.support": "🆘 Support / reports / ideas",
    "menu.language": "🌍 Язык · Language",
    "lang.title": "🌍 <b>Interface language</b>\n\nPick a language — we'll remember it.",
    "lang.saved": "Language saved",
    "lang.pending": "This language isn't translated yet — the interface stays in English.",
    "lang.back": "⬅️ Back",
    "gate.text": (
        "🎵 To use Infinity Music, please subscribe to our channels.\n\n"
        "Once subscribed, tap «Check subscription»."
    ),
    "gate.check": "✅ Check subscription",
    "gate.not_subscribed": "I don't see you in all the channels. Subscribe and try again.",
    "gate.confirmed": "✅ Subscription confirmed",
    "gate.subscribe_first": "Please subscribe to the channels first",
    "moved.text": (
        "🎧 <b>We've moved</b>\n\n"
        "This bot is no longer active. All the music, your library and playlists "
        "are waiting in the new bot — @{username}.\n\n"
        "Just open it and tap «Start»."
    ),
    "moved.button": "🎧 Open the new bot",
    "library.empty": (
        "🎵 Library\n\nTracks: 0\n\nYour library is empty — add tracks via search or upload."
    ),
    "library.title": "🎵 Library\n\nTracks: {count}",
    "library.search_button": "🔍 Search my library",
    "library.nothing_found": "Nothing found in your library.",
    "library.found": "Found in your library: {count}",
    "playlists.title": "📂 Playlists\n\nTotal: {total}",
    "playlists.empty_hint": "\n\nNo playlists yet — create your first one.",
    "playlists.view": "Title:\n{title}\n\nTracks:\n{total}",
    "playlists.view_empty_hint": "\n\nThis playlist is empty — add tracks from a track card.",
    "playlists.enter_title": "Type the playlist title",
    "playlists.title_length": "The title must be 1 to {limit} characters. Try again.",
    "playlists.free_limit": (
        "The free plan allows {limit} playlists.\n"
        "💎 Premium removes the limit — see «Buy Premium» in the menu."
    ),
    "playlists.created": "✅ Playlist «{title}» created.",
    "playlists.not_found": "Playlist not found",
    "playlists.delete_confirm": (
        "Delete playlist «{title}»?\n\nThe tracks stay in the catalogue and your library."
    ),
    "playlists.deleted": "Playlist deleted",
    "playlists.create_button": "➕ New playlist",
    "playlists.delete_button": "🗑 Delete playlist",
    "playlists.delete_yes": "🗑 Yes, delete",
    "search.nothing": "Nothing found for «{query}».",
    "search.results": "🔍 Results for «{query}»\n\nFound: {total}",
    "search.enter_track": "Type a track title",
    "search.searching_web": "🔎 Searching the web — the track will arrive shortly.",
    "search.instrumental_not_found": "Instrumental not found",
    "search.instrumental_card": "🎼 {title} (Instrumental)",
    "quick.nothing": (
        "Found nothing. Try it differently — «Kizaru Fake ID», for example: "
        "artist and title together give the best match."
    ),
    "quick.stale": "This list is out of date — search again.",
    "quick.results_title": "🎵 Tracks for «{query}»",
    "quick.searching": "🔎 Searching…",
    "quick.sending": "Sending…",
    "quick.busy": "The download service is busy, try again in a minute",
    "quick.downloading": "Downloading the track — it'll arrive here",
    "quick.already_fetching": "Already downloading this track — it arrives in a few seconds",
    "original.caption": "🎚 Original quality: {format}, {size} MB",
    "menu.settings": "⚙️ Settings",
    "settings.title": "<b>⚙️ Settings</b>",
    "settings.quality_hint": "The format your tracks arrive in.\n\n<b>MP3</b> — fast, small, plays right in the Telegram player.\n<b>Original</b> — the file the author uploaded, often WAV or FLAC. It arrives as a separate file in a second message, weighs tens of megabytes and is not available for every track: where the author disabled downloads, you get the usual mp3.",
    "settings.quality_mp3": "🎵 MP3",
    "settings.quality_original": "🎚 Original (Premium)",
    "settings.quality_premium_only": "Original quality comes with a Premium subscription.",
    "settings.quality_saved_mp3": "Done: tracks arrive as mp3",
    "settings.quality_saved_original": "Done. The original arrives in a second message wherever the author allowed downloads. Where they didn't, you keep the usual mp3.",
    "settings.back": "◀️ Back",
    "card.title": "🎧 {title}",
    "card.not_found": "Track not found",
    "card.added": "Added to your library",
    "card.already": "Already in your library",
    "card.removed": "Removed from your library",
    "card.no_playlists": "You have no playlists yet — create one in 📂 Playlists",
    "card.added_to_playlist": "Added to «{title}»",
    "card.already_in_playlist": "The track is already in this playlist",
    "card.removed_from_playlist": "Removed from the playlist",
    "card.share_text": "Share the track «{artist} — {title}»:",
    "card.add_library": "➕ Add to library",
    "card.remove_library": "🗑 Remove from library",
    "card.add_playlist": "📂 Add to playlist",
    "card.remove_playlist": "🗑 Remove from playlist",
    "card.download": "⬇️ Download",
    "card.share": "📤 Share",
    "card.edit_admin": "✏️ Edit (admin)",
    "player.next": "▶️ Next",
    "player.stop": "⏹ Stop",
    "player.library_empty_add": "Your library is empty — add some tracks",
    "player.mix_started": "🎶 Mix started",
    "player.mix_continue": "🎲 Continue the mix",
    "player.library_empty": "Your library is empty",
    "player.queue_finished": "✅ The queue is done",
    "player.playing_library": "▶️ Playing your library",
    "player.playlist_empty": "The playlist is empty",
    "player.playlist_finished": "✅ Playlist finished",
    "player.playing_playlist": "▶️ Playing «{title}»",
    "player.results_stale": "These results are out of date — search again",
    "player.nothing_found": "Nothing found",
    "player.results_finished": "✅ Results finished",
    "player.playing_results": "▶️ Playing the search results",
    "player.queue_stopped": "⏹ Queue stopped",
    "upload.intro": (
        "⬆️ <b>Upload music</b>\n\n"
        "📎 <b>As a file</b> — send the track as an audio file. As many as you like, "
        "your whole collection one by one — <b>free and unlimited</b>.\n\n"
        "🔗 <b>By link</b> — YouTube Music or SoundCloud:\n"
        "• a single track — <b>free</b>;\n"
        "• a whole profile, playlist or likes in bulk — <b>💎 Premium</b>.\n\n"
        "⚠️ Do name the artist — otherwise the track becomes «Unknown».\n\n"
        "Send a file or a link 👇"
    ),
    "upload.confirm_button": "✅ Upload",
    "upload.enter_title": "Type the title.",
    "upload.as_audio": "Send the file as audio (music), not as a document.",
    "upload.premium_bulk": (
        "Uploading a whole profile, playlist or likes is 💎 Premium only.\n"
        "For free you can upload one track at a time — send a link to a single track."
    ),
    "upload.reading_playlist": "🔍 Reading the playlist…",
    "upload.playlist_failed": "Couldn't read that playlist. Check the link and try again.",
    "upload.unavailable": "Importing is unavailable right now — try later.",
    "upload.queued_videos": (
        "⏳ Accepted {queued} videos.\n\n"
        "The music will appear in your library as it's processed — no message per track."
    ),
    "upload.reading_soundcloud": "🔍 Reading the SoundCloud page…",
    "upload.soundcloud_failed": "Couldn't read that SoundCloud page. Check the link and try again.",
    "upload.queued_soundcloud": (
        "⏳ Accepted {queued} tracks from SoundCloud.\n\n"
        "They'll appear in your library as they're processed — no message per track."
    ),
    "upload.queued_one_soundcloud": "⏳ Got it! We'll grab the track from SoundCloud and send it here — usually under a minute.",
    "upload.waiting_file": "Waiting for an audio file or a track link — YouTube Music or SoundCloud 🎵",
    "upload.checking_link": "🔍 Checking the link…",
    "upload.video_failed": "Couldn't open that video. Check the link and try again.",
    "upload.live_stream": "That's a live stream — we don't take those.",
    "upload.queued_video": (
        "⏳ Accepted: «{title}» ({duration}).\n"
        "We'll download it and send the track here — usually under a minute."
    ),
    "upload.title_length": "The title must be 1 to 256 characters. Try again.",
    "upload.enter_artist": "Type the artist.",
    "upload.artist_length": "The artist name must be 1 to 256 characters. Try again.",
    "upload.duplicate_warning": (
        "\n\n⚠️ «{artist} — {title}» is already in the catalogue.\n"
        "If this is a different track, go back and change the title "
        "(add «(Rex)», for example). Otherwise just confirm."
    ),
    "upload.check_data": "Check the details:\n\nTitle: {title}\nArtist: {artist}\nLength: {duration}",
    "upload.moderation": (
        "⏳ «{artist} — {title}» was added to your library and sent for review — "
        "it will appear in the shared catalogue once approved."
    ),
    "upload.done": "✅ «{artist} — {title}» was added to the shared catalogue and your library.",
    "premium.perks": (
        "🚫 <b>No ads</b> — no banners, no interruptions\n"
        "📥 <b>Offline mode</b> — download tracks, listen without internet\n"
        "🔄 <b>Bulk transfer</b> — whole playlists from Spotify, Yandex, VK, SoundCloud\n"
        "🎼 <b>No limits</b> — as many playlists and uploads as you want\n"
        "🎛 <b>Equalizer and sleep timer</b> — 20 presets, fall asleep to music\n"
        "📝 <b>Lyrics</b> — add and edit them\n"
        "🎁 <b>Bonus days</b> — achievements and friends bring more Premium"
    ),
    "premium.plan_year": "a year",
    "premium.plan_month": "a month",
    "premium.plan_months": "{months} {months_word}",
    "premium.active": "💎 <b>Premium is active</b> until {date}\n\nYou can extend early — the days add up.",
    "premium.offer": (
        "💎 <b>Infinity Music Premium</b>\n\n"
        "Just <b>{price} ₽ a month</b> — cheaper than a coffee. "
        "The longer the plan, the lower the monthly price.\n\nPick a plan:"
    ),
    "premium.invoice_title": "Premium for {label}",
    "premium.invoice_description": "No ads, unlimited playlists, a higher upload limit.",
    "premium.invoice_failed": "Couldn't issue the invoice — try later",
    "premium.invoice_failed_card": "Couldn't issue the invoice — try later or pay with Stars",
    "premium.payment_failed": "Couldn't create the payment — try later",
    "premium.pay_intro": (
        "💳 Paying {price} ₽ — Premium for {label}.\n\n"
        "Tap the button, pay any way you like and come back to the bot — "
        "Premium switches on automatically within a minute."
    ),
    "premium.pay_button": "Pay {price} ₽",
    "premium.card_unavailable": "Card payments aren't available yet",
    "premium.bad_payment": "Invalid payment — please start over",
    "premium.activated": "✅ Premium is active until {date}! Thank you for the support 💛",
    "premium.plan_button": "💳 {label} — {price} ₽{suffix}",
    "premium.per_month": " · {per_month} ₽/mo",
    "premium.discount": " · −{discount}%",
    "premium.month_short": "mo",
    "premium.disable_ads": "💎 Turn off ads (Premium)",
    "premium.continue": "Keep using the bot",
    "ads.text": (
        "📢 Advertisement\n\nYour ad could be here.\n\n"
        "Turn ads off and go unlimited with 💎 Premium."
    ),
    "referral.forever": "Infinity Premium",
    "referral.reward_days": "{days} {days_word} of Premium",
    "referral.rank": "{emoji} Rank: <b>{title}</b>",
    "referral.to_next_rank": "To rank {emoji} {title} — {count} more {friends_word}",
    "referral.next_reward": "\n🔥 {count} more {friends_word} — and you get {reward}\n",
    "referral.title": "🎁 <b>Referral program</b>",
    "referral.invited": "👥 Invited: <b>{count}</b>",
    "referral.your_link": "<b>Your link</b> (tap to copy):",
    "referral.rewards": "<b>Rewards</b>",
    "referral.share_text": (
        "Here's a bot where you can find and download any track for free — "
        "you just type the title and it sends you the music."
    ),
    "referral.invite_button": "📤 Invite a friend",
    "referral.refresh": "🔄 Refresh",
    "transfer.intro": (
        "📥 <b>Move your music from other services</b>\n\n"
        "Send me:\n"
        "▪️ a link to a public <b>Spotify</b> or <b>Yandex Music</b> playlist;\n"
        "▪️ a <b>SoundCloud</b> link (profile, likes, set);\n"
        "▪️ or simply a plain text list, one track per line:\n"
        "<code>Kizaru — Fendi\nBig Baby Tape — Gimme the Loot</code>\n\n"
        "That's how music moves over from VK and anywhere else: copy the list "
        "and send it here.\n\n"
        "We'll find these tracks in our catalogue and download whatever is missing."
    ),
    "transfer.button": "📥 Transfer",
    "transfer.cancelled": "Transfer cancelled.",
    "transfer.soundcloud_hint": (
        "SoundCloud links go to the «Upload a track» wizard — it downloads the "
        "audio directly, without matching titles."
    ),
    "transfer.reading": "Reading the list…",
    "transfer.parse_failed": "Couldn't read the list. Try sending it as plain text.",
    "transfer.no_tracks": "No tracks found. Line format: <code>Artist — Title</code>.",
    "transfer.more": "\n…and {count} more",
    "transfer.found": "Tracks found: <b>{count}</b>\n\n{preview}{tail}\n\nMove them to your library?",
    "transfer.empty_list": "The list is empty — start over",
    "transfer.unavailable": "Transfers are temporarily unavailable — background jobs are off.",
    "transfer.start_failed": "Couldn't start the transfer — try later.",
    "transfer.started": (
        "📥 Moving {count} tracks. This takes a while — I'll send a report when it's done.\n\n"
        "Whatever is already in the catalogue appears in your library right away."
    ),
    "contest.already": "You're already in — waiting for the results 🍀",
    "contest.joined": "🎉 You're on the list! Good luck in the draw",
    "contest.finished": "The contest is over",
    "contest.requirements": "Requirements not met yet:",
    "contest.need_channel": "• subscribe to the channel",
    "contest.need_referrals": "• invite friends: {referrals} of {required}",
    "contest.subscribe": "📢 Subscribe to the channel",
    "contest.participating": "✅ You're participating",
    "contest.join": "🎉 Take part",
    "contest.open_app": "🎧 Open Infinity Music",
    "inline.listen": "🎧 Listen in Infinity Music",
    "inline.instrumental": "🎼 Instrumental",
    "inline.open": "🎧 Open Infinity Music",
}
