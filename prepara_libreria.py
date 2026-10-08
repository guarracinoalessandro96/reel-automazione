"""
Musica dalla Raccolta audio di YouTube (brani veri, gratuiti, ammessi su YouTube).
Da ogni brano scaricato in musica_youtube_originali/ (non va su GitHub: troppo pesante) estrae i 3 pezzi da 8 secondi
piu' energici (saltando intro e finale), li porta a -14 LUFS con picchi sotto -1,5 dB e li salva in
musica/yt_<categoria>/ come .m4a (circa 300 KB l'uno).
Categorie: yt_carica (hip hop / elettronica, mood arrabbiato o drammatico) | yt_epica (cinematografica / ispirante).
Uso: python prepara_libreria.py   (legge musica_youtube_originali/elenco.json con genere e mood di ogni brano)
"""
import glob, json, os, re, subprocess
import numpy as np
import imageio_ffmpeg

F = imageio_ffmpeg.get_ffmpeg_exe()
HERE = os.path.dirname(os.path.abspath(__file__))
ORIG = os.path.join(HERE, "musica_youtube_originali")
DUR, PEZZI = 8.0, 3


def categoria(info):
    g, m = info.get("g", ""), info.get("m", "")
    if "CINEMATIC" in g and "ANGRY" not in m:
        return "yt_epica"
    return "yt_carica"


def pcm(path):
    raw = subprocess.run([F, "-v", "error", "-i", path, "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
                         capture_output=True).stdout
    return np.frombuffer(raw, "<i2").astype(np.float32) / 32768


def migliori_inizi(x, sr=8000):
    n = len(x) / sr
    if n < DUR + 4:
        return [max(0.0, (n - DUR) / 2)]
    rms = np.sqrt(np.convolve(x ** 2, np.ones(sr) / sr, "valid")[::sr // 2])     # energia ogni mezzo secondo
    cand = []
    for i in np.arange(max(6.0, n * 0.12), n - DUR - 4, 0.5):                      # niente intro ne' finale
        a, b = int(i * 2), int((i + DUR) * 2)
        seg = rms[a:b]
        if len(seg):
            cand.append((float(seg.mean() - 0.5 * seg.std()), float(i)))           # forte e costante
    cand.sort(reverse=True)
    scelti = []
    for _, s in cand:
        if all(abs(s - t) >= DUR + 4 for t in scelti):
            scelti.append(s)
        if len(scelti) == PEZZI:
            break
    return sorted(scelti)


def guadagno(path, s):
    r = subprocess.run([F, "-hide_banner", "-ss", f"{s:.2f}", "-t", str(DUR), "-i", path, "-af",
                        "loudnorm=print_format=json", "-f", "null", "-"], capture_output=True, text=True, errors="ignore").stderr
    j = json.loads(r[r.rindex("{"):r.rindex("}") + 1])
    return min(-14.0 - float(j["input_i"]), -1.5 - float(j["input_tp"]))


def main():
    elenco = json.load(open(os.path.join(ORIG, "elenco.json"), encoding="utf-8")) if os.path.exists(
        os.path.join(ORIG, "elenco.json")) else {}
    for d in ("yt_carica", "yt_epica"):
        os.makedirs(os.path.join(HERE, "musica", d), exist_ok=True)
    fatti = 0
    for p in sorted(glob.glob(os.path.join(ORIG, "*.mp3"))):
        nome = os.path.splitext(os.path.basename(p))[0]
        cat = categoria(elenco.get(nome, {}))
        slug = re.sub(r"[^a-z0-9]+", "_", nome.lower()).strip("_")
        for k, s in enumerate(migliori_inizi(pcm(p)), 1):
            out = os.path.join(HERE, "musica", cat, f"{slug}_{k}.m4a")
            if os.path.exists(out):
                continue
            g = guadagno(p, s)
            subprocess.run([F, "-y", "-v", "error", "-ss", f"{s:.2f}", "-t", str(DUR), "-i", p, "-af",
                            f"volume={g:.2f}dB,afade=t=in:d=0.05,afade=t=out:st={DUR - 0.35}:d=0.35",
                            "-ac", "2", "-ar", "44100", "-c:a", "aac", "-b:a", "256k", out], check=True)
            fatti += 1
            print(f"{cat}/{os.path.basename(out)}  da {s:.0f}s  guadagno {g:+.1f} dB", flush=True)
    print(fatti, "pezzi creati")


if __name__ == "__main__":
    main()
