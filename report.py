"""
Report e ottimizzazione automatica (ogni mattina, GitHub Actions).

1. Per ogni reel pubblicato negli ultimi 60 giorni legge visualizzazioni e like su YouTube.
2. Calcola la media per tema, scena, orario, musica e origine (video nuovo o archivio).
3. Aggiorna pesi.json: i temi che rendono di piu' vengono scelti piu' spesso (senza mai escluderne nessuno).
4. Salva il riassunto in docs/report.json (si vede sul sito, sotto la gara dei follower).
"""
import datetime, json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "stato.json")
PESI = os.path.join(HERE, "pesi.json")
OUT = os.path.join(HERE, "docs", "report.json")
ENV = os.environ.get
MIN_POST = 10          # sotto questo numero di reel i dati sono troppo pochi per cambiare i pesi
K = 5                  # "prudenza": con pochi reel su un tema, il suo peso resta vicino alla media


def stat_youtube(ids):
    """{id: (views, like)} letti da YouTube."""
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
            st = it["statistics"]
            res[it["id"]] = (int(st.get("viewCount", 0)), int(st.get("likeCount", 0)))
    return res


def genere(musica):
    """'phonk_13.flac' -> 'phonk' (generi creati da noi); 'taking_flight_2.m4a' -> 'Taking Flight' (Raccolta audio YouTube)."""
    if not musica:
        return "senza musica"
    nome = re.sub(r"_\d+$", "", os.path.splitext(os.path.basename(musica))[0])
    return nome if os.path.splitext(musica)[1] == ".flac" else nome.replace("_", " ").title()


def media(gruppi):
    return {k: {"reel": len(v), "media_views": round(sum(v) / len(v))} for k, v in sorted(gruppi.items())}


def main():
    state = json.load(open(STATE, encoding="utf-8"))
    limite = (datetime.datetime.now() - datetime.timedelta(days=60)).isoformat()
    post = [h for h in state.get("storico", []) if h.get("quando", "") >= limite
            and h.get("risultati", {}).get("youtube", {}).get("ok") and h["risultati"]["youtube"].get("id")]
    # gli Shorts usciti da meno di 2 giorni sono ancora nel "test" di YouTube: non si contano
    maturi = (datetime.datetime.now() - datetime.timedelta(days=2)).isoformat()
    post = [h for h in post if h["quando"] < maturi]
    yt = stat_youtube([h["risultati"]["youtube"]["id"] for h in post])
    righe = []
    for h in post:
        if h["risultati"]["youtube"]["id"] not in yt:        # Short cancellato da YouTube: non conta
            continue
        v, l = yt[h["risultati"]["youtube"]["id"]]
        righe.append({"quando": h["quando"], "frase": h.get("frase"), "tema": h.get("tema"), "scena": h.get("scena"),
                      "orario": (h.get("slot") or "").split(" ")[-1][:2], "musica": genere((h.get("montaggio") or {}).get("musica")),
                      "origine": "archivio" if h.get("da_archivio") else "video nuovo", "views": v, "like": l})

    per = {"tema": {}, "scena": {}, "orario": {}, "musica": {}, "origine": {}}
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

    migliori = sorted(righe, key=lambda r: (-r["views"], -r["like"]))[:5]
    report = {"data": datetime.date.today().isoformat(), "reel_analizzati": len(righe),
              "media_views": round(media_tot), "like_totali": sum(r["like"] for r in righe),
              "per_tema": media(per["tema"]), "per_scena": media(per["scena"]), "per_orario": media(per["orario"]),
              "per_musica": media(per["musica"]), "per_origine": media(per["origine"]),
              "pesi_temi": pesi.get("temi", {}), "migliori": migliori,
              "nota": "Solo YouTube; non contati gli Shorts usciti da meno di 2 giorni."
              + ("" if len(righe) >= MIN_POST else f" Servono almeno {MIN_POST} reel per conclusioni affidabili.")}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(report, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(json.dumps({k: report[k] for k in ("reel_analizzati", "media_views", "like_totali", "nota")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
