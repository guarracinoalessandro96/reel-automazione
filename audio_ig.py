"""
Audio dei reel Instagram (3/11/2026). Il brano sta dentro al file (il brano nativo via API non viene applicato), quindi
qui si cura tutto cio' che dipende da noi: punto di partenza del brano, colpo sullo stacco, controllo del file PRIMA di
pubblicare, controllo di quello che Instagram ha davvero pubblicato, nome dell'audio.
"""
import os, re, subprocess
import numpy as np
import overlay

FFMPEG = overlay.FFMPEG
PASSO = 0.05                  # risoluzione dell'analisi del brano: 50 ms
LUFS_MIN, LUFS_MAX = -19.0, -10.0
SILENZIO_MAX = 1.2            # un buco piu' lungo di cosi' a meta' reel e' un difetto
NOMI_AUDIO = {"phonk": "Phonk motivazione", "drive": "Drive motivazione", "trap": "Trap motivazione",
              "deciso": "Carica decisa", "energia": "Energia pura"}


def genere(nome):
    return re.sub(r"[_\d]+$", "", os.path.splitext(os.path.basename(nome))[0])


def nome_audio(brano):
    """Nome pubblico dell'audio su Instagram: senza, resta 'Audio originale' e nessuno lo ritrova."""
    return NOMI_AUDIO.get(genere(brano or ""))


def ammesso(brano):
    """Mai la Raccolta audio di YouTube fuori da YouTube."""
    return not re.search(r"[\\/]yt_[^\\/]*[\\/]", brano) and not os.path.basename(brano).endswith(".m4a")


def inviluppo(brano):
    """Forza dei colpi del brano, un valore ogni PASSO secondi."""
    sr = 11025
    raw = subprocess.run([FFMPEG, "-v", "error", "-i", brano, "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                         capture_output=True, timeout=120).stdout
    a = np.frombuffer(raw, "<f4")
    n = int(sr * PASSO)
    k = len(a) // n
    if not k:
        return np.zeros(1)
    e = np.log1p(100 * np.sqrt((a[:k * n].reshape(k, n) ** 2).mean(axis=1)))
    o = np.maximum(np.diff(e, prepend=e[0]), 0)
    return o / (o.max() or 1)


def stacchi(video):
    """Secondi in cui il video cambia inquadratura."""
    r = subprocess.run([FFMPEG, "-hide_banner", "-i", video, "-an", "-vf", "scale=160:-2,select='gt(scene,0.35)',showinfo",
                        "-f", "null", "-"], capture_output=True, text=True, errors="ignore", timeout=300).stderr
    return [float(x) for x in re.findall(r"pts_time:([\d.]+)", r)]


def punto_inizio(brano, tagli=()):
    """Da dove far partire il brano: su un colpo forte (mai dall'intro), scegliendo quello che porta un altro colpo
    sugli stacchi del video."""
    o = inviluppo(brano)
    meglio, inizio = -1.0, 0
    for s in np.argsort(o)[-10:]:
        forza = o[s] + 0.6 * sum(o[(s + round(t / PASSO)) % len(o)] for t in tagli)
        if forza > meglio:
            meglio, inizio = forza, int(s)
    return round(inizio * PASSO, 2)


# 6/11/2026 (Alessandro: "non devi prendere la musica dall'inizio ma nel momento piu' virale: i suoni di tendenza
# partono gia' dal ritornello"): l'API di Instagram NON fa scegliere da dove parte il brano (audio_configuration ha solo
# audio_id, audio_volume e video_volume; /ig_audio non da' il punto del ritornello: provato il 6/11 sulla v26), quindi
# il brano parte dal secondo 0. Dei brani della libreria Instagram da' il file intero (download_url): si controlla che
# parta GIA' forte. Sui 36 brani della Raccolta di YouTube presi dall'inizio passerebbero solo in 6: gli altri hanno un
# intro di 5-20 s (primo secondo da 10 a 80 dB sotto i momenti forti).
APERTURA_PRIMO_MIN = -6.0     # dB, il primo secondo rispetto ai momenti forti del brano (90esimo percentile)
APERTURA_DIECI_MIN = -5.0     # dB, i primi 10 s
APERTURA_SALTO_MAX = 6.0      # dB, un salto di volume nei primi 10 s = il drop arriva dopo (si parte dal crescendo)


def apertura_pcm(x, sr=8000):
    """Quanto e' forte l'inizio di un brano (x: campioni mono): dB del primo secondo e dei primi 10 s rispetto ai
    momenti forti, salto di volume piu' grande nei primi 10 s, e forte = parte gia' pieno."""
    n = sr // 2
    k = len(x) // n
    if k < 24:
        return None
    db = 10 * np.log10((np.asarray(x[:k * n], np.float64).reshape(k, n) ** 2).mean(axis=1) + 1e-10)
    p90 = float(np.percentile(db, 90))
    salto = max(float(db[i:i + 4].mean() - db[i - 4:i].mean()) for i in range(4, 17))
    primo, dieci = float(db[:2].mean() - p90), float(db[:20].mean() - p90)
    return {"primo": round(primo, 1), "dieci": round(dieci, 1), "salto": round(salto, 1),
            "forte": primo >= APERTURA_PRIMO_MIN and dieci >= APERTURA_DIECI_MIN and salto < APERTURA_SALTO_MAX}


def apertura(url, timeout=30):
    """apertura_pcm del file di un brano di Instagram (download_url, ~0,5 MB). None se non si riesce a leggerlo."""
    import tempfile, requests
    tmp = None
    try:
        r = requests.get(url, timeout=timeout, stream=True)
        r.raise_for_status()
        fd, tmp = tempfile.mkstemp(suffix=".m4a")
        with os.fdopen(fd, "wb") as f:
            letti = 0
            for pezzo in r.iter_content(256 * 1024):
                f.write(pezzo)
                letti += len(pezzo)
                if letti > 25e6:
                    raise ValueError("file troppo grande")
        raw = subprocess.run([FFMPEG, "-v", "error", "-i", tmp, "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
                             capture_output=True, timeout=90).stdout
        return apertura_pcm(np.frombuffer(raw, "<i2").astype(np.float32) / 32768)
    except Exception:
        return None
    finally:
        if tmp:
            try:
                os.remove(tmp)      # file temporaneo nostro (copia scaricata), non dati di Alessandro
            except OSError:
                pass


def _misura(path):
    return subprocess.run([FFMPEG, "-hide_banner", "-nostats", "-i", path, "-af",
                           f"ebur128=peak=true,silencedetect=n=-45dB:d=0.4", "-vn", "-f", "null", "-"],
                          capture_output=True, text=True, errors="ignore", timeout=300).stderr


def difetti_audio(testo):
    """Cosa c'e' che non va nell'audio, dall'uscita di _misura. Lista vuota = a posto."""
    flusso = re.search(r"Stream #.*Audio: (\w+).*?(\d+) Hz, (\w+)", testo)
    if not flusso:
        return ["senza traccia audio"]
    p = []
    if flusso.group(1) != "aac":
        p.append("codec " + flusso.group(1))
    if int(flusso.group(2)) > 48000:
        p.append("frequenza " + flusso.group(2))
    if flusso.group(3) not in ("stereo", "mono"):
        p.append("canali " + flusso.group(3))
    lufs = re.findall(r"I:\s+(-?[\d.]+|nan|-inf) LUFS", testo)
    v = float(lufs[-1]) if lufs and lufs[-1] not in ("nan", "-inf") else -99.0
    if not LUFS_MIN <= v <= LUFS_MAX:
        p.append(f"volume {v:.1f} LUFS")
    for s in re.findall(r"silence_end: ([\d.]+) \| silence_duration: ([\d.]+)", testo):
        if float(s[1]) >= SILENZIO_MAX or float(s[0]) - float(s[1]) < 0.05:
            p.append(f"silenzio di {float(s[1]):.1f} s")
            break
    return p


def controlla(path):
    """Controllo del file prima di caricarlo su Instagram."""
    return difetti_audio(_misura(path))


def controlla_pubblicato(url):
    """Controllo di cio' che Instagram ha pubblicato davvero (video dritto, audio presente)."""
    testo = _misura(url)
    dim = re.search(r"Stream #.*Video:.*?, (\d{3,5})x(\d{3,5})", testo)
    p = [x for x in difetti_audio(testo) if not x.startswith(("codec", "frequenza"))]
    if dim and int(dim.group(1)) > int(dim.group(2)):
        p.append(f"video di lato {dim.group(1)}x{dim.group(2)}")
    return p
