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
DUR, PEZZI = 5.0, 4      # dal 13/10/2026 reel da 5 s: 4 pezzi da 5 s per brano


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
    return sorted(sul_colpo(x, s, sr) for s in scelti)


def sul_colpo(x, s, sr=8000, cerca=0.6):
    """Sposta l'inizio sul colpo (attacco) piu' forte entro +-0.6 s: il reel parte su un beat, non a meta' nota."""
    hop = sr // 100                                                       # 10 ms
    a, b = max(0, int((s - cerca) * sr)), min(len(x), int((s + cerca) * sr))
    seg = x[a:b]
    if len(seg) < hop * 4:
        return s
    e = np.sqrt(np.convolve(seg ** 2, np.ones(hop) / hop, "valid")[::hop])  # energia ogni 10 ms
    flux = np.maximum(np.diff(e), 0)                                        # quanto sale: attacchi
    if not len(flux) or flux.max() <= 0:
        return s
    return max(0.0, a / sr + (int(flux.argmax()) + 1) * hop / sr - 0.02)


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
