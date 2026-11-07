"""
Dove stanno le cartelle dei reel su Google Drive, prima e dopo il riordino del 7/11/2026.

7/11/2026 (Alessandro: "rinomina la cartella 'Reel Alessandro' con '0.' davanti cosi' esce per prima; dentro metti solo
quello che mi serve all'inizio: 'Da pubblicare', che diventa 'Video da pubblicare', poi 'Foto da pubblicare' e 'Frasi da
pubblicare'; tutte le altre cartelle mettile in una sola cartella generica"). Dopo il riordino:

  0. Reel Alessandro/              (prima "Reel Alessandro")
      Video da pubblicare/         (prima "Da pubblicare": stesso ID, DRIVE_FOLDER_DA_PUBBLICARE; non cambia MAI posto)
      Foto da pubblicare/          (prima "Foto della giornata")
      Frasi da pubblicare/Fatte/   (prima "Frasi da usare")
      Sistema (non toccare)/       tutto il resto: Archivio, TikTok - da pubblicare, Instagram temporanei, Foto usate,
                                   Pronti, il Documento "Le mie citazioni", ...

Il codice trova le cartelle partendo da quella che contiene "Video da pubblicare" (come prima del riordino) e deve
funzionare PRIMA, DURANTE e DOPO lo spostamento, in qualsiasi ordine si cambino codice e Drive:
  - ogni cartella si cerca col nome nuovo e con quello vecchio, accanto a "Video da pubblicare" e dentro
    "Sistema (non toccare)", con una sola ricerca;
  - se ce n'e' piu' d'una (per esempio una vuota creata per sbaglio da un codice vecchio) si usa la PIU' VECCHIA, che e'
    quella vera, e lo si scrive nel log;
  - una cartella si crea SOLO se non c'e' da nessuna parte, col nome nuovo e nel posto giusto: le tre cartelle di
    Alessandro in cima, tutte le altre dentro "Sistema (non toccare)" (in cima finche' quella non esiste);
  - "Sistema (non toccare)" e la cartella principale non le crea mai il codice.
Sul PC (Google Drive per desktop, H:) percorso_h() fa lo stesso con i percorsi.
Solo libreria standard: lo usano anche coda.py e ricevi_telegram.py, che girano prima di installare il resto.

  python cartelle.py [nome ...]      dove sono sul PC (H:) le cartelle, oppure dove andrebbero create
"""
import os

CARTELLA = "application/vnd.google-apps.folder"
DOCUMENTO = "application/vnd.google-apps.document"
CAMPI = "id,name,createdTime"                  # cosa chiedere a Drive per ogni cartella trovata

PRINCIPALE = "0. Reel Alessandro"
SISTEMA = "Sistema (non toccare)"
VIDEO, FOTO, FRASI = "Video da pubblicare", "Foto da pubblicare", "Frasi da pubblicare"
IN_CIMA = (VIDEO, FOTO, FRASI)                 # le sole cartelle che restano accanto a "Sistema (non toccare)"
VECCHI = {PRINCIPALE: ("Reel Alessandro",), VIDEO: ("Da pubblicare",), FOTO: ("Foto della giornata",),
          FRASI: ("Frasi da usare",)}          # nome nuovo -> nomi di prima del riordino
DRIVE_H = (r"H:\Il mio Drive", r"H:\My Drive")   # Google Drive per desktop sul PC di Alessandro


def nomi(nome):
    """Tutti i nomi con cui si cerca 'nome', prima il nuovo: 'Foto della giornata' -> ('Foto da pubblicare',
    'Foto della giornata'). Le cartelle che non cambiano nome restano come sono: 'Archivio' -> ('Archivio',)."""
    for nuovo, vecchi in VECCHI.items():
        if nome == nuovo or nome in vecchi:
            return (nuovo,) + tuple(vecchi)
    return (nome,)


def in_cima(nome):
    """True per le tre cartelle di Alessandro (Video, Foto, Frasi da pubblicare), con qualsiasi loro nome."""
    return nomi(nome)[0] in IN_CIMA


def _testo(s):
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def query(nome, dentro, tipo=CARTELLA):
    """La ricerca di Drive di 'nome' (con tutti i suoi nomi) dentro una delle cartelle 'dentro' (id)."""
    posti_q = " or ".join(f"{_testo(d)} in parents" for d in dentro)
    chi = " or ".join(f"name = {_testo(n)}" for n in nomi(nome))
    return f"({posti_q}) and ({chi}) and mimeType = {_testo(tipo)} and trashed = false"


def scegli(trovati, nome, avvisa=print):
    """L'id della piu' vecchia fra le cartelle trovate (None se nessuna). Una cartella creata per sbaglio (vuota) e'
    sempre piu' nuova di quella vera, anche se ha il nome nuovo o sta nel posto nuovo."""
    if not trovati:
        return None
    ordine = nomi(nome)
    trovati = sorted(trovati, key=lambda f: (f.get("createdTime") or "9999",
                                             ordine.index(f["name"]) if f.get("name") in ordine else len(ordine)))
    if len(trovati) > 1 and avvisa:
        avvisa(f"ATTENZIONE: su Drive ci sono {len(trovati)} '{ordine[0]}' (anche col nome vecchio): uso la piu' "
               f"vecchia, del {(trovati[0].get('createdTime') or '?')[:10]}; le altre vanno controllate a mano")
    return trovati[0]["id"]


def posti(principale, elenca, avvisa=print):
    """Dove si cerca: [cartella principale] e, se c'e' gia', anche "Sistema (non toccare)" dentro di lei."""
    s = scegli(elenca(query(SISTEMA, [principale])), SISTEMA, avvisa)
    return [principale, s] if s else [principale]


def trova(nome, principale, elenca, crea=None, tipo=CARTELLA, avvisa=print):
    """Id di 'nome' accanto a "Video da pubblicare" o dentro "Sistema (non toccare)", col nome nuovo o vecchio.
    principale = la cartella che contiene "Video da pubblicare" (parents[0] di DRIVE_FOLDER_DA_PUBBLICARE).
    elenca(q) -> [{"id", "name", "createdTime"}]: una ricerca su Drive con i campi CAMPI (un errore di Drive deve
    alzare un'eccezione, mai restituire [] come se la cartella non ci fosse).
    crea(nome, dentro) -> id: solo per le cartelle; None = non creare mai (si restituisce None).
    tipo = DOCUMENTO per il Documento "Le mie citazioni" (mai creato)."""
    trovato = scegli(elenca(query(nome, posti(principale, elenca, avvisa), tipo)), nome, avvisa)
    if trovato or not crea or tipo != CARTELLA:
        return trovato
    dove = posti(principale, elenca, avvisa)          # si ricontrolla subito prima di creare: mai doppioni
    trovato = scegli(elenca(query(nome, dove, tipo)), nome, avvisa)
    if trovato:
        return trovato
    return crea(nomi(nome)[0], dove[0] if in_cima(nome) or len(dove) == 1 else dove[1])


# ------------------------------------------------------------------------------------------- sul PC (disco H:)

def drive_h():
    """La cartella "Il mio Drive" sul PC (None su GitHub o con Google Drive per desktop spento).
    REEL_DRIVE_H la sostituisce (prove)."""
    for d in (os.environ.get("REEL_DRIVE_H"),) + DRIVE_H:
        if d and os.path.isdir(d):
            return d
    return None


def candidati_h(nome, base):
    """I posti in cui puo' stare 'nome', nell'ordine in cui si guardano: prima la cartella principale nuova, nel posto
    giusto (le tre di Alessandro in cima, le altre dentro "Sistema (non toccare)"), poi gli altri posti."""
    out = []
    for principale in nomi(PRINCIPALE):
        for n in nomi(nome):
            su, sis = os.path.join(base, principale, n), os.path.join(base, principale, SISTEMA, n)
            out += [su, sis] if in_cima(nome) else [sis, su]
    return out


def percorso_h(nome, *resto, base=None):
    """Percorso sul PC di una cartella o di un file di "0. Reel Alessandro" (con 'resto': di un file dentro di lei),
    prima e dopo il riordino: il primo che esiste fra quelli di candidati_h. None se non c'e' da nessuna parte."""
    base = base or drive_h()
    if not base:
        return None
    for p in candidati_h(nome, base):
        if os.path.exists(p):
            return os.path.join(p, *resto) if resto else p
    return None


def posto_nuovo_h(nome, base=None):
    """Dove va creata sul PC una cartella che non c'e' ancora (stessa regola di trova): le tre di Alessandro in cima,
    le altre dentro "Sistema (non toccare)" se c'e', se no nella cartella principale. None senza H:."""
    base = base or drive_h()
    principale = next((os.path.join(base, p) for p in nomi(PRINCIPALE) if base and os.path.isdir(os.path.join(base, p))),
                      None)
    if not principale:
        return None
    sis = os.path.join(principale, SISTEMA)
    return os.path.join(sis if not in_cima(nome) and os.path.isdir(sis) else principale, nomi(nome)[0])


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    elenco = sys.argv[1:] or [VIDEO, FOTO, FRASI, SISTEMA, "Archivio", "TikTok - da pubblicare", "Foto usate",
                              "Automazione", "Raccolta", "Frasi da foto", "Documenti", "Studio viralità",
                              "LEGGIMI - ISTRUZIONI PER CLAUDE.md", "Agente - diario.md"]
    for n in elenco:
        p = percorso_h(n)
        print(f"{n}: {p}" if p else f"{n}: non c'e' (andrebbe in {posto_nuovo_h(n) or '? (H: non trovato)'})")
