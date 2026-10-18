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


VIRALI = set()      # id delle frasi [virale] (riempito da testi_citazioni)


def testi_citazioni():
    """{id: testo} delle citazioni del Google Doc (nello storico c'e' solo l'id, es. MIE-1c29fe87)."""
    try:
        import mie_citazioni
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        c = Credentials(None, refresh_token=ENV("GOOGLE_REFRESH_TOKEN"), client_id=ENV("GOOGLE_CLIENT_ID"),
                        client_secret=ENV("GOOGLE_CLIENT_SECRET"), token_uri="https://oauth2.googleapis.com/token")
        api = build("drive", "v3", credentials=c, cache_discovery=False)
        frasi = mie_citazioni.frasi(mie_citazioni.leggi(api, ENV("DRIVE_FOLDER_DA_PUBBLICARE")))
        VIRALI.update(f["id"] for f in frasi if f.get("virale"))
        return {f["id"]: f["gancio"] for f in frasi}
    except Exception as e:
        print("Testi delle citazioni non letti:", e)
        return {}


def stat_facebook(post):
    """Riproduzioni dei reel Facebook (ultimi 30 giorni): {"reel": n, "riproduzioni": tot, "media": m, "ultimi": [...]}."""
    import requests
    token = ENV("META_PAGE_TOKEN")
    if not token:
        return None
    limite = (datetime.datetime.now() - datetime.timedelta(days=30)).isoformat()
    righe = []
    for h in post:
        fid = h.get("risultati", {}).get("facebook", {}).get("id")
        if not fid or not h.get("risultati", {}).get("facebook", {}).get("ok") or h.get("quando", "") < limite:
            continue
        try:
            r = requests.get(f"https://graph.facebook.com/v23.0/{fid}/video_insights",
                             params={"metric": "fb_reels_total_plays", "access_token": token}, timeout=30).json()
            v = sum(d["values"][0]["value"] for d in r.get("data", []))
        except Exception:
            continue
        righe.append({"quando": h["quando"], "riproduzioni": int(v)})
    if not righe:
        return None
    tot = sum(r["riproduzioni"] for r in righe)
    return {"reel": len(righe), "riproduzioni": tot, "media": round(tot / len(righe), 1), "ultimi": righe[-10:]}


def num(n):
    return f"{n:,}".replace(",", ".")


def riassunto_settimana(state):
    """Testo del riassunto del lunedi' (su Telegram): reel della settimana, visualizzazioni, migliori, follower."""
    da = datetime.datetime.now() - datetime.timedelta(days=7)
    post = [h for h in state.get("storico", []) if h.get("slot") and h.get("quando", "") >= da.isoformat()]
    yt = stat_youtube([h["risultati"]["youtube"]["id"] for h in post
                       if h.get("risultati", {}).get("youtube", {}).get("ok") and h["risultati"]["youtube"].get("id")])
    testi = testi_citazioni()
    righe = []
    for h in post:
        v, l = yt.get(h.get("risultati", {}).get("youtube", {}).get("id"), (0, 0))
        righe.append((v, l, testi.get(h.get("frase"), "")))
    righe.sort(reverse=True)
    formati = {}
    for h in post:
        v, _ = yt.get(h.get("risultati", {}).get("youtube", {}).get("id"), (0, 0))
        formati.setdefault((h.get("montaggio") or {}).get("formato") or "frase", []).append(v)
    fb = stat_facebook(post)
    fol = []
    try:
        fol = json.load(open(os.path.join(HERE, "docs", "follower.json"), encoding="utf-8"))
    except Exception:
        pass
    def follower(rete):
        """(totale oggi, differenza rispetto a 7 giorni fa) oppure None."""
        valori = [(f["data"], f.get(rete)) for f in fol if f.get(rete) is not None]
        if not valori:
            return None
        ora = valori[-1][1]
        prima = next((v for d, v in reversed(valori) if d <= (da.date().isoformat())), valori[0][1])
        return ora, ora - prima
    # Un dato per riga, titoli in maiuscolo (richiesta di Alessandro: messaggi "che vanno sempre daccapo")
    t = ["RIASSUNTO DELLA SETTIMANA", f"{da:%d/%m} - {datetime.date.today():%d/%m}", "",
         "YOUTUBE", f"{len(post)} reel", f"{num(sum(r[0] for r in righe))} visualizzazioni",
         f"{sum(r[1] for r in righe)} like"]
    iscritti = follower("youtube")
    if iscritti:
        t += [f"{num(iscritti[0])} iscritti", f"{iscritti[1]:+d} iscritti in una settimana"]
    t += ["", "I 3 MIGLIORI"]
    for i, (v, l, f) in enumerate(righe[:3], 1):
        t += ["", f"{i}) {f}", f"{num(v)} visualizzazioni", f"{l} like"]
    if formati:
        import statistics
        t += ["", "FORMATI (visualizzazioni a meta' classifica)"]
        for f, v in sorted(formati.items(), key=lambda x: -statistics.median(x[1])):
            t += [f"{f}: {num(int(statistics.median(v)))} ({len(v)} reel)"]
    t += ["", "FACEBOOK"]
    if fb:
        t += [f"{fb['reel']} reel", f"{num(fb['riproduzioni'])} riproduzioni"]
    fbf = follower("facebook")
    if fbf:
        t += [f"{num(fbf[0])} follower"]
    t += ["", "TIKTOK", "Pubblicazione a mano dal telefono", "I numeri li trovi nell'app TikTok"]
    return "\n".join(t)


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
    testi_citazioni()                                         # riempie VIRALI
    for h in post:
        if h["risultati"]["youtube"]["id"] not in yt:        # Short cancellato da YouTube: non conta
            continue
        v, l = yt[h["risultati"]["youtube"]["id"]]
        righe.append({"quando": h["quando"], "frase": h.get("frase"), "tema": h.get("tema"), "scena": h.get("scena"),
                      "orario": (h.get("slot") or "").split(" ")[-1][:2], "musica": genere((h.get("montaggio") or {}).get("musica")),
                      "origine": "archivio" if h.get("da_archivio") else "video nuovo",
                      "frase_virale": "frase virale" if h.get("frase") in VIRALI else "frase normale",
                      "formato": (h.get("montaggio") or {}).get("formato") or f"frase {round((h.get('montaggio') or {}).get('durata') or 8)} s", "views": v, "like": l})

    per = {"tema": {}, "scena": {}, "orario": {}, "musica": {}, "origine": {}, "frase_virale": {}, "formato": {}}
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

    # FORMATI (18/10/2026): piu' spazio ai formati che rendono di piu' (mediana delle views rispetto a quella di tutti),
    # da 6 reel in su per formato; mai sotto 0,4 (si continua a provarli) e mai sopra 2,5.
    import statistics
    per_f = {}
    for r in righe:
        nome_f = "frase" if r["formato"].startswith("frase") else r["formato"]
        per_f.setdefault(nome_f, []).append(r["views"])
    tutte = [r["views"] for r in righe]
    # frasi "vincenti" (sopra 900 views e sopra il 60% degli altri): pubblica.py le ripropone su un altro video
    if tutte:
        soglia = max(900, sorted(tutte)[int(len(tutte) * 0.6)])
        pesi["frasi_vincenti"] = sorted({r["frase"] for r in righe if r["views"] >= soglia
                                         and r.get("frase") and not str(r["frase"]).startswith("L")})
    if tutte:
        med = statistics.median(tutte) or 1
        pesi["formati"] = {f: round(min(max(statistics.median(v) / med, 0.4), 2.5), 2)
                           for f, v in per_f.items() if len(v) >= 6}
        pesi["aggiornato"] = datetime.date.today().isoformat()
        json.dump(pesi, open(PESI, "w", encoding="utf-8"), indent=1, ensure_ascii=False)

    migliori = sorted(righe, key=lambda r: (-r["views"], -r["like"]))[:5]
    testi = testi_citazioni() if migliori else {}
    migliori = [dict(m, frase=testi.get(m["frase"], m["frase"])) for m in migliori]
    tutti = [h for h in state.get("storico", []) if h.get("slot")]
    report = {"data": datetime.date.today().isoformat(), "reel_analizzati": len(righe),
              "facebook": stat_facebook(tutti),
              "media_views": round(media_tot), "like_totali": sum(r["like"] for r in righe),
              "per_tema": media(per["tema"]), "per_scena": media(per["scena"]), "per_orario": media(per["orario"]),
              "per_musica": media(per["musica"]), "per_origine": media(per["origine"]), "per_frase_virale": media(per["frase_virale"]),
              "per_formato": media(per["formato"]),
              "pesi_temi": pesi.get("temi", {}), "pesi_formati": pesi.get("formati", {}), "migliori": migliori,
              "nota": "Solo YouTube; non contati gli Shorts usciti da meno di 2 giorni."
              + ("" if len(righe) >= MIN_POST else f" Servono almeno {MIN_POST} reel per conclusioni affidabili.")}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(report, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    if datetime.date.today().weekday() == 0 or ENV("FORZA_RIASSUNTO") == "1":   # lunedi': riassunto su Telegram
        import avvisi
        testo = riassunto_settimana(state)
        print(testo)
        avvisi.manda(testo)
    print(json.dumps({k: report[k] for k in ("reel_analizzati", "media_views", "like_totali", "nota")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
