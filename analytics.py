"""
Statistiche di VISIONE degli Short (25/10/2026): quanto del video guardano e dove smettono di guardare.
Serve il permesso "yt-analytics.readonly" (collegamento/collega_google.py, da rifare una volta con Alessandro);
senza permesso restituisce None e l'agente usa solo views e like.

- visione(ids)        -> {id: {"views", "perc_vista", "secondi_visti", "like", "iscritti"}}
- curva(id)           -> [(frazione del video 0..1, quota di spettatori ancora presenti)]: dove si perde attenzione
- riassunto_curva(c)  -> {"dopo_1s", "a_meta", "alla_fine", "riguardato"} (es. alla_fine > 1 = lo riguardano)
"""
import datetime, os

ENV = os.environ.get


def _servizio():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    c = Credentials(None, refresh_token=ENV("GOOGLE_REFRESH_TOKEN"), client_id=ENV("GOOGLE_CLIENT_ID"),
                    client_secret=ENV("GOOGLE_CLIENT_SECRET"), token_uri="https://oauth2.googleapis.com/token")
    return build("youtubeAnalytics", "v2", credentials=c, cache_discovery=False)


def _rapporto(**p):
    oggi = datetime.date.today()
    return _servizio().reports().query(ids="channel==MINE", startDate=(oggi - datetime.timedelta(days=90)).isoformat(),
                                       endDate=oggi.isoformat(), **p).execute()


def visione(ids):
    """Metriche per video; None se manca il permesso."""
    out = {}
    try:
        for i in range(0, len(ids), 200):
            r = _rapporto(metrics="views,averageViewPercentage,averageViewDuration,likes,subscribersGained",
                          dimensions="video", filters="video==" + ",".join(ids[i:i + 200]), maxResults=200)
            for v, views, perc, dur, like, isc in r.get("rows", []):
                out[v] = {"views": views, "perc_vista": perc, "secondi_visti": dur, "like": like, "iscritti": isc}
    except Exception as e:
        if "insufficient" in str(e).lower() or "403" in str(e) or "scope" in str(e).lower():
            return None
        raise
    return out


def curva(video_id):
    """Ritenzione: [(frazione del video, spettatori ancora presenti rispetto all'inizio)]."""
    try:
        r = _rapporto(metrics="audienceWatchRatio", dimensions="elapsedVideoTimeRatio", filters=f"video=={video_id}")
    except Exception:
        return None
    return [(float(a), float(b)) for a, b in r.get("rows", [])]


def riassunto_curva(c):
    if not c:
        return None
    vicino = lambda x: min(c, key=lambda p: abs(p[0] - x))[1]
    return {"dopo_1s": round(vicino(0.1), 2), "a_meta": round(vicino(0.5), 2), "alla_fine": round(vicino(1.0), 2),
            "riguardato": vicino(1.0) > 1.0}


if __name__ == "__main__":       # prova: python analytics.py <id video>
    import json, sys
    k = json.load(open(os.path.join(os.path.expanduser("~"), "reel-segreti.json"), encoding="utf-8"))
    os.environ.update({x: k[x] for x in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN")})
    v = visione(sys.argv[1:])
    print("PERMESSO MANCANTE: rifare collegamento/collega_google.bat" if v is None else v)
    if v and sys.argv[1:]:
        print(riassunto_curva(curva(sys.argv[1])))
