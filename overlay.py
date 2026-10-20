"""Mette il testo-gancio sul video in una zona senza viso (viso in alto -> testo in basso e viceversa)."""
import os, random, re, shutil, subprocess, tempfile
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg
import grade

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
_DIR = os.path.dirname(os.path.abspath(__file__))
FONTS = [
    os.path.join(_DIR, "font", "Poppins-SemiBold.ttf"),        # carattere del profilo (Google Fonts, licenza OFL)
    r"C:\Windows\Fonts\segoeuib.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
FONT = next((f for f in FONTS if os.path.exists(f)), None)

SAFE_TOP, SAFE_BOTTOM = 0.10, 0.76   # sopra: nome utente; sotto: descrizione e pulsanti
TEXT_MAX_W = 0.72                    # resta lontano dalla colonna di icone a destra
DIM_TESTO = 0.043     # grandezza della frase rispetto alla larghezza del video (0,050 fino al 18/10/2026; dal 19/10
                      # un po' piu' piccola, richiesta di Alessandro: si vede di piu' la scena)
DIM_SERIE = 0.030     # etichetta "GIORNO X / 365" (stessa grandezza di prima)
RIDUZIONE_REGOLE = 0.87   # formato REGOLE: titolo e righe ridotti nella stessa proporzione
TOP_FIRST = [0.13, 0.22, 0.32, 0.58, 0.48]
BOTTOM_FIRST = [0.58, 0.50, 0.42, 0.13, 0.22]

_casc = [cv2.CascadeClassifier(os.path.join(cv2.data.haarcascades, f))
         for f in ("haarcascade_frontalface_default.xml", "haarcascade_frontalface_alt2.xml",
                   "haarcascade_profileface.xml")]


def probe(path):
    r = subprocess.run([FFMPEG, "-hide_banner", "-i", path], capture_output=True, text=True, errors="ignore")
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    seconds = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 6.0
    hdr = bool(re.search(r"arib-std-b67|smpte2084", r.stderr))
    return seconds, hdr


def fps(path):
    """Fotogrammi al secondo del video (es. 30 o 60); 30 se non si legge."""
    r = subprocess.run([FFMPEG, "-hide_banner", "-i", path], capture_output=True, text=True, errors="ignore").stderr
    m = re.search(r"Video:.*?([\d.]+) fps", r)
    return m.group(1) if m else "30"


def rotazione(path):
    """Gradi di rotazione salvati nel file (i telefoni spesso salvano il video 'sdraiato' + un'indicazione)."""
    r = subprocess.run([FFMPEG, "-hide_banner", "-i", path], capture_output=True, text=True, errors="ignore").stderr
    m = re.search(r"displaymatrix: rotation of (-?[\d.]+) degrees", r) or re.search(r"rotate\s*:\s*(-?\d+)", r)
    return int(round(float(m.group(1)))) % 360 if m else 0


def raddrizza(gradi):
    """Filtro ffmpeg che applica a mano la rotazione (con -noautorotate): risultato identico su ogni computer."""
    # displaymatrix -90 (= 270) significa: ruotare di 90 gradi in senso orario per vederlo dritto
    return {90: "transpose=2", 270: "transpose=1", 180: "hflip,vflip"}.get(gradi, "")


def has_audio(path):
    r = subprocess.run([FFMPEG, "-hide_banner", "-i", path], capture_output=True, text=True, errors="ignore")
    return "Audio:" in r.stderr


HDR_TO_SDR = ("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
              "tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p")


def extract_frames(path, seconds, n=16, start=0.0, vf=None):
    """n fotogrammi presi SOLO dal pezzo che finira' nel reel (da start a start+seconds)."""
    tmp = tempfile.mkdtemp()
    frames = []
    for i in range(n):
        out = os.path.join(tmp, f"f{i:02d}.png")
        subprocess.run([FFMPEG, "-v", "error", "-ss", f"{start + seconds * (i + 0.5) / n:.2f}", "-i", path,
                        *(["-vf", vf] if vf else []), "-frames:v", "1", out], capture_output=True)
        img = cv2.imread(out)
        if img is not None:
            frames.append(img)
    shutil.rmtree(tmp, ignore_errors=True)
    return frames


def detect_faces(frames):
    boxes = []
    for img in frames:
        h, w = img.shape[:2]
        s = 720 / max(h, w)
        gray = cv2.equalizeHist(cv2.cvtColor(cv2.resize(img, (int(w * s), int(h * s))), cv2.COLOR_BGR2GRAY))
        sh, sw = gray.shape
        mins = int(min(sh, sw) * 0.08)
        for i, c in enumerate(_casc):
            variants = ((gray, False), (cv2.flip(gray, 1), True)) if i == 2 else ((gray, False),)
            for g, flip in variants:
                for (x, y, fw, fh) in c.detectMultiScale(g, 1.1, 6, minSize=(mins, mins)):
                    if flip:
                        x = sw - x - fw
                    x, y, fw, fh = x / sw, y / sh, fw / sw, fh / sh
                    boxes.append((x - fw * 0.25, y - fh * 0.35, x + fw * 1.25, y + fh * 1.45))
    return boxes


def _overlap(a, b):
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


def choose_position(block_h, faces):
    # 20/10/2026: SEMPRE prima in alto (dati di 98 Short: testo in alto mediana 988 views, in basso 485). Prima, con il
    # viso nella meta' alta si partiva dal basso anche quando sopra il viso c'era spazio. Il viso non si copre mai:
    # se in alto non c'e' posto si scende (posizioni di TOP_FIRST in ordine).
    left, right = 0.5 - TEXT_MAX_W / 2 - 0.03, 0.5 + TEXT_MAX_W / 2 + 0.03
    order = TOP_FIRST
    best, best_score = None, None
    for y in order:
        y = min(max(y, SAFE_TOP), SAFE_BOTTOM - block_h)
        score = sum(_overlap((left, y, right, y + block_h), f) for f in faces)
        if score == 0:
            return y, 0.0
        if best_score is None or score < best_score:
            best, best_score = y, score
    return best, best_score


# Stile del testo sul video: "riquadro" (scuro semitrasparente), "contorno" (senza riquadro, ombra forte),
# "evidenziato" (ogni riga su una fascia bianca, testo nero), "vetro" (riquadro chiaro, testo scuro)
STILE = os.environ.get("STILE_TESTO") or "riquadro"


def _a_capo_semplice(d, text, font, max_px):
    lines, cur = [], ""
    for wd in text.split():
        t = (cur + " " + wd).strip()
        if d.textlength(t, font=font) <= max_px:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    return lines


def _a_capo(d, text, font, max_px):
    """Righe EQUILIBRATE (19/10/2026): stesso numero di righe ma la larghezza piu' stretta possibile, cosi' l'ultima
    riga non resta con una parola sola (es. "...tra lui e la tua / pace.")."""
    lines = _a_capo_semplice(d, text, font, max_px)
    if len(lines) < 2:
        return lines
    lo, hi = max_px * 0.4, max_px
    for _ in range(12):
        mid = (lo + hi) / 2
        if len(_a_capo_semplice(d, text, font, mid)) <= len(lines):
            hi = mid
        else:
            lo = mid
    return _a_capo_semplice(d, text, font, hi)


def build_overlay_2tempi(W, H, prima, seconda, faces, serie=None):
    """Formato GANCIO: (immagine con solo la prima parte, immagine con tutto, y_frac, score). Stesso stile del
    riquadro normale; la seconda parte va a capo sotto la prima e il riquadro si allunga."""
    fsize = int(W * DIM_TESTO)
    font = ImageFont.truetype(FONT, fsize)
    tmp = ImageDraw.Draw(Image.new("RGBA", (W, H)))
    la, lb = _a_capo(tmp, prima, font, W * TEXT_MAX_W), _a_capo(tmp, seconda, font, W * TEXT_MAX_W)
    lh, pad_x, pad_y = int(fsize * 1.28), int(fsize * 0.6), int(fsize * 0.45)
    fs = int(W * DIM_SERIE)
    eh = int(fs * 1.7) + int(fsize * 0.3) if serie else 0
    y_frac, score = choose_position((lh * (len(la) + len(lb)) + pad_y * 2 + eh) / H, faces)
    immagini = []
    for righe in (la, la + lb):
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        y = int(y_frac * H)
        if serie:
            font_s = ImageFont.truetype(FONT, fs)
            ws = d.textlength(serie, font=font_s)
            d.rounded_rectangle([(W - ws) / 2 - fs * 0.7, y, (W + ws) / 2 + fs * 0.7, y + int(fs * 1.7)],
                                radius=int(fs * 0.85), fill=(255, 255, 255, 235))
            d.text(((W - ws) / 2, y + int(fs * 0.3)), serie, font=font_s, fill=(15, 15, 15, 255))
            y += eh
        larghe = [d.textlength(x, font=font) for x in righe]
        bw = max(larghe) + pad_x * 2
        d.rounded_rectangle([(W - bw) / 2, y, (W + bw) / 2, y + lh * len(righe) + pad_y * 2], radius=int(lh * 0.35),
                            fill=(0, 0, 0, 150))
        for i, (x, w) in enumerate(zip(righe, larghe)):
            d.text(((W - w) / 2, y + pad_y + i * lh), x, font=font, fill=(255, 255, 255, 255))
        immagini.append(img)
    return immagini[0], immagini[1], y_frac, score


def build_overlay_serie(W, H, serie):
    """Solo l'etichetta della serie in alto (formato PARLATO: il testo sono i sottotitoli)."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if serie:
        d = ImageDraw.Draw(img)
        fs = int(W * DIM_SERIE)
        font_s = ImageFont.truetype(FONT, fs)
        ws = d.textlength(serie, font=font_s)
        y = int(H * 0.08)
        d.rounded_rectangle([(W - ws) / 2 - fs * 0.7, y, (W + ws) / 2 + fs * 0.7, y + int(fs * 1.7)],
                            radius=int(fs * 0.85), fill=(255, 255, 255, 235))
        d.text(((W - ws) / 2, y + int(fs * 0.3)), serie, font=font_s, fill=(15, 15, 15, 255))
    return img


def dividi_frase(testo):
    """('prima parte', 'seconda parte') per il formato GANCIO, oppure None se la frase non si divide bene."""
    t = testo.strip()
    m = re.search(r"[.!?:](?=\s+\S)", t)
    if m:
        a, b = t[:m.end()], t[m.end():]
    elif "," in t:
        a, b = t[:t.index(",") + 1], t[t.index(",") + 1:]
    else:
        return None
    a, b = a.strip(), b.strip()
    return (a, b) if len(a.split()) >= 2 and len(b.split()) >= 2 else None


def ha_audio(path):
    r = subprocess.run([FFMPEG, "-hide_banner", "-i", path], capture_output=True, text=True, errors="ignore").stderr
    return "Audio:" in r


def build_overlay(W, H, text, faces, stile=None, autore=None, serie=None):
    """serie: piccola etichetta sopra la frase (es. "GIORNO 12 / 365"), la "serie" che da' un motivo per seguire."""
    stile = stile or STILE
    fsize = int(W * DIM_TESTO * (1.12 if stile == "contorno" else 1.0))
    font = ImageFont.truetype(FONT, fsize)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if autore:                                   # citazione: tra virgolette, con l'autore sotto
        text = "“" + text.strip().strip('"“”') + "”"
    lines = _a_capo(d, text, font, W * TEXT_MAX_W)
    lh = int(fsize * (1.55 if stile == "evidenziato" else 1.28))
    pad_x, pad_y = int(fsize * 0.6), int(fsize * 0.45)
    font_a = ImageFont.truetype(FONT, int(fsize * 0.72))
    riga_a = "— " + autore if autore else ""
    ah = int(fsize * 1.25) if autore else 0      # spazio per la riga dell'autore
    block_h = lh * len(lines) + pad_y * 2 + ah
    fs = int(W * DIM_SERIE)
    eh = int(fs * 1.7) + int(fsize * 0.3) if serie else 0      # altezza etichetta della serie + spazio
    y_frac, score = choose_position((block_h + eh) / H, faces)
    y = int(y_frac * H)
    if serie:      # etichetta sopra il riquadro, poi la frase subito sotto
        font_s = ImageFont.truetype(FONT, fs)
        ws = d.textlength(serie, font=font_s)
        d.rounded_rectangle([(W - ws) / 2 - fs * 0.7, y, (W + ws) / 2 + fs * 0.7, y + int(fs * 1.7)],
                            radius=int(fs * 0.85), fill=(255, 255, 255, 235))
        d.text(((W - ws) / 2, y + int(fs * 0.3)), serie, font=font_s, fill=(15, 15, 15, 255))
        y += eh
    widths = [d.textlength(l, font=font) for l in lines]
    wa = d.textlength(riga_a, font=font_a) if autore else 0
    bw = max(widths + [wa]) + pad_x * 2
    x0 = (W - bw) / 2
    ty = lambda i: y + pad_y + i * lh

    if stile == "contorno":
        ombra = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        do = ImageDraw.Draw(ombra)
        for i, (l, w) in enumerate(zip(lines, widths)):
            do.text(((W - w) / 2, ty(i) + fsize * 0.06), l, font=font, fill=(0, 0, 0, 170))
        from PIL import ImageFilter
        img.alpha_composite(ombra.filter(ImageFilter.GaussianBlur(fsize * 0.18)))
        d = ImageDraw.Draw(img)
        for i, (l, w) in enumerate(zip(lines, widths)):
            d.text(((W - w) / 2, ty(i)), l, font=font, fill=(255, 255, 255, 255),
                   stroke_width=max(2, int(fsize * 0.045)), stroke_fill=(0, 0, 0, 200))
    elif stile == "evidenziato":
        for i, (l, w) in enumerate(zip(lines, widths)):
            px, py = fsize * 0.35, fsize * 0.12
            d.rounded_rectangle([(W - w) / 2 - px, ty(i) - py, (W + w) / 2 + px, ty(i) + fsize * 1.25],
                                radius=int(fsize * 0.25), fill=(255, 255, 255, 240))
        for i, (l, w) in enumerate(zip(lines, widths)):
            d.text(((W - w) / 2, ty(i)), l, font=font, fill=(17, 17, 17, 255))
    elif stile == "vetro":
        d.rounded_rectangle([x0, y, x0 + bw, y + block_h], radius=int(lh * 0.45), fill=(255, 255, 255, 205))
        for i, (l, w) in enumerate(zip(lines, widths)):
            d.text(((W - w) / 2, ty(i)), l, font=font, fill=(20, 20, 20, 255))
    else:   # "riquadro"
        d.rounded_rectangle([x0, y, x0 + bw, y + block_h], radius=int(lh * 0.35), fill=(0, 0, 0, 150))
        for i, (l, w) in enumerate(zip(lines, widths)):
            d.text(((W - w) / 2, ty(i)), l, font=font, fill=(255, 255, 255, 255))
    if autore:
        d = ImageDraw.Draw(img)
        ya = y + pad_y + len(lines) * lh + int(fsize * 0.2)
        chiaro = stile in ("vetro", "evidenziato")
        if stile == "evidenziato":
            d.rounded_rectangle([(W - wa) / 2 - fsize * 0.3, ya - fsize * 0.1, (W + wa) / 2 + fsize * 0.3,
                                 ya + fsize * 0.95], radius=int(fsize * 0.2), fill=(255, 255, 255, 240))
        extra = {"stroke_width": max(1, int(fsize * 0.035)), "stroke_fill": (0, 0, 0, 200)} if stile == "contorno" else {}
        d.text(((W - wa) / 2, ya), riga_a, font=font_a,
               fill=(40, 40, 40, 255) if chiaro else (255, 255, 255, 215), **extra)
    return img, y_frac, score


TEMPO_MAX_MONTAGGIO = 900  # 15 minuti al massimo per un montaggio (GitHub ferma tutto a 40)
LATO_USCITA = 1080       # lato corto del reel finito (1080x1920, il massimo che usano Instagram e TikTok)
ZOOM = 0                 # zoom lento avanti-indietro (es. 0.20); DISATTIVATO il 4/10/2026: ad Alessandro non piace
MUSIC_LOOP = 8.0          # i brani di musica/ durano esattamente 8 s e si ripetono senza stacchi
MUSIC_VOL = 0.9           # i brani sono gia' a -14 LUFS (normalizza_musica.py): il reel esce a circa -15 LUFS
LIMITATORE = "alimiter=limit=0.89:level=disabled"   # picchi sotto -1 dB: niente distorsione dopo la compressione


TAGLIO_INIZIO = 2.0      # si tolgono sempre i primi 2 secondi (il momento in cui si preme "registra")
DURATA_MAX = 5.0         # dal 13/10/2026 reel da 5 secondi (prima 8): es. video da 12 s -> si usa da 2 a 7
LOOP_SFUMATURA = 0.3     # secondi di sfumatura fine -> inizio (loop senza stacco)
DURATA_ARCHIVIO = 15.0   # 18/10: all'archivio 15 s (prima 8): con uno Short ogni ora servono piu' pezzi diversi per video


def segmento(seconds, durata=None):
    """(inizio, durata) del pezzo da usare. Se il video e' troppo corto per togliere 2 s, non si taglia l'inizio."""
    start = TAGLIO_INIZIO if seconds > TAGLIO_INIZIO + 1.0 else 0.0
    return start, min(durata or DURATA_MAX, seconds - start)


def segmento_migliore(src, seconds, vf=None, durata=None, a_caso=False):
    """(inizio, durata) dei 5 secondi PIU' FORTI del video (16/10/2026): viso visibile, movimento, immagine nitida,
    niente primo secondo (quando si preme "registra"). Video corti: come segmento().
    a_caso=True (riuso dall'archivio): uno dei pezzi migliori scelto a caso, cosi' ogni riuso e' diverso."""
    durata = durata or DURATA_MAX
    if seconds < durata + LOOP_SFUMATURA + 2.5:
        return segmento(seconds, durata)
    n = int(min(24, max(10, seconds * 2)))
    frames = extract_frames(src, seconds, n, 0.0, vf)
    if len(frames) < 6:
        return segmento(seconds, durata)
    tempi = [seconds * (i + 0.5) / len(frames) for i in range(len(frames))]
    piccoli = [cv2.cvtColor(cv2.resize(f, (90, 160)), cv2.COLOR_BGR2GRAY).astype(np.float32) for f in frames]
    viso = [1.0 if detect_faces([f]) else 0.0 for f in frames]
    nitido = [float(cv2.Laplacian(g, cv2.CV_32F).var()) for g in piccoli]
    moto = [0.0] + [float(np.abs(piccoli[i] - piccoli[i - 1]).mean()) for i in range(1, len(piccoli))]
    norm = lambda v: [x / (max(v) or 1) for x in v]
    nitido, moto = norm(nitido), norm(moto)
    punti = [viso[i] + 0.6 * moto[i] + 0.4 * nitido[i] - (1.0 if tempi[i] < 1.0 else 0.0) for i in range(len(frames))]
    migliore, inizio = None, None
    finestre = []
    s = 0.8
    while s + durata + LOOP_SFUMATURA <= seconds:
        dentro = [p for t, p in zip(tempi, punti) if s <= t <= s + durata]
        if dentro:
            v = sum(dentro) / len(dentro)
            finestre.append((v, s))
            if migliore is None or v > migliore + 0.02:      # a parita' resta il pezzo piu' vicino all'inizio
                migliore, inizio = v, s
        s += 0.5
    if a_caso and finestre:
        buone = [x for v, x in finestre if v >= migliore - 0.25]
        inizio = random.choice(buone)
    return (round(inizio, 2), durata) if inizio is not None else segmento(seconds, durata)


def segmento_archivio(seconds, durata=None):
    """Clip d'archivio (gia' tagliata, di solito 8 s): un pezzo da DURATA_MAX preso in un punto a caso,
    cosi' lo stesso video riusato non e' mai identico."""
    length = min(durata or DURATA_MAX, seconds)
    return round(random.uniform(0, max(0.0, seconds - length - LOOP_SFUMATURA)), 2), length   # spazio per il loop


def scegli_copertina(frames, length):
    """Momento migliore per la copertina (ms dall'inizio del reel): nitido, ben esposto e con il viso visibile."""
    best, best_s = 0, -1e9
    for i, f in enumerate(frames):
        small = cv2.resize(f, (360, int(360 * f.shape[0] / f.shape[1])))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        nitidezza = min(cv2.Laplacian(gray, cv2.CV_64F).var() / 300.0, 3.0)
        luce = 1.0 - abs(gray.mean() / 255.0 - 0.5) * 2          # 1 = esposizione media ideale
        viso = 1.5 if detect_faces([f]) else 0.0
        s = nitidezza + luce + viso
        if s > best_s:
            best, best_s = i, s
    t = length * (best + 0.5) / len(frames)
    return int(min(max(t, 0.3), max(length - 0.3, 0.3)) * 1000)


def crea_clip_archivio(src, dst, inizio=None):
    """Copia per l'archivio alla MASSIMA qualita': 8 s dopo i primi 2 (il reel ne usa 5) copiato dall'originale
    SENZA ricomprimere (stessa risoluzione 4K, stessi colori/HDR, stessa rotazione), senza audio (circa 20-30 MB).
    Si potra' rimontare con una frase nuova (make_video da_archivio=True)."""
    seconds, hdr = probe(src)
    start, length = segmento(seconds, DURATA_ARCHIVIO)
    if inizio is not None:          # intorno al pezzo usato nel reel (il migliore)
        start = max(0.0, min(inizio - 1.5, seconds - DURATA_ARCHIVIO))
        length = min(DURATA_ARCHIVIO, seconds - start)
    r = subprocess.run([FFMPEG, "-y", "-v", "error", "-ss", f"{start:.3f}", "-i", src, "-t", f"{length:.3f}",
                        "-map", "0:v:0", "-map", "0:a:0?", "-c", "copy", dst],   # 18/10: anche l'audio (formati AMBIENTE/PARLATO)
                       capture_output=True, text=True, errors="ignore", timeout=TEMPO_MAX_MONTAGGIO)
    if r.returncode != 0 or not os.path.exists(dst):
        raise RuntimeError("clip archivio: " + r.stderr[-300:])
    return dst


def senza_audio(src, dst):
    """Stesso reel senza traccia audio (video copiato, nessuna perdita): per TikTok, dove Alessandro aggiunge
    a mano un audio di tendenza dall'app."""
    r = subprocess.run([FFMPEG, "-y", "-v", "error", "-i", src, "-map", "0:v:0", "-c:v", "copy", "-an",
                        "-movflags", "+faststart", dst], capture_output=True, text=True, errors="ignore",
                       timeout=TEMPO_MAX_MONTAGGIO)
    if r.returncode != 0 or not os.path.exists(dst) or os.path.getsize(dst) < 50_000:
        raise RuntimeError("versione senza audio: " + r.stderr[-300:])
    return dst


def cambia_musica(src, music, dst):
    """Stesso reel (video copiato, senza ricomprimere) con un'altra musica: es. la versione per Facebook/Instagram
    con i nostri brani al posto di quelli della Raccolta audio di YouTube."""
    length, _ = probe(src)
    r = subprocess.run([FFMPEG, "-y", "-v", "error", "-i", src, "-stream_loop", "-1", "-i", music,
                        "-filter_complex", f"[1:a]volume={MUSIC_VOL},{LIMITATORE},"
                        f"afade=t=out:st={max(0.0, length - 0.3):.2f}:d=0.3[a]",
                        "-map", "0:v:0", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
                        "-t", f"{length:.3f}", "-movflags", "+faststart", dst],
                       capture_output=True, text=True, errors="ignore", timeout=TEMPO_MAX_MONTAGGIO)
    if r.returncode != 0 or not os.path.exists(dst) or os.path.getsize(dst) < 50_000:
        raise RuntimeError("cambio musica: " + r.stderr[-300:])
    return dst


def make_video(src, hook, dst, preview=None, music=None, colore=True, nome="", scena_rilevata=None, autore=None,
               da_archivio=False, serie=None, formato=None):
    """formato (18/10/2026): None/"frase" = 5 s; {"nome": "gancio", "durata": 8, "seconda": testo, "t": 3.0};
    {"nome": "ambiente", "durata": 6, "audio_originale": 0.35} (suono vero della ripresa sotto la musica)."""
    """Come _make_video, ma con piani di riserva: se ffmpeg fallisce si riprova togliendo, nell'ordine,
    zoom e loop, la color correction e la musica. Cosi' un problema su un effetto non blocca mai la pubblicazione."""
    if music and (not os.path.exists(music) or os.path.getsize(music) < 1000):   # brano mancante: niente musica,
        music = None                                                              # ma zoom e colore restano
    prove = [dict(zoom=True, colore=colore, music=music), dict(zoom=False, colore=colore, music=music),
             dict(zoom=False, colore=False, music=music), dict(zoom=False, colore=False, music=None)]
    errori = []
    for i, p in enumerate(prove):
        if i and p == prove[i - 1]:
            continue
        try:
            info = _make_video(src, hook, dst, preview, p["music"], p["colore"], nome, scena_rilevata, autore, p["zoom"],
                               da_archivio, serie, formato if p["zoom"] else None)
            if errori:
                info["ripiego"] = {"senza": [k for k in ("zoom", "colore", "music") if not p[k]], "errori": errori}
            return info
        except Exception as e:
            errori.append(str(e)[:300])
    raise RuntimeError("montaggio fallito: " + " | ".join(errori))


def _make_video(src, hook, dst, preview=None, music=None, colore=True, nome="", scena_rilevata=None, autore=None,
                zoom=True, da_archivio=False, serie=None, formato=None):
    """Crea dst (mp4 H.264 alta qualita') con il gancio e, se indicata, la musica in loop. Restituisce info."""
    seconds, hdr = probe(src)
    formato = formato or {}
    durata = formato.get("durata")
    parlato = formato.get("nome") == "parlato"
    momento = formato.get("nome") == "momento"
    if parlato or momento:              # PARLATO: dalla prima all'ultima parola; MOMENTO: il video come l'ha girato lui
        start = max(0.0, min(float(formato.get("inizio", 0)), seconds - 1))
        length = max(1.0, min(float(durata or seconds), seconds - start))
    elif da_archivio:                   # clip d'archivio: gia' tagliata, pezzo a caso
        if seconds > 20:                # originale intero (archivio dal 18/10): uno dei pezzi migliori, a caso
            start, length = segmento_migliore(src, seconds, HDR_TO_SDR if hdr else None, durata, a_caso=True)
        else:                           # clip gia' tagliata (8-15 s): un punto a caso
            start, length = segmento_archivio(seconds, durata)
    else:                               # video nuovo: i secondi migliori
        start, length = segmento_migliore(src, seconds, HDR_TO_SDR if hdr else None, durata)
    frames = extract_frames(src, length, start=start, vf=HDR_TO_SDR if hdr else None)
    if not frames:
        raise RuntimeError("video illeggibile")
    H, W = frames[0].shape[:2]
    faces = detect_faces(frames)
    taglio_x = None
    if W / H > 9 / 16 + 0.02:       # video orizzontale o quadrato: si ritaglia un 9:16 verticale centrato sul viso
        cw = int(H * 9 / 16) // 2 * 2
        cx = float(np.median([(f[0] + f[2]) / 2 for f in faces])) * W if faces else W / 2
        taglio_x = int(min(max(cx - cw / 2, 0), W - cw)) // 2 * 2
        frames = [f[:, taglio_x:taglio_x + cw] for f in frames]
        W = cw
        faces = detect_faces(frames)
    # formato finale sempre largo 1080 (1080x1920 per i video 9:16): 4K ridotto, 720p e ritagli ingranditi
    W0, H0 = W, H
    W, H = LATO_USCITA, int(round(LATO_USCITA * H0 / W0 / 2)) * 2
    if abs(W0 / H0 - 9 / 16) < 0.03:     # quasi 9:16 (es. dopo il ritaglio): esattamente 1080x1920
        H = LATO_USCITA * 16 // 9
    png2, t2 = None, None
    if parlato:                     # il testo sono i sottotitoli: in alto solo la serie
        overlay, y_frac, score = build_overlay_serie(W, H, serie), 0.08, 0
    elif formato.get("seconda"):      # GANCIO: prima parte subito, la seconda compare dopo t secondi
        ov1, ov2, y_frac, score = build_overlay_2tempi(W, H, hook, formato["seconda"], faces, serie)
        png2 = os.path.join(tempfile.gettempdir(), "overlay_reel_2.png")
        ov2.save(png2)
        overlay, t2 = ov1, min(float(formato.get("t", 3.0)), length - 1.5)
    else:
        overlay, y_frac, score = build_overlay(W, H, hook, faces, autore=autore, serie=serie)
    png = os.path.join(tempfile.gettempdir(), "overlay_reel.png")
    overlay.save(png)
    cmd = [FFMPEG, "-y", "-v", "error", "-display_rotation", "0", "-ss", f"{start:.3f}", "-i", src, "-i", png]
    n_in = 2
    if png2:
        cmd += ["-i", png2]
        i_png2, n_in = n_in, n_in + 1
    chain = [raddrizza(rotazione(src))] if raddrizza(rotazione(src)) else []
    if hdr:     # video HDR dell'iPhone (HLG/PQ): conversione a colori normali, altrimenti esce grigio e sbiadito
        chain.append(HDR_TO_SDR)
    if taglio_x is not None:
        chain.append(f"crop={cw}:ih:{taglio_x}:0")
    if zoom and ZOOM > 0 and length > 1:    # zoom lentissimo avanti e indietro: il video sembra "vivo" e il loop resta continuo
        # zoompan lavora sul video originale (4K) e restituisce gia' il formato finale: movimento fluido, niente
        # "scale" a ogni fotogramma (era lentissimo e su alcuni video mandava ffmpeg in crash)
        # sale e torna: inizio e fine identici, il loop non salta. Si usa il numero del fotogramma (on): il tempo
        # del video (it) su alcuni file non e' affidabile e lo zoom restava fermo
        fr = fps(src)
        if W0 < 2 * W:   # sotto il 4K: prima si raddoppia, cosi' lo zoom non fa micro-scatti (misurati: 2,5x piu' fluido)
            chain.append(f"scale={2 * W}:{2 * H}:flags=lanczos")
        z =f"1+{ZOOM}*sin(PI*on/{length * float(fr):.1f})"
        chain.append(f"zoompan=z='{z}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s={W}x{H}:fps={fr}")
    elif (W, H) != (W0, H0):
        chain.append(f"scale={W}:{H}:flags=lanczos")
    grade_info = None
    if colore:  # color correction automatica in base alla scena (grade.py)
        misure = grade.analizza(frames, faces)
        tipo, motivo = grade.scena(misure, nome)
        if scena_rilevata == "palestra" and tipo != "palestra":   # riconosciuta dalle immagini: profilo palestra
            tipo, motivo = "palestra", "scena riconosciuta: palestra"
        chain.append(grade.build_filter(misure, tipo))
        grade_info = grade.descrivi(misure, tipo, motivo)
    base = f"[0:v]{','.join(chain)}[base];[base]" if chain else "[0:v]"
    # LOOP PERFETTO (16/10/2026): si usa il pezzo da X a length+X e negli ultimi X secondi ci si sfuma sopra l'inizio
    # (fotogrammi 0..X): l'ultimo fotogramma coincide con il primo, quando lo Short ricomincia non si vede lo stacco.
    # L'inizio si legge con un SECONDO ingresso dello stesso file (con "split" ffmpeg 7.1 si bloccava). Durata invariata.
    # (solo al primo tentativo: se ffmpeg fallisce, il piano di riserva riprova SENZA loop, poi senza colore...)
    X = (LOOP_SFUMATURA if zoom and not (parlato or momento) and seconds - start >= length + LOOP_SFUMATURA
         and length > 2 else 0)
    filtri = ",".join(chain)
    if X:
        graph = (f"[0:v]{filtri + ',' if filtri else ''}trim=start={X}:end={length + X},setpts=PTS-STARTPTS[mn];"
                 f"[LOOPIN:v]{filtri + ',' if filtri else ''}trim=start=0:end={X},"
                 f"setpts=PTS-STARTPTS+{length - X:.3f}/TB,format=yuva420p,"
                 f"fade=t=in:st={length - X:.3f}:d={X}:alpha=1[hd];"
                 "[mn][hd]overlay=eof_action=pass[mx];[mx][1:v]overlay=0:0:format=auto,format=yuv420p[v]")
    else:
        graph = base + "[1:v]overlay=0:0:format=auto,format=yuv420p[v]"
    if png2:   # seconda parte del GANCIO: prima solo la prima parte, dopo t2 tutto il testo
        graph = graph.replace("[1:v]overlay=0:0:format=auto,format=yuv420p[v]",
                              f"[1:v]overlay=0:0:format=auto:enable='lt(t,{t2:.2f})'[t1];"
                              f"[t1][{i_png2}:v]overlay=0:0:format=auto:enable='gte(t,{t2:.2f})',format=yuv420p[v]")
    # audio: SOLO la nostra musica. L'audio originale del telefono (voci, rumori) non entra MAI nel reel
    # (regola di Alessandro). Senza musica il reel esce muto, mai con l'audio originale.
    # AMBIENTE (18/10/2026, scelta lasciata a Claude da Alessandro): il suono vero della ripresa (es. palestra) resta
    # sotto la musica. Negli altri formati l'audio originale non entra mai.
    vol_orig = float(formato.get("audio_originale") or 0) if ha_audio(src) else 0
    amap, fade = ["-an"], f"afade=t=out:st={max(0.0, length - 0.3):.2f}:d=0.3"
    if music:
        cmd += ["-stream_loop", "-1", "-i", music]
        graph += f";[{n_in}:a]volume={MUSIC_VOL * (0.8 if vol_orig else 1):.2f}[mu]"
        n_in += 1
    if vol_orig:
        norm = "loudnorm=I=-16:TP=-1.5:LRA=11," if parlato or momento else ""   # sempre allo stesso volume
        graph += (f";[0:a]atrim=start={X}:end={length + X},asetpts=PTS-STARTPTS,volume={vol_orig:.2f},{norm}"
                  "aresample=44100,aformat=channel_layouts=stereo[ao]")
        graph += (f";[mu][ao]amix=inputs=2:normalize=0:duration=first,{LIMITATORE},{fade}[a]" if music
                  else f";[ao]{LIMITATORE},{fade}[a]")
        amap = ["-map", "[a]"]
    elif music:
        graph += f";[mu]{LIMITATORE},{fade}[a]"
        amap = ["-map", "[a]"]
    if X:      # secondo ingresso: solo l'inizio del pezzo, per la sfumatura del loop
        cmd += ["-display_rotation", "0", "-ss", f"{start:.3f}", "-t", f"{X + 0.2:.3f}", "-i", src]
        graph = graph.replace("[LOOPIN:v]", f"[{n_in}:v]")
    cartella_sub = None
    if formato.get("sottotitoli"):      # PARLATO: sottotitoli bruciati nel video (file .ass + font nella stessa cartella)
        import parlato as parlato_mod
        cartella_sub = tempfile.mkdtemp()
        parlato_mod.file_ass(formato["sottotitoli"], start, os.path.join(cartella_sub, "sub.ass"), W, H)
        shutil.copy(FONT, os.path.join(cartella_sub, os.path.basename(FONT)))
        i = graph.rfind("format=yuv420p[v]")
        graph = graph[:i] + "format=yuv420p,subtitles=sub.ass:fontsdir=.[v]" + graph[i + len("format=yuv420p[v]"):]
    cmd += ["-filter_complex", graph, "-map", "[v]", *amap, "-t", f"{length:.3f}",
            "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-profile:v", "high",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-movflags", "+faststart", dst]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, errors="ignore", timeout=TEMPO_MAX_MONTAGGIO,
                           cwd=cartella_sub)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"ffmpeg: oltre {TEMPO_MAX_MONTAGGIO} s")
    if r.returncode != 0 or not os.path.exists(dst) or os.path.getsize(dst) < 50_000:
        raise RuntimeError("ffmpeg: " + r.stderr[-400:])
    if preview:   # anteprima presa dal reel finito (colori e testo come verranno pubblicati)
        subprocess.run([FFMPEG, "-y", "-v", "error", "-ss", f"{length / 2:.2f}", "-i", dst, "-frames:v", "1",
                        "-vf", f"scale={W // 3}:-2", preview], capture_output=True)
    return {"testo": "alto" if y_frac < 0.4 else "basso", "volti": len(faces),
            "tocca_viso": bool(score > 0), "hdr": hdr, "risoluzione": f"{W}x{H}", "taglio": f"da {start:.1f}s a {start + length:.1f}s",
            "durata": round(length, 2), "inizio": round(start, 2), "colore": grade_info, "copertina_ms": scegli_copertina(frames, length),
            "musica": os.path.basename(music) if music else None, "formato": formato.get("nome") or "frase",
            "audio_originale": vol_orig or None}


# ------------------------------------------------------------------ formato "REGOLE" (esperimento dal 17/10/2026)
REGOLE_DURATA = 13.0
REGOLE_TEMPI = (2.2, 5.6, 9.0)     # quando compare ognuna delle 3 righe (titolo subito, dal primo fotogramma)


def _tavola_regole(titolo, righe, n, serie=None):
    """Immagine trasparente 1080x1920 con il titolo (e la serie) e le prime n righe."""
    W, H = LATO_USCITA, int(LATO_USCITA * 16 / 9)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    k = RIDUZIONE_REGOLE
    font_t, font_r, font_s = (ImageFont.truetype(FONT, s) for s in (int(62 * k), int(50 * k), 34))
    lt, lr = int(76 * k), int(64 * k)            # interlinea del titolo e delle righe
    y = int(H * 0.13)
    if serie:
        ws = d.textlength(serie, font=font_s)
        d.rounded_rectangle([(W - ws) / 2 - 24, y, (W + ws) / 2 + 24, y + 58], radius=29, fill=(255, 255, 255, 235))
        d.text(((W - ws) / 2, y + 10), serie, font=font_s, fill=(15, 15, 15, 255))
        y += 80
    righe_t = _a_capo(d, titolo, font_t, W * 0.84)
    bw = max(d.textlength(x, font=font_t) for x in righe_t) + int(64 * k)
    th = len(righe_t) * lt + int(30 * k)
    d.rounded_rectangle([(W - bw) / 2, y, (W + bw) / 2, y + th], radius=28, fill=(255, 255, 255, 240))
    for i, x in enumerate(righe_t):
        d.text(((W - d.textlength(x, font=font_t)) / 2, y + int(14 * k) + i * lt), x, font=font_t, fill=(15, 15, 15, 255))
    y += th + 34
    for k, r in enumerate(righe[:n], 1):
        rr = _a_capo(d, f"{k}. {r}", font_r, W * 0.80)
        h = len(rr) * lr + int(36 * k)
        bw = max(d.textlength(x, font=font_r) for x in rr) + int(56 * k)
        d.rounded_rectangle([(W - bw) / 2, y, (W + bw) / 2, y + h], radius=24, fill=(0, 0, 0, 165))
        for i, x in enumerate(rr):
            d.text(((W - d.textlength(x, font=font_r)) / 2, y + int(18 * k) + i * lr), x, font=font_r,
                   fill=(255, 255, 255, 255))
        y += h + 26
    return img


def inizio_bello(c, secondi, hdr, durata, riserva):
    """Formati a piu' clip: nei video lunghi (es. originali interi dell'archivio) uno dei pezzi migliori, a caso;
    nei video corti (o se il calcolo non riesce) il punto di riserva."""
    if secondi <= 12:
        return riserva
    try:
        return segmento_migliore(c, secondi, HDR_TO_SDR if hdr else None, durata, a_caso=True)[0]
    except Exception:
        return riserva


def make_regole(clips, titolo, righe, dst, musiche=(), serie=None):
    """Reel "REGOLE": 3 clip (o meno, ripetute) di ~4.5 s con dissolvenza, titolo subito e 3 righe che compaiono
    una alla volta (REGOLE_TEMPI). musiche: 1-3 pezzi da 5 s (stesso brano) uniti con sfumatura."""
    W, H, DUR = LATO_USCITA, int(LATO_USCITA * 16 / 9), REGOLE_DURATA
    clips = (list(clips) * 3)[:3]
    seg, X = DUR / 3, 0.4
    tmp = tempfile.mkdtemp()
    cmd, catena = [FFMPEG, "-y", "-v", "error"], []
    for i, c in enumerate(clips):
        secondi, hdr = probe(c)
        inizio = inizio_bello(c, secondi, hdr, seg + X, max(0.0, min(1.0, secondi - seg - X)))
        cmd += ["-display_rotation", "0", "-ss", f"{inizio:.2f}", "-t", f"{seg + X:.2f}", "-i", c]
        f = [x for x in (raddrizza(rotazione(c)), HDR_TO_SDR if hdr else "") if x]
        f += [f"scale={W}:{H}:force_original_aspect_ratio=increase", f"crop={W}:{H}", "setsar=1", "fps=30",
              f"trim=0:{seg + X:.2f}", "setpts=PTS-STARTPTS", "format=yuv420p", "settb=AVTB", "fps=30",
              "tpad=stop_mode=clone:stop_duration=1"]       # clip un po' corta: si allunga l'ultimo fotogramma
        catena.append(f"[{i}:v]{','.join(f)},trim=0:{seg + X:.2f}[c{i}]")
    for n in range(4):
        p = os.path.join(tmp, f"t{n}.png")
        _tavola_regole(titolo, righe, n, serie).save(p)
        cmd += ["-i", p]
    g = ";".join(catena)
    g += (f";[c0][c1]xfade=transition=fade:duration={X}:offset={seg - X / 2:.2f}[x1]"
          f";[x1][c2]xfade=transition=fade:duration={X}:offset={2 * seg - X:.2f}[bg]")
    fasi, cur = (0.0,) + REGOLE_TEMPI + (DUR,), "bg"
    for n in range(4):
        g += f";[{cur}][{3 + n}:v]overlay=0:0:enable='between(t,{fasi[n]},{fasi[n + 1]})'[o{n}]"
        cur = f"o{n}"
    g += f";[{cur}]format=yuv420p[v]"
    amap = ["-an"]
    musiche = [m for m in musiche if m and os.path.exists(m)]
    if musiche:
        musiche = (musiche * 3)[:3]
        for m in musiche:
            cmd += ["-i", m]
        a0 = 7
        g += (f";[{a0}:a][{a0 + 1}:a]acrossfade=d=0.3[m1];[m1][{a0 + 2}:a]acrossfade=d=0.3,"
              f"volume={MUSIC_VOL},{LIMITATORE},apad,atrim=0:{DUR},afade=t=out:st={DUR - 0.5}:d=0.5[a]")
        amap = ["-map", "[a]"]
    cmd += ["-filter_complex", g, "-map", "[v]", *amap, "-t", f"{DUR}", "-c:v", "libx264", "-preset", "medium",
            "-crf", "18", "-profile:v", "high", "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-movflags", "+faststart", dst]
    r = subprocess.run(cmd, capture_output=True, text=True, errors="ignore", timeout=TEMPO_MAX_MONTAGGIO)
    shutil.rmtree(tmp, ignore_errors=True)
    if r.returncode != 0 or not os.path.exists(dst) or os.path.getsize(dst) < 50_000:
        raise RuntimeError("regole: " + r.stderr[-400:])
    return {"formato": "regole", "durata": DUR, "titolo": titolo, "musica": os.path.basename(musiche[0]) if musiche else None}


# ------------------------------------------------------------------ formato "MONTAGGIO" (18/10/2026)
MONTAGGIO_DURATA = 8.0


def make_montaggio(clips, frase, dst, musiche=(), serie=None):
    """3 clip da ~2,7 s a TAGLI NETTI (ritmo) con la frase fissa dal primo fotogramma. Restituisce info."""
    W, H, DUR = LATO_USCITA, int(LATO_USCITA * 16 / 9), MONTAGGIO_DURATA
    clips = (list(clips) * 3)[:3]
    seg = DUR / 3
    tmp = tempfile.mkdtemp()
    cmd, catena = [FFMPEG, "-y", "-v", "error"], []
    for i, c in enumerate(clips):
        secondi, hdr = probe(c)
        inizio = inizio_bello(c, secondi, hdr, seg + 0.2, max(0.0, min(1.0 + i * 0.7, secondi - seg - 0.2)))
        cmd += ["-display_rotation", "0", "-ss", f"{inizio:.2f}", "-t", f"{seg + 0.2:.2f}", "-i", c]
        f = [x for x in (raddrizza(rotazione(c)), HDR_TO_SDR if hdr else "") if x]
        f += [f"scale={W}:{H}:force_original_aspect_ratio=increase", f"crop={W}:{H}", "setsar=1", "fps=30",
              "format=yuv420p", "settb=AVTB", "fps=30", "tpad=stop_mode=clone:stop_duration=1",
              f"trim=0:{seg:.3f}", "setpts=PTS-STARTPTS"]
        catena.append(f"[{i}:v]{','.join(f)}[c{i}]")
    ov, _, _ = build_overlay(W, H, frase, [], serie=serie)
    png = os.path.join(tmp, "testo.png")
    ov.save(png)
    cmd += ["-i", png]
    g = ";".join(catena) + ";[c0][c1][c2]concat=n=3:v=1:a=0[bg];[bg][3:v]overlay=0:0:format=auto,format=yuv420p[v]"
    amap = ["-an"]
    musiche = [m for m in musiche if m and os.path.exists(m)]
    if musiche:
        musiche = (musiche * 2)[:2]
        for m in musiche:
            cmd += ["-i", m]
        g += (f";[4:a][5:a]acrossfade=d=0.3,volume={MUSIC_VOL},{LIMITATORE},apad,atrim=0:{DUR},"
              f"afade=t=out:st={DUR - 0.3}:d=0.3[a]")
        amap = ["-map", "[a]"]
    cmd += ["-filter_complex", g, "-map", "[v]", *amap, "-t", f"{DUR}", "-c:v", "libx264", "-preset", "medium",
            "-crf", "18", "-profile:v", "high", "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-movflags", "+faststart", dst]
    r = subprocess.run(cmd, capture_output=True, text=True, errors="ignore", timeout=TEMPO_MAX_MONTAGGIO)
    shutil.rmtree(tmp, ignore_errors=True)
    if r.returncode != 0 or not os.path.exists(dst) or os.path.getsize(dst) < 50_000:
        raise RuntimeError("montaggio: " + r.stderr[-400:])
    return {"formato": "montaggio", "durata": DUR, "musica": os.path.basename(musiche[0]) if musiche else None}
