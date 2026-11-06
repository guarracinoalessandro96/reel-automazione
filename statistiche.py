"""
Visualizzazioni delle ultime 24 ore su Telegram (1/11/2026, richiesta di Alessandro: ogni mattina alle 8, Facebook,
Instagram, TikTok e YouTube, solo questi dati). Gira sul PC dall'attivita' "statistiche-mattina": TikTok non ha un'API
per i numeri, quindi l'attivita' scarica il file da TikTok Studio e lo script lo legge da Download.

6/11/2026 (Alessandro: "concentrati ad aggiustare le notifiche su telegram che mi mandi"):
- TikTok: dal file si prende l'ultimo giorno COMPLETO (mai quello di oggi, ancora a meta'). TikTok mette i numeri di un
  giorno con circa 2 giorni di ritardo (alle 8 il file arriva fino all'altro ieri): se non e' ieri, accanto c'e' il
  giorno. Mai un numero di piu' di 2 giorni prima: allora "non disponibile". Se il download non riesce, l'attivita'
  passa il numero letto nella pagina di TikTok Studio: --tiktok N --tiktok-data AAAA-MM-GG.
- Riserva su GitHub (.github/workflows/statistiche.yml -> python statistiche.py --github): se il PC e' spento, dopo le
  8:20 il messaggio lo manda GitHub (YouTube, Instagram, Facebook; TikTok solo se l'ultimo numero salvato non ha piu'
  di 2 giorni). Chi manda lo segna nel registro statistiche_inviate.json del repository (scritto con l'API di GitHub,
  senza toccare la cartella di lavoro del PC) con il totale YouTube del giorno e l'ultimo numero di TikTok: prima di
  mandare lo si "prenota" nel registro, cosi' non partono mai due messaggi nello stesso giorno.

  python statistiche.py [--prova] [--tiktok N --tiktok-data AAAA-MM-GG]
  python statistiche.py --github [--prova]
  --prova: stampa il messaggio, non lo manda e non scrive niente
"""
import base64, csv, datetime, glob, io, json, os, re, subprocess, sys, time, zipfile
import requests
from zoneinfo import ZoneInfo

import avvisi

QUI = os.path.dirname(os.path.abspath(__file__))
SEGRETI = os.path.join(os.path.expanduser("~"), "reel-segreti.json")
STORICO = os.path.join(os.path.expanduser("~"), "statistiche_giornaliere.json")
GRAPH = "https://graph.facebook.com/v23.0"
ROMA = ZoneInfo("Europe/Rome")
MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre",
        "novembre", "dicembre"]
# il file di TikTok ha le date in italiano senza anno ("4 novembre"); anche in inglese, se cambia la lingua
MESE_DA_PAROLA = {**{m[:3]: i + 1 for i, m in enumerate(MESI)},
                  **{m: i + 1 for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep",
                                                     "oct", "nov", "dec"))}}
TIKTOK_MAX_GIORNI = 2       # 6/11/2026: un numero di TikTok piu' vecchio di cosi' non si mostra
# 6/11/2026: registro condiviso PC/GitHub (niente segreti: solo orari e numeri di visualizzazioni)
REPO = "guarracinoalessandro96/reel-automazione"
REGISTRO = "statistiche_inviate.json"
API_REGISTRO = f"https://api.github.com/repos/{REPO}/contents/{REGISTRO}"
RISERVA_DALLE, RISERVA_FINO = (8, 20), (12, 0)     # ora di Roma in cui GitHub puo' mandare al posto del PC
PC_DALLE, PC_FINO = (7, 30), (23, 0)    # il PC acceso di notte recupera il giro saltato: mai un messaggio di notte
PRENOTAZIONE_MINUTI = 20    # una prenotazione piu' vecchia senza "inviato" (mittente spento a meta') non conta piu'
GIORNI_TENUTI = 60
CHIAVI = ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN", "META_PAGE_TOKEN", "IG_USER_ID",
          "FB_PAGE_ID", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")


def adesso():
    return datetime.datetime.now(ROMA)


def pulito(e):
    """6/11/2026: gli errori si stampano (log di GitHub pubblico): mai token, nemmeno dentro un indirizzo."""
    s = re.sub(r"(access_token=)[^&\s'\"]+", r"\1***", str(e))
    return re.sub(r"bot\d+:[\w-]+", "bot***", re.sub(r"Bearer \S+", "Bearer ***", s))


def segreti(su_github):
    """PC: reel-segreti.json. GitHub: i Secrets passati dal lavoro come variabili (mai stampati)."""
    if su_github:
        return {c: os.environ[c] for c in CHIAVI if os.environ.get(c)}
    return json.load(open(SEGRETI, encoding="utf-8"))


def credenziali(k):
    from google.oauth2.credentials import Credentials
    return Credentials(None, refresh_token=k.get("YOUTUBE_REFRESH_TOKEN") or k["GOOGLE_REFRESH_TOKEN"],
                       client_id=k.get("YOUTUBE_CLIENT_ID") or k["GOOGLE_CLIENT_ID"],
                       client_secret=k.get("YOUTUBE_CLIENT_SECRET") or k["GOOGLE_CLIENT_SECRET"],
                       token_uri="https://oauth2.googleapis.com/token")


def youtube_totale(k):
    """Il totale del canale adesso: le 24 ore sono la differenza con quello di ieri (i report arrivano dopo 3 giorni)."""
    from googleapiclient.discovery import build
    api = build("youtube", "v3", credentials=credenziali(k), cache_discovery=False)
    return int(api.channels().list(part="statistics", mine=True).execute()["items"][0]["statistics"]["viewCount"])


def totali_youtube(storico, registro):
    """6/11/2026: giorno -> totale del canale salvato quel giorno, dal PC (file locale) e da GitHub (registro). Il piu'
    basso, cioe' il primo del giorno, il piu' vicino alle 8."""
    out = {}
    for fonte in (storico, (registro or {}).get("giorni") or {}):
        for g, v in fonte.items():
            t = v.get("youtube_totale") if isinstance(v, dict) else None
            if isinstance(t, int):
                out[g] = min(t, out.get(g, t))
    return out


def instagram(k, oggi):
    """Giorni interi come Facebook: le ultime ore Instagram le conta in ritardo (272 invece di 1.533 il 1/11/2026)."""
    fine = int(datetime.datetime(oggi.year, oggi.month, oggi.day, tzinfo=ROMA).timestamp())
    def viste(giorni):
        r = requests.get(f"{GRAPH}/{k['IG_USER_ID']}/insights", timeout=30, params={
            "metric": "views", "period": "day", "metric_type": "total_value", "since": fine - giorni * 86400, "until": fine,
            "access_token": k["META_PAGE_TOKEN"]}).json()
        return r["data"][0]["total_value"]["value"]
    return viste(1), viste(7)


def facebook(k, oggi):
    """Facebook da' solo giorni interi: l'ultimo giorno completo e gli ultimi 7."""
    r = requests.get(f"{GRAPH}/{k['FB_PAGE_ID']}/insights", timeout=30, params={
        "metric": "page_media_view", "period": "day", "since": (oggi - datetime.timedelta(days=7)).isoformat(),
        "until": oggi.isoformat(), "access_token": k["META_PAGE_TOKEN"]}).json()
    valori = [v["value"] for v in r["data"][0]["values"]]
    return valori[-1], sum(valori[-7:])


def data_tiktok(testo, oggi):
    """'4 novembre' (senza anno: quello che non cade nel futuro), 'November 4', '2026-11-04', '04/11/2026' -> date."""
    s = str(testo or "").strip().lower()
    try:
        m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
        if m:
            return datetime.date(int(m[1]), int(m[2]), int(m[3]))
        m = re.fullmatch(r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})", s)
        if m:
            return datetime.date(int(m[3]), int(m[2]), int(m[1]))
        mese = next((MESE_DA_PAROLA[p[:3]] for p in re.findall(r"[a-z]+", s) if p[:3] in MESE_DA_PAROLA), None)
        numeri = re.findall(r"\d+", s)
        giorni = [int(n) for n in numeri if len(n) <= 2]
        anni = [int(n) for n in numeri if len(n) == 4]
        if not mese or not giorni:
            return None
        d = datetime.date(anni[0] if anni else oggi.year, mese, giorni[0])
        if not anni and d > oggi:
            d = d.replace(year=oggi.year - 1)
        return d
    except ValueError:
        return None


def scegli_giorno_tiktok(righe, oggi):
    """6/11/2026: l'ultimo giorno COMPLETO del file (mai oggi, ancora a meta'). -> (views, views dei 7 giorni, data)."""
    campi = list(righe[0].keys()) if righe else []
    c_data = next((c for c in campi if c.strip().lower() in ("date", "data")), "Date")
    c_viste = next((c for c in campi if ("view" in c.lower() or "visualizz" in c.lower()) and "profil" not in c.lower()),
                   "Video Views")
    giorni = {}
    for r in righe:
        d = data_tiktok(r.get(c_data), oggi)
        try:
            v = int(re.sub(r"[.,\s]", "", str(r.get(c_viste) or "")))
        except ValueError:
            continue
        if d and d < oggi:
            giorni[d] = v
    if not giorni:
        return None, None, None
    d = max(giorni)
    return giorni[d], sum(v for g, v in giorni.items() if 0 <= (d - g).days < 7), d


def tiktok_da_file(oggi):
    """1/11/2026: il file di "Scarica dati" di TikTok Studio (zip con Overview.csv) ha i numeri esatti giorno per giorno.
    -> (views, views 7 giorni, data, file); solo un file scaricato nell'ultima ora."""
    file = glob.glob(os.path.join(os.path.expanduser("~"), "Downloads", "Overview_*.zip"))
    file = max(file, key=os.path.getmtime) if file else None
    if not file or time.time() - os.path.getmtime(file) > 3600:
        return None, None, None, None
    with zipfile.ZipFile(file) as z:
        nome = next((n for n in z.namelist() if n.lower().endswith("overview.csv")), "Overview.csv")
        righe = list(csv.DictReader(io.StringIO(z.read(nome).decode("utf-8-sig"))))
    v, sett, d = scegli_giorno_tiktok(righe, oggi)
    return v, sett, d, file


def tiktok_da_argomenti(argv, oggi):
    """6/11/2026: --tiktok N --tiktok-data AAAA-MM-GG, il numero di UN giorno letto dall'attivita' nella pagina di TikTok
    Studio quando il download non riesce. -> (views, data) oppure (None, None)."""
    def valore(nome):
        i = argv.index(nome) + 1 if nome in argv else len(argv)
        return argv[i] if i < len(argv) else None
    n, d = valore("--tiktok"), valore("--tiktok-data")
    if n is None or d is None:
        return None, None
    try:
        n, d = int(re.sub(r"[.,\s]", "", n)), datetime.date.fromisoformat(d)
    except ValueError:
        print("TikTok: --tiktok/--tiktok-data non validi, ignorati")
        return None, None
    return (n, d) if n >= 0 and d < oggi else (None, None)


def tiktok_ultimo_noto(storico, registro, oggi):
    """L'ultimo numero di TikTok salvato (file locale del PC o registro su GitHub) -> (views, data)."""
    candidati = []
    for t in [storico.get("tiktok_ultimo")] + [(g or {}).get("tiktok") for g in
                                               ((registro or {}).get("giorni") or {}).values()]:
        if not isinstance(t, dict):
            continue
        d = data_tiktok(t.get("data"), oggi)
        if d and isinstance(t.get("views"), int):
            candidati.append((d, t["views"]))
    if not candidati:
        return None, None
    d, v = max(candidati)
    return v, d


def punti(n):
    return f"{n:,}".replace(",", ".")


def messaggio(giorno, oggi, data_tt, note):
    """Il formato di Alessandro (3/11/2026): titolo, il giorno, poi un social per riga. 6/11/2026: accanto a TikTok il
    giorno solo se non e' ieri; in fondo il TOTALE (permesso da lui) quando ci sono tutti e quattro."""
    ieri = oggi - datetime.timedelta(days=1)
    righe = [avvisi.TITOLO_STATISTICHE, f"{ieri.day} {MESI[ieri.month - 1]} {ieri.year}"]
    nomi = ("Facebook", "Instagram", "TikTok", "YouTube")
    for nome in nomi:
        v = giorno.get(nome)
        if v is None:
            righe.append(f"{nome}: non disponibile")
            continue
        coda = note.get(nome, "")
        if nome == "TikTok" and data_tt and data_tt != ieri:     # TikTok arriva con 1-2 giorni di ritardo
            coda = f" (del {data_tt.day} {MESI[data_tt.month - 1]})"
        righe.append(f"{nome}: {punti(v)}{coda}")
    if all(giorno.get(n) is not None for n in nomi):
        righe.append(f"TOTALE: {punti(sum(giorno[n] for n in nomi))}")
    return "\n".join(righe)


def reel_mancanti(oggi, k, aggiorna=True):
    """1/11/2026: se ieri sono usciti meno di 10 reel su YouTube o Instagram, una riga di errore (solo nel log)."""
    if aggiorna:
        subprocess.run(["git", "pull", "-q", "--ff-only"], cwd=QUI, capture_output=True, timeout=60)
    storia = json.load(open(os.path.join(QUI, "stato.json"), encoding="utf-8"))["storico"]
    ieri = (oggi - datetime.timedelta(days=1)).isoformat()
    out = []
    for p, nome in (("youtube", "YouTube"), ("instagram", "Instagram")):
        n = sum(1 for h in storia if str(h.get("slot") or h.get("quando", "")).startswith(ieri)
                and (h.get("risultati") or {}).get(p, {}).get("ok"))
        if n < 10:
            out.append(f"{nome}: ieri usciti {n} reel su 10")
    # 3/11/2026: Instagram deve avere il brano DI INSTAGRAM (scelta di Alessandro): se manca su qualche reel, errore
    try:
        ids = [h["risultati"]["instagram"]["id"] for h in storia if str(h.get("slot", "")).startswith(ieri)
               and (h.get("risultati") or {}).get("instagram", {}).get("ok")
               and (h.get("montaggio") or {}).get("formato") not in ("parlato", "momento")]
        musica = sum(requests.get(f"https://graph.facebook.com/v25.0/{i}", timeout=30, params={
            "fields": "media_audio_type", "access_token": k["META_PAGE_TOKEN"]}).json().get("media_audio_type") == "MUSIC"
            for i in ids)
        if ids and musica < len(ids):
            out.append(f"Instagram: ieri {musica} reel su {len(ids)} con la musica di Instagram")
    except Exception as e:
        out.append(f"Instagram, controllo musica: {e}")
    return out


# ------------------------------------------------------------------ registro su GitHub (6/11/2026)
def token_github(su_github):
    """GitHub: il token del lavoro. PC: il collegamento gia' salvato per git push (come avvia_pubblicazione.py),
    senza finestre di accesso. Mai stampato."""
    if su_github:
        return os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    try:
        env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
        r = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
                           capture_output=True, text=True, timeout=60, env=env, cwd=QUI)
        for riga in r.stdout.splitlines():
            if riga.startswith("password="):
                return riga.split("=", 1)[1]
    except Exception as e:
        print("GitHub: collegamento del PC non letto:", type(e).__name__)
    return None


def _github(metodo, tok, **kw):
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if tok:
        h["Authorization"] = "Bearer " + tok
    for i in range(4):           # la rete del PC a volte non risponde (DNS, 3/11): si riprova
        try:
            return requests.request(metodo, API_REGISTRO, headers=h, timeout=30, **kw)
        except requests.RequestException:
            if i == 3:
                raise
            time.sleep(10 * (i + 1))


def registro_leggi(tok):
    """(dati, sha) del registro su main; ({}, None) se non c'e' ancora. Il repository e' pubblico: si legge anche
    senza collegamento."""
    r = _github("GET", tok, params={"ref": "main"})
    if r.status_code == 404:
        return {}, None
    r.raise_for_status()
    j = r.json()
    try:
        dati = json.loads(base64.b64decode(j["content"]).decode("utf-8"))
    except ValueError:
        dati = None
    if not isinstance(dati, dict):       # file rovinato (a mano?): si riparte da vuoto, il messaggio parte lo stesso
        dati = {}
    if not isinstance(dati.get("giorni"), dict):
        dati["giorni"] = {}
    return dati, j["sha"]


def registro_aggiorna(tok, cambia, messaggio_commit):
    """cambia(dati) modifica il registro appena letto (False = niente da fare). Si scrive solo se nessuno l'ha cambiato
    nel frattempo (sha): se PC e GitHub scrivono insieme, uno solo vince e l'altro rilegge. True se scritto."""
    for i in range(6):
        dati, sha = registro_leggi(tok)
        prima = json.dumps(dati, sort_keys=True)
        if cambia(dati) is False or json.dumps(dati, sort_keys=True) == prima:
            return False
        corpo = {"message": messaggio_commit, "branch": "main",
                 "committer": {"name": "reel-bot", "email": "reel-bot@users.noreply.github.com"},
                 "content": base64.b64encode((json.dumps(dati, indent=1, ensure_ascii=False) + "\n").encode()).decode()}
        if sha:
            corpo["sha"] = sha
        r = _github("PUT", tok, json=corpo)
        if r.status_code in (200, 201):
            return True
        if r.status_code not in (409, 422):      # 409/422: cambiato (o creato) da un altro nel frattempo
            raise RuntimeError(f"GitHub {r.status_code}: {r.text[:150]}")
        time.sleep(2 + 3 * i)
    raise RuntimeError("registro cambiato troppe volte di seguito")


def prenota(tok, oggi, chi):
    """Prima di mandare: (True, "") se tocca a me, (False, motivo) se il messaggio di oggi e' gia' partito o sta
    partendo dall'altro mittente."""
    ora = adesso()
    motivo = [""]
    def cambia(dati):
        g = dati.setdefault("giorni", {}).setdefault(oggi.isoformat(), {})
        if g.get("inviato"):
            motivo[0] = f"gia' mandato da {g.get('da', '?')} alle {g['inviato']}"
            return False
        p = g.get("invio") or {}
        if p.get("da") and p["da"] != chi:
            try:
                fresca = ora - datetime.datetime.fromisoformat(p["ora"]) < datetime.timedelta(minutes=PRENOTAZIONE_MINUTI)
            except (KeyError, TypeError, ValueError):
                fresca = False
            if fresca:
                motivo[0] = f"lo sta mandando {p['da']}"
                return False
        g["invio"] = {"da": chi, "ora": ora.isoformat(timespec="seconds")}
        if chi == "pc":
            dati.setdefault("pc_dal", oggi.isoformat())
    if registro_aggiorna(tok, cambia, f"Statistiche {oggi}: in invio ({chi})"):
        return True, ""
    if not motivo[0]:          # la prenotazione c'era gia' (stesso mittente): tocca comunque a me
        return True, ""
    return False, motivo[0]


def registra_giorno(tok, oggi, chi, inviato_alle, youtube_tot, tiktok, numeri):
    """Dopo il giro: chi ha mandato e quando, il totale YouTube di oggi (il primo del giorno: base delle 24 ore di
    domani) e l'ultimo numero di TikTok. Senza invio toglie la propria prenotazione (l'altro puo' riprovare)."""
    def cambia(dati):
        giorni = dati.setdefault("giorni", {})
        g = giorni.setdefault(oggi.isoformat(), {})
        if inviato_alle and not g.get("inviato"):
            g.update(inviato=inviato_alle, da=chi, numeri=numeri)
        if (g.get("invio") or {}).get("da") == chi:
            del g["invio"]
        if youtube_tot is not None:
            g.setdefault("youtube_totale", youtube_tot)
        if tiktok and tiktok["data"] >= (g.get("tiktok") or {}).get("data", ""):
            g["tiktok"] = tiktok
        if chi == "pc":
            dati.setdefault("pc_dal", oggi.isoformat())
        for vecchio in sorted(giorni)[:-GIORNI_TENUTI]:
            del giorni[vecchio]
    return registro_aggiorna(tok, cambia, f"Statistiche {oggi} ({chi})")


# ------------------------------------------------------------------ giro
def main():
    sys.stdout.reconfigure(encoding="utf-8")
    argv = sys.argv[1:]
    su_github, prova = "--github" in argv, "--prova" in argv
    chi = "github" if su_github else "pc"
    ora = adesso()
    oggi = ora.date()
    if not su_github and not prova and not PC_DALLE <= (ora.hour, ora.minute) < PC_FINO:
        print(f"Statistiche: fuori orario ({ora:%H:%M}), niente messaggio di notte")
        return
    tok = None if prova else token_github(su_github)     # in prova si legge e basta (repository pubblico)
    if not tok and not prova:
        print("ATTENZIONE: collegamento a GitHub non trovato: il registro dei messaggi non si aggiorna")
    try:
        registro, _ = registro_leggi(tok)
    except Exception as e:
        registro = None
        print("Registro su GitHub non letto:", pulito(e)[:150])
    reg_oggi = ((registro or {}).get("giorni") or {}).get(oggi.isoformat()) or {}
    if su_github:            # riserva: solo se serve davvero (mai due messaggi nello stesso giorno)
        fermo = None
        if registro is None:
            fermo = "registro non letto"
        elif not registro.get("pc_dal"):
            fermo = "il PC non scrive ancora nel registro"
        elif not RISERVA_DALLE <= (ora.hour, ora.minute) < RISERVA_FINO:
            fermo = f"fuori orario ({ora:%H:%M})"
        elif reg_oggi.get("inviato"):
            fermo = f"messaggio di oggi gia' mandato da {reg_oggi.get('da', '?')} alle {reg_oggi['inviato']}"
        if fermo and not prova:
            print("Riserva GitHub: non mando,", fermo)
            return
        if fermo:
            print("(prova) la riserva adesso non manderebbe:", fermo)
    storico, ora_file = {}, None
    if not su_github and os.path.exists(STORICO):
        storico = json.load(open(STORICO, encoding="utf-8"))
        ora_file = datetime.datetime.fromtimestamp(os.path.getmtime(STORICO), ROMA)
    k = segreti(su_github)
    giorno, settimana, errori, note = {}, {}, [], {}
    tot = None
    try:
        tot = youtube_totale(k)
        totali = totali_youtube(storico, registro)
        for g in range(1, 8):       # 3/11/2026: manca il totale di ieri (giro saltato): dall'ultimo salvato
            prima = totali.get((oggi - datetime.timedelta(days=g)).isoformat())
            if prima is not None:
                giorno["YouTube"] = tot - prima
                if g > 1:
                    note["YouTube"] = f" (ultimi {g} giorni)"
                break
        prima = totali.get((oggi - datetime.timedelta(days=7)).isoformat())
        settimana["YouTube"] = tot - prima if prima is not None else None
    except Exception as e:
        errori.append(f"YouTube: {e}")
    for nome, f in (("Instagram", lambda: instagram(k, oggi)), ("Facebook", lambda: facebook(k, oggi))):
        try:
            giorno[nome], settimana[nome] = f()
        except Exception as e:
            errori.append(f"{nome}: {e}")
    # TikTok: il file appena scaricato, se no il numero letto nella pagina, se no l'ultimo salvato (6/11/2026)
    file_tiktok = data_tt = tiktok_nuovo = None
    if not su_github:
        scelte = []
        try:
            v, sett, d, file_tiktok = tiktok_da_file(oggi)
            if v is not None:
                scelte.append((d, 1, v, sett))
            elif file_tiktok:
                errori.append("TikTok: nel file nessun giorno completo")
        except Exception as e:
            errori.append(f"TikTok: {e}")
        v, d = tiktok_da_argomenti(argv, oggi)
        if v is not None:
            scelte.append((d, 0, v, None))
        if scelte:
            data_tt, _, giorno["TikTok"], settimana["TikTok"] = max(scelte)
            tiktok_nuovo = {"data": data_tt.isoformat(), "views": giorno["TikTok"]}
    if giorno.get("TikTok") is None:      # 3/11/2026: se oggi manca, l'ultimo salvato (con il suo giorno)
        giorno["TikTok"], data_tt = tiktok_ultimo_noto(storico, registro, oggi)
    if data_tt and (oggi - data_tt).days > TIKTOK_MAX_GIORNI:
        errori.append(f"TikTok: l'ultimo numero e' del {data_tt}, troppo vecchio: non disponibile")
        giorno["TikTok"] = data_tt = None
    for nome in ("YouTube", "Instagram", "Facebook"):
        if giorno.get(nome) is not None and giorno[nome] < 0:      # mai un numero assurdo nel messaggio
            errori.append(f"{nome}: {giorno[nome]} (negativo): non disponibile")
            giorno[nome] = None
    if not su_github:
        try:
            errori += reel_mancanti(oggi, k, aggiorna=not prova)
        except Exception as e:
            errori.append(f"Conteggio reel: {e}")
    # 3/11/2026 (Alessandro): "solamente le visualizzazioni delle ultime 24 ore con il giorno, e poi sotto facebook,
    # instagram, tiktok e youtube, ogni social daccapo": niente 7 giorni e niente errori nel messaggio (restano nel log)
    testo = messaggio(giorno, oggi, data_tt, note)
    if errori:
        print("ERRORI (non inviati su Telegram):", *map(pulito, errori), sep="\n")
    print(testo)
    loc = storico.get(oggi.isoformat()) or {}
    # gia' partito oggi? Registro su GitHub, oppure il file del PC ("v" manca = giro col codice di prima del 6/11,
    # che salvava i numeri e subito dopo mandava: l'ora del file e' quella dell'invio)
    gia = reg_oggi.get("inviato") and f"gia' mandato da {reg_oggi.get('da', '?')} alle {reg_oggi['inviato']}"
    ora_pc = loc.get("inviato") or (loc.get("giorno") and not loc.get("v") and ora_file and f"{ora_file:%H:%M}")
    gia_dal_pc = bool(not su_github and ora_pc)
    if not gia and gia_dal_pc:
        gia = f"gia' mandato dal PC alle {ora_pc}"
    if prova:
        print("(prova: niente inviato e niente salvato)" + (f" Il messaggio di oggi e' {gia}." if gia else ""))
        return
    if not gia:
        if tok and registro is not None:
            try:
                ok, motivo = prenota(tok, oggi, chi)
                if not ok:
                    gia = motivo
            except Exception as e:
                print("Registro su GitHub: prenotazione non riuscita:", pulito(e)[:150])
                if su_github:
                    raise SystemExit("Riserva GitHub: senza prenotazione non mando (mai due messaggi)")
        elif su_github:
            raise SystemExit("Riserva GitHub: senza collegamento al registro non mando (mai due messaggi)")
    inviato_alle = None
    if gia:
        print(f"Messaggio di oggi {gia}: non lo rimando.")
    else:
        if not su_github:
            os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"] = k["TELEGRAM_BOT_TOKEN"], k["TELEGRAM_CHAT_ID"]
        if avvisi.manda_statistiche(testo):
            inviato_alle = adesso().strftime("%H:%M")
    if not su_github:
        try:
            g = storico.setdefault(oggi.isoformat(), {})
            if tot is not None:
                g.setdefault("youtube_totale", tot)      # 6/11/2026: il primo del giorno (un secondo giro non lo sposta)
            g.update(giorno=giorno, settimana=settimana, v=2)
            if inviato_alle:
                g["inviato"] = inviato_alle
            if tiktok_nuovo:
                storico["tiktok_ultimo"] = tiktok_nuovo
            json.dump(storico, open(STORICO, "w", encoding="utf-8"), indent=1)
        except Exception as e:
            print("ATTENZIONE: statistiche_giornaliere.json non salvato:", pulito(e)[:150])
    if tok:
        try:          # se l'aveva gia' mandato il PC (giro di prima) lo si segna ora, cosi' GitHub non lo rimanda
            segna = inviato_alle or (ora_pc if gia_dal_pc and not reg_oggi.get("inviato") else None)
            registra_giorno(tok, oggi, chi, segna, tot, tiktok_nuovo, giorno)
        except Exception as e:
            print("ATTENZIONE: registro su GitHub non aggiornato:", pulito(e)[:150])
    if not inviato_alle and not gia:
        raise SystemExit("Telegram non ha ricevuto il messaggio")
    if file_tiktok:      # un solo file, cosi' la cartella Download non si riempie
        os.replace(file_tiktok, os.path.join(os.path.expanduser("~"), "statistiche_tiktok_ultimo.zip"))


if __name__ == "__main__":
    main()
