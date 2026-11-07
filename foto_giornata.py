"""
Reel con le foto della giornata (1/11/2026, richiesta di Alessandro): le foto dell'iPhone arrivano nella cartella Drive
"Foto della giornata", si sistemano come fa l'iPhone (luce, contrasto, colori, nitidezza) e diventano un reel da 10 s
con un movimento leggero, la musica e la scritta. Agli orari ORARIO_FOTO di pubblica.py, finche' ci sono foto.
Le foto arrivano anche dal bot Telegram (ricevi_telegram.py); quelle uscite vanno in "Foto usate".
6/11/2026 (Alessandro: "ogni giorno produco 10 video, 100 foto"): due formati a meta' negli orari delle foto,
"dieci_foto" (6 foto che scorrono piano) e "foto_rapide" (photo dump: 12-18 foto ferme, una a ogni colpo della musica);
senza foto nuove si riusano quelle di una giornata gia' uscita ("se non ci sono foto in coda... quelle vecchie").
"""
import datetime, math, os, shutil, subprocess, tempfile
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import formati_nuovi as fn
import overlay as ov
try:                         # 5/11/2026: le foto dell'iPhone arrivano in HEIC, che Pillow da solo non apre
    import pillow_heif
except ImportError:          # lavoro di GitHub partito prima dell'aggiornamento: si installa adesso (come parlato.py)
    import sys
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pillow-heif"], timeout=300)
    try:
        import pillow_heif
    except ImportError:
        pillow_heif = None
if pillow_heif:
    pillow_heif.register_heif_opener()

CARTELLA = "Foto della giornata"
USATE = "Foto usate"         # 5/11/2026: dove finiscono le foto gia' uscite in un reel
STILE = "virale"             # 6/11/2026: "virale" (scelto da me su sua delega), "caldo" (prima) o "flash" (scartato)
LATO_MINIMO = 700           # foto piu' piccole (miniature, screenshot ridotti) verrebbero sgranate nel reel
MINIMO, MASSIMO = 4, 6       # foto della stessa giornata in un reel
MARGINE = 1.08               # 8% in piu' della larghezza: lo spazio del movimento
LUCE = 0.46                  # luminosita' media a cui portare la foto
STACCO = 3                   # secondi minimi tra due foto dello stesso reel: delle raffiche se ne prende una sola
NITIDEZZA = 0.35             # sotto questa frazione della foto piu' nitida del gruppo la foto e' mossa e si scarta
# 6/11/2026 (Alessandro: "implementa come puoi migliorare le mie immagini"):
INCLINAZIONE = (1.0, 10.0)   # gradi: si raddrizzano solo le foto un po' storte (oltre 10 e' un'inquadratura voluta)
SIMILI = 8                   # differenza massima (su 64) tra le impronte di due foto quasi uguali: se ne tiene una
PELLE = 0.7                  # un "viso" con meno del 70% di pelle al centro e' un falso (pedana, dischi, scarpe:
                             # sulle foto di prova la pedana della pressa arriva al 60%, i visi veri a 76-87%)
RIDUZIONE = 0.9              # 6/11/2026 (revisione): sulle foto raddrizzate il taglio spostato per il viso puo'
                             # stringersi al massimo del 10% per restare dentro; se non basta la foto non si raddrizza
GANCIO = 0.65                # 6/11/2026 (revisione): la prima foto solo tra quelle nitide almeno al 65% della piu'
                             # nitida (la foto col dito davanti all'obiettivo vinceva per il viso grande)
# 6/11/2026 (Alessandro: "100 foto al giorno"; i 2 reel con 6 foto che scorrono del 5/11: 13 e 47 views su YouTube):
# foto_rapide, il "photo dump" a tempo di musica. Guide 2025: 0,5-1 s a foto e stacchi sul battito per i dump veloci
RAPIDE_MINIMO, RAPIDE_MASSIMO = 12, 18   # foto nuove della stessa giornata per un reel rapido / foto al massimo nel reel
RAPIDE_SCELTE = RAPIDE_MASSIMO + 8       # quante se ne scaricano (alcune si scartano: mosse, quasi-doppie, viso coperto)
RAPIDE_MINIMO_USO = 10                   # sotto 10 foto buone il reel rapido non si fa (esce dieci_foto, come prima)
RAPIDE_DURATA = (0.5, 0.8)               # secondi per foto: lo stacco cade sul colpo della musica in questo intervallo
RIUSO_GIORNI = 7                         # senza foto nuove: una giornata gia' uscita torna dopo almeno 7 giorni
# revisione 6/11/2026 (sera):
RAPIDE_MOMENTO = 10          # secondi: due scatti piu' vicini sono lo stesso momento, nel reel rapido ne resta uno...
RAPIDE_DIVERSE = 16          # ...salvo impronte diverse di almeno 16 bit (stessa posa nello stesso secondo: 10-11 bit)
SCENA = 15 * 60              # secondi: la nitidezza si confronta solo tra foto della stessa scena (un'auto liscia contro
                             # la palestra piena di dettagli sembrava mossa: 0,20 della piu' nitida)
RAPIDE_PASSO = (0.42, 0.95)  # secondi: il passo degli stacchi (1 o 2 battiti) anche un po' fuori da 0,5-0,8 s, cosi'
                             # anche i brani da 120-150 e da 60-75 BPM vanno a tempo (prima a 140 BPM: 47% sul battito)
RAPIDE_FIDUCIA = 0.1         # sotto questa fiducia il battito non e' chiaro: foto da 0,5-0,8 s sui colpi (come prima)
# 6/11/2026 (integrazione): pelle minima al centro dei riquadri dei rilevatori senza controlli (make_rapide): piu' bassa di
# PELLE (0,7, per il taglio) perche' qui un viso perso finirebbe sotto la scritta
RAPIDE_PELLE = 0.4
SERIE = 180                  # secondi: foto della stessa serie; solo una foto piu' nitida della serie la scarta per sempre


def _accelerometro(mn):
    """6/11/2026: il vettore di gravita' (x, y, z in g) che l'iPhone scrive nella MakerNote Apple (tag 0x0008,
    AccelerationVector): dice di quanto era storto il telefono nello scatto. None se manca."""
    import struct
    if not isinstance(mn, bytes) or not mn.startswith(b"Apple iOS") or len(mn) < 16:
        return None
    e = ">" if mn[12:14] == b"MM" else "<"
    for i in range(struct.unpack(e + "H", mn[14:16])[0]):
        o = 16 + 12 * i
        tag, tipo, n = struct.unpack(e + "HHI", mn[o:o + 8])
        if tag == 8 and tipo == 10 and n == 3:
            p = struct.unpack(e + "I", mn[o + 8:o + 12])[0]
            v = [struct.unpack(e + "ii", mn[p + 8 * k:p + 8 * k + 8]) for k in range(3)]
            return tuple(a / b if b else 0.0 for a, b in v)
    return None


def dati_scatto(im):
    """6/11/2026: (ISO, obiettivo, vettore di gravita') dall'EXIF della foto originale; (0, "", None) se mancano
    (es. foto compresse da Telegram)."""
    try:
        sub = im.getexif().get_ifd(0x8769)
        iso = sub.get(0x8827) or 0
        iso = int(iso[0] if isinstance(iso, (tuple, list)) else iso)
        return iso, str(sub.get(0xA434) or ""), _accelerometro(sub.get(0x927C))
    except Exception:
        return 0, "", None


def inclinazione(acc, obiettivo="", verticale=True):
    """6/11/2026: gradi di cui il telefono era storto (+ = girato in senso orario), SOLO quando e' sicuro: telefono
    fermo e in verticale, non puntato verso terra o cielo, fotocamera posteriore, angolo tra 1 e 10 gradi. Altrimenti 0."""
    if not acc or "front" in obiettivo.lower() or not verticale:
        return 0.0
    x, y, z = acc
    if not 0.85 <= math.sqrt(x * x + y * y + z * z) <= 1.15 or abs(z) > 0.7 or y > -0.5 or abs(x) > abs(y):
        return 0.0
    gradi = math.degrees(math.atan2(x, -y))
    return gradi if INCLINAZIONE[0] <= abs(gradi) <= INCLINAZIONE[1] else 0.0


def _dentro(x0, y0, w, h, W, H, rot):
    """True se il riquadro sta tutto dentro la foto girata di rot gradi con Image.rotate (niente angoli neri)."""
    c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    bordo = 2 + 0.005 * min(W, H)      # un filo di margine: il ricampionamento sfuma i pixel del bordo
    for px, py in ((x0, y0), (x0 + w, y0), (x0, y0 + h), (x0 + w, y0 + h)):
        u, v = px - W / 2, py - H / 2
        if abs(u * c - v * s) > W / 2 - bordo or abs(u * s + v * c) > H / 2 - bordo:
            return False
    return True


import cv2 as _cv2
_OCCHI = _cv2.CascadeClassifier(os.path.join(_cv2.data.haarcascades, "haarcascade_eye.xml"))   # gia' dentro OpenCV


def _occhio(im, g):
    """6/11/2026 (revisione): True se nella parte alta del viso g (frazioni, con i margini di detect_faces) c'e' almeno
    un occhio. Si cerca sul viso ritagliato dalla foto GRANDE e portato a 240 px: sulla miniatura da 720 px un viso a
    figura intera e' largo 40-80 px e l'occhio non si trovava mai (nessun viso nelle foto di prova, neanche frontale)."""
    import cv2, numpy as np
    x0, y0, x1, y1 = g[0] * im.width, g[1] * im.height, g[2] * im.width, g[3] * im.height
    if x1 - x0 < 24 or y1 - y0 < 24:
        return False
    alto = max(48, round((y1 - y0) * 240 / (x1 - x0)))
    r = cv2.equalizeHist(np.asarray(im.crop((int(x0), int(y0), int(x1), int(y1))).convert("L").resize((240, alto),
                                                                                                       Image.BILINEAR)))
    # tra il 15% e il 60% dell'altezza, dentro il viso vero (1/6 di margine per lato = 40 px su 240)
    return len(_OCCHI.detectMultiScale(r[int(alto * 0.15):int(alto * 0.6), 40:200], 1.1, 4,
                                       minSize=(20, 20), maxSize=(80, 80))) > 0


def visi_foto(im, ruotati=False, occhi=False, inclinati=False):
    """6/11/2026: i visi della foto [(x0, y0, x1, y1) in frazioni, con margine per capelli e mento], uniti quando
    piu' rilevatori trovano lo stesso viso; dal piu' grande al piu' piccolo. In palestra i rilevatori vedono "visi"
    anche nella pedana della pressa o nei dischi: si tengono solo quelli con abbastanza pelle al centro (PELLE) e,
    con occhi=True (per il taglio: meglio perdere un viso che spostare il taglio su un falso), con almeno un occhio
    (_occhio, cercato sulla foto grande: im va passata a piena grandezza).
    Revisione 6/11, inclinati=True (per il taglio): anche le teste inclinate di 25-45 gradi (sdraiato sulla pressa,
    foto 4702 e 4710: di dritto non si trovano e lo zoom della raddrizzatura le spingeva fuori). Si cercano sulla
    miniatura girata; il riquadro torna nella foto dritta come rettangolo che contiene il viso girato."""
    import cv2, numpy as np
    p = ImageOps.contain(im, (720, 720))
    veri = []
    for ang in ((0, 25, -25, 45, -45) if inclinati else (0,)):
        q = p.rotate(ang, resample=Image.BICUBIC, expand=True) if ang else p
        bgr = cv2.cvtColor(np.asarray(q), cv2.COLOR_RGB2BGR)
        ycc = cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb)
        pelle = (ycc[..., 0] > 40) & (ycc[..., 1] >= 135) & (ycc[..., 1] <= 180) & (ycc[..., 2] >= 80) & (ycc[..., 2] <= 135)
        gruppi = []
        for b in ov.detect_faces([bgr], ruotati=ruotati and not ang):
            b = (max(0.0, b[0]), max(0.0, b[1]), min(1.0, b[2]), min(1.0, b[3]))
            for i, g in enumerate(gruppi):
                if ov._overlap(g, b) > 0:
                    gruppi[i] = (min(g[0], b[0]), min(g[1], b[1]), max(g[2], b[2]), max(g[3], b[3]))
                    break
            else:
                gruppi.append(b)
        for g in gruppi:         # centro del riquadro (senza i margini per capelli e mento)
            x0, x1 = int((g[0] + (g[2] - g[0]) * 0.25) * q.width), int((g[2] - (g[2] - g[0]) * 0.25) * q.width)
            y0, y1 = int((g[1] + (g[3] - g[1]) * 0.3) * q.height), int((g[3] - (g[3] - g[1]) * 0.3) * q.height)
            if not (x1 > x0 and y1 > y0 and float(pelle[y0:y1, x0:x1].mean()) >= PELLE):
                continue
            faccia = (im, g)
            if ang:              # il viso torna nella foto dritta; l'occhio si cerca sul quadrato girato come q
                g, faccia = _raddrizza_viso(g, q, p, ang), _faccia_girata(im, g, q, p, ang)
            if any(ov._overlap(g, v) > 0 for v in veri):
                continue         # lo stesso viso, gia' trovato in un altro giro
            # almeno un occhio nella parte alta del viso (la pedana con le scarpe passa anche la prova della pelle)
            if not occhi or _OCCHI.empty() or _occhio(*faccia):
                veri.append(g)
    return sorted(veri, key=lambda g: -(g[2] - g[0]) * (g[3] - g[1]))


def _indietro(x, y, q, p, ang):
    """6/11/2026: un punto (pixel) della miniatura q girata di ang gradi (expand) -> frazioni della miniatura dritta p."""
    a = math.radians(ang)
    dx, dy = x - q.width / 2, y - q.height / 2
    return ((dx * math.cos(a) - dy * math.sin(a)) + p.width / 2) / p.width, \
           ((dx * math.sin(a) + dy * math.cos(a)) + p.height / 2) / p.height


def _raddrizza_viso(g, q, p, ang):
    """6/11/2026: il viso g trovato sulla miniatura girata -> riquadro nella foto dritta, con gli stessi margini di
    detect_faces intorno al rettangolo che contiene il viso vero girato (cosi' taglio() lo legge come gli altri)."""
    w, h = (g[2] - g[0]) * q.width, (g[3] - g[1]) * q.height
    x0, y0, x1, y1 = g[0] * q.width + w / 6, g[1] * q.height + h * 0.35 / 1.8, g[2] * q.width - w / 6, \
        g[3] * q.height - h * 0.45 / 1.8
    pts = [_indietro(x, y, q, p, ang) for x, y in ((x0, y0), (x1, y0), (x0, y1), (x1, y1))]
    tx0, tx1 = min(x for x, _ in pts), max(x for x, _ in pts)
    ty0, ty1 = min(y for _, y in pts), max(y for _, y in pts)
    fw, fh = tx1 - tx0, ty1 - ty0
    return (max(0.0, tx0 - 0.25 * fw), max(0.0, ty0 - 0.35 * fh), min(1.0, tx1 + 0.25 * fw), min(1.0, ty1 + 0.45 * fh))


def _faccia_girata(im, g, q, p, ang):
    """6/11/2026: (immagine, riquadro) per _occhio di un viso inclinato: un quadrato della foto grande intorno al viso,
    girato come la miniatura (il viso torna dritto), col riquadro del viso al centro."""
    s = im.width / p.width
    cx, cy = _indietro((g[0] + g[2]) / 2 * q.width, (g[1] + g[3]) / 2 * q.height, q, p, ang)
    bw, bh = (g[2] - g[0]) * q.width * s, (g[3] - g[1]) * q.height * s
    lato = math.hypot(bw, bh) + 4
    cx, cy = cx * im.width, cy * im.height
    sq = im.crop((int(cx - lato / 2), int(cy - lato / 2), int(cx + lato / 2), int(cy + lato / 2)))
    sq = sq.rotate(ang, resample=Image.BILINEAR)
    return sq, (0.5 - bw / 2 / sq.width, 0.5 - bh / 2 / sq.height, 0.5 + bw / 2 / sq.width, 0.5 + bh / 2 / sq.height)


def taglio(W, H, rot, visi, margine=None):
    """6/11/2026: il riquadro 9:16 (+ MARGINE per il movimento) da prendere dalla foto. Si parte dal taglio di prima
    (centro, un filo in alto); solo se quel taglio tagliasse un viso (foto orizzontali, viso vicino al bordo) si sposta
    quanto basta per prenderlo intero, capelli e mento compresi. Mai angoli neri se la foto e' stata raddrizzata.
    Un viso "falso" (macchine della palestra) che sta dentro il taglio di prima non sposta niente.
    Revisione 6/11: il viso deve stare nella fascia che si vede SEMPRE durante lo scorrimento (tra 1-1/MARGINE e
    1/MARGINE del riquadro: a un capo dello scorrimento la nuca usciva); sulle foto raddrizzate si parte dal centro
    esatto (il riquadro piu' grande sta dentro solo li') e il riquadro spostato si stringe quanto basta per restare
    dentro (al massimo RIDUZIONE). -> (x0, y0, w, h, intero); intero=False se il viso vero resta tagliato.
    margine: 1.0 per le foto ferme di foto_rapide (niente scorrimento: il viso basta che stia nel riquadro)."""
    r, k = 9 / 16 * (margine or MARGINE), 1 / (margine or MARGINE)
    h = min(H, W / r)
    if rot:                  # foto raddrizzata: il riquadro piu' grande che sta tutto dentro (al centro esatto)
        lo, hi = 0.0, h
        for _ in range(30):
            m = (lo + hi) / 2
            lo, hi = (m, hi) if _dentro((W - m * r) / 2, (H - m) / 2, m * r, m, W, H, rot) else (lo, m)
        h = lo
    a = vero = None
    if visi:
        a = visi[0]          # il viso piu' grande, insieme agli altri visi grandi se ci stanno (foto di gruppo)
        for v in visi[1:]:
            u = (min(a[0], v[0]), min(a[1], v[1]), max(a[2], v[2]), max(a[3], v[3]))
            if (v[2] - v[0]) * (v[3] - v[1]) >= 0.3 * (visi[0][2] - visi[0][0]) * (visi[0][3] - visi[0][1]) \
                    and (u[2] - u[0]) * W <= 0.9 * h * r * (2 * k - 1):
                a = u
        a = (a[0] * W, a[1] * H, a[2] * W, a[3] * H)
        # il viso vero (senza i margini di detect_faces: 1/6 della larghezza per lato, capelli 0.35/1.8, mento 0.45/1.8)
        vero = (a[0] + (a[2] - a[0]) / 6, a[1] + (a[3] - a[1]) * 0.35 / 1.8,
                a[2] - (a[2] - a[0]) / 6, a[3] - (a[3] - a[1]) * 0.45 / 1.8)

    def posto(h):
        """dove va il riquadro alto h: il taglio di prima, spostato quanto basta se taglierebbe il viso vero"""
        w = h * r
        x0, y0 = (W - w) / 2, (H - h) * (0.5 if rot else 0.45)
        if vero:
            f0, f1 = w * (1 - k), w * k        # la fascia sempre in vista, misurata dal bordo sinistro del riquadro
            if vero[0] < x0 + f0 or vero[2] > x0 + f1:      # capelli e orecchie dentro se ci stanno, se no il viso al centro
                x0 = min(max(x0, a[2] - f1), a[0] - f0) if a[2] - a[0] <= f1 - f0 else (vero[0] + vero[2] - w) / 2
            if vero[1] < y0 or vero[3] > y0 + h:
                y0 = min(max(y0, a[3] - h), a[1]) if a[3] - a[1] <= h else (vero[1] + vero[3] - h) / 2
        return min(max(x0, 0.0), W - w), min(max(y0, 0.0), H - h)

    x0, y0 = posto(h)
    if rot and not _dentro(x0, y0, h * r, h, W, H, rot):
        lo, hi = h * RIDUZIONE, h      # spostato per il viso: il riquadro piu' grande che sta dentro in quel punto
        if _dentro(*posto(lo), lo * r, lo, W, H, rot):
            for _ in range(20):
                m = (lo + hi) / 2
                lo, hi = (m, hi) if _dentro(*posto(m), m * r, m, W, H, rot) else (lo, m)
            h = lo
            x0, y0 = posto(h)
        else:                # non basta: verso il centro esatto (dentro per costruzione) quanto serve per restare dentro
            cx, cy = (W - h * r) / 2, (H - h) / 2
            lo, hi = 0.0, 1.0
            for _ in range(20):
                m = (lo + hi) / 2
                lo, hi = (lo, m) if _dentro(x0 + (cx - x0) * m, y0 + (cy - y0) * m, h * r, h, W, H, rot) else (m, hi)
            x0, y0 = x0 + (cx - x0) * hi, y0 + (cy - y0) * hi
    w = h * r
    intero = not vero or (x0 + w * (1 - k) - 1 <= vero[0] and vero[2] <= x0 + w * k + 1
                          and y0 - 1 <= vero[1] and vero[3] <= y0 + h + 1)
    return x0, y0, w, h, intero


def pulisci(im, iso, luce):
    """6/11/2026: foto buie o ad alti ISO (sera, macchina, locali): via la grana colorata e un filo di quella di luce,
    PRIMA che chiarezza e nitidezza la facciano risaltare. Leggera e veloce anche in 4K; le foto chiare restano uguali."""
    if iso < 640 and luce >= 0.22:
        return im
    import cv2, numpy as np
    a = cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2YCrCb)
    k = max(3, int(im.width * 0.004) | 1)                 # ~9 px in 4K
    for c in (1, 2):
        a[..., c] = cv2.GaussianBlur(a[..., c], (k, k), 0)
    if iso >= 1250 or luce < 0.15:
        a[..., 0] = cv2.bilateralFilter(a[..., 0], 5, 12, 3)
    return Image.fromarray(cv2.cvtColor(a, cv2.COLOR_YCrCb2RGB))


def prepara(src, margine=None):
    """6/11/2026: foto -> immagine 9:16 (+ MARGINE) raddrizzata, tagliata sul viso e ripulita. Restituisce
    (immagine, info) con info = {"gradi", "visi" (nel taglio), "verso" (1/0 o None), "iso"}. Se qualcosa va storto:
    il taglio di prima (centro, un filo in alto), cosi' il reel esce sempre. margine=1.0: 9:16 esatto (foto ferme)."""
    W, H = ov.LATO_USCITA, int(ov.LATO_USCITA * 16 / 9)
    margine = margine or MARGINE
    orig = Image.open(src)
    iso, obiettivo, acc = dati_scatto(orig)
    im = base = ImageOps.exif_transpose(orig).convert("RGB")
    info = {"gradi": 0.0, "visi": [], "verso": None, "iso": iso}
    try:
        gradi = inclinazione(acc, obiettivo, im.height > im.width)
        if gradi:
            im = im.rotate(-gradi, resample=Image.BICUBIC)
        # solo visi con un occhio: la pedana della pressa con le scarpe sembra un viso (anche per la pelle);
        # revisione 6/11: anche le teste inclinate (sdraiato sulle macchine), mai quelle girate di 90 gradi
        visi = visi_foto(im, ruotati=False, occhi=True, inclinati=True)
        x0, y0, w, h, intero = taglio(im.width, im.height, -gradi, visi, margine)
        if gradi and not intero:     # revisione 6/11: meglio storta di qualche grado che con la testa tagliata
            visi0 = visi_foto(base, ruotati=False, occhi=True, inclinati=True)
            if visi0:
                print(f"Foto: raddrizzata di {gradi:.1f} gradi taglierebbe il viso, resta com'e'")
                gradi, im, visi = 0.0, base, visi0
                x0, y0, w, h, intero = taglio(im.width, im.height, 0.0, visi, margine)
        tagliata = im.resize((int(W * margine), H), Image.LANCZOS, box=(x0, y0, x0 + w, y0 + h))
        info.update(gradi=round(gradi, 1), visi=[((a - x0 / im.width) * im.width / w, (b - y0 / im.height) * im.height / h,
                                                  (c - x0 / im.width) * im.width / w, (d - y0 / im.height) * im.height / h)
                                                 for a, b, c, d in visi])
        if info["visi"]:     # il movimento porta il viso verso il centro, non verso il bordo
            centro = (info["visi"][0][0] + info["visi"][0][2]) / 2
            info["verso"] = None if abs(centro - 0.5) < 0.03 else int(centro > 0.5)
        im = tagliata
    except Exception as e:
        print("Foto: taglio sul viso non riuscito, taglio al centro:", e)
        info.update(gradi=0.0, visi=[], verso=None)
        im = ImageOps.fit(base, (int(W * margine), H), Image.LANCZOS, centering=(0.5, 0.45))
    return im, info


def migliora(src, dst, margine=None):
    """Sistemazione automatica: esposizione, contrasto, saturazione, tono un po' caldo, nitidezza. Taglio 9:16.
    6/11/2026: raddrizzata, tagliata sul viso e ripulita dalla grana (prepara); restituisce le info del taglio."""
    im, info = prepara(src, margine)
    media = sum(ImageOps.grayscale(im).resize((64, 64)).getdata()) / (64 * 64 * 255)
    gamma = max(0.75, min(1.25, math.log(LUCE) / math.log(max(media, 0.02))))
    if getattr(ov, "STILE_CENTRO", False):
        # 7/11/2026 (Alessandro: "da oggi le foto le faro' tutte con il filtro drammatico"): mai schiarire, la sua luce
        # scura resta; le foto troppo chiare le scurisce poi il montaggio sotto la frase al centro
        gamma = max(1.0, gamma)
    tabella = [round(255 * (i / 255) ** gamma) for i in range(256)]
    try:
        im = pulisci(im, info["iso"], media)
    except Exception as e:
        print("Foto: pulizia della grana non riuscita:", e)
    im = im.point(tabella * 3)
    im = ImageOps.autocontrast(im, cutoff=0.5, preserve_tone=True)
    if STILE == "flash":
        flash(im).save(dst, quality=96)
        return info
    if STILE == "virale":
        virale(im).save(dst, quality=96)
        return info
    # stile delle foto che piacciono ad Alessandro: caldo e morbido, luci basse, ombre piene, colori naturali (non saturi)
    im = im.point([round(255 * ((i / 255) - 0.10 * max(0.0, (i / 255) - 0.7) / 0.3)) for i in range(256)] * 3)
    im = ImageEnhance.Contrast(im).enhance(1.04)
    r, g, b = im.split()
    im = Image.merge("RGB", (r.point(lambda v: min(255, int(v * 1.03))), g, b.point(lambda v: int(v * 0.95))))
    im = im.filter(ImageFilter.UnsharpMask(radius=2, percent=40, threshold=3))
    im.save(dst, quality=96)
    return info


def virale(im):
    """6/11/2026 (Alessandro: il Flash di Instagram costa 55 euro al mese, "editami tu le foto... in base a come secondo
    te possono andare virali"): foto nitide e "piene" come i profili lifestyle che girano di piu'. Chiarezza (contrasto
    locale), colori vivi ma pelle naturale, luce leggermente calda, bordi un filo piu' scuri (la scritta si legge
    meglio), nitidezza fine e un velo di grana."""
    import numpy as np
    im = im.filter(ImageFilter.UnsharpMask(radius=40, percent=22, threshold=0))          # chiarezza
    a = np.asarray(im).astype(np.float32) / 255
    a = a * a * (3 - 2 * a) * 0.35 + a * 0.65                                            # curva a S leggera
    grigio = a.mean(axis=2, keepdims=True)
    sat = a.max(axis=2, keepdims=True) - a.min(axis=2, keepdims=True)
    r, g, b = a[..., 0:1], a[..., 1:2], a[..., 2:3]
    pelle = ((r > g) & (g > b) & (r - b > 0.06)).astype(np.float32)                     # la pelle si spinge meno
    spinta = (0.30 * (1 - sat) ** 2) * (1 - 0.6 * pelle)                                 # vivacita'
    a = grigio + (a - grigio) * (1 + spinta)
    a *= np.array([1.025, 1.0, 0.965], dtype=np.float32)                                 # un po' caldo
    H, W = a.shape[:2]
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = ((xx / W - 0.5) ** 2 + (yy / H - 0.47) ** 2) / 0.5
    a *= (1 - 0.16 * np.clip(d, 0, 1) ** 1.5)[..., None]                                 # vignettatura morbida
    a += np.random.default_rng(7).normal(0, 0.007, (H, W, 1)).astype(np.float32)         # grana leggera
    im = Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8))
    return im.filter(ImageFilter.UnsharpMask(radius=1.3, percent=70, threshold=2))       # nitidezza fine


def centro_luce(im):
    """Dove "cade" il flash: sul viso piu' grande (e un po' sotto, sul corpo); se non c'e' un viso, al centro."""
    import cv2, numpy as np
    g = np.asarray(ImageOps.grayscale(im).resize((im.width // 4, im.height // 4)))
    visi = []
    for c in ov._casc:
        visi += [tuple(v) for v in c.detectMultiScale(g, 1.1, 5, minSize=(20, 20))]
    if not visi:
        return 0.5, 0.45, 0.0
    x, y, w, h = max(visi, key=lambda v: v[2] * v[3])
    return (x + w / 2) / g.shape[1], (y + h * 1.5) / g.shape[0], w / g.shape[1]


def flash(im):
    """5/11/2026, richiesta di Alessandro: l'effetto "Flash" di Instagram (flash diretto della fotocamera), rifatto qui
    SENZA AI (il filtro di Instagram rigenera la foto e a volte cambia il viso; e via API non si puo' usare): soggetto
    illuminato e pelle chiara, sfondo che cade nel buio, luce bianca neutra (niente giallo della palestra), contrasto
    duro, un filo di grana. Il video e' lo stesso su tutti i social, quindi l'effetto arriva ovunque."""
    import numpy as np
    a = np.asarray(im).astype(np.float32) / 255.0
    H, W = a.shape[:2]
    cx, cy, lw = centro_luce(im)
    yy, xx = np.mgrid[0:H, 0:W]
    sx, sy = W * max(0.34, lw * 2.0), H * 0.30        # ellisse di luce piu' alta che larga (persona in piedi/seduta)
    luce = np.exp(-(((xx - cx * W) / sx) ** 2 + ((yy - cy * H) / sy) ** 2) / 2)[..., None]
    a = a * (0.28 + 1.15 * luce)                        # soggetto +40%, bordi -70%: lo sfondo cade nel buio
    grigio = a.mean(axis=2, keepdims=True)
    a = grigio + (a - grigio) * (0.65 + 0.25 * luce)    # colori spenti, soprattutto sullo sfondo
    a = a * np.array([0.94, 0.99, 1.08], np.float32)    # bianco freddo del flash (via il giallo delle luci)
    a = np.clip(a, 0, 1)
    for _ in range(2):                                  # curva a S doppia: neri pieni, luci che "bruciano" sulla pelle
        a = a * a * (3 - 2 * a) * 0.7 + a * 0.3
    a = np.clip(a * 1.12, 0, 1)
    rng = np.random.default_rng(7)
    a = np.clip(a + rng.normal(0, 0.018, a.shape[:2])[..., None].astype(np.float32), 0, 1)   # grana
    out = Image.fromarray((a * 255 + 0.5).astype(np.uint8))
    return out.filter(ImageFilter.UnsharpMask(radius=1.5, percent=60, threshold=2))


def in_clip(img, dst, secondi, verso):
    """Foto -> clip con uno scorrimento leggero (verso 1: a destra, 0: a sinistra).
    6/11/2026: la clip porta la data di oggi (creation_time): cosi' il montaggio (ov.luce_sua) non ci rimette sopra
    LOOK e schiarita, e il reel ha la stessa luce delle foto "virale" che Alessandro ha approvato (prima erano
    lavorate due volte: piu' scure e con doppia vignettatura)."""
    import datetime as dt
    W, H = ov.LATO_USCITA, int(ov.LATO_USCITA * 16 / 9)
    x = f"(iw-{W})*t/{secondi:.2f}" if verso else f"(iw-{W})*(1-t/{secondi:.2f})"
    adesso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000000Z")
    subprocess.run([ov.FFMPEG, "-y", "-v", "error", "-loop", "1", "-framerate", str(ov.FPS_MULTI), "-t", f"{secondi:.2f}",
                    "-i", img, "-vf", f"crop={W}:{H}:'{x}':0,format=yuv420p", "-c:v", "libx264", "-preset", "ultrafast",
                    "-crf", "16", "-metadata", f"creation_time={adesso}", dst], check=True, timeout=ov.TEMPO_MAX_MONTAGGIO)


def make_foto(foto, frase, dst, musiche=()):
    """Reel da 10 s: le foto una dopo l'altra, frase intera dal primo fotogramma, stacchi sul colpo della musica."""
    tmp = tempfile.mkdtemp()
    try:
        durate = [round(10.0 / len(foto), 3)] * len(foto)
        if musiche and os.path.exists(musiche[0]):
            durate = fn.tagli_a_tempo(musiche[0], durate)
        clips, area = [], []
        for i, (f, d) in enumerate(zip(foto, durate)):
            img, clip = os.path.join(tmp, f"f{i}.jpg"), os.path.join(tmp, f"c{i}.mp4")
            info = migliora(f, img) or {}
            # 6/11/2026: il movimento porta il viso verso il centro (prima: a destra e a sinistra alternati)
            in_clip(img, clip, d + 1.0, i % 2 if info.get("verso") is None else info["verso"])
            clips.append(clip)
            area.append(sum((v[2] - v[0]) * (v[3] - v[1]) for v in info.get("visi", [])))
        # la scritta resta ferma per 10 s: se copre un viso si riprova con meno foto, altrimenti esce comunque nel punto migliore.
        # 6/11/2026: si tolgono prima le foto coi visi piu' grandi (prima le ultime); la prima, il gancio, resta sempre
        via = sorted(range(1, len(clips)), key=lambda i: -area[i])
        for n in range(len(clips), 2, -1):
            fn.CONTROLLO.clear()     # 6/11/2026 (revisione): niente dati di un tentativo scartato nel montaggio
            try:
                tenute = sorted(set(range(len(clips))) - set(via[:len(clips) - n]))
                d = durate if n == len(clips) else [round(10.0 / n, 3)] * n     # 6/11: stacchi a tempo anche qui
                return fn.make_sequenza([clips[i] for i in tenute], d, [(0.0, 10.0, frase)], dst, musiche, None,
                                        "dieci_foto", True)
            except fn.VisoCoperto:
                pass
        fn.CONTROLLO.clear()
        return fn.make_sequenza(clips, durate, [(0.0, 10.0, frase)], dst, musiche, None, "dieci_foto")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def ritmo(musica, secondi=10.0):
    """6/11/2026 (foto_rapide): i colpi del brano. -> (forza, battito, fase, fiducia): forza = quanto "colpisce" la
    musica in ogni centesimo di secondo (flusso spettrale, 0-1); battito = secondi tra due battiti (autocorrelazione,
    preferenza intorno a 120 BPM); fase = secondi del primo battito; fiducia = 0-1 (quanto il battito e' regolare)."""
    import numpy as np
    sr, hop, nfft = 12000, 120, 1024                        # 100 analisi al secondo
    pcm = subprocess.run([ov.FFMPEG, "-v", "error", "-i", musica, "-t", f"{secondi + 0.5:.2f}", "-ac", "1",
                          "-ar", str(sr), "-f", "s16le", "-"], capture_output=True, timeout=60).stdout
    x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768
    if len(x) < sr * 2:
        raise ValueError("brano troppo corto o illeggibile")
    x = np.pad(x, nfft // 2)                                # finestre centrate: l'analisi i e' l'istante i/100 s
    fr = np.lib.stride_tricks.sliding_window_view(x, nfft)[::hop] * np.hanning(nfft).astype(np.float32)
    spettro = np.log1p(100 * np.abs(np.fft.rfft(fr, axis=1)))
    flusso = np.maximum(np.diff(spettro, axis=0, prepend=spettro[:1]), 0).sum(axis=1)
    forza = np.maximum(flusso - np.convolve(flusso, np.ones(31) / 31, mode="same"), 0)    # meno la media di 0,3 s
    forza /= forza.max() or 1.0
    e = forza - forza.mean()
    ac = np.correlate(e, e, "full")[len(e) - 1:]
    passi = np.arange(25, 101)                              # battiti da 0,25 a 1 s (240-60 BPM)
    L = int(passi[np.argmax(ac[passi] * np.exp(-0.5 * np.log2(passi / 50.0) ** 2))])
    a, b, c = ac[L - 1], ac[L], ac[L + 1]
    periodo = L + (0.5 * (a - c) / (a - 2 * b + c) if a - 2 * b + c < 0 else 0.0)    # vertice della parabola
    fiducia = float(max(0.0, b / ac[0])) if ac[0] > 0 else 0.0
    fasi = np.arange(0, periodo, 1.0)
    somme = [forza[np.round(np.arange(f, len(forza) - 1, periodo)).astype(int)].sum() for f in fasi]
    return forza, periodo / 100, float(fasi[int(np.argmax(somme))]) / 100, fiducia


def _sul_passo(colpo, griglia, passo, m, T, primo=0.75):
    """Revisione 6/11/2026 (sera): gli stacchi di m foto SOLO sui punti della griglia (fotogrammi dei battiti), ogni foto
    di 1 o 2 passi, mai 1,5 (con un battito e mezzo meta' degli stacchi cadeva sul controtempo e il montaggio
    "zoppicava"). La prima foto da `primo` a 2,5 passi, l'ultima da 0,75 a 2,5, meglio 2; tra i punti si preferiscono
    i colpi piu' forti del brano. passo in fotogrammi. -> fotogrammi dei tagli (0 e T compresi) o None se non ci stanno."""
    G = len(griglia)
    if m < 2 or G == 0:
        return None
    lo, hi, due = max(0.75 * passo, RAPIDE_PASSO[0] * ov.FPS_MULTI), 2.5 * passo, 1.5 * passo
    NEG = -1e18
    best = [[NEG] * G for _ in range(m)]        # best[k][j]: k stacchi, l'ultimo sul punto j
    da = [[-1] * G for _ in range(m)]
    for j, c in enumerate(griglia):
        if max(lo, primo * passo) <= c <= hi:
            best[1][j] = colpo[c] + (0.5 if c >= due else 0.0)
    for k in range(2, m):
        for j in range(G):
            for s in (1, 2):
                if j >= s and best[k - 1][j - s] > NEG / 2 and best[k - 1][j - s] + colpo[griglia[j]] > best[k][j]:
                    best[k][j], da[k][j] = best[k - 1][j - s] + colpo[griglia[j]], j - s
    fine = [(best[m - 1][j] + (0.5 if T - c >= due else 0.0), j) for j, c in enumerate(griglia)
            if best[m - 1][j] > NEG / 2 and lo <= T - c <= hi]
    if not fine:
        return None
    j, tagli = max(fine)[1], [T]
    for k in range(m - 1, 0, -1):
        tagli.append(griglia[j])
        j = da[k][j]
    return [0] + tagli[::-1]


def tempi_rapide(musica, n, durata=10.0):
    """6/11/2026 (foto_rapide): quanto dura ogni foto (secondi, a fotogrammi interi), con gli stacchi a tempo.
    Revisione 6/11 (sera): con un battito chiaro (fiducia >= RAPIDE_FIDUCIA) gli stacchi cadono SOLO sui battiti: passo
    di 1 o 2 battiti (o mezzo battito sotto i 63 BPM) tra 0,42 e 0,95 s, ogni foto 1 o 2 passi, il gancio e l'ultima
    meglio 2, il piu' possibile foto (al massimo n e RAPIDE_MASSIMO); prima a 120-150 BPM nessun passo stava in 0,5-0,8 s
    e gli stacchi finivano a caso (mediana 73% sul battito, 26 brani su 108 sotto il 50%). Battito poco chiaro: come
    prima, foto da 0,5-0,8 s sui colpi piu' forti. -> (durate, ritmo). Senza musica o se l'analisi non riesce: uguali."""
    import numpy as np
    fps = ov.FPS_MULTI
    T = int(round(durata * fps))
    dmin, dmax = int(round(RAPIDE_DURATA[0] * fps)), int(round(RAPIDE_DURATA[1] * fps))
    try:
        if not musica or not os.path.exists(musica):
            raise ValueError("nessun brano")
        forza, battito, fase, fiducia = ritmo(musica, durata)
        t = np.arange(T + 1) / fps
        i = np.clip(np.round(t * 100).astype(int), 1, len(forza) - 2)
        colpo = np.maximum(np.maximum(forza[i - 1], forza[i]), forza[i + 1])      # il colpo piu' vicino (+-10 ms)
        colpo[T] = 0.0
        tagli, passo = None, None
        if fiducia >= RAPIDE_FIDUCIA:
            passi = [p for p in (battito, 2 * battito) if RAPIDE_PASSO[0] <= p <= RAPIDE_PASSO[1]] or \
                    [p for p in (battito / 2,) if RAPIDE_PASSO[0] <= p <= RAPIDE_PASSO[1]]
            for passo in sorted(passi, key=lambda p: abs(p - 0.62)):
                # punti della griglia: ogni passo; per 2 battiti la meta' dei battiti che colpisce di piu'
                fasi = [fase, fase + battito] if passo > 1.5 * battito else [fase]
                punti = lambda f: [k for k in np.arange(f % passo, durata, passo) * fps if 1 <= round(k) < T]
                f0 = max(fasi, key=lambda f: sum(float(colpo[int(round(k))]) for k in punti(f)))
                # ogni punto sul colpo piu' forte entro un fotogramma (16 ms): il battito stimato scivola di poco
                griglia = sorted({int(round(k)) + int(np.argmax(colpo[int(round(k)) - 1:int(round(k)) + 2])) - 1
                                  for k in punti(f0) if 2 <= round(k) < T - 1})
                # il piu' possibile foto, col gancio di almeno un battito e mezzo (una foto in meno, se serve); se no
                # anche il gancio corto
                for primo in (1.5, 0.75):
                    for m in range(int(min(n, RAPIDE_MASSIMO)), 1, -1):
                        tagli = _sul_passo(colpo, griglia, passo * fps, m, T, primo)
                        if tagli:
                            break
                    if tagli:
                        break
                if tagli:
                    break
        if not tagli:            # battito poco chiaro (o nessun passo possibile): foto da 0,5-0,8 s sui colpi (come prima)
            passo = None
            m = int(max(1, min(n, RAPIDE_MASSIMO, max(math.ceil(durata / RAPIDE_DURATA[1]), round(durata / 0.62)))))
            if m * dmax < T:                                  # poche foto: ognuna un po' piu' lunga
                dmax = math.ceil(T / m) + 6
            NEG = -1e18
            best = np.full((m + 1, T + 1), NEG)
            best[0, 0] = 0.0
            da = np.zeros((m + 1, T + 1), dtype=np.int32)
            for k in range(1, m + 1):    # best[k, t]: k foto, l'ultima finisce al fotogramma t
                for d in range(dmin, dmax + 1):
                    cand = np.full(T + 1, NEG)
                    cand[d:] = best[k - 1, :T + 1 - d]
                    meglio = cand > best[k]
                    best[k, meglio], da[k, meglio] = cand[meglio], d
                best[k] += colpo
            if best[m, T] < NEG / 2:
                raise ValueError(f"{m} foto non stanno in {durata} s")
            tagli = [T]
            for k in range(m, 0, -1):
                tagli.append(tagli[-1] - int(da[k, tagli[-1]]))
            tagli = tagli[::-1]
        if tagli[0] != 0 or tagli[-1] != T or min(np.diff(tagli)) < 1:
            raise ValueError("stacchi non ricostruiti")
        stacchi = [c / fps for c in tagli[1:-1]]
        q = lambda s, div: abs((s - fase) / (battito / div) - round((s - fase) / (battito / div))) * battito / div
        pieni = [q(s, 1) <= 0.025 for s in stacchi]
        quota = lambda xs: round(float(sum(xs)) / max(1, len(stacchi)), 2)
        ritmo_info = {"bpm": int(round(60 / battito)), "fiducia": round(float(fiducia), 2),
                      "passo": round(float(passo), 3) if passo else None,   # secondi; None: sui colpi (0,5-0,8 s)
                      # quota di stacchi entro 25 ms da un battito pieno / da un mezzo battito (non pieno, a parte:
                      # revisione 6/11, prima contavano insieme e il dato era gonfiato) / da un colpo forte del brano
                      "sul_battito": quota(pieni),
                      "sul_mezzo": quota(q(s, 2) <= 0.025 and not p for s, p in zip(stacchi, pieni)),
                      "sul_colpo": quota(float(forza[max(0, round(s * 100) - 2):round(s * 100) + 3].max()) >= 0.3
                                         for s in stacchi)}
    except Exception as e:
        print("Foto rapide: ritmo del brano non letto, foto tutte uguali:", str(e)[:200])
        m = int(max(1, min(n, 16)))
        tagli = [round(k * T / m) for k in range(m + 1)]
        ritmo_info = {}
    return [round((b - a) / fps, 6) for a, b in zip(tagli, tagli[1:])], ritmo_info


def _pelle(bgr, g):
    """6/11/2026 (integrazione): quota di pelle al centro del riquadro g (frazioni, con i margini di detect_faces) sulla
    miniatura bgr, con la stessa regola di visi_foto. Se non si misura, 1.0 (il riquadro resta: mai un viso perso)."""
    try:
        import cv2
        h, w = bgr.shape[:2]
        g = (max(0.0, g[0]), max(0.0, g[1]), min(1.0, g[2]), min(1.0, g[3]))
        ycc = cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb)
        pelle = ((ycc[..., 0] > 40) & (ycc[..., 1] >= 135) & (ycc[..., 1] <= 180) & (ycc[..., 2] >= 80)
                 & (ycc[..., 2] <= 135))
        x0, x1 = int((g[0] + (g[2] - g[0]) * 0.25) * w), int((g[2] - (g[2] - g[0]) * 0.25) * w)
        y0, y1 = int((g[1] + (g[3] - g[1]) * 0.3) * h), int((g[3] - (g[3] - g[1]) * 0.3) * h)
        return float(pelle[y0:y1, x0:x1].mean()) if x1 > x0 and y1 > y0 else 1.0
    except Exception:
        return 1.0


def _vero(f):
    """Il viso senza i margini di detect_faces (capelli 0.35/1.8, mento 0.45/1.8, 1/6 della larghezza per lato)."""
    w, h = f[2] - f[0], f[3] - f[1]
    return f[0] + w / 6, f[1] + h * 0.35 / 1.8, f[2] - w / 6, f[3] - h * 0.45 / 1.8


def _testo_libero(W, H, frase, visi, mappa, ganci=(0,)):
    """6/11/2026 (foto_rapide): la frase ferma per 10 s in un posto libero su TUTTE le foto (Alessandro: mai sul viso).
    Si prova con tutte; se una foto resterebbe col viso coperto si toglie (prima quella coperta di piu') e si riprova.
    Il gancio (la prima foto) non si toglie mai: i suoi visi pesano 20 volte tanto; se resta coperto lo stesso, si
    prova come gancio la foto dopo in ganci (in ordine di voto). -> (scritta, indici delle foto nell'ordine del reel)
    6/11/2026 (integrazione): il VisoCoperto finale ha viso_gancio = True se la scritta copriva il viso del PRIMO gancio
    (la foto che anche make_foto metterebbe per prima): allora monta_rapide non ripiega su make_foto."""
    if getattr(ov, "STILE_CENTRO", False):
        # 7/11/2026 (Alessandro: "testo al centro anche se copre il viso"): la frase al centro su tutte le foto, nessuna
        # foto tolta per il viso; l'ordine e' quello del primo gancio
        img, _, _ = ov.build_testo_giallo(W, H, frase, [], mappa)
        g = list(ganci)[0] if ganci else 0
        return img, [g] + [i for i in range(len(visi)) if i != g]
    viso_gancio = False
    for k, g in enumerate(list(ganci)[:3]):
        ordine = [g] + [i for i in range(len(visi)) if i != g]
        while len(ordine) >= min(RAPIDE_MINIMO_USO, len(visi)):
            facce = visi[ordine[0]] * 20 + [f for i in ordine[1:] for f in visi[i]]
            img, _, _ = ov.build_testo_giallo(W, H, frase, facce, mappa)
            b = img.getbbox() or (0, 0, 0, 0)
            box = (b[0] / W, b[1] / H, b[2] / W, b[3] / H)
            coperte = {i: c for i in ordine if (c := sum(ov._overlap(box, _vero(f)) for f in visi[i])) > 0}
            if ordine[0] in coperte:
                viso_gancio = viso_gancio or k == 0
                break                # il viso del gancio resta sotto la scritta: si prova un altro gancio
            if not coperte:
                return img, ordine
            del ordine[ordine.index(max(coperte, key=coperte.get))]
    e = fn.VisoCoperto(frase)
    e.viso_gancio = viso_gancio
    raise e


def make_rapide(foto, frase, dst, musiche=(), ganci=(0,)):
    """6/11/2026 (Alessandro: "ogni giorno produco 10 video, 100 foto"): reel "foto_rapide", un photo dump da 10 s.
    Le foto della giornata FERME (niente scorrimento ne' zoom), 0,5-0,8 s l'una con lo stacco sul colpo della musica
    (tempi_rapide): la prima e' il gancio, le altre in ordine di scatto. Stessa sistemazione delle foto di dieci_foto
    (migliora: dritta, taglio sul viso, stile "virale"). La frase ferma dal primo fotogramma in un posto libero su
    tutte le foto (_testo_libero). foto: percorsi, il gancio per primo. -> info, con "tenute" = indici delle foto
    uscite nel reel, nell'ordine del reel."""
    import cv2, numpy as np
    W, H = ov.LATO_USCITA, int(ov.LATO_USCITA * 16 / 9)
    fps = ov.FPS_MULTI
    tmp = tempfile.mkdtemp()
    try:
        visi, piccole, luci = [], [], {}
        for i, f in enumerate(foto):
            p = os.path.join(tmp, f"r{i}.jpg")
            info = migliora(f, p, margine=1.0) or {}           # 9:16 esatto: nessuno spazio per lo scorrimento
            im = Image.open(p).convert("RGB")
            v = list(info.get("visi", []))
            bgr = cv2.cvtColor(np.asarray(ImageOps.contain(im, (720, 720))), cv2.COLOR_RGB2BGR)   # come visi_foto
            try:     # per la scritta TUTTI i visi possibili: anche senza occhi visibili (occhiali, profilo), con la testa
                # inclinata o sdraiato, e quelli dei rilevatori senza controlli (sulle foto di prova della pressa 5 visi
                # su 12 sfuggivano al solo controllo con gli occhi). Un falso viso al massimo toglie una foto, che
                # resta in coda per il prossimo reel
                trovati = visi_foto(im, ruotati=True, inclinati=True)
                v += trovati
                # 6/11/2026 (integrazione, revisione delle foto rapide): i riquadri dei rilevatori senza controlli
                # contano se hanno un po' di pelle al centro (RAPIDE_PELLE) OPPURE se sulla foto nessun altro
                # controllo ha trovato un viso: meno foto buone tolte per un disco o una macchina, mai un viso vero perso
                nessuno = not (info.get("visi") or trovati)
                for b in ov.detect_faces([bgr], ruotati=True):
                    b = tuple(float(x) for x in b)
                    if nessuno or _pelle(bgr, b) >= RAPIDE_PELLE:
                        v.append(b)
            except Exception as e:
                print("Foto rapide: visi per la scritta non cercati:", str(e)[:200])
            visi.append(v)
            piccole.append(bgr)
            if getattr(ov, "STILE_CENTRO", False):     # 7/11/2026: luce nella zona della frase al centro
                try:
                    import stile_centro
                    luci[i] = stile_centro.luce_immagine(im)
                except Exception as e:
                    print("Foto rapide: luce della foto non misurata:", str(e)[:150])
        testo, ordine = _testo_libero(W, H, frase, visi, ov.mappa_dettagli(piccole), ganci)
        durate, ritmo_info = tempi_rapide(musiche[0] if musiche else None, len(ordine))
        if len(durate) < len(ordine):        # le foto in piu' restano in coda: il gancio, poi sparse sulla giornata
            ordine = ordine[:1] + _sparse(ordine[1:], len(durate) - 1)
        quadri = [int(round(d * fps)) for d in durate]       # fotogrammi di ogni foto (a fotogrammi esatti)
        DUR = round(sum(quadri) / fps, 3)
        cmd, catena, scuriti = [ov.FFMPEG, "-y", "-v", "error"], [], []
        for k, (i, nf) in enumerate(zip(ordine, quadri)):
            # foto ferma: pochi fotogrammi letti (2 al secondo), fps li ripete
            cmd += ["-loop", "1", "-framerate", "2", "-t", f"{nf / fps + 0.6:.3f}", "-i", os.path.join(tmp, f"r{i}.jpg")]
            scuro = ""
            if i in luci:      # 7/11/2026: foto troppo chiara sotto la frase al centro -> un po' piu' scura
                try:
                    import stile_centro
                    m = stile_centro.fattore(luci[i])
                    scuro = stile_centro.filtro(m)
                    scuriti.append((1 - m, luci[i]))
                except Exception as e:
                    print("Foto rapide: foto non scurita:", str(e)[:150])
            catena.append(f"[{k}:v]scale={W}:{H},setsar=1,format=yuv420p,{scuro + ',' if scuro else ''}fps={fps},"
                          f"tpad=stop_mode=clone:stop_duration=1,trim=end_frame={nf},setpts=PTS-STARTPTS[c{k}]")
        n = len(ordine)
        p_testo = os.path.join(tmp, "testo.png")
        testo.save(p_testo)
        cmd += ["-i", p_testo]
        g = (";".join(catena) + ";" + "".join(f"[c{k}]" for k in range(n)) + f"concat=n={n}:v=1:a=0[bg];"
             f"[bg][{n}:v]overlay=0:0:format=auto,format=yuv420p[v]")
        amap, idx = ["-an"], n + 1
        musiche = [m for m in musiche if m and os.path.exists(m)]
        if musiche:          # come make_sequenza: pezzi dello stesso brano uniti con sfumatura, stesso volume
            quanti = max(1, int(DUR // 4.7) + 1)
            musiche = (musiche * quanti)[:quanti]
            for m in musiche:
                cmd += ["-i", m]
            prec = f"[{idx}:a]"
            for j in range(1, len(musiche)):
                g += f";{prec}[{idx + j}:a]acrossfade=d=0.3[x{j}]"
                prec = f"[x{j}]"
            g += f";{prec}volume={ov.MUSIC_VOL},{ov.LIMITATORE},apad,atrim=0:{DUR}[a]"
            amap = ["-map", "[a]"]
        cmd += ["-filter_complex", g, "-map", "[v]", *amap, "-t", f"{DUR}", "-c:v", "libx264", "-preset", "medium",
                "-crf", "18", "-profile:v", "high", "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
                "-movflags", "+faststart", dst]
        r = subprocess.run(cmd, capture_output=True, text=True, errors="ignore", timeout=ov.TEMPO_MAX_MONTAGGIO)
        if r.returncode != 0 and scuriti:
            try:     # 7/11/2026: se non riesce con lo scurimento, lo stesso montaggio senza (il reel esce)
                import stile_centro
                cmd2 = stile_centro.senza_scuro(cmd)
                if cmd2:
                    print("Foto rapide: montaggio non riuscito con lo scurimento, riprovo senza:", r.stderr[-200:])
                    r = subprocess.run(cmd2, capture_output=True, text=True, errors="ignore",
                                       timeout=ov.TEMPO_MAX_MONTAGGIO)
                    scuriti = [(0.0, l) for _, l in scuriti]
            except Exception as e:
                print("Foto rapide: ripiego senza scurimento non riuscito:", str(e)[:150])
        if r.returncode != 0 or not os.path.exists(dst) or os.path.getsize(dst) < 50_000:
            raise RuntimeError("foto_rapide: " + r.stderr[-400:])
        info = {"formato": "foto_rapide", "durata": DUR, "musica": os.path.basename(musiche[0]) if musiche else None,
                "stacchi": n, "testi": 1, "ritmo": ritmo_info, "foto_tolte": len(foto) - n, "tenute": ordine}
        if getattr(ov, "STILE_CENTRO", False) and ov.ULTIMO_STILE == "centro_serif":
            try:     # 7/11/2026: montaggio.stile_centro (carattere, corpo, righe, quanto e' scurita la foto piu' chiara)
                import stile_centro
                info["stile_centro"] = stile_centro.dati(max([s for s, _ in scuriti] or [0.0]),
                                                         max([l for _, l in scuriti] or [0.0]) if scuriti else None)
            except Exception as e:
                print("Foto rapide: dati dello stile al centro non scritti:", str(e)[:150])
        return info
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _elenco(drive, cartella=CARTELLA):
    """Tutte le foto della cartella Drive (5/11/2026: tutte le pagine, prima solo le prime 500 foto)."""
    q = (f"'{drive.cartella(cartella)}' in parents and trashed = false and mimeType contains 'image/'")
    r, pagina = [], None
    while True:
        ris = drive.api.files().list(q=q, fields="nextPageToken,files(id,name,createdTime,appProperties,imageMediaMetadata(time))",
                                     pageSize=500, pageToken=pagina).execute()
        r += ris.get("files", [])
        pagina = ris.get("nextPageToken")
        if not pagina:
            break
    return r


def _per_giorno(files, anche_usate=False):
    """{giorno: [foto]} delle foto buone (6/11: anche_usate per riusare quelle di "Foto usate")."""
    giorni = {}
    for f in files:
        prop = f.get("appProperties") or {}
        if (prop.get("usata") == "1" and not anche_usate) or prop.get("scartata") == "1" or int(prop.get("fallita", 0)) >= 2:
            continue         # 5/11: una foto che fa fallire il montaggio 2 volte non blocca piu' le altre
        f["quando"] = (f.get("imageMediaMetadata") or {}).get("time", "").replace(":", "-", 2) or f.get("createdTime", "")
        giorni.setdefault(f["quando"][:10], []).append(f)
    return giorni


def giornata_nuova(drive):
    """(giorno, foto) della giornata piu' recente con abbastanza foto non ancora usate; (None, []) se non ce n'e'."""
    giorni = _per_giorno(_elenco(drive))
    vecchio = (datetime.date.today() - datetime.timedelta(days=2)).isoformat()
    # 6/11/2026 (Alessandro: "dai sempre priorita' ai nuovi contenuti"): prima la giornata PIU' RECENTE, poi le altre
    for g in sorted(giorni, reverse=True):
        # 5/11: gli avanzi (3 foto) di una giornata passata escono lo stesso invece di restare per sempre nella cartella
        if len(giorni[g]) >= MINIMO or (len(giorni[g]) >= 3 and g < vecchio):
            return g, giorni[g]
    return None, []


def pronte(drive):
    """Le foto non ancora usate della giornata piu' recente che ne ha abbastanza (dal 6/11; prima la piu' vecchia):
    [] se non ce ne sono."""
    return scegli(giornata_nuova(drive)[1] or [])


def _sparse(lista, n):
    """n elementi sparsi su tutta la lista (il primo e l'ultimo compresi); tutta la lista se ne ha al massimo n."""
    if len(lista) <= n:
        return list(lista)
    return [lista[round(i * (len(lista) - 1) / max(1, n - 1))] for i in range(n)] if n > 0 else []


def scegli_tante(foto, quante=RAPIDE_SCELTE):
    """6/11/2026 (foto_rapide): fino a `quante` foto sparse su tutta la giornata, una per raffica come scegli().
    Revisione 6/11 (sera): non si riempie piu' con altre foto delle stesse raffiche (l'impronta non riconosce la stessa
    posa nello stesso secondo: nel reel uscivano 3 foto uguali di fila); con pochi momenti diversi esce dieci_foto."""
    foto = sorted(foto, key=lambda f: (f["quando"], f["name"]))
    diverse = []
    for f in foto:
        if not diverse or _secondi(f["quando"]) - _secondi(diverse[-1]["quando"]) >= STACCO:
            diverse.append(f)
    return _sparse(diverse, quante)


def momenti(foto, distacco=RAPIDE_MOMENTO):
    """6/11/2026 (integrazione, ricontrollo delle foto rapide): quanti momenti diversi ha la giornata, cioe' scatti ad
    almeno `distacco` s l'uno dall'altro (come scegli_tante). Per scegliere foto_rapide si contano con RAPIDE_MOMENTO
    (10 s), lo stesso distacco con cui il reel toglie le quasi-doppie: con STACCO (3 s) bastava una serie di 40 s per
    scegliere foto_rapide, poi restavano meno di 10 foto e il reel ripiegava su dieci_foto dopo minuti di lavoro."""
    n, ultimo = 0, None
    for f in sorted(foto, key=lambda f: (f.get("quando", ""), f.get("name", ""))):
        t = _secondi(f.get("quando", ""))
        if ultimo is None or t - ultimo >= distacco:
            n, ultimo = n + 1, t
    return n


def riusabili(drive, state, minimo=MINIMO, quante=None):
    """6/11/2026 (Alessandro: "se non ci sono foto in coda, si andranno ad utilizzare quelle vecchie"): le foto di una
    giornata gia' uscita (cartella "Foto usate") non uscita negli ultimi RIUSO_GIORNI giorni, la piu' recente per prima
    (contenuti nuovi prima). Mai la giornata dell'ultimo reel con le foto e, dentro la giornata, prima le foto non uscite
    l'ultima volta. [] se non ce n'e' una con almeno `minimo` foto (con quante, per foto_rapide: momenti diversi).
    Revisione 6/11 (sera): se tutte le giornate sono uscite negli ultimi 7 giorni, [] (prima: quella uscita da piu'
    tempo, cioe' foto viste 12-48 ore prima): meglio il reel col video nuovo in coda."""
    scelta = (lambda fs: scegli_tante(fs, quante)) if quante else scegli
    # 6/11/2026 (integrazione): per foto_rapide contano i momenti a RAPIDE_MOMENTO (vedi momenti)
    conta = (lambda fs: min(len(scelta(fs)), momenti(fs))) if quante else len
    giorni = {g: fs for g, fs in _per_giorno(_elenco(drive, USATE), anche_usate=True).items() if conta(fs) >= minimo}
    if not giorni:
        return []
    giorno_di = {f["id"]: g for g, fs in giorni.items() for f in fs}
    ultimo, ultime, recenti = {}, {}, set()       # giorno -> ultima uscita; giorno -> foto di quell'uscita
    for h in state.get("storico", []):
        ids = (h.get("montaggio") or {}).get("foto_ids") or []
        for g in {giorno_di.get(i) for i in ids} - {None}:
            if h.get("quando", "") >= ultimo.get(g, ""):
                ultimo[g], ultime[g] = h.get("quando", ""), set(ids)
        if ids:
            recenti = {giorno_di.get(i) for i in ids} - {None}     # le giornate dell'ultimo reel con le foto
    adatti = sorted((g for g in giorni if g not in recenti), reverse=True)
    if not adatti:
        return []
    soglia = (datetime.datetime.now() - datetime.timedelta(days=RIUSO_GIORNI)).isoformat()
    liberi = [g for g in adatti if ultimo.get(g, "") < soglia]
    if not liberi:
        print(f"Foto: nessuna foto nuova e nessuna giornata libera da {RIUSO_GIORNI} giorni: niente reel con le foto")
        return []
    g = liberi[0]
    altre = [f for f in giorni[g] if f["id"] not in ultime.get(g, set())]
    fs = altre if conta(altre) >= minimo else giorni[g]
    print(f"Foto: nessuna foto nuova, riuso la giornata del {g} (uscita l'ultima volta: {ultimo.get(g) or 'mai'})")
    return scelta(fs)


def foto_per_slot(drive, state, voluto="dieci_foto"):
    """6/11/2026: (foto, formato, riuso) per un orario delle foto. Prima le foto NUOVE della giornata piu' recente:
    foto_rapide se ha almeno RAPIDE_MINIMO momenti diversi (una foto per raffica; e l'estrazione dell'orario l'ha
    scelto), se no dieci_foto come prima.
    Senza foto nuove si riusano quelle di una giornata gia' uscita (riusabili). ([], None, False): niente reel con le
    foto. Se qualcosa va storto: come prima (pronte, dieci_foto)."""
    try:
        _, nuove = giornata_nuova(drive)
        if nuove:
            if voluto == "foto_rapide":
                tante = scegli_tante(nuove)
                # revisione 6/11: contano i momenti diversi, non le foto delle raffiche; integrazione 6/11: a 10 s
                if len(tante) >= RAPIDE_MINIMO and momenti(nuove) >= RAPIDE_MINIMO:
                    return tante, "foto_rapide", False
            return scegli(nuove), "dieci_foto", False
        for formato in (("foto_rapide", "dieci_foto") if voluto == "foto_rapide" else ("dieci_foto",)):
            rapide = formato == "foto_rapide"
            vecchie = riusabili(drive, state, RAPIDE_MINIMO if rapide else MINIMO, RAPIDE_SCELTE if rapide else None)
            if vecchie:
                return vecchie, formato, True
        return [], None, False
    except Exception as e:
        print("Foto: scelta delle foto non riuscita, come prima:", str(e)[:300])
        foto = pronte(drive)
        return foto, "dieci_foto" if foto else None, False


def _secondi(quando):
    try:
        return datetime.datetime.fromisoformat(quando.replace("T", " ")[:19]).timestamp()
    except ValueError:
        return 0.0


def scegli(foto):
    """5/11/2026: una foto per raffica (l'iPhone ne scatta 8 in 3 secondi) e foto prese da tutta la giornata, non le prime
    in ordine di nome: cosi' ogni reel mostra momenti diversi. Qualcuna in piu' di MASSIMO per poter scartare le mosse."""
    foto = sorted(foto, key=lambda f: (f["quando"], f["name"]))
    diverse = []
    for f in foto:
        if not diverse or _secondi(f["quando"]) - _secondi(diverse[-1]["quando"]) >= STACCO:
            diverse.append(f)
    n = min(len(diverse), MASSIMO + 2)
    if n < 3:
        return foto[:MASSIMO]
    return [diverse[round(i * (len(diverse) - 1) / max(1, n - 1))] for i in range(n)]


def nitidezza(path):
    """Quanto e' nitida la foto (varianza del laplaciano sulla versione piccola): bassa = mossa o sfocata."""
    import cv2, numpy as np
    im = ImageOps.exif_transpose(Image.open(path)).convert("L")
    im.thumbnail((720, 720))
    return float(cv2.Laplacian(np.asarray(im), cv2.CV_64F).var())


def scheda(path):
    """6/11/2026: i voti di una foto con una sola lettura: nitidezza (come nitidezza()), viso (area del viso piu'
    grande, frazione della foto), luce (media 0-1), impronta (dHash da 64 bit, per le quasi-doppie)."""
    import cv2, numpy as np
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    # per il gancio conta il viso dritto, ben visibile; revisione 6/11: con gli occhi aperti, cercati sulla foto grande
    visi = visi_foto(im, ruotati=False, occhi=True)
    im.thumbnail((720, 720))
    g = np.asarray(im.convert("L"))
    p = cv2.resize(g, (9, 8), interpolation=cv2.INTER_AREA).astype(int)
    return {"nitidezza": float(cv2.Laplacian(g, cv2.CV_64F).var()),
            "viso": max(((v[2] - v[0]) * (v[3] - v[1]) for v in visi), default=0.0),
            "luce": float(g.mean()) / 255,
            "impronta": int("".join("1" if b else "0" for b in (p[:, 1:] > p[:, :-1]).flatten()), 2)}


def voto(s, nit_max):
    """6/11/2026: quanto la foto "aggancia" nel primo secondo: viso grande e chiaro, nitida, luce giusta."""
    viso = min(1.0, math.sqrt(s["viso"]) / 0.35)
    luce = max(0.0, 1 - abs(s["luce"] - 0.45) / 0.35)
    return 1.2 * viso + 0.6 * s["nitidezza"] / max(nit_max, 1e-6) + 0.4 * luce


def _simili(a, b):
    """6/11/2026: True se le impronte di due schede differiscono al massimo di SIMILI bit su 64 (quasi-doppie)."""
    return bin(a["impronta"] ^ b["impronta"]).count("1") <= SIMILI


def _doppie(x, y, schede, momento=None):
    """Revisione 6/11/2026 (sera): True se le foto x e y ((file, percorso)) sono quasi-doppie: impronte a meno di
    SIMILI bit (come _simili) o, con momento (secondi, foto_rapide), scatti a meno di `momento` secondi con impronte a
    meno di RAPIDE_DIVERSE bit (sulle foto di prova la stessa posa nello stesso secondo: 10-11 bit)."""
    d = bin(schede[x[1]]["impronta"] ^ schede[y[1]]["impronta"]).count("1")
    return d <= SIMILI or bool(momento and d < RAPIDE_DIVERSE and
                               abs(_secondi(x[0].get("quando", "")) - _secondi(y[0].get("quando", ""))) <= momento)


def ordina(locali, schede, massimo=MASSIMO, momento=None):
    """6/11/2026 (gancio): delle foto quasi uguali se ne tiene una (la migliore), poi la foto piu' forte va per prima
    (e' quella che ferma chi scorre) e le altre seguono in ordine di scatto, sparse su tutta la giornata.
    Revisione 6/11: il gancio solo tra le foto nitide (GANCIO); restituisce (scelte, doppie), con doppie = le
    quasi-doppie rimaste fuori di una foto scelta: si segnano come usate con le altre, se no il reel dopo avrebbe
    le stesse pose. massimo: foto nel reel (RAPIDE_MASSIMO per foto_rapide); momento: vedi _doppie (foto_rapide)."""
    nit_max = max(schede[p]["nitidezza"] for _, p in locali)
    punti = {p: voto(schede[p], nit_max) for _, p in locali}
    per_voto = sorted(locali, key=lambda x: -punti[x[1]])
    nitide = [x for x in per_voto if schede[x[1]]["nitidezza"] >= GANCIO * nit_max]
    # 6/11/2026 (100 punti, punto 14): il gancio mai nero, buio o bruciato (stesse soglie di formati_nuovi, la luce
    # "tipica" e' quella delle foto della giornata); se nessuna foto nitida lo e', come prima
    luci = sorted(schede[p]["luce"] for _, p in locali)
    tipica = luci[len(luci) // 2]
    pulita = lambda s: 16 / 255 <= s["luce"] <= 232 / 255 and s["luce"] >= 0.45 * tipica
    tenute = [next((x for x in nitide if pulita(schede[x[1]])), nitide[0])]
    for x in per_voto:
        if not any(_doppie(x, y, schede, momento) for y in tenute):
            tenute.append(x)
    for x in per_voto:       # mai meno di 3 foto per togliere le quasi-doppie
        if len(tenute) >= 3:
            break
        if x not in tenute:
            tenute.append(x)
    gancio, altre = tenute[0], sorted(tenute[1:], key=lambda x: (x[0].get("quando", ""), x[0].get("name", "")))
    if len(altre) > massimo - 1:
        altre = [altre[round(i * (len(altre) - 1) / (massimo - 2))] for i in range(massimo - 1)]
    scelte = [gancio] + altre
    doppie = [x for x in locali if x not in scelte and any(_doppie(x, y, schede, momento) for y in scelte)]
    return scelte, doppie


def _mosse(locali, voti, isolate=False):
    """Revisione 6/11/2026 (sera): le foto mosse o sfocate. Ogni foto si confronta solo con le foto della stessa scena
    (scattate a meno di SCENA, 15 minuti): la nitidezza misurata dipende da quanti dettagli ha la scena (palestra
    795-1370, un primo piano nitido in macchina 268) e col confronto su tutta la giornata le foto nitide di macchina,
    ufficio e specchio si scartavano per sempre. Una foto sola nella sua scena non si scarta.
    6/11/2026 (integrazione, ricontrollo delle foto rapide): -> (mosse, da_segnare). mosse = fuori da QUESTO reel;
    da_segnare = solo quelle piu' sfocate di una foto della stessa SERIE (meno di 3 minuti): queste si segnano
    'scartata' per sempre. Con la foto piu' nitida a 3-15 minuti (cambio di scena: il selfie in macchina subito dopo
    l'allenamento) la foto resta in coda per un altro reel. isolate=True (dieci_foto): le foto senza vicine nella
    stessa scena si confrontano con la piu' nitida di tutte, come prima, ma solo per lasciarle fuori."""
    t = {p: _secondi(f.get("quando", "")) for f, p in locali}
    tutte = max(voti.values()) if voti else 0.0
    mosse, segnare = [], []
    for f, p in locali:
        vicine = [(voti[q], abs(t[q] - t[p])) for _, q in locali if q != p and abs(t[q] - t[p]) <= SCENA]
        if vicine and voti[p] < NITIDEZZA * max(v for v, _ in vicine):
            mosse.append((f, p))
            serie = [v for v, d in vicine if d <= SERIE]
            if serie and voti[p] < NITIDEZZA * max(serie):
                segnare.append((f, p))
        elif not vicine and isolate and voti[p] < NITIDEZZA * tutte:
            mosse.append((f, p))
    return mosse, segnare


def _scarica(foto, drive, work, massimo=MASSIMO, riuso=False, momento=None):
    """Scarica le foto, scarta le mosse e le quasi-doppie, la migliore per prima. -> (locali, doppie, schede).
    6/11/2026: riuso = foto gia' uscite (cartella "Foto usate"): non si segnano come scartate. momento: vedi _doppie."""
    locali = []
    for i, f in enumerate(foto):
        p = os.path.join(work, f"foto_{i}.jpg")
        drive.download(f["id"], p, folder=USATE if riuso else CARTELLA)
        locali.append((f, p))
    schede = {}
    try:
        try:                     # 6/11/2026: una sola lettura per nitidezza, viso, luce e impronta
            schede = {p: scheda(p) for _, p in locali}
            voti = {p: schede[p]["nitidezza"] for _, p in locali}
        except Exception as e:
            print("Foto: schede non riuscite, solo nitidezza:", e)
            schede, voti = {}, {p: nitidezza(p) for _, p in locali}
        piccola = lambda p: min(Image.open(p).size) < LATO_MINIMO
        try:                     # revisione 6/11 (sera): solo con le foto della stessa scena
            # 6/11/2026 (integrazione): 'scartata' solo se la foto piu' nitida e' della stessa serie (vedi _mosse)
            mosse, segnare = _mosse(locali, voti, isolate=momento is None)
        except Exception as e:
            print("Foto: confronto per scena non riuscito, come prima:", e)
            mosse = [(f, p) for f, p in locali if voti[p] < NITIDEZZA * max(voti.values())]
            segnare = list(mosse)
        piccole = [(f, p) for f, p in locali if (f, p) not in mosse and piccola(p)]
        mosse += piccole
        segnare += piccole       # troppo piccola resta troppo piccola: fuori per sempre, come prima
        if len(locali) - len(mosse) >= 3:
            for f, _ in ([] if riuso else segnare):
                drive.api.files().update(fileId=f["id"], body={"appProperties": {"scartata": "1"}}).execute()
            locali = [x for x in locali if x not in mosse]
    except Exception:
        pass                     # senza il controllo si usano tutte
    doppie = []
    try:                         # 6/11/2026: niente quasi-doppie, la foto migliore per prima
        if schede:
            locali, doppie = ordina(locali, schede, massimo, momento)
    except Exception as e:
        print("Foto: ordine col gancio non riuscito, ordine di scatto:", e)
    if len(locali) > massimo:    # restano sparse su tutta la giornata
        locali = [locali[round(i * (len(locali) - 1) / (massimo - 1))] for i in range(massimo)]
    return locali, doppie, schede


def _conta_fallite(drive, locali):
    """Conta il fallimento sulle foto (non se manca il lettore HEIC): dopo 2 si saltano."""
    for f, _ in (locali if pillow_heif else []):
        prop = f.get("appProperties") or {}
        try:
            drive.api.files().update(fileId=f["id"], body={"appProperties": {
                "fallita": str(int(prop.get("fallita", 0)) + 1)}}).execute()
        except Exception:
            pass


def _dati_foto(usate, doppie, riuso):
    """Quello che va in stato.json (montaggio): le foto da segnare come usate dopo la pubblicazione e il giorno."""
    giorno = next((f.get("quando", "")[:10] for f, _ in usate if f.get("quando")), None)
    return dict(foto_ids=[f["id"] for f, _ in usate + doppie], foto_doppie=len(doppie), foto_giorno=giorno,
                **({"foto_riuso": True} if riuso else {}))


def monta(foto, frase, dst, musiche, drive, work, riuso=False):
    """Scarica le foto, scarta le mosse, monta il reel e le segna come usate."""
    locali, doppie, _ = _scarica(foto, drive, work, MASSIMO, riuso)
    try:
        info = make_foto([p for _, p in locali], frase, dst, musiche)
    except Exception:
        _conta_fallite(drive, [] if riuso else locali)
        raise
    # 5/11/2026: le foto si segnano come usate solo DOPO la pubblicazione (segna_usate, da pubblica.py):
    # prima un reel montato ma non uscito su nessuna piattaforma le faceva perdere.
    # 6/11/2026 (revisione): con loro anche le quasi-doppie rimaste fuori (stessa posa gia' uscita in questo reel)
    return dict(info, **_dati_foto(locali, doppie, riuso))


def monta_rapide(foto, frase, dst, musiche, drive, work, riuso=False):
    """6/11/2026: reel foto_rapide (make_rapide) con le foto della giornata: scarica, scarta mosse e quasi-doppie, la
    migliore per prima. Se non riesce (poche foto buone, scritta che coprirebbe il viso, errore): il reel con le foto
    di sempre (make_foto, 6 foto) con le stesse foto, cosi' esce comunque; le altre restano per il prossimo reel."""
    locali, doppie, schede = _scarica(foto, drive, work, RAPIDE_MASSIMO, riuso, RAPIDE_MOMENTO)
    ganci = [0]
    try:         # ganci di riserva se la scritta coprisse il viso del primo: le foto nitide col voto piu' alto
        nit_max = max(schede[p]["nitidezza"] for _, p in locali)
        ganci += sorted((i for i in range(1, len(locali)) if schede[locali[i][1]]["nitidezza"] >= GANCIO * nit_max),
                        key=lambda i: -voto(schede[locali[i][1]], nit_max))[:2]
    except Exception:
        pass
    try:
        if len(locali) < RAPIDE_MINIMO_USO:
            raise ValueError(f"solo {len(locali)} foto buone")
        info = make_rapide([p for _, p in locali], frase, dst, musiche, ganci)
        usate = [locali[i] for i in info.pop("tenute")]
    except Exception as e:
        if isinstance(e, fn.VisoCoperto) and getattr(e, "viso_gancio", False):
            # 6/11/2026 (integrazione, revisione delle foto rapide; regola 2: la scritta mai sul viso): la scritta copre
            # il viso della prima foto, la stessa che make_foto metterebbe per prima (e il suo ultimo tentativo non
            # guarda i visi): esce il reel col video (pubblica: controllo del viso e fascia cinema/post). Le foto
            # restano in coda, nessun fallimento contato
            print("Foto rapide: la scritta coprirebbe il viso della prima foto, esce il reel col video")
            raise
        print("Foto rapide non riuscite, reel con le foto che scorrono (come prima):", str(e)[:300])
        usate = locali[:1] + _sparse(locali[1:], MASSIMO - 1)
        try:
            info = dict(make_foto([p for _, p in usate], frase, dst, musiche), ripiego_da="foto_rapide")
        except Exception:
            _conta_fallite(drive, [] if riuso else usate)
            raise
    try:         # le quasi-doppie solo delle foto uscite davvero (le altre foto restano in coda)
        doppie = [x for x in doppie if any(_doppie(x, y, schede, RAPIDE_MOMENTO) for y in usate)]
    except Exception:
        doppie = []
    return dict(info, **_dati_foto(usate, doppie, riuso))


def segna_usate(drive, ids):
    """Segna le foto come usate e le sposta in "Foto usate" (accanto): in "Foto della giornata" restano solo quelle
    ancora da usare, cosi' Alessandro vede a colpo d'occhio cosa manca. Niente si cancella."""
    import time
    try:
        da, a = drive.cartella(CARTELLA), drive.cartella(USATE)
    except Exception:
        da = a = None
    for i in ids:
        for tentativo in range(2):   # una foto non segnata uscirebbe di nuovo
            try:
                drive.api.files().update(fileId=i, body={"appProperties": {"usata": "1"}},
                                         **({"addParents": a, "removeParents": da} if a else {})).execute()
                break
            except Exception:
                time.sleep(5)
