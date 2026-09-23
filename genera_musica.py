"""
Compone la libreria musicale del profilo: loop strumentali ORIGINALI da 6 secondi (niente copyright).

Ogni brano: 80 BPM, 2 battute = 6,0 s esatti, 2 accordi, pad morbido + piano leggero + basso,
riverbero calcolato "in cerchio" (convoluzione circolare) cosi' la fine si attacca all'inizio senza stacchi:
chi legge la descrizione mentre il video gira in loop sente un sottofondo continuo.

Umori (cartelle in musica/):  calmo, caldo, deciso, malinconico, luminoso
Uso: python genera_musica.py   (rigenera tutto, ~1 minuto)
"""
import os, random, subprocess, wave
import numpy as np
import imageio_ffmpeg

SR = 44100
BPM = 80
BEAT = 60 / BPM
LOOP = 8 * BEAT                     # 6.0 s
N = int(round(LOOP * SR))
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "musica")
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

NOTE = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5, "F#": 6, "Gb": 6,
        "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}


def hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def chord(root, kind, octave=4):
    r = 12 * (octave + 1) + NOTE[root]
    iv = {"maj7": [0, 4, 7, 11], "min7": [0, 3, 7, 10], "add9": [0, 4, 7, 14], "min9": [0, 3, 7, 14],
          "sus2": [0, 2, 7, 12], "maj": [0, 4, 7, 12], "min": [0, 3, 7, 12]}[kind]
    return [r + i for i in iv]


# Progressioni di 2 accordi per umore (tutte suonano bene in loop)
MOODS = {
    "calmo":       [[("C", "maj7"), ("A", "min7")], [("F", "maj7"), ("C", "add9")], [("D", "min9"), ("G", "sus2")],
                    [("E", "min7"), ("C", "maj7")], [("A", "min9"), ("F", "maj7")], [("G", "add9"), ("E", "min7")]],
    "caldo":       [[("F", "maj7"), ("G", "add9")], [("C", "add9"), ("F", "maj7")], [("Bb", "maj7"), ("C", "sus2")],
                    [("D", "maj7"), ("B", "min7")], [("Eb", "maj7"), ("F", "add9")], [("G", "maj7"), ("C", "maj7")]],
    "deciso":      [[("A", "min"), ("F", "maj")], [("E", "min"), ("C", "maj")], [("D", "min"), ("Bb", "maj")],
                    [("C", "min"), ("Ab", "maj")], [("G", "min"), ("Eb", "maj")], [("B", "min"), ("G", "maj")]],
    "malinconico": [[("A", "min9"), ("E", "min7")], [("D", "min7"), ("A", "min7")], [("F#", "min7"), ("D", "maj7")],
                    [("C", "min9"), ("Ab", "maj7")], [("E", "min9"), ("B", "min7")], [("G", "min9"), ("Eb", "maj7")]],
    "luminoso":    [[("D", "add9"), ("A", "sus2")], [("G", "maj7"), ("D", "add9")], [("E", "add9"), ("B", "sus2")],
                    [("C", "maj"), ("G", "maj")], [("A", "add9"), ("E", "sus2")], [("F", "add9"), ("C", "sus2")]],
}
STYLE = {  # (volume pad, volume piano, arpeggio: note per battuta, batteria lo-fi, filtro "calore")
    "calmo":       (0.55, 0.30, 2, False, 2500),
    "caldo":       (0.50, 0.35, 2, False, 3200),
    "deciso":      (0.40, 0.35, 4, True, 3500),
    "malinconico": (0.55, 0.32, 1, False, 2200),
    "luminoso":    (0.40, 0.38, 4, False, 4500),
}

t = np.arange(N) / SR


def lowpass(x, cutoff):
    """Filtro passa-basso circolare (in frequenza): mantiene il loop perfetto."""
    X = np.fft.rfft(x, axis=0)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    resp = 1 / np.sqrt(1 + (f / cutoff) ** 4)
    return np.fft.irfft(X * (resp[:, None] if X.ndim == 2 else resp), n=len(x), axis=0)


def reverb(x, rng, secs=2.8, wet=0.35):
    """Riverbero con convoluzione circolare: la coda della fine rientra all'inizio."""
    n = int(secs * SR)
    ir = rng.standard_normal((n, 2)) * np.exp(-np.arange(n) / SR * 4.5 / secs)[:, None]
    ir = lowpass(ir, 5000)
    ir /= np.sqrt((ir ** 2).sum(axis=0))
    irp = np.zeros((N, 2))
    irp[:n] = ir[:N]
    X = np.fft.rfft(x, axis=0)
    wetsig = np.fft.irfft(X * np.fft.rfft(irp, axis=0), n=N, axis=0)
    return x * (1 - wet) + wetsig * wet * 1.8


def wrap_add(buf, sig, start):
    idx = (np.arange(len(sig)) + start) % N
    np.add.at(buf, idx, sig)


def pad(notes, start, length, rng):
    out = np.zeros((N, 2))
    L = int(length * SR)
    tt = np.arange(L) / SR
    env = np.minimum(1, tt / 0.6) * np.minimum(1, (length - tt) / 0.9).clip(0, 1)   # entrata e uscita morbide
    for m in notes:
        f = hz(m)
        for ch, det in ((0, -0.12), (1, 0.12)):             # leggero "chorus" stereo
            s = sum(np.sin(2 * np.pi * f * k * (1 + det / 100) * tt + rng.uniform(0, 6.28)) / k ** 1.6
                    for k in range(1, 5))
            sig = np.zeros((L, 2))
            sig[:, ch] = s * env
            wrap_add(out, sig, int(start * SR))
    return out / max(1, len(notes))


def piano(m, start, vel, length=2.5):
    L = int(length * SR)
    tt = np.arange(L) / SR
    f = hz(m)
    s = (np.sin(2 * np.pi * f * tt) + 0.35 * np.sin(2 * np.pi * 2 * f * tt) * np.exp(-tt * 3)
         + 0.12 * np.sin(2 * np.pi * 3 * f * tt) * np.exp(-tt * 5))
    env = np.minimum(1, tt / 0.004) * np.exp(-tt * 2.2)
    sig = np.stack([s * env * vel] * 2, axis=1)
    out = np.zeros((N, 2))
    wrap_add(out, sig, int(start * SR))
    return out


def bass(m, start, length):
    L = int(length * SR)
    tt = np.arange(L) / SR
    s = np.sin(2 * np.pi * hz(m) * tt) * np.minimum(1, tt / 0.05) * np.minimum(1, (length - tt) / 0.3).clip(0, 1)
    out = np.zeros((N, 2))
    wrap_add(out, np.stack([s, s], axis=1), int(start * SR))
    return out


def drums(rng):
    out = np.zeros((N, 2))
    for b in range(8):
        st = b * BEAT
        if b % 4 in (0, 2) or (b % 4 == 3 and rng.random() < 0.5):          # cassa morbida
            L = int(0.35 * SR)
            tt = np.arange(L) / SR
            k = np.sin(2 * np.pi * (55 + 90 * np.exp(-tt * 25)) * tt) * np.exp(-tt * 9)
            wrap_add(out, np.stack([k, k], axis=1) * 0.9, int(st * SR))
        for h in (0.5,) if b % 2 else (0.5,):                                 # hi-hat leggero in levare
            L = int(0.06 * SR)
            n_ = rng.standard_normal(L) * np.exp(-np.arange(L) / SR * 60)
            wrap_add(out, np.stack([n_, n_], axis=1) * 0.08, int((st + h * BEAT) * SR))
    return lowpass(out, 6000)


def compose(mood, prog, seed):
    rng = random.Random(seed)
    nrng = np.random.default_rng(seed)
    vpad, vpiano, arp, drum, warm = STYLE[mood]
    mix = np.zeros((N, 2))
    half = LOOP / 2
    for i, (root, kind) in enumerate(prog):
        notes = chord(root, kind, 3 if NOTE[root] > 6 else 4)
        mix += pad(notes, i * half, half + 0.9, nrng) * vpad            # si sovrappone un po' al successivo
        mix += bass(notes[0] - 12, i * half, half) * 0.35
        step = BEAT / arp
        pattern = rng.choice([[0, 1, 2, 3], [0, 2, 1, 3], [0, 2, 3, 2], [3, 2, 1, 0]])
        for j in range(int(4 * arp)):
            if arp == 1 and j % 2 and rng.random() < 0.5:
                continue
            m = notes[pattern[j % 4]] + 12
            vel = (0.9 if j % arp == 0 else 0.6) * rng.uniform(0.8, 1.0)
            mix += piano(m, i * half + j * step + rng.uniform(0, 0.012), vel) * vpiano
    if drum:
        mix += drums(nrng) * 0.5
    mix = reverb(mix, nrng)
    mix = lowpass(mix, warm)
    mix += nrng.standard_normal((N, 2)) * 0.0015                       # un filo di "fruscio" lo-fi
    mix -= mix.mean(axis=0)
    mix *= 10 ** (-16 / 20) / np.sqrt((mix ** 2).mean())             # volume uniforme (circa -16 dB RMS)
    peak = np.abs(mix).max()
    if peak > 0.95:
        mix *= 0.95 / peak
    return mix


def save(mix, path):
    wav = os.path.splitext(path)[0] + ".wav"
    with wave.open(wav, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((mix * 32767).astype("<i2").tobytes())
    subprocess.run([FFMPEG, "-y", "-v", "error", "-i", wav, "-c:a", "flac", path], check=True)
    os.remove(wav)


def main():
    count = 0
    for mood, progs in MOODS.items():
        d = os.path.join(OUT, mood)
        os.makedirs(d, exist_ok=True)
        for f in os.listdir(d):
            os.remove(os.path.join(d, f))
        for i, prog in enumerate(progs):
            mix = compose(mood, prog, seed=sum(map(ord, mood)) * 100 + i)
            jump = np.abs(mix[0] - mix[-1]).max()          # controllo del loop: deve essere quasi zero
            save(mix, os.path.join(d, f"{mood}_{i + 1:02d}.flac"))
            count += 1
            print(f"{mood}_{i + 1:02d}  loop {jump:.4f}")
    print(count, "brani creati in", OUT)


if __name__ == "__main__":
    main()
