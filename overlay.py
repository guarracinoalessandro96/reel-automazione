"""Mette il testo-gancio sul video in una zona senza viso (viso in alto -> testo in basso e viceversa)."""
import os, re, shutil, subprocess, tempfile
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
    left, right = 0.5 - TEXT_MAX_W / 2 - 0.03, 0.5 + TEXT_MAX_W / 2 + 0.03
    order = TOP_FIRST
    if faces and float(np.median([(f[1] + f[3]) / 2 for f in faces])) < 0.5:
        order = BOTTOM_FIRST
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


def _a_capo(d, text, font, max_px):
    lines, cur = [], ""
    for wd in text.split():
        t = (cur + " " + wd).strip()
        if d.textlength(t, font=font) <= max_px:
            cur = t
        else:
            lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    return lines


def build_overlay(W, H, text, faces, stile=None, autore=None):
    stile = stile or STILE
    fsize = int(W * (0.056 if stile == "contorno" else 0.050))
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
    y_frac, score = choose_position(block_h / H, faces)
    y = int(y_frac * H)
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
DURATA_MAX = 8.0         # poi si tengono 8 secondi: es. video da 12 s -> si usa da 2 a 10 (reel e musica: 8 s)


def segmento(seconds):
    """(inizio, durata) del pezzo da usare. Se il video e' troppo corto per togliere 2 s, non si taglia l'inizio."""
    start = TAGLIO_INIZIO if seconds > TAGLIO_INIZIO + 1.0 else 0.0
    return start, min(DURATA_MAX, seconds - start)


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


def make_video(src, hook, dst, preview=None, music=None, colore=True, nome="", scena_rilevata=None, autore=None):
    """Come _make_video, ma con piani di riserva: se ffmpeg fallisce si riprova togliendo, nell'ordine,
    lo zoom, la color correction e la musica. Cosi' un problema su un effetto non blocca mai la pubblicazione."""
    if music and (not os.path.exists(music) or os.path.getsize(music) < 1000):   # brano mancante: niente musica,
        music = None                                                              # ma zoom e colore restano
    prove = [dict(zoom=True, colore=colore, music=music), dict(zoom=False, colore=colore, music=music),
             dict(zoom=False, colore=False, music=music), dict(zoom=False, colore=False, music=None)]
    errori = []
    for i, p in enumerate(prove):
        if i and p == prove[i - 1]:
            continue
        try:
            info = _make_video(src, hook, dst, preview, p["music"], p["colore"], nome, scena_rilevata, autore, p["zoom"])
            if errori:
                info["ripiego"] = {"senza": [k for k in ("zoom", "colore", "music") if not p[k]], "errori": errori}
            return info
        except Exception as e:
            errori.append(str(e)[:300])
    raise RuntimeError("montaggio fallito: " + " | ".join(errori))


def _make_video(src, hook, dst, preview=None, music=None, colore=True, nome="", scena_rilevata=None, autore=None,
                zoom=True):
    """Crea dst (mp4 H.264 alta qualita') con il gancio e, se indicata, la musica in loop. Restituisce info."""
    seconds, hdr = probe(src)
    start, length = segmento(seconds)
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
    overlay, y_frac, score = build_overlay(W, H, hook, faces, autore=autore)
    png = os.path.join(tempfile.gettempdir(), "overlay_reel.png")
    overlay.save(png)
    cmd = [FFMPEG, "-y", "-v", "error", "-display_rotation", "0", "-ss", f"{start:.3f}", "-i", src, "-i", png]
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
    graph = base + "[1:v]overlay=0:0:format=auto,format=yuv420p[v]"
    # audio: SOLO la nostra musica. L'audio originale del telefono (voci, rumori) non entra MAI nel reel
    # (regola di Alessandro). Senza musica il reel esce muto, mai con l'audio originale.
    amap = ["-an"]
    if music:
        cmd += ["-stream_loop", "-1", "-i", music]
        graph += f";[2:a]volume={MUSIC_VOL},{LIMITATORE}[a]"
        amap = ["-map", "[a]"]
    cmd += ["-filter_complex", graph, "-map", "[v]", *amap, "-t", f"{length:.3f}",
            "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-profile:v", "high",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-movflags", "+faststart", dst]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, errors="ignore", timeout=TEMPO_MAX_MONTAGGIO)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"ffmpeg: oltre {TEMPO_MAX_MONTAGGIO} s")
    if r.returncode != 0 or not os.path.exists(dst) or os.path.getsize(dst) < 50_000:
        raise RuntimeError("ffmpeg: " + r.stderr[-400:])
    if preview:   # anteprima presa dal reel finito (colori e testo come verranno pubblicati)
        subprocess.run([FFMPEG, "-y", "-v", "error", "-ss", f"{length / 2:.2f}", "-i", dst, "-frames:v", "1",
                        "-vf", f"scale={W // 3}:-2", preview], capture_output=True)
    return {"testo": "alto" if y_frac < 0.4 else "basso", "volti": len(faces),
            "tocca_viso": bool(score > 0), "hdr": hdr, "risoluzione": f"{W}x{H}", "taglio": f"da {start:.1f}s a {start + length:.1f}s",
            "durata": round(length, 2), "colore": grade_info, "copertina_ms": scegli_copertina(frames, length),
            "musica": os.path.basename(music) if music else None}
