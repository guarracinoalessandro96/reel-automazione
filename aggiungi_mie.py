"""
Aggiunge frasi nuove in fondo al Google Doc "Le mie citazioni" (quelle che escono nei reel), in sicurezza.
Uso: python aggiungi_mie.py nuove.txt "nota della sezione" [--suoi] [--sostituisce=MIE-xxxx,MIE-yyyy]   (una frase per riga)

Tiene solo frasi da 7 a 30 parole (le corte rendono meno: dati YouTube 16/10/2026; dal 26/10 anche lunghe, fino a 30), senza eta' ("30 anni"),
senza autori/virgolette, senza doppioni (anche quasi uguali) rispetto al documento. Stampa cosa scarta e perche'.
--suoi (7/11/2026, Alessandro: "quando vedi i miei screenshot dimenticati delle regole che ti ho dato e pubblicale lo
stesso"): per le frasi dei SUOI screenshot non controlla lunghezza, eta' e parole vietate; il controllo dei doppioni resta.
--sostituisce=MIE-xxxx,... (7/11/2026): quelle righe del Doc non contano nel controllo doppioni. Sono le versioni cambiate
(parole tolte, aggiunte o girate) di frasi dei suoi screenshot, che nello stesso giro vanno a 0 in classifica_frasi.json
perche' il testo esatto le sostituisce. Il controllo doppioni resta per tutte le altre righe e tra le frasi nuove; se un
id non e' nel Doc non scrive niente.
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


def compatta(testo):
    """6/11/2026: ogni giro raddoppiava le righe vuote del Doc (Google, all'export, ne rende 2 per ognuna scritta: in
    cima erano 32.768 e la prima frase stava alla riga 32.771) -> al massimo una riga vuota di fila. Le righe delle
    frasi non cambiano, quindi nemmeno i loro id (mie_citazioni.frasi salta le righe vuote)."""
    return re.sub(r"\n\s*\n+", "\n\n", testo.replace("\r", "")).rstrip("\n")


def main():
    suoi = "--suoi" in sys.argv[1:]
    sostituite = {i.strip() for a in sys.argv[1:] if a.startswith("--sostituisce=")
                  for i in a.split("=", 1)[1].split(",") if i.strip()}
    argomenti = [a for a in sys.argv[1:] if a != "--suoi" and not a.startswith("--sostituisce=")]
    righe = [pulisci(l) for l in open(argomenti[0], encoding="utf-8") if l.strip() and not l.startswith("#")]
    nota = argomenti[1] if len(argomenti) > 1 else "aggiunte"
    s = json.load(open(os.path.join(os.path.expanduser("~"), "reel-segreti.json"), encoding="utf-8"))
    c = Credentials(None, refresh_token=s["GOOGLE_REFRESH_TOKEN"], client_id=s["GOOGLE_CLIENT_ID"],
                    client_secret=s["GOOGLE_CLIENT_SECRET"], token_uri="https://oauth2.googleapis.com/token")
    api = build("drive", "v3", credentials=c, cache_discovery=False)
    testo = mie_citazioni.leggi(api, s["DRIVE_FOLDER_DA_PUBBLICARE"]) or ""
    tutte = mie_citazioni.frasi(testo)
    mancano = sostituite - {f["id"] for f in tutte}
    if mancano:       # --sostituisce: un id sbagliato non deve togliere niente dal controllo doppioni
        print("FERMO, non aggiungo niente: righe da sostituire che non sono nel documento:", ", ".join(sorted(mancano)))
        return
    viste = [f["gancio"].lower() for f in tutte if f["id"] not in sostituite]
    buone = []
    for r in righe:
        n = len(re.sub(r"^\[\w+\]\s*", "", r).split())
        motivo = None if suoi else (                  # --suoi: frasi dei suoi screenshot, solo il controllo doppioni
            "meno di 7 parole" if n < 7 else "piu' di 30 parole" if n > 30 else "parla di eta'" if ETA.search(r)
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
    # 7/11/2026 (riordino del Drive): il Documento si trova come in mie_citazioni.leggi, anche dentro
    # "Sistema (non toccare)"; se non c'e' non si scrive niente (prima un errore a meta')
    fid = mie_citazioni.trova_doc(api, s["DRIVE_FOLDER_DA_PUBBLICARE"])
    if not fid:
        print(f"FERMO, non aggiungo niente: documento '{mie_citazioni.DOC}' non trovato su Drive")
        return
    pulito = compatta(testo)
    nuovo = pulito + f"\n\n# --- {nota} ---\n" + "\n".join(buone) + "\n"
    api.files().update(fileId=fid, media_body=MediaIoBaseUpload(io.BytesIO(nuovo.encode("utf-8")),
                                                                 mimetype="text/plain")).execute()
    tolte = testo.replace("\r", "").count("\n") - pulito.count("\n")
    print(f"AGGIUNTE {len(buone)} frasi. Ora nel documento: {len(mie_citazioni.frasi(nuovo))}"
          + (f" (tolte {tolte} righe vuote in piu')" if tolte > 0 else ""))


if __name__ == "__main__":
    main()
