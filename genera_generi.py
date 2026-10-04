"""
Musica per SCENA: un genere diverso per ogni contesto, sui suoni che vanno di piu' nei reel di quella nicchia.
Loop ORIGINALI (niente copyright) da 8,0 s esatti, che ripartono senza stacchi come quelli di genera_musica.py.

  palestra -> phonk      (150 BPM, 808 distorto, cowbell)       macchina -> drive    (120 BPM, 808 profondo, synth scuri)
  lavoro   -> house      (120 BPM, cassa dritta, accordi)       cibo     -> lofi     (90 BPM, batteria swing, Rhodes, vinile)
  uscita   -> tropical   (120 BPM, marimba, shaker)             specchio -> trap     (150 BPM half-time, hi-hat veloci, campanelli)
  (casa usa l'umore "caldo" di genera_musica.py)

Uso: python genera_generi.py [genere]     -> musica/<genere>/<genere>_NN.flac
"""
import os, random, sys
import numpy as np
import genera_musica as gm

SR, N, LOOP = gm.SR, gm.N, gm.LOOP
BRANI = 16          # brani per genere
SCALA_MIN = [0, 3, 5, 7, 10]           # pentatonica minore
SCALA_MAJ = [0, 2, 4, 7, 9]


def _env(L, att, dec):
    tt = np.arange(L) / SR
    return np.minimum(1, tt / max(att, 1e-4)) * np.exp(-tt * dec), tt


def put(buf, mono, start, pan=0.0, vol=1.0):
    st = np.stack([mono * (1 - max(0, pan)), mono * (1 + min(0, pan))], axis=1) * vol
    gm.wrap_add(buf, st, int(round(start * SR)))


def highpass(x, fc):
    return x - gm.lowpass(x, fc)


def kick(punch=1.0, f0=48, decay=7.0, drive=1.5):
    L = int(0.5 * SR)
    env, tt = _env(L, 0.001, decay)
    s = np.sin(2 * np.pi * (f0 * tt + 160 * punch * (1 - np.exp(-tt * 30)) / 30))
    return np.tanh(s * env * drive) * 0.9


def sub808(m, length, drive=2.0, glide_from=None):
    L = int(length * SR)
    tt = np.arange(L) / SR
    f = gm.hz(m)
    if glide_from is not None:                  # "slide" tipico della trap
        f = gm.hz(m) + (gm.hz(glide_from) - gm.hz(m)) * np.exp(-tt * 18)
    ph = 2 * np.pi * np.cumsum(np.broadcast_to(f, tt.shape)) / SR
    env = np.minimum(1, tt / 0.004) * np.minimum(1, (length - tt) / 0.05).clip(0, 1) * np.exp(-tt * 0.8)
    return np.tanh(np.sin(ph) * drive) * env * 0.8


def noise(L, rng):
    return rng.standard_normal(L)


def snare(rng, tone=190, decay=18, clap=False):
    L = int(0.3 * SR)
    env, tt = _env(L, 0.001, decay)
    n = noise(L, rng)
    n = n - np.convolve(n, np.ones(8) / 8, "same")           # toglie i bassi del rumore
    if clap:                                                 # 3 colpi ravvicinati = battito di mani
        e2 = sum(np.exp(-np.clip(tt - d, 0, None) * 60) * (tt >= d) for d in (0, 0.011, 0.023))
        return n * (0.5 * e2 + env) * 0.5
    return n * env * 0.6 + np.sin(2 * np.pi * tone * tt) * np.exp(-tt * 30) * 0.4


def hat(rng, length=0.05, open_=False):
    L = int((0.25 if open_ else length) * SR)
    env, _ = _env(L, 0.0005, 9 if open_ else 70)
    n = noise(L, rng)
    n = n - np.convolve(n, np.ones(4) / 4, "same")
    n = n - np.convolve(n, np.ones(3) / 3, "same")
    return n * env * 0.35


def shaker(rng):
    L = int(0.09 * SR)
    tt = np.arange(L) / SR
    env = np.sin(np.pi * tt / tt[-1]) ** 2
    n = noise(L, rng)
    return (n - np.convolve(n, np.ones(5) / 5, "same")) * env * 0.18


def cowbell(m, length=0.18):
    L = int(length * SR)
    env, tt = _env(L, 0.001, 14)
    f = gm.hz(m)
    sq = np.sign(np.sin(2 * np.pi * f * tt)) + 0.7 * np.sign(np.sin(2 * np.pi * f * 1.48 * tt))
    return np.tanh(sq * 0.6) * env * 0.35


def bell(m, length=1.2):
    L = int(length * SR)
    env, tt = _env(L, 0.002, 3.5)
    f = gm.hz(m)
    s = np.sin(2 * np.pi * f * tt + 1.5 * np.sin(2 * np.pi * f * 3.5 * tt) * np.exp(-tt * 6))   # FM: campanello
    return s * env * 0.3


def marimba(m, length=0.6):
    L = int(length * SR)
    env, tt = _env(L, 0.001, 9)
    f = gm.hz(m)
    return (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(2 * np.pi * 4 * f * tt) * np.exp(-tt * 40)) * env * 0.45


def rhodes(notes, length):
    L = int(length * SR)
    env, tt = _env(L, 0.003, 1.3)
    trem = 1 + 0.12 * np.sin(2 * np.pi * 4.5 * tt)
    s = sum(np.sin(2 * np.pi * gm.hz(m) * tt) + 0.2 * np.sin(2 * np.pi * gm.hz(m) * 2 * tt) * np.exp(-tt * 8)
            for m in notes)
    return s * env * trem * 0.18


def saw(m, length, cutoff_decay=6.0, detune=0.25):
    """Synth "sega" con filtro che si chiude (pluck/arpeggio moderno)."""
    L = int(length * SR)
    env, tt = _env(L, 0.002, 3.0)
    out = np.zeros(L)
    for d in (-detune, detune):
        f = gm.hz(m) * (1 + d / 100)
        for k in range(1, 14):
            amp = np.exp(-tt * cutoff_decay * k / 4) / k
            out += np.sin(2 * np.pi * f * k * tt) * amp
    return out * env * 0.12


def stab(notes, length=0.22):
    L = int(length * SR)
    env, tt = _env(L, 0.002, 12)
    s = sum(np.sin(2 * np.pi * gm.hz(m) * tt) + 0.4 * np.sin(2 * np.pi * gm.hz(m) * 2 * tt) * np.exp(-tt * 20)
            for m in notes)
    return s * env * 0.12


def finale(mix, rng, rms_db=-14, riverbero=0.18, vinile=False):
    mix = gm.reverb(mix, rng, secs=1.6, wet=riverbero)
    if vinile:
        crack = np.zeros((N, 2))
        idx = rng.integers(0, N, 90)
        crack[idx] = rng.standard_normal((90, 2)) * 0.25
        mix = gm.lowpass(mix, 4200) + crack + rng.standard_normal((N, 2)) * 0.003
    mix -= mix.mean(axis=0)
    mix *= 10 ** ((rms_db - 2) / 20) / np.sqrt((mix ** 2).mean())
    return np.tanh(mix * 1.2) / np.tanh(1.2) * 0.95          # "glue": suono piu' compatto e forte


# ------------------------------------------------------------------ generi
def phonk(seed):
    rng, r = np.random.default_rng(seed), random.Random(seed)
    beat = 60 / 150                                  # 150 BPM -> 20 battiti = 5 battute in 8 s
    key = r.choice([1, 3, 4, 6, 8])                  # tonalita' minore
    mix = np.zeros((N, 2))
    melodia = [r.choice(SCALA_MIN) + 12 * r.choice([0, 1]) for _ in range(8)]
    for b in range(20):
        t0 = b * beat
        if b % 4 == 0 or (b % 4 == 2 and r.random() < 0.6):
            put(mix, kick(1.2, 45, 6, 2.5), t0)
            put(mix, sub808(36 + key + r.choice([0, 0, 7, 5]), beat * 1.8, drive=3.0), t0, vol=0.8)
        if b % 4 == 2:
            put(mix, snare(rng, clap=True), t0, vol=0.9)
        for h in range(2):
            put(mix, hat(rng), t0 + h * beat / 2, pan=0.3, vol=0.7 if h else 1.0)
        for h in range(2):                           # cowbell: la firma del phonk
            m = 72 + key + melodia[(b * 2 + h) % 8]
            put(mix, cowbell(m), t0 + h * beat / 2, pan=-0.2)
    return finale(mix, rng, -13, 0.12)


def drive(seed):
    rng, r = np.random.default_rng(seed), random.Random(seed)
    beat = 0.5
    key = r.choice([0, 2, 5, 7, 9])
    prog = r.choice([[0, 8, 3, 10], [0, 5, 8, 7], [0, 8, 10, 7], [0, 3, 8, 10]])
    mix = np.zeros((N, 2))
    for bar in range(4):
        root = 45 + key + prog[bar]
        third = 3 if prog[bar] in (0, 5, 7) else 4
        notes = [root + 12, root + 12 + third, root + 19]
        mix += gm.pad(notes, bar * 2.0, 2.6, rng) * 0.35
        put(mix, sub808(root - 12, 1.9, drive=2.2, glide_from=root - 7 if r.random() < 0.4 else None), bar * 2.0, vol=0.8)
        for s16 in range(16):                       # arpeggio "notte in macchina"
            m = notes[[0, 1, 2, 1][s16 % 4]] + 12
            put(mix, saw(m, 0.2, 9), bar * 2.0 + s16 * beat / 4, pan=0.4 if s16 % 2 else -0.4, vol=0.6)
        for b in range(4):
            t0 = bar * 2.0 + b * beat
            if b == 0 or (b == 2 and r.random() < 0.5):
                put(mix, kick(1.0, 50, 7, 1.8), t0)
            if b in (1, 3):
                put(mix, snare(rng, 180, 14), t0, vol=0.7)
            for h in range(4 if r.random() < 0.15 else 2):
                put(mix, hat(rng), t0 + h * beat / (4 if h > 1 else 2), vol=0.5)
    return finale(mix, rng, -14, 0.25)


def house(seed):
    rng, r = np.random.default_rng(seed), random.Random(seed)
    beat = 0.5
    key = r.choice([0, 2, 4, 5, 7, 9])
    prog = r.choice([[0, 5, 3, 8], [0, 8, 3, 10], [0, 3, 5, 3], [0, 10, 8, 7]])
    mix = np.zeros((N, 2))
    ritmo = r.choice([[0, 0.75, 1.5], [0.5, 1.25, 1.75], [0, 0.5, 1.25, 1.75]])
    for bar in range(4):
        root = 48 + key + prog[bar]
        notes = [root, root + 3, root + 7, root + 10, root + 14]          # accordi min7/9: "deep"
        for p in ritmo:
            put(mix, stab([n + 12 for n in notes]), bar * 2.0 + p * beat * 2, vol=0.9)
        for b in range(4):
            t0 = bar * 2.0 + b * beat
            put(mix, kick(0.8, 50, 9, 1.4), t0)                           # cassa dritta
            put(mix, hat(rng, open_=True), t0 + beat / 2, pan=0.2, vol=0.6)
            if b in (1, 3):
                put(mix, snare(rng, clap=True), t0, vol=0.55)
            put(mix, sub808(root - 12 + (7 if b == 3 and r.random() < 0.4 else 0), beat * 0.45, 1.2), t0 + beat / 2, vol=0.7)
    tt = (np.arange(N) / SR) % beat                                       # sidechain sulla cassa
    mix *= (0.55 + 0.45 * np.minimum(1, tt / (beat * 0.6)))[:, None]
    return finale(mix, rng, -14, 0.2)


def lofi(seed):
    rng, r = np.random.default_rng(seed), random.Random(seed)
    beat = 60 / 90                                   # 90 BPM -> 12 battiti = 3 battute in 8 s
    key = r.choice([0, 2, 3, 5, 7, 10])
    prog = r.choice([[0, 9, 5], [0, 5, 7], [2, 7, 0], [9, 5, 0], [0, 4, 9]])
    mix = np.zeros((N, 2))
    swing = beat / 2 * 1.16
    for bar in range(3):
        root = 48 + key + prog[bar]
        third = 3 if prog[bar] in (2, 4, 9) else 4
        notes = [root, root + third, root + 7, root + (10 if third == 3 else 11), root + 14]
        put(mix, rhodes(notes, beat * 4.2), bar * beat * 4)
        put(mix, rhodes(notes[1:4], beat * 1.5), bar * beat * 4 + beat * 2.5, vol=0.6)
        put(mix, sub808(root - 12, beat * 3.5, 1.0), bar * beat * 4, vol=0.55)
        for b in range(4):
            t0 = (bar * 4 + b) * beat
            if b == 0 or (b == 2 and r.random() < 0.7) or (b == 1 and r.random() < 0.3):
                put(mix, kick(0.6, 55, 10, 1.2), t0 + (swing if b == 1 else 0), vol=0.8)
            if b in (1, 3):
                put(mix, snare(rng, 200, 22), t0, vol=0.5)
            put(mix, hat(rng), t0, vol=0.35)
            put(mix, hat(rng), t0 + swing, vol=0.22)
        if r.random() < 0.7:                                               # piccola melodia
            for k in range(3):
                put(mix, gm.piano(60 + key + r.choice(SCALA_MAJ) + 12, 0, 0.35, 1.0)[:, 0], bar * beat * 4 + r.choice([1, 1.5, 2.5, 3]) * beat, vol=0.6)
    return finale(mix, rng, -16, 0.25, vinile=True)


def tropical(seed):
    rng, r = np.random.default_rng(seed), random.Random(seed)
    beat = 0.5
    key = r.choice([0, 2, 5, 7, 9])
    prog = r.choice([[0, 7, 9, 5], [0, 5, 9, 7], [9, 5, 0, 7], [0, 9, 5, 7]])
    mix = np.zeros((N, 2))
    figura = r.choice([[0, 0.75, 1.5, 2.5, 3], [0, 0.5, 1.5, 2, 3], [0.5, 1, 2, 2.75, 3.5]])
    for bar in range(4):
        root = 60 + key + prog[bar]
        third = 3 if prog[bar] in (9, 2, 4) else 4
        notes = [root, root + third, root + 7, root + 12]
        mix += gm.pad([n - 12 for n in notes[:3]], bar * 2.0, 2.4, rng) * 0.2
        for i, p in enumerate(figura):                                    # marimba "estate"
            put(mix, marimba(notes[(i * 2) % 4] + 12), bar * 2.0 + p * beat, pan=0.25 if i % 2 else -0.25)
        put(mix, sub808(root - 24, 0.4, 1.3), bar * 2.0, vol=0.7)
        put(mix, sub808(root - 24 + 7, 0.3, 1.3), bar * 2.0 + 1.5 * beat, vol=0.6)
        for b in range(4):
            t0 = bar * 2.0 + b * beat
            put(mix, kick(0.7, 52, 9, 1.3), t0, vol=0.9)
            if b in (1, 3):
                put(mix, snare(rng, clap=True), t0, vol=0.45)
            for s in range(4):
                put(mix, shaker(rng), t0 + s * beat / 4, pan=0.4, vol=1.0 if s % 2 else 0.6)
    tt = (np.arange(N) / SR) % beat
    mix *= (0.65 + 0.35 * np.minimum(1, tt / (beat * 0.5)))[:, None]
    return finale(mix, rng, -14, 0.22)


def trap(seed):
    rng, r = np.random.default_rng(seed), random.Random(seed)
    beat = 60 / 150                                  # 150 BPM, feeling half-time (75)
    key = r.choice([1, 3, 6, 8, 10])
    mix = np.zeros((N, 2))
    giro = [r.choice(SCALA_MIN) for _ in range(5)]
    prec = None
    for bar in range(5):
        t_bar = bar * 4 * beat
        for k, off in enumerate((0, 1.5, 2.5) if r.random() < 0.6 else (0, 2)):
            m = 72 + key + giro[(bar + k) % 5]
            put(mix, bell(m), t_bar + off * beat, pan=-0.3 if k % 2 else 0.3, vol=0.8)
        root = 36 + key + giro[bar] % 12
        put(mix, sub808(root, beat * 3.6, 2.4, glide_from=prec if r.random() < 0.5 else None), t_bar, vol=0.9)
        prec = root
        put(mix, kick(1.1, 45, 6, 2.2), t_bar)
        if r.random() < 0.5:
            put(mix, kick(1.1, 45, 6, 2.2), t_bar + 2.5 * beat)
        put(mix, snare(rng, clap=True), t_bar + 2 * beat, vol=0.9)                     # half-time: colpo sul 3
        for s in range(8):                                                               # hi-hat in ottavi...
            t0 = t_bar + s * beat / 2
            if r.random() < 0.18:                                                        # ...con le "rullate"
                for q in range(4):
                    put(mix, hat(rng, 0.03), t0 + q * beat / 8, pan=0.2, vol=0.5)
            else:
                put(mix, hat(rng), t0, pan=0.2, vol=0.8 if s % 2 == 0 else 0.55)
    return finale(mix, rng, -13, 0.15)


GENERI = {"phonk": phonk, "drive": drive, "house": house, "lofi": lofi, "tropical": tropical, "trap": trap}


def main(solo=None):
    for nome, fn in GENERI.items():
        if solo and nome != solo:
            continue
        d = os.path.join(gm.OUT, nome)
        os.makedirs(d, exist_ok=True)
        for f in os.listdir(d):
            os.remove(os.path.join(d, f))
        for i in range(BRANI):
            mix = fn(sum(map(ord, nome)) * 100 + i)
            gm.save(mix, os.path.join(d, f"{nome}_{i + 1:02d}.flac"))
        print(nome, BRANI, "brani")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
