"""
Report settimanale e ottimizzazione automatica (ogni lunedi', GitHub Actions).

1. Per ogni reel pubblicato negli ultimi 60 giorni legge le visualizzazioni (Instagram + YouTube).
2. Calcola la media per tema, scena e orario.
3. Aggiorna pesi.json: i temi che rendono di piu' vengono scelti piu' spesso (senza mai escluderne nessuno).
4. Salva il riassunto in docs/report.json (si vede sul sito, sotto la gara dei follower).
"""
import datetime, json, os
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "stato.json")
PESI = os.path.join(HERE, "pesi.json")
OUT = os.path.join(HERE, "docs", "report.json")
GRAPH = "https://graph.facebook.com/v23.0"
ENV = os.environ.get
MIN_POST = 10          # sotto questo numero di reel i dati sono troppo pochi per cambiare i pesi
K = 5                  # "prudenza": con pochi reel su un tema, il suo peso resta vicino alla media


def views_instagram(media_id):
    r = requests.get(f"{GRAPH}/{media_id}/insights", params={"metric": "views,reach,saved,shares",
                                                             "access_token": ENV("META_PAGE_TOKEN")}).json()
    if "error" in r:            # es. manca il permesso instagram_manage_insights: dato non disponibile (non "0")
        return None, {}
    out = {d["name"]: d["values"][0]["value"] for d in r.get("data", [])}
    return out.get("views", 0), out


def views_youtube(ids):
    if not ids or not ENV("GOOGLE_REFRESH_TOKEN"):
        return {}
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    c = Credentials(None, refresh_token=ENV("GOOGLE_REFRESH_TOKEN"), client_id=ENV("GOOGLE_CLIENT_ID"),
                    client_secret=ENV("GOOGLE_CLIENT_SECRET"), token_uri="https://oauth2.googleapis.com/token")
    yt = build("youtube", "v3", credentials=c, cache_discovery=False)
    res = {}
    for i in range(0, len(ids), 50):
        for it in yt.videos().list(part="statistics", id=",".join(ids[i:i + 50])).execute().get("items", []):
            res[it["id"]] = int(it["statistics"].get("viewCount", 0))
    return res


def media(gruppi):
    return {k: {"reel": len(v), "media_views": round(sum(v) / len(v))} for k, v in sorted(gruppi.items())}


def main():
    if not ENV("META_PAGE_TOKEN"):
        print("Account non collegati: niente da fare.")
        return
    state = json.load(open(STATE, encoding="utf-8"))
    limite = (datetime.datetime.now() - datetime.timedelta(days=60)).isoformat()
    post = [h for h in state.get("storico", []) if h.get("tema") and h.get("quando", "") >= limite
            and h.get("risultati", {}).get("instagram", {}).get("ok")]
    yt = views_youtube([h["risultati"]["youtube"]["id"] for h in post
                        if h["risultati"].get("youtube", {}).get("ok") and h["risultati"]["youtube"].get("id")])
    righe, ig_mancante = [], False
    for h in post:
        v_ig, dettagli = views_instagram(h["risultati"]["instagram"]["id"])
        if v_ig is None:
            ig_mancante, v_ig = True, 0
        v_yt = yt.get(h["risultati"].get("youtube", {}).get("id"), 0)
        righe.append({"quando": h["quando"], "tema": h["tema"], "scena": h.get("scena"),
                      "orario": (h.get("slot") or "").split(" ")[-1], "instagram": v_ig, "youtube": v_yt,
                      "views": v_ig + v_yt, "salvataggi": dettagli.get("saved", 0), "condivisioni": dettagli.get("shares", 0)})

    per = {"tema": {}, "scena": {}, "orario": {}}
    for r in righe:
        for k in per:
            per[k].setdefault(r[k] or "?", []).append(r["views"])
    media_tot = sum(r["views"] for r in righe) / len(righe) if righe else 0

    pesi = json.load(open(PESI, encoding="utf-8")) if os.path.exists(PESI) else {"temi": {}}
    if len(righe) >= MIN_POST and media_tot > 0:
        pesi["temi"] = {}
        for tema, v in per["tema"].items():
            stima = (sum(v) + K * media_tot) / (len(v) + K)          # media "prudente"
            pesi["temi"][tema] = round(min(max(stima / media_tot, 0.7), 1.5), 2)
        pesi["aggiornato"] = datetime.date.today().isoformat()
        json.dump(pesi, open(PESI, "w", encoding="utf-8"), indent=1, ensure_ascii=False)

    migliori = sorted(righe, key=lambda r: -r["views"])[:5]
    report = {"data": datetime.date.today().isoformat(), "reel_analizzati": len(righe),
              "media_views": round(media_tot), "per_tema": media(per["tema"]), "per_scena": media(per["scena"]),
              "per_orario": media(per["orario"]), "pesi_temi": pesi.get("temi", {}), "migliori": migliori,
              "nota": ("" if len(righe) >= MIN_POST else f"Servono almeno {MIN_POST} reel per ottimizzare: per ora pesi invariati.")
              + (" Statistiche Instagram non disponibili (manca il permesso instagram_manage_insights): conteggi solo YouTube."
                 if ig_mancante else "")}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(report, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(json.dumps({k: report[k] for k in ("reel_analizzati", "media_views", "pesi_temi", "nota")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
