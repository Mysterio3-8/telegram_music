"""Português. Os preços ficam em ₽ — os pagamentos são processados em rublos."""

MESSAGES: dict[str, str] = {
    "word.tracks.one": "faixa",
    "word.tracks.many": "faixas",
    "word.friends.one": "amigo",
    "word.friends.many": "amigos",
    "word.days.one": "dia",
    "word.days.many": "dias",
    "word.months.one": "mês",
    "word.months.many": "meses",
    "common.back": "◀️ Voltar",
    "common.back_arrow": "⬅️ Voltar",
    "common.back_to_menu": "◀️ Menu",
    "common.back_menu_long": "◀️ Voltar ao menu",
    "common.cancel": "◀️ Cancelar",
    "common.page": "Página {page} / {total_pages}",
    "common.updated": "Atualizado",
    "common.no_changes": "Ainda sem novidades",
    "common.error": "⚠️ Algo deu errado. Já estamos a ver — tenta de novo daqui a um minuto.",
    "common.throttled": "⏳ Pedidos a mais. Espera uns segundos.",
    "common.file_unavailable": "Ficheiro indisponível",
    "common.listen_all": "▶️ Tocar tudo",
    "common.listen": "▶️ Tocar",
    "common.mix": "🎲 Mix",
    "common.artist_line": "Artista: {artist}",
    "common.duration_line": "Duração: {duration}",
    "common.enter_title": "Escreve um título",
    "common.miniapp_soon": "O Mini App ainda está em desenvolvimento.",
    "cabinet.greeting": "👋 Olá, <b>{name}</b> · ID: <code>{telegram_id}</code>",
    "cabinet.premium_until": "💎 Premium até {date}",
    "cabinet.free_plan": "Plano grátis",
    "cabinet.library": "🎵 Na tua biblioteca: {count} {tracks_word}",
    "cabinet.hint": (
        "Envia o título de uma música ou um artista para este chat — "
        "encontro a faixa num instante."
    ),
    "cabinet.player_title": "🎧 <b>Abrir o leitor</b>",
    "cabinet.player_pitch": (
        "Um serviço de música completo, como o VK ou o Apple Music: mixes, playlists, "
        "letras, equalizador e modo offline."
    ),
    "cabinet.price": "💎 {price} ₽/mês • Primeiro dia grátis",
    "menu.player": "🎧 Abrir o leitor",
    "menu.upload": "⬆️ Enviar uma faixa",
    "menu.premium": "💎 Abrir o leitor — {price} ₽/mês",
    "menu.referral": "🎁 Programa de indicações",
    "menu.playlists": "🗂 As minhas playlists",
    "menu.support": "🆘 Apoio / queixas / ideias",
    "menu.language": "🌍 Язык · Language",
    "lang.title": "🌍 <b>Idioma da interface</b>\n\nEscolhe um idioma — vamos guardá-lo.",
    "lang.saved": "Idioma guardado",
    "lang.pending": "Este idioma ainda não está traduzido — a interface fica em inglês.",
    "lang.back": "⬅️ Voltar",
    "gate.text": (
        "🎵 Para usar o Infinity Music, subscreve os nossos canais.\n\n"
        "Depois toca em «Verificar subscrição»."
    ),
    "gate.check": "✅ Verificar subscrição",
    "gate.not_subscribed": "Não te vejo em todos os canais. Subscreve e tenta de novo.",
    "gate.confirmed": "✅ Subscrição confirmada",
    "gate.subscribe_first": "Subscreve primeiro os canais",
    "moved.text": (
        "🎧 <b>Mudámos de casa</b>\n\n"
        "Este bot já não funciona. Toda a música, a tua biblioteca e as playlists "
        "esperam por ti no novo bot — @{username}.\n\n"
        "Abre-o e toca em «Começar»."
    ),
    "moved.button": "🎧 Ir para o novo bot",
    "library.empty": (
        "🎵 Biblioteca\n\nFaixas: 0\n\n"
        "A tua biblioteca está vazia — adiciona faixas pela pesquisa ou pelo envio."
    ),
    "library.title": "🎵 Biblioteca\n\nFaixas: {count}",
    "library.search_button": "🔍 Pesquisar na minha biblioteca",
    "library.nothing_found": "Nada encontrado na tua biblioteca.",
    "library.found": "Encontrado na biblioteca: {count}",
    "playlists.title": "📂 Playlists\n\nTotal: {total}",
    "playlists.empty_hint": "\n\nAinda não há playlists — cria a primeira.",
    "playlists.view": "Nome:\n{title}\n\nFaixas:\n{total}",
    "playlists.view_empty_hint": "\n\nEsta playlist está vazia — adiciona faixas a partir da ficha.",
    "playlists.enter_title": "Escreve o nome da playlist",
    "playlists.title_length": "O nome deve ter entre 1 e {limit} caracteres. Tenta de novo.",
    "playlists.free_limit": (
        "O plano grátis permite {limit} playlists.\n"
        "💎 O Premium tira o limite — vê «Comprar Premium» no menu."
    ),
    "playlists.created": "✅ Playlist «{title}» criada.",
    "playlists.not_found": "Playlist não encontrada",
    "playlists.delete_confirm": (
        "Apagar a playlist «{title}»?\n\nAs faixas ficam no catálogo e na tua biblioteca."
    ),
    "playlists.deleted": "Playlist apagada",
    "playlists.create_button": "➕ Nova playlist",
    "playlists.delete_button": "🗑 Apagar playlist",
    "playlists.delete_yes": "🗑 Sim, apagar",
    "search.nothing": "Nada encontrado para «{query}».",
    "search.results": "🔍 Resultados de «{query}»\n\nEncontrados: {total}",
    "search.enter_track": "Escreve o título da faixa",
    "search.searching_web": "🔎 A procurar na web — a faixa chega já.",
    "search.instrumental_not_found": "Instrumental não encontrado",
    "search.instrumental_card": "🎼 {title} (Instrumental)",
    "quick.nothing": (
        "Não encontrei nada. Tenta de outra forma — «Kizaru Fake ID», por exemplo: "
        "artista e título juntos acertam melhor."
    ),
    "quick.stale": "Esta lista está desatualizada — pesquisa de novo.",
    "quick.results_title": "🎵 Faixas para «{query}»",
    "quick.results_artist_only": "🎵 Sem correspondência exata para «{query}». Faixas de {artist}:",
    "quick.searching": "🔎 A procurar…",
    "quick.sending": "A enviar…",
    "quick.busy": "O serviço de download está ocupado, tenta daqui a um minuto",
    "quick.downloading": "A descarregar a faixa — chega aqui",
    "quick.already_fetching": "Já estou a descarregar esta faixa — chega em poucos segundos",
    "quality.note_high": "🎚 Melhor qualidade disponível · {format} · {size} MB",
    "quality.note_lossless": "🎚 Original do autor · {format} · {size} MB",
    "quick.preparing_best": "A preparar a melhor qualidade — chega aqui",
    "menu.settings": "⚙️ Definições",
    "settings.title": "<b>⚙️ Definições</b>",
    "settings.quality_hint": "A qualidade em que as faixas chegam.\n\n<b>Normal</b> — mp3 128 kbps, o que todos recebem hoje.\n<b>Melhor</b> — o máximo que a fonte oferece: 160 kbps e, nalgumas faixas, o ficheiro original do autor (WAV ou FLAC). Demora mais alguns segundos e pesa mais.",
    "settings.quality_mp3": "🎵 Normal · mp3 128",
    "settings.quality_best": "🎚 Melhor qualidade (Premium)",
    "settings.quality_premium_only": "A melhor qualidade faz parte da subscrição Premium.",
    "settings.quality_saved_mp3": "Pronto: as faixas chegam como antes",
    "settings.quality_saved_best": "Pronto. As faixas passam a chegar no melhor que a fonte oferece: o original do autor onde existe, caso contrário 160 kbps em vez de 128. Onde não há nenhum dos dois, recebe o ficheiro do costume, sem erros nem esperas.",
    "settings.back": "◀️ Voltar",
    "settings.cover_hint": "<b>A capa</b> já vem embutida no ficheiro e aparece no leitor. Ative a imagem à parte se guarda a música na sua própria biblioteca.",
    "settings.cover_on": "🖼 Capa à parte — ligada",
    "settings.cover_off": "🖼 Capa à parte — desligada",
    "card.title": "🎧 {title}",
    "card.not_found": "Faixa não encontrada",
    "card.added": "Adicionada à tua biblioteca",
    "card.already": "Já está na tua biblioteca",
    "card.removed": "Removida da tua biblioteca",
    "card.no_playlists": "Ainda não tens playlists — cria uma em 📂 Playlists",
    "card.added_to_playlist": "Adicionada a «{title}»",
    "card.already_in_playlist": "A faixa já está nesta playlist",
    "card.removed_from_playlist": "Removida da playlist",
    "card.share_text": "Partilha a faixa «{artist} — {title}»:",
    "card.add_library": "➕ Adicionar à biblioteca",
    "card.remove_library": "🗑 Remover da biblioteca",
    "card.add_playlist": "📂 Adicionar à playlist",
    "card.remove_playlist": "🗑 Remover da playlist",
    "card.download": "⬇️ Descarregar",
    "card.share": "📤 Partilhar",
    "card.edit_admin": "✏️ Editar (admin)",
    "player.next": "▶️ Seguinte",
    "player.stop": "⏹ Parar",
    "player.library_empty_add": "A tua biblioteca está vazia — adiciona faixas",
    "player.mix_started": "🎶 Mix iniciado",
    "player.mix_continue": "🎲 Continuar o mix",
    "player.library_empty": "A tua biblioteca está vazia",
    "player.queue_finished": "✅ A fila terminou",
    "player.playing_library": "▶️ A tocar a tua biblioteca",
    "player.playlist_empty": "A playlist está vazia",
    "player.playlist_finished": "✅ Playlist terminada",
    "player.playing_playlist": "▶️ A tocar «{title}»",
    "player.results_stale": "Estes resultados estão desatualizados — pesquisa de novo",
    "player.nothing_found": "Nada encontrado",
    "player.results_finished": "✅ Resultados terminados",
    "player.playing_results": "▶️ A tocar os resultados",
    "player.queue_stopped": "⏹ Fila parada",
    "upload.intro": "⬆️ <b>Carregar música</b>\n\n📎 <b>Como ficheiro de áudio</b> — envie a faixa como ficheiro. Quantas quiser, toda a coleção uma a uma — <b>grátis e sem limites</b>.\n\n🔗 <b>Por link</b> — do YouTube Music, SoundCloud e outras plataformas: requer <b>💎 Premium</b>.\n\n⚠️ Indique o intérprete — caso contrário a faixa fica «Desconhecido».\n\nAguardo ficheiro ou link 👇",
    "upload.confirm_button": "✅ Enviar",
    "upload.enter_title": "Escreve o título.",
    "upload.as_audio": "Envia o ficheiro como áudio (música), não como documento.",
    "upload.premium_bulk": "Carregar por link é só para 💎 Premium.\nFicheiros de áudio são grátis e sem limites — envie a faixa como ficheiro.",
    "upload.reading_link": "🔍 A ler o link…",
    "upload.link_failed": "Não foi possível abrir esse link. Verifique-o e tente de novo.",
    "upload.queued_link": "⏳ Recebido! Vamos buscar a faixa e enviá-la aqui — normalmente menos de um minuto.",
    "upload.drm_service": "🔒 <b>{service}</b> só entrega um fluxo protegido — o ficheiro em si não está lá.\n\nA lista de faixas lê-se à mesma: «Transferência» encontra as mesmas músicas em fontes disponíveis e coloca-as na sua biblioteca.",
    "upload.go_transfer": "🔄 Transferir a playlist",
    "upload.reading_playlist": "🔍 A ler a playlist…",
    "upload.playlist_failed": "Não consegui ler essa playlist. Verifica o link e tenta de novo.",
    "upload.unavailable": "A importação está indisponível — tenta mais tarde.",
    "upload.queued_videos": (
        "⏳ Aceites {queued} vídeos.\n\n"
        "A música vai aparecer na tua biblioteca à medida que for processada — sem mensagem por faixa."
    ),
    "upload.reading_soundcloud": "🔍 A ler a página do SoundCloud…",
    "upload.soundcloud_failed": "Não consegui ler essa página do SoundCloud. Verifica o link e tenta de novo.",
    "upload.queued_soundcloud": (
        "⏳ Aceites {queued} faixas do SoundCloud.\n\n"
        "Vão aparecer na tua biblioteca à medida que forem processadas — sem mensagem por faixa."
    ),
    "upload.queued_one_soundcloud": "⏳ Recebido! Vamos buscar a faixa ao SoundCloud e enviá-la aqui — normalmente em menos de um minuto.",
    "upload.waiting_file": "Espero um ficheiro de áudio ou um link — YouTube Music ou SoundCloud 🎵",
    "upload.checking_link": "🔍 A verificar o link…",
    "upload.video_failed": "Não consegui abrir esse vídeo. Verifica o link e tenta de novo.",
    "upload.live_stream": "Isso é uma transmissão em direto — não aceitamos.",
    "upload.queued_video": (
        "⏳ Aceite: «{title}» ({duration}).\n"
        "Vamos descarregar e enviar a faixa aqui — normalmente em menos de um minuto."
    ),
    "upload.title_length": "O título deve ter entre 1 e 256 caracteres. Tenta de novo.",
    "upload.enter_artist": "Escreve o artista.",
    "upload.artist_length": "O nome do artista deve ter entre 1 e 256 caracteres. Tenta de novo.",
    "upload.duplicate_warning": (
        "\n\n⚠️ «{artist} — {title}» já existe no catálogo.\n"
        "Se for outra faixa, volta atrás e muda o título "
        "(acrescenta «(Rex)», por exemplo). Caso contrário, confirma."
    ),
    "upload.check_data": "Confirma os dados:\n\nTítulo: {title}\nArtista: {artist}\nDuração: {duration}",
    "upload.moderation": (
        "⏳ «{artist} — {title}» foi adicionada à tua biblioteca e enviada para revisão — "
        "aparece no catálogo comum depois de aprovada."
    ),
    "upload.done": "✅ «{artist} — {title}» foi adicionada ao catálogo comum e à tua biblioteca.",
    "premium.perks": (
        "🚫 <b>Sem publicidade</b> — nem banners nem pausas\n"
        "📥 <b>Modo offline</b> — descarrega faixas e ouve sem internet\n"
        "🔄 <b>Transferência em bloco</b> — playlists inteiras do Spotify, Yandex, VK, SoundCloud\n"
        "🎼 <b>Sem limites</b> — playlists e envios à vontade\n"
        "🎛 <b>Equalizador e temporizador</b> — 20 predefinições, adormece com música\n"
        "📝 <b>Letras</b> — adiciona e edita\n"
        "🎁 <b>Dias de oferta</b> — conquistas e amigos trazem mais Premium"
    ),
    "premium.plan_year": "um ano",
    "premium.plan_month": "um mês",
    "premium.plan_months": "{months} {months_word}",
    "premium.active": "💎 <b>Premium ativo</b> até {date}\n\nPodes renovar antes — os dias somam-se.",
    "premium.offer": (
        "💎 <b>Infinity Music Premium</b>\n\n"
        "Apenas <b>{price} ₽ por mês</b> — mais barato que um café. "
        "Quanto mais longo o plano, menor o preço do mês.\n\nEscolhe a duração:"
    ),
    "premium.invoice_title": "Premium por {label}",
    "premium.invoice_description": "Sem publicidade, playlists ilimitadas e limite de envios maior.",
    "premium.invoice_failed": "Não foi possível emitir a fatura — tenta mais tarde",
    "premium.invoice_failed_card": "Não foi possível emitir a fatura — tenta mais tarde ou paga com Stars",
    "premium.payment_failed": "Não foi possível criar o pagamento — tenta mais tarde",
    "premium.pay_intro": (
        "💳 Pagamento de {price} ₽ — Premium por {label}.\n\n"
        "Toca no botão, paga como preferires e volta ao bot — "
        "o Premium ativa-se sozinho em menos de um minuto."
    ),
    "premium.pay_button": "Pagar {price} ₽",
    "premium.card_unavailable": "O pagamento com cartão ainda não está disponível",
    "premium.bad_payment": "Pagamento inválido — começa de novo",
    "premium.activated": "✅ Premium ativo até {date}! Obrigado pelo apoio 💛",
    "premium.plan_button": "{label} — {price} ₽{suffix}",
    "premium.method_title": "<b>Premium por {label}</b>\n\nComo prefere pagar?\n\n⭐ <b>{stars} Stars</b> — dentro do Telegram, sem cartão\n💳 <b>{price} ₽</b> — cartão ou SBP",
    "premium.pay_stars": "⭐ Pagar {stars} Stars",
    "premium.pay_rub": "💳 Pagar {price} ₽",
    "premium.per_month": " · {per_month} ₽/mês",
    "premium.discount": " · −{discount}%",
    "premium.month_short": "mês",
    "premium.disable_ads": "💎 Desligar a publicidade (Premium)",
    "premium.continue": "Continuar a usar o bot",
    "ads.text": (
        "📢 Publicidade\n\nA tua publicidade podia estar aqui.\n\n"
        "Desliga os anúncios e fica sem limites com 💎 Premium."
    ),
    "referral.forever": "Infinity Premium",
    "referral.reward_days": "{days} {days_word} de Premium",
    "referral.rank": "{emoji} Nível: <b>{title}</b>",
    "referral.to_next_rank": "Até ao nível {emoji} {title} — faltam {count} {friends_word}",
    "referral.next_reward": "\n🔥 Mais {count} {friends_word} — e recebes {reward}\n",
    "referral.title": "🎁 <b>Programa de indicações</b>",
    "referral.invited": "👥 Convidados: <b>{count}</b>",
    "referral.your_link": "<b>O teu link</b> (toca para copiar):",
    "referral.rewards": "<b>Recompensas</b>",
    "referral.share_text": (
        "Olha este bot: encontra e descarrega qualquer música de graça — "
        "escreves o título e ele envia-te a música."
    ),
    "referral.invite_button": "📤 Convidar um amigo",
    "referral.refresh": "🔄 Atualizar",
    "transfer.intro": (
        "📥 <b>Traz a tua música de outros serviços</b>\n\n"
        "Envia-me:\n"
        "▪️ um link para uma playlist pública do <b>Spotify</b> ou <b>Yandex Music</b>;\n"
        "▪️ um link do <b>SoundCloud</b> (perfil, gostos, set);\n"
        "▪️ ou apenas uma lista em texto, uma faixa por linha:\n"
        "<code>Kizaru — Fendi\nBig Baby Tape — Gimme the Loot</code>\n\n"
        "É assim que a música vem do VK e de qualquer outro lado: copia a lista "
        "e envia-a aqui.\n\n"
        "Vamos procurar essas faixas no nosso catálogo e descarregar o que faltar."
    ),
    "transfer.button": "📥 Transferir",
    "transfer.cancelled": "Transferência cancelada.",
    "transfer.soundcloud_hint": (
        "Os links do SoundCloud vão para o assistente «Enviar uma faixa» — ele "
        "descarrega o áudio diretamente, sem procurar correspondências."
    ),
    "transfer.reading": "A ler a lista…",
    "transfer.parse_failed": "Não consegui ler a lista. Tenta enviá-la como texto.",
    "transfer.no_tracks": "Não encontrei faixas. Formato da linha: <code>Artista — Título</code>.",
    "transfer.more": "\n…e mais {count}",
    "transfer.found": "Faixas encontradas: <b>{count}</b>\n\n{preview}{tail}\n\nPasso-as para a tua biblioteca?",
    "transfer.empty_list": "A lista está vazia — começa de novo",
    "transfer.unavailable": "A transferência está indisponível — as tarefas em segundo plano estão desligadas.",
    "transfer.start_failed": "Não foi possível iniciar a transferência — tenta mais tarde.",
    "transfer.started": (
        "📥 A transferir {count} faixas. Vai demorar — envio um relatório quando terminar.\n\n"
        "O que já está no catálogo aparece já na tua biblioteca."
    ),
    "contest.already": "Já estás a participar — aguardamos os resultados 🍀",
    "contest.joined": "🎉 Estás na lista! Boa sorte no sorteio",
    "contest.finished": "O concurso terminou",
    "contest.requirements": "Ainda faltam condições:",
    "contest.need_channel": "• subscreve o canal",
    "contest.need_referrals": "• convida amigos: {referrals} de {required}",
    "contest.subscribe": "📢 Subscrever o canal",
    "contest.participating": "✅ Estás a participar",
    "contest.join": "🎉 Participar",
    "contest.open_app": "🎧 Abrir o Infinity Music",
    "inline.listen": "🎧 Ouvir no Infinity Music",
    "inline.instrumental": "🎼 Instrumental",
    "inline.open": "🎧 Abrir o Infinity Music",
}
