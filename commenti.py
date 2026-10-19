"""
Commenti nuovi su YouTube (19/10/2026): una volta al giorno, la sera, arrivano su Telegram con il link per rispondere
dal telefono. Alessandro vuole che le persone si affezionino a LUI: rispondere di persona ai commenti e' il modo piu'
diretto (e YouTube premia i video con conversazioni). Solo lettura: non scrive niente su YouTube (i commenti
automatici sono stati spenti su sua richiesta).
Lo chiama pubblica.py dopo ogni pubblicazione: il primo giro dalle ORA_INVIO in poi manda il riassunto di tutto
quello che e' arrivato dall'ultimo invio (stato["commenti_fino"]), quindi niente si perde anche se un giro salta.
"""
import datetime, os

ENV = os.environ.get
ORA_INVIO = 20            # ora di Roma: dopo il lavoro
MAX_COMMENTI = 15         # nel messaggio (Telegram: massimo ~4.000 caratteri)


def _youtube():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    c = Credentials(None, refresh_token=ENV("GOOGLE_REFRESH_TOKEN"), client_id=ENV("GOOGLE_CLIENT_ID"),
                    client_secret=ENV("GOOGLE_CLIENT_SECRET"), token_uri="https://oauth2.googleapis.com/token")
    return build("youtube", "v3", credentials=c, cache_discovery=False)


def nuovi(da, a):
    """Commenti (non suoi) scritti tra da e a (stringhe ISO UTC "2026-10-19T18:00:00Z"), dal piu' recente."""
    yt = _youtube()
    canale = yt.channels().list(part="id", mine=True).execute()["items"][0]["id"]
    out, pagina = [], None
    for _ in range(5):                                   # al massimo 500 commenti
        r = yt.commentThreads().list(part="snippet", allThreadsRelatedToChannelId=canale, maxResults=100,
                                     order="time", textFormat="plainText", pageToken=pagina).execute()
        for it in r.get("items", []):
            s = it["snippet"]["topLevelComment"]["snippet"]
            if s["publishedAt"] < da:
                return out
            if s["publishedAt"] >= a or (s.get("authorChannelId") or {}).get("value") == canale:
                continue
            out.append({"chi": s.get("authorDisplayName") or "?", "testo": " ".join(s.get("textOriginal", "").split()),
                        "link": f"https://www.youtube.com/watch?v={s.get('videoId') or it['snippet'].get('videoId')}"
                                f"&lc={it['snippet']['topLevelComment']['id']}"})
        pagina = r.get("nextPageToken")
        if not pagina:
            break
    return out


def testo(commenti):
    """Messaggio Telegram: un dato per riga, titoli in maiuscolo."""
    righe = ["COMMENTI NUOVI SU YOUTUBE", f"{len(commenti)} dall'ultimo messaggio",
             "Rispondi tu, di persona: e' cosi' che le persone si affezionano"]
    for c in commenti[:MAX_COMMENTI]:
        t = c["testo"] if len(c["testo"]) <= 180 else c["testo"][:177].rsplit(" ", 1)[0] + "..."
        righe += ["", c["chi"], t, c["link"]]
    if len(commenti) > MAX_COMMENTI:
        righe += ["", f"Altri {len(commenti) - MAX_COMMENTI} nell'app YouTube Studio"]
    return "\n".join(righe)


def forse_manda(state, adesso):
    """adesso = ora di Roma (datetime con fuso). Manda il riassunto una volta al giorno, dopo ORA_INVIO."""
    utc = adesso.astimezone(datetime.timezone.utc)
    soglia = adesso.replace(hour=ORA_INVIO, minute=0, second=0, microsecond=0).astimezone(datetime.timezone.utc)
    fino = state.get("commenti_fino") or (utc - datetime.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    if adesso.hour < ORA_INVIO or fino >= soglia.strftime("%Y-%m-%dT%H:%M:%SZ"):
        return None                                      # non e' ora, o gia' mandato oggi
    a = utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    commenti = nuovi(fino, a)
    if commenti:
        import avvisi
        avvisi.manda(testo(commenti))
    state["commenti_fino"] = a
    return len(commenti)
