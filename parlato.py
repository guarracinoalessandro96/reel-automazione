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
    # 12/11/2026 (Alessandro: "tutti i video devono essere di 10 secondi"): il reel parlato si ferma a 10 s
    # 15/11/2026 (Alessandro: "impostiamo la durata dei reel di 8 secondi"): si ferma a overlay.DURATA_REEL (8 s)
    import overlay
    fine = min(durata_video, parole[-1]["e"] + 0.6, inizio + overlay.DURATA_REEL)
    # 20/11/2026, Alessandro: "tutti i video devono essere di 7 secondi": il reel parlato dura SEMPRE overlay.DURATA_REEL
    # (7 s) se il video e' lungo almeno 7 s: se le parole finiscono prima si tiene il video fino a 7 s (prima o dopo le
    # parole, dentro il video). Un video piu' corto di 7 s non esce come parlato (pubblica.monta_parlato -> ripiego)
    D = float(overlay.DURATA_REEL)
    if durata_video >= D:
        inizio = min(inizio, max(0.0, durata_video - D))
        return round(float(inizio), 2), round(D, 2)
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


# 20/11/2026 (Alessandro: "voglio che le scritte non stiano mai sulla mia faccia"): anche i sottotitoli dei parlati.
# Si parte dal posto di sempre (terzo basso); se la fascia dei sottotitoli tocca un viso del pezzo si sposta (dentro il
# 10%-80% dell'altezza) nel punto libero piu' vicino; se non c'e' si rimpicciolisce (fino al 60%); se neanche cosi':
# SottotitoliSulViso (il reel esce col ripiego, una scena da 7 s con la frase, anche quella mai sul viso)
FASCIA_RIGHE = 2.6       # altezza della fascia dei sottotitoli in corpi (fino a 2 righe con il contorno)


class SottotitoliSulViso(Exception):
    pass


def posto_sottotitoli(visi, larghezza=1080, altezza=1920):
    """(MarginV, corpo) dei sottotitoli che non toccano i visi (frazioni). Alza SottotitoliSulViso se non c'e' posto."""
    f = larghezza / 1080
    corpo0, margine0 = round(86 * f), round(560 * f)
    lati = round(70 * f)
    for k in (1.0, 0.9, 0.8, 0.7, 0.6):
        corpo = round(corpo0 * k)
        alto = corpo * FASCIA_RIGHE
        fondi = [altezza - margine0] + sorted(range(int(altezza * 0.10 + alto), int(altezza * 0.80) + 1,
                                                    max(1, altezza // 200)), key=lambda y: abs(y - (altezza - margine0)))
        for fondo in fondi:
            y0, y1 = fondo - alto, fondo
            if y0 < altezza * 0.10 or y1 > altezza * 0.80 + 1:
                continue
            if not any(min(larghezza - lati, v[2] * larghezza) > max(lati, v[0] * larghezza)
                       and min(y1, v[3] * altezza) > max(y0, v[1] * altezza) for v in visi or []):
                return altezza - fondo, corpo
    raise SottotitoliSulViso(f"{len(visi or [])} riquadri di visi")


def file_ass(blocchi_, inizio, path, larghezza=1080, altezza=1920, visi=None):
    """Scrive il file .ass: testo bianco grassetto con contorno nero, centrato nel terzo basso.
    20/11/2026: con visi (frazioni) la fascia non li tocca mai (posto_sottotitoli). -> (path, MarginV, corpo)."""
    f = larghezza / 1080                     # misure pensate per 1080 (4K dal 25/10/2026)
    margine, corpo = (round(560 * f), round(86 * f)) if visi is None else posto_sottotitoli(visi, larghezza, altezza)
    righe = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {larghezza}", f"PlayResY: {altezza}", "",
             "[V4+ Styles]",
             "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
             "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
             "MarginR, MarginV, Encoding",
             f"Style: Sub,Poppins,{corpo},&H00FFFFFF,&H000000FF,&H00000000,&H78000000,-1,0,0,0,100,100,0,0,1,"
             f"{round(6 * f)},{round(2 * f)},2,{round(70 * f)},{round(70 * f)},{margine},1",
             "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    for a, b, t in blocchi_:
        t = re.sub(r"[{}\\]", "", t)
        righe.append(f"Dialogue: 0,{_tempo(a - inizio)},{_tempo(b - inizio)},Sub,,0,0,0,,{t}")
    open(path, "w", encoding="utf-8").write("\n".join(righe) + "\n")
    return path, margine, corpo
