"""
TikTok Studio (25/10/2026, rivisto il 27/10/2026). L'attivita' di Claude "tiktok-programma-sera" (Claude in Chrome,
profilo Alessandro) programma su TikTok, con un suono NATIVO di TikTok, i reel gia' usciti su YouTube.

pubblica.py salva per ogni orario, nella cartella Drive "TikTok - da pubblicare", la versione 1080p (sotto i 10 MB,
senza musica salvo parlato/momento) con la didascalia nella descrizione e l'orario YouTube in appProperties.

27/10/2026: il primo giro (26/10) e' partito tardi e la rete e' caduta dopo 1 video -> 17 video arretrati. Ora:
- ogni video in attesa prende il PROSSIMO ORARIO LIBERO (gli stessi 10 orari di YouTube), cosi' niente si perde;
- (29/10) prima i PIU' NUOVI; quelli usciti su YouTube da piu' di 2 giorni si saltano;
- l'attivita' gira piu' volte la sera (20, 21, 22, 23) e ogni giro ne fa al massimo --max (default 4);
- i file sopra i 9 MB (limite di Chrome 10 MB) vengono rimpiccioliti qui sul PC.

  python tiktok_prepara.py [--max 4]      scarica i prossimi video in CARTELLA_PC\\<data> e scrive elenco.json
  python tiktok_prepara.py segna ID "AAAA-MM-GG HH:MM"   segna su Drive che il video ID e' programmato a quell'ora

I video gia' programmati da piu' di 3 giorni vanno nel cestino di Drive (lo svuota Alessandro).
"""
import datetime, json, os, sys
import requests
from sposta_su_pc import SEGRETI, API, token

CARTELLA_TIKTOK = "TikTok - da pubblicare"
CARTELLA_PC = os.path.join(os.path.expanduser("~"), "TikTok da programmare")
from orario import ORE      # stessi orari di YouTube (29/10/2026: 10 al giorno)
MAX_MB = 9.0
VECCHIO_GIORNI = 2           # 29/10/2026: con 10 al giorno Chrome ne programma 2-8 a sera: si pubblicano i piu' nuovi
ANTICIPO_MIN = 40            # TikTok vuole almeno 15' di anticipo: si tiene margine per il caricamento


def ora_roma():
    from zoneinfo import ZoneInfo
    return datetime.datetime.now(ZoneInfo("Europe/Rome")).replace(tzinfo=None)


def collega():
    k = json.load(open(SEGRETI, encoding="utf-8"))
    H = {"Authorization": "Bearer " + token(k)}
    padre = requests.get(f"{API}/{k['DRIVE_FOLDER_DA_PUBBLICARE']}", params={"fields": "parents"}, headers=H,
                         timeout=30).json()["parents"][0]
    q = (f"'{padre}' in parents and name = '{CARTELLA_TIKTOK}' and trashed = false "
         "and mimeType = 'application/vnd.google-apps.folder'")
    cart = requests.get(API, params={"q": q, "fields": "files(id)"}, headers=H, timeout=30).json()["files"][0]["id"]
    return H, cart


def elenca(H, cart):
    files, pagina = [], None
    while True:
        r = requests.get(API, headers=H, timeout=60, params={
            "q": f"'{cart}' in parents and trashed = false and mimeType = 'video/mp4'", "pageSize": 200,
            "fields": "nextPageToken,files(id,name,size,description,appProperties)", "pageToken": pagina}).json()
        files += r.get("files", [])
        pagina = r.get("nextPageToken")
        if not pagina:
            return files


def orari_liberi(occupati, adesso):
    """Orari della giornata (orario.ORE) a partire da adesso + ANTICIPO_MIN, saltando quelli gia' usati."""
    t = (adesso + datetime.timedelta(minutes=ANTICIPO_MIN)).replace(minute=0, second=0, microsecond=0)
    t += datetime.timedelta(hours=1)
    while True:
        if t.hour in ORE and t not in occupati:
            yield t
        t += datetime.timedelta(hours=1)


def rimpicciolisci(path):
    """Se il file supera MAX_MB lo ricodifica sotto gli 8 MB (stessa risoluzione)."""
    if os.path.getsize(path) <= MAX_MB * 1e6:
        return
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import overlay
    tmp = path + ".piccolo.mp4"
    overlay.versione_tiktok(path, tmp, audio=True, max_mb=7.5)
    os.replace(tmp, path)


def prepara(massimo=4):
    H, cart = collega()
    adesso = ora_roma()
    attesa, occupati, cestino = [], set(), []
    for f in elenca(H, cart):
        p = f.get("appProperties") or {}
        if "tiktok_slot" not in p:
            continue                                     # vecchi video del periodo Telegram
        slot = datetime.datetime.strptime(p["tiktok_slot"], "%Y-%m-%d %H:%M")
        if p.get("tiktok_fatto") == "1":
            if p.get("tiktok_quando"):
                occupati.add(datetime.datetime.strptime(p["tiktok_quando"], "%Y-%m-%d %H:%M"))
            if slot < adesso - datetime.timedelta(days=3):
                cestino.append(f["id"])
            continue
        if slot > adesso:
            continue                                     # non ancora uscito su YouTube
        if slot < adesso - datetime.timedelta(days=VECCHIO_GIORNI):
            continue                                     # 29/10/2026: troppo vecchio, si salta (resta su Drive)
        attesa.append((0, slot, f, p))
    attesa.sort(key=lambda x: x[1], reverse=True)       # 29/10/2026: prima i PIU' NUOVI (formato attuale da 10 s)
    liberi = orari_liberi(occupati, adesso)
    elenco = []
    for _, slot, f, p in attesa[:massimo]:
        quando = next(liberi)
        d = os.path.join(CARTELLA_PC, f"{quando:%Y-%m-%d}")
        os.makedirs(d, exist_ok=True)
        dest = os.path.join(d, f["name"])
        if not os.path.exists(dest):
            with requests.get(f"{API}/{f['id']}", params={"alt": "media"}, headers=H, stream=True, timeout=600) as r:
                r.raise_for_status()
                with open(dest, "wb") as out:
                    for pezzo in r.iter_content(4 * 1024 * 1024):
                        out.write(pezzo)
        rimpicciolisci(dest)
        elenco.append({"id": f["id"], "file": dest, "mb": round(os.path.getsize(dest) / 1e6, 1),
                       "orario": f"{quando:%Y-%m-%d %H:%M}", "youtube": p["tiktok_slot"],
                       "voce": p.get("tiktok_voce") == "1", "didascalia": f.get("description", "")})
    for fid in cestino:                                  # nel cestino, non cancellati per sempre
        requests.patch(f"{API}/{fid}", json={"trashed": True}, headers=H, timeout=30)
    os.makedirs(CARTELLA_PC, exist_ok=True)
    json.dump(elenco, open(os.path.join(CARTELLA_PC, "elenco.json"), "w", encoding="utf-8"), ensure_ascii=False,
              indent=1)
    return elenco, len(attesa)


def segna(fid, quando):
    H, _ = collega()
    requests.patch(f"{API}/{fid}", json={"appProperties": {"tiktok_fatto": "1", "tiktok_quando": quando}}, headers=H,
                   timeout=30).raise_for_status()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) > 2 and sys.argv[1] == "segna":
        segna(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "")
        print("segnato", sys.argv[2])
    else:
        n = int(sys.argv[sys.argv.index("--max") + 1]) if "--max" in sys.argv else 4
        elenco, in_attesa = prepara(n)
        for x in elenco:
            print(x["orario"], f"{x['mb']} MB", "voce" if x["voce"] else "muto", x["file"])
        print(f"in attesa in tutto: {in_attesa} | in questo giro: {len(elenco)}")
        print("elenco:", os.path.join(CARTELLA_PC, "elenco.json"))
