"""Türkçe. Fiyatlar ₽ olarak kalır — ödemeler ruble üzerinden işlenir."""

MESSAGES: dict[str, str] = {
    "word.tracks.one": "parça",
    "word.tracks.many": "parça",
    "word.friends.one": "arkadaş",
    "word.friends.many": "arkadaş",
    "word.days.one": "gün",
    "word.days.many": "gün",
    "word.months.one": "ay",
    "word.months.many": "ay",
    "common.back": "◀️ Geri",
    "common.back_arrow": "⬅️ Geri",
    "common.back_to_menu": "◀️ Menüye",
    "common.back_menu_long": "◀️ Menüye dön",
    "common.cancel": "◀️ İptal",
    "common.page": "Sayfa {page} / {total_pages}",
    "common.updated": "Güncellendi",
    "common.no_changes": "Henüz yeni bir şey yok",
    "common.error": "⚠️ Bir şeyler ters gitti. İlgileniyoruz — bir dakika sonra tekrar dene.",
    "common.throttled": "⏳ Çok fazla istek. Birkaç saniye bekle.",
    "common.file_unavailable": "Dosya kullanılamıyor",
    "common.listen_all": "▶️ Hepsini çal",
    "common.listen": "▶️ Çal",
    "common.mix": "🎲 Mix",
    "common.artist_line": "Sanatçı: {artist}",
    "common.duration_line": "Süre: {duration}",
    "common.enter_title": "Bir başlık yaz",
    "common.miniapp_soon": "Mini App hâlâ geliştiriliyor.",
    "cabinet.greeting": "👋 Merhaba, <b>{name}</b> · ID: <code>{telegram_id}</code>",
    "cabinet.premium_until": "💎 {date} tarihine kadar Premium",
    "cabinet.free_plan": "Ücretsiz plan",
    "cabinet.library": "🎵 Kitaplığında: {count} {tracks_word}",
    "cabinet.hint": (
        "Bu sohbete bir şarkı adı ya da sanatçı yaz — parçayı anında bulurum."
    ),
    "cabinet.player_title": "🎧 <b>Oynatıcıyı aç</b>",
    "cabinet.player_pitch": (
        "VK ya da Apple Music gibi tam bir müzik servisi: mixler, çalma listeleri, "
        "şarkı sözleri, ekolayzer ve çevrimdışı mod."
    ),
    "cabinet.price": "💎 {price} ₽/ay • İlk gün ücretsiz",
    "menu.player": "🎧 Oynatıcıyı aç",
    "menu.upload": "⬆️ Parça yükle",
    "menu.premium": "💎 Oynatıcıyı aç — {price} ₽/ay",
    "menu.referral": "🎁 Davet programı",
    "menu.playlists": "🗂 Çalma listelerim",
    "menu.support": "🆘 Destek / şikâyet / fikir",
    "menu.language": "🌍 Язык · Language",
    "lang.title": "🌍 <b>Arayüz dili</b>\n\nBir dil seç — hatırlayacağız.",
    "lang.saved": "Dil kaydedildi",
    "lang.pending": "Bu dil henüz çevrilmedi — arayüz İngilizce kalacak.",
    "lang.back": "⬅️ Geri",
    "gate.text": (
        "🎵 Infinity Music'i kullanmak için kanallarımıza abone ol.\n\n"
        "Sonra «Aboneliği kontrol et»e dokun."
    ),
    "gate.check": "✅ Aboneliği kontrol et",
    "gate.not_subscribed": "Seni tüm kanallarda göremiyorum. Abone ol ve tekrar dene.",
    "gate.confirmed": "✅ Abonelik doğrulandı",
    "gate.subscribe_first": "Önce kanallara abone ol",
    "moved.text": (
        "🎧 <b>Taşındık</b>\n\n"
        "Bu bot artık çalışmıyor. Tüm müzik, kitaplığın ve çalma listelerin "
        "yeni botta seni bekliyor — @{username}.\n\n"
        "Aç ve «Başlat»a dokun."
    ),
    "moved.button": "🎧 Yeni bota geç",
    "library.empty": (
        "🎵 Kitaplık\n\nParça: 0\n\n"
        "Kitaplığın boş — arama ya da yükleme ile parça ekle."
    ),
    "library.title": "🎵 Kitaplık\n\nParça: {count}",
    "library.search_button": "🔍 Kitaplığımda ara",
    "library.nothing_found": "Kitaplığında bir şey bulunamadı.",
    "library.found": "Kitaplıkta bulundu: {count}",
    "playlists.title": "📂 Çalma listeleri\n\nToplam: {total}",
    "playlists.empty_hint": "\n\nHenüz çalma listen yok — ilkini oluştur.",
    "playlists.view": "Ad:\n{title}\n\nParça sayısı:\n{total}",
    "playlists.view_empty_hint": "\n\nBu çalma listesi boş — parça kartından ekleyebilirsin.",
    "playlists.enter_title": "Çalma listesinin adını yaz",
    "playlists.title_length": "Ad 1 ile {limit} karakter arasında olmalı. Tekrar dene.",
    "playlists.free_limit": (
        "Ücretsiz planda {limit} çalma listesi hakkın var.\n"
        "💎 Premium sınırı kaldırır — menüdeki «Premium satın al»a bak."
    ),
    "playlists.created": "✅ «{title}» çalma listesi oluşturuldu.",
    "playlists.not_found": "Çalma listesi bulunamadı",
    "playlists.delete_confirm": (
        "«{title}» çalma listesi silinsin mi?\n\nParçalar katalogda ve kitaplığında kalır."
    ),
    "playlists.deleted": "Çalma listesi silindi",
    "playlists.create_button": "➕ Yeni çalma listesi",
    "playlists.delete_button": "🗑 Çalma listesini sil",
    "playlists.delete_yes": "🗑 Evet, sil",
    "search.nothing": "«{query}» için bir şey bulunamadı.",
    "search.results": "🔍 «{query}» sonuçları\n\nBulunan: {total}",
    "search.enter_track": "Parça adını yaz",
    "search.searching_web": "🔎 İnternette arıyorum — parça birazdan gelecek.",
    "search.instrumental_not_found": "Enstrümantal bulunamadı",
    "search.instrumental_card": "🎼 {title} (Enstrümantal)",
    "quick.nothing": (
        "Hiçbir şey bulamadım. Başka türlü dene — mesela «Kizaru Fake ID»: "
        "sanatçı ve parça adı birlikte en isabetli sonucu verir."
    ),
    "quick.stale": "Bu liste eskidi — yeniden ara.",
    "quick.results_title": "🎵 «{query}» için parçalar",
    "quick.searching": "🔎 Arıyorum…",
    "quick.sending": "Gönderiliyor…",
    "quick.busy": "İndirme servisi meşgul, bir dakika sonra dene",
    "quick.downloading": "Parçayı indiriyorum — buraya gelecek",
    "quick.already_fetching": "Bu parça zaten indiriliyor — birkaç saniye içinde gelecek",
    "quality.note_high": "🎚 Mevcut en iyi kalite · {format} · {size} MB",
    "quality.note_lossless": "🎚 Sanatçının orijinali · {format} · {size} MB",
    "quick.preparing_best": "En iyi kalitede hazırlıyorum — buraya gelecek",
    "menu.settings": "⚙️ Ayarlar",
    "settings.title": "<b>⚙️ Ayarlar</b>",
    "settings.quality_hint": "Parçaların geleceği kalite.\n\n<b>Normal</b> — mp3 128 kbps, bugün herkesin aldığı.\n<b>En iyi</b> — kaynağın verdiği azami: 160 kbps ve bazı parçalarda sanatçının orijinal dosyası (WAV ya da FLAC). Birkaç saniye uzun sürer ve daha çok yer kaplar.",
    "settings.quality_mp3": "🎵 Normal · mp3 128",
    "settings.quality_best": "🎚 En iyi kalite (Premium)",
    "settings.quality_premium_only": "En iyi kalite Premium aboneliğe dahildir.",
    "settings.quality_saved_mp3": "Tamam: parçalar eskisi gibi gelecek",
    "settings.quality_saved_best": "Tamam. Parçalar artık kaynağın verdiği en iyi hâlde gelecek: sanatçının orijinali varsa o, yoksa 128 yerine 160 kbps. İkisi de yoksa her zamanki dosya gelir — hata da yok, bekleme de.",
    "settings.back": "◀️ Geri",
    "settings.cover_hint": "<b>Kapak</b> zaten dosyanın içinde ve oynatıcıda görünüyor. Müziği kendi kitaplığınızda topluyorsanız ayrı görsel işinize yarar.",
    "settings.cover_on": "🖼 Ayrı kapak — açık",
    "settings.cover_off": "🖼 Ayrı kapak — kapalı",
    "card.title": "🎧 {title}",
    "card.not_found": "Parça bulunamadı",
    "card.added": "Kitaplığına eklendi",
    "card.already": "Zaten kitaplığında",
    "card.removed": "Kitaplığından çıkarıldı",
    "card.no_playlists": "Henüz çalma listen yok — 📂 Çalma listeleri bölümünden oluştur",
    "card.added_to_playlist": "«{title}» listesine eklendi",
    "card.already_in_playlist": "Parça zaten bu listede",
    "card.removed_from_playlist": "Çalma listesinden çıkarıldı",
    "card.share_text": "«{artist} — {title}» parçasını paylaş:",
    "card.add_library": "➕ Kitaplığa ekle",
    "card.remove_library": "🗑 Kitaplıktan çıkar",
    "card.add_playlist": "📂 Çalma listesine ekle",
    "card.remove_playlist": "🗑 Çalma listesinden çıkar",
    "card.download": "⬇️ İndir",
    "card.share": "📤 Paylaş",
    "card.edit_admin": "✏️ Düzenle (yönetici)",
    "player.next": "▶️ Sonraki",
    "player.stop": "⏹ Durdur",
    "player.library_empty_add": "Kitaplığın boş — parça ekle",
    "player.mix_started": "🎶 Mix başladı",
    "player.mix_continue": "🎲 Mix'e devam et",
    "player.library_empty": "Kitaplığın boş",
    "player.queue_finished": "✅ Sıra bitti",
    "player.playing_library": "▶️ Kitaplığını çalıyorum",
    "player.playlist_empty": "Çalma listesi boş",
    "player.playlist_finished": "✅ Çalma listesi bitti",
    "player.playing_playlist": "▶️ «{title}» çalıyor",
    "player.results_stale": "Bu sonuçlar eskidi — yeniden ara",
    "player.nothing_found": "Bir şey bulunamadı",
    "player.results_finished": "✅ Sonuçlar bitti",
    "player.playing_results": "▶️ Arama sonuçlarını çalıyorum",
    "player.queue_stopped": "⏹ Sıra durduruldu",
    "upload.intro": "⬆️ <b>Müzik yükleme</b>\n\n📎 <b>Ses dosyası olarak</b> — parçayı dosya olarak gönderin. İstediğiniz kadar, tüm koleksiyonunuzu tek tek — <b>ücretsiz ve sınırsız</b>.\n\n🔗 <b>Bağlantıyla</b> — YouTube Music, SoundCloud ve diğer platformlardan: <b>💎 Premium</b> gerekir.\n\n⚠️ Sanatçıyı yazın — yoksa parça «Bilinmeyen» olur.\n\nDosya ya da bağlantı bekliyorum 👇",
    "upload.confirm_button": "✅ Yükle",
    "upload.enter_title": "Başlığı yaz.",
    "upload.as_audio": "Dosyayı ses (müzik) olarak gönder, belge olarak değil.",
    "upload.premium_bulk": "Bağlantıyla yükleme yalnızca 💎 Premium içindir.\nSes dosyaları ücretsiz ve sınırsız — parçayı dosya olarak gönderin.",
    "upload.reading_link": "🔍 Bağlantıyı okuyorum…",
    "upload.link_failed": "Bu bağlantı açılamadı. Kontrol edip tekrar deneyin.",
    "upload.queued_link": "⏳ Alındı! Parçayı indirip buraya göndereceğiz — genelde bir dakikadan az.",
    "upload.drm_service": "🔒 <b>{service}</b> yalnızca korumalı akış veriyor — dosyanın kendisi orada yok.\n\nAma parça listesi okunuyor: «Aktarım» aynı şarkıları erişilebilir kaynaklarda bulup kitaplığınıza ekler.",
    "upload.go_transfer": "🔄 Çalma listesini aktar",
    "upload.reading_playlist": "🔍 Çalma listesini okuyorum…",
    "upload.playlist_failed": "Bu çalma listesini okuyamadım. Bağlantıyı kontrol edip tekrar dene.",
    "upload.unavailable": "İçe aktarma şu anda kullanılamıyor — sonra dene.",
    "upload.queued_videos": (
        "⏳ {queued} video alındı.\n\n"
        "Müzik işlendikçe kitaplığında görünecek — her parça için mesaj gelmez."
    ),
    "upload.reading_soundcloud": "🔍 SoundCloud sayfasını okuyorum…",
    "upload.soundcloud_failed": "Bu SoundCloud sayfasını okuyamadım. Bağlantıyı kontrol edip tekrar dene.",
    "upload.queued_soundcloud": (
        "⏳ SoundCloud'dan {queued} parça alındı.\n\n"
        "İşlendikçe kitaplığında görünecekler — her parça için mesaj gelmez."
    ),
    "upload.queued_one_soundcloud": "⏳ Alındı! Parçayı SoundCloud'dan indirip buraya göndereceğiz — genelde bir dakikadan kısa sürer.",
    "upload.waiting_file": "Ses dosyası ya da parça bağlantısı bekliyorum — YouTube Music veya SoundCloud 🎵",
    "upload.checking_link": "🔍 Bağlantıyı kontrol ediyorum…",
    "upload.video_failed": "Bu videoyu açamadım. Bağlantıyı kontrol edip tekrar dene.",
    "upload.live_stream": "Bu canlı yayın — onları almıyoruz.",
    "upload.queued_video": (
        "⏳ Alındı: «{title}» ({duration}).\n"
        "İndirip parçayı buraya göndereceğiz — genelde bir dakikadan kısa sürer."
    ),
    "upload.title_length": "Başlık 1 ile 256 karakter arasında olmalı. Tekrar dene.",
    "upload.enter_artist": "Sanatçıyı yaz.",
    "upload.artist_length": "Sanatçı adı 1 ile 256 karakter arasında olmalı. Tekrar dene.",
    "upload.duplicate_warning": (
        "\n\n⚠️ «{artist} — {title}» katalogda zaten var.\n"
        "Bu farklı bir parçaysa geri dön ve başlığı değiştir "
        "(mesela «(Rex)» ekle). Değilse onayla."
    ),
    "upload.check_data": "Bilgileri kontrol et:\n\nBaşlık: {title}\nSanatçı: {artist}\nSüre: {duration}",
    "upload.moderation": (
        "⏳ «{artist} — {title}» kitaplığına eklendi ve incelemeye gönderildi — "
        "onaylanınca ortak katalogda görünecek."
    ),
    "upload.done": "✅ «{artist} — {title}» ortak kataloga ve kitaplığına eklendi.",
    "premium.perks": (
        "🚫 <b>Reklamsız</b> — ne banner ne kesinti\n"
        "📥 <b>Çevrimdışı mod</b> — parçaları indir, internetsiz dinle\n"
        "🔄 <b>Toplu aktarım</b> — Spotify, Yandex, VK, SoundCloud'dan tüm listeler\n"
        "🎼 <b>Sınırsız</b> — istediğin kadar çalma listesi ve yükleme\n"
        "🎛 <b>Ekolayzer ve uyku zamanlayıcı</b> — 20 hazır ayar, müzikle uyu\n"
        "📝 <b>Şarkı sözleri</b> — ekle ve düzenle\n"
        "🎁 <b>Hediye günler</b> — başarımlar ve arkadaşlar daha fazla Premium getirir"
    ),
    "premium.plan_year": "bir yıl",
    "premium.plan_month": "bir ay",
    "premium.plan_months": "{months} {months_word}",
    "premium.active": "💎 <b>Premium etkin</b> — {date} tarihine kadar\n\nErkenden uzatabilirsin — günler toplanır.",
    "premium.offer": (
        "💎 <b>Infinity Music Premium</b>\n\n"
        "Ayda sadece <b>{price} ₽</b> — bir kahveden ucuz. "
        "Plan uzadıkça aylık fiyat düşer.\n\nSüreyi seç:"
    ),
    "premium.invoice_title": "{label} için Premium",
    "premium.invoice_description": "Reklamsız, sınırsız çalma listesi, daha yüksek yükleme limiti.",
    "premium.invoice_failed": "Fatura oluşturulamadı — sonra dene",
    "premium.invoice_failed_card": "Fatura oluşturulamadı — sonra dene ya da Stars ile öde",
    "premium.payment_failed": "Ödeme oluşturulamadı — sonra dene",
    "premium.pay_intro": (
        "💳 {price} ₽ ödeme — {label} için Premium.\n\n"
        "Düğmeye dokun, dilediğin yöntemle öde ve bota dön — "
        "Premium bir dakika içinde kendiliğinden açılır."
    ),
    "premium.pay_button": "{price} ₽ öde",
    "premium.card_unavailable": "Kartla ödeme henüz kullanılamıyor",
    "premium.bad_payment": "Geçersiz ödeme — baştan dene",
    "premium.activated": "✅ Premium {date} tarihine kadar etkin! Desteğin için teşekkürler 💛",
    "premium.plan_button": "{label} — {price} ₽{suffix}",
    "premium.method_title": "<b>{label} için Premium</b>\n\nNasıl ödemek istersiniz?\n\n⭐ <b>{stars} Stars</b> — doğrudan Telegram içinde, kartsız\n💳 <b>{price} ₽</b> — kart veya SBP",
    "premium.pay_stars": "⭐ {stars} Stars öde",
    "premium.pay_rub": "💳 {price} ₽ öde",
    "premium.per_month": " · {per_month} ₽/ay",
    "premium.discount": " · −%{discount}",
    "premium.month_short": "ay",
    "premium.disable_ads": "💎 Reklamları kapat (Premium)",
    "premium.continue": "Kullanmaya devam et",
    "ads.text": (
        "📢 Reklam\n\nBurada senin reklamın olabilirdi.\n\n"
        "Reklamları kapat, 💎 Premium ile sınırsıza geç."
    ),
    "referral.forever": "Infinity Premium",
    "referral.reward_days": "{days} {days_word} Premium",
    "referral.rank": "{emoji} Seviye: <b>{title}</b>",
    "referral.to_next_rank": "{emoji} {title} seviyesine — {count} {friends_word} kaldı",
    "referral.next_reward": "\n🔥 {count} {friends_word} daha — ve {reward} kazanıyorsun\n",
    "referral.title": "🎁 <b>Davet programı</b>",
    "referral.invited": "👥 Davet edilen: <b>{count}</b>",
    "referral.your_link": "<b>Bağlantın</b> (kopyalamak için dokun):",
    "referral.rewards": "<b>Ödüller</b>",
    "referral.share_text": (
        "Şu bota bak: her parçayı ücretsiz bulup indiriyor — "
        "sadece adını yazıyorsun, müziği gönderiyor."
    ),
    "referral.invite_button": "📤 Arkadaş davet et",
    "referral.refresh": "🔄 Yenile",
    "transfer.intro": (
        "📥 <b>Müziğini başka servislerden taşı</b>\n\n"
        "Bana şunu gönder:\n"
        "▪️ herkese açık bir <b>Spotify</b> veya <b>Yandex Music</b> listesi bağlantısı;\n"
        "▪️ bir <b>SoundCloud</b> bağlantısı (profil, beğeniler, set);\n"
        "▪️ ya da düz metin liste, her satırda bir parça:\n"
        "<code>Kizaru — Fendi\nBig Baby Tape — Gimme the Loot</code>\n\n"
        "Müzik VK'dan ve başka her yerden böyle taşınır: listeyi kopyala "
        "ve buraya gönder.\n\n"
        "Bu parçaları katalogumuzda arayacağız, olmayanları indireceğiz."
    ),
    "transfer.button": "📥 Taşı",
    "transfer.cancelled": "Taşıma iptal edildi.",
    "transfer.soundcloud_hint": (
        "SoundCloud bağlantıları «Parça yükle» sihirbazına gider — sesi eşleşme "
        "aramadan doğrudan indirir."
    ),
    "transfer.reading": "Listeyi okuyorum…",
    "transfer.parse_failed": "Listeyi okuyamadım. Düz metin olarak göndermeyi dene.",
    "transfer.no_tracks": "Parça bulamadım. Satır biçimi: <code>Sanatçı — Başlık</code>.",
    "transfer.more": "\n…ve {count} tane daha",
    "transfer.found": "Bulunan parçalar: <b>{count}</b>\n\n{preview}{tail}\n\nKitaplığına aktaralım mı?",
    "transfer.empty_list": "Liste boş — baştan başla",
    "transfer.unavailable": "Taşıma şu an kullanılamıyor — arka plan görevleri kapalı.",
    "transfer.start_failed": "Taşıma başlatılamadı — sonra dene.",
    "transfer.started": (
        "📥 {count} parça taşınıyor. Biraz sürecek — bitince rapor göndereceğim.\n\n"
        "Katalogda zaten olanlar kitaplığında hemen görünür."
    ),
    "contest.already": "Zaten katılıyorsun — sonuçları bekliyoruz 🍀",
    "contest.joined": "🎉 Listedesin! Çekilişte bol şans",
    "contest.finished": "Yarışma sona erdi",
    "contest.requirements": "Koşullar henüz tamamlanmadı:",
    "contest.need_channel": "• kanala abone ol",
    "contest.need_referrals": "• arkadaş davet et: {required} kişiden {referrals}",
    "contest.subscribe": "📢 Kanala abone ol",
    "contest.participating": "✅ Katılıyorsun",
    "contest.join": "🎉 Katıl",
    "contest.open_app": "🎧 Infinity Music'i aç",
    "inline.listen": "🎧 Infinity Music'te dinle",
    "inline.instrumental": "🎼 Enstrümantal",
    "inline.open": "🎧 Infinity Music'i aç",
}
