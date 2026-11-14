"""
ANDAMENTO SOCIAL (14/11/2026, Alessandro: "una dashboard dove vedo giorno per giorno l'andamento dei 4 social, con il
confronto con il giorno prima, la settimana e il mese precedente; aggiungi anche i follower"; "va bene che sia pubblica,
solo che non voglio dipendere da Claude").
Pagina pubblica: docs/andamento/index.html (GitHub Pages), dati in docs/andamento/dati.json. Questo script gira ogni
mattina su GitHub (.github/workflows/andamento.yml) e aggiorna dati.json:
- visualizzazioni del giorno: Facebook (page_media_view) e Instagram (views) dall'API di Meta; YouTube dal report di
  YouTube Analytics per i giorni di piu' di 4 giorni fa (prima e' incompleto) e, per gli ultimi, dalla differenza dei
  totali del canale salvati nel registro statistiche_inviate.json; TikTok dal registro (lo scrive il PC alle 8);
- follower a fine giornata: docs/follower.json (lavoro "Conta follower" ogni sera) e, per TikTok, il registro
  (chiave "tiktok_follower", letta dal PC la mattina = fine del giorno prima). I giorni prima del 23/09/2026 e i buchi
  restano quelli gia' in dati.json (ricostruiti il 14/11 dai dati delle piattaforme).
Non stampa mai segreti (statistiche.pulito).
  python andamento.py            (GitHub: segreti dalle variabili)
  python andamento.py --pc       (PC: reel-segreti.json)
"""
import datetime, json, os, sys
import requests
import statistiche as S

QUI = os.path.dirname(os.path.abspath(__file__))
DATI = os.path.join(QUI, "docs", "andamento", "dati.json")
SOCIAL = ("YouTube", "Instagram", "TikTok", "Facebook")


def main():
    pc = "--pc" in sys.argv
    k = S.segreti(not pc)
    oggi = S.adesso().date()
    gg = lambda n: (oggi - datetime.timedelta(days=n)).isoformat()
    prima = lambda iso: (datetime.date.fromisoformat(iso) - datetime.timedelta(days=1)).isoformat()
    try:
        dati = json.load(open(DATI, encoding="utf-8"))
    except Exception:
        dati = {}
    vis = dati.setdefault("visualizzazioni", {})
    fol = dati.setdefault("follower", {})
    metti = lambda tab, g, s, v: tab.setdefault(g, {}).__setitem__(s, int(v)) if v is not None else None
    T = k.get("META_PAGE_TOKEN")

    # Facebook: ultimi 30 giorni
    try:
        r = requests.get(f"{S.GRAPH}/{k['FB_PAGE_ID']}/insights", timeout=30, params={
            "metric": "page_media_view", "period": "day", "since": gg(30), "until": oggi.isoformat(), "access_token": T}).json()
        for v in r["data"][0]["values"]:
            metti(vis, prima(v["end_time"][:10]), "Facebook", v["value"])
    except Exception as e:
        print("Facebook:", S.pulito(e))
    # Instagram: ultimi 5 giorni sempre (conta in ritardo) e quelli che mancano negli ultimi 30
    for n in range(1, 31):
        g = gg(n)
        if n > 5 and "Instagram" in vis.get(g, {}):
            continue
        d = datetime.date.fromisoformat(g)
        ini = int(datetime.datetime(d.year, d.month, d.day, tzinfo=S.ROMA).timestamp())
        try:
            r = requests.get(f"{S.GRAPH}/{k['IG_USER_ID']}/insights", timeout=30, params={
                "metric": "views", "period": "day", "metric_type": "total_value", "since": ini, "until": ini + 86400,
                "access_token": T}).json()
            metti(vis, g, "Instagram", r["data"][0]["total_value"]["value"])
        except Exception as e:
            print("Instagram", g, S.pulito(e))
    # YouTube: report per i giorni di piu' di 4 giorni fa
    try:
        from googleapiclient.discovery import build
        yta = build("youtubeAnalytics", "v2", credentials=S.credenziali(k), cache_discovery=False)
        r = yta.reports().query(ids="channel==MINE", startDate=gg(35), endDate=gg(5), metrics="views", dimensions="day").execute()
        for g, v in r.get("rows", []):
            metti(vis, g, "YouTube", v)
    except Exception as e:
        print("YouTube Analytics:", S.pulito(e)[:200])
    # registro del messaggio delle 8: totali YouTube, TikTok
    try:
        reg = json.load(open(os.path.join(QUI, "statistiche_inviate.json"), encoding="utf-8"))
    except Exception:
        reg = {}
    giorni = reg.get("giorni") or {}
    tot = S.totali_youtube({}, reg)
    for g in sorted(tot):
        dopo = (datetime.date.fromisoformat(g) + datetime.timedelta(days=1)).isoformat()
        if dopo in tot and tot[dopo] >= tot[g] and g >= gg(5):      # il giorno g (8:00 -> 8:00 del giorno dopo)
            metti(vis, prima(dopo), "YouTube", tot[dopo] - tot[g])
    for g, v in giorni.items():
        tt = v.get("tiktok") if isinstance(v, dict) else None
        if isinstance(tt, dict) and tt.get("data") and isinstance(tt.get("views"), int):
            metti(vis, tt["data"], "TikTok", tt["views"])
    for g, n in (reg.get("tiktok_follower") or {}).items():
        if isinstance(n, int):
            metti(fol, prima(g), "TikTok", n)
    # follower veri della sera
    try:
        for r in json.load(open(os.path.join(QUI, "docs", "follower.json"), encoding="utf-8")):
            for s in ("youtube", "instagram", "facebook", "tiktok"):
                if isinstance(r.get(s), int):
                    metti(fol, r["data"], s.capitalize().replace("Youtube", "YouTube").replace("Tiktok", "TikTok"), r[s])
    except Exception as e:
        print("follower.json:", S.pulito(e))

    for tab in (vis, fol):
        for g in [g for g in tab if g >= oggi.isoformat()]:
            del tab[g]
    dati["visualizzazioni"] = dict(sorted(vis.items()))
    dati["follower"] = dict(sorted(fol.items()))
    dati["aggiornato"] = S.adesso().strftime("%Y-%m-%d %H:%M")
    os.makedirs(os.path.dirname(DATI), exist_ok=True)
    with open(DATI, "w", encoding="utf-8") as f:
        json.dump(dati, f, ensure_ascii=False, separators=(",", ":"))
    ult = max(dati["visualizzazioni"]) if dati["visualizzazioni"] else "-"
    print("Andamento aggiornato:", len(dati["visualizzazioni"]), "giorni di visualizzazioni, ultimo", ult)


if __name__ == "__main__":
    main()
