"""
Copia l'automazione (questa cartella, cioe' il repository GitHub) nella cartella Drive
"Reel Alessandro/Automazione", cosi' su Drive c'e' sempre la versione aggiornata di tutto.
Da eseguire dopo ogni modifica:  python sincronizza.py
Non copia mai i file segreti (client_secret*.json) ne' la cartella .git.
"""
import filecmp, os, shutil, sys

SRC = os.path.dirname(os.path.abspath(__file__))
# 7/11/2026 (riordino del Drive chiesto da Alessandro): "Automazione" passa in
# "0. Reel Alessandro\Sistema (non toccare)"; si usa il posto in cui c'e' davvero (prima o dopo il riordino,
# cartelle.percorso_h). Se non c'e' da nessuna parte non si ricrea: prima rinasceva da sola e si ricaricava tutto il
# repository (~450 MB) anche dopo averla tolta apposta.
try:
    import cartelle
    _AUTOMAZIONE = cartelle.percorso_h("Automazione")
except Exception:            # cartelle.py mancante: come prima
    _AUTOMAZIONE = r"H:\Il mio Drive\Reel Alessandro\Automazione"
DST = sys.argv[1] if len(sys.argv) > 1 else _AUTOMAZIONE
ESCLUDI_DIR = {".git", "_lavoro", "__pycache__"}
ESCLUDI_FILE = ("client_secret",)


def da_copiare(rel):
    parti = rel.replace("\\", "/").split("/")
    return not (set(parti) & ESCLUDI_DIR) and not os.path.basename(rel).startswith(ESCLUDI_FILE)


def main():
    if not DST or not os.path.isdir(os.path.dirname(DST)):
        print("Drive non trovato:", DST or "nessuna cartella 'Automazione' in 0. Reel Alessandro (o Reel Alessandro): "
              "non copio niente")
        return
    copiati = rimossi = 0
    presenti = set()
    for root, dirs, files in os.walk(SRC):
        dirs[:] = [d for d in dirs if d not in ESCLUDI_DIR]
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), SRC)
            if not da_copiare(rel):
                continue
            presenti.add(os.path.normcase(rel))
            a, b = os.path.join(SRC, rel), os.path.join(DST, rel)
            if not os.path.exists(b) or not filecmp.cmp(a, b, shallow=False):
                os.makedirs(os.path.dirname(b), exist_ok=True)
                shutil.copy2(a, b)
                copiati += 1
    for root, dirs, files in os.walk(DST):            # toglie da Drive i file che non esistono piu'
        dirs[:] = [d for d in dirs if d not in ESCLUDI_DIR]
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), DST)
            if da_copiare(rel) and os.path.normcase(rel) not in presenti and f != "desktop.ini":
                os.remove(os.path.join(root, f))
                rimossi += 1
    print(f"Drive aggiornato: {copiati} file copiati, {rimossi} file vecchi rimossi.")


if __name__ == "__main__":
    main()
