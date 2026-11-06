"""
Reel con le foto della giornata (1/11/2026, richiesta di Alessandro): le foto dell'iPhone arrivano nella cartella Drive
"Foto della giornata", si sistemano come fa l'iPhone (luce, contrasto, colori, nitidezza) e diventano un reel da 10 s
con un movimento leggero, la musica e la scritta. Agli orari ORARIO_FOTO di pubblica.py, finche' ci sono foto.
Le foto arrivano anche dal bot Telegram (ricevi_telegram.py); quelle uscite vanno in "Foto usate".
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
VISO_Y = 0.40                # dove cade il viso nel taglio 9:16 (frazione dell'altezza), quando la foto lo permette
SIMILI = 8                   # differenza massima (su 64) tra le impronte di due foto quasi uguali: se ne tiene una
PELLE = 0.7                  # un "viso" con meno del 70% di pelle al centro e' un falso (pedana, dischi, scarpe:
                             # sulle foto di prova la pedana della pressa arriva al 60%, i visi veri a 76-87%)


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


def visi_foto(im, ruotati=False):
    """6/11/2026: i visi della foto [(x0, y0, x1, y1) in frazioni, con margine per capelli e mento], uniti quando
    piu' rilevatori trovano lo stesso viso; dal piu' grande al piu' piccolo. In palestra i rilevatori vedono "visi"
    anche nella pedana della pressa o nei dischi: si tengono solo quelli con abbastanza pelle al centro (PELLE)."""
    import cv2, numpy as np
    p = ImageOps.contain(im, (720, 720))
    bgr = cv2.cvtColor(np.asarray(p), cv2.COLOR_RGB2BGR)
    ycc = cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb)
    pelle = (ycc[..., 0] > 40) & (ycc[..., 1] >= 135) & (ycc[..., 1] <= 180) & (ycc[..., 2] >= 80) & (ycc[..., 2] <= 135)
    gruppi = []
    for b in ov.detect_faces([bgr], ruotati=ruotati):
        b = (max(0.0, b[0]), max(0.0, b[1]), min(1.0, b[2]), min(1.0, b[3]))
        for i, g in enumerate(gruppi):
            if ov._overlap(g, b) > 0:
                gruppi[i] = (min(g[0], b[0]), min(g[1], b[1]), max(g[2], b[2]), max(g[3], b[3]))
                break
        else:
            gruppi.append(b)
    veri = []
    for g in gruppi:             # centro del riquadro (senza i margini per capelli e mento)
        x0, x1 = int((g[0] + (g[2] - g[0]) * 0.25) * p.width), int((g[2] - (g[2] - g[0]) * 0.25) * p.width)
        y0, y1 = int((g[1] + (g[3] - g[1]) * 0.3) * p.height), int((g[3] - (g[3] - g[1]) * 0.3) * p.height)
        if x1 > x0 and y1 > y0 and float(pelle[y0:y1, x0:x1].mean()) >= PELLE:
            veri.append(g)
    return sorted(veri, key=lambda g: -(g[2] - g[0]) * (g[3] - g[1]))


def taglio(W, H, rot, visi):
    """6/11/2026: il riquadro 9:16 (+ MARGINE per il movimento) da prendere dalla foto. Si parte dal taglio di prima
    (centro, un filo in alto); se quel taglio tagliasse il viso (foto orizzontali, viso vicino al bordo) si centra sul
    viso, con il viso in alto (VISO_Y) quando la foto lo permette. Mai angoli neri se la foto e' stata raddrizzata.
    Un viso "falso" che sta gia' dentro il taglio di prima non sposta niente. Restituisce (x0, y0, w, h)."""
    r = 9 / 16 * MARGINE
    h = min(H, W / r)
    if rot:                  # foto raddrizzata: il riquadro piu' grande che sta tutto dentro
        lo, hi = 0.0, h
        for _ in range(30):
            m = (lo + hi) / 2
            lo, hi = (m, hi) if _dentro((W - m * r) / 2, (H - m) / 2, m * r, m, W, H, rot) else (lo, m)
        h = lo
    w = h * r
    cx, cy = (W - w) * 0.5, (H - h) * 0.45
    x0, y0 = cx, cy
    if visi:
        a = visi[0]          # il viso piu' grande, insieme agli altri visi grandi se ci stanno (foto di gruppo)
        for v in visi[1:]:
            u = (min(a[0], v[0]), min(a[1], v[1]), max(a[2], v[2]), max(a[3], v[3]))
            if (v[2] - v[0]) * (v[3] - v[1]) >= 0.3 * (visi[0][2] - visi[0][0]) * (visi[0][3] - visi[0][1]) \
                    and (u[2] - u[0]) * W <= 0.9 * w:
                a = u
        fx, fy = (a[0] + a[2]) / 2 * W, (a[1] + a[3]) / 2 * H
        x0 = cx if cx <= a[0] * W and a[2] * W <= cx + w else fx - w / 2
        y0 = cy if h >= H - 1 else fy - h * VISO_Y      # foto piu' alte del 9:16: il viso sale a VISO_Y
        if a[2] * W - a[0] * W <= w:          # viso intero dentro il riquadro, se ci sta
            x0 = min(max(x0, a[2] * W - w), a[0] * W)
        if a[3] * H - a[1] * H <= h:
            y0 = min(max(y0, a[3] * H - h), a[1] * H)
    x0, y0 = min(max(x0, 0.0), W - w), min(max(y0, 0.0), H - h)
    if rot and not _dentro(x0, y0, w, h, W, H, rot):
        lo, hi = 0.0, 1.0    # si avvicina al centro quanto basta per restare dentro la foto
        for _ in range(20):
            m = (lo + hi) / 2
            lo, hi = (lo, m) if _dentro(x0 + (cx - x0) * m, y0 + (cy - y0) * m, w, h, W, H, rot) else (m, hi)
        x0, y0 = x0 + (cx - x0) * hi, y0 + (cy - y0) * hi
    return x0, y0, w, h


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


def prepara(src):
    """6/11/2026: foto -> immagine 9:16 (+ MARGINE) raddrizzata, tagliata sul viso e ripulita. Restituisce
    (immagine, info) con info = {"gradi", "visi" (nel taglio), "verso" (1/0 o None), "iso"}. Se qualcosa va storto:
    il taglio di prima (centro, un filo in alto), cosi' il reel esce sempre."""
    W, H = ov.LATO_USCITA, int(ov.LATO_USCITA * 16 / 9)
    orig = Image.open(src)
    iso, obiettivo, acc = dati_scatto(orig)
    im = base = ImageOps.exif_transpose(orig).convert("RGB")
    info = {"gradi": 0.0, "visi": [], "verso": None, "iso": iso}
    try:
        gradi = inclinazione(acc, obiettivo, im.height > im.width)
        if gradi:
            im = im.rotate(-gradi, resample=Image.BICUBIC)
        # solo visi dritti: girata di 90 gradi la pedana della pressa con le scarpe sembra un viso (anche per la pelle)
        visi = visi_foto(im, ruotati=False)
        x0, y0, w, h = taglio(im.width, im.height, -gradi, visi)
        tagliata = im.resize((int(W * MARGINE), H), Image.LANCZOS, box=(x0, y0, x0 + w, y0 + h))
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
        im = ImageOps.fit(base, (int(W * MARGINE), H), Image.LANCZOS, centering=(0.5, 0.45))
    return im, info


def migliora(src, dst):
    """Sistemazione automatica: esposizione, contrasto, saturazione, tono un po' caldo, nitidezza. Taglio 9:16.
    6/11/2026: raddrizzata, tagliata sul viso e ripulita dalla grana (prepara); restituisce le info del taglio."""
    im, info = prepara(src)
    media = sum(ImageOps.grayscale(im).resize((64, 64)).getdata()) / (64 * 64 * 255)
    gamma = max(0.75, min(1.25, math.log(LUCE) / math.log(max(media, 0.02))))
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
            try:
                tenute = sorted(set(range(len(clips))) - set(via[:len(clips) - n]))
                d = durate if n == len(clips) else [round(10.0 / n, 3)] * n     # 6/11: stacchi a tempo anche qui
                return fn.make_sequenza([clips[i] for i in tenute], d, [(0.0, 10.0, frase)], dst, musiche, None,
                                        "dieci_foto", True)
            except fn.VisoCoperto:
                pass
        return fn.make_sequenza(clips, durate, [(0.0, 10.0, frase)], dst, musiche, None, "dieci_foto")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def pronte(drive):
    """Le foto non ancora usate della giornata piu' vecchia che ne ha abbastanza: [] se non ce ne sono."""
    q = (f"'{drive.cartella(CARTELLA)}' in parents and trashed = false and mimeType contains 'image/'")
    r, pagina = [], None
    while True:              # 5/11/2026: tutte le pagine (prima solo le prime 500 foto)
        ris = drive.api.files().list(q=q, fields="nextPageToken,files(id,name,createdTime,appProperties,imageMediaMetadata(time))",
                                     pageSize=500, pageToken=pagina).execute()
        r += ris.get("files", [])
        pagina = ris.get("nextPageToken")
        if not pagina:
            break
    giorni = {}
    for f in r:
        prop = f.get("appProperties") or {}
        if prop.get("usata") == "1" or prop.get("scartata") == "1" or int(prop.get("fallita", 0)) >= 2:
            continue         # 5/11: una foto che fa fallire il montaggio 2 volte non blocca piu' le altre
        f["quando"] = (f.get("imageMediaMetadata") or {}).get("time", "").replace(":", "-", 2) or f.get("createdTime", "")
        giorni.setdefault(f["quando"][:10], []).append(f)
    vecchio = (datetime.date.today() - datetime.timedelta(days=2)).isoformat()
    for g in sorted(giorni):
        # 5/11: gli avanzi (3 foto) di una giornata passata escono lo stesso invece di restare per sempre nella cartella
        if len(giorni[g]) >= MINIMO or (len(giorni[g]) >= 3 and g < vecchio):
            return scegli(giorni[g])
    return []


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
    im.thumbnail((720, 720))
    g = np.asarray(im.convert("L"))
    visi = visi_foto(im, ruotati=False)          # per il gancio conta il viso dritto, ben visibile
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


def ordina(locali, schede):
    """6/11/2026 (gancio): delle foto quasi uguali se ne tiene una (la migliore), poi la foto piu' forte va per prima
    (e' quella che ferma chi scorre) e le altre seguono in ordine di scatto, sparse su tutta la giornata."""
    nit_max = max(schede[p]["nitidezza"] for _, p in locali)
    punti = {p: voto(schede[p], nit_max) for _, p in locali}
    tenute = []
    for f, p in sorted(locali, key=lambda x: -punti[x[1]]):
        if all(bin(schede[p]["impronta"] ^ schede[q]["impronta"]).count("1") > SIMILI for _, q in tenute):
            tenute.append((f, p))
    for x in sorted(locali, key=lambda x: -punti[x[1]]):     # mai meno di 3 foto per togliere le quasi-doppie
        if len(tenute) >= 3:
            break
        if x not in tenute:
            tenute.append(x)
    gancio, altre = tenute[0], sorted(tenute[1:], key=lambda x: (x[0].get("quando", ""), x[0].get("name", "")))
    if len(altre) > MASSIMO - 1:
        altre = [altre[round(i * (len(altre) - 1) / (MASSIMO - 2))] for i in range(MASSIMO - 1)]
    return [gancio] + altre


def monta(foto, frase, dst, musiche, drive, work):
    """Scarica le foto, scarta le mosse, monta il reel e le segna come usate."""
    locali = []
    for i, f in enumerate(foto):
        p = os.path.join(work, f"foto_{i}.jpg")
        drive.download(f["id"], p, folder=CARTELLA)
        locali.append((f, p))
    schede = {}
    try:
        try:                     # 6/11/2026: una sola lettura per nitidezza, viso, luce e impronta
            schede = {p: scheda(p) for _, p in locali}
            voti = {p: schede[p]["nitidezza"] for _, p in locali}
        except Exception as e:
            print("Foto: schede non riuscite, solo nitidezza:", e)
            schede, voti = {}, {p: nitidezza(p) for _, p in locali}
        soglia = NITIDEZZA * max(voti.values())
        piccola = lambda p: min(Image.open(p).size) < LATO_MINIMO
        mosse = [(f, p) for f, p in locali if voti[p] < soglia or piccola(p)]
        if len(locali) - len(mosse) >= 3:
            for f, _ in mosse:
                drive.api.files().update(fileId=f["id"], body={"appProperties": {"scartata": "1"}}).execute()
            locali = [x for x in locali if x not in mosse]
    except Exception:
        pass                     # senza il controllo si usano tutte
    try:                         # 6/11/2026: niente quasi-doppie, la foto migliore per prima
        locali = ordina(locali, schede) if schede else locali
    except Exception as e:
        print("Foto: ordine col gancio non riuscito, ordine di scatto:", e)
    if len(locali) > MASSIMO:    # restano sparse su tutta la giornata
        locali = [locali[round(i * (len(locali) - 1) / (MASSIMO - 1))] for i in range(MASSIMO)]
    try:
        info = make_foto([p for _, p in locali], frase, dst, musiche)
    except Exception:
        for f, _ in (locali if pillow_heif else []):   # conta il fallimento (non se manca il lettore HEIC): dopo 2 si salta
            prop = f.get("appProperties") or {}
            try:
                drive.api.files().update(fileId=f["id"], body={"appProperties": {
                    "fallita": str(int(prop.get("fallita", 0)) + 1)}}).execute()
            except Exception:
                pass
        raise
    # 5/11/2026: le foto si segnano come usate solo DOPO la pubblicazione (segna_usate, da pubblica.py):
    # prima un reel montato ma non uscito su nessuna piattaforma le faceva perdere
    return dict(info, foto_ids=[f["id"] for f, _ in locali])


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
