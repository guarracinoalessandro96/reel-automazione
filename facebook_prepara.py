"""
Facebook + INSTAGRAM da Meta Business Suite (29/10/2026, scelta di Alessandro): un solo reel programmato su entrambi. La Pagina "Alessandro Guarracin" non ha restrizioni
ma i reel caricati dalla macchina via API facevano 0-6 visualizzazioni: si prova a programmarli A MANO (Claude in Chrome,
Meta Business Suite) con un AUDIO di Meta scelto li', come TikTok Studio.

Usa gli stessi file della cartella Drive "TikTok - da pubblicare" (1080p, sotto i 10 MB, senza musica salvo voce, con la
didascalia nella descrizione e l'orario YouTube in appProperties) e segna su Drive fb_fatto / fb_quando.

  python facebook_prepara.py [--max 4]          scarica i prossimi video e scrive "Facebook da programmare/elenco_facebook.json"
  python facebook_prepara.py segna ID "AAAA-MM-GG HH:MM"
"""
import datetime, json, os, sys
import requests
import tiktok_prepara as tp
from orario import ORE

CARTELLA_PC = os.path.join(os.path.expanduser("~"), "Facebook da programmare")
VECCHIO_GIORNI = 2


def prepara(massimo=4):
    H, cart = tp.collega()
    adesso = tp.ora_roma()
    attesa, occupati = [], set()
    for f in tp.elenca(H, cart):
        p = f.get("appProperties") or {}
        if "tiktok_slot" not in p:
            continue
        slot = datetime.datetime.strptime(p["tiktok_slot"], "%Y-%m-%d %H:%M")
        if p.get("fb_fatto") == "1":
            if p.get("fb_quando"):
                occupati.add(datetime.datetime.strptime(p["fb_quando"], "%Y-%m-%d %H:%M"))
            continue
        if "STO-" in f["name"]:
            continue                                     # 29/10/2026: niente racconti ("storie inventate")
        if slot > adesso + datetime.timedelta(hours=1) or slot < adesso - datetime.timedelta(days=VECCHIO_GIORNI):
            continue
        attesa.append((slot, f, p))
    attesa.sort(key=lambda x: x[0], reverse=True)          # prima i piu' nuovi
    liberi = tp.orari_liberi(occupati, adesso)
    elenco = []
    for slot, f, p in attesa[:massimo]:
        quando = next(liberi)
        d = os.path.join(CARTELLA_PC, f"{quando:%Y-%m-%d}")
        os.makedirs(d, exist_ok=True)
        dest = os.path.join(d, f["name"])
        if not os.path.exists(dest):
            with requests.get(f"{tp.API}/{f['id']}", params={"alt": "media"}, headers=H, stream=True, timeout=600) as r:
                r.raise_for_status()
                with open(dest, "wb") as out:
                    for pezzo in r.iter_content(4 * 1024 * 1024):
                        out.write(pezzo)
        elenco.append({"id": f["id"], "file": dest, "mb": round(os.path.getsize(dest) / 1e6, 1),
                       "orario": f"{quando:%Y-%m-%d %H:%M}", "youtube": p["tiktok_slot"],
                       "voce": p.get("tiktok_voce") == "1", "didascalia": f.get("description", "")})
    os.makedirs(CARTELLA_PC, exist_ok=True)
    json.dump(elenco, open(os.path.join(CARTELLA_PC, "elenco_facebook.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return elenco, len(attesa)


def segna(fid, quando):
    H, _ = tp.collega()
    requests.patch(f"{tp.API}/{fid}", json={"appProperties": {"fb_fatto": "1", "fb_quando": quando}}, headers=H,
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
        print("elenco:", os.path.join(CARTELLA_PC, "elenco_facebook.json"))
