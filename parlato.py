"""
Video PARLATI (18/10/2026): quando Alessandro parla in camera da solo, il reel tiene la SUA VOCE (niente musica)
con SOTTOTITOLI automatici grandi. Trascrizione con faster-whisper (modello "small", italiano, sul computer di
GitHub: gratis, niente servizi esterni). Il modello si scarica una volta e resta nella cache di GitHub.

- trascrivi(video) -> parole con i tempi
- e_parlato(parole, durata) -> True se nel video si parla davvero (non solo rumori)
- blocchi(parole) -> sottotitoli da 1-3 parole che seguono la voce
- file_ass(blocchi, inizio) -> file di sottotitoli in stile reel (bianco grande, contorno nero)
Se qualcosa non va (libreria mancante, audio strano) il video resta un reel normale: mai bloccare la pubblicazione.
"""
import os, re

MODELLO = os.environ.get("WHISPER_MODELLO") or "small"
CARTELLA_MODELLO = os.path.join(os.path.expanduser("~"), ".cache", "whisper")
MAX_SECONDI = 60          # i reel parlati durano al massimo un minuto
_modello = None


def _carica():
    global _modello
    if _modello is None:
        try:
            from faster_whisper import WhisperModel
        except ImportError:     # su GitHub si installa solo quando arriva un video parlato (i reel normali non aspettano)
            import importlib, subprocess, sys
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "faster-whisper"], check=True, timeout=600)
            importlib.invalidate_caches()
            from faster_whisper import WhisperModel
        _modello = WhisperModel(MODELLO, device="cpu", compute_type="int8", download_root=CARTELLA_MODELLO)
    return _modello


def trascrivi(path, max_sec=150):
    """[{"w": parola, "s": inizio, "e": fine, "p": sicurezza}] dei primi max_sec secondi (lingua italiana)."""
    segmenti, _ = _carica().transcribe(path, language="it", word_timestamps=True, vad_filter=True, beam_size=1,
                                       condition_on_previous_text=False)
    parole = []
    for seg in segmenti:
        if seg.start > max_sec:
            break
        for w in seg.words or []:
            t = w.word.strip()
            if t:
                parole.append({"w": t, "s": round(float(w.start), 2), "e": round(float(w.end), 2),
                               "p": round(float(w.probability), 2)})
    return parole


def e_parlato(parole, durata):
    """Parla davvero? Almeno 12 parole capite bene e voce per almeno un terzo del video."""
    if len(parole) < 12:
        return False
    sicurezza = sum(p["p"] for p in parole) / len(parole)
    voce = sum(p["e"] - p["s"] for p in parole)
    return sicurezza >= 0.55 and voce >= 0.33 * min(max(durata, 1), MAX_SECONDI)


def testo(parole):
    return re.sub(r"\s+([,.!?])", r"\1", " ".join(p["w"] for p in parole)).strip()


def taglio(parole, durata_video):
    """(inizio, durata) del reel: dalla prima all'ultima parola (massimo MAX_SECONDI)."""
    inizio = max(0.0, parole[0]["s"] - 0.3)
    fine = min(durata_video, parole[-1]["e"] + 0.6, inizio + MAX_SECONDI)
    return round(float(inizio), 2), round(float(max(fine - inizio, 3.0)), 2)


def blocchi(parole, max_parole=3, max_caratteri=20):
    """Sottotitoli corti che seguono la voce: [(inizio, fine, testo)]."""
    out, cur = [], []
    for p in parole:
        cur.append(p)
        t = " ".join(x["w"] for x in cur)
        if len(cur) >= max_parole or len(t) >= max_caratteri or re.search(r"[.!?,:]$", p["w"]):
            out.append([cur[0]["s"], cur[-1]["e"], t])
            cur = []
    if cur:
        out.append([cur[0]["s"], cur[-1]["e"], " ".join(x["w"] for x in cur)])
    for i in range(len(out) - 1):                      # niente buchi brevi: il blocco resta fino al successivo
        if out[i + 1][0] - out[i][1] < 0.6:
            out[i][1] = out[i + 1][0]
    return [(a, b, t) for a, b, t in out]


def _tempo(t):
    t = max(t, 0)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def file_ass(blocchi_, inizio, path, larghezza=1080, altezza=1920):
    """Scrive il file .ass: testo bianco grassetto con contorno nero, centrato nel terzo basso."""
    righe = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {larghezza}", f"PlayResY: {altezza}", "",
             "[V4+ Styles]",
             "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
             "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
             "MarginR, MarginV, Encoding",
             "Style: Sub,Poppins,86,&H00FFFFFF,&H000000FF,&H00000000,&H78000000,-1,0,0,0,100,100,0,0,1,6,2,2,70,70,560,1",
             "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    for a, b, t in blocchi_:
        t = re.sub(r"[{}\\]", "", t)
        righe.append(f"Dialogue: 0,{_tempo(a - inizio)},{_tempo(b - inizio)},Sub,,0,0,0,,{t}")
    open(path, "w", encoding="utf-8").write("\n".join(righe) + "\n")
    return path
