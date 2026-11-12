"""
TikTok Studio (25/10/2026, rivisto il 27/10/2026). L'attivita' di Claude "tiktok-programma-sera" (Claude in Chrome,
profilo Alessandro) programma su TikTok, con un suono NATIVO di TikTok, i reel gia' usciti su YouTube.

pubblica.py salva per ogni orario, nella cartella Drive "TikTok - da pubblicare", la versione 1080p (sotto i 10 MB,
senza musica salvo parlato/momento) con la didascalia nella descrizione e l'orario YouTube in appProperties.

27/10/2026: il primo giro (26/10) e' partito tardi e la rete e' caduta dopo 1 video -> 17 video arretrati. Ora:
- ogni video in attesa prende il PROSSIMO ORARIO LIBERO (gli stessi 10 orari di YouTube), cosi' niente si perde;
- (29/10) prima i PIU' NUOVI; quelli usciti su YouTube da piu' di 2 giorni si saltano;
- l'attivita' gira piu' volte la sera (20, 21, 22, 23) e ogni giro ne fa al massimo --max (default 4);
- i file sopra i 9 MB (limite di Chrome 10 MB) vengono rimpiccioliti qui sul PC.

  python tiktok_prepara.py [--max 4]      scarica i prossimi video in CARTELLA_PC\\<data> e scrive elenco.json
  python tiktok_prepara.py segna ID "AAAA-MM-GG HH:MM"   segna su Drive che il video ID e' programmato a quell'ora

I video gia' programmati da piu' di 3 giorni vanno nel cestino di Drive (lo svuota Alessandro).
"""
import datetime, json, os, re, sys
import requests
from sposta_su_pc import SEGRETI, API, token, elenca_cartelle
import cartelle              # 7/11/2026: dove stanno le cartelle su Drive, prima e dopo il riordino

CARTELLA_TIKTOK = "TikTok - da pubblicare"
CARTELLA_PC = os.path.join(os.path.expanduser("~"), "TikTok da programmare")
from orario import ORE      # stessi orari di YouTube (29/10/2026: 10 al giorno)
MAX_MB = 9.0
VECCHIO_GIORNI = 2           # 29/10/2026: con 10 al giorno Chrome ne programma 2-8 a sera: si pubblicano i piu' nuovi
ANTICIPO_MIN = 40            # TikTok vuole almeno 15' di anticipo: si tiene margine per il caricamento


def ora_roma():
    from zoneinfo import ZoneInfo
    return datetime.datetime.now(ZoneInfo("Europe/Rome")).replace(tzinfo=None)


def collega():
    k = json.load(open(SEGRETI, encoding="utf-8"))
    H = {"Authorization": "Bearer " + token(k)}
    padre = requests.get(f"{API}/{k['DRIVE_FOLDER_DA_PUBBLICARE']}", params={"fields": "parents"}, headers=H,
                         timeout=30).json()["parents"][0]
    # 7/11/2026 (riordino del Drive chiesto da Alessandro): accanto a "Video da pubblicare" o dentro
    # "Sistema (non toccare)" (cartelle.py). Qui non si crea mai: se manca ci si ferma, come prima.
    cart = cartelle.trova(CARTELLA_TIKTOK, padre, lambda q: elenca_cartelle(H, q))
    if not cart:
        raise RuntimeError(f"cartella '{CARTELLA_TIKTOK}' non trovata su Drive")
    return H, cart


def elenca(H, cart):
    files, pagina = [], None
    while True:
        r = requests.get(API, headers=H, timeout=60, params={
            "q": f"'{cart}' in parents and trashed = false and mimeType = 'video/mp4'", "pageSize": 200,
            "fields": "nextPageToken,files(id,name,size,description,appProperties)", "pageToken": pagina}).json()
        files += r.get("files", [])
        pagina = r.get("nextPageToken")
        if not pagina:
            return files


def orari_liberi(occupati, adesso, ore=None):
    """Orari della giornata (orario.ORE, o le ore date: Facebook ha le sue) a partire da adesso + ANTICIPO_MIN,
    saltando quelli gia' usati."""
    ore = ORE if ore is None else ore
    t = (adesso + datetime.timedelta(minutes=ANTICIPO_MIN)).replace(minute=0, second=0, microsecond=0)
    t += datetime.timedelta(hours=1)
    while True:
        if t.hour in ore and t not in occupati:
            yield t
        t += datetime.timedelta(hours=1)


def rimpicciolisci(path):
    """Se il file supera MAX_MB lo ricodifica sotto gli 8 MB (stessa risoluzione)."""
    if os.path.getsize(path) <= MAX_MB * 1e6:
        return
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import overlay
    tmp = path + ".piccolo.mp4"
    overlay.versione_tiktok(path, tmp, audio=True, max_mb=7.5)
    os.replace(tmp, path)


def frase_di(descrizione):
    """La frase del reel dalla descrizione (senza 'Giorno X/365' e hashtag), per riconoscere i doppioni."""
    righe = [r.strip() for r in (descrizione or "").splitlines()
             if r.strip() and not r.strip().startswith(("Giorno", "#"))]
    return re.sub(r"\W+", " ", righe[0].lower()).strip() if righe else ""


def gia_programmate(files, fatto, quando, giorni=7):
    """3/11/2026: frasi gia' programmate negli ultimi `giorni`: la stessa frase non torna su questa piattaforma."""
    da = ora_roma() - datetime.timedelta(days=giorni)
    fatte = set()
    for f in files:
        p = f.get("appProperties") or {}
        if p.get(fatto) == "1" and p.get(quando, "") >= f"{da:%Y-%m-%d %H:%M}":
            fatte.add(frase_di(f.get("description")))
    return fatte - {""}


def prepara(massimo=4):
    H, cart = collega()
    adesso = ora_roma()
    attesa, occupati, cestino = [], set(), []
    files = elenca(H, cart)
    doppie = gia_programmate(files, "tiktok_fatto", "tiktok_quando")
    for f in files:
        p = f.get("appProperties") or {}
        if "tiktok_slot" not in p:
            continue                                     # vecchi video del periodo Telegram
        slot = datetime.datetime.strptime(p["tiktok_slot"], "%Y-%m-%d %H:%M")
        if p.get("tiktok_fatto") == "1":
            if p.get("tiktok_quando"):
                occupati.add(datetime.datetime.strptime(p["tiktok_quando"], "%Y-%m-%d %H:%M"))
            if slot < adesso - datetime.timedelta(days=3):
                cestino.append(f["id"])
            continue
        if slot > adesso:
            continue                                     # non ancora uscito su YouTube
        if "STO-" in f["name"]:
            continue                                     # 29/10/2026: niente racconti ("storie inventate, non su di me")
        if slot < adesso - datetime.timedelta(days=VECCHIO_GIORNI):
            continue                                     # 29/10/2026: troppo vecchio, si salta (resta su Drive)
        fr = frase_di(f.get("description"))
        if fr and fr in doppie:
            continue                                     # 3/11/2026: stessa frase gia' su TikTok negli ultimi 7 giorni
        doppie.add(fr)
        attesa.append((0, slot, f, p))
    attesa.sort(key=lambda x: x[1], reverse=True)       # 29/10/2026: prima i PIU' NUOVI (formato attuale da 10 s)
    liberi = orari_liberi(occupati, adesso)
    elenco = []
    for _, slot, f, p in attesa[:massimo]:
        quando = next(liberi)
        d = os.path.join(CARTELLA_PC, f"{quando:%Y-%m-%d}")
        os.makedirs(d, exist_ok=True)
        dest = os.path.join(d, f["name"])
        if not os.path.exists(dest):
            with requests.get(f"{API}/{f['id']}", params={"alt": "media"}, headers=H, stream=True, timeout=600) as r:
                r.raise_for_status()
                with open(dest, "wb") as out:
                    for pezzo in r.iter_content(4 * 1024 * 1024):
                        out.write(pezzo)
        rimpicciolisci(dest)
        elenco.append({"id": f["id"], "file": dest, "mb": round(os.path.getsize(dest) / 1e6, 1),
                       "orario": f"{quando:%Y-%m-%d %H:%M}", "youtube": p["tiktok_slot"],
                       "voce": p.get("tiktok_voce") == "1", "didascalia": pulisci(f.get("description", ""))})
    for fid in cestino:                                  # nel cestino, non cancellati per sempre
        requests.patch(f"{API}/{fid}", json={"trashed": True}, headers=H, timeout=30)
    os.makedirs(CARTELLA_PC, exist_ok=True)
    try:     # 6/11/2026 (revisione): un registro rovinato non deve mai fermare il giro: l'elenco esce comunque
        evita = suoni_recenti()
        for x in elenco:
            x["suoni_da_evitare"] = evita
        metti_ricerche(elenco)
    except Exception as e:
        print("suoni da evitare non aggiunti:", e)
    metti_musica_screenshot(elenco)
    json.dump(elenco, open(os.path.join(CARTELLA_PC, "elenco.json"), "w", encoding="utf-8"), ensure_ascii=False,
              indent=1)
    return elenco, len(attesa)


NON_SUONI = {"-", "", "audio suo", "nessuno", "nessun audio"}


def suoni_recenti(quanti=30, registro=None):
    """6/11/2026: negli ultimi 20 TikTok giravano sempre gli stessi 4 brani (i primi di audio_tendenza.json):
    i brani degli ultimi `quanti` video del registro non si riusano. registro: un altro registro con le stesse colonne
    (6/11/2026: anche quello di Facebook, facebook_prepara.py); le note tra parentesi non sono brani.
    6/11/2026 (revisione): le righe scritte da strumenti di Windows possono essere in ANSI ("Sarà" in cp1252, es.
    Add-Content di PowerShell 5.1): ogni riga si legge in UTF-8 e, se non va, in cp1252; mai un errore."""
    try:
        dati = open(registro or os.path.join(CARTELLA_PC, "registro.txt"), "rb").read()
        righe = []
        for b in dati.replace(b"\x00", b"").splitlines():     # anche righe UTF-16 (Out-File): via gli zeri
            try:
                righe.append(b.decode("utf-8-sig"))
            except UnicodeDecodeError:
                righe.append(b.decode("cp1252", errors="replace"))
    except Exception:
        return []
    suoni = []
    for r in reversed(righe):
        c = [x.strip() for x in r.split("|")]
        if len(c) >= 5 and c[1] != "nota" and c[3].lower() not in NON_SUONI and not c[3].startswith("("):
            if c[3] not in suoni:
                suoni.append(c[3])
            if len(suoni) >= quanti:
                break
    return suoni


# 6/11/2026 (Alessandro: "ogni video una musica diversa"): ogni video del giro ha una parola di ricerca diversa per i
# suoni, a rotazione con giorno e ora, cosi' ogni giro non riparte dagli stessi brani in cima alla lista
# (revisione: niente "gym", la palestra non va nei testi e il nome del suono si vede sotto il video)
RICERCHE = ["motivational", "epic", "workout", "cinematic", "phonk", "powerful", "hype", "energetic", "trailer",
            "sport", "inspiring", "determination"]


def ricerche(n, adesso=None):
    adesso = adesso or ora_roma()
    inizio = adesso.toordinal() * 5 + adesso.hour
    return [RICERCHE[(inizio + i) % len(RICERCHE)] for i in range(n)]


def metti_musica_screenshot(elenco):
    """12/11/2026 (Alessandro: "utilizza la stessa musica che sta su quello screenshot... cerca prima se puoi mettere
    quella musica"): "musica_screenshot" = il brano dello screenshot della frase (dal nome del file, che ha l'id):
    il giro lo cerca PRIMA di tutto il resto, anche se e' tra i suoni da evitare; se non c'e', sceglie come sempre."""
    try:
        qui = os.path.dirname(os.path.abspath(__file__))
        if qui not in sys.path:
            sys.path.insert(0, qui)
        import musica_screenshot
        for x in elenco:
            brano = musica_screenshot.da_nome_file(os.path.basename(x.get("file", "")))
            if brano:
                x["musica_screenshot"] = brano
    except Exception as e:      # mai fermare il giro per un suggerimento
        print("musica degli screenshot non aggiunta:", e)


def metti_ricerche(elenco):
    try:
        for x, q in zip(elenco, ricerche(len(elenco))):
            x["cerca"] = q
    except Exception as e:      # mai fermare il giro per un suggerimento
        print("parole di ricerca non aggiunte:", e)


PAROLE_RICERCA ="frasi motivazionali · motivazione · disciplina · lavoro · costanza"


def pulisci(testo):
    """29/10/2026: via le domande per i commenti ("scrivilo nei commenti"/"qui sotto"): non piacciono ad Alessandro.
    6/11/2026: la riga di ricerca e' quella della frase (didascalie.py: "Frasi motivazionali sulla costanza e sul
    lavoro."), non piu' le stesse 5 parole su ogni video: TikTok penalizza le parole ammucchiate o che non c'entrano.
    Le didascalie nuove ce l'hanno gia'; ai momenti veri (#vitavera) niente riga sulle frasi motivazionali."""
    righe = [re.sub(r"\s*·\s*seguimi per vedere dove arrivo", "", r) for r in testo.splitlines() if "👇" not in r]   # 30/10: via "seguimi"
    testo = re.sub(r"(\r?\n){3,}", "\n\n", "\n".join(righe)).strip()
    try:
        qui = os.path.dirname(os.path.abspath(__file__))
        if qui not in sys.path:
            sys.path.insert(0, qui)
        import didascalie
        # 8/11/2026 23:20 (Alessandro: "ci va solo il titolo", su tutti i social): solo la frase, niente riga di
        # ricerca, hashtag o Giorno X/365 (anche per i video gia' preparati con la descrizione vecchia)
        frase = didascalie.frase_della_didascalia(testo)
        if frase:
            return frase
        return testo
    except Exception as e:
        print("riga di ricerca dalla frase non riuscita, uso quella fissa:", e)
    if PAROLE_RICERCA not in testo:      # 1/11/2026: TikTok e' anche un motore di ricerca
        testo += "\n\n" + PAROLE_RICERCA
    return testo


def segna(fid, quando):
    H, _ = collega()
    requests.patch(f"{API}/{fid}", json={"appProperties": {"tiktok_fatto": "1", "tiktok_quando": quando}}, headers=H,
                   timeout=30).raise_for_status()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) > 2 and sys.argv[1] == "segna":
        segna(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "")
        print("segnato", sys.argv[2])
    else:
        n = int(sys.argv[sys.argv.index("--max") + 1]) if "--max" in sys.argv else 4
        elenco, in_attesa = prepara(n)
        for x in elenco:
            print(x["orario"], f"{x['mb']} MB", "voce" if x["voce"] else "muto", x["file"])
        print(f"in attesa in tutto: {in_attesa} | in questo giro: {len(elenco)}")
        print("elenco:", os.path.join(CARTELLA_PC, "elenco.json"))
