"""
Musica per i reel da 10 s (31/10/2026). Finora un reel da 10 s univa due pezzi da 5 s NON consecutivi dello stesso brano:
a meta' video la musica saltava. Qui si estrae da ogni brano originale (musica_youtube_originali/, solo su questo PC) un
pezzo UNICO da 10,5 s: parte forte, sul colpo, senza stacchi. Finisce in musica/yt_dieci/.
Restano fuori i brani con la mediana piu' bassa su YouTube (dati 20-30/10/2026, sotto 100 visualizzazioni).
6/11/2026 (Alessandro: "ogni video una musica diversa da altri video, su ogni piattaforma"): rientrano i 5 esclusi
(energia e colpi al secondo nella media degli altri, misurati sui pezzi): 36 brani -> mai lo stesso brano negli ultimi
30 Short (pubblica.YT_FINESTRA_BRANI). I brani forti restano preferiti (pesi.json, aggiornato la domenica).
  python prepara_dieci.py           pezzi da 10,5 s mancanti in musica/yt_dieci/
  python prepara_dieci.py lunghi [brano...]   per ogni pezzo la versione da 20,5 s (stesso inizio e volume)
                                             in musica/yt_venti/; con i nomi, solo quei brani
"""
import glob, os, re, subprocess, sys
import prepara_libreria as pl

ESCLUSI = set()
LUNGO = 20.5     # 6/11/2026: il formato "intero" dura fino a 20 s; col pezzo da 10,5 s la musica ripartiva da capo a 10 s


def _brani(cartella=None):
    """Brani da lavorare; con cartella, salta quelli che ci hanno gia' tutti i pezzi (6/11/2026: senza decodificarli,
    sul PC carico ogni decodifica durava quasi un minuto)."""
    for p in sorted(glob.glob(os.path.join(pl.ORIG, "*.mp3"))):
        slug = re.sub(r"[^a-z0-9]+", "_", os.path.splitext(os.path.basename(p))[0].lower()).strip("_")
        fatti = cartella and all(os.path.exists(os.path.join(cartella, f"{slug}_{k}.m4a")) for k in range(1, pl.PEZZI + 1))
        if slug not in ESCLUSI and not fatti:
            yield p, slug


def _taglia(p, s, dur, g, out):
    subprocess.run([pl.F, "-y", "-v", "error", "-ss", f"{s:.2f}", "-t", str(dur), "-i", p, "-af",
                    f"volume={g:.2f}dB,afade=t=in:d=0.05,afade=t=out:st={dur - 0.35}:d=0.35",
                    "-ac", "2", "-ar", "44100", "-c:a", "aac", "-b:a", "192k", out], check=True)


def main():
    pl.DUR, pl.PEZZI = 10.5, 3
    dest = os.path.join(pl.HERE, "musica", "yt_dieci")
    os.makedirs(dest, exist_ok=True)
    fatti = 0
    for p, slug in _brani(dest):
        for k, s in enumerate(pl.migliori_inizi(pl.pcm(p)), 1):
            out = os.path.join(dest, f"{slug}_{k}.m4a")
            if os.path.exists(out):
                continue
            _taglia(p, s, pl.DUR, pl.guadagno(p, s), out)
            fatti += 1
    print(fatti, "pezzi creati")


def _inizio(x, y, sr=8000):
    """6/11/2026: il secondo dell'originale x da cui e' tagliato il pezzo y (correlazione normalizzata via FFT, in meno
    di un secondo: migliori_inizi ci metteva quasi un minuto a brano), arrotondato a 0,01 s come il taglio."""
    import numpy as np
    m = 1 << (len(x) + len(y) - 1).bit_length()
    c = np.fft.irfft(np.fft.rfft(x, m) * np.conj(np.fft.rfft(y, m)), m)[:len(x) - len(y) + 1]
    e = np.concatenate(([0.0], np.cumsum(x.astype(np.float64) ** 2)))
    return round(int(np.argmax(c / np.sqrt(np.maximum(e[len(y):] - e[:-len(y)], 1e-9)))) / sr, 2)


def _confronto(a, b, sr=8000):
    """(correlazione, differenza in dB) dei primi 9,5 s di due pezzi: 1 e 0 = stesso audio, stesso volume."""
    import numpy as np
    n = int(9.5 * sr)
    if min(len(a), len(b)) < n:
        return 0.0, 99.0
    a, b = a[:n].astype(np.float64), b[:n].astype(np.float64)
    na, nb = np.linalg.norm(a) + 1e-12, np.linalg.norm(b) + 1e-12
    return float(np.dot(a, b) / (na * nb)), float(20 * np.log10(na / nb))


def lunghi(solo=()):
    """6/11/2026: per ogni pezzo di yt_dieci la versione da 20,5 s in yt_venti: nel formato "intero" (fino a 20 s) il
    pezzo da 10,5 s ripartiva da capo a 10 s. Parte dallo STESSO punto del pezzo corto (ritrovato nell'originale) con
    lo STESSO guadagno, e si tiene solo se i primi 10 s sono uguali al pezzo corto (correlazione > 0,97, volume entro
    0,3 dB): cosi' nei reel da 10 s la musica non cambia (revisione: prima il limite dei picchi poteva abbassarla).
    Se il brano finisce prima resta solo il pezzo corto. solo: i brani da fare (a gruppi, col lucchetto del PC)."""
    import shutil, tempfile
    pl.DUR, pl.PEZZI = 10.5, 3
    dieci = os.path.join(pl.HERE, "musica", "yt_dieci")
    dest = os.path.join(pl.HERE, "musica", "yt_venti")
    os.makedirs(dest, exist_ok=True)
    fatti = 0
    for p, slug in _brani(dest):
        corti = [(k, os.path.join(dieci, f"{slug}_{k}.m4a")) for k in range(1, pl.PEZZI + 1)]
        corti = [(k, c) for k, c in corti
                 if os.path.exists(c) and not os.path.exists(os.path.join(dest, os.path.basename(c)))]
        if (solo and slug not in solo) or not corti:
            continue
        x = pl.pcm(p)
        for k, c in corti:
            y = pl.pcm(c)
            s = _inizio(x, y)
            if s + LUNGO > len(x) / 8000 - 1.0:
                print("troppo vicino alla fine, resta corto:", slug, k)
                continue
            tmp = os.path.join(tempfile.gettempdir(), f"yt_venti_{slug}_{k}.m4a")
            g = pl.guadagno(p, s)
            _taglia(p, s, LUNGO, g, tmp)
            corr, db = _confronto(pl.pcm(tmp), y)
            if corr > 0.97 and 0.05 <= abs(db) < 3:      # stesso punto ma volume un po' diverso: si corregge una volta
                g -= db
                _taglia(p, s, LUNGO, g, tmp)
                corr, db = _confronto(pl.pcm(tmp), y)
            ok = corr > 0.97 and abs(db) < 0.3
            print(f"{slug}_{k}: da {s:.2f} s, guadagno {g:+.2f} dB, primi 10 s come il pezzo corto: "
                  f"{'si' if ok else 'NO'} (correlazione {corr:.3f}, {db:+.2f} dB)", flush=True)
            if ok:
                shutil.move(tmp, os.path.join(dest, os.path.basename(c)))
                fatti += 1
    print(fatti, "pezzi lunghi creati")


if __name__ == "__main__":
    if sys.argv[1:2] == ["lunghi"]:
        lunghi(set(sys.argv[2:]))
    else:
        main()
