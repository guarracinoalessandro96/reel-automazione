"""
Le citazioni scelte da Alessandro: Google Doc "Le mie citazioni" nella cartella Drive "Reel Alessandro".
Una riga = una citazione. Righe che iniziano con # = note. Facoltativo: [palestra] [cibo] [lavoro] [famiglia] [amici]
all'inizio della riga per legarla a un tipo di video. Senza etichetta il tema si indovina dalle parole.
Usato da pubblica.py (sceglie la frase) e da salute.py (controlla che ne restino).
"""
import hashlib, re

DOC = "Le mie citazioni"
ETICHETTE = {"palestra": "palestra", "cibo": "dieta", "dieta": "dieta", "lavoro": "imprenditore", "famiglia": "famiglia",
             "amici": "amicizia", "amicizia": "amicizia", "casa": "famiglia", "macchina": "mentalita", "uscita": "amicizia"}
PAROLE_TEMA = [("dieta", ("mangi", "cibo", "dieta", "nutri", "pasto", "fame")),
               ("palestra", ("palestra", "allen", "muscol", "pesi", "serie", "ripetizion", "fisico")),
               ("famiglia", ("famiglia", "madre", "padre", "mamma", "papà", "genitori", "figli")),
               ("amicizia", ("amic", "fratell")),
               ("imprenditore", ("business", "azienda", "client", "soldi", "impresa", "lavoro"))]


def leggi(api, cartella_da_pubblicare):
    """Testo del documento (cerca nella cartella che contiene 'Da pubblicare'). None se non c'e'."""
    padre = api.files().get(fileId=cartella_da_pubblicare, fields="parents").execute()["parents"][0]
    q = (f"'{padre}' in parents and name = '{DOC}' and trashed = false "
         "and mimeType = 'application/vnd.google-apps.document'")
    found = api.files().list(q=q, fields="files(id)").execute().get("files", [])
    if not found:
        return None
    return api.files().export(fileId=found[0]["id"], mimeType="text/plain").execute().decode("utf-8")


def frasi(testo, temi_per_scena=None):
    """Dal testo del documento alle frasi nel formato di frasi.json (id stabile = impronta del testo)."""
    temi_per_scena = temi_per_scena or {}
    out = []
    for riga in (testo or "").replace("\r", "").split("\n"):
        r = riga.strip().lstrip("﻿").strip()
        if not r or r.startswith("#"):
            continue
        tema = None
        m = re.match(r"\[(\w+)\]\s*(.+)", r)
        if m:
            tema, r = ETICHETTE.get(m.group(1).lower()), m.group(2).strip()
        r = r.strip('"“”').strip()
        if len(r) < 8:
            continue
        if not tema:
            low = r.lower()
            tema = next((t for t, parole in PAROLE_TEMA if any(p in low for p in parole)), "mentalita")
        scene = ([s for s, temi in temi_per_scena.items() if tema in temi] if tema != "mentalita" else []) \
            or list(temi_per_scena)
        out.append({"id": "MIE-" + hashlib.md5(r.lower().encode()).hexdigest()[:8], "tema": tema, "scene": scene,
                    "gancio": r, "autore": "", "hashtag": ["#citazioni", "#motivazione", "#mentalita"]})
    return out
