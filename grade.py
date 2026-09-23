"""
Color correction automatica "da professionista" per ogni reel.

1. ANALISI dei fotogrammi (gia' in colori normali): luminosita', punto nero/bianco, dominante di colore,
   saturazione, rumore, presenza di cielo/mare, luce calda artificiale.
2. SCENA riconosciuta: mare, esterno giorno, sera/notte, interno caldo (ristorante, casa la sera),
   interno (ufficio, palestra...). Si puo' forzare con una parola nel nome del file:
   "palestra", "mare", "ristorante", "ufficio", "sera", "esterno".
3. REGOLAZIONI calcolate per quel video: riduzione rumore, bilanciamento del bianco, temperatura,
   esposizione, punto nero/bianco, luci e ombre, contrasto, saturazione, vividezza, definizione,
   nitidezza, vignettatura + un "look" leggero e sempre uguale (ombre fredde, luci calde) per dare
   al profilo uno stile riconoscibile.

build_filter() restituisce la catena di filtri ffmpeg da applicare prima del testo.
"""
import cv2
import numpy as np

INTENSITA = 1.0     # 0 = nessuna correzione, 1 = normale, 1.3 = piu' marcata

# Profili per scena: ogni valore e' un "obiettivo" o un'intensita', poi adattato alle misure del video
PROFILI = {
    #                esposiz. contrasto satur. vividezza  calore  definiz. nitidezza  vignetta  ombre  luci
    "mare":        dict(l=0.50, con=1.06, sat=1.08, vib=0.30, warm=0.02, cla=0.30, sha=0.55, vig=0.35, sh=0.03, hl=0.05),
    "esterno":     dict(l=0.48, con=1.07, sat=1.05, vib=0.25, warm=0.02, cla=0.35, sha=0.55, vig=0.35, sh=0.04, hl=0.04),
    "sera":        dict(l=0.38, con=1.05, sat=1.00, vib=0.15, warm=0.04, cla=0.20, sha=0.35, vig=0.45, sh=0.06, hl=0.02),
    "interno_caldo": dict(l=0.43, con=1.06, sat=1.00, vib=0.18, warm=0.02, cla=0.25, sha=0.45, vig=0.40, sh=0.05, hl=0.03),
    "interno":     dict(l=0.46, con=1.07, sat=1.02, vib=0.20, warm=0.01, cla=0.30, sha=0.50, vig=0.35, sh=0.04, hl=0.03),
    "palestra":    dict(l=0.44, con=1.12, sat=0.98, vib=0.15, warm=0.01, cla=0.55, sha=0.70, vig=0.45, sh=0.03, hl=0.03),
}
PAROLE = {"palestra": "palestra", "gym": "palestra", "mare": "mare", "spiaggia": "mare", "ristorante": "interno_caldo",
          "cena": "interno_caldo", "ufficio": "interno", "lavoro": "interno", "sera": "sera", "notte": "sera",
          "esterno": "esterno", "fuori": "esterno"}


def analizza(frames, volti=None):
    """Misure medie sui fotogrammi (BGR uint8, gia' in SDR). volti: riquadri normalizzati (x1,y1,x2,y2)."""
    m = {k: [] for k in ("L", "p1", "p99", "a", "b", "sat", "noise", "sky", "blue", "gray")}
    for f in frames:
        f = cv2.resize(f, (360, int(360 * f.shape[0] / f.shape[1])))
        lab = cv2.cvtColor(f, cv2.COLOR_BGR2LAB).astype(np.float32)
        L, A, B = lab[..., 0] / 255, lab[..., 1] - 128, lab[..., 2] - 128
        hsv = cv2.cvtColor(f, cv2.COLOR_BGR2HSV)
        H, S, V = hsv[..., 0], hsv[..., 1], hsv[..., 2]
        mid = (L > 0.15) & (L < 0.9) & (S < 90)          # pixel "neutri" per stimare la dominante
        m["L"].append(L.mean())
        m["p1"].append(np.percentile(L, 1))
        m["p99"].append(np.percentile(L, 99.5))
        m["a"].append(A[mid].mean() if mid.any() else 0)
        m["b"].append(B[mid].mean() if mid.any() else 0)
        m["sat"].append(S.mean() / 255)
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32)
        resid = np.abs(g - cv2.GaussianBlur(g, (5, 5), 0))
        dark = g < 90
        m["noise"].append(resid[dark].mean() if dark.sum() > 500 else resid.mean())
        blue = (H >= 90) & (H <= 130) & (S > 50) & (V > 110)
        top = blue[: blue.shape[0] // 3]
        m["sky"].append(top.mean())
        m["blue"].append(blue.mean())
        bgr = f.reshape(-1, 3).astype(np.float32)
        m["gray"].append(bgr[mid.reshape(-1)].mean(axis=0) if mid.any() else bgr.mean(axis=0))
    out = {k: float(np.median(v)) for k, v in m.items() if k != "gray"}
    if volti:   # luminosita' del viso: centro del riquadro (senza i margini di sicurezza)
        vals = []
        for f in frames[::2]:
            h, w = f.shape[:2]
            L = cv2.cvtColor(f, cv2.COLOR_BGR2LAB)[..., 0]
            for (x1, y1, x2, y2) in volti[:20]:
                cx1, cx2 = int((x1 + (x2 - x1) * 0.3) * w), int((x1 + (x2 - x1) * 0.7) * w)
                cy1, cy2 = int((y1 + (y2 - y1) * 0.35) * h), int((y1 + (y2 - y1) * 0.6) * h)
                if cx2 > cx1 and cy2 > cy1:
                    vals.append(L[max(cy1, 0):cy2, max(cx1, 0):cx2].mean() / 255)
        if vals:
            out["viso"] = float(np.median(vals))
    out["gray"] = np.median(np.array(m["gray"]), axis=0).tolist()   # B, G, R medi dei pixel neutri
    return out


def scena(misure, nome_file=""):
    n = nome_file.lower()
    for parola, s in PAROLE.items():
        if parola in n:
            return s, "dal nome del file"
    L, b = misure["L"], misure["b"]
    if L < 0.28 or misure["p99"] < 0.6:
        return "sera", "poca luce"
    if misure["blue"] > 0.22 and L > 0.42:
        return "mare", "molto azzurro"
    if misure["sky"] > 0.12 and L > 0.40:
        return "esterno", "cielo visibile"
    if L > 0.55 and misure["p99"] > 0.95:
        return "esterno", "luce del giorno"
    if b > 7 and L < 0.50:
        return "interno_caldo", "luce calda artificiale"
    return "interno", "luce neutra"


def _c(x, lo, hi):
    return max(lo, min(hi, x))


def build_filter(misure, tipo, intensita=INTENSITA):
    """Catena ffmpeg (senza etichette) calcolata dalle misure e dal profilo della scena."""
    p = PROFILI[tipo]
    k = intensita
    f = []

    # 1. riduzione rumore (prima di tutto, prima di aumentare la nitidezza)
    noise = misure["noise"]
    if tipo == "sera" or (misure["L"] < 0.40 and noise > 2.5):
        s = _c((noise - 1.5) * 0.8, 0.8, 3.0) * k
        f.append(f"hqdn3d={s:.2f}:{s * 0.75:.2f}:{s * 1.5:.2f}:{s * 1.1:.2f}")

    # 2. bilanciamento del bianco (grey world parziale) + temperatura del profilo
    bgr = np.array(misure["gray"]) + 1e-3
    gains = bgr.mean() / bgr                      # guadagni per B, G, R
    forza = 0.15
    if misure["b"] < -3 or misure["a"] < -3:      # luce fredda o verdastra (neon, ufficio): si corregge di piu'
        forza = 0.5
    elif misure["b"] > 14:                        # luce gialla/arancione molto forte (lampadine): un po' di piu'
        forza = 0.35
    gains = 1 + (gains - 1) * forza * k
    gains = np.clip(gains, 0.92, 1.08)
    w = p["warm"] * k
    rr, gg, bb = gains[2] * (1 + w), gains[1] * (1 + w * 0.2), gains[0] * (1 - w)
    f.append(f"colorchannelmixer=rr={rr:.3f}:gg={gg:.3f}:bb={bb:.3f}")

    # 3. punto nero / punto bianco (stretching leggero)
    blk = _c(misure["p1"] * 0.6 * k, 0, 0.08)
    wht = _c(1 - (1 - min(misure["p99"], 1)) * 0.6 * k, 0.85, 1.0)
    f.append(f"colorlevels=rimin={blk:.3f}:gimin={blk:.3f}:bimin={blk:.3f}:rimax={wht:.3f}:gimax={wht:.3f}:bimax={wht:.3f}")

    # 4. esposizione: porta la luminosita' media verso l'obiettivo della scena (gamma)
    if misure.get("viso"):                        # c'e' un viso: e' lui che deve essere esposto bene
        L, target = max(misure["viso"], 0.05), 0.52
    else:
        L, target = max(misure["L"], 0.05), p["l"]
    g = np.log(target) / np.log(L)                # esponente che porta L sul target
    g = _c(g, 0.75, 1.15)                         # schiarire fino a +, scurire al massimo un poco
    gamma = 1 + (1 / g - 1) * 0.6 * k             # eq: gamma > 1 schiarisce
    # 5. luci e ombre + contrasto morbido (curva a S)
    sh, hl = p["sh"] * k, p["hl"] * k
    f.append("curves=m='0/0 0.12/%.3f 0.30/%.3f 0.50/0.50 0.72/%.3f 0.90/%.3f 1/0.985'"
             % (0.12 + sh * 0.6, 0.30 + sh * 0.5, 0.72 + 0.015, 0.90 - hl * 0.5))
    con = 1 + (p["con"] - 1) * k
    sat = 1 + (p["sat"] - 1) * k
    if misure["sat"] > 0.45:                      # gia' molto saturo: non esagerare
        sat = min(sat, 1.0)
    f.append(f"eq=gamma={gamma:.3f}:contrast={con:.3f}:saturation={sat:.3f}")

    # 6. vividezza (satura di piu' i colori spenti, protegge la pelle)
    f.append(f"vibrance=intensity={p['vib'] * k:.2f}")

    # 7. look del profilo: ombre leggermente fredde, luci leggermente calde
    lk = 0.035 * k
    f.append(f"colorbalance=rs={-lk:.3f}:bs={lk:.3f}:rh={lk * 0.8:.3f}:bh={-lk * 0.8:.3f}")

    # 8. definizione (contrasto locale ampio) e nitidezza (dettaglio fine)
    f.append(f"unsharp=13:13:{p['cla'] * k:.2f}:13:13:0")
    f.append(f"unsharp=5:5:{p['sha'] * k:.2f}:5:5:0")

    # 9. vignettatura leggera
    f.append(f"vignette=angle={0.25 + p['vig'] * 0.6 * k:.2f}")
    return ",".join(f)


def descrivi(misure, tipo, motivo):
    return {"scena": tipo, "motivo": motivo, "luce": round(misure["L"], 2),
            "dominante": "calda" if misure["b"] > 4 else "fredda" if misure["b"] < -4 else "neutra",
            "rumore": round(misure["noise"], 1)}
