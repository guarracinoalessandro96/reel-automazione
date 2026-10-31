"""
Statistiche del giorno prima su Telegram (31/10/2026, richiesta di Alessandro: ogni mattina alle 8, Facebook, Instagram,
YouTube e TikTok). Gira sul PC dall'attivita' "statistiche-mattina": TikTok non ha un'API per i numeri, quindi l'attivita'
li legge da TikTok Studio e li passa con --tiktok.

  python statistiche.py [--tiktok 1234] [--prova]     --prova: stampa e non manda
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


def youtube(k, ieri, storico):
    """Il totale del canale oggi meno quello di ieri mattina: i report di YouTube arrivano con 2 giorni di ritardo."""
    from googleapiclient.discovery import build
    api = build("youtube", "v3", credentials=credenziali(k), cache_discovery=False)
    tot = int(api.channels().list(part="statistics", mine=True).execute()["items"][0]["statistics"]["viewCount"])
    prima = storico.get(ieri.isoformat(), {}).get("youtube_totale")
    return tot, (tot - prima if prima is not None else None)


def instagram(k, ieri):
    da = int(datetime.datetime(ieri.year, ieri.month, ieri.day, tzinfo=ZoneInfo("Europe/Rome")).timestamp())
    r = requests.get(f"{GRAPH}/{k['IG_USER_ID']}/insights", timeout=30, params={
        "metric": "views", "period": "day", "metric_type": "total_value", "since": da, "until": da + 86400,
        "access_token": k["META_PAGE_TOKEN"]}).json()
    return r["data"][0]["total_value"]["value"]


def facebook(k, ieri):
    r = requests.get(f"{GRAPH}/{k['FB_PAGE_ID']}/insights", timeout=30, params={
        "metric": "page_media_view", "period": "day", "since": ieri.isoformat(),
        "until": (ieri + datetime.timedelta(days=1)).isoformat(), "access_token": k["META_PAGE_TOKEN"]}).json()
    return sum(v["value"] for v in r["data"][0]["values"])


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    k = json.load(open(SEGRETI, encoding="utf-8"))
    oggi = datetime.datetime.now(ZoneInfo("Europe/Rome")).date()
    ieri = oggi - datetime.timedelta(days=1)
    storico = json.load(open(STORICO, encoding="utf-8")) if os.path.exists(STORICO) else {}
    numeri, errori = {}, []
    tot = None
    try:
        tot, numeri["YouTube"] = youtube(k, ieri, storico)
    except Exception as e:
        errori.append(f"YouTube: {e}")
    for nome, f in (("Instagram", instagram), ("Facebook", facebook)):
        try:
            numeri[nome] = f(k, ieri)
        except Exception as e:
            errori.append(f"{nome}: {e}")
    if "--tiktok" in sys.argv:
        numeri["TikTok"] = int(sys.argv[sys.argv.index("--tiktok") + 1])
    righe = [f"STATISTICHE DI IERI ({ieri:%d/%m})", ""]
    for nome in ("YouTube", "Instagram", "Facebook", "TikTok"):
        v = numeri.get(nome)
        righe.append(f"{nome}: {v:,}".replace(",", ".") if v is not None else f"{nome}: non disponibile")
    if all(isinstance(numeri.get(n), int) for n in ("YouTube", "Instagram", "Facebook", "TikTok")):
        righe += ["", f"Totale: {sum(numeri.values()):,}".replace(",", ".")]
    if errori:
        righe += ["", "ERRORE", *errori]
    testo = "\n".join(righe)
    print(testo)
    if "--prova" in sys.argv:
        return
    if tot is not None:
        storico.setdefault(oggi.isoformat(), {})["youtube_totale"] = tot
    storico.setdefault(ieri.isoformat(), {}).update({"numeri": numeri})
    json.dump(storico, open(STORICO, "w", encoding="utf-8"), indent=1)
    os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"] = k["TELEGRAM_BOT_TOKEN"], k["TELEGRAM_CHAT_ID"]
    import avvisi
    if not avvisi.manda(testo):
        raise SystemExit("Telegram non ha ricevuto il messaggio")


if __name__ == "__main__":
    main()
