"""Quanti video ci sono in 'Da pubblicare' su Drive? Stampa il numero (o -1 se non si riesce a controllare).
Solo libreria standard: gira in un secondo, prima di installare torch e il resto. Se la coda e' vuota,
il workflow si ferma subito (le esecuzioni ogni 20 minuti restano leggerissime)."""
import json, os, urllib.parse, urllib.request


def conta():
    env = os.environ.get
    if not (env("GOOGLE_REFRESH_TOKEN") and env("DRIVE_FOLDER_DA_PUBBLICARE")):
        return -1
    dati = urllib.parse.urlencode({"client_id": env("GOOGLE_CLIENT_ID"), "client_secret": env("GOOGLE_CLIENT_SECRET"),
                                   "refresh_token": env("GOOGLE_REFRESH_TOKEN"), "grant_type": "refresh_token"}).encode()
    token = json.load(urllib.request.urlopen("https://oauth2.googleapis.com/token", dati, timeout=20))["access_token"]
    q = f"'{env('DRIVE_FOLDER_DA_PUBBLICARE')}' in parents and trashed = false and mimeType contains 'video/'"
    url = "https://www.googleapis.com/drive/v3/files?" + urllib.parse.urlencode({"q": q, "fields": "files(id)", "pageSize": 100})
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
    return len(json.load(urllib.request.urlopen(req, timeout=20)).get("files", []))


if __name__ == "__main__":
    try:
        print(conta())
    except Exception:
        print(-1)          # nel dubbio si procede (pubblica.py fara' il controllo completo)
