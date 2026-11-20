"""
TESTO MAI SUL VISO (20/11/2026, Alessandro: "voglio che le scritte non stiano mai sulla mia faccia nei video. Quando il
testo non riesce a stare sullo schermo perche' copre la mia faccia, allora procedere a rimpicciolire il font del copy,
ma mai le scritte sulla mia faccia").

Qui si trovano i visi su TUTTO il pezzo di video che finisce nel reel (un fotogramma ogni PASSO s, gia' nel taglio
9:16 finale), con piu' prudenza di overlay.detect_faces:
- tre classificatori Haar di OpenCV (frontale default e alt2, profilo da tutti e due i lati: gia' dentro OpenCV, nessun
  modello da scaricare), CLAHE sul grigio (visi in ombra o controluce), soglia piu' bassa (VICINI = 4 invece di 6);
- la testa inclinata (+-INCLINAZIONI gradi) e, per la famiglia "dieci", lui sdraiato (+-90 gradi, come detect_faces);
- un riquadro trovato in un solo fotogramma resta solo se ha pelle al centro (un falso viso nel muro si scarta, un viso
  vero che compare per un attimo resta); quelli confermati da un fotogramma vicino restano sempre;
- tra due fotogrammi vicini il viso che si muove copre anche lo spazio in mezzo (riquadro che li contiene tutti e due);
- margine: i riquadri di Haar (fronte-bocca) si allargano del 15% per lato (orecchie), 45% sopra (capelli), 20% sotto
  (mento e barba), piu' MARGINE (12% del viso) tutto intorno.
L'unione di questi riquadri e' la zona dove la frase non va MAI (stile_centro.impagina_senza_visi).

20/11/2026 sera (Alessandro: il reel delle 18:00, lui sdraiato alla pressa con la testa all'indietro, aveva la frase
SULLA faccia: Haar l'aveva visto in 1 fotogramma su 20). Da qui il rilevatore PRINCIPALE e' YuNet (rete neurale di
OpenCV, modello ufficiale opencv_zoo face_detection_yunet_2023mar.onnx, 230 KB, licenza MIT, nella cartella modelli/
del repo; cv2.FaceDetectorYN da OpenCV 4.8): trova anche visi piccoli, scuri, di tre quarti e girati. Si usa su ogni
fotogramma (720 x 1280, uno ogni PASSO = 0,25 s) dritto e ruotato di 90, 180 e 270 gradi (lui sdraiato o a testa in
giu'), i riquadri tornano nel fotogramma dritto. Haar resta come fonte in piu' (unione). Sui clip veri del 20/11:
18:00 (IMG_4118) da 1/20 fotogrammi a 28/28; 14:00 (IMG_4129, lui a pancia in giu') da 0/20 a 28/28.
Margini di YuNet (riquadro gia' dalla fronte al mento): MARGINI_YN, piu' stretti di quelli di Haar (il riquadro e' piu'
preciso), applicati nel verso del viso (i capelli "sopra" la fronte anche quando lui e' sdraiato).
Rete di sicurezza per le pose che nessun rilevatore vede: i visi di TUTTO il pezzo valgono per tutto il pezzo (unione),
e la frase ha comunque SPAZIO_VISO intorno. Niente stima della testa dal corpo (Haar upperbody/fullbody): provato sui
clip di oggi, non vede le persone sdraiate o piegate (le pose che servirebbero) e da dritto copre mezzo schermo, che
toglierebbe il posto alla frase senza proteggere di piu' il viso.
"""
import math, os, subprocess
import cv2
import numpy as np

PASSO = 0.25                 # secondi tra due fotogrammi guardati (7 s -> 28 fotogrammi; 0,35 fino al 20/11 sera)
LATO = (720, 1280)           # fotogrammi nel taglio 9:16 (YuNet ci lavora a questa grandezza: visi da ~15 px; Haar a 480)
VICINI = 4                   # minNeighbors di Haar (detect_faces usa 6: qui conta non perdere un viso)
SCALA = 1.15                 # scaleFactor di Haar (1,1 in detect_faces: qui piu' veloce, i visi da evitare sono grandi)
ALTEZZA_HAAR = 480           # lato lungo del grigio su cui lavora Haar (720 in detect_faces: i visi che contano sono grandi)
INCLINAZIONI = (20, -20)     # testa inclinata (gradi), oltre a 0
MARGINE = 0.12               # margine in piu' tutto intorno al riquadro (frazione della grandezza del viso)
PELLE_MIN = 0.25             # un riquadro visto una volta sola resta solo con almeno il 25% di pelle al centro
_CLAHE = cv2.createCLAHE(2.0, (8, 8))
_CASC = None
# 20/11/2026 sera: YuNet (vedi sopra)
MODELLO_YN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "modelli", "face_detection_yunet_2023mar.onnx")
SOGLIA_YN = 0.5              # punteggio minimo di YuNet: tenuto se confermato (stesso fotogramma o uno vicino)
SOGLIA_YN_SOLO = 0.65        # da qui in su tenuto anche da solo (sui clip veri il viso sta tra 0,5 e 0,9)
DRITTO_FORTE = 0.80          # viso dritto "sicuro" (vedi visi_frames: lui dritto, i visi solo ruotati vanno confermati)
MARGINI_YN = (0.12, 0.30, 0.12, 0.10)    # sinistra, sopra (capelli), destra, sotto (mento/barba): frazioni del viso
_YN = None
_ROTAZIONI = ((None, lambda x0, y0, x1, y1: (x0, y0, x1, y1)),
              (cv2.ROTATE_90_CLOCKWISE, lambda x0, y0, x1, y1: (y0, 1 - x1, y1, 1 - x0)),
              (cv2.ROTATE_180, lambda x0, y0, x1, y1: (1 - x1, 1 - y1, 1 - x0, 1 - y0)),
              (cv2.ROTATE_90_COUNTERCLOCKWISE, lambda x0, y0, x1, y1: (1 - y1, x0, 1 - y0, x1)))


def _yunet():
    """Il rilevatore YuNet (uno solo, ricreato solo la prima volta). Errore se manca il modello o OpenCV < 4.8: chi
    chiama (formati_nuovi._guarda) non mette la frase alla cieca."""
    global _YN
    if _YN is None:
        if not os.path.exists(MODELLO_YN):
            raise FileNotFoundError(f"modello YuNet mancante: {MODELLO_YN}")
        _YN = cv2.FaceDetectorYN.create(MODELLO_YN, "", (320, 320), 0.3, 0.3, 50)
    return _YN


def visi_yunet(img, soglia=SOGLIA_YN):
    """[(riquadro con MARGINI_YN in frazioni del fotogramma dritto, punteggio, rotazione)] di YuNet su img BGR dritto e
    ruotato di 90, 180 e 270 gradi. I margini si mettono nel fotogramma ruotato (dove il viso e' dritto: i capelli
    sopra la fronte), poi il riquadro torna dritto."""
    det = _yunet()
    out = []
    ml, mt, mr, mb = MARGINI_YN
    for k, (rot, ritorna) in enumerate(_ROTAZIONI):
        g = img if rot is None else cv2.rotate(img, rot)
        h, w = g.shape[:2]
        det.setInputSize((w, h))
        _, ff = det.detect(g)
        for r in (ff if ff is not None else []):
            sc = float(r[14])
            if sc < soglia:
                continue
            x, y, fw, fh = (float(v) for v in r[:4])
            b = ((x - fw * ml) / w, (y - fh * mt) / h, (x + fw * (1 + mr)) / w, (y + fh * (1 + mb)) / h)
            out.append((ritorna(*b), sc, k))
    return out


def _cascate():
    global _CASC
    if _CASC is None:
        d = cv2.data.haarcascades
        _CASC = [(cv2.CascadeClassifier(d + "haarcascade_frontalface_default.xml"), False),
                 (cv2.CascadeClassifier(d + "haarcascade_frontalface_alt2.xml"), False),
                 (cv2.CascadeClassifier(d + "haarcascade_profileface.xml"), True)]
    return _CASC


def fotogrammi(src, inizio, durata, passo=PASSO, lato=LATO, ffmpeg=None, timeout=420):
    """Fotogrammi BGR (lato, taglio 9:16 al centro come nel montaggio) da `inizio` per `durata` s, uno ogni `passo` s,
    con UNA lettura di ffmpeg senza file. [] se non si legge."""
    if ffmpeg is None:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    w, h = lato
    fps = 1.0 / max(0.05, float(passo))
    out = b""
    # -skip_frame noref: i fotogrammi che nessun altro usa non si decodificano (4K 60 HEVC: ~40% piu' veloce sul PC); il
    # fotogramma piu' vicino dista al massimo pochi centesimi di secondo, per i visi non cambia niente. Se cosi' non
    # esce niente, la lettura normale
    for salta in (["-skip_frame:v", "noref"], []):
        try:
            r = subprocess.run([ffmpeg, "-v", "error", *salta, "-ss", f"{max(0.0, inizio):.3f}",
                                "-t", f"{max(0.1, durata):.3f}", "-i", src, "-vf",
                                f"fps={fps:.4f}:start_time=0,scale={w}:{h}:force_original_aspect_ratio="
                                f"increase:flags=fast_bilinear,crop={w}:{h}", "-pix_fmt", "bgr24", "-f", "rawvideo", "-"],
                               capture_output=True, timeout=timeout)
            out = r.stdout
        except subprocess.TimeoutExpired:      # troppo lento: niente secondo giro (restano i visi di prima)
            out = b""
            break
        except Exception:
            out = b""
        if len(out) >= w * h * 3:
            break
    n = len(out) // (w * h * 3)
    return [np.frombuffer(out[i * w * h * 3:(i + 1) * w * h * 3], np.uint8).reshape(h, w, 3) for i in range(n)]


def _con_margine(x, y, fw, fh):
    """Riquadro di Haar (frazioni: dalla fronte alla bocca) -> riquadro della testa: capelli (+45% sopra), mento e
    barba (+20% sotto), orecchie (+15% per lato), piu' MARGINE (12% del viso) tutto intorno."""
    mw, mh = fw * MARGINE, fh * MARGINE
    return (x - fw * 0.15 - mw, y - fh * 0.45 - mh, x + fw * 1.15 + mw, y + fh * 1.20 + mh)


def _haar(gray, angolo=0.0, quali=(0, 1, 2)):
    """Riquadri (x, y, w, h in frazioni del grigio non ruotato) dei classificatori `quali` (indici di _cascate), col
    grigio ruotato di `angolo` gradi (il riquadro ruotato torna dritto come rettangolo che lo contiene)."""
    sh, sw = gray.shape
    M = Mi = None
    g = gray
    if angolo:
        M = cv2.getRotationMatrix2D((sw / 2, sh / 2), angolo, 1.0)
        g = cv2.warpAffine(gray, M, (sw, sh), borderMode=cv2.BORDER_REPLICATE)
        Mi = cv2.invertAffineTransform(M)
    mins = int(min(sh, sw) * 0.08)
    out = []
    casc = _cascate()
    for k in quali:
        c, profilo = casc[k]
        for gg, flip in ((g, False), (cv2.flip(g, 1), True)) if profilo else ((g, False),):
            for (x, y, fw, fh) in c.detectMultiScale(gg, SCALA, VICINI, minSize=(mins, mins)):
                x, y, fw, fh = float(x), float(y), float(fw), float(fh)
                if flip:
                    x = sw - x - fw
                if Mi is not None:
                    q = cv2.transform(np.array([[[x, y], [x + fw, y], [x, y + fh], [x + fw, y + fh]]], np.float32),
                                      Mi)[0]
                    x, y = (float(v) for v in q.min(0))
                    fw, fh = (float(v) for v in q.max(0) - q.min(0))
                out.append((x / sw, y / sh, fw / sw, fh / sh))
    return out


def visi_fotogramma(img, ruotati=False, con_tipo=False):
    """Riquadri (x0, y0, x1, y1 in frazioni, CON i margini) dei visi in un fotogramma BGR: frontale default e alt2 e
    profilo (due lati) dritti; alt2 con la testa inclinata di +-20 gradi e con lui sdraiato (+-90).
    con_tipo=True -> [(riquadro, girato)] (girato = trovato sul fotogramma ruotato: chiede piu' prove, vedi visi_frames).
    20/11/2026 sera: anche i visi di YuNet (dritto e ruotato), con girato = ("yn", punteggio, rotazione: 0 dritto,
    1 = 90 gradi orari, 2 = 180, 3 = 90 antiorari)."""
    return _visi_fotogramma(img, ruotati, con_tipo)


def _visi_fotogramma(img, ruotati=False, con_tipo=False, yunet=True):
    h, w = img.shape[:2]
    s = ALTEZZA_HAAR / max(h, w)
    gray = _CLAHE.apply(cv2.cvtColor(cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA),
                                     cv2.COLOR_BGR2GRAY))
    boxes = [(_con_margine(*b), False) for b in _haar(gray, 0.0, (0, 1, 2))]
    for a in INCLINAZIONI:
        boxes += [(_con_margine(*b), True) for b in _haar(gray, a, (1,))]
    if ruotati:      # lui sdraiato (come overlay.detect_faces): il fotogramma girato di 90 gradi
        for rot, ritorna in ((cv2.ROTATE_90_CLOCKWISE, lambda x0, y0, x1, y1: (y0, 1 - x1, y1, 1 - x0)),
                             (cv2.ROTATE_90_COUNTERCLOCKWISE, lambda x0, y0, x1, y1: (1 - y1, x0, 1 - y0, x1))):
            boxes += [(ritorna(*_con_margine(*b)), True) for b in _haar(cv2.rotate(gray, rot), 0.0, (1,))]
    if yunet:
        boxes += [(b, ("yn", round(sc, 3), k)) for b, sc, k in visi_yunet(img)]
    return boxes if con_tipo else [b for b, _ in boxes]


def _pelle(img, b):
    """Quota di pelle (YCrCb) al centro del riquadro b (frazioni con i margini)."""
    h, w = img.shape[:2]
    bw, bh = b[2] - b[0], b[3] - b[1]
    x0, x1 = int(max(0.0, b[0] + bw * 0.3) * w), int(min(1.0, b[2] - bw * 0.3) * w)
    y0, y1 = int(max(0.0, b[1] + bh * 0.35) * h), int(min(1.0, b[3] - bh * 0.35) * h)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    ycc = cv2.cvtColor(img[y0:y1, x0:x1], cv2.COLOR_BGR2YCrCb)
    m = ((ycc[..., 0] > 30) & (ycc[..., 1] >= 133) & (ycc[..., 1] <= 180) & (ycc[..., 2] >= 77) & (ycc[..., 2] <= 135))
    return float(m.mean())


def _vicini(a, b):
    """Due riquadri dello stesso viso: centri vicini (meno di meta' della grandezza del piu' grande) e grandezze simili
    (lati al massimo il doppio)."""
    wa, ha, wb, hb = a[2] - a[0], a[3] - a[1], b[2] - b[0], b[3] - b[1]
    return (abs((a[0] + a[2]) - (b[0] + b[2])) / 2 < 0.5 * max(wa, wb)
            and abs((a[1] + a[3]) - (b[1] + b[3])) / 2 < 0.5 * max(ha, hb)
            and max(wa, wb) <= 2.0 * min(wa, wb) and max(ha, hb) <= 2.0 * min(ha, hb))


def _taglia(b):
    return (max(0.0, b[0]), max(0.0, b[1]), min(1.0, b[2]), min(1.0, b[3]))


def visi_frames(frames, ruotati=False):
    """-> (riquadri della zona vietata, dati). Riquadri: unione (come lista) dei visi di tutti i fotogrammi, filtrati
    e con lo spazio tra due fotogrammi vicini; dati: {"fotogrammi", "con_viso", "riquadri", "scartati"}."""
    per = [visi_fotogramma(f, ruotati, con_tipo=True) for f in frames]
    visi_frames.ultimi = per
    tenuti, scartati = [], 0
    yn = set()
    # 20/11/2026 sera (prova sul selfie allo specchio delle 20:00, lui a torso nudo): sul fotogramma ruotato YuNet vede
    # a volte un "viso" nel petto (punteggio fino a 0,76). Se lui e' DRITTO (viso dritto di YuNet sicuro, almeno
    # DRITTO_FORTE, in almeno meta' dei fotogrammi), un viso trovato solo ruotato (o solo da Haar, che sullo stesso
    # selfie vedeva "visi" nel collo e nel petto e coi suoi margini larghi copriva mezzo schermo: frase al 48%) resta
    # solo se il suo centro cade in un viso dritto sicuro dello stesso fotogramma o di uno vicino (lo stesso viso visto
    # in un altro verso o da un altro rilevatore). Se lui e' sdraiato o girato (18:00, 14:00) i visi dritti sicuri non
    # ci sono e restano tutti (YuNet ruotato e Haar coi loro filtri)
    forti = [[b for b, t in bs if isinstance(t, tuple) and t[2] == 0 and t[1] >= DRITTO_FORTE] for bs in per]
    if per and sum(1 for x in forti if x) * 2 >= len(per):
        def _dentro(b, c):
            cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
            return c[0] <= cx <= c[2] and c[1] <= cy <= c[3]
        for i, bs in enumerate(per):
            vf = [c for j in range(max(0, i - 2), min(len(per), i + 3)) for c in forti[j]]
            if not vf:       # qui (e vicino) nessun viso dritto sicuro: lui si e' girato, restano tutti
                continue
            area = max((c[2] - c[0]) * (c[3] - c[1]) for c in vf)
            via = [(b, t) for b, t in bs
                   if not (isinstance(t, tuple) and t[2] == 0 and t[1] >= DRITTO_FORTE)
                   and not any(_dentro(b, c) for c in vf)
                   # un altro viso dritto (un'altra persona) resta se e' grande al massimo 1,5 volte il suo; il "viso"
                   # dritto debole grande come il torso (0,5 sul selfie delle 20:00) no
                   and not (isinstance(t, tuple) and t[2] == 0 and (b[2] - b[0]) * (b[3] - b[1]) <= 1.5 * area)]
            scartati += len(via)
            per[i] = [x for x in bs if x not in via]
    for i, (f, bs) in enumerate(zip(frames, per)):
        for b, girato in bs:
            # confermato: un riquadro quasi uguale nello stesso fotogramma (un altro classificatore) o in uno vicino
            conferma = any(_vicini(b, c) for j in range(max(0, i - 2), min(len(per), i + 3))
                           for k, (c, _) in enumerate(per[j]) if (j, k) != (i, bs.index((b, girato))))
            if isinstance(girato, tuple):
                # 20/11/2026 sera: YuNet sbaglia molto meno di Haar e vede anche i visi scuri (niente prova della
                # pelle): sopra SOGLIA_YN_SOLO resta da solo, tra SOGLIA_YN e SOGLIA_YN_SOLO con una conferma
                if girato[1] >= SOGLIA_YN_SOLO or conferma:
                    tenuti.append((i, b))
                    yn.add(i)
                else:
                    scartati += 1
                continue
            pelle = _pelle(f, b)
            # dritto: confermato oppure con pelle; trovato sul fotogramma ruotato (testa inclinata, sdraiato), dove Haar
            # vede piu' facilmente visi nei disegni e nei piatti: confermato E con pelle
            if (conferma and pelle >= PELLE_MIN) if girato else (conferma or pelle >= PELLE_MIN):
                tenuti.append((i, b))
            else:
                scartati += 1
    zona = [_taglia(b) for _, b in tenuti]
    # il viso che si muove tra due fotogrammi guardati: anche il rettangolo che contiene i due riquadri
    for (i, a) in tenuti:
        for (j, b) in tenuti:
            if j == i + 1 and _vicini(a, b):
                zona.append(_taglia((min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))))
    zona = unisci(zona)
    return zona, {"fotogrammi": len(frames), "con_viso": len({i for i, _ in tenuti}), "con_viso_yunet": len(yn),
                  "riquadri": len(zona), "scartati": scartati, "rilevatore": "yunet+haar"}


def unisci(boxes):
    """Toglie i riquadri contenuti in un altro (l'unione resta la stessa, meno conti dopo)."""
    boxes = sorted(set(tuple(round(float(v), 4) for v in b) for b in boxes),
                   key=lambda b: -(b[2] - b[0]) * (b[3] - b[1]))
    out = []
    for b in boxes:
        if not any(o[0] <= b[0] and o[1] <= b[1] and o[2] >= b[2] and o[3] >= b[3] for o in out):
            out.append(b)
    return out


def visi_pezzo(src, inizio, durata, ruotati=False, passo=PASSO, ffmpeg=None):
    """Zona dei visi (vedi visi_frames) di tutto il pezzo src[inizio, inizio + durata], piu' i fotogrammi letti."""
    fr = fotogrammi(src, inizio, durata, passo, ffmpeg=ffmpeg)
    zona, dati = visi_frames(fr, ruotati)
    return zona, dati, fr


def lettere_sul_viso(img, visi, soglia=200):
    """True se una lettera della scritta (pixel con alfa >= soglia: il bianco pieno, non l'ombra ne' l'alone, che insieme arrivano a ~140) cade in
    un riquadro dei visi. img: immagine RGBA PIL W x H (la scritta), visi: riquadri in frazioni."""
    if not visi:
        return False
    a = np.asarray(img.getchannel("A"))
    H, W = a.shape
    for b in visi:
        x0, y0 = int(max(0.0, b[0]) * W), int(max(0.0, b[1]) * H)
        x1, y1 = int(math.ceil(min(1.0, b[2]) * W)), int(math.ceil(min(1.0, b[3]) * H))
        if x1 > x0 and y1 > y0 and (a[y0:y1, x0:x1] >= soglia).any():
            return True
    return False
