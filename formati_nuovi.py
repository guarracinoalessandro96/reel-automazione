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
import functools, os, re, shutil, subprocess, tempfile
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
}
# formati della famiglia "dieci" (scritta gialla, colori, viso controllato), oltre ai nomi che iniziano con "dieci"
DIECI_NOMI = ("taglio1", "taglio2", "taglio3", "intero", "cinema", "post", "rallenty", "loop")
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
    return _momento_forte(src, round(float(durata), 1), _firma(src))


def _firma(src):
    try:
        return (os.path.getsize(src), os.path.getmtime(src))
    except OSError:
        return None


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


def _grigi(src, prima, dopo=""):
    """Fotogrammi PICCOLO in grigio, nel taglio 9:16 del reel, con una sola lettura di ffmpeg e senza file."""
    import numpy as np
    w, h = PICCOLO
    vf = ",".join(x for x in (dopo, f"scale={w}:{h}:force_original_aspect_ratio=increase", f"crop={w}:{h}",
                              "format=gray") if x)
    r = subprocess.run([ov.FFMPEG, "-v", "error", *prima, "-i", src, "-vf", vf, "-fps_mode", "passthrough",
                        "-f", "rawvideo", "-"], capture_output=True, timeout=240)
    n = len(r.stdout) // (w * h)
    return [np.frombuffer(r.stdout[i * w * h:(i + 1) * w * h], dtype=np.uint8).reshape(h, w) for i in range(n)]


def _misure(g):
    """(luce media, contrasto, nitidezza) di un fotogramma grigio."""
    import cv2
    return float(g.mean()), float(g.std()), float(cv2.Laplacian(g, cv2.CV_32F).var())


@functools.lru_cache(maxsize=16)
def _tipico(src, firma):
    """(luce, contrasto, nitidezza) tipici della clip: la mediana sui fotogrammi chiave (ffmpeg decodifica solo quelli:
    veloce anche in 4K). None se sono meno di 3: allora contano solo nero e bianco."""
    import numpy as np
    m = [_misure(g) for g in _grigi(src, ["-skip_frame", "nokey"])]
    return tuple(float(x) for x in np.median(np.array(m), axis=0)) if len(m) >= 3 else None


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
    tmp = tempfile.mkdtemp()
    n = len(durate)
    cmd, catena, volti, mappe = [ov.FFMPEG, "-y", "-v", "error"], [], [], []
    dieci = nome.startswith("dieci") or nome in DIECI_NOMI
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
            if i == 0 and dieci:                   # 6/11/2026 (punto 14): primo secondo pulito (dieci, dieci_broll)
                inizio = _controlla_primo(c, inizio, 0.0, max(0.0, secondi - sorgente - 0.2), min(seg, PRIMO_S))
        # 29/10/2026 (Alessandro: "le scritte non devono mai coprire il viso"): volti di questo pezzo, gia' nel taglio
        # 9:16 del reel (prima qui il testo andava sempre in alto, anche sopra la faccia).
        # 6/11/2026: un fotogramma alla volta (stessi riquadri di prima) per sapere in quanti si vede il viso
        p = {"c": c, "inizio": inizio, "secondi": secondi, "hdr": hdr, "volti": [], "visi": 0, "mappa": None,
             "schiarisci": ""}
        try:
            fr = ov.extract_frames(c, sorgente, n=5 if controlla_viso else 3, start=inizio,
                                   vf=f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}")
            per = [ov.detect_faces([x], ruotati=dieci) for x in fr]
            p["volti"], p["visi"] = [b for x in per for b in x], sum(1 for x in per if x)
            p["mappa"] = ov.mappa_dettagli(fr)
            p["schiarisci"] = ov.schiarita(fr) if dieci else ""
        except Exception:
            pass
        pezzi.append(p)
    if dieci and n > 1 and not velocita and not indietro and PRIMO_CONTROLLO:
        try:           # 6/11/2026 (punti 13 e 14): per prima una scena col viso e il primo secondo pulito
            pezzi = _primo_pezzo(pezzi, durate)
        except Exception as e:
            print("Scelta della prima scena non riuscita, ordine di prima:", e)
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
        info["scene_dal_video"] = sum(1 for c, _ in piano if c == clips[0])
    if velocita and min(velocita) < 1:
        info["velocita"] = min(velocita)
    if dieci and CONTROLLO:      # 6/11/2026: cosa hanno cambiato i controlli del primo secondo e del viso (analisi 16/11)
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
    if ok0:            # pulita ma senza viso: le scene col viso, prima quelle dove si vede di piu'
        cand = sorted(altri_viso, key=lambda k: (-pezzi[k]["visi"], k))
    else:              # primo secondo sporco: le altre scene, prima quelle col viso
        cand = sorted(range(1, len(pezzi)), key=lambda k: (not ha_viso(pezzi[k]), -pezzi[k]["visi"], k))
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
