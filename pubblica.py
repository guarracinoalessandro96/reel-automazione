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
import overlay, audio_ig, avvisi
import scena as scene_mod
import mie_citazioni
import cartelle              # 7/11/2026: dove stanno le cartelle su Drive, prima e dopo il riordino
import orario

HERE = os.path.dirname(os.path.abspath(__file__))
FRASI = os.path.join(HERE, "frasi.json")
STATE = os.path.join(HERE, "stato.json")
GRAPH = "https://graph.facebook.com/v23.0"
ENV = os.environ.get
DRY = ENV("DRY_RUN") == "1"
from piattaforme import PLATFORMS, TIKTOK_A_MANO, TIKTOK_STUDIO, TIKTOK_BOZZE  # 19/10/2026: SOLO YOUTUBE (si cambia in piattaforme.py)
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
# 29/10/2026 sera (sue parole): "anche la parola palestra e' cringe, puoi parlare di tenersi in forma" -> vietata la
# parola e il gergo da palestra, si' a "tenersi in forma", "stare bene", "allenarsi"
PALESTRA = re.compile(r"palestr|gym|ripetizion|muscol|\bpes[io]\b|squat|panca|addominal|bilancier|serie in pi|massa|"
                      r"pompar|\bpump", re.I)
# 29/10/2026 sera: "non parlare della parola RICCO, e' troppo cringe, togli tutte le parole cringe"
# 29/10/2026 sera: "togliamo le cose inerenti alla famiglia. parliamo solo di vincere nella vita, voglio sembrare un
# ragazzo che si da' da fare" + "togliamo lo storytelling, sono storie inventate": niente famiglia nelle frasi, niente
# racconti (storie.json spento), si torna alle FRASI MOTIVAZIONALI
FAMIGLIA = re.compile(r"madr|padr|genitor|famigl|nonn|fratell|sorell|figli|mamma|pap[aà]|chi amo|"
                      r"persone che amo|casa tranquilla", re.I)
# 29/10/2026 notte: "niente mentre gli altri si lamentano, nessun paragone con gli altri"
CONFRONTO = re.compile(r"\baltr[ie]\b|la gente|le persone|\btutti\b|\bloro\b|\bpochi\b|maggior parte|"
                       r"mentre (gli|tutti|voi|qualcuno)|più di me|\bil più\b|meglio di|peggio di|\bchi non\b|\bvoi\b", re.I)
CRINGE = re.compile(r"\bricc[oaih]\w*|ricchezz|milion|miliard|lusso|lussuos|lamborghini|ferrari|rolex|supercar|"
                    r"hustle|grind|\balpha\b|sigma|\bleon[ei]\b|\blup[oi]\b|\bboss\b|\bbro\b|\bfra\b|mindset|guerrier|"
                    r"squal[oi]|\bre\b|regina|vincent[ei]|perdent[ei]|\bpecor|\bmassa\b|haters?|flex", re.I)

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


def brani_forti(chiave="brani_forti"):
    try:
        return set(json.load(open(os.path.join(HERE, "pesi.json"), encoding="utf-8")).get(chiave, []))
    except Exception:
        return set()


def audio_tendenza():
    """31/10/2026: titoli dei brani piu' usati dai reel forti (audio_tendenza.json, aggiornato la domenica)."""
    try:
        dati = json.load(open(os.path.join(HERE, "audio_tendenza.json"), encoding="utf-8"))
        return [b["titolo"] for b in dati.get("brani", []) if b.get("titolo")]
    except Exception:
        return []


YT_FINESTRA_BRANI = 30   # 6/11/2026 (Alessandro: "ogni video una musica diversa"): stesso brano mai negli ultimi 30 Short
# con musica (prima 8: in 3 giorni 16 brani su 23 reel, dusty_road_magic 3 volte). yt_dieci ne ha 36 (prepara_dieci.py)


def scegli_musica(tema, recenti, scena=None, nostra=False):
    """Un brano adatto alla scena, evitando quelli usati di recente: prima la Raccolta audio di YouTube, poi i loop
    generati da motivazione. nostra=True: solo i nostri brani (versione per Facebook/Instagram)."""
    yt = [] if nostra else list(YT_PER_SCENA.get(scena, ["yt_carica", "yt_epica"]))
    if TUTTO_10S and not nostra:      # 31/10/2026: pezzi unici da 10,5 s (prepara_dieci.py): la musica non salta a meta'
        yt = ["yt_dieci"]
    random.shuffle(yt)
    generi = (*yt, GENERE_PER_SCENA.get(scena), *random.sample(GENERI_MOTIVAZIONE, len(GENERI_MOTIVAZIONE)))
    if not nostra:     # 3/11/2026 (Alessandro): "anche su YouTube audio di YouTube": mai i nostri brani, neanche di riserva
        generi = (*yt, *[g for g in ("yt_dieci", "yt_carica", "yt_epica") if g not in yt])
    if nostra:     # 3/11/2026: generi diversi di fila; quelli appena usati restano solo come ultima scelta
        vicini_generi = {audio_ig.genere(b) for b in recenti[-2:]}
        generi = (*[g for g in generi if g not in vicini_generi], *generi)
    for mood in generi:
        if not mood:
            continue
        d = os.path.join(HERE, "musica", mood)
        brani = sorted(f for f in os.listdir(d) if f.endswith((".flac", ".m4a"))) if os.path.isdir(d) else []
        if brani:
            # niente stesso pezzo tra i recenti e niente stesso BRANO (pezzi diversi della stessa canzone) negli ultimi
            # YT_FINESTRA_BRANI (6/11/2026; prima 8); se la cartella ha pochi brani la finestra si stringe da sola
            brano = lambda f: re.sub(r"_\d+$", "", os.path.splitext(f)[0])
            finestra, liberi = (8 if nostra else YT_FINESTRA_BRANI), []
            for k in dict.fromkeys((finestra, finestra * 2 // 3, finestra // 3, 8)):
                vicini = {brano(b) for b in recenti[-k:]}
                liberi = [b for b in brani if b not in recenti and brano(b) not in vicini]
                if liberi:
                    break
            liberi = liberi or [b for b in brani if b not in recenti] or brani
            # 31/10/2026: 2 volte su 3 i brani che su YouTube rendono di piu' (pesi.json, aggiornati la domenica)
            preferiti = brani_forti("brani_forti_ig" if nostra else "brani_forti")   # 3/11: i nostri, dai numeri di Instagram
            forti = [b for b in liberi if brano(b) in preferiti or os.path.splitext(b)[0] in preferiti]
            if forti and random.random() < 0.67:
                liberi = forti
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


DOMANDE_COMMENTI = False   # 29/10/2026: "non mi piace quella cosa scrivila nei commenti, togliamola"


# 3/11/2026: parole che la gente cerca davvero, prese dalla frase (titolo/tag YouTube e hashtag delle didascalie)
PAROLE_CERCATE = [("disciplin", "#disciplina"), ("costan", "#costanza"), ("sacrifi", "#sacrificio"),
                  ("obiettiv", "#obiettivi"), ("futur", "#futuro"), ("lavor", "#lavoro"), ("sogn", "#sogni"),
                  ("success", "#successo"), ("mental", "#mentalita"), ("crescit", "#crescitapersonale"),
                  ("non mollare", "#nonmollare"), ("forza", "#forzadivolonta")]
HASHTAG_GIRO = ["#frasimotivazionali", "#motivazione", "#citazioni", "#mentalita", "#obiettivi", "#disciplina",
                "#crescitapersonale", "#frasidivita"]


def parole_cercate(testo):
    try:     # 6/11/2026: piu' parole riconosciute (vita, tempo, pazienza, coraggio, rispetto...): didascalie.py
        import didascalie
        return didascalie.tag_della_frase(testo)[:2]
    except Exception as e:
        log("parole cercate: uso l'elenco di prima:", e)
    t = (testo or "").lower()
    return list(dict.fromkeys(tag for radice, tag in PAROLE_CERCATE if radice in t))[:2]


def hashtag_a_rotazione(cap, n, escludi=None):
    """n hashtag: prima quelli della frase, poi a rotazione (fissi per la stessa frase, diversi tra frasi)."""
    giro = int(hashlib.md5(str(cap.get("id", cap.get("gancio", ""))).encode()).hexdigest(), 16)
    k = giro % len(HASHTAG_GIRO)
    tutti = parole_cercate(cap.get("gancio")) + HASHTAG_GIRO[k:] + HASHTAG_GIRO[:k]
    return [t for t in dict.fromkeys(tutti) if t != escludi][:n]


DIDASCALIE_NUOVE = True    # 6/11/2026: didascalie.py (False = quelle di prima)


def frase_semplice(cap):
    """True per i reel con una frase (non momento, parlato, liste o racconti: quelli tengono il loro testo)."""
    return not cap.get("righe") and cap.get("tema") not in ("momento", "parlato", "regole", "storia")


def testo_breve(cap):
    """Descrizione pubblicata (Instagram e, dal file su Drive, TikTok e Facebook). 6/11/2026: la frase in prima riga
    (si legge subito e ha le parole cercate), una riga di ricerca presa dalla frase, Giorno X/365, 4 hashtag
    pertinenti (didascalie.py); se qualcosa non va, la descrizione di prima."""
    if DIDASCALIE_NUOVE and frase_semplice(cap) and (cap.get("gancio") or "").strip():
        try:
            import didascalie
            return didascalie.didascalia(cap["gancio"], serie_testo(cap), cap.get("tema"), cap.get("id"))
        except Exception as e:
            log("didascalia nuova non riuscita, uso quella di prima:", e)
    tags = cap.get("hashtag") or ["#citazioni", "#motivazione"]
    if tags == ["#citazioni", "#motivazione", "#mentalita"]:     # 3/11: le frasi del Doc non hanno sempre gli stessi 3
        tags = hashtag_a_rotazione(cap, 3)
    testo = cap["gancio"].strip().strip('"“”')
    if MOSTRA_AUTORE and cap.get("autore"):
        testo = "“" + testo.strip('"“”') + "” — " + cap["autore"]
    else:
        testo = testo.rstrip(" .")
    if cap.get("righe"):          # formato REGOLE: titolo + regole numerate
        testo = cap["gancio"] + "\n" + "\n".join(f"{i}. {r}" for i, r in enumerate(cap["righe"], 1)) + "\n\nSalva questo video."
    serie = serie_testo(cap)
    if DOMANDE_COMMENTI and cap.get("tema") not in ("momento", "parlato", "regole"):   # 29/10/2026 sera: SPENTO: una domanda in fondo -> piu' commenti -> piu' spinta dall'algoritmo
        # 29/10/2026: tolta "Per chi lo fai tu? Scrivilo nei commenti" (non gli piace)
        domande = ["E tu, cosa ti sei promesso? Scrivilo qui sotto 👇", "Qual è il tuo obiettivo di quest'anno? 👇",
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
    if TUTTO_10S and str(slot).endswith(ORARIO_LISTA) and lista_regole(slot, state):   # 31/10/2026: una lista al giorno
        return "dieci_lista"
    if TUTTO_10S:                    # 29/10/2026: tutti da 10 s, a turno (mai lo stesso due volte di fila)
        scelte = [f for f in FORMATI_10 if f != state.get("formato_ultimo")] or list(FORMATI_10)
        try:                         # 31/10/2026: piu' spazio ai formati che rendono (pesi.json, da report.py)
            pesi_f = json.load(open(os.path.join(HERE, "pesi.json"), encoding="utf-8")).get("formati", {})
        except Exception:
            pesi_f = {}
        if str(slot)[:10] < FORMATI_PROVA_FINO:
            pesi_f = {}
        return random.choices(scelte, weights=[float(pesi_f.get(f, 1.0)) for f in scelte])[0]
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


def frase_forzata(mie, state, spinto=True):
    """2/11/2026: frase che Alessandro vuole ripetere nel prossimo reel (frasi_forzate.json: [{"id", "dal"}, ...]).
    6/11/2026: con "solo_spinti": true la frase aspetta un orario spinto da YouTube: dal 29/10 nessuno Short di un
    orario previsto fermo ha preso il giro di prova (0 su 14), le frasi migliori non vanno sprecate li'."""
    try:
        forzate = json.load(open(os.path.join(HERE, "frasi_forzate.json"), encoding="utf-8"))
    except Exception:
        return None
    # 6/11/2026: le richieste di Alessandro prima delle frasi che aspettano un orario spinto (sorted e' stabile)
    for v in sorted(forzate, key=lambda v: bool(v.get("solo_spinti"))):
        if v.get("solo_spinti") and not spinto:
            continue
        ultima = max([h.get("quando", "") for h in state["storico"] if h.get("frase") == v["id"]] or [""])
        trovata = next((f for f in mie if f["id"] == v["id"]), None)
        if trovata and ultima < v["dal"]:
            return trovata
    return None


def coda_screenshot():
    """7/11/2026 (Alessandro: "pubblica quelle che non sono state utilizzate privilegiando sempre quelle che ti ho
    salvato per prima"): le frasi dei suoi screenshot in fila, dalla piu' vecchia (notte/ordine_screenshot.json:
    [{"id", "file", "cartella", "creato", "frase"}, ...]) -> {id: posto}. Senza il file: {} e si sceglie come prima."""
    try:
        with open(os.path.join(HERE, "notte", "ordine_screenshot.json"), encoding="utf-8") as f:
            return {v["id"]: n for n, v in enumerate(json.load(f))}
    except Exception:
        return {}


def clip_voti():
    """1/11/2026: voto visivo delle clip (luce + inquadratura + nitidezza, 3-15) e clip escluse (brutte o con altre persone)."""
    try:
        return json.load(open(os.path.join(HERE, "clip_voti.json"), encoding="utf-8"))
    except Exception:
        return {"escluse": [], "voti": {}}


def clip_extra(drive, work, clip, n=2, giorno=None):
    """n clip dall'archivio (diverse da quella dell'orario), scaricate in locale: PRIMA quelle girate lo stesso
    giorno (es. la domenica delle castagne: un piccolo racconto della giornata), poi a caso."""
    out = []
    try:
        fuori = clip_voti()["escluse"]
        altre = [c for c in drive.lista_archivio() if (not clip or c["id"] != clip["id"]) and c.get("parlato") != "1"
                 and c.get("nome") not in fuori]
        random.shuffle(altre)
        if giorno:
            altre.sort(key=lambda c: 0 if str(c.get("registrato") or "")[:10] == giorno else 1)
        # 6/11/2026 (revisione, punto 14): mai le clip messe da parte (tutte nere o che non si montano: 2 fallimenti)
        # 6/11/2026 (integrazione): ne' quelle trovate nere in questo stesso giro (NERE: clip extra o clip dell'orario)
        noto = lambda c: ORIENTAMENTI_NOTI.get(c["id"], {})
        altre = [c for c in altre if not noto(c).get("nera") and int(noto(c).get("fallimenti", 0) or 0) < 2
                 and c["id"] not in NERE]
        # 6/11/2026 (punto 34): le clip che sappiamo orizzontali (tagliate al centro nel 9:16) per ultime
        altre.sort(key=lambda c: _orizz(dict(c, **noto(c))) is True)
        for i, c in enumerate(altre[:n + 2]):
            if len(out) >= n:
                break
            p = os.path.join(work, f"extra_{i}{os.path.splitext(c['nome'])[1] or '.mov'}")
            drive.download(c["id"], p, folder="Archivio")
            ORIENTAMENTI[c["id"]] = orizzontale(p)
            if _nera(p):     # 6/11/2026 (revisione): IMG_4508.MOV, tutta nera, metteva 2-5 s di nero nei reel
                NERE.add(c["id"])
                log(f"Clip extra {c['nome']} tutta nera: messa da parte, ne prendo un'altra")
                continue
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
    if os.path.basename(d) == "yt_dieci":      # 1/11/2026: pezzo unico da 10 s: si usa quello scelto, non sempre il primo
        # 6/11/2026: la versione da 20,5 s dello stesso pezzo (prepara_dieci.py lunghi): nel formato "intero" (fino a
        # 20 s) il pezzo da 10,5 s ripartiva da capo a 10 s. Stesso inizio e stesso guadagno, e prepara_dieci controlla
        # che i primi 10 s siano uguali al pezzo corto: nei reel da 10 s la musica resta identica
        lungo = os.path.join(os.path.dirname(d), "yt_venti", os.path.basename(music))
        return [lungo if os.path.exists(lungo) else music]
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
# 6/11/2026 (Alessandro: "studia 10 format di video diversi"): 10 formati diversi per ritmo o impaginazione:
# una scena (dieci), il video intero, scene da 1/2/3/5 s tagliate dal SUO video (taglio1/2/3, dieci_due), bande da
# film (cinema) e post (frase fuori dal video), rallentatore (rallenty), avanti-indietro senza stacco (loop).
# dieci_broll (4 clip qualsiasi da 2,5 s) esce dal giro: stesso ritmo di taglio2/taglio3 e il peggiore nei dati (266
# views medie contro 522 di dieci); resta solo come ultimo ripiego in monta_dieci.
FORMATI_10 = ("dieci", "dieci_due", "taglio1", "taglio2", "taglio3", "intero", "cinema", "post", "rallenty", "loop",
              "giornata")   # 6/11/2026: la sua giornata, un momento diverso per scena (monta_giornata)
if overlay.STILE_CENTRO:
    # 7/11/2026 (Alessandro: "scene di video o foto e frase al centro"): cinema e post mettono la frase su una fascia
    # fuori dal video, il contrario del nuovo stile: escono dal giro (la prova degli altri formati va avanti al 16/11)
    FORMATI_10 = tuple(f for f in FORMATI_10 if f not in ("cinema", "post"))
# 6/11/2026 (Alessandro: "sfruttare diversi tipi di format per capire quali video possano funzionare, poi faremo solo
# quelle"): fino a FORMATI_PROVA_FINO tutti i formati da 10 s con la STESSA probabilita' (niente pesi vecchi), mai lo
# stesso due volte di fila; poi report.py/l'agente delle 18:30 tengono i migliori
FORMATI_PROVA_FINO = "2026-11-16"
# 6/11/2026 (Alessandro: "prova a meta'"): fino a FORMATI_PROVA_FINO la scritta e' a caso (meta' e meta', fissa per
# orario) tra la nuova (bianca con le parole chiave gialle) e il suo giallo pieno; montaggio.scritta in stato.json
SCRITTE_PROVA = ("bianco_parola_gialla", "giallo_classico")
# 7/11/2026 (studio della sera, modifica 2): ogni novita' che cambia i video parte su META' dei reel, con una moneta per
# orario indipendente dal formato, dalla scritta e dalle altre prove (seme diverso), e il lato uscito va in stato.json
# (montaggio.prove). Il 1/11 una decina di cambi insieme e la mediana YouTube e' scesa da 375 a 152,5 views: non si sa
# per quale. "apertura": "azione" (lui in movimento, mai il primo piano fermo per primo, solo visi veri) contro "viso"
# (com'era, fase 1); "frase": "aforisma" (tra le stesse 12 di oggi l'aforisma in una frase sola meglio piazzato)
# contro "classifica" (com'era). Fino a "fino" compreso meta' e meta', poi "dopo" (il lato da tenere se non si decide)
# 7/11/2026 (revisione): la prova della frase agisce solo quando la coda dei suoi screenshot e' finita (182 frasi a 100
# in notte/ordine_screenshot.json, 10 al giorno: verso il 25/11); prima esce "forzata" su tutti e due i lati. Dura
# quindi fino al 15/12, cosi' ha circa 20 giorni veri (~100 reel per lato) e non solo i 5 prima del 30/11
PROVE = {"apertura": {"lati": ("azione", "viso"), "fino": "2026-11-30", "dopo": "azione"},
         "frase": {"lati": ("aforisma", "classifica"), "fino": "2026-12-15", "dopo": "classifica"}}


def lato_prova(nome, slot):
    """7/11/2026: il lato della prova `nome` per l'orario `slot` (sempre lo stesso per lo stesso orario): fino a
    PROVE[nome]["fino"] compreso una moneta random.Random(f"{nome} {slot}"), meta' e meta'; dopo, o con un errore,
    PROVE[nome]["dopo"]. Non tocca il random di tutto il resto (formato, frase, musica)."""
    try:
        p = PROVE[nome]
        if str(slot)[:10] <= p["fino"]:
            return random.Random(f"{nome} {slot}").choice(p["lati"])
        return p["dopo"]
    except Exception as e:
        log(f"Prova {nome}: lato non deciso ({e}), uso quello di dopo la prova")
        return (PROVE.get(nome) or {}).get("dopo")


# 7/11/2026 (studio della sera, modifica 4): la forma della frase (montaggio.frase_forma). Su Instagram gli aforismi
# positivi in una frase sola sono andati meglio (5 su 6 sopra 200 views contro 2 su 16: indizio debole), su YouTube le
# frasi da 11+ parole. Regole semplici sull'italiano: voce "io" (prima persona), "tu" (seconda o un imperativo in
# testa) o "generale"; forma "due" se dentro la frase c'e' un punto, ! ? ; : o un trattino staccato, se no "una"
_VOCE_IO = set("io mi me mio mia miei mie ho sono faccio voglio devo posso sto vado ero avevo volevo potevo dovevo "
               "noi nostro nostra nostri nostre siamo abbiamo".split())
_VOCE_TU = set("tu ti te tuo tua tuoi tue sei hai puoi devi vuoi sai stai fai vai".split())
_IMPERATIVI = set("fai vai smetti inizia ricomincia continua ricorda credi lavora alzati rialzati pensa guarda impara "
                  "sii abbi prendi scegli lascia metti fidati allenati concentrati resta rimani cerca trova dimostra "
                  "ascolta diventa costruisci combatti insisti segui sogna osa svegliati muoviti datti dai vivi ama "
                  "goditi accetta sorridi respira fermati provaci tieni mantieni porta smettila spingi corri fallo "
                  "falla fatti stai credici vivila rischia rilassati calmati lotta parti pensaci punta migliora "
                  "studia leggi chiedi aspetta parla agisci sbaglia riprova perdona ringrazia".split())
# "sono" dopo un plurale ("i sogni sono", "le cose che sono", "ci sono") e' la terza persona, non "io"
_PLURALI = set("i gli le questi queste quelli quelle tutti tutte molti molte pochi poche alcuni alcune certi certe "
               "loro coloro tanti tante".split())


def forma_frase(testo):
    """7/11/2026: {"voce": "io"|"tu"|"generale", "forma": "una"|"due", "parole": n} della frase (regole semplici)."""
    t = str(testo or "").strip()
    pezzi = re.findall(r"[a-zàèéìíòóùú]+|[.!?;:,]", t.lower().replace("’", "'"))
    parole = [w for w in pezzi if w.isalpha()]
    pos_io = pos_tu = None
    if parole and (parole[0] in _IMPERATIVI or (parole[0] == "non" and len(parole) > 1
                                                and re.search(r"(are|ere|ire|arti|erti|irti)$", parole[1]))):
        pos_tu = 0
    clausola, i = [], 0
    for w in pezzi:
        if not w.isalpha():          # nuova frase o nuova parte: il plurale di prima non vale piu'
            clausola = []
            continue
        if w == "sono" and (set(clausola) & _PLURALI or (clausola and clausola[-1] == "ci")):
            pass
        elif w in _VOCE_IO and pos_io is None:
            pos_io = i
        elif w in _VOCE_TU and pos_tu is None:
            pos_tu = i
        clausola.append(w)
        i += 1
    voce = ("io" if pos_tu is None or (pos_io is not None and pos_io < pos_tu) else "tu") \
        if pos_io is not None or pos_tu is not None else "generale"
    due = bool(re.search(r"[.!?;:…]+[\"'»”)]*\s+\S", t) or re.search(r"\s[-–—]\s", t))
    return {"voce": voce, "forma": "due" if due else "una", "parole": sum(1 for w in t.split() if re.search(r"\w", w))}


def aforisma(testo):
    """7/11/2026: aforisma = una frase sola, voce generale, 9-20 parole (forma_frase)."""
    f = forma_frase(testo)
    return f["forma"] == "una" and f["voce"] == "generale" and 9 <= f["parole"] <= 20


def segna_prove(info, con_foto, lato_frase, frase_via, scelta, frase, src):
    """7/11/2026 (studio della sera): in montaggio (stato.json) le prove a meta' del reel, per la tabella del 16-17/11:
    prove = {"apertura": lato, "frase": lato} ("apertura" solo nei reel col video: sulle foto non cambia niente),
    apertura = {"lato", "viso_alto", "movimento", "primo_piano_fermo", "soglia_moto"} (misurata in make_sequenza, o qui
    dal file per i formati senza make_sequenza: momento, parlato, reel normale), frase_forma = forma_frase della frase
    uscita, frase_via = come e' stata scelta ("forzata" anche quando il formato ha messo il suo titolo). Mai un errore.
    7/11/2026 (revisione): prove["frase"] solo dove la prova poteva agire (frase_via diverso da "forzata"). "forzata" si
    decide PRIMA della moneta e nello stesso modo sui due lati (frase scelta da lui, suo screenshot o suoi screenshot tra
    le candidate, titolo del formato...): togliere quei reel non falsa il confronto. Con la coda degli screenshot quasi
    tutti i reel sono "forzata": prima la tabella del 17/11 avrebbe confrontato due gruppi trattati allo stesso modo;
    cosi' scrive che la prova non e' ancora partita. Oltre la scadenza del reel l'apertura non si misura dal file."""
    try:
        via = frase_via if (frase.get("id"), frase.get("gancio")) == tuple(scelta) else "forzata"
        prove = {"frase": lato_frase} if lato_frase and via != "forzata" else {}
        if con_foto:
            info.pop("apertura", None)
        else:
            prove["apertura"] = overlay.APERTURA
            ap = info.get("apertura")
            if not isinstance(ap, dict) and "viso_prima_scena" not in info:   # montato senza make_sequenza
                import formati_nuovi
                if formati_nuovi.scaduto():
                    info["oltre_scadenza"] = True
                else:
                    formati_nuovi._APERTURA_TEMPO[0] = 0.0
                    ap = formati_nuovi.apertura_info([formati_nuovi.apertura_da(src, float(info.get("inizio") or 0.0))])
            if ap:
                info["apertura"] = dict(ap, lato=overlay.APERTURA)
        info["prove"] = prove
        testo = frase.get("gancio") or frase.get("titolo") or ""
        info["frase_forma"] = forma_frase(testo)
        info["frase_via"] = via
    except Exception as e:
        log("Prove a meta' non segnate nello stato (il reel esce lo stesso):", e)
# massimo di clip extra; dal 6/11 per i formati a scene si scaricano SOLO se il suo video non basta (scene_mancanti)
SCENE_EXTRA = {"dieci_due": 1, "dieci_broll": 3, "taglio1": 3, "taglio2": 2, "taglio3": 2, "cinema": 1, "post": 1,
               "giornata": 7}   # 6/11/2026: momenti della stessa giornata (clip_giornata), una clip di scorta
# 7/11/2026 (revisione, tempi): i tetti di tempo valevano ognuno per un pezzo solo e nessuno guardava l'orario del reel.
# Ora una scadenza unica (formati_nuovi.SCADENZA) a SCADENZA_MINUTI dall'orario (YouTube va caricato almeno 10 minuti
# prima: restano ~5 minuti per la versione 1080p e il caricamento); la giornata (il formato piu' pesante) parte solo se
# alla scadenza mancano almeno GIORNATA_MINUTI minuti, se no subito taglio2 (ripiego_da = giornata). Le clip d'archivio
# piu' grandi di GIORNATA_MB_MAX (originali da 470-500 MB) vanno per ultime tra i momenti della giornata
SCADENZA_MINUTI = 15
GIORNATA_MINUTI = 20
GIORNATA_MB_MAX = 250
ORARIO_FOTO, FOTO_DAL = ("12:00", "18:00"), "2026-11-05"   # 1/11/2026: reel con le foto della giornata (foto_giornata.py); 5/11: 43 foto caricate -> si parte oggi, 2 al giorno finche' ce ne sono
COMMENTI_SU_TELEGRAM = False   # 31/10/2026: "non voglio i commenti": su Telegram solo errori e statistiche delle 8
ORARIO_LISTA = "spenta"      # 31/10/2026: prima tutte le frasi delle foto; per riaccenderla "18:00". Formato lista, da salvare e mandare (un post cosi' fa 1 invio ogni 2 like)


def monta_momento(an, src, out, music, serie, nome):
    """Reel MOMENTO: il video come l'ha girato lui (dall'inizio, fino a MOMENTO_MAX), il SUO titolo sopra e come
    titolo YouTube, il suono vero della ripresa. Con la famiglia: musica (mai voci di parenti) e al massimo 15 s."""
    import hashlib
    titolo = an["momento"]["titolo"]
    secondi, _ = overlay.probe(src)
    famiglia = an.get("compagnia") == "famiglia"
    # 12/11/2026 (Alessandro: "tutti i video devono essere di 10 secondi"): anche i momenti al massimo 10 s
    durata = round(min(secondi, 10.0), 2)
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
    if TUTTO_10S:                # 31/10/2026: solo le liste nuove (le vecchie parlano di persone, lealta', soldi)
        libere = [l for l in libere if l["id"].startswith("D")]
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


def monta_dieci(formato, frase, src, out, music, serie, drive, work, clip, ultimo=None):
    """Reel da 10 s (formati_nuovi.make_dieci). 'dieci' usa solo il video dell'orario: se e' piu' corto di 10 s
    si passa a 'dieci_due' (video dell'orario + una clip). Si usano TUTTI i suoi video, anche quelli in palestra
    (29/10/2026: "i video della palestra vanno bene"; e' solo la PAROLA palestra nei testi a essere vietata)."""
    import formati_nuovi
    if formato == "giornata":        # 6/11/2026: ha il suo montaggio (da qui senza la coda: solo l'archivio)
        return monta_giornata(frase, src, out, music, serie, drive, work, clip, {}, {"formato_ultimo": ultimo})
    if formato in ("dieci", "intero") and overlay.probe(src)[0] < 10.5:
        formato = "dieci_due"
    if formato in ("rallenty", "loop") and overlay.probe(src)[0] < 6.5:     # 6/11/2026: troppo corto per giocarci
        formato = "dieci_due"
    if formato == "rallenty":        # 6/11/2026 (revisione): 2,4 s + 8 s rallentati, a 0,5x (60 fps) o 0,75x (30 fps)
        try:
            v = 0.5 if float(overlay.fps(src)) >= 50 else 0.75
        except Exception:
            v = 0.75
        if overlay.probe(src)[0] < 2.4 + 8 * v:
            formato = "dieci_due"
    # 6/11/2026: le altre scene PRIMA dallo stesso giorno (i video della stessa palestra), poi a caso
    giorno = str((clip or {}).get("registrato") or overlay.data_ripresa(src) or "")[:10] or None
    musiche = musiche_brano(music, 3)
    n_extra = SCENE_EXTRA.get(formato, 0)
    if formato in formati_nuovi.A_SCENE:     # 6/11/2026: le scene dal SUO video; altre clip solo se non bastano
        n_extra = min(n_extra, formati_nuovi.scene_mancanti(formato, src, musiche))
    clips = [src] + (clip_extra(drive, work, clip, n_extra, giorno) if n_extra > 0 else [])
    # 31/10/2026: controllo PRIMA di pubblicare: la scritta non deve coprire il viso
    try:
        return formati_nuovi.make_dieci(formato, clips, frase["gancio"], out, musiche, serie, True)
    except formati_nuovi.VisoCoperto:
        pass
    # 6/11/2026 (revisione): se la scritta coprirebbe il viso, lo STESSO video esce in 'cinema' o 'post' (la frase sta
    # sulla fascia, fuori dal video: mai sul viso). Prima si passava a dieci_broll con 4 clip d'archivio a caso: il suo
    # video spariva, e dopo 2 prove l'ultimo montaggio partiva senza controllo del viso
    # 7/11/2026: con overlay.STILE_CENTRO la frase va al centro anche sul viso, VisoCoperto non arriva: qui non si passa
    ripiego = random.choice([f for f in ("cinema", "post") if f != ultimo] or ["cinema"])
    log(f"Scritta sul viso con {formato}: stesse clip in '{ripiego}', con la frase fuori dal video")
    # 6/11/2026 (integrazione, revisione della giornata): con la fascia la frase non e' la scritta in prova: lo stile del
    # tentativo scartato non finisce in montaggio.scritta (se si arriva a dieci_broll, la sua scritta lo rimette)
    overlay.ULTIMO_STILE = None
    try:
        if len(clips) == 1 and formati_nuovi.scene_mancanti(ripiego, src, musiche) > 0:   # video corto: 2 scene da 5 s
            clips += clip_extra(drive, work, clip, 1, giorno)
        info = formati_nuovi.make_dieci(ripiego, clips, frase["gancio"], out, musiche, serie, True)
        info["scritta"] = None
        # 7/11/2026 (revisione, giro 2): montaggio.fascia_viso = fascia perche' la scritta copriva un viso (anche falso:
        # regola 2). Sul lato "azione" della prova dell'apertura capita piu' spesso: la tabella del 17/11 conta questi
        # reel per lato e confronta i lati anche solo sui reel con la frase sul video (notte/formati_skill.txt, punto 6)
        info["fascia_viso"] = True
    except Exception as e:     # solo se anche questo non riesce: 4 clip d'archivio, sempre con il controllo del viso
        log(f"Anche {ripiego} non riuscito ({e}): dieci_broll con altre clip")
        cambio = os.path.join(work, "cambio")
        os.makedirs(cambio, exist_ok=True)
        info = formati_nuovi.make_dieci("dieci_broll", clip_extra(drive, cambio, clip, 4) or clips, frase["gancio"],
                                        out, musiche, serie, True)
    info["ripiego_da"] = formato             # per report.py: questo reel non e' uscito nel formato estratto
    return info


def _stem_clip(n):
    return os.path.splitext(n or "")[0].lower()


def _byte(x):
    """7/11/2026 (revisione): la grandezza di un file di Drive ('size', una stringa) in byte; 0 se manca o e' strana."""
    try:
        return max(0, int(float(x or 0)))
    except (TypeError, ValueError):
        return 0


def _memoria_giornata(state):
    """6/11/2026 (revisione della giornata; integrazione: in comune con monta_giornata) dallo storico: (nomi senza
    estensione dei video usciti da soli nelle ultime 48 ore, nomi delle clip usate come scena in un reel GIORNATA
    negli ultimi 7 giorni, {giorno della giornata: ultima uscita})."""
    adesso = datetime.datetime.now()
    da = lambda ore: (adesso - datetime.timedelta(hours=ore)).isoformat(timespec="minutes")
    soli, come_scena, giorni_usati = set(), set(), {}
    for h in state.get("storico", []):
        quando, m = str(h.get("quando") or ""), h.get("montaggio")
        m = m if isinstance(m, dict) else {}
        if quando >= da(48) and h.get("video"):
            soli.add(_stem_clip(h["video"]))
        if quando >= da(24 * 7):
            come_scena |= {_stem_clip(x) for x in m.get("clip_scene") or [] if x}
        if m.get("giornata_del"):
            giorni_usati[m["giornata_del"]] = max(giorni_usati.get(m["giornata_del"], ""), quando)
    return soli, come_scena, giorni_usati


def clip_giornata(drive, work, clip, an, src, state, videos=(), video=None):
    """6/11/2026 (formato GIORNATA): clip di altri momenti della stessa giornata del video dell'orario, scaricate in
    locale (al massimo SCENE_EXTRA["giornata"]). Le clip gia' uscite stanno nell'ARCHIVIO (data di ripresa nelle
    proprieta', 'registrato'), quelle caricate e non ancora uscite in 'Da pubblicare' (state["analisi"]): il portinaio
    le carica tutte insieme quando il telefono e' in carica, quindi la mattina la giornata di ieri e' quasi tutta
    ancora in coda. Se quel giorno ha meno di 4 momenti diversi: il giorno piu' recente che li ha (prima i nuovi).
    Prima scene diverse (macchina, ufficio, cibo, palestra...), poi le clip nuove; mai il video dell'orario, i video
    parlati, i momenti col titolo (escono da soli), le clip escluse o con la famiglia, le clip senza data.
    6/11/2026 (revisione): con memoria (stato.json). In fondo, senza escluderle, le clip uscite da sole nelle ultime
    48 ore e quelle gia' usate come scena in un reel GIORNATA negli ultimi 7 giorni (montaggio.clip_scene); se il
    giorno del video non basta, tra i giorni con 4 momenti quello usato meno di recente (montaggio.giornata_del), a
    parita' il piu' recente. Prima il giorno di ripiego e le sue scene tornavano uguali a ogni reel.
    Restituisce (percorsi, ore di ripresa, scene, giorno, nomi delle clip, viste di recente si/no)."""
    import formati_nuovi
    stem = _stem_clip
    mio = clip or video or {}
    mio_id = mio.get("id")
    giorno0 = str((clip or {}).get("registrato") or an.get("registrato") or overlay.data_ripresa(src) or "")[:10]
    fuori, usi = set(clip_voti()["escluse"]), state.get("archivio_usi", {})
    soli, come_scena, giorni_usati = _memoria_giornata(state)
    usata = lambda c: stem(c["nome"]) in soli or stem(c["nome"]) in come_scena
    cand = []
    for v in videos or []:               # la coda: i video nuovi, gia' analizzati (scena, ora di ripresa)
        a = state.get("analisi", {}).get(v["id"], {})
        if v["id"] != mio_id and not (a.get("parlato") or a.get("momento") or a.get("analisi_fallita")
                                      or a.get("fallimenti")):
            cand.append({"id": v["id"], "nome": v["name"], "scena": a.get("scena"), "registrato": a.get("registrato"),
                         "compagnia": a.get("compagnia"), "cartella": "Da pubblicare", "nuova": True})
    try:
        archivio = drive.lista_archivio()
    except Exception as e:
        log("Giornata: archivio non letto, solo i video in coda:", e)
        archivio = []
    for c in archivio:
        if c["id"] != mio_id and c.get("parlato") != "1" and c.get("nome") not in fuori \
                and usi.get(c["id"], {}).get("fallimenti", 0) < 2 and c["id"] not in NERE:   # 6/11 (integrazione)
            cand.append(dict(c, cartella="Archivio", nuova=False))
    visti, per_giorno = {stem(mio.get("nome") or mio.get("name"))}, {}
    for c in cand:                       # stesso nome = stesso video (gia' uscito, o esportato due volte)
        reg = str(c.get("registrato") or "")
        if len(reg) >= 16 and c.get("compagnia") != "famiglia" and stem(c["nome"]) not in visti:
            visti.add(stem(c["nome"]))
            per_giorno.setdefault(reg[:10], []).append(c)
    minimo = formati_nuovi.GIORNATA_MIN
    if len(per_giorno.get(giorno0, [])) >= minimo - 1:
        giorno = giorno0
    else:     # min() tiene il primo a parita': in ordine dal giorno piu' recente
        adatti = sorted((g for g in per_giorno if len(per_giorno[g]) >= minimo), reverse=True)
        giorno = min(adatti, key=lambda g: giorni_usati.get(g, "")) if adatti else None
    if not giorno:
        raise ValueError(f"nessun giorno con {minimo} momenti diversi")
    scelte = per_giorno[giorno]
    random.shuffle(scelte)
    scelte.sort(key=lambda c: not c["nuova"])          # a parita' di scena prima le clip nuove

    def a_giro(lista):                                 # una per scena a giro, prima le scene diverse dalla sua
        gruppi = {}
        for c in lista:
            gruppi.setdefault(c.get("scena") or "?", []).append(c)
        giro = sorted(gruppi, key=lambda s: (s == an.get("scena"), random.random()))
        fila = []
        while any(gruppi.values()):
            fila += [gruppi[s].pop(0) for s in giro if gruppi[s]]
        return fila
    ordine = a_giro([c for c in scelte if not usata(c)]) + a_giro([c for c in scelte if usata(c)])
    try:     # 7/11/2026 (revisione, tempi): le clip d'archivio piu' grandi di GIORNATA_MB_MAX per ultime (sorted e'
        # stabile: le altre restano nell'ordine di prima); le clip nuove mai (regola 7: prima il contenuto nuovo)
        grande = lambda c: not c["nuova"] and _byte(c.get("size")) > GIORNATA_MB_MAX * 1_000_000
        if any(grande(c) for c in ordine):
            ordine.sort(key=grande)
            log("Giornata: per ultime le clip d'archivio oltre "
                f"{GIORNATA_MB_MAX} MB: {', '.join(c['nome'] for c in ordine if grande(c))}")
    except Exception as e:
        log("Giornata: grandezza delle clip non letta (ordine di prima):", e)
    percorsi, ore, scene, nomi, viste, nuove = [], [], [], [], [], 0
    for i, c in enumerate(ordine):
        if len(percorsi) >= SCENE_EXTRA.get("giornata", 7):
            break
        p = os.path.join(work, f"giornata_{i}{os.path.splitext(c['nome'])[1] or '.mov'}")
        try:
            drive.download(c["id"], p, folder=c["cartella"])
            percorsi.append(p)
            ore.append(str(c["registrato"])[:16])
            scene.append(c.get("scena"))
            nomi.append(c["nome"])
            viste.append(usata(c))
            nuove += 1 if c["nuova"] else 0
        except Exception as e:
            log(f"Giornata: {c['nome']} non scaricata:", e)
    if len(percorsi) < minimo - 1:
        raise ValueError(f"solo {len(percorsi)} clip della giornata scaricate")
    log(f"Giornata del {giorno}{' (stesso giorno del video)' if giorno == giorno0 else ''}: {len(percorsi)} momenti "
        f"({', '.join(str(s) for s in scene)}), {nuove} ancora in coda, {sum(viste)} gia' viste di recente")
    return percorsi, ore, scene, giorno, nomi, viste


def monta_giornata(frase, src, out, music, serie, drive, work, clip, an, state, videos=(), video=None):
    """6/11/2026 (Alessandro: "devi essere tu a capire come devi fare l'editing"): reel GIORNATA, il video dell'orario
    e altri momenti della stessa giornata (clip_giornata) in formati_nuovi.make_giornata. Se i momenti non bastano o
    il montaggio non riesce: il video dell'orario in 'taglio2' come oggi (montaggio.estratto = giornata).
    6/11/2026 (revisione): montaggio.clip_scene e giornata_del per la memoria di clip_giornata.
    7/11/2026 (revisione, tempi): con meno di GIORNATA_MINUTI minuti alla scadenza del reel la giornata non si prova
    (download di 7 clip, analisi, forse la fascia: 8-20 minuti su GitHub): subito taglio2. Il motivo di ogni ripiego
    va in montaggio.ripiego_motivo."""
    import formati_nuovi
    motivo = None
    try:
        rimasti = formati_nuovi.secondi_rimasti()
        if rimasti is not None and rimasti < GIORNATA_MINUTI * 60:
            raise ValueError(f"mancano {max(0.0, rimasti) / 60:.0f} minuti alla scadenza del reel")
        altre, ore, scene, giorno, nomi, viste = clip_giornata(drive, work, clip, an, src, state, videos, video)
        ora0 = (clip or {}).get("registrato") or an.get("registrato") or overlay.data_ripresa(src)
        try:     # 6/11/2026 (integrazione, revisione della giornata): anche il video dell'orario puo' essere gia'
            # uscito da poco (da solo o come scena): allora non fa da prima scena se c'e' un'altra clip adatta
            mio = clip or video or {}
            soli, come_scena, _ = _memoria_giornata(state)
            nome0 = _stem_clip(mio.get("nome") or mio.get("name"))
            vista0 = bool(nome0) and (nome0 in soli or nome0 in come_scena)
        except Exception as e:
            log("Giornata: memoria del video dell'orario non letta:", e)
            vista0 = False
        info = formati_nuovi.make_giornata([src] + altre, frase["gancio"], out, musiche_brano(music, 3),
                                           [ora0] + ore, [an.get("scena")] + scene, True, state.get("formato_ultimo"),
                                           [None] + nomi, [vista0] + viste)
        info["giornata_del"] = giorno
        return info
    except Exception as e:
        log("Giornata non riuscita, il video dell'orario in 'taglio2':", e)
        motivo = str(e)[:120]
    info = monta_dieci("taglio2", frase, src, out, music, serie, drive, work, clip, state.get("formato_ultimo"))
    # 6/11/2026 (integrazione): come gli altri formati non riusciti (report.nome_formato: "ripiego ...", la tabella del
    # 16/11 a parte); montaggio.estratto = giornata lo aggiunge main
    info["ripiego_da"] = "giornata"
    if motivo:
        info["ripiego_motivo"] = motivo
    return info


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


def monta_dieci_lista(lista, src, out, music, serie, drive, work, clip):
    """Lista da 10 s con il video dell'orario + 3 clip dell'archivio. Restituisce (frase, info)."""
    import formati_nuovi
    clips = [src] + clip_extra(drive, work, clip, 3)
    info = formati_nuovi.make_lista(clips, lista["titolo"], lista["righe"], out, musiche_brano(music, 3), serie)
    info["musica"] = os.path.basename(music) if music else None
    frase = {"id": lista["id"], "tema": "regole", "gancio": lista["titolo"], "righe": lista["righe"], "autore": "",
             "hashtag": ["#obiettivi", "#motivazione", "#disciplina"], "serie": serie}
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


def google_con_tentativi():
    """4/11/2026: ogni chiamata a Drive e YouTube riprova da sola fino a 5 volte (SSL EOF, errori 5xx, 429): prima lo
    facevano solo alcune, e un errore di rete su una qualsiasi faceva saltare un pezzo del reel (il TikTok delle 10)."""
    from googleapiclient import http as gh
    if getattr(gh.HttpRequest.execute, "con_tentativi", False):
        return
    esegui, pezzo = gh.HttpRequest.execute, gh.MediaIoBaseDownload.next_chunk

    def execute(self, http=None, num_retries=0):
        return esegui(self, http=http, num_retries=max(num_retries, 5))

    def next_chunk(self, num_retries=0):
        return pezzo(self, num_retries=max(num_retries, 5))

    execute.con_tentativi = True
    gh.HttpRequest.execute, gh.MediaIoBaseDownload.next_chunk = execute, next_chunk


def con_tentativi(fn, cosa, drive=None, n=3):
    """4/11/2026: fn() con n tentativi se la rete cade; tra uno e l'altro una connessione nuova a Drive."""
    for i in range(n):
        try:
            return fn()
        except Exception as e:
            if i == n - 1:
                raise
            log(f"{cosa} non riuscito, riprovo:", e)
            time.sleep(10 * (i + 1))
            if drive:
                drive.riconnetti()


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
            google_con_tentativi()
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
        out, token = [], None
        while True:     # 4/11/2026: tutte le pagine (prima solo i primi 100 video: gli altri non uscivano mai)
            res = self.api.files().list(q=q, orderBy="createdTime", pageSize=100, pageToken=token,
                                        fields="nextPageToken,files(id,name,createdTime,md5Checksum,description,"
                                               "appProperties)").execute()
            out += res.get("files", [])
            token = res.get("nextPageToken")
            if not token:
                return out

    def download(self, file_id, dest, folder="Da pubblicare"):
        if self.local:
            shutil.copy(os.path.join(self.local, folder, file_id), dest)
            return
        from googleapiclient.http import MediaIoBaseDownload
        # 7/11/2026: la data di caricamento su Drive, chiesta solo se nel video manca la data di ripresa (overlay.intatta)
        overlay.CARICATI[dest] = (self.api, file_id)
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

    def cartella(self, nome, crea=True):
        """Id della cartella 'nome' accanto a 'Da pubblicare' (la crea se manca). 4/11/2026: ricordato per tutto il
        giro (prima 2 chiamate a Drive ogni volta, ~15 per reel: ognuna un punto in cui la rete poteva cadere).
        7/11/2026 (riordino del Drive): anche dentro "Sistema (non toccare)" e col nome vecchio (cartelle.py), ricordato
        col nome nuovo; crea=False: None se non c'e' (per le pulizie, che non devono far nascere cartelle)."""
        memo = self.__dict__.setdefault("_cartelle", {})
        chiave = cartelle.nomi(nome)[0]
        if chiave not in memo:
            trovata = self._cartella(nome, crea)
            if not trovata:
                return None
            memo[chiave] = trovata
        return memo[chiave]

    def _cartella(self, nome, crea=True):
        # 7/11/2026 (Alessandro: "tutte le altre cartelle mettile in una sola cartella generica"): si cerca col nome
        # nuovo e col vecchio, accanto a "Video da pubblicare" e dentro "Sistema (non toccare)"; si crea solo se non
        # c'e' da nessuna parte, nel posto giusto. Prima si cercava solo accanto e, se la cartella era stata spostata,
        # ne nasceva subito una nuova vuota (archivio vuoto, cartella TikTok vuota...).
        padre = self.api.files().get(fileId=ENV("DRIVE_FOLDER_DA_PUBBLICARE"), fields="parents").execute()["parents"][0]

        def elenca(q):
            return self.api.files().list(q=q, fields=f"files({cartelle.CAMPI})", pageSize=100).execute().get("files", [])

        def nuova(n, dentro):
            log(f"Drive: la cartella '{n}' non c'era da nessuna parte: creata")
            return self.api.files().create(body={"name": n, "parents": [dentro], "mimeType": cartelle.CARTELLA},
                                           fields="id").execute()["id"]
        return cartelle.trova(nome, padre, elenca, nuova if crea else None, avvisa=log)

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
        """Clip dell'archivio: [{id, nome, scena, fascia, compagnia, registrato, size}].
        7/11/2026 (revisione, tempi): anche size (byte del file, 0 se non si sa) per clip_giornata."""
        if self.local:
            d = os.path.join(self.local, "Archivio")
            if not os.path.isdir(d):
                return []
            return [dict(json.load(open(os.path.join(d, f + ".json"))), id=f, nome=f, size=os.path.getsize(os.path.join(d, f)))
                    for f in sorted(os.listdir(d)) if not f.endswith(".json") and os.path.exists(os.path.join(d, f + ".json"))]
        q = f"'{self.cartella('Archivio')}' in parents and trashed = false and mimeType contains 'video/'"
        out, token = [], None
        while True:
            res = self.api.files().list(q=q, fields="nextPageToken,files(id,name,size,appProperties)", pageSize=500,
                                        pageToken=token).execute()
            out += [dict(f.get("appProperties") or {}, id=f["id"], nome=f["name"], size=_byte(f.get("size")))
                    for f in res.get("files", [])]
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
        """Sposta un video da 'Da pubblicare' a una cartella accanto (creata se manca).
        7/11/2026 (riordino del Drive): la cartella si trova come tutte le altre (cartelle.py): dopo il riordino
        "Da controllare" sta (o nasce) dentro "Sistema (non toccare)"."""
        if self.local:
            dest = os.path.join(self.local, nome)
            os.makedirs(dest, exist_ok=True)
            shutil.move(os.path.join(self.local, "Da pubblicare", file_id), os.path.join(dest, file_id))
            return
        origine = ENV("DRIVE_FOLDER_DA_PUBBLICARE")
        self.api.files().update(fileId=file_id, addParents=self.cartella(nome), removeParents=origine,
                                fields="id").execute()

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
            try:     # 7/11/2026: crea=False, una cartella che non c'e' piu' non rinasce solo per essere pulita
                c = self.cartella(nome_c, crea=False)
                if c:
                    cartelle_dopo.append((c, datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=GIORNI_DOPO)))
            except Exception:
                pass
        for cartella, soglia in ((ENV("DRIVE_FOLDER_PRONTI"), limite),
                                 (ENV("DRIVE_FOLDER_PUBBLICATI"), datetime.datetime.now(datetime.timezone.utc)),
                                 *cartelle_dopo):
            if not cartella:
                continue
            # 4/11/2026: solo i file piu' vecchi della soglia e tutte le pagine (prima i primi 200 a caso: con 10 reel
            # al giorno la cartella TikTok ne ha ~600 e i vecchi non andavano mai nel cestino)
            limite_q = soglia.strftime("%Y-%m-%dT%H:%M:%S")
            q = (f"'{cartella}' in parents and trashed = false and mimeType contains 'video/' "
                 f"and createdTime < '{limite_q}'")
            token = None
            while True:
                res = self.api.files().list(q=q, fields="nextPageToken,files(id)", pageSize=200,
                                            pageToken=token).execute()
                for f in res.get("files", []):
                    self.api.files().update(fileId=f["id"], body={"trashed": True}, fields="id").execute()
                    n += 1
                token = res.get("nextPageToken")
                if not token:
                    break
        return n


def titolo_youtube(frase, parole):
    """6/11/2026 (revisione: 23 titoli su 120 perdevano la fine della frase, quella che le da' senso, per far posto
    all'hashtag): prima la frase INTERA. Poi il primo hashtag di `parole` che ci sta nei 100 caratteri di YouTube
    (se nessuno ci sta resta solo in descrizione) e #shorts se c'e' posto: e' sempre anche in descrizione, quindi
    l'hashtag della frase vale di piu' (e cambia il titolo quando la frase torna). Si taglia (a parola intera + "…",
    mai solo la prima frase) solo una frase che da sola supera 100 caratteri. Ritorna (titolo, hashtag usato o None)."""
    frase = frase.strip()
    for fine in (" #shorts", ""):
        for p in parole:
            if len(f"{frase} {p}{fine}") <= 100:
                return f"{frase} {p}{fine}", p
    if len(f"{frase} #shorts") <= 100:
        return f"{frase} #shorts", None
    if len(frase) <= 100:
        return frase, None
    return frase[:99].rsplit(" ", 1)[0].rstrip(",;:") + "…", None


def youtube_upload(creds, path, cap, publish_at=None):
    """publish_at (datetime): caricato subito come privato e PROGRAMMATO: YouTube lo pubblica all'ora esatta."""
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    # 3/11/2026: la parola cercata viene dalla frase stessa (se parla di costanza -> #costanza), altrimenti una a caso
    della_frase = parole_cercate(cap["gancio"])
    parole = della_frase or [random.choice(("#motivazione", "#disciplina", "#crescitapersonale"))]
    if cap.get("volte"):     # frase gia' uscita: mai lo stesso titolo, la parola cambia a ogni ritorno
        giro = list(dict.fromkeys(della_frase + ["#motivazione", "#disciplina", "#crescitapersonale",
                                                 "#obiettivi", "#mentalita"]))
        k = cap["volte"] % len(giro)
        parole = giro[k:] + giro[:k]
    title, parola = titolo_youtube(cap["gancio"], parole)    # 6/11: la frase intera conta piu' dell'hashtag
    privacy = ENV("YOUTUBE_PRIVACY") or "public"
    momento = cap.get("tema") == "momento"
    descr = (cap["gancio"].strip().strip('"“”') + ("\n\n#shorts " + " ".join(cap.get("hashtag") or []) if momento else
             "\n\n#shorts " + " ".join(hashtag_a_rotazione(cap, 2, escludi=parola))))
    if cap.get("righe"):    # formato REGOLE: le regole in descrizione
        descr = "\n".join(f"{i}. {r}" for i, r in enumerate(cap["righe"], 1)) + "\n\n" + descr
    if serie_testo(cap):    # la serie in prima riga + invito a seguire il viaggio (il personaggio, non solo le frasi)
        descr = f"{serie_testo(cap)}\n\n" + descr
    if DIDASCALIE_NUOVE and frase_semplice(cap):
        try:     # 6/11/2026: come le didascalie: frase in prima riga (si vede nei risultati di ricerca), riga di
            # ricerca, Giorno X/365, #shorts + 2 hashtag pertinenti (diversi da quello del titolo)
            import didascalie
            descr = didascalie.descrizione_youtube(cap["gancio"], serie_testo(cap), cap.get("tema"), cap.get("id"),
                                                   didascalie.hashtag(cap["gancio"], cap.get("tema"), cap.get("id"),
                                                                      2, escludi=(parola,) if parola else ()))
        except Exception as e:
            log("descrizione YouTube nuova non riuscita, uso quella di prima:", e)
    body = {"snippet": {"title": title, "description": descr, "categoryId": "22",
                        "tags": list(dict.fromkeys(["vita vera", "momenti", "oggi", "italia", "shorts"] if momento else
                                 ["motivazione", "obiettivi", "disciplina", "frasi motivazionali", "crescita personale",
                                  "futuro", "lavoro", "vincere", "shorts"]
                                 + [p.lstrip("#") for p in parole_cercate(cap["gancio"])])),   # 29/10: niente palestra; 3/11: + parole della frase
                        "defaultLanguage": "it", "defaultAudioLanguage": "it"},
            "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}}
    if publish_at and privacy == "public":
        body["status"].update(privacyStatus="private",
                              publishAt=publish_at.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(path, mimetype="video/mp4", resumable=True))
    resp, cadute = None, 0
    while resp is None:
        try:     # 4/11/2026: YouTube 5xx (num_retries) o rete che cade a meta' (SSL EOF): si riprende da dove era
            _, resp = req.next_chunk(num_retries=5)
        except OSError as e:
            cadute += 1
            if cadute > 5:
                raise
            log("youtube: caricamento interrotto, riprendo:", e)
            time.sleep(5 * 2 ** cadute)
    vid = resp["id"]
    if PRIMO_COMMENTO and cap.get("commento") and privacy == "public":
        try:
            yt.commentThreads().insert(part="snippet", body={"snippet": {"videoId": vid, "topLevelComment": {
                "snippet": {"textOriginal": cap["commento"]}}}}).execute()
        except Exception as e:
            log("youtube: commento non pubblicato:", e)
    return vid


PLAYLIST_TUTTE = "Frasi motivazionali"
PLAYLIST_SCENA = {"palestra": "Tenersi in forma",       # 29/10/2026: niente parola "palestra" "macchina": "Pensieri in macchina",
                  "lavoro": "Lavoro e disciplina", "pacchi": "Lavoro e disciplina", "specchio": "Lavoro e disciplina",
                  "casa": "Lavoro e disciplina", "cibo": "Disciplina ogni giorno", "uscita": "Vita e persone"}


# 7/11/2026 (Alessandro: vuole cancellare tutte le playlist del canale, non i video): niente piu' playlist,
# ne' aggiunte ne' create di nuovo
PLAYLIST_ATTIVE = False


def aggiungi_playlist(creds, video_id, scena, state):
    """Ogni Short in 2 playlist pubbliche (tutte + quella della scena): YouTube fa guardare piu' video di fila."""
    if not PLAYLIST_ATTIVE:
        return
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
    for i in range(3):     # 4/11/2026: se la rete cade a meta' si ricarica da capo (offset 0)
        try:
            with open(path, "rb") as f:
                r = requests.post(url, headers={"Authorization": f"OAuth {token}", "offset": "0",
                                                "file_size": str(os.path.getsize(path))}, data=f, timeout=600)
            return r.json()
        except (requests.exceptions.RequestException, ValueError) as e:
            if i == 2:
                raise
            log("Meta: caricamento del video interrotto, riprovo:", e)
            time.sleep(15 * (i + 1))


def _meta(metodo, url, tentativi=3, **kw):
    """4/11/2026: chiamata a Meta con un tempo massimo e nuovi tentativi se la rete cade (prima senza timeout:
    una risposta che non arrivava bloccava il lavoro fino al limite di GitHub)."""
    kw.setdefault("timeout", 60)
    for i in range(tentativi):
        try:
            return requests.request(metodo, url, **kw).json()
        except (requests.exceptions.RequestException, ValueError) as e:
            if i == tentativi - 1:
                raise
            log("Meta non raggiungibile, riprovo:", e)
            time.sleep(10 * (i + 1))


def _ig_pubblica(V, ig, cid, token, elenco="media"):
    """media_publish; se Instagram risponde che il video non e' ancora pronto (9007 / 2207027) riprova per ~2 minuti.
    elenco: "media" (reel) o "stories", per ritrovare il post se e' uscito ma la risposta si e' persa."""
    pub, errore = {}, None
    for _ in range(8):
        try:
            pub = _meta("POST", f"{V}/{ig}/media_publish", data={"creation_id": cid, "access_token": token})
        except Exception as e:
            errore = e
            break
        err = pub.get("error") or {}
        if "id" in pub or not (err.get("code") == 9007 or err.get("error_subcode") == 2207027):
            break
        log("instagram: video non ancora pronto per l'uscita, riprovo")
        time.sleep(15)
    if "id" in pub:
        return pub
    # 4/11/2026: la risposta si e' persa (rete) ma il reel e' uscito: senza questo controllo finiva tra quelli da
    # riprovare e al giro dopo usciva DOPPIO
    try:
        if _meta("GET", f"{V}/{cid}", params={"fields": "status_code", "access_token": token}).get(
                "status_code") == "PUBLISHED":
            ultimi = _meta("GET", f"{V}/{ig}/{elenco}", params={"fields": "id", "limit": 1,
                                                                "access_token": token}).get("data") or []
            if ultimi:
                log("instagram: la risposta si era persa ma il post e' uscito:", ultimi[0]["id"])
                return {"id": ultimi[0]["id"]}
    except Exception as e:
        log("instagram: controllo dell'uscita non riuscito:", e)
    if errore:
        raise errore
    return pub


def _ig_carica_e_pubblica(path, dati):
    """Crea il contenitore Instagram (reel o storia), carica il video, aspetta l'elaborazione e pubblica."""
    token, ig = ENV("META_PAGE_TOKEN"), ENV("IG_USER_ID")
    r = _meta("POST", f"{GRAPH}/{ig}/media", data={**dati, "upload_type": "resumable", "access_token": token})
    if "id" not in r:
        raise RuntimeError(r)
    cid = r["id"]
    up = _rupload(r.get("uri", f"https://rupload.facebook.com/ig-api-upload/v23.0/{cid}"), token, path)
    if up.get("success") is False or "error" in up:
        raise RuntimeError(up)
    if _aspetta_contenitore(GRAPH, cid, token) == "ERROR":      # attende l'elaborazione (max ~10 minuti)
        raise RuntimeError(f"contenitore Instagram in errore ({cid})")
    pub = _ig_pubblica(GRAPH, ig, cid, token, "stories" if dati.get("media_type") == "STORIES" else "media")
    if "id" not in pub:
        raise RuntimeError(pub)
    return pub["id"]


def instagram_storia(path):
    """Lo stesso reel anche nelle Storie di Instagram: piu' persone lo vedono."""
    return _ig_carica_e_pubblica(path, {"media_type": "STORIES"})


# Instagram con MUSICA NATIVA (16/10/2026): l'API audio di Meta (/ig_audio, Graph v25+) da' i brani di Instagram
# autorizzati per le app; si carica il reel SENZA musica e si attacca il brano scelto (audio_configuration).
GRAPH_AUDIO = "https://graph.facebook.com/v26.0"   # 4/11/2026: l'ultima; la stessa per creare, controllare e pubblicare
IG_RICERCHE = {"palestra": ["motivational", "emotional", "cinematic"], "macchina": ["drive", "phonk", "night drive"],
               "lavoro": ["motivational", "epic", "hustle"], "pacchi": ["motivational", "hustle"],
               "specchio": ["motivational", "phonk"], "casa": ["motivational", "epic"],
               "cibo": ["motivational", "epic"], "uscita": ["epic", "motivational"]}
IG_DA_EVITARE = re.compile(r"love|amore|romantic|lullaby|sleep|relax|432hz|christmas|natale|baby|happy|domenica|"
                           r"lofi|lo-fi|slowed|chill|pensive|memor|miss|sad|calm|halloween|birthday|yummy|sitaron|"
                           r"kannan|maya|vayam|afro|jazz|piano|vivaldi|lullab|meditat|"
                           # 6/11/2026: il nome del brano compare sotto ogni reel: niente "Hell", doppi sensi, palestra
                           r"\bhell\b|right round|sexy|\bsex\b|booty|twerk|gym|palestr|funkytown|"
                           # e niente donne o coppie nei titoli (sue regole sui testi)
                           r"housewife|\bwife\b|girlfriend|boyfriend|\bgirls?\b|\blad(y|ies)\b|\bbabe\b|darling|"
                           r"sweetheart|bonnie (and|&) clyde", re.I)
# 30/10/2026: l'API delle app NON da' i suoni di tendenza veri di Instagram (cercando "trending" o "viral" escono brani
# a caso della libreria libera: "Let Me Love You", "I Love My Baby", lofi...). Si cercano solo brani energici/epici e
# si preferiscono i titoli che "suonano" motivazionali.
IG_ENERGICI = ["motivational", "epic", "workout", "cinematic", "powerful", "inspiring", "energetic", "hype"]
IG_TITOLI_FORTI = re.compile(r"knockout|fighter|level up|success|go go|big league|you can|inspired|\brise|champion|"
                             r"power|epic|victory|brave|breathtaker|unstoppable|believe|dream big|warrior|nerve|move",
                             re.I)


# 4/11/2026: brani di stagione o cupi che compaiono tra le tendenze ma non c'entrano con un reel motivazionale
IG_STAGIONE = re.compile(r"halloween|spooky|skeleton|trick or|ghost|thriller|dracula|monster|nightmare|llorona|"
                         r"witch|zombie|vampir|bloody|creep|horror|scary|goo goo|xmas|jingle|santa", re.I)
# 6/11/2026 (Alessandro: "ogni video una musica diversa", brani energici che partono forte): nei 3 giorni prima 9 reel su
# 23 avevano brani lenti, romantici o di stagione (Sara' perche' ti amo in 2 versioni di fila, November Rain, Piccole
# Cose, Ovunque Sarai, Sta passando novembre, fantasmas, Winter Magic). Fuori anche i jingle "Reels Sound".
IG_LENTI = re.compile(r"\bti amo\b|\bte amo\b|\bamor\b|amour|lovin|kiss|bacio|\bbaci\b|cuore|heart|coraz|valentine|"
                      r"wedding|you.re mine|be mine|novembre|november|autumn|autunno|winter|inverno|\bsnow|\bneve\b|"
                      r"candle|twinkl|sunday|coffee|caff[eè]\b|moka|funeral|ballad|acoustic|lounge|ambient|bossa|"
                      r"swing|reels sound|fantasm|\brain\b|raining|pioggia|lacrim|tears|\bcry(ing)?\b|triste|"
                      r"piccole cose|ovunque sarai|one more light|apocalypse|always you|here you come|sogna, ragazzo|"
                      r"guzarish|\bgod\b|jesus|ges[uù]|hallelujah|ave maria|"
                      # 6/11/2026 (revisione): parole generiche dei brani lenti, di festa, inni o da sottofondo
                      # (la lista cambia ogni ora: 135 brani su 160 in due ore e mezza), piu' quelli visti oggi
                      r"\bslow|holiday|\bbells?\b|carol|sheep|lazy|quiet|\bsoft\b|garden|seaside|moonlight|"
                      r"harvest moon|\bhalo\b|cinnamon girl|tu mil jaaye|ipanema|whisp|helpless|little moments|"
                      r"lost in the moment|\binno\b|\b(with|without|like|only|need|want) you\b|"
                      r"\byour (hand|eyes|arms|lips)\b|\bhold me\b|\bleave me\b|first time|passion|desire|\bheves\b|"
                      r"ocean trance|come ?over", re.I)
# brani che "suonano" energici: tra le tendenze vengono prima (insieme a IG_TITOLI_FORTI). 6/11/2026: fuori Highway
# (to Hell), Right Round e On The Floor (testi e titoli fuori tema) e gym/workout (la palestra non va nei testi)
IG_ENERGIA = re.compile(r"anthem|hall of fame|champion|climb|running|\brun\b|spark|\bin motion\b|\bmotion\b|"
                        r"march|\bfire\b|legacy|winner|\bwin\b|beast|strong|fight|battle|legend|"
                        r"glory|hero|thunder|storm|phonk|\bhype\b|energy|adrenalin|accelerand|"
                        r"eye of the tiger|lose yourself|remember the name|believer|rock you|"
                        r"can.t hold us|top of the world", re.I)   # 6/11/2026: tolti remix/sped up (una canzone
# d'amore in remix contava come energica)
IG_FINESTRA_BRANI = 60       # 6/11/2026: stesso brano (audio_id) mai negli ultimi 60 reel Instagram (prima 30)
IG_FINESTRA_TITOLI = 40      # stessa canzone, anche in un'altra versione o di un altro artista, mai negli ultimi 40
IG_FINESTRA_ARTISTI = 10     # stesso artista mai negli ultimi 10 (prima 3)
IG_PRIME_TENDENZE = 50       # le prime ~50 della lista sono le canzoni del momento, dopo vengono brani di libreria
# 6/11/2026 (revisione): il nome del brano compare sotto il reel: mai titoli con le parole vietate nei suoi testi
# (TRADIMENTO, DONNE, PALESTRA: "Pump It", "GymBro Phonk", "Innamorati a Milano") o su rancore e inganno
IG_TITOLI_VIETATI = re.compile(r"betray|traitor|cheat|liar|toxic|revenge", re.I)


def _titolo_vietato(t):
    t = str(t or "")
    return bool(TRADIMENTO.search(t) or DONNE.search(t) or PALESTRA.search(t) or IG_TITOLI_VIETATI.search(t))


def titolo_base(t):
    """6/11/2026: titolo senza versioni, accenti e parentesi ("Sarà Perché Ti Amo (Remix)" = "sara perche ti amo")."""
    import unicodedata
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[\(\[].*?[\)\]]", " ", t)
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


_TENDENZE = {}     # 4/11/2026: la lista letta una volta per lavoro (reel, nuovi tentativi e recuperi la riusano)


def tendenze_instagram(pagine=3):
    """4/11/2026: i brani DI TENDENZA di Instagram: /ig_audio senza search_query restituisce le tendenze del
    momento (la stessa lista dell'app; prima si cercava sempre per parola e uscivano brani a caso).
    6/11/2026: la lista intera, ~160 brani (prima 25): pagine da 100 (limit) e pagina dopo col cursore "after" (Meta
    non da' "next", quindi si leggeva solo la prima pagina). Se limit non va, resta la pagina normale."""
    if _TENDENZE.get("lista") and time.time() - _TENDENZE["ora"] < 1800:
        return _TENDENZE["lista"]
    token, ig = ENV("META_PAGE_TOKEN"), ENV("IG_USER_ID")
    base = {"audio_type": "music", "user_id": ig, "access_token": token}
    out, visti, dopo = [], set(), None
    for i in range(pagine):
        par = dict(base, limit=100, **({"after": dopo} if dopo else {}))
        try:
            r = _meta("GET", f"{GRAPH_AUDIO}/ig_audio", params=par, timeout=30)
        except Exception as e:
            if not out:
                raise
            log("Tendenze di Instagram: pagina", i + 1, "non letta:", type(e).__name__)
            break
        semplice = bool(r.get("error")) and not out
        if semplice:      # limit rifiutato: la lettura di prima (una pagina)
            log("Tendenze di Instagram: lettura a pagine rifiutata, leggo la prima pagina:",
                (r.get("error") or {}).get("message"))
            r = _meta("GET", f"{GRAPH_AUDIO}/ig_audio", params=base, timeout=30)
        nuovi = [a for a in r.get("audio", []) if a.get("audio_id") and a["audio_id"] not in visti]
        visti.update(a["audio_id"] for a in nuovi)
        out += nuovi
        dopo = ((r.get("paging") or {}).get("cursors") or {}).get("after")
        if semplice or not nuovi or not dopo:
            break
    if out:
        _TENDENZE.update(lista=out, ora=time.time())
    return out


def _priorita_ig(a, posto):
    """6/11/2026: 0 = canzoni del momento che suonano energiche, 1 = brani di libreria energici, 2 = le altre canzoni
    del momento, 3 = il resto, che tra le tendenze non si sceglie (revisione: dal 25esimo reel uscivano brani da
    sottofondo come Me In My Garden, Ipanema, Seaside). Energico = dal TITOLO (con l'artista, "Here With Me - Indian
    Run" contava come corsa). A parita', l'ordine delle tendenze."""
    forte = IG_TITOLI_FORTI.search(a.get("title", "") or "") or IG_ENERGIA.search(a.get("title", "") or "")
    # 6/11/2026 (revisione): le canzoni con licenza hanno on_platform_audio_preview_link, i brani di libreria
    # download_url (oggi le canzoni finivano ai posti 40-44, poi libreria da sottofondo): se c'e' il campo vale quello
    if a.get("download_url") or a.get("on_platform_audio_preview_link") or "libreria" in a:
        vera = not (a.get("download_url") or a.get("libreria"))
    else:
        vera = posto < IG_PRIME_TENDENZE
    return 0 if forte and vera else 1 if forte else 2 if vera else 3


# 6/11/2026 (Alessandro: "non devi prendere la musica dall'inizio ma nel momento piu' virale"): su Instagram il brano
# parte SEMPRE dal secondo 0 (l'API non ha un punto di partenza: audio_ig.apertura). Dei brani della libreria
# (download_url) si controlla l'inizio e quelli con un intro lento si scartano; le canzoni con licenza non hanno il
# file e restano come prima. False = come prima.
IG_APERTURA = True
IG_APERTURA_MAX = 4          # file nuovi controllati al massimo per gruppo di candidati (~0,5 MB e un secondo l'uno)
IG_APERTURA_TOTALE = 8       # ... e per ogni brano scelto (tendenze + ricerche)
# 6/11/2026 (integrazione, revisione del ritornello): tutti i file dei brani controllati in UNA scelta stanno in circa
# 60 s; poi niente altri download e la scelta di prima (la tendenza del gruppo migliore): con la rete lenta 8 file da
# 30 s l'uno potevano far tardare il reel
IG_APERTURA_SECONDI = 60
_APERTURE = {}               # audio_id -> True (parte forte) / False (intro) / None (non si sa), una volta per lavoro
_APERTURE_LETTE = [0]        # file letti per il brano in corso di scelta
_APERTURA_FINE = [None]      # ora (time.time()) oltre cui nella scelta in corso non si scarica piu' niente


def _tempo_brani_finito():
    return _APERTURA_FINE[0] is not None and time.time() >= _APERTURA_FINE[0]


def _parte_forte(a):
    """True/False per i brani con file (download_url), None se non si sa (canzoni con licenza, file non letto)."""
    if not IG_APERTURA or not a.get("download_url"):
        return None
    aid = a.get("audio_id")
    if aid not in _APERTURE:
        if _tempo_brani_finito():          # 6/11/2026 (integrazione): tempo finito, il brano resta "non si sa"
            return None
        try:
            m = audio_ig.apertura(a["download_url"], fine=_APERTURA_FINE[0])
        except Exception as e:
            log("Instagram: inizio del brano non controllato:", type(e).__name__)
            m = None
        _APERTURE[aid] = None if m is None else bool(m["forte"])
        if m:
            log(f"Instagram: inizio di '{a.get('title')}': primo secondo {m['primo']:+.1f} dB, primi 10 s "
                f"{m['dieci']:+.1f} dB, salto {m['salto']:+.1f} dB ->", "parte forte" if m["forte"] else "intro, scartato")
    return _APERTURE[aid]


def _riserva_senza_intro(gruppo, riserva):
    """6/11/2026 (integrazione, revisione del ritornello): la riserva tra i brani del gruppo che NON sono stati misurati
    con un intro lento (_APERTURE False), se ce n'e' almeno uno; se no quella di prima."""
    try:
        if riserva is None or _APERTURE.get(riserva.get("audio_id")) is not False:
            return riserva
        buoni = [a for a in gruppo if _APERTURE.get(a.get("audio_id")) is not False]
        return random.choice(buoni) if buoni else riserva
    except Exception as e:
        log("Instagram: riserva non ricontrollata:", e)
        return riserva


def _scegli_forte(candidati):
    """Il primo candidato che non parte con un intro lento: i brani della libreria si controllano (al massimo
    IG_APERTURA_MAX file nuovi), le canzoni con licenza passano come prima. None se nessuno passa."""
    nuovi = 0
    for a in candidati:
        if IG_APERTURA and a.get("download_url") and a.get("audio_id") not in _APERTURE:
            if nuovi >= IG_APERTURA_MAX or _APERTURE_LETTE[0] >= IG_APERTURA_TOTALE or _tempo_brani_finito():
                continue
            nuovi += 1
            _APERTURE_LETTE[0] += 1
        if _parte_forte(a) is not False:
            return a
    return None


def scegli_audio_instagram(scena, recenti=(), artisti_recenti=(), titoli_recenti=None):
    """(audio_id, titolo) di un brano Instagram, evitando i recenti. None se nessuno.
    Ordine (4/11/2026, Alessandro: "scegliendo la musica di tendenza di instagram, oppure la stessa musica degli altri
    reel"): 1) tendenze ufficiali di Instagram, 2) brani piu' usati dai reel forti (audio_tendenza.json, domenica),
    3) ricerca per parole energiche.
    6/11/2026: mai la stessa canzone (anche in un'altra versione) negli ultimi IG_FINESTRA_TITOLI reel, mai brani lenti
    o romantici (IG_LENTI). Ordine: tendenze energiche (_priorita_ig 0 e 1), altre canzoni del momento (2), ricerche
    energiche; ultima riserva la tendenza adatta usata meno di recente, perche' senza brano di Instagram il reel non
    esce (instagram_upload).
    6/11/2026 (Alessandro: "la musica deve partire dal momento piu' virale"): Instagram fa partire il brano dal secondo
    0, quindi tra i brani della libreria passano solo quelli che partono gia' forti (_scegli_forte); se nessuno
    passa, la scelta di prima."""
    token, ig = ENV("META_PAGE_TOKEN"), ENV("IG_USER_ID")
    _APERTURE_LETTE[0] = 0
    _APERTURA_FINE[0] = time.time() + IG_APERTURA_SECONDI     # 6/11/2026 (integrazione): un tempo per tutta la scelta
    if titoli_recenti is None:     # 6/11/2026: anche il secondo tentativo di instagram_upload evita le stesse canzoni
        titoli_recenti = (_IG_STATO.get("state") or {}).get("ig_titoli_recenti", [])
    titoli = set(titoli_recenti)
    testo = lambda a: f"{a.get('title', '')} {a.get('display_artist', '')}"
    giusto = lambda a: (a.get("audio_id") and a.get("duration_in_ms", 99999) >= 15000
                        and not IG_DA_EVITARE.search(testo(a)) and not IG_STAGIONE.search(testo(a))
                        and not IG_LENTI.search(testo(a)) and not _titolo_vietato(a.get("title")))
    adatto = lambda a: (giusto(a) and a["audio_id"] not in recenti
                        and (titolo_base(a.get("title")) or "?") not in titoli)    # titoli non latini: solo l'id
    try:
        lista = tendenze_instagram()
    except Exception as e:
        log("Tendenze di Instagram non lette:", e)
        lista = []
    stato = _IG_STATO.get("state")
    try:    # 6/11/2026: le ultime tendenze adatte restano nello stato, per l'ultima riserva se Instagram non le da'
        if lista and isinstance(stato, dict):
            stato["ig_tendenze_riserva"] = [dict({k: a.get(k) for k in ("audio_id", "title", "display_artist",
                                                                         "duration_in_ms")},
                                                 libreria=bool(a.get("download_url")))
                                            for i, a in enumerate(lista) if giusto(a) and _priorita_ig(a, i) <= 1][:30]
    except Exception as e:
        log("Tendenze di riserva non salvate:", e)
    tendenza = [(i, a) for i, a in enumerate(lista) if adatto(a)]
    if tendenza:     # tra le prime 8, un po' a caso cosi' i reel vicini non hanno lo stesso brano
        # 4/11/2026: e mai lo stesso artista dei reel recenti (6/11: ultimi 10), se resta almeno un brano
        tendenza = [x for x in tendenza if x[1].get("display_artist") not in artisti_recenti] or tendenza
        # 6/11/2026 (Alessandro: "Sara' perche' ti amo non ci va, Funkytown Flute non ci va perche' non significa nulla,
        # Novembre di Giusy Ferreri non ci va: devi capire le musiche che devono andare nei video"): solo brani col
        # titolo da video motivazionale (gruppi 0-1 di _priorita_ig); finiti, le ricerche energiche
        tendenza = [x for x in sorted((_priorita_ig(a, i), i, a) for i, a in tendenza) if x[0] <= 1]
    riserva = None
    if tendenza:     # tendenze prima delle ricerche: Alessandro vuole la musica di tendenza di Instagram (4/11)
        gruppo = [x[2] for x in tendenza if x[0] == tendenza[0][0]][:8]    # il gruppo migliore
        riserva = a = random.choice(gruppo)
        try:     # 6/11/2026: in ordine casuale, il primo che non parte con un intro lento (brani della libreria)
            a = _scegli_forte(random.sample(gruppo, len(gruppo)))
        except Exception as e:
            log("Instagram: inizio dei brani non controllato:", e)
        if a:
            return a["audio_id"], f"{a.get('title')} - {a.get('display_artist')} [tendenza]"
        # 6/11/2026 (integrazione): la riserva tra i brani del gruppo NON misurati con l'intro (se ce ne sono)
        riserva = _riserva_senza_intro(gruppo, riserva)
        if _tempo_brani_finito():     # 6/11/2026 (integrazione): tempo dei controlli finito: la scelta di prima
            log("Instagram: tempo per controllare i brani finito, la tendenza del gruppo migliore come prima")
            return riserva["audio_id"], f"{riserva.get('title')} - {riserva.get('display_artist')} [tendenza]"
        log("Instagram: le tendenze adatte partono tutte con un intro lento, provo le ricerche")
    ricerche = list(dict.fromkeys(random.sample(IG_ENERGICI, len(IG_ENERGICI))))
    # 4/11/2026: anche le ricerche di riserva con nuovi tentativi e gli stessi filtri delle tendenze (stagione, durata)
    cerca = lambda q: _meta("GET", f"{GRAPH_AUDIO}/ig_audio", timeout=30, params={
        "audio_type": "music", "search_query": q, "user_id": ig, "access_token": token}).get("audio", [])
    tutti = []
    # 6/11/2026 (integrazione, revisione del ritornello): dei brani usati dagli altri reel solo i titoli energici e
    # adatti, come per le tendenze (gruppi 0-1 di _priorita_ig): "DEFEATED" o "retire (final)" non vanno sotto un
    # reel motivazionale
    energico = lambda t: bool(IG_TITOLI_FORTI.search(t or "") or IG_ENERGIA.search(t or ""))
    try:
        da_altri = [q for q in audio_tendenza() if energico(q) and giusto({"audio_id": "-", "title": q})]
    except Exception as e:
        log("Brani degli altri reel non filtrati:", e)
        da_altri = []
    try:      # 6/11/2026: un errore di rete qui non deve lasciare il reel senza brano (c'e' ancora la riserva sotto)
        for q in da_altri[:6]:                        # i brani usati dagli altri reel, se Instagram li concede all'API
            trovati = [a for a in cerca(q) if adatto(a)
                       and q.lower().strip() == a.get("title", "").lower().strip()]   # 3/11: titolo esatto ("Violin" dava Brahms)
            a = _scegli_forte(trovati) if trovati else None      # 6/11/2026: mai un brano che parte con un intro lento
            if a:
                return a["audio_id"], f"{a.get('title')} - {a.get('display_artist')}"
        for q in ricerche[:4]:
            tutti += [a for a in cerca(q) if adatto(a)]
    except Exception as e:
        log("Ricerca di brani Instagram non riuscita:", type(e).__name__)
    # 6/11/2026: dalle ricerche solo i titoli energici (prima, senza, uno a caso dei primi 8), mai l'artista dei reel
    # recenti se ce n'e' un altro
    forti = [a for a in tutti if IG_TITOLI_FORTI.search(a.get("title", "")) or IG_ENERGIA.search(a.get("title", ""))]
    forti = [a for a in forti if a.get("display_artist") not in artisti_recenti] or forti
    try:     # 6/11/2026: prima un brano energico che parte gia' forte dal primo secondo
        a = _scegli_forte(random.sample(forti, len(forti))) if forti else None
    except Exception as e:
        log("Instagram: inizio dei brani non controllato:", e)
        a = None
    if a:
        return a["audio_id"], f"{a.get('title')} - {a.get('display_artist')}"
    if riserva:      # 6/11/2026: nessuno parte forte: la tendenza del gruppo migliore, come prima
        return riserva["audio_id"], f"{riserva.get('title')} - {riserva.get('display_artist')} [tendenza]"
    if forti:        # 6/11/2026 (integrazione): prima quelli non misurati con l'intro
        a = random.choice([x for x in forti if _APERTURE.get(x.get("audio_id")) is not False] or forti)
        return a["audio_id"], f"{a.get('title')} - {a.get('display_artist')}"
    # 6/11/2026: ultima riserva, la tendenza adatta usata meno di recente, prima i gruppi 0-2 (meglio un brano ripetuto
    # che nessun brano di Instagram); senza lista, le ultime tendenze adatte salvate nello stato
    uso = {x: i for i, x in enumerate(recenti)}
    fonte = lista or (stato or {}).get("ig_tendenze_riserva") or []
    vecchie = sorted((titolo_base(a.get("title")) in titoli, uso.get(a["audio_id"], -1), i, a)
                     for i, a in enumerate(fonte) if giusto(a) and _priorita_ig(a, i) <= 1)
    if vecchie:
        a = vecchie[0][3]
        return a["audio_id"], f"{a.get('title')} - {a.get('display_artist')} [tendenza]"
    if tutti:
        a = random.choice(tutti[:8])
        return a["audio_id"], f"{a.get('title')} - {a.get('display_artist')}"
    return None


def ricontrolla_youtube(state, creds, save):
    """3/11/2026: un'ora dopo l'orario rilegge gli Short da YouTube: rifiutato, fallito, sparito o ancora privato
    (programmazione saltata) -> avviso su Telegram."""
    from googleapiclient.discovery import build
    da_vedere = []
    for h in state["storico"][-12:]:
        yt = (h.get("risultati") or {}).get("youtube") or {}
        t = ora_slot(h.get("slot", "")) if h.get("slot") else None
        if yt.get("ok") and yt.get("id") and "controllo" not in yt and t and ora_roma() - t > datetime.timedelta(hours=1):
            da_vedere.append((h, yt))
    if not da_vedere:
        return
    try:
        api = build("youtube", "v3", credentials=creds, cache_discovery=False)
        trovati = {v["id"]: v["status"] for v in api.videos().list(
            part="status", id=",".join(yt["id"] for _, yt in da_vedere)).execute().get("items", [])}
    except Exception as e:
        log("controllo YouTube non riuscito:", e)
        return
    for h, yt in da_vedere:
        s = trovati.get(yt["id"])
        if s is None:
            yt["controllo"] = ["video non trovato su YouTube"]
        else:
            yt["controllo"] = [f"{s['uploadStatus']}: {s.get('rejectionReason') or s.get('failureReason') or ''}".strip()
                               ] if s.get("uploadStatus") in ("rejected", "failed", "deleted") else []
            if s.get("privacyStatus") != "public" and (ENV("YOUTUBE_PRIVACY") or "public") == "public":
                yt["controllo"].append(f"ancora {s.get('privacyStatus')} dopo l'orario")
        if yt["controllo"]:
            avvisi.manda(f"YouTube, Short delle {h['slot']}: " + ", ".join(yt["controllo"]))
    save()


_IG_STATO = {}     # 4/11/2026: lo stato del reel in corso, per il brano del secondo tentativo (instagram_upload)


def ricorda_brano(state, scelto):
    # 6/11/2026: finestre piu' larghe (brani 60, canzoni 40, artisti 10; prima 30 e 3)
    state["ig_audio_recenti"] = (state.get("ig_audio_recenti", []) + [scelto[0]])[-IG_FINESTRA_BRANI:]
    nome = scelto[1].replace(" [tendenza]", "")
    artista = nome.rsplit(" - ", 1)[-1]
    state["ig_artisti_recenti"] = (state.get("ig_artisti_recenti", []) + [artista])[-IG_FINESTRA_ARTISTI:]
    state["ig_titoli_recenti"] = (state.get("ig_titoli_recenti", []) + [titolo_base(nome.rsplit(" - ", 1)[0]) or "-"]
                                  )[-IG_FINESTRA_TITOLI:]


def _semina_titoli(state):
    """6/11/2026: la prima volta canzoni e artisti recenti si ricostruiscono dallo storico (musica_instagram)."""
    if "ig_titoli_recenti" in state:
        return
    try:
        nomi = [(h.get("montaggio") or {}).get("musica_instagram") for h in state.get("storico", [])]
        nomi = [n.replace(" [tendenza]", "") for n in nomi if n][-IG_FINESTRA_TITOLI:]
        state["ig_titoli_recenti"] = [titolo_base(n.rsplit(" - ", 1)[0]) for n in nomi]
        artisti = [n.rsplit(" - ", 1)[-1] for n in nomi][-IG_FINESTRA_ARTISTI:]
        if len(artisti) > len(state.get("ig_artisti_recenti", [])):
            state["ig_artisti_recenti"] = artisti
    except Exception as e:
        log("Canzoni recenti di Instagram non ricostruite:", e)
        state.setdefault("ig_titoli_recenti", [])


def brano_dello_screenshot(fid):
    """12/11/2026 (Alessandro: "utilizza la stessa musica che sta su quello screenshot... dai priorita' e cerca prima
    se puoi mettere quella musica"): (audio_id, titolo) del brano dello screenshot della frase tra quelli di Instagram,
    o None (allora si sceglie come sempre). Il brano e' una sua scelta: niente filtri di gusto o di brani recenti."""
    try:
        import musica_screenshot
        brano = musica_screenshot.di(fid)
        if not brano:
            return None
        titolo, artista = musica_screenshot.parti(brano)
        base = titolo_base(titolo)
        if not base:
            return None
        par = {"audio_type": "music", "search_query": f"{titolo} {artista}".strip(), "user_id": ENV("IG_USER_ID"),
               "access_token": ENV("META_PAGE_TOKEN")}
        trovati = [a for a in (_meta("GET", f"{GRAPH_AUDIO}/ig_audio", timeout=30, params=par).get("audio") or [])
                   if a.get("audio_id") and titolo_base(a.get("title")) == base]
        if artista:     # stesso titolo: prima l'artista giusto
            trovati.sort(key=lambda a: titolo_base(artista) not in titolo_base(a.get("display_artist")))
        if trovati:
            a = trovati[0]
            log(f"Instagram: il brano dello screenshot c'e': {a.get('title')} - {a.get('display_artist')}")
            return a["audio_id"], f"{a.get('title')} - {a.get('display_artist')} [screenshot]"
        log(f"Instagram: il brano dello screenshot ({brano}) non c'e', scelgo come sempre")
    except Exception as e:
        log("Brano dello screenshot non cercato:", e)
    return None


def brano_ig(state, scena, fid=None):
    """3/11/2026: (audio_id, titolo) di un brano DI INSTAGRAM per il reel (anche per recuperi e nuovi tentativi).
    12/11/2026: fid = id della frase: se la frase viene da un suo screenshot con un brano, prima quel brano."""
    _IG_STATO["state"] = state
    _semina_titoli(state)
    scelto = brano_dello_screenshot(fid) if fid else None
    if scelto:
        ricorda_brano(state, scelto)
        return scelto
    try:
        scelto = scegli_audio_instagram(scena, state.get("ig_audio_recenti", []), state.get("ig_artisti_recenti", []),
                                        state.get("ig_titoli_recenti", []))
    except Exception as e:
        log("Brano di Instagram non scelto:", e)
        return None
    if scelto:
        ricorda_brano(state, scelto)
    return scelto


def ricontrolla_instagram(state, save):
    """3/11/2026: rilegge i reel appena usciti da Instagram: se sono muti o di lato arriva l'avviso su Telegram."""
    token = ENV("META_PAGE_TOKEN")
    limite = (datetime.datetime.now() - datetime.timedelta(minutes=90)).isoformat()
    for h in state["storico"][-12:]:
        ig = (h.get("risultati") or {}).get("instagram") or {}
        if not ig.get("ok") or "controllo" in ig or h.get("quando", "") > limite or not str(ig.get("id", "")).isdigit():
            continue
        try:
            r = _meta("GET", f"{GRAPH_AUDIO}/{ig['id']}", timeout=30, params={"fields": "media_url,media_audio_type",
                                                                                "access_token": token})
            ig["tipo_audio"] = r.get("media_audio_type")
            if not r.get("media_url"):
                # 4/11/2026: con la musica di Instagram (brano con licenza) l'API non da' mai il file: e' normale, non
                # un errore (prima ogni reel MUSIC finiva "non leggibile"); senza musica si riprova al giro dopo
                if ig["tipo_audio"] == "MUSIC":
                    ig["controllo"] = []
                continue
            ig["controllo"] = audio_ig.controlla_pubblicato(r["media_url"])
            if ig["tipo_audio"] == "MUSIC":      # 3/11: il brano di Instagram non e' nel file scaricabile: conta solo il resto
                ig["controllo"] = [x for x in ig["controllo"] if x.startswith("video di lato")]
            elif (h.get("montaggio") or {}).get("musica_instagram"):
                if state.get("ig_avviso_brano") != h.get("quando", "")[:10]:     # questo avviso al massimo 1 al giorno
                    state["ig_avviso_brano"] = h.get("quando", "")[:10]
                    ig["controllo"].append("brano di Instagram non applicato (resta l'audio del file"
                                           + (", caricato senza link)" if ig.get("metodo") == "diretto" else ")"))
            if ig["controllo"] and (h.get("montaggio") or {}).get("formato") != "parlato":
                avvisi.manda(f"Instagram, reel delle {h.get('slot', '?')}: " + ", ".join(ig["controllo"]))
        except Exception as e:
            log("controllo Instagram non riuscito:", e)
    save()


def _aspetta_contenitore(V, cid, token):
    """Attende l'elaborazione del contenitore Instagram (max ~10 minuti): FINISHED, ERROR o l'ultimo stato."""
    st = {}
    for _ in range(60):
        try:
            st = requests.get(f"{V}/{cid}", params={"fields": "status_code,status", "access_token": token},
                              timeout=30).json()
        except requests.exceptions.RequestException:
            st = {}
        if st.get("status_code") in ("FINISHED", "ERROR", "EXPIRED"):
            break
        time.sleep(10)
    if st.get("status_code") == "ERROR":
        log("instagram: contenitore in errore:", st)
    return st.get("status_code")


def link_temporaneo(path):
    """4/11/2026: carica il video in Drive ('Instagram temporanei') e lo rende leggibile con il link, cosi'
    Instagram lo scarica da li' (video_url). (id, indirizzo); togli_link() lo chiude e lo mette nel cestino."""
    from googleapiclient.http import MediaFileUpload
    for i in range(4):     # 4/11/2026: il reel delle 10 e' uscito senza musica per un SSL EOF di Drive: si riprova
        d, fid = None, None
        try:
            d = Drive(google_creds())
            fid = d.api.files().create(body={"name": os.path.basename(path),
                                             "parents": [d.cartella("Instagram temporanei")]},
                                       media_body=MediaFileUpload(path, mimetype="video/mp4", resumable=True),
                                       fields="id").execute(num_retries=3)["id"]
            d.api.permissions().create(fileId=fid, body={"type": "anyone", "role": "reader"}).execute(num_retries=3)
            return (d, fid), f"https://drive.usercontent.google.com/download?id={fid}&export=download&confirm=t"
        except Exception as e:
            if fid:
                togli_link((d, fid))
            if i == 3:
                raise
            log("instagram: Drive non raggiungibile per il link temporaneo, riprovo:", e)
            time.sleep(10 * (i + 1))


def togli_link(temp):
    """Toglie la condivisione e mette il file nel cestino di Drive (mai cancellato per sempre)."""
    if not temp:
        return
    from googleapiclient.errors import HttpError
    d, fid = temp
    for _ in range(3):
        try:
            try:      # 4/11/2026: se la condivisione era gia' tolta si mette comunque nel cestino
                d.api.permissions().delete(fileId=fid, permissionId="anyoneWithLink").execute()
            except HttpError as e:
                if e.resp.status != 404:
                    raise
            d.api.files().update(fileId=fid, body={"trashed": True}).execute()
            return
        except Exception as e:
            log("instagram: link temporaneo non chiuso, riprovo:", e)
            time.sleep(5)


def pulisci_temporanei(drive):
    """4/11/2026: un link temporaneo rimasto aperto (rete caduta a meta') si chiude al lavoro dopo: i video di
    Alessandro non restano mai condivisi con il link per piu' di un paio d'ore."""
    limite = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
    q = f"'{drive.cartella('Instagram temporanei')}' in parents and trashed = false and createdTime < '{limite}'"
    rimasti = drive.api.files().list(q=q, fields="files(id)").execute().get("files", [])
    for f in rimasti:
        togli_link((drive, f["id"]))
    if rimasti:
        log(f"Instagram: {len(rimasti)} link temporanei rimasti aperti, chiusi e nel cestino")


def con_traccia(path):
    """4/11/2026: la musica di Instagram si applica solo se il video ha una traccia audio (senza: errore 2207082):
    se manca se ne aggiunge una muta."""
    if overlay.ha_audio(path):
        return path
    dst = os.path.splitext(path)[0] + "_traccia.mp4"
    subprocess.run([overlay.FFMPEG, "-y", "-v", "error", "-i", path, "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                    "-map", "0:v:0", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-shortest",
                    "-movflags", "+faststart", dst], check=True, capture_output=True, timeout=300)
    return dst


ULTIMO_IG = {}     # 4/11/2026: come e' uscito l'ultimo reel Instagram (metodo, brano se cambiato): finisce nei risultati
# 6/11/2026 (Alessandro: su ogni social solo la musica di quel social, mai la nostra, nemmeno di riserva): i file con la
# NOSTRA musica (versione_meta) escono su Instagram solo col brano di Instagram sopra (video_volume 1). Senza brano o
# col caricamento diretto (che lo ignora) si sentiva la nostra traccia: ora errore e si riprova al giro dopo
NOSTRA_MUSICA = set()

# 6/11/2026: REEL DI PROVA di Instagram (trial reels, Graph API trial_params, documentato da Meta per tutte le versioni
# dal 3/12/2025) su 5 reel su 10, a orari alterni che si scambiano ogni giorno. Instagram li mostra solo a chi NON lo
# segue: finche' sono di prova NON compaiono sul suo profilo e non arrivano ai follower; se nelle prime 72 ore vanno
# bene li pubblica da solo per tutti (graduation_strategy SS_PERFORMANCE).
# ACCESI: si' di Alessandro del 6/11/2026 ("Si', su meta' dei reel"). Partono solo se prova_ig_ferma() non trova motivi
# contro (tra cui: almeno 200 follower su Instagram). False = mai reel di prova.
# In stato.json, risultati instagram: "prova" true/false e "prova_rifiutata" col motivo (allora lo stesso reel esce
# subito normale: mai perso, mai doppio).
PROVA_IG = True
PROVA_IG_PARAMETRI = json.dumps({"graduation_strategy": "SS_PERFORMANCE"})
PROVA_IG_FOLLOWER = 200      # guide 2025-26: almeno 200 follower per gli account professionali (altre dicono 1.000)
PROVA_IG_PAUSA_ORE = 24      # dopo un rifiuto di Instagram (es. vuole piu' follower): niente prove per un giorno
PROVA_IG_DAL = "2026-11-06"  # reel di prova controllati da questa data: spostarla in avanti riaccende dopo uno stop
PROVA_IG_NON_IDONEO = re.compile(r"follower|eligib|maximum number of trial", re.I)   # account non (ancora) idoneo
# 6/11/2026 (Alessandro: "100 foto al giorno"): negli orari delle foto meta' e meta' (fisso per orario, come
# SCRITTE_PROVA) il reel con 6 foto che scorrono e il photo dump a tempo di musica (foto_giornata.make_rapide)
FORMATI_FOTO = ("dieci_foto", "foto_rapide")
COPERTINA_FORMATI = tuple(FORMATI_10) + FORMATI_FOTO     # la frase c'e' dal primo all'ultimo fotogramma


def formato_foto(slot):
    """6/11/2026: dieci_foto o foto_rapide per l'orario delle foto: fino a FORMATI_PROVA_FINO meta' e meta' (sempre lo
    stesso per lo stesso orario); dopo, coi pesi dei formati di pesi.json se ci sono (1 se mancano)."""
    r = random.Random(f"foto {slot}")
    if str(slot)[:10] < FORMATI_PROVA_FINO:
        # 6/11/2026 (integrazione, revisione delle foto rapide): alternanza fissa invece della moneta, ogni giorno un reel
        # per formato e alle 12 e alle 18 a giorni alterni (con la moneta uscivano giorni con due reel uguali)
        try:
            d = datetime.date.fromisoformat(str(slot)[:10])
            return FORMATI_FOTO[(d.toordinal() + str(slot).endswith("18:00")) % 2]
        except ValueError:
            return r.choice(FORMATI_FOTO)
    try:
        pesi_f = json.load(open(os.path.join(HERE, "pesi.json"), encoding="utf-8")).get("formati", {})
    except Exception:
        pesi_f = {}
    return r.choices(FORMATI_FOTO, weights=[max(0.05, float(pesi_f.get(f, 1.0))) for f in FORMATI_FOTO])[0]


class ProvaNonUscita(RuntimeError):
    """Il reel di prova non e' uscito ma il contenitore e' pronto e NON pubblicato: si puo' rifare normale."""


def prova_ig_ferma(state, adesso=None):
    """6/11/2026 (revisione): perche' NON fare adesso un reel di prova (None = si puo'). Si fermano da soli se:
    Instagram ha meno di PROVA_IG_FOLLOWER follower (docs/follower.json, aggiornato ogni sera); Instagram ne ha
    rifiutato uno nelle ultime PROVA_IG_PAUSA_ORE ore; un reel di prova e' uscito SENZA il brano di Instagram
    (tipo_audio letto da ricontrolla_instagram dopo 90': si sentirebbe la nostra musica) o non si e' riusciti a
    controllarlo in 24 ore (questi due li spengono finche' PROVA_IG_DAL non va avanti); il controllo di un reel di prova
    di piu' di 6 ore fa non e' ancora arrivato (si aspetta)."""
    try:
        fol = json.load(open(os.path.join(HERE, "docs", "follower.json"), encoding="utf-8"))
        n = [x["instagram"] for x in fol if x.get("instagram")][-1]
        if n < PROVA_IG_FOLLOWER:
            return f"Instagram ha {n} follower (ne servono almeno {PROVA_IG_FOLLOWER})"
    except Exception as e:
        log("reel di prova: follower non letti, decido senza:", e)
    adesso = adesso or datetime.datetime.now()
    pausa = (adesso - datetime.timedelta(hours=PROVA_IG_PAUSA_ORE)).isoformat(timespec="minutes")
    for h in (state or {}).get("storico") or []:
        ig, quando = (h.get("risultati") or {}).get("instagram") or {}, h.get("quando") or ""
        chi = h.get("slot") or quando
        if quando < PROVA_IG_DAL:
            continue
        if ig.get("prova_rifiutata") and not ig.get("prova") and quando > pausa:
            return f"Instagram ha rifiutato il reel di prova delle {chi}: pausa di un giorno"
        if not (ig.get("prova") and ig.get("ok") and str(ig.get("id", "")).isdigit()):
            continue
        tipo, ore = ig.get("tipo_audio"), (adesso - datetime.datetime.fromisoformat(quando)).total_seconds() / 3600
        if tipo and tipo != "MUSIC":
            return f"SPENTI: il reel di prova delle {chi} e' uscito senza il brano di Instagram ({tipo})"
        if not tipo and ore > 24:
            return f"SPENTI: il brano del reel di prova delle {chi} non si e' mai potuto controllare"
        if not tipo and ore > 6:
            return f"aspetto il controllo del brano del reel di prova delle {chi}"
    return None


def reel_di_prova(slot, state=None):
    """6/11/2026: True per meta' degli orari del giorno (orari alterni, scambiati ogni giorno), se prova_ig_ferma non
    trova motivi per fermarli. In caso di errore: reel normale."""
    t = ora_slot(slot)
    if not PROVA_IG or t is None or t.hour not in orario.ORE or (orario.ORE.index(t.hour) + t.toordinal()) % 2:
        return False
    try:
        motivo = prova_ig_ferma(state)
    except Exception as e:
        motivo = f"controlli non riusciti ({e})"
    if motivo:
        log("Instagram: niente reel di prova:", motivo)
    return not motivo


def copertina_reel(path, durata=None):
    """6/11/2026: copertina di Instagram (thumb_offset, ms) per i reel da 10 s: il fotogramma piu' nitido e ben
    esposto CON IL VISO (overlay.scegli_copertina); la frase c'e' sempre. Prima questi reel non la sceglievano e la
    copertina era il primo fotogramma. None se non riesce (resta il primo fotogramma, come prima)."""
    try:
        durata = float(durata or overlay.probe(path)[0])
        frames = overlay.extract_frames(path, durata, n=8)
        return overlay.scegli_copertina(frames, durata) if frames else None
    except Exception as e:
        log("copertina non scelta (resta il primo fotogramma):", e)
        return None


def _crea_reel(V, ig, token, dati, **extra):
    """6/11/2026: crea il contenitore del reel. Se Instagram rifiuta il reel di prova (trial_params) si riprova subito
    senza share_to_feed (non se l'account non e' idoneo) e poi come reel NORMALE (lo stesso reel, mai perso); se
    rifiuta la copertina, senza."""
    crea = lambda d: _meta("POST", f"{V}/{ig}/media", data={**d, **extra, "access_token": token})
    r = crea(dati)
    if "id" not in r and "trial_params" in dati:
        log("instagram: reel di prova rifiutato:", r)
        motivo = str(r.get("error", r))
        ULTIMO_IG["prova_rifiutata"] = motivo[:300]
        # 6/11/2026 (revisione): account non idoneo (pochi follower...): inutile riprovare senza share_to_feed
        if "share_to_feed" in dati and not PROVA_IG_NON_IDONEO.search(motivo):
            r = crea({k: v for k, v in dati.items() if k != "share_to_feed"})
            if "id" in r:
                del dati["share_to_feed"]
                ULTIMO_IG["senza_feed"] = True
        if "id" not in r:
            del dati["trial_params"]
            dati["share_to_feed"] = "true"
            ULTIMO_IG["prova"] = False
            log("instagram: lo pubblico come reel normale")
            r = crea(dati)
    if "id" not in r and dati.pop("thumb_offset", None) is not None:
        log("instagram: copertina rifiutata, resta il primo fotogramma:", r)
        r = crea(dati)
    return r


def _stato_contenitore(V, cid, token):
    try:
        return _meta("GET", f"{V}/{cid}", params={"fields": "status_code", "access_token": token}).get("status_code")
    except Exception as e:
        log("instagram: stato del contenitore non letto:", e)
        return None


def instagram_upload(path, cap, audio_id=None):
    """audio_id: brano nativo di Instagram (allora path e' il video SENZA musica). 6/11/2026: cap["prova_ig"] = reel
    di prova, solo col brano di Instagram (audio_id) e se prova_ig_ferma lo permette ancora (anche nei recuperi e nei
    nuovi tentativi); se la prova non esce, lo stesso reel esce subito come reel normale."""
    prova = PROVA_IG and bool(cap.get("prova_ig")) and bool(audio_id)
    if prova:
        try:
            motivo = prova_ig_ferma(_IG_STATO.get("state"))
        except Exception as e:
            motivo = f"controlli non riusciti ({e})"
        if motivo:
            log("instagram: reel normale, niente prova:", motivo)
            prova = False
    try:
        return _instagram_reel(path, cap, audio_id, prova)
    except ProvaNonUscita as e:
        log("instagram: il reel di prova non e' uscito, lo pubblico normale:", e)
        pid = _instagram_reel(path, cap, audio_id, False)
        ULTIMO_IG["prova_rifiutata"] = str(e)[:200]
        return pid


def _instagram_reel(path, cap, audio_id=None, prova=False):
    # 6/11/2026 (regola 3): un file con la nostra musica esce solo col brano di Instagram sopra, mai da solo
    nostra = os.path.abspath(path) in NOSTRA_MUSICA
    if nostra and not audio_id:
        raise RuntimeError("nessun brano di Instagram: il video ha la nostra musica, non esce (si riprova)")
    token, ig = ENV("META_PAGE_TOKEN"), ENV("IG_USER_ID")
    ULTIMO_IG.clear()
    ULTIMO_IG["prova"] = bool(prova)
    dati = {"media_type": "REELS", "caption": testo_breve(cap), "share_to_feed": "true"}
    if prova:
        dati["trial_params"] = PROVA_IG_PARAMETRI
    if audio_id:
        # 3/11/2026: video_volume 1 (minimo ammesso dalla documentazione Meta, 1-100): con 0 il brano veniva ignorato
        dati["audio_configuration"] = json.dumps({"audio_id": audio_id, "audio_volume": 100, "video_volume": 1})
    if cap.get("copertina_ms") is not None:
        dati["thumb_offset"] = str(cap["copertina_ms"])
    if cap.get("audio_nome") and not audio_id:
        dati["audio_name"] = cap["audio_nome"]
    V = GRAPH_AUDIO if audio_id else GRAPH
    cid, temp = None, None
    if audio_id:
        # 4/11/2026: la musica di Instagram (audio_configuration) e' documentata solo col caricamento da indirizzo
        # (video_url): col caricamento a pezzi (resumable) Instagram la ignorava quasi sempre. Il video passa da un
        # link temporaneo di Drive (provato: contenitore FINISHED in 20 s), tolto subito dopo l'uscita.
        # Due tentativi, il secondo con un altro brano di tendenza: il caricamento diretto (ultima riserva) fa
        # sentire la nostra traccia, che Alessandro non vuole.
        try:
            path = con_traccia(path)
        except Exception as e:
            log("instagram: traccia audio non aggiunta:", e)
        for tentativo in range(2):
            try:
                temp, url = link_temporaneo(path)
                r = _crea_reel(V, ig, token, dati, video_url=url)
                cid = r.get("id")
                if not cid:
                    log("instagram: contenitore da link non creato:", r)
                elif _aspetta_contenitore(V, cid, token) != "FINISHED":
                    log("instagram: contenitore da link non pronto")
                    cid = None
                    if dati.pop("trial_params", None):     # 6/11/2026: forse e' la prova: il tentativo dopo e' normale
                        dati["share_to_feed"] = "true"
                        ULTIMO_IG.update(prova=False, prova_rifiutata="contenitore di prova non pronto")
            except Exception as e:
                log("instagram: link temporaneo non riuscito:", e)
                cid = None
            if cid:
                ULTIMO_IG["metodo"] = "link"
                break
            togli_link(temp)
            temp = None
            if tentativo == 0:
                s = _IG_STATO.get("state") or {}
                try:     # 4/11/2026: anche il secondo brano mai tra i recenti, mai lo stesso artista degli ultimi 3
                    altro = scegli_audio_instagram(None, tuple(s.get("ig_audio_recenti", [])) + (audio_id,),
                                                   s.get("ig_artisti_recenti", []))
                except Exception as e:
                    altro = None
                    log("instagram: secondo brano non scelto:", e)
                if altro and s:
                    ricorda_brano(s, altro)
                if altro:
                    log("instagram: riprovo con un altro brano di tendenza:", altro[1])
                    ULTIMO_IG["brano"] = altro[1]
                    dati["audio_configuration"] = json.dumps({"audio_id": altro[0], "audio_volume": 100,
                                                              "video_volume": 1})
                time.sleep(20)
        if not cid and nostra:     # 6/11/2026: mai il caricamento diretto con la nostra musica (vedi NOSTRA_MUSICA)
            raise RuntimeError("due link non riusciti: niente caricamento diretto con la nostra musica, si riprova")
        if not cid:
            log("instagram: link non riuscito due volte, provo il caricamento diretto")
    if not cid:
        ULTIMO_IG["metodo"] = "diretto"
        r = _crea_reel(V, ig, token, dati, upload_type="resumable")
        if "id" not in r and dati.pop("audio_name", None):     # il nome dell'audio non deve mai fermare il reel
            log("instagram: nome dell'audio rifiutato:", r)
            r = _crea_reel(V, ig, token, dati, upload_type="resumable")
        if "id" not in r:
            togli_link(temp)
            raise RuntimeError(r)
        cid = r["id"]
        up = _rupload(r.get("uri", f"https://rupload.facebook.com/ig-api-upload/v23.0/{cid}"), token, path)
        if up.get("success") is False or "error" in up:
            togli_link(temp)
            raise RuntimeError(up)
        if _aspetta_contenitore(V, cid, token) == "ERROR":
            togli_link(temp)
            if "trial_params" in dati:      # 6/11/2026: contenitore in errore = mai uscito: si rifa' normale
                raise ProvaNonUscita(f"contenitore di prova in errore ({cid})")
            raise RuntimeError(f"contenitore Instagram in errore ({cid})")
    try:
        pub = _ig_pubblica(V, ig, cid, token)
    finally:
        togli_link(temp)
    if "id" not in pub and "trial_params" in dati and pub.get("error"):
        # 6/11/2026: reel di prova rifiutato all'uscita: si rifa' normale SOLO se Instagram conferma che non e' uscito
        time.sleep(15)
        stato = _stato_contenitore(V, cid, token)
        if stato in ("FINISHED", "ERROR", "EXPIRED"):
            raise ProvaNonUscita(pub)
        if stato == "PUBLISHED":          # uscito comunque: si ritrova il post (come in _ig_pubblica), mai doppio
            pub = _ig_pubblica(V, ig, cid, token)
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
    import avvisi
    if not avvisi.AVVISI_TELEGRAM:     # 6/11/2026 (Alessandro): su Telegram solo le visualizzazioni delle 8
        raise RuntimeError("Telegram: arrivano solo le visualizzazioni, video per TikTok non mandato")
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


def tiktok_bozza(path, cap, target):
    """29/10/2026 (Alessandro: "facciamo le bozze TikTok dall'app"): il reel (SENZA musica, salvo voce/suono vero)
    arriva nelle bozze della sua app TikTok; lui sceglie un suono di tendenza e pubblica. L'API delle bozze non
    accetta la descrizione: gliela mandiamo su Telegram, da copiare (un messaggio a parte, solo il testo)."""
    try:
        pid = tiktok_upload(path, cap)
    except Exception as e:
        log("TikTok: bozza non inviata:", e)
        return {"ok": False, "errore": str(e)[:300]}
    log("TikTok: bozza inviata all'app", pid)
    if ENV("TELEGRAM_BOT_TOKEN") and ENV("TELEGRAM_CHAT_ID"):
        try:
            import avvisi
            avvisi.manda(f"TIKTOK - BOZZA PRONTA\nReel delle {target:%H:%M}\nApri TikTok > notifiche/bozze\n"
                         "Aggiungi un suono di tendenza\nIncolla il testo qui sotto e pubblica")
            avvisi.manda(testo_breve(cap))
        except Exception as e:
            log("Telegram (testo TikTok) non riuscito:", e)
    return {"ok": True, "id": pid, "bozza": True}


# ------------------------------------------------------------------ orchestrazione
def versione_meta(path, recenti, scena=None):
    """La versione del reel per Facebook/Instagram: stessa immagine, musica nostra. None se non riesce
    (allora su quelle piattaforme non si pubblica: mai la musica della Raccolta YouTube fuori da YouTube)."""
    try:
        dst = os.path.splitext(path)[0] + "_meta.mp4"
        tagli = audio_ig.stacchi(path)
        provati = list(recenti)
        for _ in range(3):        # 3/11/2026: se il file esce muto o difettoso si riprova con un altro brano
            m = scegli_musica(None, provati, scena, nostra=True)
            if not m or not audio_ig.ammesso(m):
                break
            provati.append(os.path.basename(m))
            overlay.cambia_musica(path, m, dst, audio_ig.punto_inizio(m, tagli))
            difetti = audio_ig.controlla(dst)
            if not difetti:
                NOSTRA_MUSICA.add(os.path.abspath(dst))     # 6/11/2026: su Instagram solo col brano di Instagram
                return dst, os.path.basename(m)
            log("audio Instagram scartato:", os.path.basename(m), difetti)
    except Exception as e:
        log("versione per Facebook/Instagram non riuscita:", e)
    avvisi.manda("Instagram: nessun audio valido per questo reel, non pubblicato")
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
            if name == "instagram":      # 4/11/2026: metodo (link/diretto) e brano davvero usato, per i controlli
                results[name].update(ULTIMO_IG)
            log(name, "pubblicato")
        except Exception as e:
            results[name] = {"ok": False, "errore": str(e)[:500]}
            log(name, "ERRORE:", e)
            traceback.print_exc()
    return results


# 6/11/2026 (100 punti, gruppo 2, punto 34): al massimo UN video sorgente orizzontale ogni 10 reel. Nel reel 9:16 un video
# orizzontale si vede tagliato al centro (resta un terzo della larghezza, ingrandito): se uno e' uscito negli ultimi 10
# reel gli orizzontali aspettano, ma solo se c'e' altro da pubblicare (mai un orario saltato per questo)
ORIZZONTALI_OGNI = 10
ORIENTAMENTI = {}      # id della clip d'archivio -> orizzontale, scoperto scaricandola come clip extra in questo giro
ORIENTAMENTI_NOTI = {}  # stato.json archivio_usi (id -> {"orizzontale", "nera", "fallimenti"...}), per le clip extra
NERE = set()           # 6/11/2026 (revisione): clip extra scaricate in questo giro e risultate tutte nere


def orizzontale(path):
    """True se il video si vede in orizzontale (piu' largo che alto, contando la rotazione salvata dal telefono),
    False se verticale o quadrato, None se non si legge."""
    try:
        info = subprocess.run([overlay.FFMPEG, "-hide_banner", "-i", path], capture_output=True, text=True,
                              errors="ignore", timeout=60).stderr
        m = re.search(r"Video:[^\n]*?\b(\d{2,5})x(\d{2,5})\b", info)
        if not m:
            return None
        w, h = int(m.group(1)), int(m.group(2))
        if overlay.rotazione(path) in (90, 270):
            w, h = h, w
        return w > h * 1.05
    except Exception as e:
        log("Orientamento del video non letto:", e)
        return None


def _nera(path):
    """6/11/2026 (revisione, punto 14): True se il video e' tutto nero, bianco o tutto uguale (formati_nuovi.clip_nera);
    False se non lo e' o non si sa (come prima)."""
    try:
        import formati_nuovi
        return formati_nuovi.clip_nera(path) is True
    except Exception as e:
        log("Controllo del video nero non riuscito:", e)
        return False


def _orizz(x):
    """Orientamento noto di un video in coda (analisi) o di una clip d'archivio (proprieta' su Drive "1"/"0" o
    archivio_usi): True orizzontale, False verticale, None se non si sa ancora (conta come verticale)."""
    v = (x or {}).get("orizzontale")
    if isinstance(v, str):
        return {"1": True, "0": False}.get(v)
    return v if isinstance(v, bool) else None


def orizzontale_recente(state, n=ORIZZONTALI_OGNI):
    """True se tra gli ultimi n reel ce n'e' gia' uno fatto da un video orizzontale (montaggio.orizzontale).
    ORIZZONTALI_OGNI = 0 spegne la regola."""
    if n <= 0:
        return False
    ultimi = [h for h in state.get("storico", []) if h.get("slot") and not h.get("riprova")][-n:]
    return any((h.get("montaggio") or {}).get("orizzontale") is True for h in ultimi)


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
    oriz = orizzontale(src)          # 6/11/2026 (punto 34): per rinviare i video orizzontali (1 ogni 10 reel)
    try:     # 6/11/2026 (revisione, punto 14): tutto nero (telefono in tasca, obiettivo coperto)? Gli 8 fotogrammi
        import formati_nuovi         # dell'analisi e, solo se sono tutti vuoti, i fotogrammi chiave di tutto il video
        nero = bool(frames) and formati_nuovi._pezzo_nero(frames) and _nera(src)
    except Exception as e:
        log("Controllo del video nero non riuscito:", e)
        nero = False
    os.remove(src)
    lato_corto = min(frames[0].shape[:2]) if frames else 0
    return {"nome": v["name"], "scena": sc, "sicurezza": conf, "motivo": motivo, "lato_corto": lato_corto,
            "orizzontale": oriz, **({"nero": True} if nero else {}),
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


def scegli_video(videos, analisi, slot_ora, evita_orizzontali=False):
    """Il video NUOVO giusto per questo orario (stessa fascia della giornata, poi fasce vicine, poi qualsiasi).
    I video nuovi hanno sempre la precedenza: l'archivio si usa solo se la coda e' vuota (vedi main).
    6/11/2026 (Alessandro: "dai sempre priorita' ai nuovi contenuti piuttosto che ai vecchi"): tra quelli in coda esce
    il PIU' RECENTE (prima il piu' vecchio).
    6/11/2026 (punto 34): evita_orizzontali -> prima i video non orizzontali (se ci sono solo quelli, uno di quelli)."""
    if not videos:
        return None
    recente = lambda lista: max(lista, key=lambda v: v.get("createdTime") or "")
    momenti = [v for v in videos if analisi.get(v["id"], {}).get("momento")]
    if momenti:                                # MOMENTO: e' una cosa di oggi, esce al primo orario
        return recente(momenti)
    if evita_orizzontali:
        videos = [v for v in videos if _orizz(analisi.get(v["id"])) is not True] or videos
    if slot_ora is None:                       # esecuzione manuale
        return recente(videos)
    f = orario.fascia(slot_ora)
    for fascia in [f] + VICINE.get(f, []):
        adatti = [v for v in videos if fascia_video(analisi.get(v["id"], {})) == fascia]
        if adatti:
            return recente(adatti)
    return recente(videos)                     # nessun orario resta vuoto


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
    # 31/10/2026: una volta su due tra le clip che hanno fatto piu' visualizzazioni (pesi.json, da report.py)
    try:
        forti = set(json.load(open(os.path.join(HERE, "pesi.json"), encoding="utf-8")).get("clip_forti", []))
    except Exception:
        forti = set()
    scelte = [c for c in archivio if c.get("nome") in forti]
    if scelte and random.random() < 0.5:
        return min(scelte, key=chiave)
    return min(archivio, key=chiave)


SOSPESI = os.path.join(HERE, "_tiktok_sospesi")   # 4/11/2026: versioni TikTok che Drive non ha accettato


def metti_in_sospeso(tt, nome, dati):
    """Il file TikTok non salvato su Drive resta sulla macchina e si riprova al giro dopo (prima era perso)."""
    if not tt or not os.path.exists(tt):
        return
    try:
        os.makedirs(SOSPESI, exist_ok=True)
        shutil.copy(tt, os.path.join(SOSPESI, nome))
        json.dump(dati, open(os.path.join(SOSPESI, nome + ".json"), "w", encoding="utf-8"), ensure_ascii=False)
        log(f"TikTok: {nome} tenuto da parte, lo risalvo su Drive al prossimo giro")
    except Exception as e:
        log("TikTok: copia di riserva non riuscita:", e)


def salva_sospesi(drive):
    if not os.path.isdir(SOSPESI):
        return
    for nome in sorted(f for f in os.listdir(SOSPESI) if f.endswith(".mp4")):
        p = os.path.join(SOSPESI, nome)
        try:
            d = json.load(open(p + ".json", encoding="utf-8"))
            drive.salva_tiktok(p, nome, d["testo"], d["slot"], d["voce"])
            os.remove(p + ".json")      # copia temporanea della macchina di GitHub: il video ora e' su Drive
            os.remove(p)
            log(f"TikTok: {nome} salvato su Drive al secondo giro")
        except Exception as e:
            log(f"TikTok: {nome} ancora non salvato su Drive:", e)


def recupera_instagram(state, drive, work, save):
    """31/10/2026: se il lavoro viene interrotto mentre aspetta l'ora esatta (YouTube e' gia' programmato, Instagram no)
    al giro dopo Instagram si recupera dalla versione 1080p senza musica salvata per TikTok."""
    for h in [x for x in state["storico"] if x.get("in_corso") and x.get("frase_dati")]:
        h.pop("in_corso")
        if "instagram" not in PLATFORMS or "instagram" in (h.get("risultati") or {}) or fermo(state, "instagram"):
            continue
        nome = f"{ora_slot(h['slot']):%Y-%m-%d %H%M} - {h['frase']}.mp4"
        try:
            q = f"'{drive.cartella(CARTELLA_TIKTOK)}' in parents and name = '{nome}' and trashed = false"
            trovati = drive.api.files().list(q=q, fields="files(id)").execute().get("files", [])
            if not trovati:
                log("Recupero Instagram: video non trovato", nome)
                continue
            path = os.path.join(work, "recupero.mp4")
            drive.download(trovati[0]["id"], path, folder=CARTELLA_TIKTOK)
            scelto = None
            if (h.get("montaggio") or {}).get("formato") not in ("parlato", "momento"):   # il file TikTok e' muto
                path, brano = versione_meta(path, state.get("musica_recenti_meta", []), h.get("scena"))
                if not path:
                    continue
                h["frase_dati"]["audio_nome"] = audio_ig.nome_audio(brano)
                h.setdefault("montaggio", {})["musica_meta"] = brano
                scelto = brano_ig(state, h.get("scena"), h.get("frase"))   # 3/11/2026: anche qui il brano DI INSTAGRAM
                if scelto:
                    h["montaggio"]["musica_instagram"] = scelto[1]
            pid = instagram_upload(path, h["frase_dati"], scelto[0] if scelto else None)
            h.setdefault("risultati", {})["instagram"] = {"ok": True, "id": pid, "recuperato": True, **ULTIMO_IG}
            if ULTIMO_IG.get("brano"):
                h["montaggio"]["musica_instagram"] = ULTIMO_IG["brano"]
            log(f"Instagram recuperato per l'orario {h['slot']}")
        except Exception as e:
            log("Recupero Instagram non riuscito:", e)
            if "nostra musica" in str(e) and h.get("recuperi", 0) < 2:   # 6/11/2026 (revisione): nessun brano di
                h["in_corso"] = True                                       # Instagram: si riprova al giro dopo
                h["recuperi"] = h.get("recuperi", 0) + 1
            else:
                h.setdefault("risultati", {})["instagram"] = {"ok": False, "errore": str(e)[:200]}
        save()


def carica_stato():
    """4/11/2026: stato.json illeggibile (rovinato) -> l'ultima versione salvata su GitHub, mai uno stato vuoto
    (che ripubblicherebbe frasi, video e orari gia' usciti)."""
    if not os.path.exists(STATE):
        return {}
    try:
        return json.load(open(STATE, encoding="utf-8-sig"))
    except ValueError as e:
        log("stato.json illeggibile, riprendo l'ultima versione salvata:", e)
        for rif in ("HEAD", "HEAD~1", "HEAD~2"):
            r = subprocess.run(["git", "-C", HERE, "show", f"{rif}:stato.json"], capture_output=True)
            try:
                return json.loads(r.stdout.decode("utf-8-sig"))
            except ValueError:
                continue
        raise


def main():
    slot =sys.argv[1] if len(sys.argv) > 1 else "manuale"
    slot_ora = None if "manuale" in slot else slot.split()[-1]     # es. "09:45"
    frasi = json.load(open(FRASI, encoding="utf-8"))
    state = carica_stato()
    for k, v in (("usate", []), ("storico", []), ("riprova", []), ("slot_fatti", []), ("musica_recenti", []),
                 ("frasi_usate", []), ("temi_recenti", []), ("analisi", {}), ("archivio_usi", {})):
        state.setdefault(k, v)

    def save():
        # 4/11/2026: prima su un file a parte, poi al suo posto: se il lavoro viene fermato a meta' scrittura
        # stato.json resta quello di prima (un file tagliato faceva perdere tutta la memoria del sistema)
        tmp = STATE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=1, default=str)
        os.replace(tmp, STATE)

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
            if not job.get("pronti_id"):
                raise RuntimeError("il reel non era stato salvato in Pronti")
            drive.download(job["pronti_id"], path, folder="Pronti")
        except Exception as e:
            log("riprova: download fallito", e)
            # 4/11/2026: prima un reel non scaricabile (mai salvato, o gia' nel cestino dopo 7 giorni) restava per
            # sempre tra quelli da riprovare e rallentava ogni giro: ora conta come tentativo
            job["tentativi"] += 1
            if not job.get("pronti_id") or job["tentativi"] >= MAX_TENTATIVI:
                state["riprova"].remove(job)
            save()
            continue
        job["piattaforme"] = [x for x in job["piattaforme"] if x in PLATFORMS   # solo quelle ancora attive
                              and not fermo(state, x)]
        path_meta = None
        parlato = job["frase"].get("tema") == "parlato"
        try:      # 4/11/2026: il file in Pronti e' il 4K di YouTube: Instagram/Facebook vogliono la versione 1080p
            if parlato and MUSICA_NOSTRA & set(job["piattaforme"]):   # reel parlato: la sua voce, niente musica
                path_meta = overlay.versione_social(path, os.path.join(work, "riprova_social.mp4"), audio=True)
            elif MUSICA_NOSTRA & set(job["piattaforme"]):
                base = overlay.versione_social(path, os.path.join(work, "riprova_social.mp4"), audio=False)
                path_meta, _ = versione_meta(base, state.get("musica_recenti_meta", []))
        except Exception as e:
            log("riprova: versione 1080p non riuscita:", e)
        scelto = (brano_ig(state, None, (job.get("frase") or {}).get("id"))
                  if "instagram" in job["piattaforme"] and path_meta and not parlato else None)
        res = publish_all(path, job["frase"], creds, job["piattaforme"], path_meta,   # 3/11: brano DI INSTAGRAM
                          ig_nativo=(path_meta, scelto[0]) if scelto else None)
        job["tentativi"] += 1
        job["piattaforme"] = [p for p, r in res.items() if not r["ok"]]
        state["storico"].append({"quando": datetime.datetime.now().isoformat(timespec="minutes"),
                                 "riprova": job["frase"]["id"], "risultati": res})
        if not job["piattaforme"] or job["tentativi"] >= MAX_TENTATIVI:
            state["riprova"].remove(job)
        save()

    if not DRY:
        salva_sospesi(drive)            # prima del recupero di Instagram, che parte proprio dal file TikTok
        recupera_instagram(state, drive, work, save)
        ricontrolla_instagram(state, save)
        ricontrolla_youtube(state, creds, save)
        try:
            pulisci_temporanei(drive)
        except Exception as e:
            log("pulizia dei link temporanei non riuscita:", e)

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
    videos = con_tentativi(drive.list_videos, "Lettura della coda", drive)
    for v in videos:
        vecchia = state["analisi"].get(v["id"])
        # 4/11/2026: un'analisi fallita (spesso per la rete) si rifa' al giro dopo, una volta: prima il video restava
        # per sempre "casa / ufficio" e usciva con frase e orario sbagliati
        if vecchia is None or (vecchia.get("analisi_fallita") == 1 and not vecchia.get("fallimenti")):
            try:
                state["analisi"][v["id"]] = analizza_video(drive, v, work)
                log("Analizzato:", state["analisi"][v["id"]])
            except Exception as e:
                log("Analisi fallita per", v["name"], e)
                state["analisi"][v["id"]] = {"nome": v["name"], "scena": "casa", "fascia": "ufficio",
                                             "errore": str(e)[:200], "caricato": v["createdTime"],
                                             "analisi_fallita": (vecchia or {}).get("analisi_fallita", 0) + 1}
    for v in list(videos):
        a = state["analisi"].get(v["id"], {})
        if 0 < a.get("lato_corto", 9999) < QUALITA_MINIMA:
            log(f"{v['name']}: qualità troppo bassa ({a['lato_corto']}p), messo nel cestino di Drive")
            try:
                drive.cestino(v["id"])
            except Exception as e:
                log("cestino non riuscito:", e)
            videos.remove(v)
        elif a.get("nero"):     # 6/11/2026 (revisione, punto 14): tutto nero, non esce; niente cancellato
            log(f"{v['name']}: e' tutto nero, spostato in 'Da controllare' (non esce nei reel)")
            try:
                drive.sposta_in_sottocartella(v["id"], "Da controllare")
            except Exception as e:
                log("spostamento non riuscito (per ora resta fuori dai reel):", e)
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
    # 6/11/2026 (punto 34): un video orizzontale negli ultimi 10 reel -> prima i verticali (in coda e in archivio).
    # 6/11/2026 (revisione; Alessandro: "dai sempre priorita' ai nuovi contenuti piuttosto che ai vecchi"): un video
    # NUOVO orizzontale non lascia mai il posto a una clip d'archivio. Aspetta solo dietro i video nuovi verticali; se in
    # coda ci sono solo orizzontali esce lo stesso (montaggio.orizzontale lo segna)
    try:
        evita_oriz = orizzontale_recente(state)
        ORIENTAMENTI_NOTI.update(state.get("archivio_usi", {}))
    except Exception as e:
        log("Controllo dei video orizzontali non riuscito (scelta come prima):", e)
        evita_oriz = False
    video = scegli_video(videos, state["analisi"], slot_ora, evita_oriz)
    tenuto = None
    if (video and not spinto and len(videos) <= VIDEO_DA_TENERE
            and not state["analisi"].get(video["id"], {}).get("momento")):
        tenuto, video = video, None
    clip, riserva_arch = None, []
    if video is None:
        usi_arch = state.setdefault("archivio_usi", {})
        try:
            # 4/11/2026: con nuovi tentativi: un archivio "vuoto" per la rete faceva saltare l'orario
            archivio = [dict(c, **usi_arch.get(c["id"], {}))
                        for c in con_tentativi(drive.lista_archivio, "Lettura dell'archivio", drive)]
        except Exception as e:
            log("Lettura dell'archivio non riuscita:", e)
            archivio = []
        # i video PARLATI non si riusano con la musica sopra (si vedrebbe la bocca muoversi senza voce)
        qualita = clip_voti()
        archivio = [c for c in archivio if c.get("fallimenti", 0) < 2 and c.get("parlato") != "1"
                    and c.get("nome") not in qualita["escluse"]]
        # quante volte e quando ogni video e' gia' uscito (anche come video nuovo, prima di entrare in archivio)
        stem = lambda n: os.path.splitext(n or "")[0].lower()
        for c in archivio:
            usciti = [h["quando"][:16] for h in state["storico"] if h.get("video") and stem(h["video"]) == stem(c["nome"])]
            c["usi"] = max(int(c.get("usi", 0)), len(usciti))
            c["ultimo"] = max([c.get("ultimo", "")] + usciti)
        limite = (datetime.datetime.now() - datetime.timedelta(days=7)).isoformat(timespec="minutes")
        riposati = [c for c in archivio if c.get("ultimo", "") < limite]     # 1/11/2026: niente clip uscite negli ultimi 7 giorni
        belle = [c for c in riposati if qualita["voti"].get(c.get("nome"), 0) >= 10]   # prima le clip migliori
        gruppo = belle or riposati or archivio
        if evita_oriz:     # 6/11/2026 (punto 34): prima le clip non orizzontali; mai bloccare
            # 6/11/2026 (revisione): senza ripescare le clip uscite negli ultimi 7 giorni (regola del 1/11) se ce ne
            # sono di riposate
            vert = lambda l: [c for c in l if _orizz(c) is not True]
            gruppo = vert(belle) or vert(riposati) or vert(gruppo) or gruppo
        riserva_arch = [gruppo, archivio]     # 6/11/2026 (revisione): per cambiare clip se e' tutta nera
        clip = scegli_archivio(gruppo, slot_ora)
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
    # 7/11/2026 (studio della sera, modifica 4): prova a meta' sulla frase (montaggio.prove.frase, montaggio.frase_via):
    # "forzata" = la frase non viene dalla scelta libera in classifica (sua richiesta, suo screenshot, titolo del
    # MOMENTO, orario fermo, frase vincente riproposta; 7/11, revisione: anche un suo screenshot tra le candidate): li'
    # la prova non tocca niente, su tutti e due i lati, e prove.frase non si scrive (segna_prove)
    lato_frase, frase_via = lato_prova("frase", slot), "forzata"
    if SOLO_MIE:    # solo le citazioni del Google Doc di Alessandro: prima quelle mai uscite, a caso
        try:
            # 4/11/2026: con nuovi tentativi: senza il Doc l'orario saltava ("documento vuoto")
            mie = mie_frasi(con_tentativi(drive.testo_mie_citazioni, "Lettura di 'Le mie citazioni'", drive) or "")
        except Exception as e:
            log("Lettura di 'Le mie citazioni' non riuscita:", e)
            mie = []
        import classifica_frasi
        foto_punti = classifica_frasi.carica()
        scelte_da_lui = [f for f in mie if foto_punti.get(f["id"]) == 100]   # 1/11/2026: le frasi delle sue foto passano sempre
        if random.random() >= TRADIMENTO_QUOTA:   # 25/10/2026: di tradimento si parla poco (1 volta su 10)
            mie = [f for f in mie if not TRADIMENTO.search(f["gancio"])] or mie
        mie = [f for f in mie if not DONNE.search(f["gancio"])] or mie       # 26/10/2026: mai frasi sulle donne
        mie = [f for f in mie if not NEGATIVO.search(f["gancio"]) and not PALESTRA.search(f["gancio"])
               and not CRINGE.search(f["gancio"]) and not FAMIGLIA.search(f["gancio"])
               and not CONFRONTO.search(f["gancio"])] or mie  # 29/10
        mie += [f for f in scelte_da_lui if f not in mie]
        frasi = [f for f in mie if f["id"] not in usi]
        log(f"'{DOC_MIE}': {len(mie)} citazioni, {len(frasi)} ancora da usare.")
        # reel da 5 s: anche le frasi lunghe (scelta di Alessandro 13/10/2026: se non si fa in tempo a leggere,
        # si riguarda il video -> piu' visualizzazioni). Nessun filtro sulla lunghezza.
        # dati YouTube 16/10/2026 (53 Shorts): frasi fino a 6 parole ~340 views mediane, 7-10 parole ~1.020,
        # 11-15 parole ~1.255 -> 9 volte su 10 si sceglie una frase di almeno 7 parole (1 su 10 resta "esperimento")
        # 31/10/2026 (Alessandro): prima TUTTE le frasi delle sue foto (classifica 100); imprenditoria sospesa (0)
        frasi = [f for f in frasi if foto_punti.get(f["id"]) != 0] or frasi
        foto_rimaste = any(foto_punti.get(f["id"]) == 100 for f in frasi)
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
        forzata = frase_forzata(mie, state, spinto)
        if not forzata and not spinto and frase_forzata(mie, state):
            log("Orario fermo: le frasi scelte aspettano il prossimo orario spinto")
        if forzata:
            frase = forzata
            log("Frase richiesta da Alessandro:", frase["gancio"])
        elif not spinto and vecchie and not foto_rimaste:   # orario fermo: si riusa la frase uscita da piu' tempo
            frase = min(vecchie, key=lambda f: usi[f["id"]])
            log("Orario fermo: riuso una frase uscita il", usi[frase["id"]])
        elif vincenti and random.random() < 0.25 and not foto_rimaste:
            frase = random.choice(vincenti)
            log("Ripropongo una frase che ha gia' funzionato:", frase["gancio"])
        elif frasi:
            # 20/10/2026 (98 Short): 11-15 parole mediana 1.014 views, 7-10 parole 862, fino a 6 parole 443
            # 26/10/2026 (Alessandro): frasi piu' lunghe (la gente si ferma a leggere) e PRIMA quelle che pensiamo
            # vadano piu' virali: classifica_frasi.json (0-100, 50 se manca; lunghezza, temi sulle persone, [virale],
            # giudizio di Claude). Si sceglie a caso tra le prime 3, cosi' i reel vicini non sono sempre uguali.
            punti = foto_punti
            # 7/11/2026 (Alessandro: "privilegiando sempre quelle che ti ho salvato per prima"): a parita' di
            # punteggio le frasi dei suoi screenshot nell'ordine della coda, dalla piu' vecchia
            coda = coda_screenshot()
            # 6/11/2026 (67 reel dal 29/10): a parita' di punteggio prima le frasi da 11-17 parole: YouTube ne ha
            # spinte il 39% (13 su 33), di quelle fino a 10 parole solo il 10% (3 su 31)
            giusta = lambda f: 11 <= len(f["gancio"].split()) <= 17
            ordinate = sorted(frasi, key=lambda f: (-punti.get(f["id"], classifica_frasi.stima(f["gancio"], f.get("virale"))),
                                                    coda.get(f["id"], len(coda)), not giusta(f)))
            # 3/11/2026: mai due frasi con le stesse prime parole nello stesso giorno
            inizio = lambda t: " ".join(re.findall(r"\w+", (t or "").lower())[:2])
            oggi = {inizio(h.get("testo")) for h in state["storico"] if h.get("quando", "")[:10] == datetime.date.today().isoformat()}
            # 3/11/2026: niente frase quasi uguale a una uscita negli ultimi 30 giorni (stesse parole per il 60%)
            # e niente stesso tema dei 2 reel precedenti
            parole = lambda t: {w for w in re.findall(r"\w{4,}", (t or "").lower())}
            mese = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
            uscite = [parole(h.get("testo")) for h in state["storico"] if h.get("quando", "") >= mese and h.get("testo")]
            simile = lambda t: any(len(parole(t) & u) >= 0.6 * max(1, min(len(parole(t)), len(u))) for u in uscite if u)
            tema_di = {f["id"]: f.get("tema") for f in mie}
            temi_vicini = {tema_di.get(h.get("frase")) for h in state["storico"][-2:]} - {None}
            # 7/11/2026: le frasi della coda dei suoi screenshot non aspettano per 'simile' e per il tema (la coda e'
            # stata controllata contro le frasi gia' uscite; quelle uscite restano fuori per id)
            # 11/11/2026 (Alessandro: "tutte le frasi screenshot che ti metto nella cartella devono essere pubblicate"):
            # anche quelle a 100 aggiunte dopo la coda (attivita' delle 06:15) sono in fila, dopo la coda
            sua = lambda f: f["id"] in coda or punti.get(f["id"]) == 100
            adatte = [f for f in ordinate[:12] if inizio(f["gancio"]) not in oggi and (sua(f) or not simile(f["gancio"]))]
            adatte = [f for f in adatte if f.get("tema") not in temi_vicini or sua(f)] or adatte
            frase = random.choice(adatte[:3] or [f for f in ordinate[:8] if inizio(f["gancio"]) not in oggi][:3] or ordinate[:3])
            in_fila = [f for f in adatte if punti.get(f["id"]) == 100]
            if in_fila:          # la prima in fila, senza sorteggio (il random sopra resta per non cambiare il resto)
                frase = in_fila[0]
                log(f"Frase dei suoi screenshot, posto {coda.get(frase['id'], len(coda)) + 1} della coda:", frase["gancio"])
            else:
                log(f"Frase dalla classifica ({punti.get(frase['id'], 'stima')}):", frase["gancio"])
            # 7/11/2026 (studio della sera, modifica 4): sul lato "aforisma", tra le STESSE candidate di oggi (adatte)
            # l'aforisma (una frase sola, voce generale, 9-20 parole) meglio piazzato, se c'e'. Le frasi dei suoi
            # screenshot (classifica 100) restano davanti su tutti e due i lati. La scelta di oggi resta fatta prima
            # (stesso random per il resto del reel)
            frase_via = "forzata" if punti.get(frase["id"]) == 100 else "classifica"
            # 7/11/2026 (revisione): con una frase dei suoi screenshot (100) tra le candidate la prova non puo' agire (le
            # sue frasi restano davanti su tutti e due i lati): "forzata" anche qui, deciso prima della moneta e uguale
            # sui due lati (segna_prove allora non scrive prove.frase: la tabella non confronta reel trattati uguali)
            if frase_via == "classifica" and any(punti.get(f["id"]) == 100 for f in adatte):
                log("Prova della frase: restano davanti le frasi dei suoi screenshot (la prova non agisce)")
                frase_via = "forzata"
            if lato_frase == "aforisma" and frase_via == "classifica":
                try:
                    afo = next((f for f in adatte if aforisma(f["gancio"])), None)
                    frase_via = "aforisma" if afo else "nessun_aforisma"
                    if afo and afo is not frase:
                        log(f"Prova della frase (aforisma): {afo['gancio']} (al posto di {frase['gancio']})")
                    frase = afo or frase
                except Exception as e:
                    log("Prova della frase non riuscita (resta la scelta di oggi):", e)
                    frase_via = "classifica"
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
    # 7/11/2026 (revisione, tempi): la scadenza unica del reel (vedi SCADENZA_MINUTI), per OGNI reel; a mano nessuna
    try:
        import formati_nuovi
        t_orario = ora_slot(slot)
        formati_nuovi.SCADENZA = ((t_orario - datetime.timedelta(minutes=SCADENZA_MINUTI)).timestamp()
                                  if t_orario else None)
        if t_orario:
            log(f"Scadenza del montaggio: {t_orario - datetime.timedelta(minutes=SCADENZA_MINUTI):%H:%M} "
                f"({formati_nuovi.secondi_rimasti() / 60:.0f} minuti)")
    except Exception as e:
        log("Scadenza del reel non impostata (nessun limite, come prima):", e)
    src = os.path.join(work, "originale" + (os.path.splitext(nome)[1] or ".mov"))
    out = os.path.join(work, "reel.mp4")
    try:     # 4/11/2026: fuori dal montaggio: un errore di rete non e' colpa del video (2 "fallimenti" lo spostavano
        # in "Da controllare" e non usciva piu'); il video resta in coda per il prossimo orario
        con_tentativi(lambda: drive.download(fonte_id, src, folder="Archivio" if clip else "Da pubblicare"),
                      "Download del video", drive)
    except Exception as e:
        log(f"Download di {nome} non riuscito (rete): resta in coda, nessun tentativo contato:", e)
        shutil.rmtree(work, ignore_errors=True)
        raise
    nera_tolta = None
    if clip:
        # 6/11/2026 (revisione, punto 14): una clip d'archivio tutta nera (IMG_4508.MOV: 3,3 s di nero, il reel del 1/11
        # alle 06:00) non esce piu'. Si mette da parte senza cancellare niente (archivio_usi: nera e 2 fallimenti, come
        # una clip che non si monta) e al suo posto un'altra clip dell'archivio; se non c'e' o non si scarica, come prima
        try:
            if _nera(src):
                u = state.setdefault("archivio_usi", {}).setdefault(clip["id"], {})
                u["nera"], u["fallimenti"] = True, max(2, int(u.get("fallimenti", 0)))
                NERE.add(clip["id"])     # 6/11/2026 (integrazione): neanche come clip extra in questo giro
                altre = [[c for c in g if c["id"] != clip["id"] and not c.get("nera")] for g in riserva_arch]
                altra = scegli_archivio(next((g for g in altre if g), []), slot_ora)
                log(f"La clip d'archivio {nome} e' tutta nera: messa da parte, non torna nei reel"
                    + (f"; al suo posto {altra['nome']}" if altra else "; nessun'altra clip, resta questa"))
                save()
                if altra:
                    src2 = os.path.join(work, "altra" + (os.path.splitext(altra["nome"])[1] or ".mov"))
                    con_tentativi(lambda: drive.download(altra["id"], src2, folder="Archivio"), "Download del video", drive)
                    nera_tolta, clip, src, nome, fonte_id = nome, altra, src2, altra["nome"], altra["id"]
                    an = {"scena": clip.get("scena"), "compagnia": clip.get("compagnia"), "fascia": clip.get("fascia")}
        except Exception as e:
            log("Controllo della clip nera non riuscito (resta la clip scelta):", e)
    oriz = orizzontale(src)          # 6/11/2026 (punto 34): montaggio.orizzontale in stato.json
    try:
        serie = etichetta_serie(slot)
        frase = dict(frase, serie=serie)
        # 7/11/2026: con lo stile al centro la prova a meta' delle scritte finisce (decisione di Alessandro): ogni reel
        # ha montaggio.scritta = centro_serif e montaggio.stile_centro (carattere, corpo, righe, quanto e' scurito)
        if str(slot)[:10] < FORMATI_PROVA_FINO and not overlay.STILE_CENTRO:
            overlay.STILE_SCRITTA = random.Random(f"scritta {slot}").choice(SCRITTE_PROVA)
        overlay.ULTIMO_STILE = None
        t_montaggio = time.time()       # 7/11/2026 (revisione, tempi): montaggio.secondi_montaggio
        info, formato = None, scegli_formato(slot, state, frase, an, spinto)
        foto_oggi, foto_riuso, voluto = [], False, None
        if TUTTO_10S and formato in FORMATI_10 and str(slot).endswith(ORARIO_FOTO) and str(slot)[:10] >= FOTO_DAL:
            formato_f = None
            try:
                import foto_giornata
                # 6/11/2026: meta' degli orari il photo dump (foto_rapide); prima le foto nuove, senza foto nuove si
                # riusano quelle di una giornata gia' uscita (Alessandro: "se non ci sono foto in coda... quelle vecchie")
                voluto = formato_foto(slot)
                foto_oggi, formato_f, foto_riuso = con_tentativi(
                    lambda: foto_giornata.foto_per_slot(drive, state, voluto), "Lettura delle foto", drive)
                if foto_oggi:
                    log(f"Foto: {len(foto_oggi)} {'gia uscite (riuso)' if foto_riuso else 'nuove'}, formato "
                        f"{formato_f} (estratto {voluto})")
            except Exception as e:
                log("Foto della giornata non lette:", e)
            formato = (formato_f or "dieci_foto") if foto_oggi else formato
        log(f"Formato: {formato}")
        # 7/11/2026 (studio della sera, modifiche 1 e 7): il lato della prova dell'apertura, deciso per OGNI reel (mai
        # quello del reel prima). Le foto no: li' non cambia niente e resta "viso" (com'era); un ripiego col video si'
        lato_ap = lato_prova("apertura", slot) or "viso"
        overlay.APERTURA = "viso" if formato in FORMATI_FOTO else lato_ap
        scelta_frase = (frase.get("id"), frase.get("gancio"))
        log(f"Prove a meta': apertura {overlay.APERTURA if formato not in FORMATI_FOTO else '-'}, frase {lato_frase}"
            f" ({frase_via})")
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
            elif formato in FORMATI_FOTO:
                monta_foto = foto_giornata.monta_rapide if formato == "foto_rapide" else foto_giornata.monta
                info = monta_foto(foto_oggi, frase["gancio"], out, musiche_brano(music, 3), drive, work,
                                  riuso=foto_riuso)
                if voluto and voluto != formato:     # estratto foto_rapide, ma la giornata aveva poche foto nuove
                    info.setdefault("estratto", voluto)
            elif formato == "dieci_lista":
                frase, info = monta_dieci_lista(lista_regole(slot, state), src, out, music, serie, drive, work, clip)
            elif formato == "giornata":     # 6/11/2026: i momenti della sua giornata, anche quelli ancora in coda
                info = monta_giornata(frase, src, out, music, serie, drive, work, clip, an, state, videos, video)
            elif formato in FORMATI_10:
                info = monta_dieci(formato, frase, src, out, music, serie, drive, work, clip, state.get("formato_ultimo"))
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
            overlay.APERTURA = lato_ap   # 7/11/2026: il ripiego e' un reel col video (anche dopo le foto)
            if TUTTO_10S:                # 1/11/2026: il ripiego resta nello stile scelto (10 s, scritta gialla)
                try:
                    # 6/11/2026: prima qui formati_nuovi non era importato (NameError: il ripiego non partiva mai).
                    # monta_dieci gestisce i video corti (dieci_due) e la scritta sul viso (cinema/post, controllo
                    # del viso sempre acceso)
                    info = monta_dieci("dieci", frase, src, out, music, serie, drive, work, clip,
                                       state.get("formato_ultimo"))
                    info["ripiego_da"] = formato
                except Exception as e2:
                    log("Anche il ripiego da 10 s non riuscito:", e2)
        if info is None:
            info = overlay.make_video(src, frase["gancio"], out, preview=os.path.join(work, "anteprima.jpg"),
                                      music=music, serie=serie,
                                      autore=frase.get("autore") if MOSTRA_AUTORE else None,
                                      colore=ENV("SENZA_COLORE") != "1", nome=nome,
                                      scena_rilevata=an["scena"], da_archivio=bool(clip))
        if isinstance(info, dict):      # 7/11/2026 (revisione, tempi): per misurare i primi reel su GitHub
            info["secondi_montaggio"] = round(time.time() - t_montaggio)
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
    if overlay.ULTIMO_STILE and isinstance(info, dict):      # 6/11/2026: quale scritta e' uscita davvero
        info.setdefault("scritta", overlay.ULTIMO_STILE)
    if isinstance(info, dict) and info.get("formato") and info["formato"] != formato:
        info.setdefault("estratto", formato)     # 6/11/2026 (analisi): formato estratto, se e' uscito un altro (clip corta...)
    log("Montato:", info)
    # 5/11/2026: il reel con le foto NON usa il video scelto (resta solo come ripiego se le foto non si montano): quel
    # video non va segnato come pubblicato ne' spostato nell'archivio, e la clip d'archivio non conta come usata
    con_foto = info.get("formato") in FORMATI_FOTO
    if con_foto:
        video, clip, nome = None, None, "Foto della giornata"
        an = dict(an, registrato=None)
    # 6/11/2026 (punto 34): il video di partenza era orizzontale? (al massimo 1 ogni ORIZZONTALI_OGNI reel)
    # 6/11/2026 (integrazione): scritto per OGNI reel. Vuol dire: il video dell'orario (quello che risulta pubblicato,
    # la prima clip di ogni montaggio, anche nei formati a piu' clip e in giornata) e' orizzontale; e' quello che la
    # regola dei 10 reel controlla. Le clip extra orizzontali vanno gia' per ultime (clip_extra) e giornata le toglie
    # finche' restano 4 momenti (montaggio.scene_orizzontali conta quelle rimaste). Foto: sempre False
    info["orizzontale"] = False if con_foto else oriz is True
    if nera_tolta and not con_foto:     # 6/11/2026 (revisione): la clip tutta nera scartata prima del montaggio
        info["clip_nera_tolta"] = nera_tolta
    segna_prove(info, con_foto, lato_frase, frase_via, scelta_frase, frase, src)
    frase = dict(frase, copertina_ms=info.get("copertina_ms"),   # volte: per un titolo YouTube diverso se la frase torna
                 volte=sum(1 for h in state["storico"] if h.get("frase") == frase.get("id")))
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
        frase["audio_nome"] = audio_ig.nome_audio(info["musica_meta"])
    if "instagram" in piatt and out_meta:     # 6/11/2026: copertina con frase e viso + reel di prova a orari alterni
        try:
            if frase.get("copertina_ms") is None and info.get("formato") in COPERTINA_FORMATI:
                frase["copertina_ms"] = copertina_reel(out_meta, info.get("durata"))
            frase["prova_ig"] = bool(not voce and reel_di_prova(slot, state))
            log(f"Instagram: copertina {frase.get('copertina_ms')} ms, reel di prova:",
                "si" if frase["prova_ig"] else "no")
        except Exception as e:
            frase["prova_ig"] = False
            log("Instagram: copertina/prova non decise, reel normale:", e)
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
                                 "in_corso": True, "frase_dati": {k: frase.get(k) for k in (
                                     "id", "tema", "gancio", "righe", "autore", "hashtag", "serie",
                                     "copertina_ms", "prova_ig")}})   # 6/11: anche per il recupero di Instagram
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
    tt = None
    if TIKTOK_BOZZE and target:      # 29/10/2026: versione per le BOZZE di TikTok (inviata all'ora esatta, piu' sotto)
        try:
            tt = overlay.versione_tiktok(out, os.path.join(work, "reel_tt.mp4"), audio=bool(voce))
        except Exception as e:
            log("Versione per TikTok non preparata:", e)
    if TIKTOK_STUDIO and target:     # 25/10/2026: versione per TikTok Studio, programmata la sera prima dal PC
        nome_tt = f"{target:%Y-%m-%d %H%M} - {frase['id']}.mp4"
        dati_tt = {"testo": testo_breve(frase), "slot": f"{target:%Y-%m-%d %H:%M}", "voce": bool(voce)}
        try:
            tt = tt or overlay.versione_tiktok(out, os.path.join(work, "reel_tt.mp4"), audio=bool(voce))
            # 4/11/2026: un SSL EOF di Drive aveva fatto saltare il TikTok delle 10
            con_tentativi(lambda: drive.salva_tiktok(tt, nome_tt, dati_tt["testo"], dati_tt["slot"], voce),
                          "TikTok Studio: salvataggio su Drive", drive, n=4)
            log(f"Pronto per TikTok Studio ({os.path.getsize(tt) / 1e6:.1f} MB): {CARTELLA_TIKTOK}/{nome_tt}")
        except Exception as e:
            log("Versione per TikTok Studio non salvata su Drive:", e)
            metti_in_sospeso(tt, nome_tt, dati_tt)
    ig_nativo = None
    # 3/11/2026: Instagram con un brano DI INSTAGRAM (Alessandro: "voglio gli audio delle piattaforme", mai i nostri).
    # Instagram applica il brano (audio_configuration) solo se il video caricato HA una traccia audio: dal 25/10 al 2/11
    # si caricava senza traccia e solo 1 reel su ~80 ha avuto la musica (il 2/11 delle 18, l'unico con la traccia).
    # Si carica quindi out_meta (con traccia) e Instagram la sostituisce col suo brano (video_volume 0).
    if "instagram" in piatt and not voce and out_meta:
        scelto = brano_ig(state, an["scena"], frase.get("id"))
        if scelto:
            ig_nativo = (out_meta, scelto[0])
            info["musica_instagram"] = scelto[1]
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
    if results.get("instagram", {}).get("brano"):     # 4/11: al secondo tentativo Instagram ha preso un altro brano
        info["musica_instagram"] = results["instagram"]["brano"]
    if tt and TIKTOK_BOZZE and not DRY:
        results["tiktok"] = tiktok_bozza(tt, frase, target)
    controlla_errori(state, results)
    if results.get("youtube", {}).get("ok") and not DRY:
        try:
            aggiungi_playlist(creds, results["youtube"]["id"], an["scena"], state)
        except Exception as e:
            log("Playlist YouTube non aggiornata:", e)
    if results.get("instagram", {}).get("ok") and ENV("SENZA_STORIE") != "1" and principale(slot) and not DRY:
        try:
            # 3/11/2026: nelle Storie l'API non mette musica di Instagram -> mai i nostri brani: storia senza musica
            # (parlato/momento con il loro suono vero)
            storia = out_meta if voce else overlay.versione_social(out, os.path.join(work, "storia.mp4"), audio=False)
            results["instagram_storia"] = {"ok": True, "id": instagram_storia(storia)}
            log("instagram storia pubblicata")
        except Exception as e:
            results["instagram_storia"] = {"ok": False, "errore": str(e)[:300]}
            log("instagram storia non pubblicata:", e)
    if not any(r["ok"] for r in results.values()):
        log("Nessuna piattaforma ha funzionato: il video resta in coda per il prossimo orario.")
        sys.exit(1)

    # 5. archivio e stato
    oggi = datetime.date.today().isoformat()
    if con_foto and not DRY and not info.get("foto_riuso"):     # 6/11: le foto riusate sono gia' in "Foto usate"
        foto_giornata.segna_usate(drive, info.get("foto_ids", []))
    if clip:
        u = state["archivio_usi"].setdefault(clip["id"], {})
        u["usi"] = u.get("usi", 0) + 1
        u["ultimo"] = oggi
        if oriz is not None:     # 6/11/2026 (punto 34): la prossima volta si sa prima di scaricarla
            u["orizzontale"] = oriz
    for cid, o in ORIENTAMENTI.items():     # 6/11/2026: anche le clip extra scaricate in questo giro
        if o is not None:
            state["archivio_usi"].setdefault(cid, {})["orizzontale"] = o
    for cid in NERE:     # 6/11/2026 (revisione): clip extra tutte nere, messe da parte (niente cancellato)
        u = state["archivio_usi"].setdefault(cid, {})
        u["nera"], u["fallimenti"] = True, max(2, int(u.get("fallimenti", 0)))
    spostato = False
    if video:                # video nuovo: si tiene per riusarlo in futuro
        meta_arch = {"scena": an.get("scena"), "fascia": fascia_video(an), "compagnia": an.get("compagnia"),
                     "registrato": an.get("registrato"), "parlato": "1" if an.get("parlato") else None,
                     "orizzontale": None if oriz is None else ("1" if oriz else "0")}   # 6/11/2026 (punto 34)
        stem = os.path.splitext(nome)[0]
        try:
            if os.path.getsize(src) <= MAX_ORIGINALE_MB * 1024 * 1024:   # l'originale intero va nell'archivio
                # 4/11/2026: con nuovi tentativi: se lo spostamento falliva, l'originale finiva nel cestino
                cid = con_tentativi(lambda: drive.sposta_in_archivio(video["id"], nome, meta_arch),
                                    "Spostamento nell'archivio", drive)
                spostato = True
                log(f"Originale spostato nell'archivio: {nome}")
            else:                                                       # troppo grande: un pezzo da 15 s
                cpath = overlay.crea_clip_archivio(src, os.path.join(work, stem + "_archivio.mov"), info.get("inizio"))
                cid = drive.carica_archivio(cpath, f"{stem}.mov", meta_arch)
                log(f"Copia (15 s) salvata nell'archivio: {stem}.mov")
            state.setdefault("archivio_usi", {})[cid] = {"usi": 1, "ultimo": oggi,
                                                         **({"orizzontale": oriz} if oriz is not None else {})}
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
            pronti_id = drive.archive(None if (clip or spostato or not video) else video["id"], out,
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
    if info.get("musica"):     # 6/11/2026: 60 (prima 20), per la finestra di YT_FINESTRA_BRANI brani
        state["musica_recenti"] = (state["musica_recenti"] + [info["musica"]])[-60:]
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
    if not DRY and COMMENTI_SU_TELEGRAM:   # la sera: i commenti nuovi su Telegram, per rispondere di persona (mai bloccare il reel)
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
