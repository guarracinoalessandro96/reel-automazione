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
