"""
Riempie l'archivio con i video originali ancora nel Cestino di Drive (gli originali gia' pubblicati restano li' 30 giorni).
Per ognuno: scarica, riconosce scena / con chi / ora, copia il pezzo usato alla qualita' originale (overlay.crea_clip_archivio)
e lo carica in 'Reel Alessandro/Archivio' con i dati nelle proprieta' del file. Salta quelli gia' archiviati.
Uso (dal PC, con reel-segreti.json):  python recupera_archivio.py [--solo-elenco]
"""
import json, os, sys, tempfile
os.chdir(os.path.dirname(os.path.abspath(__file__)))
s = json.load(open(r"C:\Users\User\reel-segreti.json", encoding="utf-8"))
for k in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN", "DRIVE_FOLDER_DA_PUBBLICARE", "DRIVE_FOLDER_PRONTI"):
    os.environ[k] = s[k]
import pubblica, overlay, scena, subprocess

drive = pubblica.Drive(pubblica.google_creds())
api = drive.api
q = f"trashed = true and mimeType contains 'video/' and '{os.environ['DRIVE_FOLDER_DA_PUBBLICARE']}' in parents"
cestino = api.files().list(q=q, fields="files(id,name,size,createdTime)", pageSize=500).execute().get("files", [])
gia = {c["nome"].rsplit(".", 1)[0] for c in drive.lista_archivio()}
print(len(cestino), "originali nel cestino,", len(gia), "gia' in archivio")
if "--solo-elenco" in sys.argv:
    for f in sorted(cestino, key=lambda x: x["createdTime"]):
        print(f["name"], round(int(f.get("size", 0)) / 1e6), "MB", f["createdTime"][:10])
    sys.exit()
work = tempfile.mkdtemp()
for f in sorted(cestino, key=lambda x: x["createdTime"]):
    stem = os.path.splitext(f["name"])[0]
    if stem in gia:
        continue
    try:
        src = os.path.join(work, f["name"])
        drive.download(f["id"], src)
        sec, hdr = overlay.probe(src)
        info = subprocess.run([overlay.FFMPEG, "-hide_banner", "-i", src], capture_output=True, text=True, errors="ignore").stderr
        st, ln = overlay.segmento(sec)
        frames = overlay.extract_frames(src, ln, start=st, n=8, vf=overlay.HDR_TO_SDR if hdr else None)
        if not frames or min(frames[0].shape[:2]) < pubblica.QUALITA_MINIMA:
            print(f["name"], "saltato (illeggibile o sotto l'HD)")
            continue
        sc, conf, _ = scena.riconosci(frames, f["name"])
        comp, cc = scena.compagnia(frames)
        quando = scena.ora_registrazione(info)
        clip = overlay.crea_clip_archivio(src, os.path.join(work, stem + "_archivio.mov"))
        cid = drive.carica_archivio(clip, stem + ".mov", {
            "scena": sc, "fascia": scena.fascia_per(sc, quando), "compagnia": comp if cc >= 0.5 else None,
            "registrato": quando.isoformat(timespec="minutes") if quando else None})
        gia.add(stem)
        print(f["name"], "->", sc, scena.fascia_per(sc, quando), quando, "| archiviato", round(os.path.getsize(clip) / 1e6), "MB", flush=True)
    except Exception as e:
        print(f["name"], "ERRORE", e, flush=True)
    finally:
        for p in os.listdir(work):
            try:
                os.remove(os.path.join(work, p))
            except OSError:
                pass
print("Fatto.")
