"""
REEL DELLA SETTIMANA (21/11/2026, decisione di Alessandro: il PC resta SPENTO dal lunedi' al venerdi'; lo accende venerdi'
a mezzanotte e il sabato 00:00-09:00 le attivita' di Claude in Chrome programmano su TikTok Studio e su Meta Business
Suite (Pagina Facebook) TUTTI i reel della settimana dopo. YouTube e Instagram restano automatici su GitHub).

Il venerdi' sera GitHub (.github/workflows/settimana.yml) prepara in anticipo i reel degli slot da sabato 10:00 al
lunedi' della settimana dopo compreso (~97 reel), con le STESSE scelte di pubblica.py (scegli_reel / monta_reel: 7 s,
scena unica, frase mai sul viso, frasi escluse, screenshot per primi, varieta' dei video...). Per ogni slot salva su Drive,
in "0. Reel Alessandro/Sistema (non toccare)/Settimana - reel pronti/<lotto>/":
  "AAAA-MM-GG HHMM - <frase>.mp4"              versione TikTok/Facebook (1080p, < 10 MB, senza musica, didascalia
                                               nella descrizione, tiktok_slot in appProperties come oggi)
  "AAAA-MM-GG HHMM - <frase> - youtube.mp4"    versione YouTube/Instagram (quella che pubblica.py userebbe)
  "AAAA-MM-GG HHMM - <frase> - anteprima.jpg"  striscia di 3 fotogrammi
  "AAAA-MM-GG HHMM - <frase> - manifest.json"  slot, frase, didascalia, video, musica_screenshot, testo_viso, stato
Il registro e' settimana.json (nel repository, lo scrive solo il workflow): slot -> stato "in_preparazione" | "pronto" |
"fallito". Gli scarti di Alessandro sono in settimana_scarti.json (lo scrive "scarta", anche dal PC): uno slot scartato
torna a GitHub, che prepara un sostituto (versione + 1). stato.json NON lo tocca il workflow (lo scrive solo pubblica.py:
niente conflitti): le frasi e i video gia' presi dal lotto contano come usati con prenotati() / video_riservati().

Allo slot pubblica.py usa il reel pronto (reel_per_slot) per YouTube e Instagram (Instagram sceglie il brano di tendenza
in quel momento, come prima); se manca, e' scartato, e' fallito o la sua frase e' gia' uscita, monta come prima.

  python settimana.py pianifica [--da "AAAA-MM-GG HH:MM"] [--a "AAAA-MM-GG HH:MM"] [--gruppi 12] [--scarti]
  python settimana.py monta --gruppo N               (GitHub, un pezzo della matrice)
  python settimana.py registra                       (GitHub, dopo la matrice: settimana.json)
  python settimana.py scarta AAAA-MM-GG HH:MM [motivo]   segna lo slot scartato e lo manda a GitHub (sostituto)
  python settimana.py stato [AAAA-MM-GG]             elenco degli slot del lotto
  python settimana.py controlla "AAAA-MM-GG HH:MM"   cosa userebbe pubblica.py a quello slot (senza pubblicare)
  python settimana.py foto [AAAA-MM-GG] [giorni]     gli slot con il reel FOTO (una sua foto ferma, vedi FOTO_OGNI)
  pianifica --solo-foto: solo gli slot foto; con SETTIMANA_PROVA=1 il registro e' _settimana/lotto_prova.json (prove)

21/11/2026 (Alessandro): reel FOTO, uno slot ogni tre (slot_foto): una sua foto nuova di "Foto da pubblicare", ferma e
mai modificata, con la frase sopra (foto_giornata.make_singola); finite le foto, reel col video.
"""
import datetime, json, os, re, subprocess, sys, time
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
LOTTO = os.path.join(HERE, "settimana.json")
SCARTI = os.path.join(HERE, "settimana_scarti.json")
LAVORO = os.path.join(HERE, "_settimana")
CARTELLA = "Settimana - reel pronti"        # dentro "Sistema (non toccare)" (cartelle.py)
ROMA = ZoneInfo("Europe/Rome")
GRUPPI = 12                  # lavori in parallelo su GitHub (~2 minuti a reel: ~97 reel in ~20-25 minuti)
MINUTI_REEL = 25             # scadenza del montaggio di un reel (allo slot vero ce ne sono ~35)
DURATA = 7.0                 # 20/11/2026: tutti i reel da 7 s (lo cambia solo Alessandro)
MB_TIKTOK = 9.5              # Chrome carica fino a 10 MB
PREPARAZIONE_ORE = 6         # un "in_preparazione" piu' vecchio di cosi' (workflow interrotto) non prenota piu' niente
ANTICIPO_MIN = 90            # si preparano solo slot ad almeno 90 minuti da adesso
# 21/11/2026 (Alessandro): da lunedi' 23 TikTok e Facebook vengono SOLO dal lotto (il percorso di sempre salta i reel dal
# 22/11, tiktok_prepara.FINE_PERCORSO_VECCHIO): la copia in "TikTok - da pubblicare" allo slot e' spenta
COPIA_GIRO_DI_SEMPRE = False
# 21/11/2026 (Alessandro: "ogni 2 reel con i video, 1 reel con la foto"): reel con UNA sua foto (foto_giornata,
# FORMATO_SINGOLA) negli slot foto. Schema fisso: gli slot di orario.ORE contati in fila da FOTO_DAL alle 00:00
# (0, 1, 2, ...), e' foto ogni slot con numero % FOTO_OGNI == FOTO_OGNI - 1 (il 3o, il 6o, il 9o...). Con 10 slot al
# giorno lo schema si ripete ogni 3 giorni: 1o giorno 08, 14, 20; 2o giorno 06, 12, 18; 3o giorno 00, 10, 16, 22
# (10 foto ogni 3 giorni, 3-4 al giorno). Dal 01/12/2026 (martedi'): il 23-30/11 e' gia' pronto e approvato.
# Se le foto nuove finiscono (o nessuna va bene per la frase) lo slot resta un reel col video. FOTO_ACCESE = False:
# tutto come prima. (python settimana.py foto AAAA-MM-GG [giorni]: gli slot foto di quei giorni)
FOTO_ACCESE = True
FOTO_DAL = "2026-12-01"
FOTO_OGNI = 3
# 21/11/2026: prove su GitHub senza toccare il lotto vero: con SETTIMANA_PROVA il registro e' _settimana/lotto_prova.json
# (parte da una copia di settimana.json, mai salvato nel repository) e il workflow non fa commit
PROVA = os.environ.get("SETTIMANA_PROVA", "") not in ("", "0")
if PROVA:
    LOTTO = os.path.join(LAVORO, "lotto_prova.json")


def log(*a):
    print(datetime.datetime.now().strftime("%H:%M:%S"), *a, flush=True)


def ora_roma():
    return datetime.datetime.now(ROMA)


def t_slot(slot):
    return datetime.datetime.strptime(slot, "%Y-%m-%d %H:%M").replace(tzinfo=ROMA)


def slot_tra(da, a):
    """Gli slot di orario.ORE da 'da' ad 'a' compresi ("AAAA-MM-GG HH:MM")."""
    import orario
    t, fine, out = t_slot(da).replace(minute=0), t_slot(a), []
    while t <= fine:
        if t.hour in orario.ORE:
            out.append(f"{t:%Y-%m-%d %H:%M}")
        t += datetime.timedelta(hours=1)
    return out


def intervallo_settimana(adesso=None):
    """Da sabato 10:00 (il prossimo; il venerdi' sera = domani) al lunedi' della settimana dopo alle 22:00."""
    adesso = adesso or ora_roma()
    giorni = (5 - adesso.weekday()) % 7 or 7          # 5 = sabato
    if adesso.weekday() == 5 and adesso.hour < 8:
        giorni = 0
    sab = (adesso + datetime.timedelta(days=giorni)).date()
    lun = sab + datetime.timedelta(days=9)
    return f"{sab} 10:00", f"{lun} 22:00"


# ------------------------------------------------------------------------------------------------ registro

def _leggi(path, vuoto):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except FileNotFoundError:
        return vuoto
    except ValueError as e:
        log(f"{os.path.basename(path)} illeggibile ({e}): lo considero vuoto")
        return vuoto


def carica_lotto():
    d = _leggi(LOTTO, None)
    if d is None:       # prova: si parte dal registro vero (le sue prenotazioni contano), che non si tocca
        d = _leggi(os.path.join(HERE, "settimana.json"), {}) if PROVA else {}
    d.setdefault("slot", {})
    return d


# 25/11/2026 (Alessandro: "voglio sempre contenuti nuovi"): l'ordine e' video nuovi -> foto nuove -> riciclo.
# Uno slot col video che resterebbe una clip d'archivio (niente video nuovi) prende invece una foto nuova, se ce n'e'
# una adatta; solo senza video nuovi e senza foto nuove si ripesca dall'archivio (regola del mese compresa).
# Lo schema 2 video : 1 foto (slot_foto) resta per quando ci sono entrambi. FOTO_AL_POSTO_RICICLO = False: come prima.
FOTO_AL_POSTO_RICICLO = True


def foto_possibile(slot):
    """True se lo slot puo' avere il reel con una foto nuova (foto accese, dal FOTO_DAL, slot non manuale)."""
    try:
        return bool(FOTO_ACCESE and FOTO_AL_POSTO_RICICLO and "manuale" not in str(slot)
                    and str(slot)[:10] >= FOTO_DAL)
    except Exception:
        return False


def slot_foto(slot):
    """True se lo slot ("AAAA-MM-GG HH:MM") e' per il reel con una foto (schema fisso: vedi FOTO_OGNI)."""
    import orario
    try:
        if not FOTO_ACCESE or "manuale" in str(slot):
            return False
        t = datetime.datetime.strptime(str(slot)[:16], "%Y-%m-%d %H:%M")
        giorni = (t.date() - datetime.date.fromisoformat(FOTO_DAL)).days
        if giorni < 0 or t.minute or t.hour not in orario.ORE:
            return False
        return (giorni * len(orario.ORE) + orario.ORE.index(t.hour)) % FOTO_OGNI == FOTO_OGNI - 1
    except Exception:
        return False


def foto_riservate(state, escludi=None, lotto=None, scarti=None):
    """Id delle foto gia' prese da uno slot del lotto non ancora uscito (pronto o in preparazione), piu' quelle uscite
    (montaggio.foto_ids dello storico): un'altra foto per gli altri slot."""
    lotto = lotto if lotto is not None else carica_lotto()
    scarti = scarti if scarti is not None else carica_scarti()
    fatti = set(state.get("slot_fatti", []))
    out = {v.get("foto_id") for s, v in lotto["slot"].items()
           if s != escludi and s not in fatti and v.get("foto_id") and _attivo(s, v, scarti)}
    for h in state.get("storico", []):
        out |= set((h.get("montaggio") or {}).get("foto_ids") or [])
    return out - {None}


def carica_scarti():
    return _leggi(SCARTI, [])


def _scrivi(path, dati):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(dati, f, ensure_ascii=False, indent=1, sort_keys=isinstance(dati, dict))
        f.write("\n")
    os.replace(tmp, path)


def scartato(slot, voce, scarti):
    """True se questa versione dello slot e' stata scartata da Alessandro."""
    return any(s.get("slot") == slot and int(s.get("versione") or 0) == int(voce.get("versione") or 0) for s in scarti)


def _attivo(slot, voce, scarti, adesso=None):
    """Lo slot tiene prenotati frase e video? pronto, oppure in preparazione da poco; mai se scartato."""
    if scartato(slot, voce, scarti):
        return False
    if voce.get("stato") == "pronto":
        return True
    if voce.get("stato") == "in_preparazione":
        quando = voce.get("generato") or ""
        limite = (adesso or datetime.datetime.now()) - datetime.timedelta(hours=PREPARAZIONE_ORE)
        return quando >= limite.isoformat(timespec="minutes")
    return False


def pronto(slot, lotto=None, scarti=None):
    """La voce del lotto per lo slot, se e' pronta e non scartata; se no None."""
    lotto = lotto if lotto is not None else carica_lotto()
    scarti = scarti if scarti is not None else carica_scarti()
    v = lotto["slot"].get(slot)
    if v and v.get("stato") == "pronto" and not scartato(slot, v, scarti) and (v.get("file") or {}).get("youtube"):
        return v
    return None


def finta(slot, v):
    """La voce finta dello storico per uno slot del lotto non ancora uscito (per le scelte di pubblica.scegli_reel)."""
    return {"quando": slot.replace(" ", "T"), "slot": slot, "video": v.get("video"), "frase": v.get("frase"),
            "tema": v.get("tema"), "testo": (v.get("testo") or "")[:120], "da_archivio": v.get("da_archivio"),
            "registrato": v.get("registrato"), "scena": v.get("scena"), "settimana": True,
            "montaggio": {"formato": v.get("formato"), "musica": v.get("musica"),
                          **({"foto_ids": [v["foto_id"]]} if v.get("foto_id") else {})}}


def prenotati(state, escludi=None, lotto=None, scarti=None):
    """Voci finte dello storico per gli slot del lotto pronti (o in preparazione) e non ancora usciti: le loro frasi e i
    loro video contano come usati quel giorno. escludi = lo slot che si sta scegliendo."""
    lotto = lotto if lotto is not None else carica_lotto()
    scarti = scarti if scarti is not None else carica_scarti()
    fatti = set(state.get("slot_fatti", []))
    return [finta(s, v) for s, v in sorted(lotto["slot"].items())
            if s != escludi and s not in fatti and _attivo(s, v, scarti)]


def video_riservati(state, escludi=None, lotto=None, scarti=None):
    """Id dei video NUOVI (ancora in coda) gia' presi da uno slot del lotto non ancora uscito."""
    lotto = lotto if lotto is not None else carica_lotto()
    scarti = scarti if scarti is not None else carica_scarti()
    fatti = set(state.get("slot_fatti", []))
    return {v.get("fonte_id") for s, v in lotto["slot"].items()
            if s != escludi and s not in fatti and not v.get("da_archivio") and v.get("fonte_id")
            and _attivo(s, v, scarti)}


def _scelto(v):
    """Quando la frase dello slot e' stata scelta: "scelto" (dal piano) o, per le voci di prima, "generato" meno 2 ore
    (il montaggio di un lotto dura meno di un'ora)."""
    if v.get("scelto"):
        return v["scelto"]
    try:
        return (datetime.datetime.fromisoformat(v["generato"]) - datetime.timedelta(hours=2)).isoformat(timespec="minutes")
    except Exception:
        return ""


def uscita_altrove(slot, frase_id, state, dopo=""):
    """La frase e' uscita in un ALTRO slot DOPO la scelta del lotto (`dopo` = la voce "generato" dello slot)? Allora il
    reel pronto non si usa (mai doppioni: pubblica.py l'ha presa mentre il lotto si preparava). Le frasi riproposte
    apposta (frasi vincenti, orari fermi: uscite prima della scelta) restano buone, come allo slot dal vivo."""
    return any(h.get("frase") == frase_id and h.get("slot") != slot and str(h.get("quando") or "") >= (dopo or "")
               for h in state.get("storico", []))


# ------------------------------------------------------------------------------------------------ allo slot

_FOTO = "foto_singola"       # = foto_giornata.FORMATO_SINGOLA (qui senza importare foto_giornata, che carica OpenCV)

def reel_per_slot(slot, state, drive, work, videos):
    """pubblica.py: il reel gia' pronto per questo slot, nel formato che main usa dopo il montaggio; None = monta come
    prima. Mai un errore che fermi lo slot: chi chiama tiene il percorso di prima se qui qualcosa va storto."""
    import pubblica, overlay
    if not slot or "manuale" in slot:
        return None
    v = pronto(slot)
    if not v:
        voce = carica_lotto()["slot"].get(slot)
        if voce:
            pubblica.log(f"Reel della settimana per {slot}: {voce.get('stato')}"
                         + (" e scartato" if scartato(slot, voce, carica_scarti()) else "") + ": lo monto adesso")
        return None
    if uscita_altrove(slot, v.get("frase"), state, _scelto(v)):
        pubblica.log(f"Reel della settimana per {slot}: la frase {v.get('frase')} e' gia' uscita, lo monto adesso")
        return None
    if v.get("foto_id") and any(v["foto_id"] in ((h.get("montaggio") or {}).get("foto_ids") or [])
                                for h in state.get("storico", []) if h.get("slot") != slot):
        pubblica.log(f"Reel della settimana per {slot}: la foto {v.get('video')} e' gia' uscita, lo monto adesso")
        return None
    os.makedirs(work, exist_ok=True)
    out = os.path.join(work, "reel.mp4")
    pubblica.con_tentativi(lambda: drive.download(v["file"]["youtube"], out, folder="Settimana"),
                           "Download del reel della settimana", drive)
    durata = overlay.probe(out)[0]
    if os.path.getsize(out) < 100_000 or (v.get("formato") != "parlato" and abs(durata - DURATA) > 0.3):
        pubblica.log(f"Reel della settimana per {slot}: file non valido ({os.path.getsize(out)} byte, {durata:.2f} s)")
        return None
    in_coda = {x["id"]: x for x in videos}
    video = None if v.get("da_archivio") else in_coda.get(v.get("fonte_id"))
    clip = {"id": v.get("fonte_id"), "nome": v.get("video")} if v.get("da_archivio") else None
    info = dict(v.get("montaggio") or {})
    info["settimana"] = {"lotto": v.get("lotto"), "versione": v.get("versione"), "generato": v.get("generato")}
    pubblica.log(f"Reel della settimana per {slot}: {v.get('frase')} su {v.get('video')} (versione {v.get('versione')},"
                 f" preparato il {v.get('generato')})")
    return {"out": out, "src": os.path.join(work, "originale_non_scaricato"), "frase": dict(v["frase_dati"]),
            "info": info, "an": dict(v.get("an") or {"scena": v.get("scena")}), "nome": v.get("video"),
            "video": video, "clip": clip, "spinto": True, "oriz": info.get("orizzontale"),
            "con_foto": v.get("formato") == _FOTO,     # 21/11/2026: reel con una foto (foto_ids in montaggio)
            "settimana": dict(v, slot=slot)}


def segna_pubblicato(drive, pre, results):
    """Dopo lo slot: manifest su Drive -> pubblicato; la versione YouTube del lotto nel cestino (resta quella TikTok)."""
    v = pre["settimana"]
    if drive.local or not (v.get("file") or {}).get("manifest"):
        return
    m = _scarica_json(drive, v["file"]["manifest"])
    m["stato"] = "pubblicato"
    m["pubblicato"] = {"quando": datetime.datetime.now().isoformat(timespec="minutes"),
                       **{p: r.get("id") for p, r in results.items() if r.get("ok")}}
    _aggiorna_json(drive, v["file"]["manifest"], m)
    if all(r.get("ok") for p, r in results.items() if p in ("youtube", "instagram")):
        drive.api.files().update(fileId=v["file"]["youtube"], body={"trashed": True}, fields="id").execute()


def copia_per_giro_di_sempre(drive, v, nome, testo, slot, voce):
    """Allo slot: copia la versione TikTok del lotto in "TikTok - da pubblicare" (come i reel montati allo slot), per le
    attivita' di sempre del PC (TikTok e Facebook la sera, programmano i reel gia' usciti). Sulla copia si segnano fatte
    le piattaforme gia' programmate dal giro del sabato (tiktok_fatto / fb_fatto del file del lotto): mai doppioni. Se
    tutte e due sono gia' fatte non si copia niente."""
    import pubblica
    f = drive.api.files().get(fileId=v["file"]["tiktok"], fields="appProperties").execute()
    p = f.get("appProperties") or {}
    if p.get("tiktok_fatto") == "1" and p.get("fb_fatto") == "1":
        return "gia' programmato su TikTok e Facebook dal giro del sabato: nessuna copia"
    props = {"tiktok_slot": slot, "tiktok_voce": "1" if voce else "0", "settimana_slot": slot}
    props.update({k: p[k] for k in ("tiktok_fatto", "tiktok_quando", "fb_fatto", "fb_quando") if p.get(k)})
    drive.api.files().copy(fileId=v["file"]["tiktok"], fields="id", body={
        "name": nome, "parents": [drive.cartella(pubblica.CARTELLA_TIKTOK)], "description": testo,
        "appProperties": props}).execute()
    fatte = [x for x in ("tiktok", "fb") if p.get(f"{x}_fatto") == "1"]
    return f"copiato in {pubblica.CARTELLA_TIKTOK}/{nome}" + (f" (gia' fatto: {', '.join(fatte)})" if fatte else "")


# ------------------------------------------------------------------------------------------------ Drive

def _cartella_lotto(drive, nome):
    """La cartella del lotto dentro "Settimana - reel pronti" (creata se manca, una sola)."""
    import cartelle
    base = drive.cartella(CARTELLA)
    q = cartelle.query(nome, [base])
    trovate = drive.api.files().list(q=q, fields=f"files({cartelle.CAMPI})").execute().get("files", [])
    fid = cartelle.scegli(trovate, nome, log)
    if fid:
        return fid
    return drive.api.files().create(body={"name": nome, "parents": [base], "mimeType": cartelle.CARTELLA},
                                    fields="id").execute()["id"]


def _carica(drive, path, nome, cartella, mime, descrizione=None, props=None):
    from googleapiclient.http import MediaFileUpload
    body = {"name": nome, "parents": [cartella]}
    if descrizione:
        body["description"] = descrizione
    if props:
        body["appProperties"] = props
    return drive.api.files().create(body=body, media_body=MediaFileUpload(path, mimetype=mime),
                                    fields="id").execute()["id"]


def _scarica_json(drive, fid):
    return json.loads(drive.api.files().get_media(fileId=fid).execute().decode("utf-8"))


def _aggiorna_json(drive, fid, dati):
    import io
    from googleapiclient.http import MediaIoBaseUpload
    media = MediaIoBaseUpload(io.BytesIO(json.dumps(dati, ensure_ascii=False, indent=1).encode("utf-8")),
                              mimetype="application/json")
    drive.api.files().update(fileId=fid, media_body=media).execute()


def _drive():
    import pubblica
    return pubblica.Drive(pubblica.google_creds())


# ------------------------------------------------------------------------------------------------ pianifica

def _stato():
    import pubblica
    state = pubblica.carica_stato()
    for k, v in (("usate", []), ("storico", []), ("riprova", []), ("slot_fatti", []), ("musica_recenti", []),
                 ("frasi_usate", []), ("temi_recenti", []), ("analisi", {}), ("archivio_usi", {})):
        state.setdefault(k, v)
    return state


def _video_in_coda(drive, state):
    """I video nuovi in coda che pubblica.py userebbe: gia' analizzati da lui (lo fa a ogni slot), non troppo piccoli,
    non neri, non doppioni di video usciti. Qui non si sposta e non si cestina niente."""
    import pubblica
    vids = pubblica.con_tentativi(drive.list_videos, "Lettura della coda", drive)
    visti = {h["md5"] for h in state["storico"] if h.get("md5")}
    out = []
    for v in vids:
        a = state["analisi"].get(v["id"])
        if not a or a.get("analisi_fallita") or int(a.get("fallimenti", 0) or 0) >= 2 or a.get("nero"):
            continue
        if 0 < a.get("lato_corto", 9999) < pubblica.QUALITA_MINIMA or (v.get("md5Checksum") in visti):
            continue
        out.append(v)
    return out


def _corto(c):
    return {k: c.get(k) for k in ("id", "nome", "scena", "fascia", "compagnia", "registrato", "size", "usi", "ultimo",
                                  "orizzontale", "parlato", "fallimenti", "nera") if c.get(k) is not None}


def slot_in_corso(adesso=None, fatti=()):
    """Lo slot che pubblica.py sta preparando adesso (sceglie la frase ~50 minuti prima e la salva su GitHub solo dopo
    l'uscita): None se non ce n'e'. Il 21/11 un piano fatto in quel momento ha preso la stessa frase del reel delle 14."""
    import orario
    adesso = adesso or ora_roma()
    for ore in (0, 1):
        t = (adesso + datetime.timedelta(hours=ore)).replace(minute=0, second=0, microsecond=0)
        k = f"{t:%Y-%m-%d %H:%M}"
        if t.hour in orario.ORE and k not in fatti and \
                t - datetime.timedelta(minutes=orario.ANTICIPO + 10) <= adesso <= t + datetime.timedelta(minutes=45):
            return k
    return None


def aspetta_slot_in_corso(massimo_minuti=75):
    """Su GitHub, prima di scegliere: se pubblica.py sta preparando uno slot, si aspetta che lo salvi (git pull ogni
    minuto) per non scegliere la sua stessa frase. Al massimo `massimo_minuti`, poi si va avanti (registra e lo slot
    ricontrollano comunque i doppioni)."""
    fine = time.time() + massimo_minuti * 60
    while time.time() < fine:
        s = slot_in_corso(fatti=set(_stato().get("slot_fatti", [])))
        if not s:
            return
        log(f"pubblica.py sta preparando lo slot {s}: aspetto che lo salvi prima di scegliere")
        time.sleep(60)
        subprocess.run(["git", "-C", HERE, "pull", "-q", "--rebase", "--autostash"], capture_output=True, timeout=120)
    log("Attesa finita: scelgo lo stesso (i doppioni si ricontrollano dopo)")


def _foto_disponibili(drive, state, lotto, scarti, slots):
    """21/11/2026: le foto nuove per gli slot foto del piano (foto_giornata.candidate_singole), senza quelle gia' prese
    da altri slot del lotto o uscite (e le loro raffiche), ne' quelle delle versioni scartate degli slot da rifare.
    None se nel piano non ci sono slot foto o se l'elenco non si legge (allora reel col video, come prima)."""
    if not any(slot_foto(s) or foto_possibile(s) for s in slots):
        return None
    try:
        import foto_giornata
        escl = foto_riservate(state, lotto=lotto, scarti=scarti)
        escl |= {v.get("foto_id") for s, v in lotto["slot"].items() if s in slots and v.get("foto_id")}
        quando = [v.get("foto_quando") for v in lotto["slot"].values() if v.get("foto_id") in escl]
        cand = foto_giornata.candidate_singole(drive, escl - {None}, quando)
        log(f"Foto nuove per gli slot foto: {len(cand)} (una per raffica)")
        return cand
    except Exception as e:
        log("Foto non lette: gli slot foto restano reel col video:", e)
        return None


FOTO_STESSA_SESSIONE = 15 * 60    # secondi: foto scattate a meno di 15 minuti = stessa sessione (stessa posa, stesso posto)
FOTO_SESSIONE_DISTANZA = 3        # una sessione non torna nei 3 slot foto dopo (circa un giorno), se ci sono altre foto


def _scegli_foto(drive, cand, frase, s, scelte=None):
    """La prima foto nuova adatta alla frase (mai sul viso, leggibile, taglio senza tagliare il viso) per lo slot s;
    la toglie (con la sua raffica) da cand. Prima le foto di sessioni diverse da quelle degli ultimi
    FOTO_SESSIONE_DISTANZA slot foto (scelte: le foto gia' scelte, in ordine). -> il file di Drive o None."""
    import foto_giornata
    cartella = os.path.join(LAVORO, "foto")
    vicine = [foto_giornata._secondi(foto_giornata._quando(g)) for g in (scelte or [])[-FOTO_SESSIONE_DISTANZA:]]
    stessa = lambda f: any(t and abs(foto_giornata._secondi(foto_giornata._quando(f)) - t) < FOTO_STESSA_SESSIONE
                           for t in vicine)
    ordine = sorted(cand, key=stessa)        # stabile: dentro i due gruppi resta "prima le piu' recenti"
    f, _, _ = foto_giornata.prova_candidate(ordine, frase["gancio"],
                                            lambda f: foto_giornata.scarica_singola(drive, f, cartella),
                                            log=lambda *x: log(f"{s}:", *x))
    if f:
        cand[:] = [g for g in cand if g["id"] != f["id"] and not foto_giornata.stessa_raffica(f, g)]
        if scelte is not None:
            scelte.append(f)
    return f


def pianifica(da=None, a=None, gruppi=GRUPPI, solo_scarti=False, prova=None, solo_foto=False):
    """Sceglie in ordine (come farebbe pubblica.py slot dopo slot) video, frase, musica e formato di ogni slot da
    preparare; scrive _settimana/piano.json e mette gli slot "in_preparazione" in settimana.json (prenotano subito frasi e
    video, cosi' pubblica.py non li riprende mentre si monta). Restituisce il numero di slot da montare.
    21/11/2026: negli slot foto (slot_foto) il reel con una foto nuova, se ce n'e' una adatta alla frase; solo_foto =
    solo gli slot foto dell'intervallo (prove)."""
    import pubblica
    if os.environ.get("GITHUB_ACTIONS") == "true" and not PROVA:
        aspetta_slot_in_corso()
    if solo_scarti:     # prima: manifest e file delle versioni scartate (dopo, la voce dello slot cambia)
        segna_scartati_su_drive()
    state, lotto, scarti = _stato(), carica_lotto(), carica_scarti()
    adesso = ora_roma()
    fatti = set(state["slot_fatti"])
    if solo_scarti:     # sostituti: gli slot la cui ultima versione e' scartata
        slots = sorted(s for s, v in lotto["slot"].items() if scartato(s, v, scarti))
    else:
        if not (da and a):
            da, a = intervallo_settimana(adesso)
        slots = [s for s in slot_tra(da, a) if not pronto(s, lotto, scarti)
                 and not _attivo(s, lotto["slot"].get(s) or {}, scarti)]
    slots = [s for s in slots if s not in fatti and t_slot(s) > adesso + datetime.timedelta(minutes=ANTICIPO_MIN)]
    if solo_foto:
        slots = [s for s in slots if slot_foto(s)]
    log(f"Slot da preparare: {len(slots)}" + (f" ({slots[0]} -> {slots[-1]})" if slots else ""))
    os.makedirs(LAVORO, exist_ok=True)
    if not slots:
        _scrivi(os.path.join(LAVORO, "piano.json"), {"slot": [], "gruppi": []})
        return 0
    creds = pubblica.google_creds()
    drive = pubblica.Drive(creds)
    videos = _video_in_coda(drive, state)
    frasi = json.load(open(pubblica.FRASI, encoding="utf-8"))
    # una sola lettura del Doc e dell'archivio per tutto il piano (sono uguali per tutti gli slot)
    testo = pubblica.con_tentativi(drive.testo_mie_citazioni, "Lettura di 'Le mie citazioni'", drive)
    archivio = pubblica.con_tentativi(drive._lista_archivio_tutta, "Lettura dell'archivio", drive)
    drive.testo_mie_citazioni = lambda: testo
    # 22/11/2026: regola del mese rispetto all'ora dello slot (pubblica.ORA_RIFERIMENTO)
    drive.lista_archivio = lambda: [dict(c) for c in archivio if pubblica.fresco(c)]
    pubblica.ORIENTAMENTI_NOTI.update(state.get("archivio_usi", {}))
    finte = prenotati(state, lotto=lotto, scarti=scarti)
    finte = [f for f in finte if f["slot"] not in slots]
    # i sostituti non riprendono la frase ne' il video della versione scartata
    finte += [finta(s, lotto["slot"][s]) for s in slots if s in lotto["slot"] and scartato(s, lotto["slot"][s], scarti)]
    riservati = set(video_riservati(state, lotto=lotto, scarti=scarti))
    for s in slots:
        v = lotto["slot"].get(s)
        if v and scartato(s, v, scarti) and not v.get("da_archivio") and v.get("fonte_id"):
            riservati.add(v["fonte_id"])
    vista = json.loads(json.dumps({k: state[k] for k in ("musica_recenti", "temi_recenti", "formato_ultimo")
                                   if k in state}))
    vista = dict(state, **vista)
    foto_cand = _foto_disponibili(drive, state, lotto, scarti, slots)
    foto_scelte = []
    piano, nomi = [], {}
    nuovo_lotto = prova or f"Lotto {slots[0][:10]}"
    for i, s in enumerate(slots):
        t = t_slot(s).replace(tzinfo=None)
        sc = pubblica.scegli_reel(vista, drive, creds, videos, s, frasi, finte, riservati, adesso=t)
        if sc is None:
            log(f"{s}: niente da preparare (pubblica.py lo montera' allo slot)")
            continue
        # 25/11/2026: anche quando il video sarebbe una clip d'archivio (riciclo): prima le foto nuove
        foto_qui = slot_foto(s) or (bool(sc["clip"]) and foto_possibile(s))
        foto = _scegli_foto(drive, foto_cand, sc["frase"], s, foto_scelte) if foto_cand and foto_qui else None
        if foto and not slot_foto(s):
            log(f"{s}: niente video nuovi, foto nuova al posto del riciclo")
        if foto:             # 21/11/2026: reel con una foto; il video scelto resta in coda per gli slot dopo
            import foto_giornata
            nome_f = f"Foto {foto.get('name')}"
            sc = dict(sc, video=None, clip=None, riserva_arch=[], an={"scena": None}, nome=nome_f, fonte_id=None)
            formato = _FOTO
        else:
            if slot_foto(s):
                log(f"{s}: slot foto, ma nessuna foto nuova adatta: reel col video")
            elif sc["clip"] and foto_possibile(s):
                log(f"{s}: niente video nuovi e niente foto nuove adatte: riciclo dall'archivio")
            formato = pubblica.scegli_formato(s, dict(vista, storico=vista["storico"] + finte), sc["frase"], sc["an"],
                                              sc["spinto"])
            vista["formato_ultimo"] = formato
        if sc["music"]:
            vista["musica_recenti"] = (vista["musica_recenti"] + [os.path.basename(sc["music"])])[-60:]
        vista["temi_recenti"] = (vista["temi_recenti"] + [sc["frase"].get("tema")])[-10:]
        if sc["video"]:
            riservati.add(sc["video"]["id"])
        voce = {"video": sc["nome"], "frase": sc["frase"]["id"], "tema": sc["frase"].get("tema"),
                "testo": sc["frase"].get("gancio"), "da_archivio": bool(sc["clip"]),
                "registrato": sc["an"].get("registrato"), "scena": sc["an"].get("scena"), "formato": formato,
                "musica": os.path.basename(sc["music"]) if sc["music"] else None}
        if foto:
            voce.update(foto_id=foto["id"], foto_quando=foto_giornata._quando(foto) or None)
        finte.append(finta(s, voce))
        vecchia = lotto["slot"].get(s) or {}
        versione = int(vecchia.get("versione") or 0) + 1
        lotto_nome = vecchia.get("lotto") if vecchia.get("lotto") and solo_scarti else nuovo_lotto
        piano.append({"slot": s, "gruppo": i % gruppi, "versione": versione, "lotto": lotto_nome, "formato": formato,
                      "spinto": sc["spinto"], "video": sc["video"], "clip": sc["clip"] and _corto(sc["clip"]),
                      "riserva_arch": [[_corto(c) for c in g[:8]] for g in sc["riserva_arch"]],
                      "an": sc["an"], "nome": sc["nome"], "fonte_id": sc["fonte_id"], "lato_frase": sc["lato_frase"],
                      "frase_via": sc["frase_via"], "frase": sc["frase"],
                      "music": os.path.relpath(sc["music"], HERE) if sc["music"] else None,
                      "md5": (sc["video"] or {}).get("md5Checksum"),
                      "foto": foto and {k: foto.get(k) for k in ("id", "name", "createdTime", "imageMediaMetadata",
                                                                  "appProperties")}})
        ora = datetime.datetime.now().isoformat(timespec="minutes")
        lotto["slot"][s] = dict(voce, stato="in_preparazione", versione=versione, lotto=lotto_nome,
                                fonte_id=sc["fonte_id"], generato=ora, scelto=ora, file={})
        nomi[s] = sc["frase"]["id"]
        log(f"{s}: {sc['frase']['id']} su {sc['nome']} ({'foto' if foto else 'archivio' if sc['clip'] else 'nuovo'}),"
            f" {formato}")
    # la cartella del lotto la crea solo questo lavoro (i lavori in parallelo ne creerebbero piu' d'una)
    cartelle_lotto = {}
    for p in piano:
        if p["lotto"] not in cartelle_lotto:
            cartelle_lotto[p["lotto"]] = pubblica.con_tentativi(lambda: _cartella_lotto(drive, p["lotto"]),
                                                                "Cartella del lotto", drive)
        p["cartella"] = cartelle_lotto[p["lotto"]]
    usati = sorted({p["gruppo"] for p in piano})
    _scrivi(os.path.join(LAVORO, "piano.json"), {"slot": piano, "gruppi": usati})
    _scrivi(LOTTO, lotto)
    doppie = len(nomi) - len(set(nomi.values()))
    log(f"Piano: {len(piano)} reel in {len(usati)} gruppi; frasi ripetute nel piano: {doppie}")
    return len(piano)


# ------------------------------------------------------------------------------------------------ monta

def anteprima(path, dst, durata=DURATA):
    """Striscia jpg di 3 fotogrammi (a 1 s, a meta', alla fine)."""
    import overlay
    tempi = [1.0, durata / 2, max(0.5, durata - 0.6)]
    ins = []
    for t in tempi:
        ins += ["-ss", f"{t:.2f}", "-i", path]
    filtro = ";".join(f"[{i}:v]scale=-2:640,setsar=1[v{i}]" for i in range(3)) + ";[v0][v1][v2]hstack=inputs=3"
    r = subprocess.run([overlay.FFMPEG, "-y", "-v", "error", *ins, "-filter_complex", filtro, "-frames:v", "1",
                        "-q:v", "3", dst], capture_output=True, text=True, errors="ignore", timeout=120)
    if r.returncode != 0 or not os.path.exists(dst):
        raise RuntimeError("anteprima: " + r.stderr[-300:])
    return dst


def verifica(info, out, tt):
    """I controlli di Alessandro su un reel pronto: 7 s, testo mai sul viso (YuNet, scala >= 0,8), TikTok < 10 MB."""
    import overlay
    male = []
    durata = overlay.probe(out)[0]
    parlato = (info or {}).get("formato") == "parlato"
    if not parlato and abs(durata - DURATA) > 0.15:
        male.append(f"durata {durata:.2f} s")
    tv = (info or {}).get("testo_viso") or {}
    if not parlato:
        if tv.get("controllo") != "lettere_fuori_dai_visi":
            male.append("testo_viso mancante")
        if tv.get("fotogrammi") and tv.get("rilevatore") != "yunet+haar":
            male.append(f"rilevatore {tv.get('rilevatore')}")
        if tv.get("scala") is not None and float(tv["scala"]) < 0.8 - 1e-3:
            male.append(f"scala {tv['scala']}")
    if os.path.getsize(tt) > MB_TIKTOK * 1e6:
        male.append(f"TikTok {os.path.getsize(tt) / 1e6:.1f} MB")
    if (info or {}).get("formato") == _FOTO:     # 21/11/2026: la sua foto mai modificata, ferma, una sola
        fo = info.get("foto") or {}
        if not (fo.get("intatta") is True and fo.get("modifiche") == [] and fo.get("movimento") == "nessuno"):
            male.append("foto modificata o in movimento")
        if fo.get("differenza") is None or float(fo["differenza"]) > 3.0:
            male.append(f"foto diversa dall'originale ({fo.get('differenza')})")
        if len(info.get("foto_ids") or []) != 1:
            male.append(f"foto: {len(info.get('foto_ids') or [])} invece di una")
        if (info.get("stile_centro") or {}).get("scurito"):
            male.append("foto scurita")
    return male, round(durata, 3)


def _monta_foto(sc, drive, work, slot):
    """21/11/2026: il reel con la foto scelta dal piano (sc["foto"]), nello stesso formato di pubblica.monta_reel."""
    import pubblica, foto_giornata
    f = sc["foto"]
    frase = dict(sc["frase"], serie=pubblica.etichetta_serie(slot))
    src = pubblica.con_tentativi(lambda: foto_giornata.scarica_singola(drive, f, work), "Download della foto", drive)
    out = os.path.join(work, "reel.mp4")
    info = foto_giornata.make_singola(src, frase["gancio"], out, sc.get("music"), f)
    pubblica.segna_prove(info, True, sc.get("lato_frase"), sc.get("frase_via"), (frase.get("id"), frase.get("gancio")),
                         frase, src)
    return {"out": out, "src": src, "frase": frase, "info": info, "an": {"scena": None}, "nome": sc["nome"],
            "fonte_id": None, "video": None, "clip": None, "spinto": sc.get("spinto"), "oriz": False, "con_foto": True}


def monta(gruppo):
    """Un pezzo della matrice: monta gli slot del gruppo, li salva su Drive, scrive _settimana/risultati/<slot>.json."""
    import pubblica, overlay
    piano = _leggi(os.path.join(LAVORO, "piano.json"), {"slot": []})
    miei = [p for p in piano["slot"] if p["gruppo"] == gruppo]
    log(f"Gruppo {gruppo}: {len(miei)} reel")
    state = _stato()
    pubblica.ORIENTAMENTI_NOTI.update(state.get("archivio_usi", {}))
    drive = _drive()
    cartelle_lotto = {}
    os.makedirs(os.path.join(LAVORO, "risultati"), exist_ok=True)
    for p in miei:
        s = p["slot"]
        chiave = s.replace(":", "").replace(" ", "_")
        work = os.path.join(HERE, "_lavoro_settimana", chiave)
        os.makedirs(work, exist_ok=True)
        ris = {"slot": s, "versione": p["versione"], "lotto": p["lotto"], "stato": "fallito"}
        t0 = time.time()
        try:
            sc = dict(p, music=os.path.join(HERE, p["music"]) if p.get("music") else None)
            vista = dict(state, formato_ultimo=None)
            if p["formato"] == _FOTO:      # 21/11/2026: reel con una foto (foto_giornata.make_singola)
                m = _monta_foto(sc, drive, work, s)
            else:
                pubblica.ORA_RIFERIMENTO = t_slot(s).replace(tzinfo=None)    # 22/11/2026: regola del mese
                m = pubblica.monta_reel(sc, vista, drive, work, [], s, lambda: None, formato=p["formato"],
                                        scadenza=time.time() + MINUTI_REEL * 60)
            frase, info, out = m["frase"], m["info"], m["out"]
            info["orizzontale"] = False if m["con_foto"] else m["oriz"] is True
            voce = info.get("formato") == "parlato" or (info.get("formato") == "momento" and info.get("audio_originale"))
            tt = overlay.versione_tiktok(out, os.path.join(work, "tiktok.mp4"), audio=bool(voce))
            male, durata = verifica(info, out, tt)
            jpg = anteprima(out, os.path.join(work, "anteprima.jpg"), durata)
            didascalia = pubblica.testo_breve(frase)
            import musica_screenshot
            brano = musica_screenshot.di(frase.get("id"))
            base = f"{t_slot(s):%Y-%m-%d %H%M} - {frase['id']}"
            if p.get("cartella"):
                cartelle_lotto[p["lotto"]] = p["cartella"]
            if p["lotto"] not in cartelle_lotto:
                cartelle_lotto[p["lotto"]] = pubblica.con_tentativi(lambda: _cartella_lotto(drive, p["lotto"]),
                                                                    "Cartella del lotto", drive)
            cart = cartelle_lotto[p["lotto"]]
            props = {"tiktok_slot": s, "tiktok_voce": "1" if voce else "0", "settimana_slot": s,
                     "settimana_versione": str(p["versione"])}
            file = {}
            file["youtube"] = pubblica.con_tentativi(lambda: _carica(drive, out, base + " - youtube.mp4", cart,
                                                                     "video/mp4"), "Salvataggio YouTube", drive)
            file["tiktok"] = pubblica.con_tentativi(lambda: _carica(drive, tt, base + ".mp4", cart, "video/mp4",
                                                                    didascalia, props), "Salvataggio TikTok", drive)
            file["anteprima"] = pubblica.con_tentativi(lambda: _carica(drive, jpg, base + " - anteprima.jpg", cart,
                                                                       "image/jpeg"), "Salvataggio anteprima", drive)
            frase_dati = {k: frase.get(k) for k in ("id", "tema", "gancio", "righe", "autore", "hashtag", "serie",
                                                    "titolo", "virale", "copertina_ms") if frase.get(k) is not None}
            ris.update(stato="fallito" if male else "pronto", problemi=male, durata=durata, frase=frase["id"],
                       testo=frase.get("gancio"), tema=frase.get("tema"), didascalia=didascalia, video=m["nome"],
                       fonte_id=(m["clip"] or m["video"] or {}).get("id"), da_archivio=bool(m["clip"]),
                       md5=(m["video"] or {}).get("md5Checksum"), registrato=m["an"].get("registrato"),
                       scena=m["an"].get("scena"), an={k: m["an"].get(k) for k in ("scena", "compagnia", "fascia",
                                                                                     "registrato", "momento", "parlato")
                                                       if m["an"].get(k) is not None},
                       formato=info.get("formato"), musica=info.get("musica"), musica_screenshot=brano,
                       voce=bool(voce), testo_viso=info.get("testo_viso"), montaggio=info, frase_dati=frase_dati,
                       mb_tiktok=round(os.path.getsize(tt) / 1e6, 2), cartella=cart, file=file,
                       **({"foto_id": info["foto"].get("id"), "foto_quando": info["foto"].get("quando"),
                           "foto": info["foto"]} if info.get("formato") == _FOTO else {}),
                       generato=datetime.datetime.now().isoformat(timespec="minutes"),
                       secondi=round(time.time() - t0))
            manifest = {k: ris.get(k) for k in ("slot", "versione", "lotto", "stato", "problemi", "frase", "testo",
                                                "didascalia", "video", "fonte_id", "da_archivio", "scena", "formato",
                                                "durata", "musica", "musica_screenshot", "voce", "testo_viso",
                                                "mb_tiktok", "generato", "file")
                        + (("foto",) if ris.get("foto") else ())}
            mpath = os.path.join(work, "manifest.json")
            with open(mpath, "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=1)
            ris["file"]["manifest"] = pubblica.con_tentativi(lambda: _carica(drive, mpath, base + " - manifest.json",
                                                                             cart, "application/json"),
                                                             "Salvataggio manifest", drive)
            log(f"{s}: {ris['stato']} {frase['id']} {durata} s, TikTok {ris['mb_tiktok']} MB, "
                f"{ris['secondi']} s" + (f" PROBLEMI {male}" if male else ""))
        except BaseException as e:
            if isinstance(e, KeyboardInterrupt):
                raise
            ris["errore"] = str(e)[:300]
            log(f"{s}: NON preparato ({e}); pubblica.py lo montera' allo slot")
        _scrivi(os.path.join(LAVORO, "risultati", chiave + ".json"), ris)
        import shutil
        shutil.rmtree(work, ignore_errors=True)


# ------------------------------------------------------------------------------------------------ registra

def registra():
    """Dopo la matrice: i risultati in settimana.json; gli slot del piano senza risultato -> fallito; una frase uscita
    nel frattempo in un altro slot (pubblica.py durante il montaggio) -> fallito (allo slot si monta come prima)."""
    lotto, state = carica_lotto(), _stato()
    piano = _leggi(os.path.join(LAVORO, "piano.json"), {"slot": []})
    d = os.path.join(LAVORO, "risultati")
    ris = {}
    for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        r = _leggi(os.path.join(d, f), {})
        if r.get("slot"):
            ris[r["slot"]] = r
    conta = {"pronto": 0, "fallito": 0}
    for p in piano["slot"]:
        s = p["slot"]
        r = ris.get(s) or {"stato": "fallito", "errore": "nessun risultato (lavoro interrotto?)"}
        vecchia = lotto["slot"].get(s) or {}
        if int(vecchia.get("versione") or 0) > p["versione"]:
            continue                           # nel frattempo e' arrivata una versione piu' nuova
        if r.get("stato") == "pronto" and uscita_altrove(s, r.get("frase"), state, vecchia.get("generato") or ""):
            r = dict(r, stato="fallito", errore="frase uscita nel frattempo in un altro slot")
        voce = {k: v for k, v in r.items() if k not in ("slot",)}
        if vecchia.get("scelto") and int(vecchia.get("versione") or 0) == p["versione"]:
            voce["scelto"] = vecchia["scelto"]
        voce.setdefault("versione", p["versione"])
        voce.setdefault("lotto", p["lotto"])
        lotto["slot"][s] = voce
        conta[voce["stato"]] = conta.get(voce["stato"], 0) + 1
    _scrivi(LOTTO, lotto)
    log(f"Registrati: {conta}")
    return conta


def segna_scartati_su_drive():
    """Le versioni scartate: manifest -> scartato e i loro file nel cestino (recuperabili 30 giorni)."""
    lotto, scarti = carica_lotto(), carica_scarti()
    drive = None
    for s, v in lotto["slot"].items():
        if not scartato(s, v, scarti) or v.get("drive_scartato"):
            continue
        drive = drive or _drive()
        f = v.get("file") or {}
        try:
            if f.get("manifest"):
                m = _scarica_json(drive, f["manifest"])
                m["stato"] = "scartato"
                _aggiorna_json(drive, f["manifest"], m)
            for k in ("youtube", "tiktok"):
                if f.get(k):
                    drive.api.files().update(fileId=f[k], body={"trashed": True}, fields="id").execute()
            v["drive_scartato"] = True
            log(f"{s}: versione {v.get('versione')} scartata (file nel cestino di Drive)")
        except Exception as e:
            log(f"{s}: scarto non segnato su Drive:", e)
    _scrivi(LOTTO, lotto)


# ------------------------------------------------------------------------------------------------ PC / prove

def ora_di_push(adesso=None):
    """Mai un push tra :50 e :15 delle ore pari (si costruiscono i reel)."""
    adesso = adesso or ora_roma()
    m, h = adesso.minute, adesso.hour
    return not ((h % 2 == 1 and m >= 50) or (h % 2 == 0 and m < 15))


def scarta(slot, motivo="", invia=True):
    """Segna scartata la versione attuale dello slot (settimana_scarti.json) e, con invia, la manda a GitHub (commit +
    push): il workflow prepara il sostituto. Il venerdi' sera, dopo che Alessandro ha visto le anteprime."""
    if invia:
        subprocess.run(["git", "-C", HERE, "pull", "-q", "--ff-only"], capture_output=True, timeout=120)
    lotto, scarti = carica_lotto(), carica_scarti()
    v = lotto["slot"].get(slot)
    if not v:
        raise SystemExit(f"{slot}: non c'e' nel lotto")
    if scartato(slot, v, scarti):
        print(f"{slot}: versione {v.get('versione')} gia' scartata")
    else:
        scarti.append({"slot": slot, "versione": v.get("versione"), "frase": v.get("frase"), "motivo": motivo,
                       "quando": datetime.datetime.now().isoformat(timespec="minutes")})
        _scrivi(SCARTI, scarti)
        print(f"{slot}: versione {v.get('versione')} ({v.get('frase')}: {v.get('testo')}) scartata")
    if not invia:
        return
    while not ora_di_push():
        print("Adesso non si puo' fare il push (tra :50 e :15 delle ore pari): aspetto 1 minuto")
        time.sleep(60)
    subprocess.run(["git", "-C", HERE, "add", "settimana_scarti.json"], check=True)
    r = subprocess.run(["git", "-C", HERE, "commit", "-q", "-m", f"Settimana: scartato {slot}"], capture_output=True)
    for i in range(4):
        env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
        if subprocess.run(["git", "-C", HERE, "pull", "-q", "--rebase", "--autostash"], env=env).returncode == 0 and \
                subprocess.run(["git", "-C", HERE, "push", "-q", "origin", "HEAD:main"], env=env).returncode == 0:
            print("Mandato a GitHub: il sostituto si prepara da solo (~15 minuti), poi 'python settimana.py stato'")
            return
        time.sleep(10 * (i + 1))
    raise SystemExit("Push non riuscito: rilancia il comando (lo scarto e' gia' salvato in locale)")


def stato(giorno=None):
    lotto, scarti = carica_lotto(), carica_scarti()
    try:
        fatti = set(json.load(open(os.path.join(HERE, "stato.json"), encoding="utf-8")).get("slot_fatti", []))
    except Exception:
        fatti = set()
    righe = []
    for s, v in sorted(lotto["slot"].items()):
        if giorno and not s.startswith(giorno):
            continue
        st = "pubblicato" if s in fatti else ("scartato" if scartato(s, v, scarti) else v.get("stato"))
        righe.append(f"{s}  v{v.get('versione')}  {st:15} {v.get('frase')}  {str(v.get('video'))[:16]:16} "
                     f"{v.get('durata')} s  {v.get('mb_tiktok')} MB  {(v.get('testo') or '')[:60]}"
                     + (f"  [{v.get('errore') or v.get('problemi')}]" if v.get("errore") or v.get("problemi") else ""))
    print("\n".join(righe) or "lotto vuoto")
    return righe


def controlla(slot):
    """Cosa userebbe pubblica.py allo slot (senza scaricare e senza pubblicare)."""
    state = _stato()
    v = pronto(slot)
    if not v:
        voce = carica_lotto()["slot"].get(slot)
        print(f"{slot}: nessun reel pronto ({voce and voce.get('stato')}) -> pubblica.py monta come prima")
        return None
    if uscita_altrove(slot, v.get("frase"), state, _scelto(v)):
        print(f"{slot}: frase gia' uscita altrove -> pubblica.py monta come prima")
        return None
    print(f"{slot}: pubblica.py usa {v['file']['youtube']} ({v.get('frase')}: {v.get('testo')}); durata "
          f"{v.get('durata')} s; testo_viso {((v.get('testo_viso') or {}).get('rilevatore'))} scala "
          f"{(v.get('testo_viso') or {}).get('scala')}; TikTok {v.get('mb_tiktok')} MB")
    return v


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.path.insert(0, HERE)
    a = sys.argv[1:]

    def opz(nome, std=None):
        return a[a.index(nome) + 1] if nome in a else std

    cmd = a[0] if a else ""
    if cmd == "pianifica":
        n = pianifica(opz("--da"), opz("--a"), int(opz("--gruppi", GRUPPI)), "--scarti" in a, opz("--lotto"),
                      "--solo-foto" in a)
        print(f"DA_MONTARE={n}")
    elif cmd == "monta":
        monta(int(opz("--gruppo", "0")))
    elif cmd == "registra":
        registra()
        if not PROVA:        # prova: il registro vero e i suoi file su Drive non si toccano
            segna_scartati_su_drive()
    elif cmd == "foto":      # gli slot foto: python settimana.py foto [AAAA-MM-GG] [giorni]
        g0 = datetime.date.fromisoformat(a[1]) if len(a) > 1 else ora_roma().date()
        for k in range(int(a[2]) if len(a) > 2 else 7):
            g = g0 + datetime.timedelta(days=k)
            ss = [x[11:] for x in slot_tra(f"{g} 00:00", f"{g} 23:00") if slot_foto(x)]
            print(f"{g} ({'lun mar mer gio ven sab dom'.split()[g.weekday()]}): {', '.join(ss) or '-'}")
    elif cmd == "scarta" and len(a) >= 3:
        scarta(f"{a[1]} {a[2]}", " ".join(a[3:]).replace("--locale", "").strip(), invia="--locale" not in a)
    elif cmd == "stato":
        stato(a[1] if len(a) > 1 else None)
    elif cmd == "controlla" and len(a) >= 2:
        controlla(" ".join(a[1:3]) if len(a) >= 3 else a[1])
    else:
        print(__doc__)
