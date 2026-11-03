"""
Visualizzazioni delle ultime 24 ore e degli ultimi 7 giorni su Telegram (1/11/2026, richiesta di Alessandro: ogni mattina
alle 8, Facebook, Instagram, TikTok e YouTube, solo questi dati). Gira sul PC dall'attivita' "statistiche-mattina": TikTok non ha un'API per i numeri, quindi l'attivita'
scarica il file da TikTok Studio e lo script lo legge da Download.

  python statistiche.py [--prova]     --prova: stampa e non manda
"""
import csv, datetime, glob, io, json, os, subprocess, sys, time, zipfile
import requests
from zoneinfo import ZoneInfo

SEGRETI = os.path.join(os.path.expanduser("~"), "reel-segreti.json")
STORICO = os.path.join(os.path.expanduser("~"), "statistiche_giornaliere.json")
GRAPH = "https://graph.facebook.com/v23.0"


def credenziali(k):
    from google.oauth2.credentials import Credentials
    return Credentials(None, refresh_token=k.get("YOUTUBE_REFRESH_TOKEN") or k["GOOGLE_REFRESH_TOKEN"],
                       client_id=k.get("YOUTUBE_CLIENT_ID") or k["GOOGLE_CLIENT_ID"],
                       client_secret=k.get("YOUTUBE_CLIENT_SECRET") or k["GOOGLE_CLIENT_SECRET"],
                       token_uri="https://oauth2.googleapis.com/token")


def youtube(k, oggi, storico):
    """Il totale del canale oggi meno quello di ieri e di 7 giorni fa: i report di YouTube arrivano con 3 giorni di ritardo."""
    from googleapiclient.discovery import build
    api = build("youtube", "v3", credentials=credenziali(k), cache_discovery=False)
    tot = int(api.channels().list(part="statistics", mine=True).execute()["items"][0]["statistics"]["viewCount"])
    def da(giorni):
        prima = storico.get((oggi - datetime.timedelta(days=giorni)).isoformat(), {}).get("youtube_totale")
        return tot - prima if prima is not None else None
    return tot, da(1), da(7)


def instagram(k, oggi):
    """Giorni interi come Facebook: le ultime ore Instagram le conta in ritardo (272 invece di 1.533 il 1/11/2026)."""
    fine = int(datetime.datetime(oggi.year, oggi.month, oggi.day, tzinfo=ZoneInfo("Europe/Rome")).timestamp())
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


def tiktok():
    """1/11/2026: il file di "Scarica dati" di TikTok Studio (zip con Overview.csv) ha i numeri esatti giorno per giorno."""
    file = glob.glob(os.path.join(os.path.expanduser("~"), "Downloads", "Overview_*.zip"))
    file = max(file, key=os.path.getmtime) if file else None
    if not file or time.time() - os.path.getmtime(file) > 3600:
        return None, None, None, None
    z = zipfile.ZipFile(file)
    righe = list(csv.DictReader(io.StringIO(z.read("Overview.csv").decode("utf-8-sig"))))[-7:]
    z.close()
    return int(righe[-1]["Video Views"]), sum(int(r["Video Views"]) for r in righe), righe[-1]["Date"], file


def reel_mancanti(oggi):
    """1/11/2026: se ieri sono usciti meno di 10 reel su YouTube o Instagram, una riga di errore in fondo al messaggio."""
    qui = os.path.dirname(os.path.abspath(__file__))
    subprocess.run(["git", "pull", "-q", "--ff-only"], cwd=qui, capture_output=True, timeout=60)
    storia = json.load(open(os.path.join(qui, "stato.json"), encoding="utf-8"))["storico"]
    ieri = (oggi - datetime.timedelta(days=1)).isoformat()
    out = []
    for p, nome in (("youtube", "YouTube"), ("instagram", "Instagram")):
        n = sum(1 for h in storia if str(h.get("slot") or h.get("quando", "")).startswith(ieri)
                and (h.get("risultati") or {}).get(p, {}).get("ok"))
        if n < 10:
            out.append(f"{nome}: ieri usciti {n} reel su 10")
    # 3/11/2026: Instagram deve avere il brano DI INSTAGRAM (scelta di Alessandro): se manca su qualche reel, errore
    try:
        import requests
        tok = json.load(open(SEGRETI, encoding="utf-8"))["META_PAGE_TOKEN"]
        ids = [h["risultati"]["instagram"]["id"] for h in storia if str(h.get("slot", "")).startswith(ieri)
               and (h.get("risultati") or {}).get("instagram", {}).get("ok")
               and (h.get("montaggio") or {}).get("formato") not in ("parlato", "momento")]
        musica = sum(requests.get(f"https://graph.facebook.com/v25.0/{i}", timeout=30, params={
            "fields": "media_audio_type", "access_token": tok}).json().get("media_audio_type") == "MUSIC" for i in ids)
        if ids and musica < len(ids):
            out.append(f"Instagram: ieri {musica} reel su {len(ids)} con la musica di Instagram")
    except Exception as e:
        out.append(f"Instagram, controllo musica: {e}")
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    k = json.load(open(SEGRETI, encoding="utf-8"))
    oggi = datetime.datetime.now(ZoneInfo("Europe/Rome")).date()
    storico = json.load(open(STORICO, encoding="utf-8")) if os.path.exists(STORICO) else {}
    giorno, settimana, errori = {}, {}, []
    tot = None
    note = {}
    try:
        tot, giorno["YouTube"], settimana["YouTube"] = youtube(k, oggi, storico)
        if giorno["YouTube"] is None:     # 3/11/2026: manca il totale di ieri (giro saltato): dall'ultimo salvato
            for g in range(2, 8):
                d = (oggi - datetime.timedelta(days=g)).isoformat()
                if storico.get(d, {}).get("youtube_totale") is not None:
                    giorno["YouTube"] = tot - storico[d]["youtube_totale"]
                    note["YouTube"] = f" (ultimi {g} giorni)"
                    break
    except Exception as e:
        errori.append(f"YouTube: {e}")
    for nome, f in (("Instagram", lambda: instagram(k, oggi)), ("Facebook", lambda: facebook(k, oggi))):
        try:
            giorno[nome], settimana[nome] = f()
        except Exception as e:
            errori.append(f"{nome}: {e}")
    file_tiktok = data_tiktok = None
    try:
        giorno["TikTok"], settimana["TikTok"], data_tiktok, file_tiktok = tiktok()
    except Exception as e:
        errori.append(f"TikTok: {e}")
    # 3/11/2026: TikTok non ha API per i numeri e il download da Chrome a volte non riesce: si salva l'ultimo dato
    # e, se oggi manca, si mostra quello (con il suo giorno) invece di "non disponibile"
    if giorno.get("TikTok") is not None:
        storico["tiktok_ultimo"] = {"data": data_tiktok, "views": giorno["TikTok"]}
    elif storico.get("tiktok_ultimo"):
        giorno["TikTok"], data_tiktok = storico["tiktok_ultimo"]["views"], storico["tiktok_ultimo"]["data"]
    try:
        errori += reel_mancanti(oggi)
    except Exception as e:
        errori.append(f"Conteggio reel: {e}")
    def blocco(titolo, numeri):
        righe = [titolo]
        for nome in ("Facebook", "Instagram", "TikTok", "YouTube"):
            v = numeri.get(nome)
            coda = f" (del {data_tiktok})" if nome == "TikTok" and data_tiktok else note.get(nome, "")   # TikTok arriva con 1-2 giorni di ritardo
            righe.append(f"{nome}: {v:,}".replace(",", ".") + coda if v is not None else f"{nome}: non disponibile")
        return righe
    # 3/11/2026 (Alessandro): "solamente le visualizzazioni delle ultime 24 ore con il giorno, e poi sotto facebook,
    # instagram, tiktok e youtube, ogni social daccapo": niente 7 giorni e niente errori nel messaggio (restano nel log)
    mesi = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre",
            "novembre", "dicembre"]
    ieri = oggi - datetime.timedelta(days=1)
    righe = blocco("VISUALIZZAZIONI ULTIME 24 ORE", giorno)
    righe.insert(1, f"{ieri.day} {mesi[ieri.month - 1]} {ieri.year}")
    testo = "\n".join(righe)
    if errori:
        print("ERRORI (non inviati su Telegram):", *errori, sep="\n")
    print(testo)
    if "--prova" in sys.argv:
        return
    if tot is not None:
        storico.setdefault(oggi.isoformat(), {})["youtube_totale"] = tot
    storico.setdefault(oggi.isoformat(), {}).update({"giorno": giorno, "settimana": settimana})
    json.dump(storico, open(STORICO, "w", encoding="utf-8"), indent=1)
    os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"] = k["TELEGRAM_BOT_TOKEN"], k["TELEGRAM_CHAT_ID"]
    import avvisi
    if not avvisi.manda_statistiche(testo):
        raise SystemExit("Telegram non ha ricevuto il messaggio")
    if file_tiktok:      # un solo file, cosi' la cartella Download non si riempie
        os.replace(file_tiktok, os.path.join(os.path.expanduser("~"), "statistiche_tiktok_ultimo.zip"))


if __name__ == "__main__":
    main()
