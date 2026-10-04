"""
Porta tutti i brani di musica/ allo stesso volume percepito: -14 LUFS (lo standard di Instagram, TikTok e YouTube),
con i picchi veri sotto -1,5 dBTP (niente distorsione dopo la compressione AAC delle piattaforme).
Solo un guadagno uniforme su tutto il brano: il loop resta perfetto.

Uso: python normalizza_musica.py      (da rilanciare dopo genera_musica.py / genera_generi.py)
"""
import glob, json, os, subprocess, wave
import numpy as np
import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
HERE = os.path.dirname(os.path.abspath(__file__))
OBIETTIVO_LUFS = -14.0
PICCO_MAX = -1.5


def misura(path):
    r = subprocess.run([FFMPEG, "-hide_banner", "-stream_loop", "1", "-i", path, "-af", "loudnorm=print_format=json",
                        "-f", "null", "-"], capture_output=True, text=True, errors="ignore").stderr
    j = json.loads(r[r.rindex("{"):r.rindex("}") + 1])
    return float(j["input_i"]), float(j["input_tp"])


def normalizza(path):
    lufs, tp = misura(path)
    gain = OBIETTIVO_LUFS - lufs
    gain = min(gain, PICCO_MAX - tp)                 # se i picchi andrebbero troppo in alto, un filo piu' piano
    if abs(gain) < 0.1:
        return lufs, tp, 0.0
    raw = subprocess.run([FFMPEG, "-v", "error", "-i", path, "-f", "s16le", "-ac", "2", "-ar", "44100", "-"],
                         capture_output=True, check=True).stdout
    a = np.frombuffer(raw, "<i2").astype(np.float64) * 10 ** (gain / 20)
    a = np.clip(a, -32767, 32767).astype("<i2")
    wav = path[:-5] + "_n.wav"
    with wave.open(wav, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(44100); w.writeframes(a.tobytes())
    subprocess.run([FFMPEG, "-y", "-v", "error", "-i", wav, "-c:a", "flac", path], check=True)
    os.remove(wav)
    return lufs, tp, gain


if __name__ == "__main__":
    for p in sorted(glob.glob(os.path.join(HERE, "musica", "*", "*.flac"))):
        lufs, tp, g = normalizza(p)
        if g:
            print(f"{os.path.relpath(p, HERE)}: {lufs:.1f} LUFS, picco {tp:.1f} -> guadagno {g:+.1f} dB")
    print("Fatto.")
