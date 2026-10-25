"""Dove si pubblica (un solo posto da cambiare: lo leggono pubblica.py, report.py e salute.py).

19/10/2026: SOLO YOUTUBE (scelta di Alessandro: "pubblichiamo solamente su youtube al momento, cresciamo solo li'";
Facebook, TikTok e Instagram si penseranno in futuro). Il codice delle altre piattaforme resta pronto.
Per riaccendere Facebook: PLATFORMS = ["youtube", "facebook"]. Tutte: instagram, facebook, youtube, tiktok.
"""
# 25/10/2026: Instagram riacceso (musica NATIVA di Instagram; i reel vanno anche sulla Pagina Facebook con la
# condivisione automatica di Instagram). TikTok: programmato ogni sera dal PC (TikTok Studio), non da qui.
# 25/10 sera: la condivisione automatica di Instagram arriva solo sul profilo PERSONALE (che lui non vuole):
# la PAGINA Facebook "Alessandro Guarracin" (600 follower) la pubblica la macchina via API (musica nostra, 1080p).
PLATFORMS = ["youtube", "instagram", "facebook"]
TIKTOK_A_MANO = False     # True = ogni giorno alle 21 i video per TikTok (senza musica) arrivano su Telegram
# 25/10/2026 sera: TikTok via TikTok Studio. A ogni orario la macchina salva su Drive ("TikTok - da pubblicare") la
# versione 1080p sotto i 10 MB, senza musica, con la didascalia; alle 20 il PC programma in Chrome quelli delle ultime
# 24 ore per il giorno dopo, stessa ora, con un suono NATIVO di TikTok (tiktok_prepara.py + attivita' Claude
# "tiktok-programma-sera"). TikTok e' quindi un giorno indietro rispetto a YouTube.
TIKTOK_STUDIO = True
