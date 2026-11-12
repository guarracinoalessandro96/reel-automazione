"""
MUSICA DEGLI SCREENSHOT (12/11/2026, Alessandro: "quando ti mando uno screen di una frase utilizza la stessa musica che
sta su quello screenshot; se su altre piattaforme non c'e' quell'audio decidi tu quale musica inserire, ma dai
priorita' e cerca prima se puoi mettere quella musica").

notte/musica_screenshot.json = {id della frase: "Titolo - Artista"}: il brano scritto sotto il nome dell'account
nello screenshot (la riga con la nota musicale). Lo riempie l'attivita' notturna frasi-da-usare-notte quando aggiunge
le frasi; lo leggono pubblica.py (Instagram: si cerca prima quel brano tra quelli di Instagram) e tiktok_prepara.py /
facebook_prepara.py (il giro su Chrome cerca prima quel brano tra i suoni di TikTok e di Meta).

  python musica_screenshot.py aggiungi MIE-xxxxxxxx "Superman (Instrumental) - Eminem"
  python musica_screenshot.py di MIE-xxxxxxxx
  python musica_screenshot.py da-file brani.txt      (righe "frase esatta<TAB>Titolo - Artista": l'id si calcola qui)
"""
import hashlib, json, os, re, sys

FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notte", "musica_screenshot.json")
NIENTE = {"", "-", "audio originale", "original audio", "audio non disponibile", "contenuti ia"}


def leggi():
    try:
        with open(FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def di(fid):
    """'Titolo - Artista' del brano dello screenshot della frase, o None."""
    v = (leggi().get(fid or "") or "").strip()
    return v if v.lower() not in NIENTE else None


def da_nome_file(nome):
    """Il brano per un video il cui nome contiene l'id della frase ('2026-11-12 1600 - MIE-1234abcd.mp4')."""
    m = re.search(r"(MIE-[0-9a-f]{8})", nome or "")
    return di(m.group(1)) if m else None


def parti(brano):
    """('Titolo', 'Artista') da 'Titolo - Artista' (l'artista puo' mancare)."""
    t, _, a = (brano or "").partition(" - ")
    return t.strip(), a.strip()


def id_frase(frase):
    """Lo stesso id di mie_citazioni.frasi ('MIE-' + md5 del testo in minuscolo)."""
    return "MIE-" + hashlib.md5(frase.strip().strip('"“”').strip().lower().encode()).hexdigest()[:8]


def aggiungi(fid, brano):
    d = leggi()
    d[fid] = " ".join((brano or "").split())
    os.makedirs(os.path.dirname(FILE), exist_ok=True)
    with open(FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) >= 4 and sys.argv[1] == "aggiungi":
        aggiungi(sys.argv[2], sys.argv[3])
        print("salvato", sys.argv[2], "->", sys.argv[3])
    elif len(sys.argv) >= 3 and sys.argv[1] == "da-file":
        for riga in open(sys.argv[2], encoding="utf-8-sig"):
            frase, _, brano = riga.rstrip("\r\n").partition("\t")
            if frase.strip() and brano.strip():
                aggiungi(id_frase(frase), brano)
                print("salvato", id_frase(frase), "->", brano.strip())
    elif len(sys.argv) >= 3 and sys.argv[1] == "di":
        print(di(sys.argv[2]) or "nessun brano")
    else:
        print(__doc__)
