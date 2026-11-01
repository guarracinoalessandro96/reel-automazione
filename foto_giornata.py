"""
Reel con le foto della giornata (1/11/2026, richiesta di Alessandro): le foto dell'iPhone arrivano nella cartella Drive
"Foto della giornata", si sistemano come fa l'iPhone (luce, contrasto, colori, nitidezza) e diventano un reel da 10 s
con un movimento leggero, la musica e la scritta. Un reel al giorno, all'orario ORARIO_FOTO di pubblica.py.
"""
import datetime, math, os, shutil, subprocess, tempfile
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import formati_nuovi as fn
import overlay as ov

CARTELLA = "Foto della giornata"
MINIMO, MASSIMO = 4, 6       # foto della stessa giornata in un reel
MARGINE = 1.08               # 8% in piu' della larghezza: lo spazio del movimento
LUCE = 0.46                  # luminosita' media a cui portare la foto


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
    # stile delle foto che piacciono ad Alessandro: caldo e morbido, luci basse, ombre piene, colori naturali (non saturi)
    im = im.point([round(255 * ((i / 255) - 0.10 * max(0.0, (i / 255) - 0.7) / 0.3)) for i in range(256)] * 3)
    im = ImageEnhance.Contrast(im).enhance(1.04)
    r, g, b = im.split()
    im = Image.merge("RGB", (r.point(lambda v: min(255, int(v * 1.03))), g, b.point(lambda v: int(v * 0.95))))
    im = im.filter(ImageFilter.UnsharpMask(radius=2, percent=40, threshold=3))
    im.save(dst, quality=96)


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
    r = drive.api.files().list(q=q, fields="files(id,name,createdTime,appProperties,imageMediaMetadata(time))",
                               pageSize=500).execute().get("files", [])
    giorni = {}
    for f in r:
        if (f.get("appProperties") or {}).get("usata") == "1":
            continue
        quando = (f.get("imageMediaMetadata") or {}).get("time", "").replace(":", "-", 2) or f.get("createdTime", "")
        giorni.setdefault(quando[:10], []).append(f)
    for g in sorted(giorni):
        if len(giorni[g]) >= MINIMO:
            return sorted(giorni[g], key=lambda f: f["name"])[:MASSIMO]
    return []


def monta(foto, frase, dst, musiche, drive, work):
    """Scarica le foto, monta il reel e le segna come usate."""
    locali = []
    for i, f in enumerate(foto):
        p = os.path.join(work, f"foto_{i}.jpg")
        drive.download(f["id"], p, folder=CARTELLA)
        locali.append(p)
    info = make_foto(locali, frase, dst, musiche)
    for f in foto:
        drive.api.files().update(fileId=f["id"], body={"appProperties": {"usata": "1"}}).execute()
    return info
