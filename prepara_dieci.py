"""
Musica per i reel da 10 s (31/10/2026). Finora un reel da 10 s univa due pezzi da 5 s NON consecutivi dello stesso brano:
a meta' video la musica saltava. Qui si estrae da ogni brano originale (musica_youtube_originali/, solo su questo PC) un
pezzo UNICO da 10,5 s: parte forte, sul colpo, senza stacchi. Finisce in musica/yt_dieci/.
Restano fuori i brani con la mediana piu' bassa su YouTube (dati 20-30/10/2026, sotto 100 visualizzazioni).
6/11/2026 (Alessandro: "ogni video una musica diversa da altri video, su ogni piattaforma"): rientrano i 5 esclusi
(energia e colpi al secondo nella media degli altri, misurati sui pezzi): 36 brani -> mai lo stesso brano negli ultimi
30 Short (pubblica.YT_FINESTRA_BRANI). I brani forti restano preferiti (pesi.json, aggiornato la domenica).
  python prepara_dieci.py           pezzi da 10,5 s mancanti in musica/yt_dieci/
  python prepara_dieci.py lunghi    per ogni pezzo la versione da 20,5 s (stesso inizio) in musica/yt_venti/
"""
import glob, json, os, re, subprocess, sys
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


def picco(path, s, dur):
    """Picco vero (dBTP) del tratto [s, s + dur]."""
    r = subprocess.run([pl.F, "-hide_banner", "-ss", f"{s:.2f}", "-t", str(dur), "-i", path, "-af",
                        "loudnorm=print_format=json", "-f", "null", "-"], capture_output=True, text=True,
                       errors="ignore").stderr
    return float(json.loads(r[r.rindex("{"):r.rindex("}") + 1])["input_tp"])


def lunghi():
    """6/11/2026: per ogni pezzo di yt_dieci la versione da 20,5 s che parte dallo STESSO punto (stessi inizi di
    migliori_inizi con DUR 10,5) e con lo stesso volume: i primi 10 s sono gli stessi (i reel da 10 s non cambiano),
    quelli piu' lunghi non sentono piu' il brano ripartire. Se il brano finisce prima, resta solo il pezzo corto."""
    pl.DUR, pl.PEZZI = 10.5, 3
    dest = os.path.join(pl.HERE, "musica", "yt_venti")
    os.makedirs(dest, exist_ok=True)
    fatti = 0
    for p, slug in _brani(dest):
        x = pl.pcm(p)
        durata = len(x) / 8000
        for k, s in enumerate(pl.migliori_inizi(x), 1):
            out = os.path.join(dest, f"{slug}_{k}.m4a")
            if os.path.exists(out) or not os.path.exists(os.path.join(pl.HERE, "musica", "yt_dieci", f"{slug}_{k}.m4a")):
                continue
            if s + LUNGO > durata - 1.0:
                print("troppo vicino alla fine, resta corto:", slug, k)
                continue
            g = min(pl.guadagno(p, s), -1.5 - picco(p, s, LUNGO))   # volume del pezzo corto, picchi sotto -1,5 dB
            _taglia(p, s, LUNGO, g, out)
            fatti += 1
    print(fatti, "pezzi lunghi creati")


if __name__ == "__main__":
    lunghi() if "lunghi" in sys.argv[1:] else main()
