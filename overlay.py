"""Mette il testo-gancio sul video in una zona senza viso (viso in alto -> testo in basso e viceversa)."""
import os, re, shutil, subprocess, tempfile
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg
import grade

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
FONTS = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "font.ttf"),
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


def build_overlay(W, H, text, faces):
    fsize = int(W * 0.052)
    font = ImageFont.truetype(FONT, fsize)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    lines, cur = [], ""
    for wd in text.split():
        t = (cur + " " + wd).strip()
        if d.textlength(t, font=font) <= W * TEXT_MAX_W:
            cur = t
        else:
            lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    lh, pad_x, pad_y = int(fsize * 1.22), int(fsize * 0.55), int(fsize * 0.4)
    block_h = lh * len(lines) + pad_y * 2
    y_frac, score = choose_position(block_h / H, faces)
    y = int(y_frac * H)
    widths = [d.textlength(l, font=font) for l in lines]
    bw = max(widths) + pad_x * 2
    x0 = (W - bw) / 2
    d.rounded_rectangle([x0, y, x0 + bw, y + block_h], radius=int(lh * 0.35), fill=(0, 0, 0, 150))
    for i, (l, w) in enumerate(zip(lines, widths)):
        d.text(((W - w) / 2, y + pad_y + i * lh), l, font=font, fill=(255, 255, 255, 255))
    return img, y_frac, score


MUSIC_LOOP = 6.0          # i brani di musica/ durano esattamente 6 s e si ripetono senza stacchi
MUSIC_VOL = 0.6           # musica di sottofondo: presente ma non invadente
ORIG_VOL = 0.05           # audio originale dell'iPhone quasi azzerato (resta solo un filo di ambiente)


TAGLIO_INIZIO = 2.0      # si tolgono sempre i primi 2 secondi (il momento in cui si preme "registra")
DURATA_MAX = 6.0         # poi si tengono al massimo 6 secondi: es. video da 10 s -> si usa da 2 a 8


def segmento(seconds):
    """(inizio, durata) del pezzo da usare. Se il video e' troppo corto per togliere 2 s, non si taglia l'inizio."""
    start = TAGLIO_INIZIO if seconds > TAGLIO_INIZIO + 1.0 else 0.0
    return start, min(DURATA_MAX, seconds - start)


def make_video(src, hook, dst, preview=None, music=None, colore=True, nome=""):
    """Crea dst (mp4 H.264 alta qualita') con il gancio e, se indicata, la musica in loop. Restituisce info."""
    seconds, hdr = probe(src)
    start, length = segmento(seconds)
    frames = extract_frames(src, length, start=start, vf=HDR_TO_SDR if hdr else None)
    if not frames:
        raise RuntimeError("video illeggibile")
    H, W = frames[0].shape[:2]
    faces = detect_faces(frames)
    overlay, y_frac, score = build_overlay(W, H, hook, faces)
    png = os.path.join(tempfile.gettempdir(), "overlay_reel.png")
    overlay.save(png)
    cmd = [FFMPEG, "-y", "-v", "error", "-ss", f"{start:.3f}", "-i", src, "-i", png]
    chain = []
    if hdr:     # video HDR dell'iPhone (HLG/PQ): conversione a colori normali, altrimenti esce grigio e sbiadito
        chain.append(HDR_TO_SDR)
    grade_info = None
    if colore:  # color correction automatica in base alla scena (grade.py)
        misure = grade.analizza(frames, faces)
        tipo, motivo = grade.scena(misure, nome)
        chain.append(grade.build_filter(misure, tipo))
        grade_info = grade.descrivi(misure, tipo, motivo)
    base = f"[0:v]{','.join(chain)}[base];[base]" if chain else "[0:v]"
    graph = base + "[1:v]overlay=0:0:format=auto,format=yuv420p[v]"
    amap = ["-map", "0:a?"]
    if music:
        cmd += ["-stream_loop", "-1", "-i", music]
        if has_audio(src):
            graph += (f";[0:a]volume={ORIG_VOL}[a0];[2:a]volume={MUSIC_VOL}[a2];"
                      "[a0][a2]amix=inputs=2:duration=longest:normalize=0[a]")
        else:
            graph += f";[2:a]volume={MUSIC_VOL}[a]"
        amap = ["-map", "[a]"]
    cmd += ["-filter_complex", graph, "-map", "[v]", *amap, "-t", f"{length:.3f}",
            "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-profile:v", "high",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-movflags", "+faststart", dst]
    r = subprocess.run(cmd, capture_output=True, text=True, errors="ignore")
    if r.returncode != 0:
        raise RuntimeError("ffmpeg: " + r.stderr[-400:])
    if preview:   # anteprima presa dal reel finito (colori e testo come verranno pubblicati)
        subprocess.run([FFMPEG, "-y", "-v", "error", "-ss", f"{length / 2:.2f}", "-i", dst, "-frames:v", "1",
                        "-vf", f"scale={W // 3}:-2", preview], capture_output=True)
    return {"testo": "alto" if y_frac < 0.4 else "basso", "volti": len(faces),
            "tocca_viso": bool(score > 0), "hdr": hdr, "risoluzione": f"{W}x{H}", "taglio": f"da {start:.1f}s a {start + length:.1f}s",
            "durata": round(length, 2), "colore": grade_info,
            "musica": os.path.basename(music) if music else None}
