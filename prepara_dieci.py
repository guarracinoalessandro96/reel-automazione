"""
Musica per i reel da 10 s (31/10/2026). Finora un reel da 10 s univa due pezzi da 5 s NON consecutivi dello stesso brano:
a meta' video la musica saltava. Qui si estrae da ogni brano originale (musica_youtube_originali/, solo su questo PC) un
pezzo UNICO da 10,5 s: parte forte, sul colpo, senza stacchi. Finisce in musica/yt_dieci/.
Restano fuori i brani con la mediana piu' bassa su YouTube (dati 20-30/10/2026, sotto 100 visualizzazioni).
6/11/2026 (Alessandro: "ogni video una musica diversa da altri video, su ogni piattaforma"): rientrano i 5 esclusi
(energia e colpi al secondo nella media degli altri, misurati sui pezzi): 36 brani -> mai lo stesso brano negli ultimi
30 Short (pubblica.YT_FINESTRA_BRANI). I brani forti restano preferiti (pesi.json, aggiornato la domenica).
6/11/2026 (Alessandro: "non devi prendere la musica dall'inizio ma nel momento piu' virale: i suoni di tendenza partono
gia' dal ritornello"): i pezzi partono dove ENTRA la parte piu' forte del brano (ritornello / drop), sul colpo, con il
primo secondo gia' pieno (inizi_ritornello). Prima si prendeva il tratto piu' forte e costante, ma quasi sempre a meta'
sezione: solo 11 pezzi su 108 partivano su un'entrata.
  python prepara_dieci.py           pezzi da 10,5 s mancanti in musica/yt_dieci/
  python prepara_dieci.py lunghi [brano...]   per ogni pezzo la versione da 20,5 s (stesso inizio e volume)
                                             in musica/yt_venti/; con i nomi, solo quei brani
  python prepara_dieci.py rifai [--tutti] [brano...]   rifa' i pezzi (yt_dieci e yt_venti) che col ritornello partono
                                             da un altro punto (--tutti: anche gli altri); con i nomi, solo quei brani
                                             (al massimo 6 per volta, col lucchetto del PC)
"""
import glob, os, re, subprocess, sys
import numpy as np
import prepara_libreria as pl

ESCLUSI = set()
LUNGO = 20.5     # 6/11/2026: il formato "intero" dura fino a 20 s; col pezzo da 10,5 s la musica ripartiva da capo a 10 s
SR, HOP, NFFT, BL = 8000, 200, 1024, 20      # analisi a 8 kHz: fotogrammi da 25 ms, blocchi da 0,5 s
FPS = SR // HOP


def _mappa(x):
    """6/11/2026: la "mappa" del brano, solo numpy: volume ogni 25 ms e ogni 0,5 s, colpi (flusso spettrale),
    quanto ogni tratto si ripete nel brano (ritornello) e dove cambia sezione (novita', nucleo a scacchiera di Foote
    sulla matrice di somiglianza di timbro e armonia)."""
    x = np.asarray(x, np.float32)
    fr = np.lib.stride_tricks.sliding_window_view(x, NFFT)[::HOP]
    mag = np.abs(np.fft.rfft(fr * np.hanning(NFFT).astype(np.float32), axis=1)).astype(np.float32)
    f = np.fft.rfftfreq(NFFT, 1 / SR)
    pot = mag ** 2
    flux = np.r_[0, np.maximum(np.diff(np.log1p(10 * mag), axis=0), 0).sum(axis=1)]
    lim = np.geomspace(40, 3800, 17)                                   # 16 bande (timbro)
    bande = np.stack([pot[:, (f >= a) & (f < b)].sum(axis=1) for a, b in zip(lim, lim[1:])], 1)
    ok = (f >= 55) & (f <= 2000)
    nota = np.round(12 * np.log2(f[ok] / 440.0)).astype(int) % 12     # 12 note (armonia)
    croma = np.stack([pot[:, ok][:, nota == k].sum(axis=1) for k in range(12)], 1)
    nb = len(pot) // BL
    blocca = lambda a: a[:nb * BL].reshape(nb, BL, *a.shape[1:]).mean(axis=1)
    z = lambda a: (a - a.mean(axis=0)) / (a.std(axis=0) + 1e-9)
    tot = pot.sum(axis=1)
    c = {"forte": 10 * np.log10(blocca(tot) + 1e-9), "pot_f": 10 * np.log10(tot + 1e-9), "flux": flux}
    cr, bd = blocca(croma), np.log10(blocca(bande) + 1e-9)
    F = np.hstack([z(cr / (np.linalg.norm(cr, axis=1, keepdims=True) + 1e-9)),
                   z(bd - bd.mean(axis=1, keepdims=True)), 2 * z(bd.mean(axis=1, keepdims=True))])
    F /= np.linalg.norm(F, axis=1, keepdims=True) + 1e-9
    S = F @ F.T
    B, L, K = len(S), 16, 8
    rip = np.zeros(B)
    for l in range(L, B - L):        # ripetizione: gli 8 s che partono da qui tornano piu' avanti o piu' indietro
        m = np.convolve(S[np.arange(B - l), np.arange(B - l) + l], np.ones(L) / L, "valid")
        k = np.arange(len(m))
        rip[k] = np.maximum(rip[k], m)
        rip[k + l] = np.maximum(rip[k + l], m)
    g = np.exp(-0.5 * np.linspace(-2, 2, 2 * K) ** 2)
    segno = np.r_[-np.ones(K), np.ones(K)]
    ker = np.outer(g, g) * np.outer(segno, segno)
    Sp = np.pad(S, K, mode="edge")
    nov = np.maximum([(Sp[b:b + 2 * K, b:b + 2 * K] * ker).sum() for b in range(B)], 0)
    c["rip"], c["nov"] = rip, nov / (nov.max() or 1)
    return c


def misura_pezzo(c, s, dur=10.5):
    """Indicatori di un pezzo che parte al secondo s (dB): forza rispetto ai momenti piu' forti del brano, primo
    secondo rispetto al resto, salto di volume all'entrata, salto DENTRO il pezzo (drop in ritardo = si parte dal
    crescendo), buco (pausa a meta'), ripetizione e confine di sezione. None se il brano finisce prima."""
    b, n, forte = int(round(s * 2)), int(dur * 2), c["forte"]
    dopo, prima = forte[b:b + n], forte[max(0, b - 8):b]
    if len(dopo) < n or b < 6:
        return None
    return {"forza": float(dopo.mean() - np.percentile(forte, 95)), "primo_s": float(dopo[:2].mean() - dopo.mean()),
            "entrata": float(dopo[:8].mean() - prima.mean()),
            "dentro": float(max(forte[b + k:b + k + 6].mean() - forte[b + k - 6:b + k].mean() for k in range(4, n - 6))),
            "buco": float(dopo.mean() - np.convolve(dopo, np.ones(2) / 2, "valid").min()),
            "rip": float(c["rip"][b:b + 16].mean()), "confine": float(c["nov"][max(0, b - 1):b + 2].max())}


def _punteggi(c, durata, dur=10.5):
    """Punteggio di ogni inizio possibile (ogni 0,5 s). Prima la forza: contano solo i tratti forti quasi come il piu'
    forte del brano (entro 1,5 dB); tra questi vince chi parte su un'entrata (salto di volume, confine di sezione) e
    si ripete (ritornello), senza drop in ritardo, buchi o primo secondo debole."""
    forte = c["forte"]
    B, n = len(forte), int(dur * 2)
    cs = np.r_[0, np.cumsum(forte)]
    media = lambda a, b: (cs[np.clip(b, 0, B)] - cs[np.clip(a, 0, B)]) / np.maximum(np.clip(b, 0, B) - np.clip(a, 0, B), 1)
    b = np.arange(B)
    forza = media(b, b + n) - np.percentile(forte, 95)
    primo = media(b, b + 2) - media(b, b + n)
    salto = media(b, b + 8) - media(b - 8, b)
    finestra = lambda a, w: np.lib.stride_tricks.sliding_window_view(np.r_[a, np.full(w + 8, -np.inf)], w)[:B]
    dentro = finestra((media(b, b + 4) - media(b - 4, b))[4:], 13).max(axis=1)       # salti tra 2 e 8,5 s
    sec1 = np.r_[media(b, b + 2), np.full(n, np.inf)]
    buco = media(b, b + n) - np.lib.stride_tricks.sliding_window_view(sec1, n - 1)[:B].min(axis=1)
    rip8 = np.convolve(np.r_[c["rip"], np.zeros(15)], np.ones(16) / 16, "valid")[:B]
    rip8 = (rip8 - np.median(rip8)) / (np.percentile(rip8, 95) - np.median(rip8) + 1e-9)
    confine = finestra(np.r_[0, c["nov"]], 3).max(axis=1)
    ok = (b / 2 >= 4.0) & (b / 2 + LUNGO + 1.5 <= durata) & (b + n <= B)
    meglio = float(forza[ok].max()) if ok.any() else 0.0
    sc = (forza + 0.35 * np.clip(salto, 0, 8) + 0.8 * confine + 0.6 * np.clip(rip8, -1, 1.5)
          - 1.5 * np.maximum(0, -primo - 0.5) - 0.8 * np.maximum(0, dentro - 3) - 0.6 * np.maximum(0, buco - 4)
          - 5.0 * (forza < meglio - 1.5))
    sc[~ok] = -1e9
    return sc, meglio


def _sull_entrata(c, s, x, cerca=1.5):
    """Se entro +-1,5 s il volume fa un salto (entra la batteria, parte il drop), l'inizio va esattamente li'; poi sul
    colpo piu' forte vicino, 20 ms prima dell'attacco. 6/11/2026 (revisione): il fotogramma i copre 25*i .. 25*i+128 ms
    (NFFT 1024 a 8 kHz) e il colpo cade 80-115 ms dopo il suo inizio: i pezzi partivano con circa 0,1 s di silenzio o
    di battuta prima. Ora l'attacco si rifinisce sul PCM x a passi di 10 ms (pl.sul_colpo, come i pezzi vecchi)."""
    pf, fl = c["pot_f"], c["flux"]
    w, cs = 2 * FPS, np.r_[0, np.cumsum(c["pot_f"])]
    a, b = max(w, int((s - cerca) * FPS)), min(len(pf) - w, int((s + cerca) * FPS))
    salto = 0.0
    if b > a:
        t = np.arange(a, b)
        J = (cs[t + w] - 2 * cs[t] + cs[t - w]) / w
        i = int(np.argmax(J))
        if J[i] > 3.0:
            s, salto = (a + i) / FPS, float(J[i])
    r = 0.12 if salto else 0.35
    a, b = max(1, int((s - r) * FPS)), min(len(fl), int((s + r) * FPS) + 1)
    if b <= a:
        return s
    t = (a + int(np.argmax(fl[a:b]))) / FPS       # inizio del fotogramma col colpo: l'attacco e' 80-115 ms dopo
    return _primo_colpo(x, pl.sul_colpo(x, t + 0.07, SR, cerca=0.12))


def _primo_colpo(x, s, fin=0.35, soglia=6.0, prima=0.12):
    """6/11/2026 (revisione): il primo colpo NETTO dopo l'inizio s (il volume a 10 ms sale di almeno 6 dB sulla media
    dei 30 ms prima) deve cadere 10-40 ms dopo l'inizio. Se arriva piu' tardi (entro 0,35 s: si partiva con un
    pezzetto della battuta prima) o troppo presto (attacco tagliato), l'inizio va 20 ms prima del suo attacco. Senza
    colpi netti (trama continua) o con un errore resta s.
    6/11/2026 (integrazione, revisione finale del ritornello): i colpi netti si cercano da 0,12 s PRIMA di s a 0,35 s
    dopo, anche 3 dB sotto la mediana (rubberband_1 e i_might_be_late_2 partivano subito dopo il loro colpo: si
    sentiva il colpo tagliato e si andava al colpo dopo). Se un colpo cade gia' a 10-40 ms resta s; se no, tra i colpi
    da -0,12 a +0,04 s vince quello che sale di piu'; solo senza questi, il primo dopo 0,04 s."""
    try:
        w, h = SR // 100, SR // 400                                    # finestre da 10 ms, passo 2,5 ms
        pre = prima + 5 * w / SR                                       # 50 ms in piu': la salita guarda i 30 ms prima
        a = int(round((s - pre) * SR))
        seg = np.asarray(x[max(0, a):a + int((pre + fin) * SR) + w], np.float64)
        n = (len(seg) - w) // h
        if a < 0 or n < 40:
            return s
        e = 10 * np.log10(np.convolve(seg ** 2, np.ones(w) / w, "valid")[::h][:n] + 1e-12)
        t = (np.arange(n) * h + w) / SR - pre                          # fine della finestra, rispetto a s
        cs = np.r_[0, np.cumsum(e)]
        j0 = np.arange(n)
        salita = e - (cs[j0] - cs[np.maximum(j0 - 12, 0)]) / np.maximum(j0 - np.maximum(j0 - 12, 0), 1)
        ok = np.where((t >= -prima) & (t <= fin) & (j0 >= 12) & (salita >= soglia)
                      & (e >= np.median(e) - 3.0))[0]
        if not len(ok):
            return s
        colpi = []                                                     # un colpo per ogni salita (finestre di fila)
        for gruppo in np.split(ok, np.where(np.diff(ok) > 1)[0] + 1):
            j = int(gruppo[int(np.argmax(salita[gruppo]))])
            while j + 1 < n and salita[j + 1] > salita[j]:             # il punto piu' ripido di quella salita
                j += 1
            colpi.append(j)
        if any(0.01 <= t[j] <= 0.04 for j in colpi):
            return s
        presto = [j for j in colpi if t[j] < 0.01]                     # da -0,12 a +0,04 s (10-40 ms gia' esclusi)
        if presto:
            j = max(presto, key=lambda j: salita[j])
        else:
            dopo = [j for j in colpi if t[j] > 0.04]
            if not dopo:
                return s
            j = dopo[0]
        return max(0.0, s + float(t[j]) - 0.03)                         # attacco ~7 ms prima, poi 20 ms di margine
    except Exception:
        return s


def inizi_ritornello(x, pezzi=3, dur=10.5):
    """6/11/2026: fino a `pezzi` inizi (secondi) sull'entrata della parte piu' forte del brano (ritornello / drop),
    distanti almeno un pezzo l'uno dall'altro e con spazio per la versione da 20,5 s. Se i controlli severi non
    bastano, un secondo giro piu' largo; se manca ancora qualcosa, il resto lo mette migliori_inizi (come prima)."""
    durata = len(x) / SR
    c = _mappa(x)
    sc, meglio = _punteggi(c, durata, dur)
    ordine = [int(b) for b in np.argsort(sc)[::-1][:400] if sc[b] > -1e8]
    scelti = []
    for severo in (True, False):
        for b in ordine:
            s = round(_sull_entrata(c, b / 2, x), 2)
            m = misura_pezzo(c, s, dur)
            if s < 4.0 or s + LUNGO + 1.5 > durata or m is None:
                continue
            p1 = c["pot_f"][int(s * FPS):int(s * FPS) + FPS].mean() - c["pot_f"][int(s * FPS):int((s + dur) * FPS)].mean()
            if severo and (p1 < -1.5 or m["primo_s"] < -1.0 or m["dentro"] >= 5 or m["buco"] >= 6
                           or m["forza"] < meglio - 2.0):
                continue
            if not severo and (m["primo_s"] < -2.0 or m["forza"] < meglio - 3.5):
                continue
            if all(abs(s - t) >= dur + 1.5 for t in scelti):
                scelti.append(s)
            if len(scelti) == pezzi:
                return sorted(scelti)
    return sorted(scelti)


def _brani(cartella=None):
    """Brani da lavorare; con cartella, salta quelli che ci hanno gia' tutti i pezzi (6/11/2026: senza decodificarli,
    sul PC carico ogni decodifica durava quasi un minuto)."""
    for p in sorted(glob.glob(os.path.join(pl.ORIG, "*.mp3"))):
        slug = re.sub(r"[^a-z0-9]+", "_", os.path.splitext(os.path.basename(p))[0].lower()).strip("_")
        fatti = cartella and all(os.path.exists(os.path.join(cartella, f"{slug}_{k}.m4a")) for k in range(1, pl.PEZZI + 1))
        if slug not in ESCLUSI and not fatti:
            yield p, slug


def _taglia(p, s, dur, g, out):
    # 6/11/2026 (revisione): sfumata d'ingresso da 10 ms (prima 50 ms): il colpo cade 20-30 ms dopo l'inizio e con
    # 50 ms usciva a meta' volume; 10 ms bastano contro il clic del taglio
    subprocess.run([pl.F, "-y", "-v", "error", "-ss", f"{s:.2f}", "-t", str(dur), "-i", p, "-af",
                    f"volume={g:.2f}dB,afade=t=in:d=0.01,afade=t=out:st={dur - 0.35}:d=0.35",
                    "-ac", "2", "-ar", "44100", "-c:a", "aac", "-b:a", "192k", out], check=True)


def _inizi(x):
    """6/11/2026: inizi sul ritornello (inizi_ritornello), completati da migliori_inizi se ne mancano; se l'analisi
    non riesce, quelli di prima."""
    try:
        s = inizi_ritornello(x, pl.PEZZI, pl.DUR)
        for t in (pl.migliori_inizi(x) if len(s) < pl.PEZZI else []):
            if len(s) < pl.PEZZI and all(abs(t - u) >= pl.DUR + 1.5 for u in s):
                s.append(t)
        return sorted(s) or pl.migliori_inizi(x)
    except Exception as e:
        print("ritornello non trovato, restano gli inizi di prima:", e, flush=True)
        return pl.migliori_inizi(x)


def main():
    pl.DUR, pl.PEZZI = 10.5, 3
    dest = os.path.join(pl.HERE, "musica", "yt_dieci")
    os.makedirs(dest, exist_ok=True)
    fatti = 0
    for p, slug in _brani(dest):
        for k, s in enumerate(_inizi(pl.pcm(p)), 1):
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
            fatti += _lungo(p, x, slug, k, c, dest)
    print(fatti, "pezzi lunghi creati")


def _lungo(p, x, slug, k, c, dest, g=None):
    """La versione da 20,5 s del pezzo corto c (vedi lunghi). 1 se fatta, 0 se no. g: il guadagno del pezzo corto
    (6/11/2026: rifai lo passa, una misura di volume in meno per pezzo sul PC carico; il controllo sotto resta)."""
    import shutil, tempfile
    y = pl.pcm(c)
    s = _inizio(x, y)
    if s + LUNGO > len(x) / 8000 - 1.0:
        print("troppo vicino alla fine, resta corto:", slug, k)
        return 0
    tmp = os.path.join(tempfile.gettempdir(), f"yt_venti_{slug}_{k}.m4a")
    g = pl.guadagno(p, s) if g is None else g
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
    return int(ok)


def rifai(solo=(), tutti=False):
    """6/11/2026 (Alessandro: "la musica deve partire dal momento piu' virale, dal ritornello"): i pezzi gia' fatti
    che col ritornello partono da un altro punto si rifanno con lo stesso nome e lo stesso volume (-14 LUFS), poi la
    loro versione da 20,5 s. Se la versione lunga nuova non e' uguale al pezzo corto, quella vecchia si toglie
    (partirebbe dal punto di prima: musiche_brano la usa per tutti i formati): si sposta in _lavoro/musica_vecchia
    (mai cancellata) e resta anche nella storia di git. solo: i brani da fare (al massimo 6 per volta: il lucchetto del PC si considera dimenticato dopo 20 minuti).
    Revisione 6/11 sera: resta solo chi si sposta meno di 0,02 s (la rifinitura sul colpo vale circa 0,09 s);
    tutti=True (--tutti) rifa' anche quelli, per la sfumata d'ingresso nuova."""
    import shutil, tempfile
    pl.DUR, pl.PEZZI = 10.5, 3
    dieci = os.path.join(pl.HERE, "musica", "yt_dieci")
    venti = os.path.join(pl.HERE, "musica", "yt_venti")
    cambiati = 0
    for p, slug in _brani():
        if solo and slug not in solo:
            continue
        x = pl.pcm(p)
        for k, s in enumerate(_inizi(x), 1):
            out = os.path.join(dieci, f"{slug}_{k}.m4a")
            prima = _inizio(x, pl.pcm(out)) if os.path.exists(out) else None
            if prima is not None and abs(prima - s) < 0.02 and not tutti:
                print(f"{slug}_{k}: resta da {prima:.2f} s", flush=True)
                continue
            tmp = os.path.join(tempfile.gettempdir(), f"yt_dieci_{slug}_{k}.m4a")
            g = pl.guadagno(p, s)
            _taglia(p, s, pl.DUR, g, tmp)
            shutil.move(tmp, out)
            cambiati += 1
            print(f"{slug}_{k}: da {s:.2f} s (prima {prima if prima is None else f'{prima:.2f}'} s)", flush=True)
            lungo = os.path.join(venti, os.path.basename(out))
            os.makedirs(venti, exist_ok=True)
            if not _lungo(p, x, slug, k, out, venti, g) and os.path.exists(lungo):
                # 6/11/2026 (integrazione): mai cancellare: la versione lunga vecchia si sposta fuori da musica/
                print(f"{slug}_{k}: tolta la versione lunga vecchia (partiva da prima), messa in "
                      f"{_metti_da_parte(lungo)}", flush=True)
    print(cambiati, "pezzi rifatti")


def _metti_da_parte(path):
    """6/11/2026 (integrazione): un file tolto da musica/ non si cancella mai: va in _lavoro/musica_vecchia/ (fuori da
    git, vedi .gitignore) con l'ora nel nome e la desinenza .vecchio."""
    import shutil, time
    d = os.path.join(pl.HERE, "_lavoro", "musica_vecchia")
    os.makedirs(d, exist_ok=True)
    dest = os.path.join(d, f"{os.path.basename(path)}.{time.strftime('%Y%m%d_%H%M%S')}.vecchio")
    shutil.move(path, dest)
    return dest


if __name__ == "__main__":
    if sys.argv[1:2] == ["lunghi"]:
        lunghi(set(sys.argv[2:]))
    elif sys.argv[1:2] == ["rifai"]:
        rifai(set(sys.argv[2:]) - {"--tutti"}, "--tutti" in sys.argv[2:])
    else:
        main()
