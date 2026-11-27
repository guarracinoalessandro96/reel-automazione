"""
PULIZIA (27/11/2026, Alessandro: "un'automazione che cancella tutti i video su tutte le piattaforme se non raggiungono
1000 views entro 24 ore, e cancellare anche tutti gli altri vecchi"; scelte: 24 ore, anche TikTok da Chrome).

Ogni ora su GitHub (.github/workflows/pulizia.yml): su YouTube, Facebook e Instagram cancella PER SEMPRE i reel GIA'
PUBBLICI che dopo 24 ore hanno meno di SOGLIA visualizzazioni. I programmati / privati / non ancora usciti non si
toccano mai. TikTok non si puo' cancellare dall'API: lo fa il PC da TikTok Studio (attivita' pianificata), che registra
qui con --registra-tiktok.

Da quando e' uscito un reel: Facebook da' solo la data di CREAZIONE (i reel programmati sono creati giorni prima),
YouTube e Instagram la data di pubblicazione. Per non sbagliare mai, conta il PRIMO giro in cui il reel risulta pubblico
(cancellati.json "visti"): si cancella se e' pubblico da almeno ORE_MIN ore (e la data della piattaforma ha almeno
ORE_MIN ore). I reel vecchi (data della piattaforma oltre VECCHI_GIORNI giorni) si cancellano subito, senza aspettare.

Prima di cancellare salva in cancellati.json le visualizzazioni del reel: statistiche.py e andamento.py le sommano ai
totali, cosi' le visualizzazioni del giorno restano giuste anche se i video spariscono (cancellati.somma).
Al massimo MAX_* cancellazioni per giro: YouTube ha un limite di operazioni al giorno (50 per cancellazione) che serve
anche a pubblicare, Meta blocca l'app se le richieste sono troppe (27/11: dopo ~30 di fila). Mai segreti stampati.
  python pulizia.py              (GitHub)          python pulizia.py --pc [--prova]   (PC; --prova: non cancella)
"""
import datetime, json, os, sys, time
import requests
import statistiche as S
import cancellati as C

SOGLIA = 1000
ORE_MIN = 24
VECCHI_GIORNI = 14
MAX_YT, MAX_FB, MAX_IG = 20, 15, 15
G_DEL = "https://graph.facebook.com/v25.0"     # la cancellazione dei media Instagram c'e' dalle versioni di fine 2025


def ora_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def data(s):
    """ISO di YouTube / Meta ("...Z" o "+0000") -> datetime UTC."""
    s = s.replace("Z", "+00:00")
    if len(s) > 5 and s[-5] in "+-" and s[-3] != ":":
        s = s[:-2] + ":" + s[-2:]
    return datetime.datetime.fromisoformat(s)


def da_cancellare(reg, piatt, pid, quando, views, adesso):
    """True se il reel pubblico va cancellato. Segna il primo giro in cui e' visto pubblico."""
    visti = reg.setdefault("visti", {}).setdefault(piatt, {})
    visti.setdefault(pid, adesso.isoformat(timespec="minutes"))
    if views >= SOGLIA:
        return False
    eta = (adesso - quando).total_seconds() / 3600
    if eta >= VECCHI_GIORNI * 24:
        return True
    pubblico_da = (adesso - data(visti[pid])).total_seconds() / 3600
    return eta >= ORE_MIN and pubblico_da >= ORE_MIN


def meta_lista(url, params):
    out, p = [], dict(params)
    while url:
        r = requests.get(url, params=p, timeout=60).json()
        if "error" in r:
            raise RuntimeError(r["error"].get("message", "errore")[:150])
        out += r.get("data", [])
        url, p = r.get("paging", {}).get("next"), None
    return out


def youtube(k, reg, adesso, prova):
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    yt = build("youtube", "v3", credentials=S.credenziali(k), cache_discovery=False)
    up = yt.channels().list(part="contentDetails", mine=True).execute()["items"][0]["contentDetails"][
        "relatedPlaylists"]["uploads"]
    ids, pag = [], None
    while True:
        r = yt.playlistItems().list(part="contentDetails", playlistId=up, maxResults=50, pageToken=pag).execute()
        ids += [i["contentDetails"]["videoId"] for i in r["items"]]
        pag = r.get("nextPageToken")
        if not pag:
            break
    cand = []
    for i in range(0, len(ids), 50):
        for v in yt.videos().list(part="statistics,snippet,status", id=",".join(ids[i:i + 50])).execute()["items"]:
            if v["status"]["privacyStatus"] != "public":
                continue
            views = int(v["statistics"].get("viewCount", 0))
            quando = data(v["snippet"]["publishedAt"])
            if da_cancellare(reg, "youtube", v["id"], quando, views, adesso):
                cand.append((quando, v["id"], views, v["snippet"]["title"][:80]))
    fatti = 0
    for quando, pid, views, titolo in sorted(cand)[:MAX_YT]:
        if prova:
            print("  [prova] YouTube", quando.date(), views, titolo[:40]); continue
        C.segna(reg, "youtube", pid, views, quando.isoformat(), titolo)
        try:
            yt.videos().delete(id=pid).execute()
            fatti += 1
        except HttpError as e:
            if e.resp.status == 404:
                fatti += 1; continue
            C.togli(reg, "youtube", pid)           # non cancellato: le sue visualizzazioni restano nel totale vivo
            print("YouTube, mi fermo:", e.resp.status, S.pulito(e)[:150]); break
    return fatti, len(cand)


def facebook(k, reg, adesso, prova):
    T, G = k["META_PAGE_TOKEN"], S.GRAPH
    vid = meta_lista(f"{G}/{k['FB_PAGE_ID']}/videos", {"fields": "id,created_time,views,published", "limit": 100,
                                                        "access_token": T})
    cand = []
    for v in vid:
        if v.get("published") is not True:        # programmati: mai
            continue
        views, quando = int(v.get("views", 0)), data(v["created_time"])
        if da_cancellare(reg, "facebook", v["id"], quando, views, adesso):
            cand.append((quando, v["id"], views))
    fatti = 0
    for quando, pid, views in sorted(cand)[:MAX_FB]:
        if prova:
            print("  [prova] Facebook", quando.date(), views); continue
        C.segna(reg, "facebook", pid, views, quando.isoformat())
        r = requests.delete(f"{G}/{pid}", params={"access_token": T}, timeout=60).json()
        if r.get("success"):
            fatti += 1
        else:
            C.togli(reg, "facebook", pid)
            print("Facebook, mi fermo:", S.pulito((r.get("error") or {}).get("message", r))[:150]); break
        time.sleep(1)
    return fatti, len(cand)


def instagram(k, reg, adesso, prova):
    Tdel = k.get("META_TOKEN_CANCELLA")
    if not Tdel:
        print("Instagram: manca il permesso per cancellare (META_TOKEN_CANCELLA): salto")
        return 0, 0
    T, G = k["META_PAGE_TOKEN"], S.GRAPH
    media = meta_lista(f"{G}/{k['IG_USER_ID']}/media", {"fields": "id,timestamp,insights.metric(views)",
                                                         "limit": 100, "access_token": T})
    cand = []
    for m in media:
        try:
            views = int(m["insights"]["data"][0]["values"][0]["value"])
        except Exception:
            continue                               # senza numero non si decide
        quando = data(m["timestamp"])
        if da_cancellare(reg, "instagram", m["id"], quando, views, adesso):
            cand.append((quando, m["id"], views))
    fatti = 0
    for quando, pid, views in sorted(cand)[:MAX_IG]:
        if prova:
            print("  [prova] Instagram", quando.date(), views); continue
        C.segna(reg, "instagram", pid, views, quando.isoformat())
        r = requests.delete(f"{G_DEL}/{pid}", params={"access_token": Tdel}, timeout=60).json()
        if r.get("success"):
            fatti += 1
        else:
            C.togli(reg, "instagram", pid)
            print("Instagram, mi fermo:", S.pulito((r.get("error") or {}).get("message", r))[:150]); break
        time.sleep(1)
    return fatti, len(cand)


def main():
    pc = "--pc" in sys.argv
    prova = "--prova" in sys.argv
    k = S.segreti(not pc)
    if not pc and os.environ.get("META_TOKEN_CANCELLA"):
        k["META_TOKEN_CANCELLA"] = os.environ["META_TOKEN_CANCELLA"]
    reg = C.carica()
    adesso = ora_utc()
    for nome, f in (("YouTube", youtube), ("Facebook", facebook), ("Instagram", instagram)):
        try:
            fatti, cand = f(k, reg, adesso, prova)
            print(f"{nome}: cancellati {fatti} (da cancellare {cand})")
        except Exception as e:
            print(nome, "non riuscito:", S.pulito(e)[:200])
        if not prova:
            C.salva(reg)                           # dopo ogni social: se il giro si interrompe, niente si perde
    if prova:
        print("prova: niente cancellato, niente salvato")


if __name__ == "__main__":
    main()
