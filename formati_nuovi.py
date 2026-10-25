"""
FORMATI NUOVI da testare (25/10/2026, richiesta di Alessandro: "voglio che i video siano diversi tra di loro... capire
il prima possibile quale format funziona"). Tutti in 4K 60 come gli altri, con la serie "GIORNO X / 365" in alto.

- broll1 : 8 s, 8 stacchi da 1 s (b-roll veloce), la frase fissa sopra
- broll2 : 10 s, 5 stacchi da 2 s, la frase divisa in pezzi: cambia a ogni stacco
- broll3 : 12 s, 4 stacchi da 3 s, la frase divisa in pezzi: cambia a ogni stacco
- storia : ~22 s, un racconto a schermate (titolo + 3 righe di una lista, una schermata alla volta) su 2-3 clip

make_sequenza() e' il motore comune: pezzi di video tagliati netti + testi che compaiono a tempo + musica.
"""
import os, re, shutil, subprocess, tempfile
import overlay as ov

FORMATI = {
    "broll1": {"stacchi": [1.0] * 8, "testo": "fisso"},
    "broll2": {"stacchi": [2.0] * 5, "testo": "a_pezzi"},
    "broll3": {"stacchi": [3.0] * 4, "testo": "a_pezzi"},
    "storia": {"schermate": [4.0, 6.0, 6.0, 6.0]},
}


def dividi_in(testo, n):
    """La frase in n pezzi di parole equilibrati (meglio se si spezza dopo la punteggiatura)."""
    parole = testo.split()
    n = max(1, min(n, len(parole)))
    pezzi, resto = [], parole
    for i in range(n, 0, -1):
        if i == 1:
            pezzi.append(" ".join(resto))
            break
        quanti = round(len(resto) / i)
        # se c'e' una virgola/punto vicino al taglio, si spezza li'
        for d in (0, 1, -1, 2, -2):
            j = quanti + d
            if 1 <= j < len(resto) and re.search(r"[,.;:!?]$", resto[j - 1]):
                quanti = j
                break
        pezzi.append(" ".join(resto[:max(1, quanti)]))
        resto = resto[max(1, quanti):]
        if not resto:
            break
    return [p for p in pezzi if p]


def make_sequenza(clips, durate, testi, dst, musiche=(), serie=None, nome="sequenza"):
    """clips: video sorgente (si riusano a giro, ogni pezzo da un punto diverso); durate: secondi di ogni pezzo;
    testi: [(da_s, a_s, testo)] da mostrare a tempo. Restituisce info."""
    W, H = ov.LATO_USCITA, int(ov.LATO_USCITA * 16 / 9)
    DUR = round(sum(durate), 3)
    tmp = tempfile.mkdtemp()
    cmd, catena = [ov.FFMPEG, "-y", "-v", "error"], []
    for i, seg in enumerate(durate):
        c = clips[i % len(clips)]
        secondi, hdr = ov.probe(c)
        giro = i // len(clips)                     # stessa clip riusata: punto diverso
        riserva = max(0.0, min(0.5 + giro * (seg + 0.5), secondi - seg - 0.2))
        inizio = ov.inizio_bello(c, secondi, hdr, seg + 0.2, riserva) if giro == 0 else riserva
        cmd += ["-display_rotation", "0", "-ss", f"{inizio:.2f}", "-t", f"{seg + 0.2:.2f}", "-i", c]
        f = [x for x in (ov.raddrizza(ov.rotazione(c)), ov.HDR_TO_SDR if hdr else "") if x]
        f += [f"scale={W}:{H}:force_original_aspect_ratio=increase", f"crop={W}:{H}", "setsar=1",
              f"fps={ov.FPS_MULTI}", "format=yuv420p", "settb=AVTB", f"fps={ov.FPS_MULTI}",
              "tpad=stop_mode=clone:stop_duration=1", f"trim=0:{seg:.3f}", "setpts=PTS-STARTPTS"]
        catena.append(f"[{i}:v]{','.join(f)}[c{i}]")
    n = len(durate)
    g = ";".join(catena) + ";" + "".join(f"[c{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[bg]"
    corrente, idx = "bg", n
    for k, (a, b, t) in enumerate(testi):
        img, _, _ = ov.build_overlay(W, H, t, [], serie=serie)
        p = os.path.join(tmp, f"t{k}.png")
        img.save(p)
        cmd += ["-i", p]
        g += f";[{corrente}][{idx}:v]overlay=0:0:format=auto:enable='between(t,{a:.2f},{b - 0.001:.2f})'[o{k}]"
        corrente, idx = f"o{k}", idx + 1
    g += f";[{corrente}]format=yuv420p[v]"
    amap = ["-an"]
    musiche = [m for m in musiche if m and os.path.exists(m)]
    if musiche:
        quanti = max(1, int(DUR // 4.7) + 1)       # pezzi da ~5 s dello stesso brano, uniti con sfumatura
        musiche = (musiche * quanti)[:quanti]
        for m in musiche:
            cmd += ["-i", m]
        ingressi = [f"[{idx + j}:a]" for j in range(len(musiche))]
        if len(ingressi) == 1:
            a_out = ingressi[0]
        else:
            prec = ingressi[0]
            for j, x in enumerate(ingressi[1:]):
                g += f";{prec}{x}acrossfade=d=0.3[x{j}]"
                prec = f"[x{j}]"
            a_out = prec
        g += (f";{a_out}volume={ov.MUSIC_VOL},{ov.LIMITATORE},apad,atrim=0:{DUR},"
              f"afade=t=out:st={DUR - 0.3}:d=0.3[a]")
        amap = ["-map", "[a]"]
    cmd += ["-filter_complex", g, "-map", "[v]", *amap, "-t", f"{DUR}", "-c:v", "libx264",
            "-preset", "medium" if DUR <= 10 else "veryfast", "-crf", "18", "-profile:v", "high",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-movflags", "+faststart", dst]
    r = subprocess.run(cmd, capture_output=True, text=True, errors="ignore", timeout=ov.TEMPO_MAX_MONTAGGIO)
    shutil.rmtree(tmp, ignore_errors=True)
    if r.returncode != 0 or not os.path.exists(dst) or os.path.getsize(dst) < 50_000:
        raise RuntimeError(f"{nome}: " + r.stderr[-400:])
    return {"formato": nome, "durata": DUR, "musica": os.path.basename(musiche[0]) if musiche else None,
            "stacchi": n, "testi": len(testi)}


def make_broll(nome, clips, frase, dst, musiche=(), serie=None):
    """broll1/2/3: stacchi veloci di b-roll con la frase (fissa o a pezzi)."""
    d = FORMATI[nome]
    durate = d["stacchi"]
    if d["testo"] == "fisso":
        testi = [(0.0, sum(durate), frase)]
    else:
        # pezzi di senso compiuto (circa 5 parole l'uno, mai piu' degli stacchi), distribuiti sugli stacchi
        n = min(len(durate), max(2, round(len(frase.split()) / 5)))
        pezzi = dividi_in(frase, n)
        tot, testi = sum(durate), []
        tagli = [sum(durate[:i]) for i in range(len(durate) + 1)]          # istanti degli stacchi
        for i, p in enumerate(pezzi):
            a = tagli[round(i * len(durate) / len(pezzi))]
            b = tot if i == len(pezzi) - 1 else tagli[round((i + 1) * len(durate) / len(pezzi))]
            testi.append((a, b, p))
    return make_sequenza(clips, durate, testi, dst, musiche, serie, nome)


def make_storia(clips, titolo, righe, dst, musiche=(), serie=None):
    """storia: titolo poi le righe, una schermata alla volta (racconto di ~22 s)."""
    sch = FORMATI["storia"]["schermate"][:1 + len(righe[:3])]
    testi, t0 = [], 0.0
    for i, (dur, t) in enumerate(zip(sch, [titolo] + [f"{k}. {r}" for k, r in enumerate(righe[:3], 1)])):
        testi.append((t0, t0 + dur, t))
        t0 += dur
    # sfondo: pezzi lunghi (6-8 s) dalle clip, cosi' si legge con calma
    totale, durate = sum(sch), []
    while sum(durate) < totale - 0.01:
        durate.append(min(7.0, round(totale - sum(durate), 2)))
    return make_sequenza(clips, durate, testi, dst, musiche, serie, "storia")
