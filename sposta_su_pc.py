"""
Archivio sul PC (25/10/2026). Drive ha 100 GB: quando l'archivio dei reel e' pieno, pubblica.py mette i video meno
utili nella cartella Drive "Archivio - verso il PC". Questo script (lo lancia ogni ora avvia_pubblicazione.py sul PC,
che resta sempre acceso) li SCARICA in CARTELLA_PC a piena qualita' e, SOLO dopo aver controllato che la copia sul PC
e' completa (stessa grandezza), li toglie da Drive. Nessun video va perso: i 4K restano sul disco del PC.
"""
import json, os
import requests
import cartelle              # 7/11/2026: dove stanno le cartelle su Drive, prima e dopo il riordino

SEGRETI = os.path.join(os.path.expanduser("~"), "reel-segreti.json")
CARTELLA_PC = os.path.join(os.path.expanduser("~"), "Archivio reel (4K)")
VERSO_PC = "Archivio - verso il PC"
API = "https://www.googleapis.com/drive/v3/files"


def token(k):
    return requests.post("https://oauth2.googleapis.com/token", timeout=30, data={
        "client_id": k["GOOGLE_CLIENT_ID"], "client_secret": k["GOOGLE_CLIENT_SECRET"],
        "refresh_token": k["GOOGLE_REFRESH_TOKEN"], "grant_type": "refresh_token"}).json()["access_token"]


def elenca_cartelle(H, q):
    """7/11/2026: una ricerca di cartelle su Drive per cartelle.trova (anche tiktok_prepara.py). Un errore di Drive
    ferma il giro: non deve sembrare "cartella non trovata"."""
    r = requests.get(API, params={"q": q, "fields": f"files({cartelle.CAMPI})", "pageSize": 100}, headers=H, timeout=30)
    r.raise_for_status()
    return r.json().get("files", [])


def sposta():
    """Restituisce (spostati, GB liberati, GB liberi sul disco del PC)."""
    k = json.load(open(SEGRETI, encoding="utf-8"))
    H = {"Authorization": "Bearer " + token(k)}
    padre = requests.get(f"{API}/{k['DRIVE_FOLDER_DA_PUBBLICARE']}", params={"fields": "parents"}, headers=H,
                         timeout=30).json()["parents"][0]
    # 7/11/2026 (riordino del Drive chiesto da Alessandro): accanto a "Video da pubblicare" o dentro
    # "Sistema (non toccare)" (cartelle.py); qui non si crea mai (se non c'e', niente da spostare)
    trovata = cartelle.trova(VERSO_PC, padre, lambda q: elenca_cartelle(H, q))
    cart = [{"id": trovata}] if trovata else []
    os.makedirs(CARTELLA_PC, exist_ok=True)
    spostati, liberati = 0, 0
    if cart:
        q = f"'{cart[0]['id']}' in parents and trashed = false"
        files = requests.get(API, params={"q": q, "fields": "files(id,name,size,appProperties)", "pageSize": 200},
                             headers=H, timeout=30).json().get("files", [])
        for f in files:
            size = int(f.get("size", 0))
            dest = os.path.join(CARTELLA_PC, f["name"])
            if os.path.exists(dest) and os.path.getsize(dest) != size:      # nome uguale ma video diverso
                dest = os.path.join(CARTELLA_PC, f"{f['id']}_{f['name']}")
            if not (os.path.exists(dest) and os.path.getsize(dest) == size):
                with requests.get(f"{API}/{f['id']}", params={"alt": "media"}, headers=H, stream=True,
                                  timeout=600) as r:
                    r.raise_for_status()
                    with open(dest + ".parziale", "wb") as out:
                        for pezzo in r.iter_content(8 * 1024 * 1024):
                            out.write(pezzo)
                os.replace(dest + ".parziale", dest)
            if os.path.getsize(dest) != size or size == 0:
                continue                                  # copia non completa: resta su Drive, si riprova dopo
            json.dump(f.get("appProperties") or {}, open(dest + ".json", "w", encoding="utf-8"))
            requests.delete(f"{API}/{f['id']}", headers=H, timeout=60).raise_for_status()   # copia sul PC verificata
            spostati += 1
            liberati += size
    import shutil
    return spostati, round(liberati / 1024 ** 3, 2), round(shutil.disk_usage(CARTELLA_PC).free / 1024 ** 3)


if __name__ == "__main__":
    print(sposta())
