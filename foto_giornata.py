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


def migliora(src, dst):
    """Sistemazione automatica: esposizione, contrasto, saturazione, tono un po' caldo, nitidezza. Taglio 9:16."""
    W, H = ov.LATO_USCITA, int(ov.LATO_USCITA * 16 / 9)
    im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    im = ImageOps.fit(im, (int(W * MARGINE), H), Image.LANCZOS, centering=(0.5, 0.45))
    media = sum(ImageOps.grayscale(im).resize((64, 64)).getdata()) / (64 * 64 * 255)
    gamma = max(0.75, min(1.25, math.log(LUCE) / math.log(max(media, 0.02))))
    tabella = [round(255 * (i / 255) ** gamma) for i in range(256)]
    im = im.point(tabella * 3)
    im = ImageOps.autocontrast(im, cutoff=0.5, preserve_tone=True)
    if STILE == "flash":
        flash(im).save(dst, quality=96)
        return
    if STILE == "virale":
        virale(im).save(dst, quality=96)
        return
    # stile delle foto che piacciono ad Alessandro: caldo e morbido, luci basse, ombre piene, colori naturali (non saturi)
    im = im.point([round(255 * ((i / 255) - 0.10 * max(0.0, (i / 255) - 0.7) / 0.3)) for i in range(256)] * 3)
    im = ImageEnhance.Contrast(im).enhance(1.04)
    r, g, b = im.split()
    im = Image.merge("RGB", (r.point(lambda v: min(255, int(v * 1.03))), g, b.point(lambda v: int(v * 0.95))))
    im = im.filter(ImageFilter.UnsharpMask(radius=2, percent=40, threshold=3))
    im.save(dst, quality=96)


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
    """Foto -> clip con uno scorrimento leggero (verso 1: a destra, 0: a sinistra)."""
    W, H = ov.LATO_USCITA, int(ov.LATO_USCITA * 16 / 9)
    x = f"(iw-{W})*t/{secondi:.2f}" if verso else f"(iw-{W})*(1-t/{secondi:.2f})"
    subprocess.run([ov.FFMPEG, "-y", "-v", "error", "-loop", "1", "-framerate", str(ov.FPS_MULTI), "-t", f"{secondi:.2f}",
                    "-i", img, "-vf", f"crop={W}:{H}:'{x}':0,format=yuv420p", "-c:v", "libx264", "-preset", "ultrafast",
                    "-crf", "16", dst], check=True, timeout=ov.TEMPO_MAX_MONTAGGIO)


def make_foto(foto, frase, dst, musiche=()):
    """Reel da 10 s: le foto una dopo l'altra, frase intera dal primo fotogramma, stacchi sul colpo della musica."""
    tmp = tempfile.mkdtemp()
    try:
        durate = [round(10.0 / len(foto), 3)] * len(foto)
        if musiche and os.path.exists(musiche[0]):
            durate = fn.tagli_a_tempo(musiche[0], durate)
        clips = []
        for i, (f, d) in enumerate(zip(foto, durate)):
            img, clip = os.path.join(tmp, f"f{i}.jpg"), os.path.join(tmp, f"c{i}.mp4")
            migliora(f, img)
            in_clip(img, clip, d + 1.0, i % 2)
            clips.append(clip)
        # la scritta resta ferma per 10 s: se copre un viso si riprova con meno foto, altrimenti esce comunque nel punto migliore
        for n in range(len(clips), 2, -1):
            try:
                d = [round(10.0 / n, 3)] * n
                return fn.make_sequenza(clips[:n], d, [(0.0, 10.0, frase)], dst, musiche, None, "dieci_foto", True)
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


def monta(foto, frase, dst, musiche, drive, work):
    """Scarica le foto, scarta le mosse, monta il reel e le segna come usate."""
    locali = []
    for i, f in enumerate(foto):
        p = os.path.join(work, f"foto_{i}.jpg")
        drive.download(f["id"], p, folder=CARTELLA)
        locali.append((f, p))
    try:
        voti = {p: nitidezza(p) for _, p in locali}
        soglia = NITIDEZZA * max(voti.values())
        piccola = lambda p: min(Image.open(p).size) < LATO_MINIMO
        mosse = [(f, p) for f, p in locali if voti[p] < soglia or piccola(p)]
        if len(locali) - len(mosse) >= 3:
            for f, _ in mosse:
                drive.api.files().update(fileId=f["id"], body={"appProperties": {"scartata": "1"}}).execute()
            locali = [x for x in locali if x not in mosse]
    except Exception:
        pass                     # senza il controllo si usano tutte
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
