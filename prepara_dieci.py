"""
Musica per i reel da 10 s (31/10/2026). Finora un reel da 10 s univa due pezzi da 5 s NON consecutivi dello stesso brano:
a meta' video la musica saltava. Qui si estrae da ogni brano originale (musica_youtube_originali/, solo su questo PC) un
pezzo UNICO da 10,5 s: parte forte, sul colpo, senza stacchi. Finisce in musica/yt_dieci/.
Restano fuori i brani con la mediana piu' bassa su YouTube (dati 20-30/10/2026, sotto 100 visualizzazioni).
"""
import glob, os, re, subprocess
import prepara_libreria as pl

ESCLUSI = {"the_road_to_mordor", "survival_mode", "break_ya_neck", "stake_out", "rubberband"}


def main():
    pl.DUR, pl.PEZZI = 10.5, 3
    dest = os.path.join(pl.HERE, "musica", "yt_dieci")
    os.makedirs(dest, exist_ok=True)
    fatti = 0
    for p in sorted(glob.glob(os.path.join(pl.ORIG, "*.mp3"))):
        slug = re.sub(r"[^a-z0-9]+", "_", os.path.splitext(os.path.basename(p))[0].lower()).strip("_")
        if slug in ESCLUSI:
            continue
        for k, s in enumerate(pl.migliori_inizi(pl.pcm(p)), 1):
            out = os.path.join(dest, f"{slug}_{k}.m4a")
            if os.path.exists(out):
                continue
            g = pl.guadagno(p, s)
            subprocess.run([pl.F, "-y", "-v", "error", "-ss", f"{s:.2f}", "-t", str(pl.DUR), "-i", p, "-af",
                            f"volume={g:.2f}dB,afade=t=in:d=0.05,afade=t=out:st={pl.DUR - 0.35}:d=0.35",
                            "-ac", "2", "-ar", "44100", "-c:a", "aac", "-b:a", "192k", out], check=True)
            fatti += 1
    print(fatti, "pezzi creati")


if __name__ == "__main__":
    main()
