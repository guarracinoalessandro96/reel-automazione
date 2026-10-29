"""Dove si pubblica (un solo posto da cambiare: lo leggono pubblica.py, report.py e salute.py).

19/10/2026: SOLO YOUTUBE (scelta di Alessandro: "pubblichiamo solamente su youtube al momento, cresciamo solo li'";
Facebook, TikTok e Instagram si penseranno in futuro). Il codice delle altre piattaforme resta pronto.
Per riaccendere Facebook: PLATFORMS = ["youtube", "facebook"]. Tutte: instagram, facebook, youtube, tiktok.
"""
# 25/10/2026: Instagram riacceso (musica NATIVA di Instagram; i reel vanno anche sulla Pagina Facebook con la
# condivisione automatica di Instagram). TikTok: programmato ogni sera dal PC (TikTok Studio), non da qui.
# 25/10 sera: la condivisione automatica di Instagram arriva solo sul profilo PERSONALE (che lui non vuole):
# la PAGINA Facebook "Alessandro Guarracin" (600 follower) la pubblica la macchina via API (musica nostra, 1080p).
# 29/10/2026: Facebook NON piu' via API (0-6 visualizzazioni da sempre, Pagina senza restrizioni): Alessandro ha scelto
# di programmarlo da Meta Business Suite dal PC, come TikTok Studio (facebook_prepara.py + attivita' Claude
# "facebook-programma"), con gli stessi file della cartella "TikTok - da pubblicare" e un audio scelto li'.
# Poco dopo, sempre il 29/10: anche INSTAGRAM da Meta Business Suite ("voglio pubblicare dall'app Meta Business Suite e
# prendere l'audio di tendenza, lo faccio anche con BauVet"): un solo reel programmato su Pagina Facebook + Instagram.
# ... ma Meta Business Suite da PC NON permette l'audio sui reel per Instagram ("La pubblicazione dei reel modificati su
# Instagram non e' supportata"): Instagram resta automatico via API, che gia' attacca un brano NATIVO di Instagram scelto
# tra quelli di tendenza (scegli_audio_instagram). Facebook: Meta Business Suite con l'audio di Meta.
PLATFORMS = ["youtube", "instagram"]
TIKTOK_A_MANO = False     # True = ogni giorno alle 21 i video per TikTok (senza musica) arrivano su Telegram
# 25/10/2026 sera: TikTok via TikTok Studio. A ogni orario la macchina salva su Drive ("TikTok - da pubblicare") la
# versione 1080p sotto i 10 MB, senza musica, con la didascalia; alle 20 il PC programma in Chrome quelli delle ultime
# 24 ore per il giorno dopo, stessa ora, con un suono NATIVO di TikTok (tiktok_prepara.py + attivita' Claude
# "tiktok-programma-sera"). TikTok e' quindi un giorno indietro rispetto a YouTube.
TIKTOK_STUDIO = True
# 29/10/2026: provate le BOZZE nell'app TikTok (API, funzionano), ma Alessandro vuole gli stessi video pubblicati su tutte
# le piattaforme, TikTok compreso, tramite TikTok Studio dal PC: bozze spente (per riaccenderle: True)
TIKTOK_BOZZE = False
