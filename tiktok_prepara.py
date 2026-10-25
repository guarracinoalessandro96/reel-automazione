"""
TikTok Studio (25/10/2026). Ogni sera alle 20 l'attivita' di Claude "tiktok-programma-sera" (Claude in Chrome, profilo
Alessandro) programma su TikTok, con un suono NATIVO di TikTok, i reel usciti su YouTube nelle ultime 24 ore: su
TikTok escono UN GIORNO DOPO, alla stessa ora (la macchina monta ogni reel solo ~50' prima del suo orario, quindi
alle 20 i reel di domani non esistono ancora).

pubblica.py salva per ogni orario, nella cartella Drive "TikTok - da pubblicare", la versione 1080p sotto i 10 MB
(senza musica, salvo parlato/momento) con la didascalia nella descrizione e l'orario in appProperties.

  python tiktok_prepara.py            scarica i video da programmare (gia' usciti su YouTube, orario TikTok tra almeno
                                      30') in CARTELLA_PC\\<data>
                                      e scrive elenco.json (file, orario, didascalia, voce)
  python tiktok_prepara.py segna ID   segna su Drive che il video ID e' programmato su TikTok (non si riprende piu')

I video gia' programmati da piu' di 3 giorni vanno nel cestino di Drive (lo svuota Alessandro).
"""
import datetime, json, os, sys
import requests
from sposta_su_pc import SEGRETI, API, token

CARTELLA_TIKTOK = "TikTok - da pubblicare"
CARTELLA_PC = os.path.join(os.path.expanduser("~"), "TikTok da programmare")


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


def prepara():
    H, cart = collega()
    adesso = ora_roma()
    elenco, cestino = [], []
    for f in elenca(H, cart):
        p = f.get("appProperties") or {}
        if "tiktok_slot" not in p:
            continue                                     # vecchi video del periodo Telegram
        slot = datetime.datetime.strptime(p["tiktok_slot"], "%Y-%m-%d %H:%M")
        if p.get("tiktok_fatto") == "1":
            if slot < adesso - datetime.timedelta(days=3):
                cestino.append(f["id"])
            continue
        quando = slot + datetime.timedelta(days=1)      # su TikTok un giorno dopo YouTube, alla stessa ora
        if slot > adesso or quando < adesso + datetime.timedelta(minutes=30):
            continue                                     # non ancora uscito su YouTube / ormai troppo tardi
        d = os.path.join(CARTELLA_PC, f"{quando:%Y-%m-%d}")
        os.makedirs(d, exist_ok=True)
        dest = os.path.join(d, f["name"])
        if not (os.path.exists(dest) and os.path.getsize(dest) == int(f.get("size", 0))):
            with requests.get(f"{API}/{f['id']}", params={"alt": "media"}, headers=H, stream=True, timeout=600) as r:
                r.raise_for_status()
                with open(dest, "wb") as out:
                    for pezzo in r.iter_content(4 * 1024 * 1024):
                        out.write(pezzo)
        elenco.append({"id": f["id"], "file": dest, "mb": round(os.path.getsize(dest) / 1e6, 1),
                       "orario": f"{quando:%Y-%m-%d %H:%M}", "youtube": p["tiktok_slot"], "voce": p.get("tiktok_voce") == "1",
                       "didascalia": f.get("description", "")})
    for fid in cestino:                                  # nel cestino, non cancellati per sempre
        requests.patch(f"{API}/{fid}", json={"trashed": True}, headers=H, timeout=30)
    elenco.sort(key=lambda x: x["orario"])
    os.makedirs(CARTELLA_PC, exist_ok=True)
    json.dump(elenco, open(os.path.join(CARTELLA_PC, "elenco.json"), "w", encoding="utf-8"), ensure_ascii=False,
              indent=1)
    return elenco


def segna(fid):
    H, _ = collega()
    requests.patch(f"{API}/{fid}", json={"appProperties": {"tiktok_fatto": "1"}}, headers=H,
                   timeout=30).raise_for_status()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) > 2 and sys.argv[1] == "segna":
        segna(sys.argv[2])
        print("segnato", sys.argv[2])
    else:
        for x in prepara():
            print(x["orario"], f"{x['mb']} MB", "voce" if x["voce"] else "muto", x["file"])
        print("elenco:", os.path.join(CARTELLA_PC, "elenco.json"))
