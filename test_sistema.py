"""
Test automatico del montaggio: da lanciare DOPO OGNI MODIFICA, prima del commit.
  python test_sistema.py            (completo, ~25 minuti su un PC lento)
  python test_sistema.py --veloce   (un solo video + tutti gli altri controlli)
Crea video sintetici "difficili" (orizzontale, quadrato, 60 fps muto, cortissimo, 720p), li monta e controlla:
formato 1080x1920, durata, audio presente, volume vicino a -15 LUFS e picchi sotto 0 dB, piano di riserva
(musica inesistente -> il reel esce lo stesso, senza musica), parole chiave nei nomi file, scorta musica e citazioni.
Usa video piccoli: gira in pochi minuti. Esce con codice 1 se qualcosa non va.
"""
import glob, json, os, re, subprocess, sys, tempfile
import overlay, scena

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(tempfile.gettempdir(), "test_sistema")
os.makedirs(D, exist_ok=True)
F = overlay.FFMPEG
errori = []


def check(cond, msg):
    print(("ok    " if cond else "ERRORE") + "  " + msg, flush=True)
    if not cond:
        errori.append(msg)


def sorgente(nome, w, h, fps, sec, audio=True):
    p = os.path.join(D, nome + ".mp4")
    if not os.path.exists(p):
        cmd = [F, "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=s={w}x{h}:r={fps}:d={sec}"]
        if audio:
            cmd += ["-f", "lavfi", "-i", f"sine=f=330:d={sec}"]
        subprocess.run(cmd + ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", p], check=True)
    return p


def misura(path):
    r = subprocess.run([F, "-hide_banner", "-i", path, "-af", "loudnorm=print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True, errors="ignore").stderr
    v = re.search(r"Video: .*?(\d{3,4})x(\d{3,4})", r)
    d = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r)
    j = json.loads(r[r.rindex("{"):r.rindex("}") + 1]) if "input_i" in r else {}
    return (int(v.group(1)), int(v.group(2))) if v else None, float(d.group(3)) if d else 0, \
        float(j.get("input_i", -99)), float(j.get("input_tp", 0)), "Audio:" in r


def main():
    musica = sorted(glob.glob(os.path.join(HERE, "musica", "phonk", "*.flac")))[0]
    casi = [("orizzontale", 1280, 720, 30, 11, True, 8.0), ("quadrato", 720, 720, 30, 11, True, 8.0),
            ("verticale_60fps_muto", 720, 1280, 60, 11, False, 8.0), ("cortissimo", 720, 1280, 30, 2.5, True, 2.5),
            ("verticale_720p", 720, 1280, 30, 12, True, 8.0)]
    if "--veloce" in sys.argv:      # PC lento: un solo caso di montaggio + tutti gli altri controlli
        casi = casi[:1]
    for nome, w, h, fps, sec, audio, durata in casi:
        dst = os.path.join(D, nome + "_reel.mp4")
        try:
            info = overlay.make_video(sorgente(nome, w, h, fps, sec, audio), "Prova del sistema di montaggio automatico.",
                                      dst, music=musica, autore="Test", nome=nome)
            dim, dur, lufs, tp, ha_audio = misura(dst)
            check(dim == (1080, 1920), f"{nome}: formato {dim}")
            check(abs(dur - durata) < 0.15, f"{nome}: durata {dur:.2f}s (attesa {durata})")
            check(ha_audio, f"{nome}: audio presente")
            check(-17.5 < lufs < -12.5 and tp < 0, f"{nome}: volume {lufs:.1f} LUFS, picco {tp:.1f} dBTP")
            check("ripiego" not in info, f"{nome}: nessun piano di riserva usato")
        except Exception as e:
            check(False, f"{nome}: montaggio fallito ({e})")
    # piano di riserva: musica inesistente -> deve uscire lo stesso, senza musica
    dst = os.path.join(D, "riserva_reel.mp4")
    try:
        info = overlay.make_video(sorgente("verticale_720p", 720, 1280, 30, 12), "Prova.", dst,
                                  music=os.path.join(HERE, "musica", "non_esiste.flac"))
        check(info.get("musica") is None and misura(dst)[0] == (1080, 1920),
              "riserva: con un brano mancante il reel esce lo stesso (senza musica, con zoom e colore)")
    except Exception as e:
        check(False, f"riserva: non ha funzionato ({e})")
    for n, s in (("palestra_1.mov", "palestra"), ("cibo-pranzo.MOV", "cibo"), ("IMG_0001 pacchi.mov", "pacchi")):
        check(scena.riconosci([], n)[0] == s, f"nome file '{n}' -> {s}")
    for g in ("phonk", "drive", "house", "lofi", "tropical", "trap", "caldo"):
        n = len(glob.glob(os.path.join(HERE, "musica", g, "*.flac")))
        check(n >= 8, f"musica {g}: {n} brani")
    frasi = json.load(open(os.path.join(HERE, "frasi.json"), encoding="utf-8"))
    check(len(frasi) >= 300, f"citazioni: {len(frasi)}")
    check(not [f for f in frasi if re.search(r"trent'anni|30 anni|#30anni", f["gancio"] + " ".join(f["hashtag"]), re.I)],
          "nessuna citazione con l'eta'")
    print("\nTUTTO OK" if not errori else f"\n{len(errori)} PROBLEMI")
    sys.exit(1 if errori else 0)


if __name__ == "__main__":
    main()
