"""
ANDAMENTO SOCIAL (14/11/2026, Alessandro: "una dashboard dove vedo giorno per giorno l'andamento dei 4 social, con il
confronto con il giorno prima, la settimana e il mese precedente; aggiungi anche i follower"; "va bene che sia pubblica,
solo che non voglio dipendere da Claude").
Pagina pubblica: docs/andamento/index.html (GitHub Pages), dati in docs/andamento/dati.json. Gira su GitHub
(.github/workflows/andamento.yml: ogni ora, dopo ogni reel e dopo gli altri lavori) e aggiorna dati.json.

21/11/2026 (Alessandro: follower in alto, confronto "il piu' vicino possibile al tempo reale", numeri verificati):
- GIORNATA: Meta (Instagram, Facebook) e YouTube Analytics contano i giorni con l'ora del Pacifico, cioe' dalle 9:00
  alle 9:00 italiane (provato il 21/11: la finestra delle insight di Instagram cambia valore alle 9:00). Tutti i giorni
  della pagina sono queste giornate. Prima Instagram si chiedeva da mezzanotte italiana e l'API rispondeva con la
  giornata PRIMA: ogni numero di Instagram era sul giorno dopo quello giusto (rifatto tutto lo storico con --storico).
- ISTANTANEE a ogni giro (chiave "istantanee", ultimi 9 giorni): totale visualizzazioni YouTube = somma di viewCount
  di tutti i video (playlist "uploads" + videos.list, ~30 unita' di quota; mai search.list; il viewCount del canale
  resta indietro di ore), totale Instagram = somma delle views di tutti i media, Facebook = page_media_view della
  giornata in corso. Da queste: "oggi finora" (dalle 9:00 a adesso) e "ieri alla stessa ora".
- Visualizzazioni per giorno: Facebook page_media_view (giornata in corso compresa); Instagram insight "views" (ultimi
  5 giorni rifatti a ogni giro: conta in ritardo); YouTube Analytics per i giorni fino a 3 giorni fa (prima e'
  incompleto), per gli ultimi dalle istantanee (o, se mancano, dai totali del canale del registro: provvisori);
  TikTok dal registro statistiche_inviate.json (PC: "tiktok_sera" la sera, messaggio delle 8).
- Follower: docs/follower.json (sera) + valori di adesso (Instagram e Facebook dall'API). YouTube: l'API arrotonda a 3
  cifre (1.270), quindi si usano iscritti guadagnati - persi da YouTube Analytics dall'inizio del canale: esatti fino
  a ~3 giorni fa. Facebook: page_follows (storico). TikTok: registro ("tiktok_follower" la mattina = fine del giorno
  prima, "tiktok_follower_sera" la sera = fine di quel giorno).
Non stampa mai segreti (statistiche.pulito).
  python andamento.py                 (GitHub: segreti dalle variabili)
  python andamento.py --pc            (PC: reel-segreti.json)
  python andamento.py --pc --storico  (rifa' Instagram e Facebook su tutto lo storico disponibile)
"""
import datetime, json, os, sys, time
from zoneinfo import ZoneInfo
import requests
import statistiche as S

QUI = os.path.dirname(os.path.abspath(__file__))
DATI = os.path.join(QUI, "docs", "andamento", "dati.json")
SOCIAL = ("YouTube", "Instagram", "TikTok", "Facebook")
LA = ZoneInfo("America/Los_Angeles")       # giornata di Meta e YouTube Analytics
GIORNI_ISTANTANEE = 9
BUCO_MAX = 6 * 3600                        # tra due istantanee piu' lontane di cosi' non si stima niente
YT_ANALYTICS_RITARDO = 3                   # YouTube Analytics: giorno completo dopo 3 giorni


def inizio(d):
    """Inizio della giornata d (ora del Pacifico) come timestamp."""
    return datetime.datetime(d.year, d.month, d.day, tzinfo=LA).timestamp()


def valore_a(punti, t):
    """Valore a quell'ora tra due istantanee vicine (lineare). punti = [(t, v)] ordinati. None se non si puo'."""
    prima = [p for p in punti if p[0] <= t]
    dopo = [p for p in punti if p[0] >= t]
    if prima and dopo:
        (a, va), (b, vb) = prima[-1], dopo[0]
        if b - a <= BUCO_MAX:
            return va if b == a else va + (vb - va) * (t - a) / (b - a)
    vicino = min(punti, key=lambda p: abs(p[0] - t), default=None)
    return vicino[1] if vicino and abs(vicino[0] - t) <= 1200 else None


def tra(punti, a, b):
    va, vb = valore_a(punti, a), valore_a(punti, b)
    if va is None or vb is None or vb < va - 500:     # calo grande: video tolto, non si puo' dire
        return None
    return max(0, round(vb - va))       # 21/11: il viewCount di YouTube oscilla di ~100 tra due letture vicine


def youtube(k):
    """-> (totale visualizzazioni sommando tutti i video, iscritti arrotondati dall'API)."""
    from googleapiclient.discovery import build
    yt = build("youtube", "v3", credentials=S.credenziali(k), cache_discovery=False)
    ch = yt.channels().list(part="statistics,contentDetails", mine=True).execute()["items"][0]
    up = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    ids, pag = [], None
    while True:
        r = yt.playlistItems().list(part="contentDetails", playlistId=up, maxResults=50, pageToken=pag).execute()
        ids += [i["contentDetails"]["videoId"] for i in r["items"]]
        pag = r.get("nextPageToken")
        if not pag:
            break
    tot = 0
    for i in range(0, len(ids), 50):
        for v in yt.videos().list(part="statistics", id=",".join(ids[i:i + 50])).execute()["items"]:
            tot += int(v["statistics"].get("viewCount", 0))
    return tot, int(ch["statistics"]["subscriberCount"])


def somma_media(url, campo, T):
    """Somma di un numero su tutti gli elementi di un elenco della Graph API (con le pagine)."""
    tot, p = 0, {"fields": campo, "limit": 100, "access_token": T}
    while url:
        r = requests.get(url, params=p, timeout=60).json()
        p = None
        if "error" in r:
            raise RuntimeError(r["error"].get("message", "errore")[:120])
        for m in r["data"]:
            if campo.startswith("insights"):
                tot += m["insights"]["data"][0]["values"][0]["value"]
            else:
                tot += m.get(campo, 0)
        url = r.get("paging", {}).get("next")
    return tot


def main():
    pc = "--pc" in sys.argv
    k = S.segreti(not pc)
    ora = S.adesso()
    adesso_t = ora.timestamp()
    oggiP = ora.astimezone(LA).date()           # giornata delle piattaforme in corso
    oggiR = ora.date()                          # data italiana (follower della sera)
    gg = lambda n: (oggiP - datetime.timedelta(days=n)).isoformat()
    giorno_dopo = lambda iso, n=1: (datetime.date.fromisoformat(iso) + datetime.timedelta(days=n)).isoformat()
    try:
        dati = json.load(open(DATI, encoding="utf-8"))
    except Exception:
        dati = {}
    vis = dati.setdefault("visualizzazioni", {})
    fol = dati.setdefault("follower", {})
    metti = lambda tab, g, s, v: tab.setdefault(g, {}).__setitem__(s, int(v)) if v is not None else None
    T = k.get("META_PAGE_TOKEN")
    storico = "--storico" in sys.argv
    primo = min(vis) if vis else gg(30)
    ist = {"t": int(adesso_t)}
    provvisori = {}
    adesso = {}

    # Facebook: giornate degli ultimi 30 giorni + quella in corso (finora)
    da = primo if storico else gg(30)
    while da <= oggiP.isoformat():
        a = min(giorno_dopo(da, 30), giorno_dopo(oggiP.isoformat()))
        try:
            r = requests.get(f"{S.GRAPH}/{k['FB_PAGE_ID']}/insights", timeout=30, params={
                "metric": "page_media_view,page_follows", "period": "day", "since": da, "until": a,
                "access_token": T}).json()
            for m in r["data"]:
                for v in m["values"]:
                    g = giorno_dopo(v["end_time"][:10], -1)
                    if m["name"] == "page_media_view":
                        if g == oggiP.isoformat():
                            ist["fb"], ist["fbg"] = int(v["value"]), g
                        else:
                            metti(vis, g, "Facebook", v["value"])
                    elif g < oggiP.isoformat() and "Facebook" not in fol.get(g, {}):
                        metti(fol, g, "Facebook", v["value"])      # solo i buchi: la sera c'e' follower.json
        except Exception as e:
            print("Facebook:", S.pulito(e))
        da = a
    # Instagram: giornata d = dalle 0:00 del Pacifico (si chiede da 1 ora dopo: l'API da' la giornata che finisce
    # dentro la finestra); ultimi 5 giorni sempre (conta in ritardo), poi i buchi degli ultimi 30 (--storico: tutti)
    n_max = (oggiP - datetime.date.fromisoformat(primo)).days if storico else 30
    for n in range(1, n_max + 1):
        g = gg(n)
        if n > 5 and not storico and "Instagram" in vis.get(g, {}):
            continue
        a = int(inizio(datetime.date.fromisoformat(g))) + 3600
        try:
            r = requests.get(f"{S.GRAPH}/{k['IG_USER_ID']}/insights", timeout=30, params={
                "metric": "views", "period": "day", "metric_type": "total_value", "since": a, "until": a + 86400,
                "access_token": T}).json()
            metti(vis, g, "Instagram", r["data"][0]["total_value"]["value"])
        except Exception as e:
            print("Instagram", g, S.pulito(e)[:150])
    try:
        ist["ig"] = somma_media(f"{S.GRAPH}/{k['IG_USER_ID']}/media", "insights.metric(views)", T)
    except Exception as e:
        print("Instagram media:", S.pulito(e))
    for s, chi in (("Instagram", "IG_USER_ID"), ("Facebook", "FB_PAGE_ID")):
        try:
            n = requests.get(f"{S.GRAPH}/{k[chi]}", timeout=30, params={"fields": "followers_count",
                                                                        "access_token": T}).json()["followers_count"]
            adesso[s] = {"v": int(n), "g": oggiR.isoformat()}
        except Exception as e:
            print(s, "follower:", S.pulito(e))
    # YouTube: istantanea del totale e iscritti
    yt_arrotondati = yt_esatti = None
    try:
        ist["yt"], yt_arrotondati = youtube(k)
    except Exception as e:
        print("YouTube:", S.pulito(e)[:200])

    # registro: totali del canale del messaggio delle 8 (riserva, provvisori), TikTok
    try:
        reg = json.load(open(os.path.join(QUI, "statistiche_inviate.json"), encoding="utf-8"))
    except Exception:
        reg = {}
    giorni = reg.get("giorni") or {}
    tot = S.totali_youtube({}, reg)
    for g in sorted(tot):
        dopo = giorno_dopo(g)
        if dopo in tot and tot[dopo] >= tot[g] and g >= gg(YT_ANALYTICS_RITARDO) and "YouTube" not in vis.get(g, {}):
            metti(vis, g, "YouTube", tot[dopo] - tot[g])        # 8:00 -> 8:00 del giorno dopo: vicino alla giornata
            provvisori.setdefault("YouTube", []).append(g)
    # istantanee: le ultime 9 giornate; YouTube dei giorni non ancora nel report = differenza tra due inizi di giornata
    lista = [x for x in dati.get("istantanee", []) if x.get("t", 0) >= adesso_t - GIORNI_ISTANTANEE * 86400]
    if len(ist) > 1:
        lista.append(ist)
    dati["istantanee"] = lista
    punti = {c: [(x["t"], x[c]) for x in lista if isinstance(x.get(c), int)] for c in ("yt", "ig")}
    for n in range(1, YT_ANALYTICS_RITARDO + 2):
        d = oggiP - datetime.timedelta(days=n)
        v = tra(punti["yt"], inizio(d), inizio(d + datetime.timedelta(days=1)))
        if v is not None:
            metti(vis, d.isoformat(), "YouTube", v)
            provvisori.setdefault("YouTube", [])
            if d.isoformat() not in provvisori["YouTube"]:
                provvisori["YouTube"].append(d.isoformat())
    # YouTube Analytics: visualizzazioni dei giorni completi e iscritti esatti (guadagnati - persi dall'inizio)
    try:
        from googleapiclient.discovery import build
        yta = build("youtubeAnalytics", "v2", credentials=S.credenziali(k), cache_discovery=False)
        q = lambda **kw: yta.reports().query(ids="channel==MINE", endDate=oggiP.isoformat(),
                                             metrics="views,subscribersGained,subscribersLost", **kw).execute()
        righe = q(startDate=gg(120), dimensions="day").get("rows", [])
        sempre = q(startDate="2005-01-01").get("rows", [[0, 0, 0]])[0]
        limite = gg(YT_ANALYTICS_RITARDO)
        dal = min(primo, gg(40))
        iscritti = int(sempre[1] - sempre[2])           # adesso (gli ultimi giorni possono essere ancora parziali)
        for g, v, piu, meno in sorted(righe, reverse=True):
            if g <= limite:
                if g >= dal:
                    metti(vis, g, "YouTube", v)
                if g in provvisori.get("YouTube", []):
                    provvisori["YouTube"].remove(g)
                metti(fol, g, "YouTube", iscritti)
                if "v" not in adesso.get("YouTube", {}):
                    adesso["YouTube"] = {"v": iscritti, "g": g}
                    yt_esatti = g
            iscritti -= int(piu - meno)
    except Exception as e:
        print("YouTube Analytics:", S.pulito(e)[:200])
    if yt_arrotondati is not None:
        adesso.setdefault("YouTube", {"v": yt_arrotondati, "g": oggiR.isoformat()})["arrotondato"] = yt_arrotondati

    # TikTok (solo dal PC): la sera (provvisorio), poi il messaggio delle 8 (definitivo)
    for g, n in (reg.get("tiktok_sera") or {}).items():
        if isinstance(n, int):
            metti(vis, g, "TikTok", n)
    for g, v in giorni.items():
        tt = v.get("tiktok") if isinstance(v, dict) else None
        if isinstance(tt, dict) and tt.get("data") and isinstance(tt.get("views"), int):
            metti(vis, tt["data"], "TikTok", tt["views"])
    for g, n in (reg.get("tiktok_follower_sera") or {}).items():       # sera: fine di quel giorno
        if isinstance(n, int):
            metti(fol, g, "TikTok", n)
    for g, n in (reg.get("tiktok_follower") or {}).items():            # mattina: fine del giorno prima
        if isinstance(n, int):
            metti(fol, giorno_dopo(g, -1), "TikTok", n)
    # follower veri della sera (YouTube no: quelli esatti vengono da Analytics, follower.json ha l'arrotondato)
    try:
        for r in json.load(open(os.path.join(QUI, "docs", "follower.json"), encoding="utf-8")):
            for s in ("instagram", "facebook", "tiktok", "youtube"):
                nome = {"instagram": "Instagram", "facebook": "Facebook", "tiktok": "TikTok", "youtube": "YouTube"}[s]
                if isinstance(r.get(s), int) and (s != "youtube" or nome not in fol.get(r["data"], {})):
                    metti(fol, r["data"], nome, r[s])
    except Exception as e:
        print("follower.json:", S.pulito(e))
    for g in fol:      # YouTube dopo l'ultimo giorno esatto: solo arrotondati (1.270 dopo 1.272 sembrava un calo)
        if yt_esatti and g > yt_esatti:
            fol[g].pop("YouTube", None)
    tt = [g for g in fol if "TikTok" in fol[g] and g <= oggiR.isoformat()]
    if tt:
        adesso["TikTok"] = {"v": fol[max(tt)]["TikTok"], "g": max(tt)}

    # oggi finora (dalle 0:00 del Pacifico = 9:00 italiane) e ieri alla stessa ora
    i0, i1 = inizio(oggiP), inizio(oggiP - datetime.timedelta(days=1))
    pari = i1 + (adesso_t - i0)
    finora, ieri, dalle = {}, {}, {}
    for s, c in (("YouTube", "yt"), ("Instagram", "ig")):
        finora[s] = tra(punti[c], i0, adesso_t) if isinstance(ist.get(c), int) else None
        ieri[s] = tra(punti[c], i1, pari)
        dopo = [t for t, _ in punti[c] if i0 <= t < adesso_t]
        if finora[s] is None and dopo and isinstance(ist.get(c), int):
            # manca l'istantanea delle 9:00 (primo giro, o GitHub ha saltato): da la prima istantanea della giornata
            finora[s] = tra(punti[c], dopo[0], adesso_t)
            dalle[s] = datetime.datetime.fromtimestamp(dopo[0], S.ROMA).strftime("%H:%M")
            ieri[s] = tra(punti[c], i1 + (dopo[0] - i0), pari)
    if "fb" in ist:
        finora["Facebook"] = ist["fb"]
    fbieri = [(i1, 0)] + [(x["t"], x["fb"]) for x in lista if x.get("fbg") == gg(1) and isinstance(x.get("fb"), int)]
    ieri["Facebook"] = tra(fbieri, i1, pari) if len(fbieri) > 1 else None
    dati["oggi"] = {"giorno": oggiP.isoformat(),
                    "dalle": datetime.datetime.fromtimestamp(i0, S.ROMA).strftime("%H:%M"),
                    "ora": ora.strftime("%H:%M"),
                    "finora": {s: v for s, v in finora.items() if v is not None},
                    "ieri_stessa_ora": {s: v for s, v in ieri.items() if v is not None},
                    "dalle_social": dalle}
    dati["adesso"] = adesso

    for g in [g for g in vis if g >= oggiP.isoformat()]:
        del vis[g]
    for g in [g for g in fol if g > oggiR.isoformat()]:
        del fol[g]
    dati["provvisori"] = {s: sorted(set(v)) for s, v in provvisori.items() if v}
    dati["visualizzazioni"] = dict(sorted(vis.items()))
    dati["follower"] = dict(sorted((g, v) for g, v in fol.items() if v))
    dati["aggiornato"] = ora.strftime("%Y-%m-%d %H:%M")
    os.makedirs(os.path.dirname(DATI), exist_ok=True)
    ordine = ["aggiornato", "oggi", "adesso", "provvisori", "visualizzazioni", "follower", "istantanee"]
    dati = {c: dati[c] for c in ordine if c in dati}
    with open(DATI, "w", encoding="utf-8") as f:
        json.dump(dati, f, ensure_ascii=False, separators=(",", ":"))
    ult = max(dati["visualizzazioni"]) if dati["visualizzazioni"] else "-"
    print("Andamento aggiornato:", len(dati["visualizzazioni"]), "giorni, ultimo", ult, "| oggi finora",
          dati["oggi"]["finora"], "| ieri alla stessa ora", dati["oggi"]["ieri_stessa_ora"])


if __name__ == "__main__":
    t = time.time()
    main()
    print(f"({time.time() - t:.0f} s)")
