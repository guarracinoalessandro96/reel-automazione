"""
Pubblicazione automatica dei Reel (GitHub Actions, alle 9, 12, 15, 18, 21 ora italiana).

Ad ogni esecuzione:
  0. riprova le piattaforme fallite nelle esecuzioni precedenti (max 3 tentativi)
  1. analizza i video nuovi della cartella Drive "Da pubblicare": scena (scena.py) e ora di registrazione
     -> ogni video ha il suo orario: mattina alle 9, pranzo alle 12, palestra e uscite la sera...
  2. prende il video che corrisponde a questo orario (se un video aspetta da piu' di 36 ore, esce comunque)
  3. sceglie una frase adatta alla scena (frasi.json: cibo -> dieta, palestra -> fisico, pacchi -> imprenditore...)
     alternando i temi, e una musica adatta al tema
  4. monta il video (taglio, colore, testo, musica) e lo pubblica su Instagram, Facebook, YouTube, TikTok
     con descrizione breve: la stessa frase + 3-4 hashtag
  5. archivia su Drive e aggiorna stato.json

Credenziali: variabili d'ambiente (GitHub Secrets). DRY_RUN=1 fa tutto tranne pubblicare.
"""
import calendar, hashlib, io, json, os, re, sys, time, datetime, random, traceback, subprocess, shutil
import requests
import overlay
import scena as scene_mod
import mie_citazioni
import orario

HERE = os.path.dirname(os.path.abspath(__file__))
FRASI = os.path.join(HERE, "frasi.json")
STATE = os.path.join(HERE, "stato.json")
GRAPH = "https://graph.facebook.com/v23.0"
ENV = os.environ.get
DRY = ENV("DRY_RUN") == "1"
from piattaforme import PLATFORMS, TIKTOK_A_MANO, TIKTOK_STUDIO  # 19/10/2026: SOLO YOUTUBE (si cambia in piattaforme.py)
MAX_TENTATIVI = 3
GIORNI_PRONTI = 7             # reel montati (solo quelli da riprovare) tenuti 7 giorni, poi nel Cestino
MAX_ORIGINALE_MB = 100000     # 25/10/2026: l'originale va SEMPRE intero nell'archivio (massima risoluzione, niente cestino)
# 25/10/2026 notte: Drive (100 GB) mai pieno. Sotto i 6 GB liberi le clip d'archivio meno utili scendono sul PC
# (Drive.libera_spazio + sposta_su_pc.py) fino a tornare a 10 GB liberi; su Drive restano almeno 40 clip.
DRIVE_LIBERO_MIN_GB = 6
DRIVE_LIBERO_OBIETTIVO_GB = 10
ARCHIVIO_MIN = 40
VERSO_PC = "Archivio - verso il PC"
QUALITA_MINIMA = 720          # lato corto minimo (pixel): sotto l'HD il video non si pubblica
CARTELLA_BASSA = "Da controllare - bassa qualità"
ATTESA_MAX_ORE = 36          # oltre questa attesa un video esce al primo orario libero
PRIMO_COMMENTO = False       # disattivato su richiesta: niente commento automatico sotto i reel

TRADIMENTO = re.compile(r"tradi(t|m|sc|re|rai|rei)", re.I)   # 25/10: argomento che non gli piace
TRADIMENTO_QUOTA = 0.0      # ... 26/10/2026: "non parlare di tradimento" -> mai
DONNE = re.compile(r"\b(donn[ae]|ragazz[ae]|fidanzat[ae]|moglie|lei ti|la tua ex|una ex|innamorat)", re.I)   # 26/10: mai
# 29/10/2026 (Alessandro): niente argomenti negativi (non fidarsi degli altri, falsi, invidia, chi ti usa...) e niente
# palestra nelle frasi ("e' vista come cringe, non voglio sembrare il fissato della palestra"): obiettivi di vita,
# vita normale, famiglia, futuro
NEGATIVO = re.compile(r"fid[ao]|fiduc|tradi|fals[io]|invidi|nemic|ti usa|usano|opzion|critic|spalle|giudic|ingrat|"
                      r"serpent|velen|abbandon|delu|mancar\w* di rispetto|vendett|\bodi|cattiv|tratta|ipocri|approfitt|"
                      r"cambiano|ti lasci|spariscon|sparit|squill|chi c'era|tossic|manipol|spegn|lontano da", re.I)
PALESTRA = re.compile(r"palestr|gym|allenam|allenar|ripetizion|muscol|fisico|\bpes[io]\b|squat|panca|dieta|addominal|"
                      r"sudor|bilancier|serie in pi|massa", re.I)

SOLO_MIE = True              # dal 5/10/2026 escono SOLO le citazioni scelte da Alessandro (Google Doc "Le mie citazioni")
DOC_MIE = mie_citazioni.DOC


def mie_frasi(testo):
    return mie_citazioni.frasi(testo, TEMI_PER_SCENA)


# Temi preferiti per ogni scena (il primo e' il piu' adatto)
TEMI_PER_SCENA = {
    "cibo": ["dieta"],
    "palestra": ["palestra", "disciplina", "imprenditore"],
    "lavoro": ["imprenditore", "disciplina"],
    "pacchi": ["imprenditore"],
    "macchina": ["imprenditore", "positivita", "mentalita", "abitudini", "disciplina"],
    "specchio": ["lifestyle", "positivita", "mentalita", "abitudini"],
    "casa": ["famiglia", "abitudini", "mentalita", "positivita"],
    "uscita": ["amicizia", "lifestyle", "positivita", "famiglia"],
}
# Umore della musica per tema (cartelle in musica/, create da genera_musica.py)
MOOD = {"dieta": "luminoso", "palestra": "energia", "imprenditore": "deciso", "disciplina": "deciso",
        "abitudini": "calmo", "positivita": "luminoso", "famiglia": "caldo", "amicizia": "caldo",
        "mentalita": "calmo", "lifestyle": "luminoso"}


GENERE_PER_SCENA = {   # solo musica da motivazione (5/10/2026: le frasi sono tutte motivazionali; niente lofi,
    # tropical, caldo, calmo o luminoso). Varia comunque con la scena.
    "palestra": "phonk", "macchina": "drive", "lavoro": "deciso", "pacchi": "deciso",
    "cibo": "drive", "uscita": "trap", "specchio": "trap", "casa": "deciso"}
GENERI_MOTIVAZIONE = ("phonk", "drive", "trap", "deciso", "energia")
# dal 8/10/2026: prima la musica vera della Raccolta audio di YouTube (prepara_libreria.py), poi quella generata
YT_PER_SCENA = {"palestra": ["yt_carica"], "macchina": ["yt_carica", "yt_epica"], "lavoro": ["yt_epica", "yt_carica"],
                "pacchi": ["yt_carica", "yt_epica"], "specchio": ["yt_carica"], "cibo": ["yt_epica"],
                "casa": ["yt_epica"], "uscita": ["yt_carica", "yt_epica"]}


# ESPERIMENTO "REGOLE" (17/10/2026): al reel delle 21 un titolo + 3 regole che compaiono una alla volta (13 s),
# fino al 31/10; il report confronta i formati (per_formato). Liste in liste.json, ognuna usata una volta.
REGOLE_SLOT, REGOLE_FINO = "", datetime.date(2099, 1, 1)   # dal 18/10 e' uno dei formati a rotazione
# UNO SHORT OGNI ORA (18/10/2026, richiesta di Alessandro, come MoreMozi) su YouTube e Facebook (e Instagram quando
# lo accende). Solo la versione TikTok (a mano, via Telegram) e la cartella Instagram restano alle ORE_PRINCIPALI.
ORE_PRINCIPALI = (9, 13, 17, 21)
PAUSA_ERRORI = 3          # errori di fila su una piattaforma -> pausa automatica (le altre continuano)
PAUSA_ORE = 6
ORA_TIKTOK = 21          # i video TikTok della giornata arrivano su Telegram tutti insieme a quest'ora
# FORMATI provati a rotazione; pesi iniziali, poi report.py li aggiorna (pesi.json "formati") dai risultati veri.
FORMATI = {"frase": 1.0, "frase8": 1.0, "gancio": 1.0, "montaggio": 0.8, "regole": 0.7, "ambiente": 0.6,
           "broll1": 1.0, "broll2": 1.0, "broll3": 1.0, "storia": 1.0}   # 25/10: formati_nuovi.py
# frase8 (21/10/2026): la frase da 8 s. Tra gli Short spinti da YouTube, quelli da 8 s hanno superato 1.200 views
# 10 volte su 47, quelli da 5 s 0 su 24 (stessa mediana ~1.000): si rimette in gara contro il 5 s
GANCIO = {"nome": "gancio", "durata": 8.0, "t": 3.0}          # frase in 2 tempi: la seconda parte dopo 3 s
AMBIENTE = {"nome": "ambiente", "durata": 6.0, "audio_originale": 0.35}   # suono vero della palestra sotto la musica
LIMITE_YT = re.compile(r"uploadLimitExceeded|quotaExceeded|dailyLimitExceeded|exceeded the number of videos", re.I)
SERIE_INIZIO = datetime.date(2026, 10, 16)   # "GIORNO 1 / 365": serie riconoscibile = un motivo per seguire
MIN_PAROLE = 7               # frasi piu' corte rendono meno (vedi scelta della frase in main)
MUSICA_NOSTRA = {"facebook", "instagram", "tiktok"}   # qui NON la Raccolta audio di YouTube (pensata per YouTube): i nostri brani
PREPARA_PER_DOPO = []        # es. ["instagram"]: versione con musica nostra salvata su Drive (spento dal 19/10/2026)
CARTELLA_DOPO = "Pronti per Instagram"   # ... in questa cartella, con il testo da incollare
# TikTok (15/10/2026): Alessandro pubblica a mano dal telefono con un AUDIO DI TENDENZA (non usabile via API):
# ogni reel va su Drive con la frase sopra ma SENZA musica, piu' il testo da incollare
CARTELLA_TIKTOK = "TikTok - da pubblicare"
GIORNI_DOPO = 60              # ... e ci resta 60 giorni


def scegli_musica(tema, recenti, scena=None, nostra=False):
    """Un brano adatto alla scena, evitando quelli usati di recente: prima la Raccolta audio di YouTube, poi i loop
    generati da motivazione. nostra=True: solo i nostri brani (versione per Facebook/Instagram)."""
    yt = [] if nostra else list(YT_PER_SCENA.get(scena, ["yt_carica", "yt_epica"]))
    random.shuffle(yt)
    for mood in (*yt, GENERE_PER_SCENA.get(scena), *random.sample(GENERI_MOTIVAZIONE, len(GENERI_MOTIVAZIONE))):
        if not mood:
            continue
        d = os.path.join(HERE, "musica", mood)
        brani = sorted(f for f in os.listdir(d) if f.endswith((".flac", ".m4a"))) if os.path.isdir(d) else []
        if brani:
            # niente stesso pezzo tra gli ultimi 20 e niente stesso BRANO (pezzi diversi della stessa canzone) negli ultimi 8
            brano = lambda f: re.sub(r"_\d+$", "", os.path.splitext(f)[0])
            vicini = {brano(b) for b in recenti[-8:]}
            liberi = ([b for b in brani if b not in recenti and brano(b) not in vicini]
                      or [b for b in brani if b not in recenti] or brani)
            return os.path.join(d, random.choice(liberi))
    return None


GIORNI_RIUSO = 150            # una citazione puo' tornare dopo 5 mesi (prima escono sempre quelle mai usate)


CON_CHI = {   # chi c'e' nel video (scena.compagnia) -> temi da preferire (+) o evitare (-)
    "famiglia": {"famiglia": 12, "amicizia": -10},
    "amici": {"amicizia": 12, "famiglia": -10},
    "solo": {"famiglia": -8, "amicizia": -8},
}


def scegli_frase(frasi, scena, usi, temi_recenti, pesi=None, compagnia=None):
    """Citazione adatta alla scena. usi = {id: data ISO dell'ultimo utilizzo}.
    Prima quelle mai uscite, poi quelle uscite da piu' di GIORNI_RIUSO giorni (le piu' vecchie per prime):
    la scorta non finisce mai."""
    pref = TEMI_PER_SCENA.get(scena, [])
    limite = (datetime.date.today() - datetime.timedelta(days=GIORNI_RIUSO)).isoformat()
    libere = [f for f in frasi if f["id"] not in usi or usi[f["id"]] < limite]
    cand = [f for f in libere if scena in f["scene"]] or libere
    if not cand:                              # caso estremo: tutte usate di recente -> la meno recente
        return min(frasi, key=lambda f: usi.get(f["id"], ""))

    def punteggio(f):
        s = 10 - 2 * pref.index(f["tema"]) if f["tema"] in pref else 0
        if f["tema"] in temi_recenti[-2:]:
            s -= 6                      # non lo stesso tema due volte di fila
        s += 5 * ((pesi or {}).get(f["tema"], 1.0) - 1)   # report settimanale: i temi che rendono di piu' salgono
        s += CON_CHI.get(compagnia, {}).get(f["tema"], 0)  # es. video con la mamma -> famiglia, non amicizia
        if f["id"] not in usi:
            s += 20                     # le citazioni mai uscite hanno sempre la precedenza
        return s + random.random() * 3  # un po' di varieta'
    return max(cand, key=punteggio)


MOSTRA_AUTORE = False   # dal 5/10/2026 Alessandro non vuole l'autore ne' sul video ne' nelle descrizioni


def serie_testo(cap):
    """'Giorno 12/365' per descrizioni e testi (vuoto se non c'e' la serie)."""
    return (cap.get("serie") or "").replace("GIORNO", "Giorno").replace(" / ", "/")


def testo_breve(cap):
    """Descrizione pubblicata: la stessa frase del video + 3-4 hashtag (niente dettagli personali)."""
    tags = cap.get("hashtag") or ["#citazioni", "#motivazione"]
    testo = cap["gancio"].strip().strip('"“”')
    if MOSTRA_AUTORE and cap.get("autore"):
        testo = "“" + testo.strip('"“”') + "” — " + cap["autore"]
    else:
        testo = testo.rstrip(" .")
    if cap.get("righe"):          # formato REGOLE: titolo + regole numerate
        testo = cap["gancio"] + "\n" + "\n".join(f"{i}. {r}" for i, r in enumerate(cap["righe"], 1))
    serie = serie_testo(cap)
    serie = serie + " · seguimi per vedere dove arrivo" if serie else ""     # il personaggio: un viaggio da seguire
    if cap.get("tema") not in ("momento", "parlato", "regole"):   # 27/10/2026 (racconti), dal 29/10 tutti i reel con frase: una domanda in fondo -> piu' commenti -> piu' spinta dall'algoritmo
        domande = ["E tu, cosa ti sei promesso? Scrivilo qui sotto 👇", "Per chi lo fai tu? Scrivilo nei commenti 👇",
                   "Per chi lo stai facendo tu? Scrivilo qui sotto 👇", "Qual è il tuo obiettivo di quest'anno? 👇",
                   "Sei d'accordo? Scrivi \"sì\" se anche tu non molli 👇"]
        testo += "\n\n" + domande[int(hashlib.md5(cap["id"].encode()).hexdigest(), 16) % len(domande)]
    return (serie + "\n" if serie else "") + testo + "\n\n" + " ".join(dict.fromkeys(tags[:4]))


def ora_roma():
    from zoneinfo import ZoneInfo
    return datetime.datetime.now(ZoneInfo("Europe/Rome"))


def principale(slot):
    """True alle ore principali (Facebook, TikTok, Instagram) e nelle esecuzioni manuali."""
    t = ora_slot(slot)
    return t is None or t.hour in ORE_PRINCIPALI


def youtube_fermo(state):
    return fermo(state, "youtube")


def fermo(state, piattaforma):
    """True se la piattaforma e' in pausa automatica (limite raggiunto o errori ripetuti)."""
    adesso = datetime.datetime.now().isoformat(timespec="minutes")
    fino = state.get("fermo", {}).get(piattaforma, "")
    if piattaforma == "youtube":
        fino = max(fino, state.get("youtube_fermo_fino", ""))
    return fino > adesso


def piattaforme_slot(slot, state):
    """Piattaforme di questo orario: tutte quelle attive (ogni ora), tranne quelle in pausa automatica."""
    return [p for p in attive() if not fermo(state, p)]


def controlla_errori(state, results):
    """Dopo ogni pubblicazione: una piattaforma con PAUSA_ERRORI errori di fila (o con un limite raggiunto) va in
    pausa per qualche ora, con avviso su Telegram. Cosi' un problema su una piattaforma non blocca le altre."""
    errori = state.setdefault("errori_di_fila", {})
    for p, r in results.items():
        if p not in PLATFORMS:
            continue
        if r.get("ok"):
            errori[p] = 0
            continue
        errori[p] = errori.get(p, 0) + 1
        limite = bool(LIMITE_YT.search(str(r.get("errore", ""))))
        if limite or errori[p] >= PAUSA_ERRORI:
            ore = 12 if limite else PAUSA_ORE
            state.setdefault("fermo", {})[p] = (datetime.datetime.now() + datetime.timedelta(hours=ore)).isoformat(
                timespec="minutes")
            errori[p] = 0
            try:
                import avvisi
                avvisi.manda(f"ATTENZIONE\n{p.upper()} in pausa per {ore} ore\n"
                             + ("Ha limitato i caricamenti" if limite else f"{PAUSA_ERRORI} errori di fila") +
                             f"\nUltimo errore: {str(r.get('errore', ''))[:150]}\nLe altre piattaforme continuano")
            except Exception:
                pass


CADENZA_DAL = "2026-10-21 00:00"   # dal 21/10/2026 uno Short ogni 2 ore (orario.OGNI_ORE)
SPINTA_MIN_VIEWS = 100      # lo Short di ieri alla stessa ora sopra questa soglia = orario spinto da YouTube
VIDEO_DA_TENERE = 12        # con piu' video nuovi in coda si pubblicano comunque (non si accumulano)
GIORNI_RIUSO_FRASE = 14     # negli orari fermi si riusa una frase uscita almeno 14 giorni fa


def orario_spinto(state, slot, creds):
    """True se probabilmente YouTube spingera' lo Short di quest'ora (o se non si sa). Dati 19-20/10/2026: con uno Short
    ogni ora YouTube ne spinge ~10-14 al giorno, sempre nelle stesse ore (dalle 2 alle 11; dalle 12 all'1 restano a
    10-25 views): se lo Short di IERI a quest'ora e' stato spinto, lo sara' probabilmente anche questo."""
    if ENV("PROVA_ORARIO_FERMO") == "1":     # solo per le prove a vuoto
        return False
    t = ora_slot(slot)
    if t is None or DRY or not creds:
        return True
    ieri = f"{t - datetime.timedelta(days=1):%Y-%m-%d %H:%M}"
    if ieri < CADENZA_DAL:          # ieri c'era un'altra cadenza (uno ogni ora): non dice niente su oggi
        return True
    h = next((x for x in reversed(state["storico"]) if x.get("slot") == ieri), None)
    vid = ((h or {}).get("risultati") or {}).get("youtube", {}).get("id")
    if not vid:
        return True
    try:
        from googleapiclient.discovery import build
        it = build("youtube", "v3", credentials=creds, cache_discovery=False).videos().list(
            part="statistics", id=vid).execute().get("items", [])
        views = int(it[0]["statistics"].get("viewCount", 0)) if it else None
    except Exception as e:
        log("Views dello Short di ieri non lette (vado normale):", e)
        return True
    log(f"Short di ieri alle {ieri[-5:]}: {views} views -> orario {'spinto' if views is None or views >= SPINTA_MIN_VIEWS else 'FERMO'}")
    return views is None or views >= SPINTA_MIN_VIEWS


def scegli_formato(slot, state, frase, an, spinto=True):
    """Formato del reel: a caso con i pesi (FORMATI, aggiornati da report.py), mai due volte di fila lo stesso
    se si puo'. FORMATO=nome forza un formato (prove)."""
    if ENV("FORMATO"):
        return ENV("FORMATO")
    if an.get("momento"):            # video mandato con il suo titolo: il momento com'e'
        return "momento"
    if an.get("parlato"):            # video in cui parla: sempre con la sua voce e i sottotitoli
        return "parlato"
    if TUTTO_10S:                    # 29/10/2026: tutti da 10 s, a turno (mai lo stesso due volte di fila)
        scelte = [f for f in FORMATI_10 if f != state.get("formato_ultimo")] or list(FORMATI_10)
        return random.choice(scelte)
    if TUTTO_30S:                    # 26/10/2026: tutti da 30 s, i 3 formati a turno (mai lo stesso due volte di fila)
        scelte = [f for f in FORMATI_30 if f != state.get("formato_ultimo")] or list(FORMATI_30)
        return random.choice(scelte)
    if not spinto:                   # orario fermo: il formato piu' semplice (liste e montaggi restano per gli altri)
        return "frase"
    pesi = dict(FORMATI)
    try:
        dati = json.load(open(os.path.join(HERE, "pesi.json"), encoding="utf-8"))
        pesi.update(dati.get("formati", {}))
        for f, x in dati.get("esperimento_formati", {}).items():    # AGENTE (dal 25/10/2026): esperimento con
            if f in pesi:                                           # data di verifica, report.py non lo tocca
                pesi[f] = float(pesi[f]) * float(x)
        for f in dati.get("formati_spenti", []):    # bloccato da YouTube per diritti d'autore (report.py)
            pesi.pop(f, None)
    except Exception:
        pass
    ok = {"frase": True, "gancio": bool(overlay.dividi_frase(frase["gancio"])), "montaggio": True,
          "regole": lista_regole(slot, state) is not None, "ambiente": an.get("scena") == "palestra", "frase8": True,
          "broll1": True, "broll2": True, "broll3": True, "storia": lista_regole(slot, state) is not None}
    tre = (datetime.datetime.now() - datetime.timedelta(days=3)).isoformat()
    usati = {}
    for h in state.get("storico", []):
        if h.get("quando", "") >= tre:
            f = (h.get("montaggio") or {}).get("formato") or "frase"
            usati[f] = usati.get(f, 0) + 1
    # 25/10/2026: ESPLORAZIONE (Alessandro: "voglio capire il prima possibile quale format funziona"): un formato
    # provato poche volte negli ultimi 3 giorni pesa fino a 3 volte di piu'
    pesi = {f: max(float(w), 0.05) * (0.3 if f == state.get("formato_ultimo") else 1) * (1 + 2 / (1 + usati.get(f, 0)))
            for f, w in pesi.items() if ok.get(f)}
    return random.choices(list(pesi), weights=list(pesi.values()))[0] if pesi else "frase"


def clip_extra(drive, work, clip, n=2, giorno=None):
    """n clip dall'archivio (diverse da quella dell'orario), scaricate in locale: PRIMA quelle girate lo stesso
    giorno (es. la domenica delle castagne: un piccolo racconto della giornata), poi a caso."""
    out = []
    try:
        altre = [c for c in drive.lista_archivio() if (not clip or c["id"] != clip["id"]) and c.get("parlato") != "1"]
        random.shuffle(altre)
        altre.sort(key=lambda c: c.get("scena") == "palestra")    # 29/10/2026: prima la vita normale, poi la palestra
        if giorno:
            altre.sort(key=lambda c: 0 if str(c.get("registrato") or "")[:10] == giorno else 1)
        for i, c in enumerate(altre[:n]):
            p = os.path.join(work, f"extra_{i}{os.path.splitext(c['nome'])[1] or '.mov'}")
            drive.download(c["id"], p, folder="Archivio")
            out.append(p)
    except Exception as e:
        log("Clip extra non scaricate (uso solo il video dell'orario):", e)
    return out


def musiche_brano(music, n=3):
    """Fino a n pezzi da 5 s dello stesso brano (per i formati piu' lunghi di 5 s)."""
    if not music:
        return []
    base = re.sub(r"_\d+$", "", os.path.splitext(os.path.basename(music))[0])
    d = os.path.dirname(music)
    pezzi = sorted(os.path.join(d, f) for f in os.listdir(d) if re.fullmatch(re.escape(base) + r"_\d+\.m4a", f))
    return pezzi[:n] or [music]


MOMENTO_MAX = 30.0          # secondi (i suoi momenti piu' visti duravano 9-50 s; dal 26/10/2026 tutti i reel 30 s)
# 26/10/2026 (Alessandro): prova di 7 giorni, TUTTI i reel da 30 s che raccontano una storia (storie.json), formati a
# rotazione con e senza b-roll (formati_nuovi.py). Momento e parlato restano: sono i suoi video veri.
TUTTO_30S = False            # 29/10/2026: finita (visti al 35% contro il 90-100% dei video da 8-13 s)
FORMATI_30 = ("racconto", "racconto_broll", "racconto_lento")
# 29/10/2026 (Alessandro: "passiamo a 10 secondi", "cambiamo un po' il format"): TUTTI da 10 s, frase in due tempi,
# tre varianti a turno (formati_nuovi.py). Momento e parlato restano.
TUTTO_10S = True
FORMATI_10 = ("dieci", "dieci_due", "dieci_broll")


def monta_momento(an, src, out, music, serie, nome):
    """Reel MOMENTO: il video come l'ha girato lui (dall'inizio, fino a MOMENTO_MAX), il SUO titolo sopra e come
    titolo YouTube, il suono vero della ripresa. Con la famiglia: musica (mai voci di parenti) e al massimo 15 s."""
    import hashlib
    titolo = an["momento"]["titolo"]
    secondi, _ = overlay.probe(src)
    famiglia = an.get("compagnia") == "famiglia"
    durata = round(min(secondi, 15.0 if famiglia else MOMENTO_MAX), 2)
    info = overlay.make_video(src, titolo, out, music=music if famiglia else None, serie=serie,
                              colore=ENV("SENZA_COLORE") != "1", nome=nome, scena_rilevata=an.get("scena"),
                              formato={"nome": "momento", "inizio": 0.0, "durata": durata,
                                       "audio_originale": 0 if famiglia else 1.0})
    frase = {"id": "MOM-" + hashlib.md5(titolo.encode()).hexdigest()[:8], "tema": "momento", "gancio": titolo,
             "autore": "", "hashtag": ["#vitavera", "#momenti", "#italia"], "serie": serie}
    return frase, info


def monta_parlato(an, src, out, serie, nome):
    """Reel PARLATO: la sua voce (niente musica) con i sottotitoli; titolo = la prima frase che dice."""
    import hashlib
    import parlato
    parole = an["parlato"]["parole"]
    secondi, _ = overlay.probe(src)
    inizio, durata = parlato.taglio(parole, secondi)
    dentro = [w for w in parole if inizio <= w["s"] < inizio + durata]
    info = overlay.make_video(src, "", out, music=None, serie=serie, colore=ENV("SENZA_COLORE") != "1", nome=nome,
                              scena_rilevata=an.get("scena"),
                              formato={"nome": "parlato", "inizio": inizio, "durata": durata, "audio_originale": 1.0,
                                       "sottotitoli": parlato.blocchi(dentro)})
    t = parlato.testo(dentro)
    prima = re.split(r"(?<=[.!?])\s", t)[0][:90]
    frase = {"id": "PARL-" + hashlib.md5(t.encode()).hexdigest()[:8], "tema": "parlato", "gancio": prima or t[:90],
             "autore": "", "hashtag": ["#vitavera", "#mentalita", "#imprenditore"], "serie": serie}
    return frase, info


def monta_montaggio(frase, src, out, music, serie, drive, work, clip, giorno=None):
    clips = [src] + clip_extra(drive, work, clip, 2, giorno)
    info = overlay.make_montaggio(clips, frase["gancio"], out, musiche_brano(music, 2), serie)
    info["musica"] = os.path.basename(music) if music else None
    return info


def lista_regole(slot, state):
    """La prossima lista per il formato REGOLE (None se finite o spento con SENZA_REGOLE=1)."""
    if ENV("SENZA_REGOLE") == "1":
        return None
    try:
        liste = json.load(open(os.path.join(HERE, "liste.json"), encoding="utf-8"))
    except Exception:
        return None
    libere = [l for l in liste if l["id"] not in state.get("liste_usate", [])]
    tema = lambda l: TRADIMENTO.search(l.get("titolo", "") + " " + " ".join(l.get("righe", [])))
    if random.random() >= TRADIMENTO_QUOTA:     # 25/10/2026: il tradimento solo di rado
        libere = [l for l in libere if not tema(l)] or libere
    return libere[0] if libere else None


def monta_nuovo(formato, frase, src, out, music, serie, drive, work, clip, slot, state):
    """Formati nuovi (formati_nuovi.py): b-roll da 1/2/3 s e storia a schermate. Restituisce (frase, info)."""
    import formati_nuovi
    clips = [src] + clip_extra(drive, work, clip, 3)
    if formato == "storia":
        lista = lista_regole(slot, state)
        info = formati_nuovi.make_storia(clips, lista["titolo"], lista["righe"], out, musiche_brano(music, 6), serie)
        frase = {"id": lista["id"], "tema": "regole", "gancio": lista["titolo"], "righe": lista["righe"], "autore": "",
                 "hashtag": ["#storia", "#mentalita", "#motivazione"], "serie": serie}
        return frase, info
    return frase, formati_nuovi.make_broll(formato, clips, frase["gancio"], out, musiche_brano(music, 3), serie)


def scegli_storia(state):
    """Racconto da storie.json non ancora uscito: si sceglie a caso tra i 3 con il punteggio piu' alto."""
    dati = json.load(open(os.path.join(HERE, "storie.json"), encoding="utf-8"))["storie"]
    usate = {h.get("frase") for h in state.get("storico", [])}
    libere = [x for x in dati if x["id"] not in usate and not TRADIMENTO.search(" ".join(x["righe"]))
              and not DONNE.search(" ".join(x["righe"]))]
    if not libere:          # finite: si riusa quella uscita da piu' tempo (salute/agente avvisano di scriverne altre)
        ultime = {h.get("frase"): h.get("quando", "") for h in state.get("storico", [])}
        libere = sorted(dati, key=lambda x: ultime.get(x["id"], ""))[:3]
        log("Racconti nuovi finiti: ne riuso uno vecchio. Aggiungerne altri a storie.json!")
    libere.sort(key=lambda x: -x.get("punteggio", 50))
    return random.choice(libere[:3])


def monta_dieci(formato, frase, src, out, music, serie, drive, work, clip):
    """Reel da 10 s (formati_nuovi.make_dieci). 'dieci' usa solo il video dell'orario: se e' piu' corto di 10 s
    si passa a 'dieci_due' (video dell'orario + una clip). Le clip in piu' sono di vita normale se ci sono."""
    import formati_nuovi
    if formato == "dieci" and overlay.probe(src)[0] < 10.5:
        formato = "dieci_due"
    clips = [src] + (clip_extra(drive, work, clip, 3 if formato == "dieci_broll" else 1) if formato != "dieci" else [])
    return formati_nuovi.make_dieci(formato, clips, frase["gancio"], out, musiche_brano(music, 3), serie)


def monta_racconto(formato, src, out, music, serie, drive, work, clip, state):
    """Reel da 30 s che racconta una storia (6 righe, una ogni 5 s). racconto_lento = senza b-roll: solo il video
    dell'orario, se e' abbastanza lungo (altrimenti racconto con b-roll). Restituisce (frase, info)."""
    import formati_nuovi
    storia = scegli_storia(state)
    if formato == "racconto_lento" and overlay.probe(src)[0] < 20:
        formato = "racconto"
    clips = [src] if formato == "racconto_lento" else [src] + clip_extra(drive, work, clip, 5)
    info = formati_nuovi.make_racconto(formato, clips, storia["righe"], out, musiche_brano(music, 7), serie)
    frase = {"id": storia["id"], "tema": "storia", "gancio": storia["righe"][0], "autore": "",
             "hashtag": ["#storia", "#mentalita", "#motivazione"], "serie": serie, "testo_completo": storia["righe"]}
    return frase, info


def monta_regole(lista, src, out, music, serie, drive, work, clip):
    """Reel REGOLE con il video dell'orario + 2 clip dell'archivio. Restituisce (frase, info)."""
    clips = [src] + clip_extra(drive, work, clip, 2)
    info = overlay.make_regole(clips, lista["titolo"], lista["righe"], out, musiche_brano(music, 3), serie)
    info["musica"] = os.path.basename(music) if music else None
    frase = {"id": lista["id"], "tema": "regole", "gancio": lista["titolo"], "righe": lista["righe"], "autore": "",
             "hashtag": ["#regole", "#mentalita", "#motivazione"], "serie": serie}
    return frase, info


def etichetta_serie(slot):
    """'GIORNO 294 / 365': il giorno dell'ANNO (dal 21/10/2026, scelta di Alessandro: si insiste sulla fine
    dell'anno; prima si contava da SERIE_INIZIO). Data dello slot (manuale: oggi)."""
    giorno = (ora_slot(slot) or ora_roma()).date()
    totale = 366 if calendar.isleap(giorno.year) else 365
    return f"GIORNO {giorno.timetuple().tm_yday} / {totale}"


def ora_slot(slot):
    """'2026-10-16 09:00' -> datetime (ora di Roma). None per le esecuzioni manuali."""
    from zoneinfo import ZoneInfo
    try:
        return datetime.datetime.strptime(slot, "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo("Europe/Rome"))
    except (TypeError, ValueError):
        return None


def log(*a):
    print(datetime.datetime.now().strftime("%H:%M:%S"), *a, flush=True)


CREDENZIALI = {"instagram": "META_PAGE_TOKEN", "facebook": "META_PAGE_TOKEN",
               "youtube": "GOOGLE_REFRESH_TOKEN", "tiktok": "TIKTOK_REFRESH_TOKEN"}


def attive():
    """Piattaforme da usare: non saltate a mano (SALTA_X=1) e con le credenziali gia' collegate."""
    return [p for p in PLATFORMS
            if ENV(f"SALTA_{p.upper()}") != "1" and (DRY or ENV(CREDENZIALI[p]))]


# ------------------------------------------------------------------ Google (Drive + YouTube)
def google_creds():
    from google.oauth2.credentials import Credentials
    return Credentials(None, refresh_token=ENV("GOOGLE_REFRESH_TOKEN"),
                       client_id=ENV("GOOGLE_CLIENT_ID"), client_secret=ENV("GOOGLE_CLIENT_SECRET"),
                       token_uri="https://oauth2.googleapis.com/token")


class Drive:
    """Accesso a Drive. In DRY_RUN usa una cartella locale (DRY_DIR) al posto di Drive."""

    def __init__(self, creds):
        self.local = ENV("DRY_DIR") if DRY else None
        self.creds = creds
        self.riconnetti()

    def riconnetti(self):
        """Connessione nuova a Drive: dopo l'attesa dell'ora esatta (fino a 50') quella vecchia e' chiusa
        (18/10/2026: SSLEOFError salvando in Pronti, stato non salvato)."""
        if not self.local:
            from googleapiclient.discovery import build
            self.api = build("drive", "v3", credentials=self.creds, cache_discovery=False)

    def list_videos(self):
        """Tutti i video in coda: [{id, name, createdTime}], dal piu' vecchio."""
        if self.local:
            d = os.path.join(self.local, "Da pubblicare")
            vids = sorted((f for f in os.listdir(d) if f.lower().endswith((".mov", ".mp4", ".m4v"))),
                          key=lambda f: os.path.getmtime(os.path.join(d, f)))
            import hashlib
            out = [{"id": v, "name": v, "createdTime": datetime.datetime.fromtimestamp(
                os.path.getmtime(os.path.join(d, v)), datetime.timezone.utc).isoformat(),
                "md5Checksum": hashlib.md5(open(os.path.join(d, v), "rb").read()).hexdigest()} for v in vids]
            for v in out:       # prove: description/appProperties da "<video>.meta.json" (es. un MOMENTO da Telegram)
                extra = os.path.join(d, v["id"] + ".meta.json")
                if os.path.exists(extra):
                    v.update(json.load(open(extra, encoding="utf-8")))
            return out
        q = (f"'{ENV('DRIVE_FOLDER_DA_PUBBLICARE')}' in parents and trashed = false "
             "and mimeType contains 'video/'")
        res = self.api.files().list(q=q, orderBy="createdTime", pageSize=100,
                                    fields="files(id,name,createdTime,md5Checksum,description,appProperties)").execute()
        return res.get("files", [])

    def download(self, file_id, dest, folder="Da pubblicare"):
        if self.local:
            shutil.copy(os.path.join(self.local, folder, file_id), dest)
            return
        from googleapiclient.http import MediaIoBaseDownload
        with io.FileIO(dest, "wb") as fh:
            dl = MediaIoBaseDownload(fh, self.api.files().get_media(fileId=file_id), chunksize=50 * 1024 * 1024)
            done = False
            while not done:
                _, done = dl.next_chunk()

    def testo_tiktok(self, testo, nome_video):
        """Aggiunge in cima al file 'TIKTOK - testi da incollare.txt' (cartella Pronti) la frase del reel appena inviato."""
        titolo = "TIKTOK - testi da incollare.txt"
        riga = f"{datetime.datetime.now():%d/%m %H:%M}  |  {nome_video}\n{testo}\n\n{'-' * 40}\n\n"
        if self.local:
            path = os.path.join(self.local, "Pronti", titolo)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            vecchio = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
            open(path, "w", encoding="utf-8").write(riga + vecchio)
            return
        from googleapiclient.http import MediaIoBaseUpload
        folder = ENV("DRIVE_FOLDER_PRONTI")
        q = f"'{folder}' in parents and trashed = false and name = '{titolo}'"
        found = self.api.files().list(q=q, fields="files(id)").execute().get("files", [])
        vecchio = self.api.files().get_media(fileId=found[0]["id"]).execute().decode("utf-8") if found else ""
        media = MediaIoBaseUpload(io.BytesIO((riga + vecchio)[:200000].encode("utf-8")), mimetype="text/plain")
        if found:
            self.api.files().update(fileId=found[0]["id"], media_body=media).execute()
        else:
            self.api.files().create(body={"name": titolo, "parents": [folder]}, media_body=media).execute()

    def salva_per_dopo(self, path, nome, testo, cartella_nome=CARTELLA_DOPO):
        """Reel pronto da pubblicare a mano (Instagram, TikTok): video + testo da incollare in cartella_nome."""
        riga = f"{ora_roma():%d/%m %H:%M}  |  {nome}\n{testo}\n\n{'-' * 40}\n\n"
        titolo = "TESTI da incollare.txt"
        if self.local:
            d = os.path.join(self.local, cartella_nome)
            os.makedirs(d, exist_ok=True)
            shutil.copy(path, os.path.join(d, nome))
            t = os.path.join(d, titolo)
            vecchio = open(t, encoding="utf-8").read() if os.path.exists(t) else ""
            open(t, "w", encoding="utf-8").write(riga + vecchio)
            return nome
        from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload
        folder = self.cartella(cartella_nome)
        fid = self.api.files().create(body={"name": nome, "parents": [folder]},
                                      media_body=MediaFileUpload(path, mimetype="video/mp4"), fields="id").execute()["id"]
        q = f"'{folder}' in parents and trashed = false and name = '{titolo}'"
        found = self.api.files().list(q=q, fields="files(id)").execute().get("files", [])
        vecchio = self.api.files().get_media(fileId=found[0]["id"]).execute().decode("utf-8") if found else ""
        media = MediaIoBaseUpload(io.BytesIO((riga + vecchio)[:200000].encode("utf-8")), mimetype="text/plain")
        if found:
            self.api.files().update(fileId=found[0]["id"], media_body=media).execute()
        else:
            self.api.files().create(body={"name": titolo, "parents": [folder]}, media_body=media).execute()
        return fid

    def salva_tiktok(self, path, nome, testo, slot, voce):
        """Versione per TikTok Studio: video in CARTELLA_TIKTOK con la didascalia nella descrizione del file e
        l'orario in appProperties (lo legge tiktok_prepara.py sul PC per programmarla alla stessa ora)."""
        props = {"tiktok_slot": slot, "tiktok_voce": "1" if voce else "0"}
        if self.local:
            d = os.path.join(self.local, CARTELLA_TIKTOK)
            os.makedirs(d, exist_ok=True)
            shutil.copy(path, os.path.join(d, nome))
            json.dump(dict(props, testo=testo), open(os.path.join(d, nome + ".json"), "w", encoding="utf-8"),
                      ensure_ascii=False)
            return nome
        from googleapiclient.http import MediaFileUpload
        return self.api.files().create(body={"name": nome, "parents": [self.cartella(CARTELLA_TIKTOK)],
                                             "description": testo, "appProperties": props},
                                       media_body=MediaFileUpload(path, mimetype="video/mp4"), fields="id").execute()["id"]

    def cartella(self, nome):
        """Id della cartella 'nome' accanto a 'Da pubblicare' (la crea se manca)."""
        padre = self.api.files().get(fileId=ENV("DRIVE_FOLDER_DA_PUBBLICARE"), fields="parents").execute()["parents"][0]
        q = (f"'{padre}' in parents and name = '{nome}' and trashed = false "
             "and mimeType = 'application/vnd.google-apps.folder'")
        found = self.api.files().list(q=q, fields="files(id)").execute().get("files", [])
        return found[0]["id"] if found else self.api.files().create(
            body={"name": nome, "parents": [padre], "mimeType": "application/vnd.google-apps.folder"},
            fields="id").execute()["id"]

    def carica_archivio(self, path, nome, meta):
        """Salva la clip (qualita' originale) nella cartella Archivio, con scena/fascia/ora nelle proprieta' del file
        (cosi' l'elenco dell'archivio vive su Drive e non serve tenerlo in stato.json). Restituisce l'id."""
        if os.path.getsize(path) < 200_000:
            raise RuntimeError(f"clip d'archivio troppo piccola ({os.path.getsize(path)} byte): non caricata")
        meta = {k: str(v) for k, v in meta.items() if v not in (None, "")}
        if self.local:
            d = os.path.join(self.local, "Archivio")
            os.makedirs(d, exist_ok=True)
            shutil.copy(path, os.path.join(d, nome))
            json.dump(meta, open(os.path.join(d, nome + ".json"), "w"))
            return nome
        from googleapiclient.http import MediaFileUpload
        return self.api.files().create(body={"name": nome, "parents": [self.cartella("Archivio")], "appProperties": meta},
                                       media_body=MediaFileUpload(path, mimetype="video/quicktime"),
                                       fields="id").execute()["id"]

    def sposta_in_archivio(self, file_id, nome, meta):
        """L'originale passa da 'Da pubblicare' all'Archivio (stesso file, niente copia): restano scena/fascia/ora
        nelle proprieta'. Restituisce l'id (uguale a quello di prima)."""
        meta = {k: str(v) for k, v in meta.items() if v not in (None, "")}
        if self.local:
            d = os.path.join(self.local, "Archivio")
            os.makedirs(d, exist_ok=True)
            shutil.move(os.path.join(self.local, "Da pubblicare", file_id), os.path.join(d, nome))
            json.dump(meta, open(os.path.join(d, nome + ".json"), "w"))
            return nome
        self.api.files().update(fileId=file_id, addParents=self.cartella("Archivio"),
                                removeParents=ENV("DRIVE_FOLDER_DA_PUBBLICARE"), body={"appProperties": meta},
                                fields="id").execute()
        return file_id

    def lista_archivio(self):
        """Clip dell'archivio: [{id, nome, scena, fascia, compagnia, registrato}]."""
        if self.local:
            d = os.path.join(self.local, "Archivio")
            if not os.path.isdir(d):
                return []
            return [dict(json.load(open(os.path.join(d, f + ".json"))), id=f, nome=f)
                    for f in sorted(os.listdir(d)) if not f.endswith(".json") and os.path.exists(os.path.join(d, f + ".json"))]
        q = f"'{self.cartella('Archivio')}' in parents and trashed = false and mimeType contains 'video/'"
        out, token = [], None
        while True:
            res = self.api.files().list(q=q, fields="nextPageToken,files(id,name,appProperties)", pageSize=500,
                                        pageToken=token).execute()
            out += [dict(f.get("appProperties") or {}, id=f["id"], nome=f["name"]) for f in res.get("files", [])]
            token = res.get("nextPageToken")
            if not token:
                return out

    def libera_spazio(self, usi):
        """25/10/2026: Drive 100 GB. Se lo spazio libero scende sotto DRIVE_LIBERO_MIN_GB, le clip d'archivio meno
        utili (piu' usate e usate da piu' tempo) passano nella cartella "Archivio - verso il PC": sposta_su_pc.py (sul
        PC, ogni ora) le scarica intere in 4K e solo dopo le toglie da Drive. Si tengono almeno ARCHIVIO_MIN clip.
        Restituisce [(nome, GB)] delle clip spostate."""
        if self.local:
            return []
        q = self.api.about().get(fields="storageQuota").execute()["storageQuota"]
        libero = (int(q.get("limit", 0)) - int(q.get("usage", 0))) / 1024 ** 3
        if not q.get("limit") or libero >= DRIVE_LIBERO_MIN_GB:
            return []
        arch = []
        q2 = f"'{self.cartella('Archivio')}' in parents and trashed = false and mimeType contains 'video/'"
        token = None
        while True:
            res = self.api.files().list(q=q2, fields="nextPageToken,files(id,name,size,appProperties)", pageSize=500,
                                        pageToken=token).execute()
            arch += res.get("files", [])
            token = res.get("nextPageToken")
            if not token:
                break
        recente = (datetime.date.today() - datetime.timedelta(days=2)).isoformat()
        candidati = [f for f in arch if usi.get(f["id"], {}).get("ultimo", "") < recente]
        candidati.sort(key=lambda f: (-usi.get(f["id"], {}).get("fallimenti", 0), -usi.get(f["id"], {}).get("usi", 0),
                                      usi.get(f["id"], {}).get("ultimo", "")))
        verso_pc, spostati = self.cartella(VERSO_PC), []
        for f in candidati:
            if libero >= DRIVE_LIBERO_OBIETTIVO_GB or len(arch) - len(spostati) <= ARCHIVIO_MIN:
                break
            self.api.files().update(fileId=f["id"], addParents=verso_pc, removeParents=self.cartella("Archivio"),
                                    fields="id").execute()
            gb = int(f.get("size", 0)) / 1024 ** 3
            libero += gb
            spostati.append((f["name"], round(gb, 2)))
        return spostati

    def esiste(self, file_id):
        if self.local:
            return os.path.exists(os.path.join(self.local, "Archivio", file_id))
        try:
            return not self.api.files().get(fileId=file_id, fields="trashed").execute().get("trashed")
        except Exception:
            return False

    def testo_mie_citazioni(self):
        """Testo del Google Doc 'Le mie citazioni' (cartella Reel Alessandro). None se non si trova."""
        if self.local:
            p = os.path.join(self.local, DOC_MIE + ".txt")
            return open(p, encoding="utf-8").read() if os.path.exists(p) else None
        return mie_citazioni.leggi(self.api, ENV("DRIVE_FOLDER_DA_PUBBLICARE"))

    def cestino(self, file_id):
        """Mette il video nel Cestino di Drive (recuperabile per 30 giorni, poi Google lo elimina da solo)."""
        if self.local:
            os.remove(os.path.join(self.local, "Da pubblicare", file_id))
            return
        self.api.files().update(fileId=file_id, body={"trashed": True}, fields="id").execute()

    def sposta_in_sottocartella(self, file_id, nome):
        """Sposta un video da 'Da pubblicare' a una cartella accanto (creata se manca)."""
        if self.local:
            dest = os.path.join(self.local, nome)
            os.makedirs(dest, exist_ok=True)
            shutil.move(os.path.join(self.local, "Da pubblicare", file_id), os.path.join(dest, file_id))
            return
        origine = ENV("DRIVE_FOLDER_DA_PUBBLICARE")
        padre = self.api.files().get(fileId=origine, fields="parents").execute()["parents"][0]
        nome_q = nome.replace("'", "\\'")
        q = (f"'{padre}' in parents and name = '{nome_q}' and trashed = false "
             "and mimeType = 'application/vnd.google-apps.folder'")
        found = self.api.files().list(q=q, fields="files(id)").execute().get("files", [])
        cartella = found[0]["id"] if found else self.api.files().create(
            body={"name": nome, "parents": [padre], "mimeType": "application/vnd.google-apps.folder"},
            fields="id").execute()["id"]
        self.api.files().update(fileId=file_id, addParents=cartella, removeParents=origine, fields="id").execute()

    def archive(self, file_id, final_path, final_name, carica=True):
        """Dopo la pubblicazione: l'originale (se c'e' ancora in coda) va nel Cestino e, solo se serve riprovare
        qualche piattaforma (carica=True), il reel montato va in Pronti per GIORNI_PRONTI giorni.
        Restituisce l'id del montato (None se non caricato)."""
        if self.local:
            os.makedirs(os.path.join(self.local, "Pronti"), exist_ok=True)
            if file_id:
                os.remove(os.path.join(self.local, "Da pubblicare", file_id))
            if carica:
                shutil.copy(final_path, os.path.join(self.local, "Pronti", final_name))
            return final_name if carica else None
        from googleapiclient.http import MediaFileUpload
        if file_id:              # None = originale gia' spostato nell'archivio (o reel da una clip d'archivio)
            self.api.files().update(fileId=file_id, body={"trashed": True}, fields="id").execute()
        if not carica:
            return None
        f = self.api.files().create(body={"name": final_name, "parents": [ENV("DRIVE_FOLDER_PRONTI")]},
                                    media_body=MediaFileUpload(final_path, mimetype="video/mp4"),
                                    fields="id").execute()
        return f["id"]

    def pulisci_pronti(self, giorni):
        """Mette nel Cestino i reel montati piu' vecchi di `giorni` (e gli eventuali vecchi originali in Pubblicati)."""
        limite = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=giorni)
        if self.local:
            return 0
        n = 0
        cartelle_dopo = []
        for nome_c in (CARTELLA_DOPO, CARTELLA_TIKTOK):
            try:
                cartelle_dopo.append((self.cartella(nome_c),
                                      datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=GIORNI_DOPO)))
            except Exception:
                pass
        for cartella, soglia in ((ENV("DRIVE_FOLDER_PRONTI"), limite),
                                 (ENV("DRIVE_FOLDER_PUBBLICATI"), datetime.datetime.now(datetime.timezone.utc)),
                                 *cartelle_dopo):
            if not cartella:
                continue
            q = f"'{cartella}' in parents and trashed = false and mimeType contains 'video/'"
            for f in self.api.files().list(q=q, fields="files(id,createdTime)", pageSize=200).execute().get("files", []):
                if datetime.datetime.fromisoformat(f["createdTime"].replace("Z", "+00:00")) < soglia:
                    self.api.files().update(fileId=f["id"], body={"trashed": True}, fields="id").execute()
                    n += 1
        return n


def youtube_upload(creds, path, cap, publish_at=None):
    """publish_at (datetime): caricato subito come privato e PROGRAMMATO: YouTube lo pubblica all'ora esatta."""
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    title = cap["gancio"].strip()
    if len(title) > 92:     # limite YouTube 100 caratteri con " #shorts": taglio a parola intera + "…"
        title = title[:90].rsplit(" ", 1)[0].rstrip(",;:") + "…"   # (mai solo la prima frase: cambierebbe il senso)
    privacy = ENV("YOUTUBE_PRIVACY") or "public"
    momento = cap.get("tema") == "momento"
    descr = (cap["gancio"].strip().strip('"“”') + ("\n\n#shorts " + " ".join(cap.get("hashtag") or []) if momento else
             "\n\n#shorts #motivazione #mentalita #disciplina #crescitapersonale #frasimotivazionali #successo"))
    if cap.get("righe"):    # formato REGOLE: le regole in descrizione
        descr = "\n".join(f"{i}. {r}" for i, r in enumerate(cap["righe"], 1)) + "\n\n" + descr
    if serie_testo(cap):    # la serie in prima riga + invito a seguire il viaggio (il personaggio, non solo le frasi)
        descr = f"{serie_testo(cap)} - giorno dopo giorno fino alla fine dell'anno, iscriviti per vedere dove arrivo.\n\n" + descr
    body = {"snippet": {"title": title + " #shorts", "description": descr, "categoryId": "22",
                        "tags": (["vita vera", "momenti", "oggi", "italia", "shorts"] if momento else
                                 ["motivazione", "mentalità", "disciplina", "frasi motivazionali", "crescita personale",
                                  "successo", "obiettivi", "famiglia", "mindset", "shorts"]),   # 29/10: niente palestra
                        "defaultLanguage": "it", "defaultAudioLanguage": "it"},
            "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}}
    if publish_at and privacy == "public":
        body["status"].update(privacyStatus="private",
                              publishAt=publish_at.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(path, mimetype="video/mp4", resumable=True))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    vid = resp["id"]
    if PRIMO_COMMENTO and cap.get("commento") and privacy == "public":
        try:
            yt.commentThreads().insert(part="snippet", body={"snippet": {"videoId": vid, "topLevelComment": {
                "snippet": {"textOriginal": cap["commento"]}}}}).execute()
        except Exception as e:
            log("youtube: commento non pubblicato:", e)
    return vid


PLAYLIST_TUTTE = "Frasi motivazionali"
PLAYLIST_SCENA = {"palestra": "Mentalità da palestra", "macchina": "Pensieri in macchina",
                  "lavoro": "Lavoro e disciplina", "pacchi": "Lavoro e disciplina", "specchio": "Lavoro e disciplina",
                  "casa": "Lavoro e disciplina", "cibo": "Disciplina ogni giorno", "uscita": "Vita e persone"}


def aggiungi_playlist(creds, video_id, scena, state):
    """Ogni Short in 2 playlist pubbliche (tutte + quella della scena): YouTube fa guardare piu' video di fila."""
    from googleapiclient.discovery import build
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    ids = state.setdefault("playlist", {})
    for titolo in dict.fromkeys([PLAYLIST_TUTTE, PLAYLIST_SCENA.get(scena)]):
        if not titolo:
            continue
        if titolo not in ids:
            pl = yt.playlists().insert(part="snippet,status", body={
                "snippet": {"title": titolo, "description": "Frasi motivazionali da 5 secondi: mentalità, disciplina, "
                                                            "lavoro. Una nuova ogni giorno alle 9, 13, 17 e 21.",
                            "defaultLanguage": "it"},
                "status": {"privacyStatus": "public"}}).execute()
            ids[titolo] = pl["id"]
            log(f"Playlist creata: {titolo}")
        yt.playlistItems().insert(part="snippet", body={"snippet": {
            "playlistId": ids[titolo], "position": 0,
            "resourceId": {"kind": "youtube#video", "videoId": video_id}}}).execute()


# ------------------------------------------------------------------ Meta (Instagram + Facebook)
def _rupload(url, token, path):
    with open(path, "rb") as f:
        r = requests.post(url, headers={"Authorization": f"OAuth {token}", "offset": "0",
                                        "file_size": str(os.path.getsize(path))}, data=f, timeout=600)
    return r.json()


def _ig_carica_e_pubblica(path, dati):
    """Crea il contenitore Instagram (reel o storia), carica il video, aspetta l'elaborazione e pubblica."""
    token, ig = ENV("META_PAGE_TOKEN"), ENV("IG_USER_ID")
    r = requests.post(f"{GRAPH}/{ig}/media", data={**dati, "upload_type": "resumable", "access_token": token}).json()
    if "id" not in r:
        raise RuntimeError(r)
    cid = r["id"]
    up = _rupload(r.get("uri", f"https://rupload.facebook.com/ig-api-upload/v23.0/{cid}"), token, path)
    if up.get("success") is False or "error" in up:
        raise RuntimeError(up)
    for _ in range(60):                      # attende l'elaborazione (max ~10 minuti)
        st = requests.get(f"{GRAPH}/{cid}", params={"fields": "status_code,status", "access_token": token}).json()
        if st.get("status_code") == "FINISHED":
            break
        if st.get("status_code") == "ERROR":
            raise RuntimeError(st)
        time.sleep(10)
    pub = requests.post(f"{GRAPH}/{ig}/media_publish", data={"creation_id": cid, "access_token": token}).json()
    if "id" not in pub:
        raise RuntimeError(pub)
    return pub["id"]


def instagram_storia(path):
    """Lo stesso reel anche nelle Storie di Instagram: piu' persone lo vedono."""
    return _ig_carica_e_pubblica(path, {"media_type": "STORIES"})


# Instagram con MUSICA NATIVA (16/10/2026): l'API audio di Meta (/ig_audio, Graph v25+) da' i brani di Instagram
# autorizzati per le app; si carica il reel SENZA musica e si attacca il brano scelto (audio_configuration).
GRAPH_AUDIO = "https://graph.facebook.com/v25.0"
IG_RICERCHE = {"palestra": ["motivational", "emotional", "cinematic"], "macchina": ["drive", "phonk", "night drive"],
               "lavoro": ["motivational", "epic", "hustle"], "pacchi": ["motivational", "hustle"],
               "specchio": ["motivational", "phonk"], "casa": ["motivational", "epic"],
               "cibo": ["motivational", "epic"], "uscita": ["epic", "motivational"]}
IG_DA_EVITARE = re.compile(r"love|amore|romantic|lullaby|sleep|relax|432hz|christmas|natale|baby|happy|domenica",
                           re.I)


def scegli_audio_instagram(scena, recenti=()):
    """(audio_id, titolo) di un brano Instagram motivazionale per la scena, evitando i recenti. None se nessuno."""
    token, ig = ENV("META_PAGE_TOKEN"), ENV("IG_USER_ID")
    ricerche = list(IG_RICERCHE.get(scena, ["motivational", "phonk", "epic"]))
    random.shuffle(ricerche)
    # 26/10/2026: prima i brani di tendenza (richiesta di Alessandro); 29/10: "suoni di tendenza piu' forti" ->
    # prima le ricerche dei brani piu' usati sui reel, a caso tra i primi 3 (non 8)
    tendenza = ["trending", "viral", "tiktok viral", "top hits", "trending italia"]
    random.shuffle(tendenza)
    ricerche = tendenza[:3] + ricerche
    for q in ricerche:
        r = requests.get(f"{GRAPH_AUDIO}/ig_audio", params={"audio_type": "music", "search_query": q, "user_id": ig,
                                                             "access_token": token}, timeout=30).json()
        brani = [a for a in r.get("audio", []) if a.get("audio_id") and not IG_DA_EVITARE.search(
                 f"{a.get('title', '')} {a.get('display_artist', '')}") and a["audio_id"] not in recenti]
        if brani:
            a = random.choice(brani[:3] if q in tendenza else brani[:8])
            return a["audio_id"], f"{a.get('title')} - {a.get('display_artist')}"
    return None


def instagram_upload(path, cap, audio_id=None):
    """audio_id: brano nativo di Instagram (allora path e' il video SENZA musica)."""
    token, ig = ENV("META_PAGE_TOKEN"), ENV("IG_USER_ID")
    dati = {"media_type": "REELS", "caption": testo_breve(cap), "share_to_feed": "true"}
    if audio_id:
        dati["audio_configuration"] = json.dumps({"audio_id": audio_id, "audio_volume": 100, "video_volume": 0})
    if cap.get("copertina_ms") is not None:
        dati["thumb_offset"] = str(cap["copertina_ms"])
    r = requests.post(f"{GRAPH_AUDIO if audio_id else GRAPH}/{ig}/media", data={**dati, "upload_type": "resumable",
                                                                            "access_token": token}).json()
    if "id" not in r:
        raise RuntimeError(r)
    cid = r["id"]
    up = _rupload(r.get("uri", f"https://rupload.facebook.com/ig-api-upload/v23.0/{cid}"), token, path)
    if up.get("success") is False or "error" in up:
        raise RuntimeError(up)
    for _ in range(60):                      # attende l'elaborazione (max ~10 minuti)
        st = requests.get(f"{GRAPH}/{cid}", params={"fields": "status_code,status", "access_token": token}).json()
        if st.get("status_code") == "FINISHED":
            break
        if st.get("status_code") == "ERROR":
            raise RuntimeError(st)
        time.sleep(10)
    pub = requests.post(f"{GRAPH}/{ig}/media_publish", data={"creation_id": cid, "access_token": token}).json()
    if "id" not in pub:
        raise RuntimeError(pub)
    if PRIMO_COMMENTO and cap.get("commento"):
        c = requests.post(f"{GRAPH}/{pub['id']}/comments", data={"message": cap["commento"], "access_token": token}).json()
        if "id" not in c:
            log("instagram: commento non pubblicato:", c)
    return pub["id"]


def facebook_upload(path, cap):
    token, page = ENV("META_PAGE_TOKEN"), ENV("FB_PAGE_ID")
    start = requests.post(f"{GRAPH}/{page}/video_reels", data={"upload_phase": "start", "access_token": token}).json()
    vid = start.get("video_id")
    if not vid:
        raise RuntimeError(start)
    up = _rupload(start.get("upload_url", f"https://rupload.facebook.com/video-upload/v23.0/{vid}"), token, path)
    if not up.get("success"):
        raise RuntimeError(up)
    fin = requests.post(f"{GRAPH}/{page}/video_reels",
                        data={"upload_phase": "finish", "video_id": vid, "video_state": "PUBLISHED",
                              "description": testo_breve(cap), "access_token": token}).json()
    if not fin.get("success"):
        raise RuntimeError(fin)
    if PRIMO_COMMENTO and cap.get("commento"):
        for _ in range(12):                  # il reel deve finire l'elaborazione prima di accettare commenti
            c = requests.post(f"{GRAPH}/{vid}/comments", data={"message": cap["commento"], "access_token": token}).json()
            if "id" in c:
                break
            time.sleep(15)
        else:
            log("facebook: commento non pubblicato:", c)
    return vid


# ------------------------------------------------------------------ Telegram (TikTok a mano)
def manda_tiktok_della_giornata(state, drive, work, muto, slot, salva):
    """Alle 21: tutti i video TikTok del giorno su Telegram, uno dopo l'altro (al massimo gli ultimi 6)."""
    import avvisi
    coda = state.get("tiktok_coda", [])[-6:]
    avvisi.manda(f"TIKTOK DI OGGI\n{len(coda)} video da pubblicare stasera\nPuoi anche programmarli nell'app TikTok")
    inviati = []
    for i, item in enumerate(coda, 1):
        try:
            if item.get("slot") == slot and muto:
                path = muto
            else:
                path = os.path.join(work, f"tiktok_{i}.mp4")
                drive.download(item["id"], path, folder=CARTELLA_TIKTOK)
            manda_telegram(path, item["testo"], n=i, tot=len(coda), parlato=item.get("parlato", False))
            inviati.append(item)
        except Exception as e:
            log("TikTok su Telegram non riuscito per un video:", e)
    state["tiktok_coda"] = [x for x in state.get("tiktok_coda", []) if x not in inviati]
    log(f"TikTok: {len(inviati)} video della giornata mandati su Telegram")
    salva()


def manda_telegram(path, testo, slot=None, n=None, tot=None, parlato=False):
    """Manda ad Alessandro il video per TikTok (senza musica) e, sotto, il testo: toccandolo si copia.
    n/tot: invio serale di tutti i TikTok del giorno ("TIKTOK 2 DI 4")."""
    import html
    base = f"https://api.telegram.org/bot{ENV('TELEGRAM_BOT_TOKEN')}"
    if n:
        titolo = f"TIKTOK {n} DI {tot}\n"
    else:
        titolo = (f"REEL DELLE {slot.split()[-1]}" if slot and ":" in slot else "NUOVO REEL") + " PER TIKTOK\n"
    suono = ("2. C'e' la tua voce: se aggiungi un suono di tendenza, mettilo al volume piu' basso\n" if parlato
             else "2. Aggiungi un suono di tendenza\n")
    didascalia = titolo + "Pubblicalo o programmalo:\n1. Salva il video\n" + suono + "3. Incolla il testo qui sotto"
    with open(path, "rb") as f:
        # width/height: senza, Telegram mostra il video verticale come un quadrato con le bande nere
        r = requests.post(f"{base}/sendVideo", data={"chat_id": ENV("TELEGRAM_CHAT_ID"), "supports_streaming": "true",
                                                     "width": 1080, "height": 1920, "caption": didascalia},
                          files={"video": ("reel.mp4", f, "video/mp4")}, timeout=120).json()
    if not r.get("ok"):
        raise RuntimeError(r)
    r = requests.post(f"{base}/sendMessage", data={"chat_id": ENV("TELEGRAM_CHAT_ID"), "parse_mode": "HTML",
                                                   "text": f"<code>{html.escape(testo)}</code>"}, timeout=60).json()
    if not r.get("ok"):
        raise RuntimeError(r)


# ------------------------------------------------------------------ TikTok
def tiktok_token():
    r = requests.post("https://open.tiktokapis.com/v2/oauth/token/",
                      data={"client_key": ENV("TIKTOK_CLIENT_KEY"), "client_secret": ENV("TIKTOK_CLIENT_SECRET"),
                            "grant_type": "refresh_token", "refresh_token": ENV("TIKTOK_REFRESH_TOKEN")}).json()
    if "access_token" not in r:
        raise RuntimeError(r)
    new_rt = r.get("refresh_token")
    if new_rt and new_rt != ENV("TIKTOK_REFRESH_TOKEN") and ENV("GH_PAT"):
        # TikTok puo' cambiare il refresh token: aggiorna il Secret per le esecuzioni successive
        subprocess.run(["gh", "secret", "set", "TIKTOK_REFRESH_TOKEN", "--body", new_rt],
                       env={**os.environ, "GH_TOKEN": ENV("GH_PAT")}, check=False)
    return r["access_token"]


def tiktok_upload(path, cap):
    """Due modalita' (variabile TIKTOK_MODO):
    - "bozze" (predefinita): il reel arriva nelle bozze/notifiche di TikTok e Alessandro lo pubblica con un tocco.
      Serve finche' l'app TikTok non e' approvata: le bozze le pubblica lui, quindi escono PUBBLICHE.
    - "diretto": pubblicazione diretta (privata finche' l'app non e' approvata; privacy da TIKTOK_PRIVACY)."""
    token = tiktok_token()
    size = os.path.getsize(path)
    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"}
    source = {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": size, "total_chunk_count": 1}
    if (ENV("TIKTOK_MODO") or "bozze") == "diretto":
        init = requests.post("https://open.tiktokapis.com/v2/post/publish/video/init/", headers=h,
                             json={"post_info": {"title": testo_breve(cap)[:2200],
                                                 "privacy_level": ENV("TIKTOK_PRIVACY") or "SELF_ONLY",
                                                 "disable_comment": False, "disable_duet": False,
                                                 "disable_stitch": False,
                                                 "video_cover_timestamp_ms": cap.get("copertina_ms", 1000)},
                                   "source_info": source}).json()
    else:
        init = requests.post("https://open.tiktokapis.com/v2/post/publish/inbox/video/init/", headers=h,
                             json={"source_info": source}).json()
    data = init.get("data", {})
    if "upload_url" not in data:
        raise RuntimeError(init)
    with open(path, "rb") as f:
        up = requests.put(data["upload_url"], data=f, timeout=600,
                          headers={"Content-Type": "video/mp4", "Content-Length": str(size),
                                   "Content-Range": f"bytes 0-{size - 1}/{size}"})
    if up.status_code >= 300:
        raise RuntimeError(up.text)
    return data["publish_id"]


# ------------------------------------------------------------------ orchestrazione
def versione_meta(path, recenti, scena=None):
    """La versione del reel per Facebook/Instagram: stessa immagine, musica nostra. None se non riesce
    (allora su quelle piattaforme non si pubblica: mai la musica della Raccolta YouTube fuori da YouTube)."""
    try:
        m = scegli_musica(None, recenti, scena, nostra=True)
        if not m:
            return None, None
        dst = os.path.splitext(path)[0] + "_meta.mp4"
        return overlay.cambia_musica(path, m, dst), os.path.basename(m)
    except Exception as e:
        log("versione per Facebook/Instagram non riuscita:", e)
        return None, None


def publish_all(path, cap, creds, only, path_meta=None, publish_at=None, ig_nativo=None):
    """ig_nativo = (video senza musica, audio_id): Instagram con un brano NATIVO di Instagram (pronto dal 18/10)."""
    fns = {"instagram": lambda: (instagram_upload(ig_nativo[0], cap, ig_nativo[1]) if ig_nativo
                                 else instagram_upload(path_meta, cap)),
           "facebook": lambda: facebook_upload(path_meta, cap),
           "youtube": lambda: youtube_upload(creds, path, cap, publish_at),
           "tiktok": lambda: tiktok_upload(path_meta, cap)}
    results = {}
    for name in only:
        if name in MUSICA_NOSTRA and not path_meta and not (name == "instagram" and ig_nativo):
            results[name] = {"ok": False, "errore": "manca la versione con la nostra musica"}
            log(name, "saltato: manca la versione con la nostra musica")
            continue
        if DRY:
            results[name] = {"ok": True, "id": "prova"}
            log(name, "(prova) ok")
            continue
        try:
            results[name] = {"ok": True, "id": fns[name]()}
            log(name, "pubblicato")
        except Exception as e:
            results[name] = {"ok": False, "errore": str(e)[:500]}
            log(name, "ERRORE:", e)
            traceback.print_exc()
    return results


def analizza_video(drive, v, work):
    """Scarica il video, riconosce la scena e l'ora di registrazione, calcola l'orario di uscita."""
    src = os.path.join(work, "analisi" + os.path.splitext(v["name"])[1])
    drive.download(v["id"], src)
    info = subprocess.run([overlay.FFMPEG, "-hide_banner", "-i", src], capture_output=True, text=True,
                          errors="ignore").stderr
    seconds, hdr = overlay.probe(src)
    start, length = overlay.segmento(seconds)
    frames = overlay.extract_frames(src, length, n=8, start=start, vf=overlay.HDR_TO_SDR if hdr else None)
    sc, conf, motivo = scene_mod.riconosci(frames, v["name"])
    con_chi, conf_chi = scene_mod.compagnia(frames)
    quando = scene_mod.ora_registrazione(info)
    parlato_info = None
    # PARLATO (18/10/2026): solo video in cui c'e' lui da solo (mai voci di parenti) e con l'audio. Mai in palestra:
    # la musica della palestra (con le parole) verrebbe scambiata per lui e porterebbe brani protetti nel reel
    if (con_chi == "solo" and conf_chi >= 0.5 and sc != "palestra" and overlay.ha_audio(src)
            and ENV("SENZA_PARLATO") != "1"):
        try:
            import parlato
            parole = parlato.trascrivi(src)
            if parlato.e_parlato(parole, seconds):
                parlato_info = {"parole": parole[:500]}
                log(f"{v['name']}: video PARLATO ({len(parole)} parole): {parlato.testo(parole)[:80]}")
        except Exception as e:
            log("Riconoscimento della voce non riuscito (resta un reel normale):", e)
    os.remove(src)
    lato_corto = min(frames[0].shape[:2]) if frames else 0
    return {"nome": v["name"], "scena": sc, "sicurezza": conf, "motivo": motivo, "lato_corto": lato_corto,
            "compagnia": con_chi if conf_chi >= 0.5 else None,
            "registrato": quando.isoformat(timespec="minutes") if quando else None,
            "fascia": scene_mod.fascia_per(sc, quando), "caricato": v["createdTime"], "parlato": parlato_info,
            # MOMENTO (19/10/2026): video mandato al bot con una scritta sotto (ricevi_telegram.py)
            "momento": ({"titolo": " ".join(v["description"].split())[:200]}
                        if (v.get("appProperties") or {}).get("momento") == "1" and (v.get("description") or "").strip()
                        else None)}


VICINE = {   # se manca un video della fascia giusta, si prova in queste (in ordine)
    "mattina": ["pranzo", "sera", "notte"], "ufficio": ["pranzo"], "pranzo": ["mattina", "ufficio"],
    "sera": ["notte", "pranzo", "mattina"], "palestra": ["notte"], "notte": ["palestra", "sera"]}


def fascia_video(a):
    """Fascia della giornata di un video analizzato (anche per analisi vecchie senza il campo)."""
    if a.get("fascia"):
        return a["fascia"]
    q = None
    if a.get("registrato"):
        try:
            q = datetime.datetime.fromisoformat(a["registrato"])
        except ValueError:
            pass
    return scene_mod.fascia_per(a.get("scena"), q)


def scegli_video(videos, analisi, slot_ora):
    """Il video NUOVO giusto per questo orario (stessa fascia della giornata, poi fasce vicine, poi il piu' vecchio).
    I video nuovi hanno sempre la precedenza: l'archivio si usa solo se la coda e' vuota (vedi main)."""
    if not videos:
        return None
    momenti = [v for v in videos if analisi.get(v["id"], {}).get("momento")]
    if momenti:                                # MOMENTO: e' una cosa di oggi, esce al primo orario
        return momenti[0]
    if slot_ora is None:                       # esecuzione manuale: il piu' vecchio
        return videos[0]
    f = orario.fascia(slot_ora)
    for fascia in [f] + VICINE.get(f, []):
        adatti = [v for v in videos if fascia_video(analisi.get(v["id"], {})) == fascia]
        if adatti:
            return adatti[0]
    return videos[0]                           # nessun orario resta vuoto: il piu' vecchio in coda


def scegli_archivio(archivio, slot_ora):
    """Clip d'archivio da riusare quando non ci sono video nuovi: della fascia giusta se possibile,
    tra quelle usate meno volte e da piu' tempo (cosi' non si ripetono a breve)."""
    if not archivio:
        return None
    f = orario.fascia(slot_ora) if slot_ora else None
    ordine = [f] + VICINE.get(f, []) if f else []
    def chiave(c):
        pos = ordine.index(c.get("fascia")) if c.get("fascia") in ordine else len(ordine)
        return (int(c.get("usi", 0)), c.get("ultimo", ""), pos)       # meno usato, poi da piu' tempo, poi fascia
    return min(archivio, key=chiave)


def main():
    slot = sys.argv[1] if len(sys.argv) > 1 else "manuale"
    slot_ora = None if "manuale" in slot else slot.split()[-1]     # es. "09:45"
    frasi = json.load(open(FRASI, encoding="utf-8"))
    state = json.load(open(STATE, encoding="utf-8")) if os.path.exists(STATE) else {}
    for k, v in (("usate", []), ("storico", []), ("riprova", []), ("slot_fatti", []), ("musica_recenti", []),
                 ("frasi_usate", []), ("temi_recenti", []), ("analisi", {}), ("archivio_usi", {})):
        state.setdefault(k, v)

    def save():
        json.dump(state, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)

    if not DRY and not ENV("GOOGLE_REFRESH_TOKEN"):
        log("Account non ancora collegati (Secrets mancanti): niente da fare.")
        return
    creds = None if DRY else google_creds()
    drive = Drive(creds)
    work = os.path.join(HERE, "_lavoro")
    os.makedirs(work, exist_ok=True)

    # 0. nuovi tentativi per le piattaforme fallite
    for job in list(state["riprova"]):
        if "frase" not in job:                 # formato vecchio: si scarta
            state["riprova"].remove(job)
            continue
        path = os.path.join(work, "riprova.mp4")
        try:
            drive.download(job["pronti_id"], path, folder="Pronti")
        except Exception as e:
            log("riprova: download fallito", e)
            continue
        job["piattaforme"] = [x for x in job["piattaforme"] if x in PLATFORMS   # solo quelle ancora attive
                              and not fermo(state, x)]
        path_meta = None
        if job["frase"].get("tema") == "parlato":        # reel parlato: la sua voce, niente musica da cambiare
            path_meta = path
        elif MUSICA_NOSTRA & set(job["piattaforme"]):
            path_meta, _ = versione_meta(path, state.get("musica_recenti_meta", []))
        res = publish_all(path, job["frase"], creds, job["piattaforme"], path_meta)
        job["tentativi"] += 1
        job["piattaforme"] = [p for p, r in res.items() if not r["ok"]]
        state["storico"].append({"quando": datetime.datetime.now().isoformat(timespec="minutes"),
                                 "riprova": job["frase"]["id"], "risultati": res})
        if not job["piattaforme"] or job["tentativi"] >= MAX_TENTATIVI:
            state["riprova"].remove(job)
        save()

    # pulizia di Drive (una volta al giorno, alla prima esecuzione della giornata)
    oggi = datetime.date.today().isoformat()
    if state.get("pulizia") != oggi and not DRY:
        try:
            n = drive.pulisci_pronti(GIORNI_PRONTI)
            log(f"Pulizia Drive: {n} file nel cestino")
        except Exception as e:
            log("pulizia Drive non riuscita:", e)
        state["pulizia"] = oggi
        save()

    # 1. analisi dei video nuovi in coda
    videos = drive.list_videos()
    for v in videos:
        if v["id"] not in state["analisi"]:
            try:
                state["analisi"][v["id"]] = analizza_video(drive, v, work)
                log("Analizzato:", state["analisi"][v["id"]])
            except Exception as e:
                log("Analisi fallita per", v["name"], e)
                state["analisi"][v["id"]] = {"nome": v["name"], "scena": "casa", "fascia": "ufficio",
                                             "errore": str(e)[:200], "caricato": v["createdTime"]}
    for v in list(videos):
        a = state["analisi"].get(v["id"], {})
        if 0 < a.get("lato_corto", 9999) < QUALITA_MINIMA:
            log(f"{v['name']}: qualità troppo bassa ({a['lato_corto']}p), messo nel cestino di Drive")
            try:
                drive.cestino(v["id"])
            except Exception as e:
                log("cestino non riuscito:", e)
            videos.remove(v)
    # doppioni: stesso file caricato due volte (o gia' pubblicato) -> nel cestino, non esce due volte
    # anche lo stesso video esportato due volte (file diversi, es. IMG_3796.MOV e IMG_3796.mov): stesso nome + stessa ora di ripresa
    visti = {h["md5"] for h in state["storico"] if h.get("md5")}
    gemello = lambda nome, reg: (os.path.splitext(nome or "")[0].lower(), reg) if reg else None
    visti |= {gemello(h.get("video"), h.get("registrato")) for h in state["storico"]
              if not h.get("da_archivio") and gemello(h.get("video"), h.get("registrato"))}
    for v in list(videos):
        md5 = v.get("md5Checksum")
        chiave = gemello(v["name"], state["analisi"].get(v["id"], {}).get("registrato"))
        if not md5 and not chiave:
            continue
        if (md5 and md5 in visti) or (chiave and chiave in visti):
            log(f"{v['name']}: e' un doppione di un video gia' pubblicato o in coda, messo nel cestino di Drive")
            try:
                drive.cestino(v["id"])
            except Exception as e:
                log("cestino non riuscito:", e)
            videos.remove(v)
        else:
            visti |= {x for x in (md5, chiave) if x}
    in_coda = {v["id"] for v in videos}
    state["analisi"] = {k: a for k, a in state["analisi"].items() if k in in_coda}   # dimentica quelli usciti
    save()

    if slot != "manuale" and "manuale" not in slot and not piattaforme_slot(slot, state):
        log(f"Orario {slot}: nessuna piattaforma attiva in questo momento (tutte in pausa?), salto.")
        return

    # 2. il video giusto per questo orario: prima i video NUOVI, se la coda e' vuota una clip dall'archivio.
    # Orario FERMO (20/10/2026): il video nuovo aspetta un orario che YouTube spinge (MOMENTO no: esce subito)
    spinto = orario_spinto(state, slot, creds)
    video = scegli_video(videos, state["analisi"], slot_ora)
    tenuto = None
    if (video and not spinto and len(videos) <= VIDEO_DA_TENERE
            and not state["analisi"].get(video["id"], {}).get("momento")):
        tenuto, video = video, None
    clip = None
    if video is None:
        usi_arch = state.setdefault("archivio_usi", {})
        try:
            archivio = [dict(c, **usi_arch.get(c["id"], {})) for c in drive.lista_archivio()]
        except Exception as e:
            log("Lettura dell'archivio non riuscita:", e)
            archivio = []
        # i video PARLATI non si riusano con la musica sopra (si vedrebbe la bocca muoversi senza voce)
        archivio = [c for c in archivio if c.get("fallimenti", 0) < 2 and c.get("parlato") != "1"]
        # quante volte e quando ogni video e' gia' uscito (anche come video nuovo, prima di entrare in archivio)
        stem = lambda n: os.path.splitext(n or "")[0].lower()
        for c in archivio:
            usciti = [h["quando"][:16] for h in state["storico"] if h.get("video") and stem(h["video"]) == stem(c["nome"])]
            c["usi"] = max(int(c.get("usi", 0)), len(usciti))
            c["ultimo"] = max([c.get("ultimo", "")] + usciti)
        limite = (datetime.datetime.now() - datetime.timedelta(hours=12)).isoformat(timespec="minutes")
        riposati = [c for c in archivio if c.get("ultimo", "") < limite]     # niente video usciti nelle ultime 12 ore
        clip = scegli_archivio(riposati or archivio, slot_ora)
        if clip is None and tenuto:           # archivio vuoto: esce comunque il video nuovo
            video, tenuto = tenuto, None
        elif clip is None:
            log(f"Nessun video nuovo e archivio vuoto per l'orario {slot}.")
            return
    if clip:
        if tenuto:
            log(f"Orario fermo: {tenuto['name']} aspetta un orario spinto, adesso riuso dall'archivio {clip['nome']}")
        else:
            log(f"Nessun video nuovo: riuso dall'archivio {clip['nome']} (usato {clip.get('usi', 0)} volte)")
        an = {"scena": clip.get("scena"), "compagnia": clip.get("compagnia"), "fascia": clip.get("fascia")}
        nome, fonte_id = clip["nome"], clip["id"]
    else:
        an = state["analisi"][video["id"]]
        nome, fonte_id = video["name"], video["id"]

    # 3. frase e musica adatte
    pesi_file = os.path.join(HERE, "pesi.json")
    pesi = json.load(open(pesi_file, encoding="utf-8")).get("temi", {}) if os.path.exists(pesi_file) else {}
    usi = {h["frase"]: h["quando"][:10] for h in state["storico"] if h.get("frase") and h.get("quando")}
    if SOLO_MIE:    # solo le citazioni del Google Doc di Alessandro: prima quelle mai uscite, a caso
        try:
            mie = mie_frasi(drive.testo_mie_citazioni() or "")
        except Exception as e:
            log("Lettura di 'Le mie citazioni' non riuscita:", e)
            mie = []
        if random.random() >= TRADIMENTO_QUOTA:   # 25/10/2026: di tradimento si parla poco (1 volta su 10)
            mie = [f for f in mie if not TRADIMENTO.search(f["gancio"])] or mie
        mie = [f for f in mie if not DONNE.search(f["gancio"])] or mie       # 26/10/2026: mai frasi sulle donne
        mie = [f for f in mie if not NEGATIVO.search(f["gancio"]) and not PALESTRA.search(f["gancio"])] or mie  # 29/10
        frasi = [f for f in mie if f["id"] not in usi]
        log(f"'{DOC_MIE}': {len(mie)} citazioni, {len(frasi)} ancora da usare.")
        # reel da 5 s: anche le frasi lunghe (scelta di Alessandro 13/10/2026: se non si fa in tempo a leggere,
        # si riguarda il video -> piu' visualizzazioni). Nessun filtro sulla lunghezza.
        # dati YouTube 16/10/2026 (53 Shorts): frasi fino a 6 parole ~340 views mediane, 7-10 parole ~1.020,
        # 11-15 parole ~1.255 -> 9 volte su 10 si sceglie una frase di almeno 7 parole (1 su 10 resta "esperimento")
        lunghe = [f for f in frasi if len(f["gancio"].split()) >= MIN_PAROLE]
        virali = [f for f in frasi if f.get("virale")]       # prima quelle andate virali in altri video
        # come MoreMozi (18/10/2026): 1 volta su 4 si ripropone su un altro video una frase che ha gia' funzionato
        # (frasi_vincenti da report.py, ferma da almeno 7 giorni)
        try:
            vinc_id = set(json.load(open(pesi_file, encoding="utf-8")).get("frasi_vincenti", []))
        except Exception:
            vinc_id = set()
        sette = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
        vincenti = [f for f in mie if f["id"] in vinc_id and usi.get(f["id"], "") < sette]
        vecchie_lim = (datetime.date.today() - datetime.timedelta(days=GIORNI_RIUSO_FRASE)).isoformat()
        vecchie = [f for f in mie if f["id"] in usi and usi[f["id"]] < vecchie_lim]
        if not spinto and vecchie:           # orario fermo: si riusa la frase uscita da piu' tempo
            frase = min(vecchie, key=lambda f: usi[f["id"]])
            log("Orario fermo: riuso una frase uscita il", usi[frase["id"]])
        elif vincenti and random.random() < 0.25:
            frase = random.choice(vincenti)
            log("Ripropongo una frase che ha gia' funzionato:", frase["gancio"])
        elif frasi:
            # 20/10/2026 (98 Short): 11-15 parole mediana 1.014 views, 7-10 parole 862, fino a 6 parole 443
            # 26/10/2026 (Alessandro): frasi piu' lunghe (la gente si ferma a leggere) e PRIMA quelle che pensiamo
            # vadano piu' virali: classifica_frasi.json (0-100, 50 se manca; lunghezza, temi sulle persone, [virale],
            # giudizio di Claude). Si sceglie a caso tra le prime 3, cosi' i reel vicini non sono sempre uguali.
            import classifica_frasi
            punti = classifica_frasi.carica()
            ordinate = sorted(frasi, key=lambda f: -punti.get(f["id"], classifica_frasi.stima(f["gancio"], f.get("virale"))))
            frase = random.choice(ordinate[:3])
            log(f"Frase dalla classifica ({punti.get(frase['id'], 'stima')}):", frase["gancio"])
        elif mie:            # finite: si riusa quella uscita da piu' tempo (mai fermarsi); salute.py avvisa
            frase = min(mie, key=lambda f: usi.get(f["id"], ""))
            log("Citazioni nuove finite: riuso la meno recente. Aggiungerne altre al documento!")
        else:
            log(f"Documento '{DOC_MIE}' vuoto o non leggibile: niente da pubblicare.")
            return
    else:
        frase = scegli_frase(frasi, an["scena"], usi, state["temi_recenti"], pesi, an.get("compagnia"))
    music = None if ENV("SENZA_MUSICA") == "1" else scegli_musica(frase["tema"], state["musica_recenti"], an["scena"])
    log(f"Slot {slot} | {nome} | scena {an['scena']} | frase {frase['id']}: {frase['gancio']}")

    # 4. montaggio e pubblicazione
    src = os.path.join(work, "originale" + (os.path.splitext(nome)[1] or ".mov"))
    out = os.path.join(work, "reel.mp4")
    try:
        drive.download(fonte_id, src, folder="Archivio" if clip else "Da pubblicare")
        serie = etichetta_serie(slot)
        frase = dict(frase, serie=serie)
        info, formato = None, scegli_formato(slot, state, frase, an, spinto)
        log(f"Formato: {formato}")
        try:                            # se un formato non riesce esce il reel normale (frase da 5 s)
            if formato == "momento":
                frase, info = monta_momento(an, src, out, music, serie, nome)
            elif formato == "parlato":
                frase, info = monta_parlato(an, src, out, serie, nome)
            elif formato == "regole":
                frase, info = monta_regole(lista_regole(slot, state), src, out, music, serie, drive, work, clip)
            elif formato == "montaggio":
                info = monta_montaggio(frase, src, out, music, serie, drive, work, clip,
                                       str(an.get("registrato") or (clip or {}).get("registrato") or "")[:10] or None)
            elif formato == "gancio" and overlay.dividi_frase(frase["gancio"]):
                prima, seconda = overlay.dividi_frase(frase["gancio"])
                info = overlay.make_video(src, prima, out, music=music, serie=serie,
                                          colore=ENV("SENZA_COLORE") != "1", nome=nome, scena_rilevata=an["scena"],
                                          da_archivio=bool(clip), formato=dict(GANCIO, seconda=seconda))
            elif formato in FORMATI_10:
                info = monta_dieci(formato, frase, src, out, music, serie, drive, work, clip)
            elif formato in FORMATI_30:
                frase, info = monta_racconto(formato, src, out, music, serie, drive, work, clip, state)
            elif formato in ("broll1", "broll2", "broll3", "storia"):
                frase, info = monta_nuovo(formato, frase, src, out, music, serie, drive, work, clip, slot, state)
            elif formato == "frase8":
                info = overlay.make_video(src, frase["gancio"], out, music=music, serie=serie,
                                          colore=ENV("SENZA_COLORE") != "1", nome=nome, scena_rilevata=an["scena"],
                                          da_archivio=bool(clip), formato={"nome": "frase8", "durata": 8.0})
            elif formato == "ambiente":
                info = overlay.make_video(src, frase["gancio"], out, music=music, serie=serie,
                                          colore=ENV("SENZA_COLORE") != "1", nome=nome, scena_rilevata=an["scena"],
                                          da_archivio=bool(clip), formato=dict(AMBIENTE))
        except Exception as e:
            log(f"Formato {formato} non riuscito, faccio il reel normale:", e)
            info = None
        if info is None:
            info = overlay.make_video(src, frase["gancio"], out, preview=os.path.join(work, "anteprima.jpg"),
                                      music=music, serie=serie,
                                      autore=frase.get("autore") if MOSTRA_AUTORE else None,
                                      colore=ENV("SENZA_COLORE") != "1", nome=nome,
                                      scena_rilevata=an["scena"], da_archivio=bool(clip))
    except Exception as e:      # un video "rotto" non deve bloccare la coda
        if clip:
            u = state["archivio_usi"].setdefault(clip["id"], {})
            u["fallimenti"] = u.get("fallimenti", 0) + 1
            log(f"Montaggio fallito per la clip d'archivio {nome}: {e}")
        else:
            an["fallimenti"] = an.get("fallimenti", 0) + 1
            an["errore"] = str(e)[:300]
            log(f"Montaggio fallito per {nome} (tentativo {an['fallimenti']}): {e}")
            if an["fallimenti"] >= 2:        # dopo 2 tentativi va in "Da controllare"
                try:
                    drive.sposta_in_sottocartella(video["id"], "Da controllare")
                    state["analisi"].pop(video["id"], None)
                    log(f"{nome} spostato in 'Da controllare': la coda prosegue con gli altri video.")
                except Exception as e2:
                    log("spostamento non riuscito:", e2)
        save()
        shutil.rmtree(work, ignore_errors=True)
        raise
    log("Montato:", info)
    frase = dict(frase, copertina_ms=info.get("copertina_ms"))
    out_meta = None
    piatt = piattaforme_slot(slot, state)
    per_dopo = [p for p in PREPARA_PER_DOPO if p not in attive()] if principale(slot) else []
    parla = info.get("formato") == "parlato"    # PARLATO: la sua voce ovunque, mai musica al suo posto
    voce = parla or (info.get("formato") == "momento" and info.get("audio_originale"))   # suono vero da tenere
    if voce and MUSICA_NOSTRA & set(piatt):     # 25/10: Instagram/Facebook non accettano il 4K -> versione 1080p
        out_meta = overlay.versione_social(out, os.path.join(work, "reel_social.mp4"), audio=True)
    elif voce:
        out_meta = out
    elif MUSICA_NOSTRA & set(piatt) or per_dopo:
        base_social = overlay.versione_social(out, os.path.join(work, "reel_social.mp4"), audio=False)
        out_meta, info["musica_meta"] = versione_meta(base_social, state.get("musica_recenti_meta", []), an["scena"])
    # PUNTUALITA' (16/10/2026): si parte ~45' prima dello slot. YouTube viene caricato subito e PROGRAMMATO all'ora
    # esatta; poi si aspetta l'ora esatta per Telegram (TikTok) e Facebook.
    target = ora_slot(slot)
    anticipo = (target - ora_roma()).total_seconds() if target else 0
    yt_prima = "youtube" in piatt and anticipo > 10 * 60
    results = publish_all(out, frase, creds, ["youtube"], out_meta, target) if yt_prima else {}
    if yt_prima:
        log(f"YouTube programmato per le {target:%H:%M}" if results["youtube"]["ok"] else "YouTube: errore")
    if results.get("youtube", {}).get("ok"):    # se il lavoro si interrompesse, l'orario non si ripubblica
        state["slot_fatti"] = (state["slot_fatti"] + [slot])[-80:]
        state["storico"].append({"quando": datetime.datetime.now().isoformat(timespec="minutes"), "slot": slot,
                                 "video": nome, "md5": video.get("md5Checksum") if video else None,
                                 "da_archivio": bool(clip), "scena": an["scena"], "registrato": an.get("registrato"),
                                 "frase": frase["id"], "tema": frase["tema"], "montaggio": info, "risultati": results,
                                 "in_corso": True})
        save()
    if per_dopo and out_meta:
        try:
            nome_dopo = f"{ora_roma():%Y-%m-%d %H%M} - {frase['id']}.mp4"
            drive.salva_per_dopo(out_meta, nome_dopo, testo_breve(frase))
            log(f"Pronto per {' e '.join(per_dopo)}: {CARTELLA_DOPO}/{nome_dopo}")
        except Exception as e:
            log("Versione per Instagram non salvata su Drive:", e)
    if TIKTOK_A_MANO and "tiktok" not in attive() and principale(slot):   # TikTok a mano: versione SENZA musica
        try:
            muto = out if parla else overlay.senza_audio(out, os.path.join(work, "reel_tiktok.mp4"))
            nome_tt = f"{ora_roma():%Y-%m-%d %H%M} - {frase['id']}.mp4"
            fid_tt = drive.salva_per_dopo(muto, nome_tt, testo_breve(frase), CARTELLA_TIKTOK)
            state.setdefault("tiktok_coda", []).append({"id": fid_tt, "testo": testo_breve(frase), "slot": slot,
                                                        "parlato": parla})
            save()
            log(f"Pronto per TikTok (senza musica): {CARTELLA_TIKTOK}/{nome_tt}")
        except Exception as e:
            muto = None
            log("Versione per TikTok non salvata su Drive:", e)
    else:
        muto = None
    if TIKTOK_STUDIO and target:     # 25/10/2026: versione per TikTok Studio, programmata la sera prima dal PC
        try:
            tt = overlay.versione_tiktok(out, os.path.join(work, "reel_tt.mp4"), audio=bool(voce))
            nome_tt = f"{target:%Y-%m-%d %H%M} - {frase['id']}.mp4"
            drive.salva_tiktok(tt, nome_tt, testo_breve(frase), f"{target:%Y-%m-%d %H:%M}", voce)
            log(f"Pronto per TikTok Studio ({os.path.getsize(tt) / 1e6:.1f} MB): {CARTELLA_TIKTOK}/{nome_tt}")
        except Exception as e:
            log("Versione per TikTok Studio non salvata su Drive:", e)
    ig_nativo = None
    if "instagram" in piatt and not voce:   # Instagram: video 1080p senza musica + brano NATIVO scelto per la scena
        try:
            muto_ig = overlay.versione_social(out, os.path.join(work, "reel_ig.mp4"), audio=False)
            scelto = scegli_audio_instagram(an["scena"], state.get("ig_audio_recenti", []))
            if scelto:
                ig_nativo = (muto_ig, scelto[0])
                info["musica_instagram"] = scelto[1]
                state["ig_audio_recenti"] = (state.get("ig_audio_recenti", []) + [scelto[0]])[-30:]
        except Exception as e:
            log("Brano nativo Instagram non scelto (uso la nostra musica):", e)
    attesa = (target - ora_roma()).total_seconds() if target else 0
    if 0 < attesa < 70 * 60 and not DRY:
        log(f"Aspetto le {target:%H:%M} per pubblicare puntuale ({attesa / 60:.0f} minuti)")
        time.sleep(attesa)
        drive.riconnetti()
    t_slot = ora_slot(slot)
    if (TIKTOK_A_MANO and t_slot and t_slot.hour == ORA_TIKTOK and state.get("tiktok_coda") and ENV("TELEGRAM_BOT_TOKEN")
            and ENV("TELEGRAM_CHAT_ID") and not DRY):
        try:          # un problema con Telegram non deve mai fermare la pubblicazione
            manda_tiktok_della_giornata(state, drive, work, muto, slot, save)
        except Exception as e:
            log("Invio serale TikTok su Telegram non riuscito:", e)
    results.update(publish_all(out, frase, creds, [p for p in piatt if p not in results], out_meta,
                               ig_nativo=ig_nativo))
    controlla_errori(state, results)
    if results.get("youtube", {}).get("ok") and not DRY:
        try:
            aggiungi_playlist(creds, results["youtube"]["id"], an["scena"], state)
        except Exception as e:
            log("Playlist YouTube non aggiornata:", e)
    if results.get("instagram", {}).get("ok") and ENV("SENZA_STORIE") != "1" and principale(slot) and not DRY:
        try:
            results["instagram_storia"] = {"ok": True, "id": instagram_storia(out_meta or (ig_nativo or [None])[0])}
            log("instagram storia pubblicata")
        except Exception as e:
            results["instagram_storia"] = {"ok": False, "errore": str(e)[:300]}
            log("instagram storia non pubblicata:", e)
    if not any(r["ok"] for r in results.values()):
        log("Nessuna piattaforma ha funzionato: il video resta in coda per il prossimo orario.")
        sys.exit(1)

    # 5. archivio e stato
    oggi = datetime.date.today().isoformat()
    if clip:
        u = state["archivio_usi"].setdefault(clip["id"], {})
        u["usi"] = u.get("usi", 0) + 1
        u["ultimo"] = oggi
    spostato = False
    if not clip:             # video nuovo: si tiene per riusarlo in futuro
        meta_arch = {"scena": an.get("scena"), "fascia": fascia_video(an), "compagnia": an.get("compagnia"),
                     "registrato": an.get("registrato"), "parlato": "1" if an.get("parlato") else None}
        stem = os.path.splitext(nome)[0]
        try:
            if os.path.getsize(src) <= MAX_ORIGINALE_MB * 1024 * 1024:   # l'originale intero va nell'archivio
                cid = drive.sposta_in_archivio(video["id"], nome, meta_arch)
                spostato = True
                log(f"Originale spostato nell'archivio: {nome}")
            else:                                                       # troppo grande: un pezzo da 15 s
                cpath = overlay.crea_clip_archivio(src, os.path.join(work, stem + "_archivio.mov"), info.get("inizio"))
                cid = drive.carica_archivio(cpath, f"{stem}.mov", meta_arch)
                log(f"Copia (15 s) salvata nell'archivio: {stem}.mov")
            state.setdefault("archivio_usi", {})[cid] = {"usi": 1, "ultimo": oggi}
        except Exception as e:
            log("Archivio non aggiornato (il reel e' comunque uscito):", e)
    try:
        for n_pc, gb_pc in drive.libera_spazio(state.get("archivio_usi", {})):
            log(f"Drive quasi pieno: {n_pc} ({gb_pc} GB) va sul PC (Archivio - verso il PC)")
    except Exception as e:
        log("Controllo dello spazio su Drive non riuscito:", e)
    failed =[p for p, r in results.items() if not r["ok"] and p in PLATFORMS]
    pronti_id = None
    for tentativo in range(2):          # il reel e' gia' uscito: un errore qui non deve far perdere lo stato
        try:
            pronti_id = drive.archive(None if (clip or spostato) else video["id"], out,
                                      f"{frase['id']} - {os.path.splitext(nome)[0]}.mp4", carica=bool(failed))
            break
        except Exception as e:
            log("Copia in Pronti non riuscita" + (", riprovo" if not tentativo else "") + ":", e)
            drive.riconnetti()
    if results.get("tiktok", {}).get("ok") and (ENV("TIKTOK_MODO") or "bozze") != "diretto":
        try:                                  # la frase da incollare quando pubblica la bozza su TikTok
            drive.testo_tiktok(testo_breve(frase), nome)
        except Exception as e:
            log("testo TikTok non salvato su Drive:", e)
    if failed:
        state["riprova"].append({"frase": frase, "pronti_id": pronti_id, "piattaforme": failed, "tentativi": 0})
    state["frasi_usate"].append(frase["id"])
    state["formato_ultimo"] = info.get("formato") or "frase"
    if frase.get("righe"):
        state.setdefault("liste_usate", []).append(frase["id"])
    state["temi_recenti"] = (state["temi_recenti"] + [frase["tema"]])[-10:]
    if info.get("musica"):
        state["musica_recenti"] = (state["musica_recenti"] + [info["musica"]])[-20:]
    if info.get("musica_meta"):
        state["musica_recenti_meta"] = (state.get("musica_recenti_meta", []) + [info["musica_meta"]])[-20:]
    if slot not in state["slot_fatti"]:
        state["slot_fatti"] = (state["slot_fatti"] + [slot])[-80:]
    if video:
        state["analisi"].pop(video["id"], None)
    state["storico"] = [h for h in state["storico"] if not (h.get("in_corso") and h.get("slot") == slot)]
    state["storico"].append({"quando": datetime.datetime.now().isoformat(timespec="minutes"), "slot": slot,
                             "video": nome, "md5": video.get("md5Checksum") if video else None,
                             "da_archivio": bool(clip), "scena": an["scena"], "registrato": an.get("registrato"),
                             "frase": frase["id"], "tema": frase["tema"], "montaggio": info, "risultati": results,
                             "spinto": spinto, "testo": frase["gancio"][:120]})
    if not DRY:              # la sera: i commenti nuovi su Telegram, per rispondere di persona (mai bloccare il reel)
        try:
            import commenti
            n = commenti.forse_manda(state, ora_roma())
            if n is not None:
                log(f"Commenti nuovi mandati su Telegram: {n}")
        except Exception as e:
            log("Riassunto dei commenti non mandato:", e)
    save()
    shutil.rmtree(work, ignore_errors=True)
    log("Fatto." + (f" Da riprovare: {failed}" if failed else ""))

if __name__ == "__main__":
    try:
        main()
    except BaseException as e:            # anche sys.exit(1): avviso subito su Telegram (non per Ctrl+C)
        if not isinstance(e, KeyboardInterrupt) and not (isinstance(e, SystemExit) and e.code in (0, None)) and not DRY:
            import avvisi
            orario_slot = sys.argv[1] if len(sys.argv) > 1 else ""
            avvisi.manda(f"ATTENZIONE\nIl reel delle {orario_slot.split()[-1] if orario_slot else '?'} NON e' uscito\n"
                         f"Motivo: {str(e)[:300] or 'nessuna piattaforma ha funzionato'}\n\n"
                         "Al prossimo orario riprovo da solo\nSe si ripete scrivi a Claude")
        raise
