"""
FORMATI NUOVI da testare (25/10/2026, richiesta di Alessandro: "voglio che i video siano diversi tra di loro... capire
il prima possibile quale format funziona"). Tutti in 4K 60 come gli altri, con la serie "GIORNO X / 365" in alto.

- broll1 : 8 s, 8 stacchi da 1 s (b-roll veloce), la frase fissa sopra
- broll2 : 10 s, 5 stacchi da 2 s, la frase divisa in pezzi: cambia a ogni stacco
- broll3 : 12 s, 4 stacchi da 3 s, la frase divisa in pezzi: cambia a ogni stacco
- storia : ~22 s, un racconto a schermate (titolo + 3 righe di una lista, una schermata alla volta) su 2-3 clip
- dieci / dieci_due / dieci_broll (29/10/2026): 10 s, frase in due tempi, 1 / 2 / 4 inquadrature
- taglio1/2/3, intero (6/11/2026): scene da 1/2/3 s tagliate dal SUO video (piano_scene), o il video intero
- cinema / post / rallenty / loop (6/11/2026): fascia nera da film o fascia bianca da post con la frase fuori dal
  video, rallentatore, 10 s avanti-indietro che riparte senza stacco

make_sequenza() e' il motore comune: pezzi di video tagliati netti + testi che compaiono a tempo + musica.
"""
import functools, os, re, shutil, subprocess, tempfile, time
import overlay as ov

FORMATI = {
    "broll1": {"stacchi": [1.0] * 8, "testo": "fisso"},
    "broll2": {"stacchi": [2.0] * 5, "testo": "a_pezzi"},
    "broll3": {"stacchi": [3.0] * 4, "testo": "a_pezzi"},
    "storia": {"schermate": [4.0, 6.0, 6.0, 6.0]},
    # 26/10/2026 (Alessandro: "tutti video da 30 secondi editati bene ... che raccontano una storia", prova di 7 giorni,
    # "scegli tu se mettere i b-roll o senza"): un racconto di 6 righe da storie.json, una riga ogni 5 s
    "racconto": {"stacchi": [5.0] * 6},              # uno stacco a ogni riga del racconto
    "racconto_broll": {"stacchi": [3.0] * 10},       # b-roll (stacchi da 3 s; da 2 s era troppo pesante in 4K), riga ogni 5 s
    "racconto_lento": {"stacchi": [10.0] * 3},       # SENZA b-roll: solo il video del giorno, 3 inquadrature lunghe
    # 29/10/2026 (Alessandro: "passiamo a 10 secondi"; i 30 s erano visti al 35%, quelli da 8-13 s al 90-100%):
    # frase in DUE TEMPI (gancio forte nei primi 3,5 s, poi la risposta), 10 s, si riguarda volentieri da capo
    "dieci": {"stacchi": [10.0]},                    # una sola inquadratura: il video del giorno
    "dieci_due": {"stacchi": [5.0, 5.0]},            # due inquadrature (video del giorno + una clip di vita normale)
    "dieci_broll": {"stacchi": [2.5] * 4},           # quattro stacchi veloci
    # 6/11/2026 (Alessandro: "sfruttare diversi tipi di format... scene di un secondo, due, tre, cinque o il video per
    # intero di 10 o 15 secondi"): i suoi video nuovi (10-20 s, tagliati da lui) a scene di lunghezza diversa
    "taglio1": {"stacchi": [1.0] * 10},              # 10 scene da 1 s
    "taglio2": {"stacchi": [2.0] * 5},               # 5 scene da 2 s
    "taglio3": {"stacchi": [3.0, 3.5, 3.5]},         # 3 scene da ~3 s
    "intero": {"stacchi": [20.0]},                   # il suo video com'e', per intero (10-20 s: lo accorcia make_dieci)
    # 6/11/2026 (Alessandro: "studia 10 format di video diversi"): 4 formati diversi per impaginazione o ritmo.
    # cinema/post: la frase sta FUORI dal video (mai sul viso per costruzione)
    "cinema": {"stacchi": [10.0], "layout": "cinema"},   # fascia nera da film in alto con la frase gialla, video sotto
    "post": {"stacchi": [10.0], "layout": "post"},       # come un post: frase nera su bianco sopra, il video sotto
    "rallenty": {"stacchi": [2.0, 8.0], "rallenty": True},   # 2 s normali, poi il momento migliore al rallentatore
    # 6/11/2026 (revisione): 10 s come gli altri (dal 29/10 reel da 10 s; da 7 s il brano YouTube da 10,5 s veniva
    # tagliato e ripartiva di colpo a ogni giro)
    "loop": {"stacchi": [5.0, 5.0], "loop": True},       # 5 s avanti e gli stessi all'indietro: riparte senza stacco
    # 6/11/2026 (Alessandro: "lavoro dalle 9 alle 19... registro video di 10 secondi... barba, barbiere, macchina,
    # ufficio, pacchi, ascensore, borsa, quando mangio"): la sua GIORNATA, un momento diverso per scena (make_giornata)
    "giornata": {"stacchi": [round(10.0 / 6, 3)] * 6},
}
# formati della famiglia "dieci" (scritta gialla, colori, viso controllato), oltre ai nomi che iniziano con "dieci"
DIECI_NOMI = ("taglio1", "taglio2", "taglio3", "intero", "cinema", "post", "rallenty", "loop", "giornata")
# 6/11/2026: formati le cui scene si tagliano PRIMA dal video principale (piano_scene)
A_SCENE = ("dieci_due", "taglio1", "taglio2", "taglio3", "cinema", "post")
MARGINE_S = 0.2      # secondi lasciati all'inizio e alla fine di ogni video
# 6/11/2026 (revisione): tra due scene dello stesso video si salta almeno il 60% della scena (minimo 0,75 s, massimo
# 2 s). Con 0,25 s nella stessa inquadratura non sembrava uno stacco ma un video che scatta
STACCO_MIN, STACCO_QUOTA, STACCO_MAX = 0.75, 0.6, 2.0
SPOSTA_MAX = 1.0     # la prima scena (il momento piu' forte) si sposta al massimo di 1 s per far entrare le altre
DURATA_RACCONTO = 30.0
GANCIO_S = 3.5
ENTRATA_S = 0      # 3/11/2026: frase FISSA dal primo fotogramma (Alessandro non vuole che salga; prima 0.18)        # formati da 10 s: il gancio da solo per 3,5 s, poi la frase intera


def dividi_in(testo, n):
    """La frase in n pezzi di parole equilibrati (meglio se si spezza dopo la punteggiatura)."""
    parole = testo.split()
    n = max(1, min(n, len(parole)))
    pezzi, resto = [], parole
    for i in range(n, 0, -1):
        if i == 1:
            pezzi.append(" ".join(resto))
            break
        quanti = round(len(resto) / i)
        # se c'e' una virgola/punto vicino al taglio, si spezza li'
        for d in (0, 1, -1, 2, -2):
            j = quanti + d
            if 1 <= j < len(resto) and re.search(r"[,.;:!?]$", resto[j - 1]):
                quanti = j
                break
        pezzi.append(" ".join(resto[:max(1, quanti)]))
        resto = resto[max(1, quanti):]
        if not resto:
            break
    return [p for p in pezzi if p]


class VisoCoperto(Exception):
    """31/10/2026: la scritta finirebbe sul viso anche nella posizione migliore: si riprova con altre clip."""


def viso_coperto(img, sotto, W, H):
    """True se il riquadro del testo copre piu' del 40% di un viso (le caselle dei visi hanno gia' un margine)."""
    b = img.getbbox()
    if not b:
        return False
    box = (b[0] / W, b[1] / H, b[2] / W, b[3] / H)
    return any(ov._overlap(box, f) > 0.4 * max((f[2] - f[0]) * (f[3] - f[1]), 1e-6) for f in sotto)


def salto(durate):
    """6/11/2026 (revisione): secondi minimi tra due scene vicine dello stesso video: il 60% della scena, tra 0,75 e
    2 s (taglio1 0,75 s; taglio2 1,2 s; taglio3 e dieci_due 2 s)."""
    media = sum(durate) / len(durate) if durate else 1.0
    return round(max(STACCO_MIN, min(STACCO_MAX, STACCO_QUOTA * media)), 2)


def _distribuisci(da, a, durate, passo, testa=False, coda=False):
    """Inizi delle scene (in ordine di tempo) sparse con lo stesso spazio tra loro in [da, a], con almeno `passo` s
    tra una scena e l'altra; anche prima della prima (testa) e dopo l'ultima (coda) quando li' c'e' un'altra scena
    dello stesso video. None se non ci stanno."""
    if not durate:
        return []
    n = len(durate)
    libero = (a - da) - sum(durate) - passo * (n - 1 + testa + coda)
    if libero < -1e-6:
        return None
    extra = max(0.0, libero) / (n + 1)         # lo spazio che avanza, diviso in parti uguali: scene sparse
    t, inizi = da + extra + (passo if testa else 0.0), []
    for d in durate:
        inizi.append(round(t, 3))
        t += d + extra + passo
    return inizi


def _sparse(secondi, durate):
    """Ripiego: inizi sparsi su tutto il video anche se le scene si sovrappongono (mai due scene dallo stesso punto)."""
    fine = secondi - max(durate) - MARGINE_S
    if fine <= MARGINE_S:
        return [0.0] * len(durate)
    return [round(MARGINE_S + (fine - MARGINE_S) * (i + 0.5) / len(durate), 3) for i in range(len(durate))]


def durate_formato(nome, secondi):
    """Durate delle scene del formato per un video principale lungo `secondi`."""
    durate = list(FORMATI[nome]["stacchi"])
    if nome == "intero":                       # 6/11/2026: tutta la clip, tra 10 e 20 s
        durate = [round(max(10.0, min(20.0, secondi - 0.3)), 2)]
    elif FORMATI[nome].get("layout") and secondi < durate[0] + 0.5:   # video corto: due scene da 5 s
        durate = [5.0, 5.0]
    return durate


def durate_scene(nome, src, musiche=()):
    """6/11/2026: durate finali delle scene: quelle del formato con gli stacchi spostati sul colpo della musica.
    Le stesse per scene_mancanti (prima di scaricare le clip extra) e per make_dieci (il montaggio)."""
    durate = durate_formato(nome, ov.probe(src)[0])
    if len(durate) > 1 and musiche and musiche[0] and os.path.exists(musiche[0]):
        durate = tagli_a_tempo(musiche[0], durate)
    return durate


@functools.lru_cache(maxsize=32)
def _momento_forte(src, durata, firma):
    S, hdr = ov.probe(src)
    if S <= durata + 1.5:
        return MARGINE_S
    try:
        return ov.segmento_migliore(src, S, ov.HDR_TO_SDR if hdr else None, durata + 0.2)[0]
    except Exception:
        return MARGINE_S


def momento_forte(src, durata):
    """6/11/2026 (revisione): inizio del momento piu' forte del video (overlay.segmento_migliore) per una scena di
    `durata` s, calcolato UNA volta sola: scene_mancanti e piano_scene partono dallo stesso punto."""
    return _momento_forte(src, round(float(durata), 1), _firma_lato(src))


def _firma(src):
    try:
        return (os.path.getsize(src), os.path.getmtime(src))
    except OSError:
        return None


def _firma_lato(src):
    """7/11/2026 (studio della sera): la firma per i calcoli in memoria che dipendono dal lato della prova dell'apertura
    (segmento_migliore): sul lato "viso" la stessa di prima, sul lato "azione" un'altra (mai il risultato dell'altro lato)."""
    return (_firma(src), "azione") if ov.azione() else _firma(src)


# 7/11/2026 (studio della sera, modifiche 1 e 7): l'apertura di ogni reel video, sui due lati della prova (montaggio.
# apertura): altezza del viso VERO e movimento nel primo secondo (come lo studio del 6/11: fotogramma a 0 e a +1 s,
# grigi 90x160). Primo piano fermo = viso vero alto almeno ov.PRIMO_PIANO_ALTO e movimento sotto la mediana delle
# scene candidate del reel; con una scena sola sotto MOTO_FERMO. Il lato della prova e' UNO solo, ov.APERTURA (lo decide
# pubblica per ogni reel): qui si legge con ov.azione(), mai copiato in un'altra variabile che potrebbe restare indietro
APERTURA_FPS = 4            # 5 fotogrammi nel primo secondo (0; 0,25; 0,5; 0,75; 1 s)
MOTO_FERMO = 17.0            # mediana del movimento nel primo secondo dei 95 reel dello studio del 6/11 (scala 0-255)


@functools.lru_cache(maxsize=64)
def _apertura_da(src, firma, t):
    """(altezza del viso vero piu' alto, movimento 0 -> +1 s) del primo secondo da t, con UNA lettura di ffmpeg: 5
    fotogrammi 540x960 a colori nel taglio 9:16 del reel (HDR convertito solo su quei 5). None se non si legge."""
    import cv2
    import numpy as np
    hdr = ov.probe(src)[1]
    w, h = 540, 960
    vf = ",".join(x for x in (f"fps={APERTURA_FPS}", ov.HDR_TO_SDR if hdr else "",
                              f"scale={w}:{h}:force_original_aspect_ratio=increase", f"crop={w}:{h}", "format=bgr24") if x)
    # 7/11/2026 (prova sul PC): con -t 1,05 il filtro fps dava 4 fotogrammi (0-0,75 s): si legge 1,3 s e si tengono
    # i primi 5 (0; 0,25; 0,5; 0,75; 1 s)
    r = subprocess.run([ov.FFMPEG, "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-t", "1.3", "-i", src, "-vf", vf,
                        "-f", "rawvideo", "-"], capture_output=True, timeout=60)
    q = w * h * 3
    fr = [np.frombuffer(r.stdout[i * q:(i + 1) * q], dtype=np.uint8).reshape(h, w, 3).copy()
          for i in range(min(APERTURA_FPS + 1, len(r.stdout) // q))]
    if len(fr) < 2:
        return None
    veri = ov.visi_veri(fr, [ov.detect_faces([f]) for f in fr])    # di dritto: il primo piano e' un viso dritto
    alto = max([b[3] - b[1] for v in veri for b in v] or [0.0])
    g = [cv2.cvtColor(cv2.resize(f, (90, 160)), cv2.COLOR_BGR2GRAY).astype(np.float32) for f in fr]
    return round(float(alto), 3), round(float(np.abs(g[min(len(g) - 1, APERTURA_FPS)] - g[0]).mean()), 2)


APERTURA_TEMPO_MAX = 90      # secondi di letture per reel al massimo (poi niente misura: mai un reel in ritardo)
_APERTURA_TEMPO = [0.0]      # secondi gia' spesi nel montaggio in corso (si azzera in make_sequenza)
# 7/11/2026 (revisione, tempi): la scadenza del reel in corso (time.time(); None = nessuna, es. a mano). La mette
# pubblica.main per ogni reel a pubblica.SCADENZA_MINUTI dall'orario: YouTube va caricato almeno 10 minuti prima, se no
# esce in ritardo. I tetti di prima valevano ognuno per un pezzo solo; oltre la scadenza niente lavori facoltativi
# (apertura in azione, misura dell'apertura, analisi della giornata oltre il minimo)
SCADENZA = None


def secondi_rimasti():
    """Secondi che mancano alla scadenza del reel in corso; None se non c'e' una scadenza."""
    try:
        return None if SCADENZA is None else float(SCADENZA) - time.time()
    except Exception:
        return None


def scaduto():
    """True se la scadenza del reel in corso e' passata."""
    r = secondi_rimasti()
    return r is not None and r <= 0


def apertura_da(src, t):
    """_apertura_da con la memoria; qualsiasi errore, o oltre APERTURA_TEMPO_MAX secondi spesi nel montaggio, -> None
    (il reel esce lo stesso, senza la misura)."""
    if _APERTURA_TEMPO[0] > APERTURA_TEMPO_MAX:
        return None
    t0 = time.time()
    try:
        return _apertura_da(src, _firma(src), round(max(0.0, float(t)), 2))
    except Exception as e:
        print("apertura: primo secondo non misurato:", str(e)[:120])
        return None
    finally:
        _APERTURA_TEMPO[0] += time.time() - t0


def primo_piano_fermo(alto, moto, soglia):
    """Primo piano fermo: viso vero grande (ov.PRIMO_PIANO_ALTO) e movimento sotto la soglia."""
    return bool(alto >= ov.PRIMO_PIANO_ALTO and moto < soglia)


def apertura_info(misure, scelta=0):
    """montaggio.apertura del reel: misure = [(alto, moto) o None] delle scene candidate, scelta = la prima scena.
    {"lato", "viso_alto", "movimento", "primo_piano_fermo", "soglia_moto"}; None se la prima scena non e' misurata."""
    import statistics
    m = misure[scelta] if 0 <= scelta < len(misure) else None
    if not m:
        return None
    moti = [x[1] for x in misure if x]
    soglia = float(statistics.median(moti)) if len(moti) > 1 else MOTO_FERMO
    return {"lato": ov.APERTURA, "viso_alto": m[0], "movimento": m[1],
            "primo_piano_fermo": primo_piano_fermo(m[0], m[1], soglia), "soglia_moto": round(soglia, 2)}


# 6/11/2026 (100 punti, gruppo 2, punto 14; Alessandro: "se pensi che siano meglio... mettiamoli da subito"): il PRIMO
# SECONDO di ogni reel mai nero, buio, slavato o mosso. Analisi del 6/11: 3 persone su 4 scorrono via nei primi secondi
# e su Instagram, quando nei primi 3 s se ne va il 55% o piu', nessun reel ha passato le 200 views (0 su 60); il primo
# fotogramma e' anche la copertina di default. Soglie RELATIVE alla luce tipica della SUA clip: dal 5/11 lui abbassa
# l'esposizione apposta (overlay.luce_sua), una clip scura ma leggibile non e' "nera".
PRIMO_CONTROLLO = True       # False = come prima del 6/11 (nessun controllo del primo secondo, nessuno scambio di scene)
PRIMO_S, PRIMO_FPS = 1.0, 5  # il primo secondo, 5 fotogrammi (uno ogni 0,2 s)
PICCOLO = (180, 320)         # fotogrammi del controllo: piccoli, grigi, gia' nel taglio 9:16 del reel
NERO, SLAVATO = 16, 232      # luce media (0-255): sotto e' nero, sopra e' bianco/bruciato, per qualsiasi clip
BUIO_QUOTA = 0.45            # buio: meno del 45% della luce tipica della clip
PIATTO_QUOTA = 0.35          # piatto (obiettivo coperto, appannato): contrasto sotto il 35% di quello tipico
MOSSO_QUOTA = 0.30           # mosso o sfocato: nitidezza sotto il 30% di quella tipica della clip
CERCA_S = 2.5                # un inizio pulito si cerca fino a 2,5 s prima o dopo, nella stessa clip
VISO_MIN = 2                 # una scena "mostra il viso" se il viso c'e' in almeno 2 dei suoi 5 fotogrammi
PROVE_SCENE = 4              # scene provate al massimo come nuova prima scena (una lettura di 1 s ciascuna)
CONTROLLO = {}               # cosa hanno cambiato i controlli nell'ultimo montaggio (finisce in montaggio, stato.json)
_VERDETTI = {}


def _grigi(src, prima, dopo="", uscita=(), timeout=240):
    """Fotogrammi PICCOLO in grigio, nel taglio 9:16 del reel, con una sola lettura di ffmpeg e senza file.
    6/11/2026 (integrazione): uscita = opzioni dopo l'ingresso (es. -frames:v), timeout in secondi."""
    import numpy as np
    w, h = PICCOLO
    vf = ",".join(x for x in (dopo, f"scale={w}:{h}:force_original_aspect_ratio=increase", f"crop={w}:{h}",
                              "format=gray") if x)
    r = subprocess.run([ov.FFMPEG, "-v", "error", *prima, "-i", src, "-vf", vf, "-fps_mode", "passthrough",
                        *uscita, "-f", "rawvideo", "-"], capture_output=True, timeout=timeout)
    n = len(r.stdout) // (w * h)
    return [np.frombuffer(r.stdout[i * w * h:(i + 1) * w * h], dtype=np.uint8).reshape(h, w) for i in range(n)]


def _misure(g):
    """(luce media, contrasto, nitidezza) di un fotogramma grigio."""
    import cv2
    return float(g.mean()), float(g.std()), float(cv2.Laplacian(g, cv2.CV_32F).var())


CHIAVE_S, CHIAVE_MAX, CHIAVE_TEMPO = 60, 40, 60   # 6/11/2026 (integrazione): vedi _chiave


@functools.lru_cache(maxsize=16)
def _chiave(src, firma):
    """Misure dei fotogrammi chiave della clip (ffmpeg decodifica solo quelli: veloce anche in 4K), lette una volta.
    6/11/2026 (integrazione, revisione del gruppo 2): al massimo i primi CHIAVE_S secondi e CHIAVE_MAX fotogrammi
    chiave, entro CHIAVE_TEMPO secondi: in una clip d'archivio lunga fatta tutta di fotogrammi chiave ffmpeg li
    decodificava tutti (minuti). Se non riesce: None, tenuto in memoria anche lui (nessuna seconda lettura lenta)."""
    try:
        return tuple(_misure(g) for g in _grigi(src, ["-skip_frame", "nokey", "-t", str(CHIAVE_S)],
                                                uscita=["-frames:v", str(CHIAVE_MAX)], timeout=CHIAVE_TEMPO))
    except Exception as e:
        print("Fotogrammi chiave non letti (controlli della luce senza la clip tipica):", str(e)[:120])
        return None


@functools.lru_cache(maxsize=16)
def _tipico(src, firma):
    """(luce, contrasto, nitidezza) tipici della clip: la mediana sui fotogrammi chiave. None se sono meno di 3:
    allora contano solo nero e bianco."""
    import numpy as np
    m = _chiave(src, firma)
    return tuple(float(x) for x in np.median(np.array(m), axis=0)) if m and len(m) >= 3 else None


# 6/11/2026 (revisione, punto 14): una clip TUTTA nera (es. IMG_4508.MOV dell'archivio: 3,3 s di nero, il reel del 1/11
# alle 06:00) non deve finire nei reel, ne' come video dell'orario ne' come scena presa da una clip extra
PIATTO_ASSOLUTO = 6          # contrasto sotto 6 (0-255): un'immagine tutta uguale, niente da vedere


def _vuoto(m):
    """Fotogramma senza niente da vedere: nero, bianco o tutto uguale (soglie fisse: vale anche per le sue clip scure)."""
    return m[0] < NERO or m[0] > SLAVATO or m[1] < PIATTO_ASSOLUTO


def _pezzo_nero(fr):
    """True se TUTTI i fotogrammi di una scena (quelli gia' estratti per i visi, a colori) sono vuoti."""
    import cv2
    if not fr:
        return False
    return all(_vuoto(_misure(cv2.resize(cv2.cvtColor(x, cv2.COLOR_BGR2GRAY), PICCOLO, interpolation=cv2.INTER_AREA)))
               for x in fr)


@functools.lru_cache(maxsize=32)
def _clip_nera(src, firma):
    m = _chiave(src, firma)
    if m is None:                          # 6/11/2026 (integrazione): fotogrammi chiave non letti = non si sa
        return None
    if any(not _vuoto(x) for x in m):      # basta un fotogramma chiave con qualcosa da vedere: niente altre letture
        return False
    if len(m) >= 3:
        return True
    # 0-2 fotogrammi chiave, tutti vuoti: si conferma con 2 fotogrammi al secondo (al massimo i primi 20 s)
    m2 = [_misure(g) for g in _grigi(src, ["-t", "20"], "fps=2")]
    return all(_vuoto(x) for x in m2) if m2 else None


def clip_nera(src):
    """True se la clip e' nera (o bianca, o tutta uguale) dall'inizio alla fine; None se non si legge."""
    try:
        return _clip_nera(src, _firma(src))
    except Exception as e:
        print("Controllo della clip nera non riuscito:", e)
        return None


def _difetto(m, tip):
    """Cosa non va in un fotogramma: 'nero', 'slavato', 'buio', 'piatto', 'mosso', o None se e' pulito."""
    luce, contrasto, nitidezza = m
    if luce < NERO:
        return "nero"
    if luce > SLAVATO:
        return "slavato"
    if not tip:
        return "piatto" if contrasto < 6 else None
    if luce < BUIO_QUOTA * tip[0]:
        return "buio"
    if contrasto < PIATTO_QUOTA * tip[1]:
        return "piatto"
    if nitidezza < MOSSO_QUOTA * tip[2]:
        return "mosso"
    return None


def _giudica(difetti):
    """Il motivo per cui il primo secondo (i difetti dei suoi fotogrammi) va cambiato, o None se va bene: il primo
    fotogramma pulito, al massimo un fotogramma con la luce sbagliata e al massimo 2 mossi su 5 (non i primi due)."""
    if not difetti:
        return None
    luce = [d for d in difetti if d and d != "mosso"]
    mossi = sum(1 for d in difetti if d == "mosso")
    if difetti[0]:
        return difetti[0]
    if len(luce) >= 2:
        return luce[0]
    if mossi >= 3 or (len(difetti) > 1 and difetti[1] == "mosso" and mossi >= 2):
        return "mosso"
    return None


@functools.lru_cache(maxsize=64)
def _difetti_da(src, firma, da, a):
    """((tempo, difetto), ...) dei fotogrammi tra da e a secondi, PRIMO_FPS al secondo, con una lettura."""
    tip = _tipico(src, firma)
    g = _grigi(src, ["-ss", f"{da:.3f}", "-t", f"{max(0.2, a - da):.3f}"], f"fps={PRIMO_FPS}")
    return tuple((round(da + i / PRIMO_FPS, 3), _difetto(_misure(x), tip)) for i, x in enumerate(g))


def primo_secondo(src, t, durata=PRIMO_S):
    """6/11/2026 (punto 14): None se il primo secondo da t e' pulito, se no il motivo ('nero', 'buio', 'slavato',
    'piatto', 'mosso')."""
    t, durata = round(max(0.0, t), 2), round(min(durata, PRIMO_S), 2)
    chiave = (src, _firma(src), t, durata)
    if chiave not in _VERDETTI:
        _VERDETTI[chiave] = _giudica([x for _, x in _difetti_da(src, chiave[1], t, round(t + durata, 2))])
    return _VERDETTI[chiave]


def inizio_pulito(src, t0, lo, hi, durata=PRIMO_S, ammesso=None):
    """6/11/2026 (punto 14): (inizio, motivo) della prima scena. t0 se il suo primo secondo e' pulito (motivo None); se
    no il punto pulito piu' vicino tra lo e hi (al massimo CERCA_S s prima o dopo) che il formato ammette
    (ammesso(t)), con UNA lettura in piu' per tutta la ricerca; se non c'e', t0 con il motivo."""
    motivo = primo_secondo(src, t0, durata)
    if not motivo:
        return t0, None
    durata = round(min(durata, PRIMO_S), 2)
    lo, hi = max(0.0, lo, t0 - CERCA_S), min(hi, t0 + CERCA_S)
    if hi < lo:
        return t0, motivo
    firma = _firma(src)
    d = _difetti_da(src, firma, round(lo, 2), round(hi + durata, 2))
    k = max(1, int(round(durata * PRIMO_FPS)))
    buoni = [d[i][0] for i in range(len(d) - k + 1) if d[i][0] <= hi + 1e-6
             and not _giudica([x for _, x in d[i:i + k]]) and (ammesso is None or ammesso(d[i][0]))]
    if not buoni:
        return t0, motivo
    t = min(buoni, key=lambda t: (abs(t - t0), -t))       # il piu' vicino; a pari distanza piu' avanti
    _VERDETTI[(src, firma, round(t, 2), durata)] = None
    return round(t, 3), motivo


def _controlla_primo(src, t0, lo, hi, durata=PRIMO_S, ammesso=None):
    """inizio_pulito con quello che cambia segnato in CONTROLLO; qualsiasi errore -> t0, come prima del 6/11."""
    if not PRIMO_CONTROLLO:
        return t0
    try:
        t, motivo = inizio_pulito(src, t0, min(lo, hi), hi, durata, ammesso)
    except Exception as e:
        print("Controllo del primo secondo non riuscito, resta l'inizio di prima:", e)
        return t0
    for k in ("inizio_spostato", "primo_risolto"):
        CONTROLLO.pop(k, None)
    CONTROLLO["primo_controllo"] = motivo or "buono"
    if motivo and abs(t - t0) > 1e-3:
        CONTROLLO["inizio_spostato"] = round(t - t0, 2)
        print(f"Primo secondo {motivo}: la prima scena parte {t - t0:+.2f} s piu' in la' ({t0:.2f} -> {t:.2f} s)")
    elif motivo:
        CONTROLLO["primo_risolto"] = False
        print(f"Primo secondo {motivo} da {t0:.2f} s e nessun punto pulito vicino nella clip")
    return t


def _piano_principale(src, durate, passo=None):
    """6/11/2026 (revisione): (inizio della prima scena, inizi delle altre scene che entrano nel video principale).
    La prima scena e' il momento piu' forte, spostata al massimo di SPOSTA_MAX s; le altre prima e dopo, in ordine
    di tempo, con almeno `passo` s (salto) tra due scene vicine. Prima la prima scena poteva finire a 6 s dal momento
    forte pur di far entrare un'ultima scena, e tra le scene si saltavano solo 0,25 s."""
    S = ov.probe(src)[0]
    m, d0 = MARGINE_S, durate[0]
    passo = salto(durate) if passo is None else passo
    limita = lambda t: round(min(max(t, m), max(0.0, S - d0 - m)), 3)
    forte = limita(momento_forte(src, d0))

    def disponi(t0):                           # le scene dopo la prima, prima e dopo il momento forte, in ordine
        for k in range(len(durate), 1, -1):
            dentro = list(durate[1:k])
            l1, l2 = max(0.0, t0 - m), max(0.0, S - m - t0 - d0)
            ideale = len(dentro) * l1 / max(l1 + l2, 1e-6)
            for n1 in sorted(range(len(dentro) + 1), key=lambda n: abs(n - ideale)):
                a = _distribuisci(m, t0, dentro[:n1], passo, coda=True)
                b = _distribuisci(t0 + d0, S - m, dentro[n1:], passo, testa=True)
                if a is not None and b is not None:
                    return a + b
        return []
    scelta = (forte, disponi(forte))
    passi = int(round(SPOSTA_MAX / 0.25))
    for t in sorted({limita(forte + 0.25 * s) for s in range(-passi, passi + 1)}, key=lambda t: abs(t - forte)):
        if len(scelta[1]) == len(durate) - 1:
            break
        r = disponi(t)
        if len(r) > len(scelta[1]):
            scelta = (t, r)
    # 6/11/2026 (punto 14): primo secondo pulito; si sposta solo dove entrano ancora tutte le scene di prima (stesse
    # clip extra di scene_mancanti, stesso salto tra le scene)
    quante = len(scelta[1])
    t = _controlla_primo(src, scelta[0], m, max(m, S - d0 - m), min(d0, PRIMO_S),
                         ammesso=lambda t: len(disponi(t)) >= quante)
    if t != scelta[0]:
        scelta = (t, disponi(t))
    return scelta


def scene_mancanti(nome, src, musiche=()):
    """6/11/2026: quante scene del formato NON entrano nel video principale (solo per quelle si scaricano clip extra).
    Stesso conto di piano_scene: stesse durate, stesso momento forte, stesso salto tra le scene."""
    try:
        durate = durate_scene(nome, src, musiche)
        return len(durate) - 1 - len(_piano_principale(src, durate)[1])
    except Exception:
        return len(FORMATI.get(nome, {}).get("stacchi", [1]))


def piano_scene(clips, durate):
    """6/11/2026 (Alessandro: "li ritaglio io in 10-15-20 secondi e poi tu li tagli a tua volta in scene da 1, 2, 3, 5
    secondi"): le scene si tagliano PRIMA dal video principale, sparse su tutta la sua lunghezza e in ordine di tempo,
    con la prima nel momento piu' forte (segmento_migliore); le clip extra solo per le scene che non ci stanno.
    Prima i pezzi di una clip riusata finivano tutti in fondo (con 12 s le ultime scene erano fotogrammi uguali).
    Restituisce [(clip, inizio)] per ogni scena, nell'ordine del reel."""
    c0, m, passo = clips[0], MARGINE_S, salto(durate)
    t0, altri = _piano_principale(c0, durate)
    piano = [(c0, t0)] + [(c0, t) for t in altri]
    mancanti, altre = list(range(len(piano), len(durate))), list(clips[1:])
    if mancanti and altre:
        # 6/11/2026 (revisione): una clip extra gia' scaricata vale piu' di una scena attaccata a un'altra: le scene che
        # mancano vanno a giro sulle clip extra che hanno ancora posto con lo stesso salto; solo se sono piene si
        # sovrappongono
        lunghe = [ov.probe(c)[0] for c in altre]
        gruppi = {j: [] for j in range(len(altre))}
        for q, i in enumerate(mancanti):
            giro = [(q + s) % len(altre) for s in range(len(altre))]
            j = next((j for j in giro if _distribuisci(m, lunghe[j] - m, [durate[x] for x in gruppi[j] + [i]], passo)
                      is not None), giro[0])
            gruppi[j].append(i)
        inizi = {}
        for j, idx in gruppi.items():
            if idx:
                dj = [durate[i] for i in idx]
                pos = _distribuisci(m, lunghe[j] - m, dj, passo) or _sparse(lunghe[j], dj)
                inizi.update({i: (altre[j], t) for i, t in zip(idx, pos)})
        piano += [inizi[i] for i in mancanti]
    elif mancanti:     # nessuna clip extra (Drive non risponde): il video principale con salti piu' corti, poi sparse
        t0, altri = _piano_principale(c0, durate, passo=0.25)
        piano = [(c0, t0)] + [(c0, t) for t in altri]
        resto = [durate[i] for i in range(len(piano), len(durate))]
        piano += [(c0, t) for t in (_sparse(ov.probe(c0)[0], resto) if resto else [])]
    return piano


def _riquadro_video(volti_pezzo, wv, hv):
    """Taglio verticale del video nella finestra wv x hv (cinema/post): il viso nella parte alta della finestra,
    al centro se non c'e' viso. Espressione per il crop di ffmpeg."""
    fy = 0.45
    if volti_pezzo:
        fy = sum((f[1] + f[3]) / 2 for f in volti_pezzo) / len(volti_pezzo)
    return f"(iw-{wv})/2:'max(0,min(ih-{hv},{fy:.4f}*ih-{0.40 * hv:.1f}))'"


def _righe(d, testo, font, max_px):
    try:
        return ov._a_capo(d, testo, font, max_px)
    except Exception:          # se overlay cambia: a capo semplice, mai una riga piu' larga dello schermo
        righe, cur = [], ""
        for p in testo.split():
            t = (cur + " " + p).strip()
            if cur and d.textlength(t, font=font) > max_px:
                righe.append(cur)
                t = p
            cur = t
        return righe + ([cur] if cur else [])


def cornice(W, H, tipo, testo):
    """6/11/2026: impaginazione con la frase FUORI dal video, quindi mai sul viso.
    6/11/2026 (revisione): una sola fascia, in alto, con la frase; il video largo quanto lo schermo e fino in fondo.
    Instagram mostra meno nei consigliati i reel con i bordi, e in basso nome, Segui e didascalia (bianchi) devono
    cadere sul video, non sul bianco; la finestra quasi 3:4 tiene tutto il corpo (il quadrato tagliava piedi e pesi).
    cinema: fascia nera con la frase gialla centrata come il titolo di un film, una riga nera sottile in fondo;
    post: fascia bianca con la frase nera, come un post, e il video sotto con gli angoli arrotondati in alto.
    Restituisce (immagine W x H con il buco trasparente per il video, (x, y, w, h) del video, colore del fondo)."""
    from PIL import Image, ImageDraw, ImageFont
    post = tipo == "post"
    pari = lambda v: int(v) // 2 * 2
    fsize = int(W * ov.DIM_GIALLO * (0.95 if post else 1.0))
    font = ImageFont.truetype(ov.FONT_GIALLO if os.path.exists(ov.FONT_GIALLO) else ov.FONT, fsize)
    fondo = "white" if post else "black"
    img = Image.new("RGBA", (W, H), (255, 255, 255, 255) if post else (0, 0, 0, 255))
    d = ImageDraw.Draw(img)
    margine = pari(W * 0.07)
    righe = _righe(d, testo, font, (W - 2 * margine) if post else W * 0.84)
    lh = int(fsize * 1.25)
    alto = int(H * (ov.SAFE_TOP + 0.012))      # sotto il nome utente e le schede della piattaforma
    alto_testo = lh * len(righe)
    x, w = 0, W
    y = pari(max(H * 0.20, alto + alto_testo + H * 0.03))
    h = pari(H - y - (0 if post else H * 0.025))
    y_t = y - int(H * 0.022) - alto_testo      # la frase appoggiata sopra il video
    if post:
        y_t = (alto + y - int(H * 0.022) - alto_testo) // 2      # al centro della fascia bianca
        for i, r in enumerate(righe):
            d.text((margine, y_t + i * lh), r, font=font, fill=(15, 20, 25, 255))
        raggio = int(W * 0.04)                 # angoli in basso fuori dall'immagine: arrotondati solo quelli in alto
        d.rounded_rectangle([x, y, x + w - 1, H + raggio], radius=raggio, fill=(0, 0, 0, 0))
    else:
        for i, r in enumerate(righe):
            d.text(((W - d.textlength(r, font=font)) / 2, y_t + i * lh), r, font=font, fill=ov.GIALLO)
        d.rectangle([x, y, x + w - 1, y + h - 1], fill=(0, 0, 0, 0))
    return img, (x, y, w, h), fondo


def make_sequenza(clips, durate, testi, dst, musiche=(), serie=None, nome="sequenza", controlla_viso=False,
                  piano=None, velocita=None, indietro=None, layout=None):
    """clips: video sorgente (si riusano a giro, ogni pezzo da un punto diverso); durate: secondi di ogni pezzo;
    testi: [(da_s, a_s, testo)] da mostrare a tempo. Restituisce info.
    6/11/2026: piano = [(clip, inizio)] deciso prima (piano_scene); velocita = per pezzo (0,5 = rallentatore);
    indietro = per pezzo (True = al contrario, loop); layout = (cornice, (x, y, w, h), colore) per cinema/post."""
    W, H = ov.LATO_USCITA, int(ov.LATO_USCITA * 16 / 9)
    DUR = round(sum(durate), 3)
    _APERTURA_TEMPO[0] = 0.0     # 7/11/2026: il tempo delle misure dell'apertura conta per ogni montaggio
    tmp = tempfile.mkdtemp()
    n = len(durate)
    cmd, catena, volti, mappe = [ov.FFMPEG, "-y", "-v", "error"], [], [], []
    dieci = nome.startswith("dieci") or nome in DIECI_NOMI
    # 6/11/2026 (revisione): le foto no. Il gancio lo sceglie gia' foto_giornata.ordina (viso con pelle e occhi,
    # nitidezza, luce) e su una foto ferma il controllo del primo secondo non migliora niente (Haar vede "visi" nei dischi)
    # 6/11/2026 (integrazione): neanche 'giornata', che ha la sua prima scena (il viso per tutto il primo secondo,
    # piano_giornata), la memoria delle clip usate e mai la stessa clip due volte: _senza_nere e _primo_pezzo
    # rimescolavano le sue scene e prendevano altri punti delle stesse clip (foto_rapide non passa di qui: make_rapide)
    controlli = dieci and nome not in ("dieci_foto", "foto_rapide", "giornata") and PRIMO_CONTROLLO
    wv, hv = (layout[1][2], layout[1][3]) if layout else (W, H)
    pezzi = []         # 6/11/2026: prima si guardano tutti i pezzi (viso, primo secondo), poi si monta
    for i, seg in enumerate(durate):
        v = float(velocita[i]) if velocita else 1.0
        sorgente = seg * v                         # secondi di video sorgente usati dal pezzo
        if piano:
            c, inizio = piano[i]
            secondi, hdr = ov.probe(c)
        else:
            c = clips[i % len(clips)]
            secondi, hdr = ov.probe(c)
            giro = i // len(clips)                 # stessa clip riusata: punto diverso
            # 6/11/2026: i giri si spargono su tutta la clip (prima 0,5 + giro * (seg + 0,5) finiva in fondo: uguali)
            usi = (n - 1 - i % len(clips)) // len(clips) + 1
            riserva = max(0.0, min(0.5 + giro * max(0.0, secondi - seg - 0.7) / max(1, usi - 1), secondi - seg - 0.2))
            inizio = ov.inizio_bello(c, secondi, hdr, seg + 0.2, riserva) if giro == 0 else riserva
            if i == 0 and dieci and secondi > seg + 1.5:    # 1/11/2026: si parte sempre dal punto piu' forte
                try:
                    inizio = ov.segmento_migliore(c, secondi, ov.HDR_TO_SDR if hdr else None, seg + 0.2)[0]
                except Exception:
                    pass
            if i == 0 and controlli:               # 6/11/2026 (punto 14): primo secondo pulito (dieci, dieci_broll)
                inizio = _controlla_primo(c, inizio, 0.0, max(0.0, secondi - sorgente - 0.2), min(seg, PRIMO_S))
        p = {"c": c, "inizio": inizio, "secondi": secondi, "hdr": hdr}
        pezzi.append(_guarda(p, sorgente, W, H, 5 if controlla_viso else 3, dieci, controlli))
    if controlli and not velocita and not indietro and any(p["nero"] for p in pezzi):
        try:           # 6/11/2026 (revisione, punto 14): nessuna scena tutta nera nel reel
            pezzi = _senza_nere(pezzi, durate, W, H, 5 if controlla_viso else 3, dieci)
        except Exception as e:
            print("Scene nere non sostituite, restano come prima:", e)
    misure, a_scene = None, n > 1 and not velocita and not indietro    # rallenty e loop: lo stesso momento, una scena
    if controlli and a_scene:
        fatto = None
        if ov.azione() and scaduto():   # 7/11/2026 (revisione, tempi): oltre la scadenza la scelta della fase 1
            CONTROLLO["oltre_scadenza"] = True
            print("Oltre la scadenza del reel: niente apertura in azione, prima scena come la fase 1")
        elif ov.azione():  # 7/11/2026 (studio della sera, modifica 1a): lato "azione", mai il primo piano fermo per primo
            try:
                fatto = _primo_azione(pezzi, durate, clips[0])
            except Exception as e:
                print("Apertura in azione non riuscita, prima scena come prima:", e)
        if fatto:
            pezzi, misure = fatto
        else:
            try:           # 6/11/2026 (punti 13 e 14): per prima una scena col viso e il primo secondo pulito
                pezzi = _primo_pezzo(pezzi, durate)
            except Exception as e:
                print("Scelta della prima scena non riuscita, ordine di prima:", e)
        try:               # 7/11/2026 (revisione, regola 2): le scene spostate si riguardano (visi del tratto nuovo)
            pezzi = _riguarda(pezzi, durate, W, H, 5 if controlla_viso else 3, dieci)
        except Exception as e:
            print("Scene spostate non riguardate (restano i visi di prima):", e)
    for i, seg in enumerate(durate):
        v = float(velocita[i]) if velocita else 1.0
        sorgente = seg * v
        c, inizio, secondi, hdr = (pezzi[i][k] for k in ("c", "inizio", "secondi", "hdr"))
        cmd += ["-display_rotation", "0", "-ss", f"{inizio:.2f}", "-t", f"{sorgente + 0.2:.2f}", "-i", c]
        volti.append(pezzi[i]["volti"])
        mappe.append(pezzi[i]["mappa"])
        schiarisci = pezzi[i]["schiarisci"]
        # 6/11/2026 (Alessandro: "saro' io a decidere la luminosita' dei video"): sui video girati da lui dal 5/11
        # niente schiarita e niente LOOK, la luce resta quella che ha scelto col telefono
        sua = dieci and ov.luce_sua(c)
        f = [x for x in (ov.raddrizza(ov.rotazione(c)), ov.HDR_TO_SDR if hdr else "") if x]
        if layout:     # cinema/post: il video nella sua finestra, tagliato tenendo il viso dentro
            f += [f"scale={wv}:{hv}:force_original_aspect_ratio=increase",
                  f"crop={wv}:{hv}:{_riquadro_video(volti[-1], wv, hv)}", "setsar=1"]
        else:
            f += [f"scale={W}:{H}:force_original_aspect_ratio=increase", f"crop={W}:{H}", "setsar=1"]
        f += [schiarisci, ov.LOOK] if dieci and not sua and schiarisci else [ov.LOOK] if dieci and not sua else []
        if v != 1.0:   # rallentatore: i fotogrammi si allungano, poi fps li porta a 60 (niente filtri pesanti)
            f += [f"setpts=(PTS-STARTPTS)/{v:.3f}"]
        f += [f"fps={ov.FPS_MULTI}", "format=yuv420p", "settb=AVTB", f"fps={ov.FPS_MULTI}",
              "tpad=stop_mode=clone:stop_duration=1", f"trim=0:{seg:.3f}", "setpts=PTS-STARTPTS"]
        if indietro and indietro[i]:               # loop: lo stesso pezzo al contrario (ingresso a parte, niente split)
            f += ["reverse", "setpts=PTS-STARTPTS"]
        catena.append(f"[{i}:v]{','.join(f)}[c{i}]")
    g = ";".join(catena) + ";" + "".join(f"[c{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[bg]"
    corrente, idx = "bg", n
    if layout:         # la finestra del video sul fondo, poi la cornice con la frase sopra
        img, (x, y, _, _), colore = layout
        p = os.path.join(tmp, "cornice.png")
        img.save(p)
        cmd += ["-i", p]
        g += f";[bg]pad={W}:{H}:{x}:{y}:color={colore}[pd];[pd][{idx}:v]overlay=0:0:format=auto[cn]"
        corrente, idx = "cn", idx + 1
    tagli = [sum(durate[:i]) for i in range(n + 1)]
    for k, (a, b, t) in enumerate(testi):
        sotto = [f for i in range(n) if tagli[i] < b and tagli[i + 1] > a for f in volti[i]]   # pezzi sotto il testo
        if dieci:
            piene = [mappe[i] for i in range(n) if tagli[i] < b and tagli[i + 1] > a and mappe[i] is not None]
            img, _, _ = ov.build_testo_giallo(W, H, t, sotto, sum(piene) / len(piene) if piene else None)
        else:
            img, _, _ = ov.build_overlay(W, H, t, sotto, serie=serie)
        if controlla_viso and viso_coperto(img, sotto, W, H):
            raise VisoCoperto(t)
        p = os.path.join(tmp, f"t{k}.png")
        img.save(p)
        cmd += ["-i", p]
        y = f"'if(lt(t-{a:.2f},{ENTRATA_S}),({ENTRATA_S}-(t-{a:.2f}))*{H * 0.05 / ENTRATA_S:.1f},0)'" if ENTRATA_S else "0"
        g += f";[{corrente}][{idx}:v]overlay=0:{y}:format=auto:"
        g += f"enable='between(t,{a:.2f},{b - 0.001:.2f})'[o{k}]"
        corrente, idx = f"o{k}", idx + 1
    g += f";[{corrente}]format=yuv420p[v]"
    amap = ["-an"]
    musiche = [m for m in musiche if m and os.path.exists(m)]
    if musiche:
        quanti = max(1, int(DUR // 4.7) + 1)       # pezzi da ~5 s dello stesso brano, uniti con sfumatura
        musiche = (musiche * quanti)[:quanti]
        for m in musiche:
            cmd += ["-i", m]
        ingressi = [f"[{idx + j}:a]" for j in range(len(musiche))]
        if len(ingressi) == 1:
            a_out = ingressi[0]
        else:
            prec = ingressi[0]
            for j, x in enumerate(ingressi[1:]):
                g += f";{prec}{x}acrossfade=d=0.3[x{j}]"
                prec = f"[x{j}]"
            a_out = prec
        g += f";{a_out}volume={ov.MUSIC_VOL},{ov.LIMITATORE},apad,atrim=0:{DUR}[a]"   # 1/11/2026: niente sfumata, il giro riparte pulito
        amap = ["-map", "[a]"]
    cmd += ["-filter_complex", g, "-map", "[v]", *amap, "-t", f"{DUR}", "-c:v", "libx264",
            "-preset", "medium" if DUR <= 10 else "veryfast", "-crf", "18", "-profile:v", "high",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-movflags", "+faststart", dst]
    r = subprocess.run(cmd, capture_output=True, text=True, errors="ignore", timeout=ov.TEMPO_MAX_MONTAGGIO)
    shutil.rmtree(tmp, ignore_errors=True)
    if r.returncode != 0 or not os.path.exists(dst) or os.path.getsize(dst) < 50_000:
        raise RuntimeError(f"{nome}: " + r.stderr[-400:])
    info = {"formato": nome, "durata": DUR, "musica": os.path.basename(musiche[0]) if musiche else None,
            "stacchi": n, "testi": len(testi)}
    if piano:          # 6/11/2026: quante scene vengono dal video principale (le altre dalle clip extra)
        info["scene_dal_video"] = sum(1 for p in pezzi if p["c"] == clips[0])
    if dieci and nome not in ("dieci_foto", "foto_rapide"):
        # 6/11/2026 (integrazione, revisione del gruppo 2): in quanti fotogrammi della prima scena (su 5, 3 senza il
        # controllo del viso) si vede il viso, per tutti i formati video da 10 s (anche quelli a una scena), per il 16/11
        info["viso_prima_scena"] = int(pezzi[0].get("visi") or 0)
        # 7/11/2026 (studio della sera): l'apertura misurata sui due lati della prova (montaggio.apertura, per il 16/11):
        # con piu' scene la soglia del movimento e' la mediana delle scene del reel, con una scena MOTO_FERMO
        try:
            if misure is None and scaduto():     # 7/11/2026 (revisione, tempi): oltre la scadenza niente misura
                info["oltre_scadenza"] = True
                print("Oltre la scadenza del reel: apertura non misurata")
            else:
                if misure is None:
                    misure = [apertura_da(p["c"], p["inizio"]) for p in (pezzi if a_scene else pezzi[:1])]
                ap = apertura_info(misure)
                if ap:
                    # 7/11/2026 (revisione): la prima scena viene da una clip extra dell'archivio e non dal video
                    # dell'orario (per la tabella: "in movimento" contro "clip vecchia"); in giornata non si segna
                    if nome != "giornata":
                        ap["da_archivio"] = bool(pezzi[0]["c"] != clips[0])
                    info["apertura"] = ap
        except Exception as e:
            print("apertura non misurata (il reel esce lo stesso):", str(e)[:120])
    if velocita and min(velocita) < 1:
        info["velocita"] = min(velocita)
    if controlli and CONTROLLO:  # 6/11/2026: cosa hanno cambiato i controlli del primo secondo e del viso (analisi 16/11)
        info.update(CONTROLLO)
    return info


def make_broll(nome, clips, frase, dst, musiche=(), serie=None):
    """broll1/2/3: stacchi veloci di b-roll con la frase (fissa o a pezzi)."""
    d = FORMATI[nome]
    durate = d["stacchi"]
    if d["testo"] == "fisso":
        testi = [(0.0, sum(durate), frase)]
    else:
        # pezzi di senso compiuto (circa 5 parole l'uno, mai piu' degli stacchi), distribuiti sugli stacchi
        n = min(len(durate), max(2, round(len(frase.split()) / 5)))
        pezzi = dividi_in(frase, n)
        tot, testi = sum(durate), []
        tagli = [sum(durate[:i]) for i in range(len(durate) + 1)]          # istanti degli stacchi
        for i, p in enumerate(pezzi):
            a = tagli[round(i * len(durate) / len(pezzi))]
            b = tot if i == len(pezzi) - 1 else tagli[round((i + 1) * len(durate) / len(pezzi))]
            testi.append((a, b, p))
    return make_sequenza(clips, durate, testi, dst, musiche, serie, nome)


def make_racconto(nome, clips, righe, dst, musiche=(), serie=None):
    """racconto / racconto_broll / racconto_lento: 30 s, le 6 righe del racconto una dopo l'altra (5 s l'una)."""
    righe = [r for r in righe if r.strip()][:6]
    passo = DURATA_RACCONTO / len(righe)
    testi = [(i * passo, (i + 1) * passo, r) for i, r in enumerate(righe)]
    return make_sequenza(clips, FORMATI[nome]["stacchi"], testi, dst, musiche, serie, nome)


def make_lista(clips, titolo, righe, dst, musiche=(), serie=None):
    """31/10/2026: lista da 10 s: titolo, poi una regola alla volta, 2,5 s ciascuno (un'inquadratura per ogni testo)."""
    testi = [(0.0, 2.5, titolo)] + [(2.5 * (i + 1), 2.5 * (i + 2), f"{i + 1}. {r}") for i, r in enumerate(righe[:3])]
    CONTROLLO.clear()
    return make_sequenza(clips, [2.5] * 4, testi, dst, musiche, serie, "dieci_lista")


def tagli_a_tempo(musica, durate):
    """1/11/2026: gli stacchi si spostano (massimo 0,3 s) sul colpo piu' forte del brano."""
    import numpy as np
    try:
        pcm = subprocess.run([ov.FFMPEG, "-v", "error", "-i", musica, "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
                             capture_output=True, timeout=30).stdout
        x = np.frombuffer(pcm, dtype=np.int16).astype(float)
        passo = 160                                # 20 ms
        e = np.sqrt(np.mean(x[:len(x) // passo * passo].reshape(-1, passo) ** 2, axis=1))
        colpi = np.maximum(np.diff(e, prepend=0), 0)
        tagli, t = [], 0.0
        for d in durate[:-1]:
            t += d
            a, b = max(0, int((t - 0.3) * 50)), int((t + 0.3) * 50)
            tagli.append(round((a + int(np.argmax(colpi[a:b]))) / 50, 2) if colpi[a:b].size else t)
        punti = [0.0] + tagli + [sum(durate)]
        nuove = [round(q - p, 3) for p, q in zip(punti, punti[1:])]
        return nuove if min(nuove) >= 1.0 else list(durate)
    except Exception:
        return list(durate)


def _rallenty(c, durate):
    """6/11/2026: (durate, velocita, inizio) del rallenty: i primi secondi a velocita' normale, poi lo STESSO momento
    che continua al rallentatore (meta' velocita' sui video a 60 fps; 0,75 sui 30 fps, se no scatta)."""
    secondi, hdr = ov.probe(c)
    try:
        v = 0.5 if float(ov.fps(c)) >= 50 else 0.75
    except Exception:
        v = 0.75
    norm, lento = durate[0], durate[1]
    lento = min(lento, (secondi - 2 * MARGINE_S - norm) / v)     # video corto: rallentatore piu' breve
    if norm + lento < 6.0:
        raise ValueError(f"rallenty: video troppo corto ({secondi:.1f} s)")
    serve = norm + lento * v + 0.2
    inizio = MARGINE_S
    if secondi > serve + 1.0:
        try:
            inizio = ov.segmento_migliore(c, secondi, ov.HDR_TO_SDR if hdr else None, serve)[0]
        except Exception:
            pass
    inizio = round(min(max(inizio, MARGINE_S), max(0.0, secondi - serve)), 3)
    # 6/11/2026 (punto 14): i primi 2 s (velocita' normale) con il primo secondo pulito, lo stesso momento che rallenta
    inizio = _controlla_primo(c, inizio, MARGINE_S, max(0.0, secondi - serve), min(norm, PRIMO_S))
    return [round(norm, 3), round(lento, 3)], [1.0, v], inizio


def _intero_pulito(c, durate):
    """6/11/2026 (punto 14): 'intero' usa tutta la clip e parte da 0-0,1 s (come make_sequenza). Se il primo secondo
    non e' pulito si parte dal punto pulito piu' vicino e il reel si accorcia (mai sotto i 10 s). Restituisce (piano o
    None per lasciar fare a make_sequenza come prima, durate)."""
    try:
        S = ov.probe(c)[0]
        if not PRIMO_CONTROLLO or durate[0] < S - 0.35:    # clip oltre i 20 s: c'e' margine, ci pensa make_sequenza
            return None, durate
        t_def = 0.1 if S <= 12 else 0.0
        t = _controlla_primo(c, t_def, 0.0, max(0.0, S - 10.3), PRIMO_S)
        if abs(t - t_def) < 1e-3:
            return None, durate
        return [(c, t)], [round(max(10.0, min(20.0, S - t - 0.3)), 2)]
    except Exception as e:
        print("intero: controllo del primo secondo non riuscito, la clip resta com'era:", e)
        return None, durate


def _guarda(p, sorgente, W, H, quanti, dieci, controlli, lato=None):
    """I fotogrammi del pezzo p, gia' nel taglio 9:16 del reel: volti (29/10/2026, Alessandro: "le scritte non devono
    mai coprire il viso"), in quanti fotogrammi si vede il viso (6/11: uno alla volta, stessi riquadri di prima),
    mappa dei dettagli, schiarita e, con i controlli accesi, se la scena e' tutta nera. Restituisce p.
    7/11/2026 (revisione): p["guardato"] = (inizio, secondi) del tratto guardato davvero (solo se i fotogrammi ci sono),
    per _riguarda; lato = (w, h) dei fotogrammi se non W x H (i riquadri sono in frazioni: stesso taglio 9:16)."""
    p.update(volti=[], visi=0, mappa=None, schiarisci="", nero=False)
    p.pop("guardato", None)
    try:
        w, h = lato or (W, H)
        fr = ov.extract_frames(p["c"], sorgente, n=quanti, start=p["inizio"],
                               vf=f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}")
        per = [ov.detect_faces([x], ruotati=dieci) for x in fr]
        p["volti"], p["visi"] = [b for x in per for b in x], sum(1 for x in per if x)
        p["mappa"] = ov.mappa_dettagli(fr)
        p["schiarisci"] = ov.schiarita(fr) if dieci else ""
        p["nero"] = bool(controlli) and _pezzo_nero(fr)
        if fr:
            p["guardato"] = (round(float(p["inizio"]), 2), round(float(sorgente), 2))
    except Exception:
        pass
    return p


RIGUARDA_LATO = (540, 960)   # 7/11/2026 (revisione): fotogrammi di _riguarda (detect_faces lavora comunque a 720 px)
# 7/11/2026 (revisione, prova sul PC): con 5 fotogrammi su una scena di 5 s (uno al secondo) la palestra spostata per
# prima in dieci_due aveva ancora la scritta su fronte e capelli tra due fotogrammi guardati (lui si muove: la scena e'
# scelta apposta in movimento). Le scene riguardate si guardano ogni RIGUARDA_PASSO s (al massimo RIGUARDA_MAX)
RIGUARDA_PASSO, RIGUARDA_MAX = 0.5, 12


def _riguarda(pezzi, durate, W, H, quanti, dieci):
    """7/11/2026 (revisione, regola 2: la scritta mai sul viso): dopo il riordino della prima scena (_primo_azione,
    _primo_pezzo) le scene spostate hanno un altro inizio e la durata del nuovo posto, ma i visi (e la mappa) erano quelli
    del tratto di prima: un pezzo del reel non era mai stato guardato e la scritta poteva finire su un viso che compare
    solo li'. Ogni scena che esce dal tratto gia' guardato si riguarda tutta, un fotogramma ogni RIGUARDA_PASSO s (almeno
    quanti); i visi nuovi si AGGIUNGONO a quelli di prima (mai toglierne: piu' prudenza), mappa e schiarita vengono dal
    tratto nuovo, visi resta "su quanti" (montaggio.viso_prima_scena). Vale per tutti e due i lati della prova (e'
    sicurezza). Se non riesce, la scena resta com'era. Restituisce i pezzi."""
    import math
    for i, p in enumerate(pezzi):
        g = p.get("guardato")
        a, b = float(p["inizio"]), float(p["inizio"]) + float(durate[i])
        if g and g[0] - 0.011 <= a and b <= g[0] + g[1] + 0.011:      # dentro il tratto gia' guardato
            continue
        try:
            n = int(min(RIGUARDA_MAX, max(quanti, math.ceil(float(durate[i]) / RIGUARDA_PASSO))))
            q = _guarda(dict(p), durate[i], W, H, n, dieci, False, lato=RIGUARDA_LATO)
            if not q.get("guardato"):
                print(f"Scena {i + 1}: fotogrammi del tratto nuovo non letti, restano i visi di prima")
                continue
            q["visi"] = int(round(q["visi"] * quanti / n))
            q["volti"] = list(q["volti"]) + list(p.get("volti") or [])
            q["nero"] = p.get("nero", False)
            pezzi[i] = q
            CONTROLLO["scene_riguardate"] = CONTROLLO.get("scene_riguardate", 0) + 1
            print(f"Scena {i + 1} spostata ({os.path.basename(p['c'])} {a:.2f}-{b:.2f} s): riguardata, "
                  f"{len(q['volti']) - len(p.get('volti') or [])} visi in piu'")
        except Exception as e:
            print(f"Scena {i + 1}: non riguardata ({str(e)[:100]}), restano i visi di prima")
    return pezzi


def _senza_nere(pezzi, durate, W, H, quanti, dieci):
    """6/11/2026 (revisione, punto 14): al posto di una scena tutta nera un altro punto di una clip del reel che non e'
    nera: prima le clip che hanno gia' scene buone (di solito il video principale), il punto piu' lontano dalle scene
    che usano gia' quella clip. Al massimo 3 prove per scena; se nessuna va, la scena resta com'era. Le durate restano
    ai loro posti. Segna in CONTROLLO quante scene nere c'erano e quante sono rimaste."""
    nere = [i for i, p in enumerate(pezzi) if p["nero"]]
    ordine = []
    for p in sorted(pezzi, key=lambda p: p["nero"]):        # sorted e' stabile: prima le clip con scene buone
        if p["c"] not in ordine:
            ordine.append(p["c"])
    rimaste = 0
    for i in nere:
        sorg, fatto, prove = durate[i] + 0.2, False, 0
        for c in ordine:
            if prove >= 3:
                break
            if clip_nera(c):
                continue
            secondi, hdr = ov.probe(c)
            usati = [(q["inizio"], q["inizio"] + durate[j] + 0.2) for j, q in enumerate(pezzi) if q["c"] == c]
            alto = max(MARGINE_S, secondi - sorg - MARGINE_S)
            passi = sorted({round(min(alto, MARGINE_S + k * 0.25), 2) for k in range(int((alto - MARGINE_S) / 0.25) + 2)})
            lontano = lambda t: min([max(a - (t + sorg), t - b) for a, b in usati] or [0.0])
            t = max(passi, key=lambda t: (lontano(t), -t))
            prove += 1
            nuovo = _guarda({"c": c, "inizio": t, "secondi": secondi, "hdr": hdr}, durate[i], W, H, quanti, dieci, True)
            if not nuovo["nero"]:
                print(f"Scena {i + 1} tutta nera ({os.path.basename(pezzi[i]['c'])}): al suo posto "
                      f"{os.path.basename(c)} da {t:.2f} s")
                pezzi[i], fatto = nuovo, True
                if i == 0:     # la prima scena non e' piu' quella nera: il suo primo secondo lo guarda _primo_pezzo
                    CONTROLLO.pop("primo_risolto", None)
                break
        rimaste += not fatto
    CONTROLLO["scene_nere"] = len(nere)
    if rimaste:
        CONTROLLO["scene_nere_rimaste"] = rimaste
    return pezzi


AZIONE_SPOSTA = (1.0, -1.0, 2.0, -2.0)   # 7/11/2026 (revisione): spostamenti provati nel video dell'orario (entro CERCA_S)


def _azione_spostata(pezzi, durate, mediana, principale, d0):
    """7/11/2026 (revisione, lato "azione"): (k, inizio, misura) di una scena k del video dell'orario spostata di 1 o 2 s
    che non e' un primo piano fermo e ha il primo secondo pulito; dentro la clip (al primo posto dura durate[0]), mai
    sopra le altre scene della stessa clip; al massimo PROVE_SCENE misure. None se non c'e'."""
    dmax, prove = max(durate), 0
    for k in sorted((k for k, p in enumerate(pezzi) if p["c"] == principale), key=lambda k: k):
        p = pezzi[k]
        altre = [q["inizio"] for j, q in enumerate(pezzi) if j != k and q["c"] == p["c"]]
        for dt in AZIONE_SPOSTA:
            t = round(p["inizio"] + dt, 3)
            if abs(dt) > CERCA_S or t < MARGINE_S or t + durate[0] > p["secondi"] - 0.1:
                continue
            if any(t < a + dmax and a < t + durate[0] for a in altre):     # sopra un'altra sua scena
                continue
            if prove >= PROVE_SCENE:
                return None
            prove += 1
            m = apertura_da(p["c"], t)
            if m and not primo_piano_fermo(m[0], m[1], mediana) and not primo_secondo(p["c"], t, d0):
                return k, t, m
    return None


def _primo_azione(pezzi, durate, principale=None):
    """7/11/2026 (studio della sera, modifica 1a), lato "azione": per prima una scena con il primo secondo pulito che
    NON sia un primo piano fermo (viso vero grande e movimento sotto la mediana delle scene del reel); tra queste prima
    quelle del video dell'orario (il contenuto piu' nuovo), poi quella che si muove di piu' nel primo secondo. Al massimo
    PROVE_SCENE letture del primo secondo, come la fase 1. None = nessuna scena cosi': resta la scelta della fase 1.
    Restituisce (pezzi, misure delle scene nell'ordine nuovo) o None.
    7/11/2026 (revisione; regola 7, prima il contenuto nuovo): se tutte le scene del video dell'orario sono primi piani
    fermi (il selfie in macchina, il suo video piu' comune) prima di passare alle clip d'archivio si cerca nel SUO video
    un inizio spostato di 1 o 2 s (_azione_spostata) che non sia fermo e abbia il primo secondo pulito; tra le clip
    d'archivio poi prima le scene con lui (viso vero nel primo secondo, o il viso in almeno VISO_MIN fotogrammi), poi la
    piu' mossa (al massimo PROVE_SCENE letture per ognuno dei tre passi). montaggio.apertura.da_archivio dice se il
    reel apre con una clip d'archivio, montaggio.apertura_spostata di quanto si e' spostato l'inizio nel suo video."""
    import statistics
    misure = [apertura_da(p["c"], p["inizio"]) for p in pezzi]
    if any(m is None for m in misure):
        return None
    mediana = statistics.median(m[1] for m in misure)
    principale = principale or pezzi[0]["c"]
    d0 = min(durate[0], PRIMO_S)
    fermo0 = primo_piano_fermo(*misure[0], mediana)
    pezzi = list(pezzi)        # una scena spostata nel video dell'orario cambia solo qui (copia)

    def al_primo_posto(k):     # al primo posto la scena dura durate[0]: deve stare dentro la sua clip
        p = dict(pezzi[k])
        p["inizio"] = round(min(p["inizio"], max(0.0, p["secondi"] - durate[0] - 0.1)), 3)
        return p
    fermo = lambda k: primo_piano_fermo(*misure[k], mediana)
    pulito = lambda k: not primo_secondo(pezzi[k]["c"], al_primo_posto(k)["inizio"], d0)
    suoi = sorted((k for k in range(len(pezzi)) if pezzi[k]["c"] == principale and not fermo(k)),
                  key=lambda k: (-misure[k][1], k))
    scelta = next((k for k in suoi[:PROVE_SCENE] if pulito(k)), None)
    if scelta is None:         # nel video dell'orario, un inizio spostato di 1-2 s
        spostata = _azione_spostata(pezzi, durate, mediana, principale, d0)
        if spostata:
            scelta, t, m = spostata
            CONTROLLO["apertura_spostata"] = round(t - pezzi[scelta]["inizio"], 2)
            print(f"Apertura in azione: scena {scelta + 1} del video dell'orario da {t:.2f} s invece di "
                  f"{pezzi[scelta]['inizio']:.2f} s (movimento {m[1]:.1f})")
            pezzi[scelta], misure[scelta] = dict(pezzi[scelta], inizio=t), m
    if scelta is None:         # le clip d'archivio: prima le scene con lui, poi la piu' mossa
        con_lui = lambda k: misure[k][0] > 0 or pezzi[k]["visi"] >= VISO_MIN
        altre = sorted((k for k in range(len(pezzi)) if pezzi[k]["c"] != principale and not fermo(k)),
                       key=lambda k: (not con_lui(k), -misure[k][1], k))
        scelta = next((k for k in altre[:PROVE_SCENE] if pulito(k)), None)
    if scelta is None:
        return None
    CONTROLLO["apertura_fermo_prima"] = fermo0
    if scelta == 0:
        return pezzi, misure
    p0, nuovo = pezzi[0], al_primo_posto(scelta)
    ordine = [scelta] + [j for j in range(len(pezzi)) if j not in (0, scelta)]
    resto = [pezzi[j] for j in ordine[1:]]
    stessi = [j for j, p in enumerate(resto) if p["c"] == p0["c"]]
    dopo = next((j for j in stessi if resto[j]["inizio"] > p0["inizio"]), None)
    dove = dopo if dopo is not None else (stessi[-1] + 1 if stessi else 0)
    resto.insert(dove, p0)
    ordine.insert(1 + dove, 0)
    # come la fase 1: le scene spostate prendono la durata del nuovo posto e restano dentro la loro clip
    resto = [dict(p, inizio=round(min(p["inizio"], max(0.0, p["secondi"] - durate[j + 1] - 0.1)), 3))
             if p["inizio"] + durate[j + 1] > p["secondi"] - 0.1 else p for j, p in enumerate(resto)]
    CONTROLLO["scena_azione_prima"] = True
    if primo_secondo(p0["c"], p0["inizio"], d0):
        CONTROLLO.pop("primo_risolto", None)
    print(f"Apertura in azione: scena {scelta + 1} per prima (movimento {misure[scelta][1]:.1f}, viso vero alto "
          f"{misure[scelta][0]:.2f}; la scena 1 aveva {misure[0][1]:.1f} e {misure[0][0]:.2f})")
    nuovi = [nuovo] + resto
    # le misure seguono le scene (quelle spostate dentro la clip si rimisurano)
    return nuovi, [misure[k] if nuovi[i]["inizio"] == pezzi[k]["inizio"] else apertura_da(nuovi[i]["c"], nuovi[i]["inizio"])
                   for i, k in enumerate(ordine)]


def _primo_pezzo(pezzi, durate):
    """6/11/2026 (punti 13 e 14): la prima scena deve mostrare il viso se un'altra scena del reel lo mostra (spalle o
    lontano -> dopo) e avere il primo secondo pulito; se no va per prima un'altra scena che lo e'. Prima la pulizia,
    poi il viso: mai un primo secondo nero per avere il viso. Le altre scene restano nell'ordine di prima; quella tolta
    dal primo posto torna al suo posto nel tempo tra le scene della stessa clip. Le durate restano ai loro posti (gli
    stacchi sono sul colpo della musica). Restituisce i pezzi nel nuovo ordine."""
    ha_viso = lambda p: p["visi"] >= VISO_MIN
    d0 = min(durate[0], PRIMO_S)
    pulito = lambda p: not primo_secondo(p["c"], p["inizio"], d0)
    altri_viso = [k for k in range(1, len(pezzi)) if ha_viso(pezzi[k])]
    ok0, viso0 = pulito(pezzi[0]), ha_viso(pezzi[0])
    if ok0 and (viso0 or not altri_viso):
        return pezzi
    # 6/11/2026 (integrazione, revisione del gruppo 2): a parita' prima le scene della stessa clip della prima scena
    # (il video dell'orario, il contenuto piu' nuovo), poi quelle delle clip d'archivio
    altra = lambda k: pezzi[k]["c"] != pezzi[0]["c"]
    if ok0:            # pulita ma senza viso: le scene col viso, prima quelle dove si vede di piu'
        cand = sorted(altri_viso, key=lambda k: (altra(k), -pezzi[k]["visi"], k))
    else:              # primo secondo sporco: le altre scene, prima quelle col viso
        cand = sorted(range(1, len(pezzi)), key=lambda k: (not ha_viso(pezzi[k]), altra(k), -pezzi[k]["visi"], k))
    def al_primo_posto(k):     # al primo posto la scena dura durate[0]: deve stare dentro la sua clip
        p = dict(pezzi[k])
        p["inizio"] = round(min(p["inizio"], max(0.0, p["secondi"] - durate[0] - 0.1)), 3)
        return p
    scelta = next((k for k in cand[:PROVE_SCENE] if pulito(al_primo_posto(k))), None)
    if scelta is None:
        return pezzi
    p0, nuovo = pezzi[0], al_primo_posto(scelta)
    resto = [p for j, p in enumerate(pezzi) if j not in (0, scelta)]
    stessi = [j for j, p in enumerate(resto) if p["c"] == p0["c"]]
    dopo = next((j for j in stessi if resto[j]["inizio"] > p0["inizio"]), None)
    resto.insert(dopo if dopo is not None else (stessi[-1] + 1 if stessi else 0), p0)
    # 6/11/2026 (integrazione, revisione del gruppo 2): le scene spostate prendono la durata del nuovo posto (gli stacchi
    # restano sul colpo): ognuna deve stare dentro la sua clip, se no l'ultimo fotogramma restava fermo (tpad)
    resto = [dict(p, inizio=round(min(p["inizio"], max(0.0, p["secondi"] - durate[j + 1] - 0.1)), 3))
             if p["inizio"] + durate[j + 1] > p["secondi"] - 0.1 else p for j, p in enumerate(resto)]
    CONTROLLO["scena_viso_prima" if ok0 else "scena_cambiata"] = True
    if not ok0:
        CONTROLLO.pop("primo_risolto", None)
    print("Prima scena cambiata:", "il viso si vede" if ok0 else f"primo secondo {primo_secondo(p0['c'], p0['inizio'], d0)}",
          f"-> scena {scelta + 1} per prima")
    return [nuovo] + resto


def make_dieci(nome, clips, frase, dst, musiche=(), serie=None, controlla_viso=False):
    """dieci / dieci_due / dieci_broll: 10 s. 1/11/2026: la frase intera dal primo fotogramma (Instagram: la gente se ne
    va dopo 4 s) e niente "GIORNO X / 365" sul video: lo spazio del primo secondo e' della frase, la serie e' in descrizione.
    6/11/2026: taglio1/2/3, dieci_due, cinema e post tagliano le scene dal video principale (piano_scene); cinema e post
    mettono la frase fuori dal video; rallenty e loop giocano con la velocita' dello stesso momento."""
    CONTROLLO.clear()
    d = FORMATI[nome]
    durate = durate_formato(nome, ov.probe(clips[0])[0])
    piano = velocita = indietro = layout = None
    testi = [(0.0, sum(durate), frase)]
    if d.get("rallenty"):
        durate, velocita, t0 = _rallenty(clips[0], durate)
        if musiche and os.path.exists(musiche[0]):        # il rallentatore parte sul colpo della musica
            durate = tagli_a_tempo(musiche[0], durate)
        piano = [(clips[0], t0), (clips[0], round(t0 + durate[0], 3))]
        testi = [(0.0, sum(durate), frase)]
    elif d.get("loop"):    # avanti e indietro dallo stesso punto: l'ultimo fotogramma e' il primo, il giro non si vede
        secondi = ov.probe(clips[0])[0]
        t0 = momento_forte(clips[0], durate[0])
        t0 = round(min(max(t0, 0.0), max(0.0, secondi - durate[0] - 0.1)), 3)
        # 6/11/2026 (punto 14): il primo secondo pulito (e' anche l'ultimo del giro all'indietro)
        t0 = _controlla_primo(clips[0], t0, 0.0, max(0.0, secondi - durate[0] - 0.1), min(durate[0], PRIMO_S))
        piano, indietro = [(clips[0], t0), (clips[0], t0)], [False, True]
        testi = [(0.0, sum(durate), frase)]
    else:
        # 6/11/2026: stesse durate che scene_mancanti ha usato per decidere quante clip extra scaricare
        durate = durate_scene(nome, clips[0], musiche)
        testi = [(0.0, sum(durate), frase)]
        if nome in A_SCENE:
            piano = piano_scene(clips, durate)
        elif nome == "intero":   # 6/11/2026 (punto 14): la clip intera; l'inizio si sposta solo accorciandola
            piano, durate = _intero_pulito(clips[0], durate)
            testi = [(0.0, sum(durate), frase)]
        if d.get("layout"):
            W = ov.LATO_USCITA
            layout = cornice(W, int(W * 16 / 9), d["layout"], frase)
            testi = []                             # la frase e' gia' nella cornice, fuori dal video
    return make_sequenza(clips, durate, testi, dst, musiche, None, nome, controlla_viso,
                         piano=piano, velocita=velocita, indietro=indietro, layout=layout)


def make_storia(clips, titolo, righe, dst, musiche=(), serie=None):
    """storia: titolo poi le righe, una schermata alla volta (racconto di ~22 s)."""
    sch = FORMATI["storia"]["schermate"][:1 + len(righe[:3])]
    testi, t0 = [], 0.0
    for i, (dur, t) in enumerate(zip(sch, [titolo] + [f"{k}. {r}" for k, r in enumerate(righe[:3], 1)])):
        testi.append((t0, t0 + dur, t))
        t0 += dur
    # sfondo: pezzi lunghi (6-8 s) dalle clip, cosi' si legge con calma
    totale, durate = sum(sch), []
    while sum(durate) < totale - 0.01:
        durate.append(min(7.0, round(totale - sum(durate), 2)))
    return make_sequenza(clips, durate, testi, dst, musiche, serie, "storia")


# ------------------------------------------------------------------ formato GIORNATA (6/11/2026)
# Alessandro lavora dalle 9 alle 19 e durante il giorno gira ~10 clip mute da 10 s di momenti diversi (barba, barbiere,
# macchina, ufficio, pacchi, ascensore, borsa, pranzo, allenamento). GIORNATA le mette in fila come la sua giornata:
# una scena per momento (4-7 scene sui 10 s), stacchi sul colpo della musica, la frase fissa dal primo fotogramma.
# La prima scena e' il momento piu' forte con il suo viso (3 persone su 4 vanno via nei primi secondi: rapporto del
# 6/11), poi la giornata dalla mattina alla sera. Mai la stessa clip due volte, mai due clip quasi uguali.
GIORNATA_MIN, GIORNATA_MAX = 4, 7     # momenti diversi in un reel
GIORNATA_DURATA = 10.0
GIORNATA_SCENA_MIN = 1.0              # nessuna scena sotto 1 s, anche dopo lo spostamento sul colpo della musica
# differenza media delle miniature (0-255) sotto cui due clip sono lo stesso momento (prove del 6/11: stesso video 0,
# due clip diverse 39-100, anche due selfie allo specchio di giorni diversi 39)
GIORNATA_SIMILI = 20.0
# 6/11/2026 (revisione): i visi si guardano fotogramma per fotogramma, ogni 0,5 s dall'inizio della scena (0 = il
# primo fotogramma) fino a 2,5 s; quelli della prima scena solo nel suo PRIMO secondo (il gancio)
GIORNATA_PASSO, GIORNATA_FOTOGRAMMI = 0.5, 6
GIORNATA_GANCIO_S = 1.0
# 6/11/2026 (integrazione, revisione della giornata): oltre questi secondi di analisi (e con almeno GIORNATA_MIN momenti)
# le clip che restano non si guardano piu': sul PC una clip 4K HDR costava fino a ~7 minuti
GIORNATA_TEMPO_MAX = 360
# 7/11/2026 (revisione, tempi): con la scadenza del reel (SCADENZA) l'analisi si ferma anche GIORNATA_RISERVA secondi
# prima della scadenza (il montaggio 4K e il ripiego con la fascia devono ancora starci)
GIORNATA_RISERVA = 600
GANCIO_PROVE = 3                      # 7/11/2026 (revisione): momenti provati al massimo per l'apertura in azione pulita
GIORNATA_BUIO = 0.10                  # luce media della scena (0-1) sotto cui una clip non principale e' quasi nera
GIORNATA_TAGLIO = "scale=540:960:force_original_aspect_ratio=increase,crop=540:960"   # fotogrammi ridotti, 9:16


@functools.lru_cache(maxsize=32)
def _momento_ridotto(src, durata, firma):
    """6/11/2026 (integrazione, revisione della giornata): come _momento_forte ma su fotogrammi RIDOTTI (540x960 nel
    taglio 9:16, HDR convertito): a piena risoluzione ogni fotogramma PNG costava ~19 s sul PC (~433 s per una clip
    4K HDR) e la giornata ne analizza fino a 7. Clip corte (fino alla scena + 1,5 s): MARGINE_S, come prima."""
    S, hdr = ov.probe(src)
    if S <= durata + 1.5:
        return MARGINE_S
    vf = f"{ov.HDR_TO_SDR},{GIORNATA_TAGLIO}" if hdr else GIORNATA_TAGLIO
    return ov.segmento_migliore(src, S, vf, durata + 0.2)[0]


def _verticale(path):
    """True se la clip si vede in verticale (rotazione compresa) o se non si sa; False se e' orizzontale."""
    try:
        r = subprocess.run([ov.FFMPEG, "-hide_banner", "-i", path], capture_output=True, text=True, errors="ignore",
                           timeout=30).stderr
        m = re.search(r"Video:.*?\b(\d{3,5})x(\d{3,5})\b", r)
        if not m:
            return True
        w, h = int(m.group(1)), int(m.group(2))
        if ov.rotazione(path) in (90, 270):
            w, h = h, w
        return h >= w
    except Exception:
        return True


def _stesso_file(path):
    """(grandezza, md5 del primo MB): lo stesso video caricato due volte con due nomi."""
    import hashlib
    with open(path, "rb") as f:
        return os.path.getsize(path), hashlib.md5(f.read(1 << 20)).hexdigest()


def _minuti_giornata(quando):
    """Minuti dalle 5 del mattino di 'AAAA-MM-GGTHH:MM' (dopo mezzanotte e' ancora la sera prima); None se manca."""
    m = re.search(r"T(\d{2}):(\d{2})", str(quando or ""))
    return (int(m.group(1)) * 60 + int(m.group(2)) - 300) % 1440 if m else None


def momento_giornata(c, durata):
    """La scena di `durata` s della clip, nel suo momento piu' forte (momento_forte), e cosa serve per sceglierla:
    viso visibile nel taglio 9:16 del reel, movimento, nitidezza, luce, una miniatura per i doppioni e, se fa da
    prima scena, da dove partire perche' nel PRIMO secondo si veda il viso piu' grande (gancio_inizio, gancio_area,
    viso_gancio).
    6/11/2026 (revisione): visi fotogramma per fotogramma (ogni 0,5 s dall'inizio della scena); prima 5 fotogrammi
    sparsi su 2,8 s davano il bonus del viso grande anche quando il viso arrivava dopo la fine della scena (la prima
    scena del reel partiva con il viso piccolo dietro al telefono nello specchio)."""
    import cv2
    import numpy as np
    secondi, hdr = ov.probe(c)
    if secondi < 1.0:
        raise ValueError(f"clip troppo corta ({secondi:.1f} s)")
    fine = max(0.0, secondi - durata - 0.05)               # ultimo inizio possibile della scena
    try:     # 6/11/2026 (integrazione): il momento forte sui fotogrammi ridotti; se non riesce, come prima
        t = _momento_ridotto(c, round(float(durata), 1), _firma_lato(c))   # 7/11: firma diversa sul lato "azione"
    except Exception as e:
        print(f"giornata: momento forte ridotto non riuscito ({str(e)[:80]}), uso quello a piena risoluzione", flush=True)
        t = momento_forte(c, durata)
    t = round(min(max(t, MARGINE_S if secondi >= durata + 2 * MARGINE_S else 0.0), fine), 3)
    taglio = GIORNATA_TAGLIO
    vf = f"{ov.HDR_TO_SDR},{taglio}" if hdr else taglio
    fr = {}                                                # secondi dall'inizio della scena -> fotogramma
    for k in range(GIORNATA_FOTOGRAMMI):
        o = round(k * GIORNATA_PASSO, 2)
        if k and t + o >= secondi - 0.05:
            break
        x = ov.extract_frames(c, 0.02, n=1, start=max(0.0, t + o - 0.01), vf=vf)   # il fotogramma a t + o
        if x:
            fr[o] = x[0]
    if not fr:
        raise ValueError("fotogrammi non letti")
    visi = {o: ov.detect_faces([f], ruotati=True) for o, f in fr.items()}
    area = lambda o: max([(b[2] - b[0]) * (b[3] - b[1]) for b in visi[o]] or [0.0])
    dentro = lambda da, lungo: [o for o in fr if da - 1e-6 <= o < da + lungo - 1e-6]
    scena = dentro(0.0, durata) or [min(fr)]
    # prima scena: parte dal fotogramma da cui il viso c'e' ed e' piu' grande per TUTTO il primo secondo (il piu'
    # piccolo dei suoi fotogrammi: anche il PRIMO fotogramma del reel e' il viso); si sposta solo se il viso e' piu'
    # grande di almeno il 15%, con almeno 2 fotogrammi nel primo secondo e mai oltre la fine della clip.
    # 6/11/2026 (prova sulle clip vere): un viso visto in un fotogramma si' e in quello dopo no e' un errore del
    # riconoscimento (il piatto del pranzo a 3 e 4,5 s, non a 3,5 e 4): il reel partiva dal piatto
    g_t, g_area = t, -1.0
    for o in sorted(fr):
        s = round(min(t + o, fine), 3)
        primo = dentro(s - t, GIORNATA_GANCIO_S)
        if o and len(primo) < 2:
            continue
        a = min(area(p) for p in primo) if primo else 0.0
        if a > g_area * 1.15 + 0.002:
            g_t, g_area = s, a
    g_scena = dentro(g_t - t, durata) or scena
    g = {o: cv2.cvtColor(cv2.resize(f, (90, 160)), cv2.COLOR_BGR2GRAY).astype(np.float32) for o, f in fr.items()}

    def misure(tempi):                                     # (nitidezza, movimento) dei fotogrammi della scena
        xs = [g[o] for o in sorted(tempi)]
        return (float(np.mean([cv2.Laplacian(x, cv2.CV_32F).var() for x in xs])),
                float(np.mean([np.abs(a - b).mean() for a, b in zip(xs, xs[1:])])) if len(xs) > 1 else 0.0)
    nitido, moto = misure(scena)
    nitido_g, moto_g = misure(g_scena)                     # la stessa scena se fa da prima, da gancio_inizio
    try:     # 6/11/2026 (integrazione): scena tutta nera, bianca o uguale (stesse soglie di _pezzo_nero)
        nera = bool(_pezzo_nero([fr[o] for o in scena]))
    except Exception:
        nera = False
    # 7/11/2026 (studio della sera, modifiche 1b e 7): per il lato "azione" della prova dell'apertura, sugli stessi
    # fotogrammi: il viso VERO della scena (ov.visi_veri) e il movimento nel primo secondo (0 -> +1 s, grigi 90x160)
    vero, alto_vero, moto_primo = 0.0, 0.0, None
    try:     # 7/11/2026 (revisione): fotogrammi ogni 0,5 s (radi): pelle E occhio, anche se il viso si muove
        veri = ov.visi_veri([fr[o] for o in sorted(scena)], [visi[o] for o in sorted(scena)], fermi=False)
        vero = sum(1 for v in veri if v) / len(veri)
        alto_vero = max([b[3] - b[1] for v in veri for b in v] or [0.0])
        if 0.0 in g and 1.0 in g:
            moto_primo = float(np.abs(g[1.0] - g[0.0]).mean())
    except Exception as e:
        print("giornata: viso vero e movimento non misurati:", str(e)[:120], flush=True)
    return {"clip": c, "inizio": t, "secondi": secondi, "nera": nera,
            "viso_vero": vero, "alto_vero": float(alto_vero), "moto_primo": moto_primo,
            "viso": sum(1 for o in scena if visi[o]) / len(scena),
            "gancio_inizio": float(g_t), "gancio_area": float(max(0.0, g_area)),
            "viso_gancio": sum(1 for o in g_scena if visi[o]) / len(g_scena),
            "nitido": nitido, "moto": moto, "nitido_gancio": nitido_g, "moto_gancio": moto_g,
            "luce": float(np.mean([g[o].mean() for o in scena])) / 255,
            # i doppioni su tutti i fotogrammi (fino a 2,5 s), come le prove che hanno fissato GIORNATA_SIMILI
            "firma": np.mean([cv2.resize(g[o], (18, 32), interpolation=cv2.INTER_AREA) for o in sorted(g)], axis=0),
            "verticale": _verticale(c)}


def tagli_giornata(musica, durate, minimo=GIORNATA_SCENA_MIN):
    """Come tagli_a_tempo (ogni stacco sul colpo piu' forte entro 0,3 s), ma uno stacco alla volta e mai sotto
    `minimo` s per scena: con 7 scene da 1,4 s tagli_a_tempo rinuncerebbe a tutti gli stacchi a tempo."""
    import math
    import numpy as np
    try:
        pcm = subprocess.run([ov.FFMPEG, "-v", "error", "-i", musica, "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
                             capture_output=True, timeout=30).stdout
        x = np.frombuffer(pcm, dtype=np.int16).astype(float)
        passo = 160                                # 20 ms
        e = np.sqrt(np.mean(x[:len(x) // passo * passo].reshape(-1, passo) ** 2, axis=1))
        colpi = np.maximum(np.diff(e, prepend=0), 0)
        tot, n = round(sum(durate), 3), len(durate)
        tagli, t, prima = [], 0.0, 0.0
        for k, d in enumerate(durate[:-1]):
            t += d
            lo, hi = max(t - 0.3, prima + minimo), min(t + 0.3, tot - (n - 1 - k) * minimo)
            if hi < lo:
                return list(durate)
            a, b = math.ceil(lo * 50 - 1e-6), math.floor(hi * 50 + 1e-6) + 1
            tagli.append(round((a + int(np.argmax(colpi[a:b]))) / 50, 2) if colpi[a:b].size else round(t, 2))
            prima = tagli[-1]
        punti = [0.0] + tagli + [tot]
        nuove = [round(q - p, 3) for p, q in zip(punti, punti[1:])]
        return nuove if min(nuove) >= minimo - 0.011 else list(durate)
    except Exception:
        return list(durate)


def _gancio_azione(scelte, mm, mn):
    """7/11/2026 (studio della sera, modifica 1b), lato "azione": la prima scena della giornata. Niente premio al viso
    grande (fase 1: +0,5): al suo posto il movimento nel primo secondo (fino a +0,5); il viso VERO resta un punteggio
    normale (2 come per le altre scene, mai il bonus). Tra i momenti puliti con lui (viso vero visibile; se manca,
    qualsiasi viso), MAI un primo piano fermo (viso vero alto almeno ov.PRIMO_PIANO_ALTO e movimento sotto la mediana dei
    momenti) se ce n'e' un altro. None = nessun momento cosi': resta la scelta della fase 1."""
    import statistics
    pulite = [a for a in scelte if a["verticale"] and a["luce"] >= GIORNATA_BUIO and not a.get("nera")]
    con_lui = [a for a in pulite if a.get("viso_vero", 0) > 0] or [a for a in pulite if a.get("viso", 0) > 0]
    moti = [float(a.get("moto_primo") or 0.0) for a in scelte]
    mediana = statistics.median(moti) if moti else 0.0
    mobili = [a for a in con_lui
              if not primo_piano_fermo(a.get("alto_vero", 0.0), float(a.get("moto_primo") or 0.0), mediana)]
    mobili = [a for a in mobili if not a["vista"]] or mobili
    if not mobili:
        return None
    mp = max(moti) or 1.0
    punti = lambda a: (2.0 * a.get("viso_vero", 0.0) + 0.6 * a["moto"] / mm + 0.4 * a["nitido"] / mn
                       + 0.5 * min(1.0, float(a.get("moto_primo") or 0.0) / mp))
    # 7/11/2026 (revisione): il primo secondo pulito (mai mosso o buio: regola del gruppo 2, che in giornata e' spento).
    # Il lato "viso" ce l'ha gia' (un viso visto per tutto il primo secondo); qui si parte dal momento piu' mosso. Al
    # massimo GANCIO_PROVE momenti in ordine di punti (sorted e' stabile: il primo e' quello di max); se nessuno e'
    # pulito, None e resta la scelta della fase 1
    scelto = next((a for a in sorted(mobili, key=punti, reverse=True)[:GANCIO_PROVE]
                   if not primo_secondo(a["clip"], a["inizio"], GIORNATA_GANCIO_S)), None)
    if scelto is None:
        print("giornata: nessun momento in azione col primo secondo pulito, prima scena come la fase 1", flush=True)
        return None
    print(f"giornata: apertura in azione da {os.path.basename(scelto['clip'])} (movimento "
          f"{float(scelto.get('moto_primo') or 0):.1f}, mediana {mediana:.1f})", flush=True)
    return scelto


def piano_giornata(clips, ore=None, musica=None, scene=None, durata=GIORNATA_DURATA, viste=None):
    """(piano [(clip, inizio)], durate, info) del reel GIORNATA.
    clips[0] e' il video dell'orario e resta sempre (e' quello che risulta pubblicato); le altre sono momenti della
    giornata in ordine di preferenza (pubblica.clip_giornata: prima scene diverse). ore = data e ora di ripresa di
    ogni clip ('AAAA-MM-GGTHH:MM', None = dal file con overlay.data_ripresa); scene = etichette (palestra, macchina...);
    viste = True per le clip gia' uscite di recente (da sole o come scena): non fanno da prima scena se c'e' un'altra.
    6/11/2026 (revisione): la frase non si controlla piu' qui. Il controllo preventivo guardava fotogrammi diversi da
    quelli del montaggio e sbagliava nei due sensi (fascia quando la frase ci stava, o il contrario) e toglieva scene
    senza motivo: decide make_sequenza, sugli stessi fotogrammi del reel, prima di montare (make_giornata)."""
    import numpy as np
    n0 = len(clips)
    ore, scene = (list(ore or []) + [None] * n0)[:n0], (list(scene or []) + [None] * n0)[:n0]
    viste = (list(viste or []) + [False] * n0)[:n0]
    d0 = durata / max(GIORNATA_MIN, min(GIORNATA_MAX, n0))
    scelte, file_visti = [], set()
    t_inizio = time.time()
    # 7/11/2026 (revisione, tempi): il tetto e' anche legato all'orario del reel: al massimo fino a GIORNATA_RISERVA
    # secondi prima della scadenza (SCADENZA), mai oltre GIORNATA_TEMPO_MAX
    tetto = float(GIORNATA_TEMPO_MAX)
    rimasti = secondi_rimasti()
    if rimasti is not None:
        tetto = max(0.0, min(tetto, rimasti - GIORNATA_RISERVA))
        print(f"giornata: {rimasti / 60:.0f} minuti alla scadenza del reel, analisi al massimo {tetto:.0f} s "
              f"(appena ci sono {GIORNATA_MIN} momenti)", flush=True)
    for i, c in enumerate(clips):
        # 6/11/2026 (integrazione): un tetto al tempo dell'analisi, con gia' abbastanza momenti diversi
        if i and len(scelte) >= GIORNATA_MIN and time.time() - t_inizio > tetto:
            print(f"giornata: analisi oltre {tetto:.0f} s ({time.time() - t_inizio:.0f} s), "
                  f"le ultime {n0 - i} clip restano fuori", flush=True)
            break
        t_clip = time.time()
        try:
            chiave = _stesso_file(c)
            if chiave in file_visti:
                print(f"giornata: {os.path.basename(c)} e' lo stesso file di un'altra clip: saltata", flush=True)
                continue
            a = momento_giornata(c, d0)
            print(f"giornata: {os.path.basename(c)} analizzata in {time.time() - t_clip:.0f} s", flush=True)
        except Exception as e:
            if i == 0:
                raise
            print(f"giornata: {os.path.basename(c)} saltata ({str(e)[:120]})", flush=True)
            continue
        simile = next((b for b in scelte if float(np.abs(a["firma"] - b["firma"]).mean()) < GIORNATA_SIMILI), None)
        if simile:
            print(f"giornata: {os.path.basename(c)} quasi uguale a {os.path.basename(simile['clip'])}: saltata", flush=True)
            continue
        file_visti.add(chiave)
        a.update(principale=i == 0, ora=ore[i] or ov.data_ripresa(c), scena=scene[i], vista=bool(viste[i]))
        scelte.append(a)
    t_analisi = round(time.time() - t_inizio)
    print(f"giornata: analisi di {len(scelte)} momenti in {t_analisi} s", flush=True)
    if len(scelte) < GIORNATA_MIN:
        raise ValueError(f"giornata: solo {len(scelte)} momenti diversi (ne servono {GIORNATA_MIN})")
    # 6/11/2026 (integrazione; gruppo 2, punti 14 e 34): via le clip NON principali quasi nere (luce sotto GIORNATA_BUIO
    # o scena tutta nera) e poi quelle orizzontali (nel 9:16 restano tagliate al centro), le piu' deboli per prime,
    # finche' restano almeno GIORNATA_MIN momenti. Il video dell'orario resta sempre (montaggio.orizzontale dice se e'
    # orizzontale lui; le scene orizzontali rimaste delle altre clip sono in montaggio.scene_orizzontali)
    try:
        difetto = lambda a: (None if a["principale"] else "quasi nera" if a["luce"] < GIORNATA_BUIO or a.get("nera")
                             else None if a["verticale"] else "orizzontale")
        voto = lambda a: 2.0 * a["viso"] + 0.6 * a["moto"] + 0.4 * a["nitido"] / max(1.0, max(x["nitido"] for x in scelte))
        for tipo in ("quasi nera", "orizzontale"):
            for a in sorted([a for a in scelte if difetto(a) == tipo], key=voto):
                if len(scelte) <= GIORNATA_MIN:
                    break
                scelte.remove(a)
                print(f"giornata: {os.path.basename(a['clip'])} tolta ({tipo}, luce {a['luce']:.2f})", flush=True)
    except Exception as e:
        print("giornata: controllo delle clip nere e orizzontali non riuscito, restano tutte:", e, flush=True)
    mm = max([a["moto"] for a in scelte] + [a["moto_gancio"] for a in scelte]) or 1.0
    mn = max([a["nitido"] for a in scelte] + [a["nitido_gancio"] for a in scelte]) or 1.0
    for a in scelte:   # come segmento_migliore (viso, movimento, nitidezza); giu' le clip orizzontali e quelle al buio
        meno = (1.0 if not a["verticale"] else 0.0) + (0.8 if a["luce"] < 0.10 else 0.0)
        a["punti"] = 2.0 * a["viso"] + 0.6 * a["moto"] / mm + 0.4 * a["nitido"] / mn - meno
        # come prima scena conta la scena che parte da gancio_inizio (viso, movimento, nitidezza) e quanto e' grande il
        # viso nel primo secondo (rapporto del 6/11: "nel primo secondo ci sei tu e ti si riconosce"): un primo piano in
        # macchina batte lo stesso punteggio con il viso piccolo nello specchio della sala (fino a +0,5)
        a["punti_gancio"] = (2.0 * a["viso_gancio"] + 0.6 * a["moto_gancio"] / mm + 0.4 * a["nitido_gancio"] / mn
                             - meno + 0.5 * min(1.0, a["gancio_area"] / 0.04))
    while len(scelte) > GIORNATA_MAX:      # troppe: via la piu' debole della scena che si ripete di piu'
        altre = [a for a in scelte if not a["principale"]]
        quante = {s: sum(1 for a in altre if a["scena"] == s) for s in {a["scena"] for a in altre}}
        scelte.remove(min(altre, key=lambda a: (-quante[a["scena"]], a["punti"])))
    # la prima scena: il momento piu' forte con il viso nel suo primo secondo (in verticale e con luce), poi la
    # giornata in ordine di ora. Prima le clip non viste di recente: due reel vicini non partono dalla stessa scena
    gancio = None
    if ov.azione():    # 7/11/2026 (studio della sera, modifica 1b): lato "azione" della prova dell'apertura
        try:
            gancio = _gancio_azione(scelte, mm, mn)
        except Exception as e:
            print("giornata: apertura in azione non riuscita, prima scena come prima:", e, flush=True)
            gancio = None
    in_azione = gancio is not None
    if not in_azione:
        adatte = [a for a in scelte if a["gancio_area"] > 0 and a["verticale"] and a["luce"] >= 0.10]
        adatte = [a for a in adatte if not a["vista"]] or adatte
        gancio = max(adatte or [a for a in scelte if a["gancio_area"] > 0] or scelte, key=lambda a: a["punti_gancio"])
    resto = sorted((a for a in scelte if a is not gancio), key=lambda a: (
        _minuti_giornata(a["ora"]) is None, _minuti_giornata(a["ora"]) or 0, os.path.basename(a["clip"]).lower()))
    ordine = [gancio] + resto
    n = len(ordine)
    base = round(durata / n, 3)
    durate = [base] * (n - 1) + [round(durata - base * (n - 1), 3)]
    if musica and os.path.exists(musica):
        durate = tagli_giornata(musica, durate)
    # sul lato "azione" la prima scena parte dal suo momento forte (che li' parte in movimento), non dal viso piu' grande
    inizio_gancio = gancio["inizio"] if in_azione else gancio["gancio_inizio"]
    inizi = [inizio_gancio] + [a["inizio"] for a in resto]
    if inizio_gancio != gancio["inizio"]:
        print(f"giornata: prima scena {os.path.basename(gancio['clip'])} da {gancio['gancio_inizio']:.2f} s invece di "
              f"{gancio['inizio']:.2f} s: nel primo secondo il viso e' piu' grande", flush=True)
    piano = [(a["clip"], round(min(t, max(0.0, a["secondi"] - d - 0.05)), 3)) for a, t, d in zip(ordine, inizi, durate)]
    giorno0 = str(scelte[0]["ora"] or "")[:10] if scelte[0]["principale"] else ""
    if in_azione:
        info = {"scene": n, "con_viso": sum(1 for a in ordine if a["viso"] > 0),
                "viso_primo_secondo": bool(gancio.get("viso_vero", 0) > 0), "gancio_azione": True}
    else:
        info = {"scene": n, "con_viso": sum(1 for k, a in enumerate(ordine) if (a["viso_gancio"] if k == 0 else a["viso"]) > 0),
                "viso_primo_secondo": bool(gancio["gancio_area"] > 0)}     # bool vero: va in stato.json
    # 6/11/2026 (integrazione): scene da clip non principali orizzontali o quasi nere rimaste (servivano per arrivare a
    # GIORNATA_MIN momenti)
    oriz = sum(1 for a in ordine if not a["principale"] and not a["verticale"])
    scure = sum(1 for a in ordine if not a["principale"] and (a["luce"] < GIORNATA_BUIO or a.get("nera")))
    if oriz:
        info["scene_orizzontali"] = oriz
    if scure:
        info["scene_scure"] = scure
    info["secondi_analisi"] = t_analisi     # 7/11/2026 (revisione, tempi): per misurare i primi reel su GitHub
    if giorno0:
        info["stesso_giorno"] = sum(1 for a in ordine if str(a["ora"] or "")[:10] == giorno0)
    return piano, durate, info


def make_giornata(clips, frase, dst, musiche=(), ore=None, scene=None, controlla_viso=True, ultimo=None, nomi=None,
                  viste=None):
    """Reel GIORNATA (vedi piano_giornata): clips[0] = video dell'orario, le altre = momenti della stessa giornata.
    La frase va sul video se non copre nessun viso: lo decide make_sequenza sui fotogrammi del reel, PRIMA di montare
    (VisoCoperto); se no le STESSE scene escono con la fascia 'cinema' o 'post' (frase fuori dal video).
    6/11/2026 (revisione): con la fascia il reel resta GIORNATA, segnato con montaggio.cornice = cinema/post e NON
    come ripiego (ripiego_da): con 5-7 scene e i primi piani la fascia e' il caso normale, e contati come "ripiego
    giornata" questi reel non sarebbero mai entrati nel confronto dei formati (report.py pesa i formati con almeno 6
    reel). nomi = i nomi delle clip (paralleli a clips) per montaggio.clip_scene: le clip usate come scene; viste =
    le clip gia' uscite di recente (piano_giornata)."""
    import random
    CONTROLLO.clear()     # 6/11/2026 (integrazione): niente dati dei controlli di un altro montaggio nel suo stato.json
    musiche = [m for m in musiche if m and os.path.exists(m)]
    piano, durate, info = piano_giornata(clips, ore, musiche[0] if musiche else None, scene, viste=viste)
    usate = [clips[0]] + [c for c, _ in piano if c != clips[0]]
    try:
        r = make_sequenza(usate, durate, [(0.0, sum(durate), frase)], dst, musiche, None, "giornata", controlla_viso,
                          piano=piano)
    except VisoCoperto:
        tipo = random.choice([t for t in ("cinema", "post") if t != ultimo] or ["cinema"])
        print(f"giornata: la frase coprirebbe il viso, stesse scene con la fascia '{tipo}'", flush=True)
        W = ov.LATO_USCITA
        # 6/11/2026 (integrazione, revisione della giornata): la frase e' sulla fascia, non nella scritta in prova: lo
        # stile del tentativo scartato non deve finire in montaggio.scritta (prova a meta' della scritta)
        ov.ULTIMO_STILE = None
        r = make_sequenza(usate, durate, [], dst, musiche, None, "giornata", controlla_viso, piano=piano,
                          layout=cornice(W, int(W * 16 / 9), tipo, frase))
        r["cornice"] = tipo
        r["scritta"] = None
        r["fascia_viso"] = True     # 7/11/2026 (revisione, giro 2): come pubblica.monta_dieci, per la tabella del 17/11
    r.update(info)
    if nomi:
        nome = dict(zip(clips, nomi))
        r["clip_scene"] = [nome.get(c) for c, _ in piano if c != clips[0]]
    return r
