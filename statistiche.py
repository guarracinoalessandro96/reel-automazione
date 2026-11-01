"""
Visualizzazioni delle ultime 24 ore e degli ultimi 7 giorni su Telegram (1/11/2026, richiesta di Alessandro: ogni mattina
alle 8, Facebook, Instagram, TikTok e YouTube, solo questi dati). Gira sul PC dall'attivita' "statistiche-mattina": TikTok non ha un'API per i numeri, quindi l'attivita'
li legge da TikTok Studio e li passa con --tiktok e --tiktok7.

  python statistiche.py [--tiktok 1234] [--tiktok7 5678] [--prova]     --prova: stampa e non manda
"""
import datetime, json, os, sys
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


def numero_arg(nome):
    return int(sys.argv[sys.argv.index(nome) + 1]) if nome in sys.argv else None


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    k = json.load(open(SEGRETI, encoding="utf-8"))
    oggi = datetime.datetime.now(ZoneInfo("Europe/Rome")).date()
    storico = json.load(open(STORICO, encoding="utf-8")) if os.path.exists(STORICO) else {}
    giorno, settimana, errori = {}, {}, []
    tot = None
    try:
        tot, giorno["YouTube"], settimana["YouTube"] = youtube(k, oggi, storico)
    except Exception as e:
        errori.append(f"YouTube: {e}")
    for nome, f in (("Instagram", lambda: instagram(k, oggi)), ("Facebook", lambda: facebook(k, oggi))):
        try:
            giorno[nome], settimana[nome] = f()
        except Exception as e:
            errori.append(f"{nome}: {e}")
    giorno["TikTok"], settimana["TikTok"] = numero_arg("--tiktok"), numero_arg("--tiktok7")
    def blocco(titolo, numeri):
        righe = [titolo]
        for nome in ("Facebook", "Instagram", "TikTok", "YouTube"):
            v = numeri.get(nome)
            righe.append(f"{nome}: {v:,}".replace(",", ".") if v is not None else f"{nome}: non disponibile")
        return righe
    righe = blocco("VISUALIZZAZIONI ULTIME 24 ORE", giorno) + [""] + blocco("VISUALIZZAZIONI ULTIMI 7 GIORNI", settimana)
    if errori:
        righe += ["", "ERRORE", *errori]
    testo = "\n".join(righe)
    print(testo)
    if "--prova" in sys.argv:
        return
    if tot is not None:
        storico.setdefault(oggi.isoformat(), {})["youtube_totale"] = tot
    storico.setdefault(oggi.isoformat(), {}).update({"giorno": giorno, "settimana": settimana})
    json.dump(storico, open(STORICO, "w", encoding="utf-8"), indent=1)
    os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"] = k["TELEGRAM_BOT_TOKEN"], k["TELEGRAM_CHAT_ID"]
    import avvisi
    if not avvisi.manda(testo):
        raise SystemExit("Telegram non ha ricevuto il messaggio")


if __name__ == "__main__":
    main()
