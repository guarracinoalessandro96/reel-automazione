"""
Aggiunge frasi nuove in fondo al Google Doc "Le mie citazioni" (quelle che escono nei reel), in sicurezza.
Uso: python aggiungi_mie.py nuove.txt "nota della sezione"     (una frase per riga)

Tiene solo frasi da 7 a 22 parole (le corte rendono meno: dati YouTube 16/10/2026), senza eta' ("30 anni"),
senza autori/virgolette, senza doppioni (anche quasi uguali) rispetto al documento. Stampa cosa scarta e perche'.
Le credenziali le legge da ~/reel-segreti.json (solo su questo PC).
"""
import difflib, io, json, os, re, sys
import mie_citazioni
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

ETA = re.compile(r"\b\d{1,2}\s*anni\b|\banni\s*\d|\btrent|\bquarant|\bventi\s*anni|\bcinquant|\bsessant", re.I)
VIETATE = re.compile(r"uccid|suicid|\bdio\b|diavol|sangue|droga|politic", re.I)


def pulisci(r):
    tag = re.match(r"\s*(\[\w+\])\s*(.+)", r)          # etichetta facoltativa, es. [virale]
    if tag:
        return tag.group(1) + " " + pulisci(tag.group(2))
    r = r.strip().strip('"“”').strip()
    r = re.sub(r"\s+[-–—]\s*[A-Z][\w .']+$", "", r)          # niente " - Autore" in fondo
    return re.sub(r"\s+", " ", r)


def main():
    righe = [pulisci(l) for l in open(sys.argv[1], encoding="utf-8") if l.strip() and not l.startswith("#")]
    nota = sys.argv[2] if len(sys.argv) > 2 else "aggiunte"
    s = json.load(open(os.path.join(os.path.expanduser("~"), "reel-segreti.json"), encoding="utf-8"))
    c = Credentials(None, refresh_token=s["GOOGLE_REFRESH_TOKEN"], client_id=s["GOOGLE_CLIENT_ID"],
                    client_secret=s["GOOGLE_CLIENT_SECRET"], token_uri="https://oauth2.googleapis.com/token")
    api = build("drive", "v3", credentials=c, cache_discovery=False)
    testo = mie_citazioni.leggi(api, s["DRIVE_FOLDER_DA_PUBBLICARE"]) or ""
    viste = [f["gancio"].lower() for f in mie_citazioni.frasi(testo)]
    buone = []
    for r in righe:
        n = len(re.sub(r"^\[\w+\]\s*", "", r).split())
        motivo = ("meno di 7 parole" if n < 7 else "piu' di 22 parole" if n > 22 else "parla di eta'" if ETA.search(r)
                  else "parola vietata" if VIETATE.search(r) else None)
        if not motivo:
            simile = difflib.get_close_matches(re.sub(r"^\[\w+\]\s*", "", r).lower(), viste, n=1, cutoff=0.82)
            motivo = f"doppione di: {simile[0]}" if simile else None
        if motivo:
            print("SCARTATA", f"({motivo}):", r)
            continue
        buone.append(r)
        viste.append(re.sub(r"^\[\w+\]\s*", "", r).lower())
    if not buone:
        print("Niente da aggiungere.")
        return
    padre = api.files().get(fileId=s["DRIVE_FOLDER_DA_PUBBLICARE"], fields="parents").execute()["parents"][0]
    fid = api.files().list(q=f"'{padre}' in parents and name = '{mie_citazioni.DOC}' and trashed = false",
                           fields="files(id)").execute()["files"][0]["id"]
    nuovo = testo.rstrip("\n").replace("\r", "") + f"\n\n# --- {nota} ---\n" + "\n".join(buone) + "\n"
    api.files().update(fileId=fid, media_body=MediaIoBaseUpload(io.BytesIO(nuovo.encode("utf-8")),
                                                                 mimetype="text/plain")).execute()
    print(f"AGGIUNTE {len(buone)} frasi. Ora nel documento: {len(mie_citazioni.frasi(nuovo))}")


if __name__ == "__main__":
    main()
