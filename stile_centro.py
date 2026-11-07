"""
STILE "TESTO AL CENTRO" (7/11/2026, Alessandro: "testo al centro del video anche se copre il viso, deve essere sempre
li'", "copia esattamente lo stile di questo screenshot", "cio' che fa andare virale il video sono i testi").
Come i suoi 5 esempi: la frase BIANCA in un serif da libro (Source Serif Pro, licenza OFL, nel repo in font/; il
Semibold per le frasi lunghe, come il suo esempio 2), centrata in orizzontale e in verticale (centro del blocco al 47%
dell'altezza), senza riquadro ne' contorno, solo un'ombra morbida quasi invisibile; ferma dal primo all'ultimo
fotogramma; grandezza in base alla lunghezza della frase (7% della larghezza per 1-5 parole, 5,5% per le frasi medie,
fino al 3,8% per quelle da ~45 parole; sempre intera e dentro la zona sicura, anche a ~70 parole); righe equilibrate
(mai una parola sola nell'ultima riga, mai una riga che finisce con un articolo o una preposizione se si puo'
evitare); una lista di frasi brevi va una frase per riga (esempi 3 e 5). La frase non si cambia mai (solo l'apostrofo
tipografico e i simboli che il carattere non sa disegnare, come le emoji).
Il video sotto la frase, se e' troppo chiaro, diventa piu' scuro fino a obiettivi misurati (zona della frase <= 0,20,
fotogramma <= 0,26): come un'esposizione piu' bassa (niente neri schiacciati, niente dominanti), piu' un'ombra rotonda
morbidissima dietro la frase; mai piu' chiaro.
Non importa overlay (overlay importa questo modulo): si puo' provare da solo.
"""
import os, re
from PIL import Image, ImageDraw, ImageFilter, ImageFont

_DIR = os.path.dirname(os.path.abspath(__file__))
NOME_STILE = "centro_serif"          # montaggio.scritta in stato.json dal 7/11/2026
# il carattere: Source Serif Pro (Adobe, OFL 1.1, file in font/ con la licenza); se manca, altri serif liberi
FONT_CENTRO = [os.path.join(_DIR, "font", "SourceSerifPro-Regular.ttf"),
               r"C:\Windows\Fonts\SourceSerifPro-Regular.ttf",
               "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
               "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf"]
# frasi lunghe (corpo sotto PIENO_SOTTO): lo stesso carattere un po' piu' pieno (Semibold), come l'esempio 2 di
# Alessandro (frase lunga, serif piu' pesante): sul telefono le lettere piccole restano leggibili sopra le scene piene
FONT_PIENO = [os.path.join(_DIR, "font", "SourceSerifPro-Semibold.ttf"),
              r"C:\Windows\Fonts\SourceSerifPro-Semibold.ttf"]
PIENO_SOTTO = 0.044
BIANCO = (255, 255, 255, 255)
CENTRO_Y = 0.47                      # centro del blocco di testo (frazione dell'altezza)
COLONNA = 0.72                       # larghezza massima delle righe (frazione della larghezza, centrata: 14%-86%)
CORPO_MAX, CORPO_MIN = 0.055, 0.038  # grandezza del carattere (frazione della larghezza): frasi medie / ~45 parole
CORPO_FONDO = 0.032                  # solo se a 3,8% la frase non sta nel 45% dell'altezza (frasi oltre le 45 parole)
LUNGA_DA, LUNGA_A = 60, 260          # caratteri: a 60 il 5,5%, da 260 (~45 parole) il minimo
# 7/11/2026 (Alessandro, 02:26: le frasi dei suoi screenshot escono "cosi' come sono", da 1-5 parole a ~70): le frasi
# cortissime grandi come il suo esempio 5 (~7% della larghezza), non una rigetta piccola; le liste brevi piu' grandi
CORPO_CORTA, CORTA_FINO = 0.070, 28  # fino a 28 caratteri il 7%, poi giu' fino al 5,5% a LUNGA_DA caratteri
CORPO_LISTA = (0.065, 6, 0.056)      # lista: 6,5% fino a 6 righe, 5,6% oltre (poi piu' piccolo se non entra)
CORPO_ULTIMO = 0.015                 # mai sotto: una frase lunghissima (o una parola enorme) resta intera e dentro
ALTEZZA_MAX = 0.45                   # il blocco resta dentro il 45% dell'altezza
ZONA_SICURA = (0.10, 0.80)           # sopra: nome utente e schede; sotto: didascalia e pulsanti (icone a destra: 88%+)
INTERLINEA = 1.10                    # distanza tra le linee di base, in em
LISTA_RIGA = 28                      # lista: ogni frase al massimo 28 caratteri -> una frase per riga
LISTA_MIN = 3                        # ...e almeno 3 frasi
OMBRA = (0.03, 0.10, 0.38)           # ombra morbida: spostamento in basso (em), sfocatura (em), opacita' (0-1)
ALONE = (0.45, 0.28)                 # alone larghissimo e leggero sotto le lettere: sfocatura (em), opacita'
                                     # (sui video chiari e pieni di dettagli la frase si legge, nessun riquadro)
# penalita' dell'a capo (stessa scala della differenza di larghezza tra le righe, al quadrato)
P_DEBOLE, P_ORFANA, P_SOLA, P_CORTA, P_RIGA_IN_PIU = 0.6, 1.0, 0.35, 0.2, 0.3
B_FRASE, B_VIRGOLA = 0.15, 0.05      # bonus: a capo dopo la fine di una frase / dopo una virgola
B_PRIMA = 0.10                       # bonus: la riga dopo comincia con "perche'", "che", "e", "ma"...
RIDUCI = (0.94, 0.88)                # corpi un po' piu' piccoli provati per un a capo migliore
COSTO_CORPO = 0.02                   # costo di ogni 1% di corpo in meno (6% = 0,12: meno di un a capo brutto, 0,6)
PRIMA_DI = set("perché che e ed ma se quando come dove mentre finché anche però quindi perciò poi oppure per "
               "because and but when".split())
# parole con cui una riga non dovrebbe finire (vanno con la parola dopo)
DEBOLI = set("il lo la i gli le un uno una di a da in con su per tra fra e ed o od ma che se non ne mi ti si ci vi "
             "del dello della dei degli delle al allo alla ai agli alle dal dallo dalla dai dagli dalle nel nello "
             "nella nei negli nelle sul sullo sulla sui sugli sulle col coi mio mia miei mie tuo tua tuoi tue suo sua "
             "suoi sue nostro nostra nostri nostre vostro vostra vostri vostre come quando dove perché chi "
             "più meno molto tanto troppo ogni questo questa questi queste quel quella quei quelle "
             "the a an of to in on for and or but with my your".split())
_FINE_FRASE = re.compile(r"[.!?…]['’\"”»)]*$")
_FINE_PEZZO = re.compile(r"[,;:—–]['’\"”»)]*$")
ULTIMO = {}                          # l'ultima scritta: font, corpo (px), righe (per montaggio.stile_centro)


# ------------------------------------------------------------------ carattere
_CACHE = {}


def percorso_font(pieno=False):
    """Il file del carattere: il Semibold per le frasi lunghe (se c'e'), se no il normale."""
    return next((f for f in (FONT_PIENO if pieno else []) + FONT_CENTRO if os.path.exists(f)), None)


def nome_font(p=None):
    p = p or percorso_font() or ""
    return {"SourceSerifPro-Regular.ttf": "Source Serif Pro",
            "SourceSerifPro-Semibold.ttf": "Source Serif Pro Semibold"}.get(os.path.basename(p),
                                                                            os.path.splitext(os.path.basename(p))[0])


def _font(px, pieno=False):
    p = percorso_font(pieno)
    if not p:
        raise RuntimeError("nessun carattere serif disponibile")
    k = (p, int(px))
    if k not in _CACHE:
        _CACHE[k] = ImageFont.truetype(p, int(px))
        _CACHE[k].percorso = p
    return _CACHE[k]


def _manca(font, ch):
    """True se il carattere non ha il glifo (si vedrebbe un quadratino): stesso disegno del glifo 'mancante'."""
    try:
        a, b = font.getmask(ch), font.getmask("\U0010FFFD")
        return a.size == b.size and Image.Image()._new(a).tobytes() == Image.Image()._new(b).tobytes()
    except Exception:
        return False


def pulisci(testo, font=None):
    """La frase com'e' scritta (punteggiatura e maiuscole sue), con l'apostrofo tipografico dopo una lettera
    (l'onore -> l’onore, po' -> po’: nel serif l'apostrofo dritto sembra una macchina da scrivere), spazi in ordine,
    senza i simboli che il carattere non ha (emoji)."""
    t = str(testo or "").replace("\r", "")
    t = re.sub(r"(?<=\w)'", "’", t)
    t = "\n".join(re.sub(r"[ \t]+", " ", r).strip() for r in t.split("\n"))
    t = re.sub(r"\n{2,}", "\n", t).strip()
    if font is not None:
        strani = {c for c in t if ord(c) > 127 and not c.isspace() and _manca(font, c)}
        if strani:
            t = "\n".join(re.sub(r" {2,}", " ", "".join(c for c in r if c not in strani)).strip()
                          for r in t.split("\n"))
    return t


# ------------------------------------------------------------------ a capo
def _frasi(testo):
    """Le frasi (fine con . ! ? …) e le righe gia' andate a capo nel testo."""
    out = []
    for r in testo.split("\n"):
        out += [p.strip() for p in re.split(r"(?<=[.!?…])\s+", r) if p.strip()]
    return out


def e_lista(testo):
    """True se la frase e' una lista di frasi brevi (almeno 3, ognuna al massimo LISTA_RIGA caratteri): allora una
    frase per riga, come gli esempi 3 ("Niente drammi. / Pensa a te stesso. / ...") e 5."""
    f = _frasi(testo)
    return len(f) >= LISTA_MIN and all(len(x) <= LISTA_RIGA for x in f)


def _parola(w):
    return re.sub(r"^\W+|\W+$", "", w.lower().replace("’", "'"))


def _orfane(righe):
    return sum(1 for r in righe if len(r.split()) == 1)


def righe_equilibrate(testo, larghezza, max_px, righe_in_piu=2):
    """Le righe della frase (vedi righe_e_costo)."""
    return righe_e_costo(testo, larghezza, max_px, righe_in_piu)[1]


def righe_e_costo(testo, larghezza, max_px, righe_in_piu=2):
    """(costo, righe) della frase (vedi _dp). Se la frase ha piu' frasi, si prova anche con ogni frase a capo (si legge
    come la si dice: "Non posso arrendermi. / Mamma e papa'..."): vince se costa al massimo una riga in piu' e non
    lascia piu' parole sole."""
    a = _dp(testo, larghezza, max_px, righe_in_piu)
    pezzi = _frasi(testo)
    if len(pezzi) < 2:
        return a
    b = _dp("\n".join(pezzi), larghezza, max_px, righe_in_piu)
    return b if len(b[1]) <= len(a[1]) + 1 and _orfane(b[1]) <= _orfane(a[1]) else a


def _dp(testo, larghezza, max_px, righe_in_piu=2):
    """Righe con larghezze il piu' possibile uguali dentro max_px (larghezza(stringa) -> pixel). Programmazione
    dinamica sulle parole: costo = differenze di larghezza al quadrato + penalita' (riga che finisce con un articolo o
    una preposizione, ultima riga con una parola sola, riga di una parola, ultima riga cortissima, riga in piu') - bonus
    (a capo dopo la fine di una frase o una virgola, o prima di "perche'", "che", "e"...). Gli a capo del testo
    restano. Si prova con il numero minimo di righe e con 1-2 righe in piu'."""
    parole, forzato = [], []
    for r in testo.split("\n"):
        ws = r.split()
        if ws:
            parole += ws
            forzato += [False] * (len(ws) - 1) + [True]
    N = len(parole)
    if N == 0:
        return 0.0, []
    L = {}

    def w(i, j):                     # larghezza delle parole i..j-1 su una riga
        if (i, j) not in L:
            L[(i, j)] = larghezza(" ".join(parole[i:j]))
        return L[(i, j)]
    # righe minime: riempimento semplice (rispettando gli a capo del testo)
    minimo, i = 0, 0
    while i < N:
        j = i + 1
        while j < N and not forzato[j - 1] and w(i, j + 1) <= max_px:
            j += 1
        minimo, i = minimo + 1, j
    totale = sum(w(i, i + 1) for i in range(N)) + larghezza(" ") * (N - 1)
    migliore = None
    for n in range(minimo, min(N, minimo + righe_in_piu) + 1):
        T = max(1.0, min(max_px, totale / n))
        INF = float("inf")
        best = [[INF] * (N + 1) for _ in range(n + 1)]
        da = [[-1] * (N + 1) for _ in range(n + 1)]
        best[0][0] = 0.0
        for k in range(1, n + 1):
            for j in range(1, N + 1):
                ultima = j == N
                for i in range(j - 1, -1, -1):
                    if i < j - 1 and forzato[i]:                       # una riga non scavalca un a capo del testo
                        break
                    if best[k - 1][i] == INF:
                        continue
                    lw = w(i, j)
                    if lw > max_px and j - i > 1:
                        break                                          # piu' lunga: lo sara' anche andando indietro
                    c = ((T - lw) / T) ** 2 if not ultima or lw > T else 0.5 * ((T - lw) / T) ** 2
                    if lw > max_px:                                    # una parola sola piu' larga della colonna
                        c += 2.0
                    if not ultima:
                        if forzato[j - 1]:
                            pass
                        elif _FINE_FRASE.search(parole[j - 1]):
                            c -= B_FRASE
                        elif _FINE_PEZZO.search(parole[j - 1]):
                            c -= B_VIRGOLA
                        elif _parola(parole[j - 1]) in DEBOLI or parole[j - 1].endswith("’"):
                            c += P_DEBOLE
                        elif _parola(parole[j]) in PRIMA_DI:
                            c -= B_PRIMA
                    if j - i == 1 and n > 1:
                        if ultima:
                            c += P_ORFANA if not forzato[j - 2] else P_SOLA
                        elif not _FINE_FRASE.search(parole[j - 1]):
                            c += P_SOLA
                    if ultima and n > 1 and lw < 0.35 * T:
                        c += P_CORTA
                    if best[k - 1][i] + c < best[k][j]:
                        best[k][j], da[k][j] = best[k - 1][i] + c, i
        if best[n][N] == INF:
            continue
        costo = best[n][N] + P_RIGA_IN_PIU * (n - minimo)
        if migliore is None or costo < migliore[0] - 1e-9:
            tagli, j = [], N
            for k in range(n, 0, -1):
                i = da[k][j]
                tagli.append((i, j))
                j = i
            migliore = (costo, [" ".join(parole[i:j]) for i, j in reversed(tagli)])
    return migliore if migliore else (9.0, [" ".join(parole)])


# ------------------------------------------------------------------ impaginazione e disegno
def corpo_per(testo):
    """Grandezza del carattere (frazione della larghezza) in base alla lunghezza della frase."""
    n = len(testo)
    if n <= CORTA_FINO:
        return CORPO_CORTA
    if n <= LUNGA_DA:
        return CORPO_CORTA - (CORPO_CORTA - CORPO_MAX) * (n - CORTA_FINO) / (LUNGA_DA - CORTA_FINO)
    if n >= LUNGA_A:
        return CORPO_MIN
    return CORPO_MAX - (CORPO_MAX - CORPO_MIN) * (n - LUNGA_DA) / (LUNGA_A - LUNGA_DA)


def impagina(W, H, testo):
    """Corpo, righe e posizione della frase per un fotogramma W x H. -> dict (font, corpo, righe, lh, base0...)."""
    font = _font(max(8, int(round(W * CORPO_MAX))))
    testo = pulisci(testo, font)
    if not testo:
        raise ValueError("frase vuota")
    lista = e_lista(testo)
    max_px = W * COLONNA
    corpo = (CORPO_LISTA[0] if len(_frasi(testo)) <= CORPO_LISTA[1] else CORPO_LISTA[2]) if lista else corpo_per(testo)
    sicura = H * (ZONA_SICURA[1] - ZONA_SICURA[0])
    while True:
        px = max(8, int(round(W * corpo)))
        font = _font(px, corpo < PIENO_SOTTO)
        lun = font.getlength
        if lista:
            righe = _frasi(testo)
            if max(lun(r) for r in righe) > max_px:      # una frase non entra nella colonna: piu' piccolo fino al
                if corpo > CORPO_MIN + 1e-9:             # minimo, poi a capo normale
                    corpo = max(CORPO_MIN, corpo * 0.95)
                else:
                    lista, corpo = False, corpo_per(testo)
                continue
        else:
            # anche un corpo un filo piu' piccolo (mai sotto CORPO_MIN) se toglie un a capo brutto (riga che finisce
            # con "la", "che"...) o una riga di troppo: vince il costo dell'a capo + COSTO_CORPO per 1% di corpo in meno
            prove = []
            for k in [k for k in (1.0,) + RIDUCI if corpo * k >= min(corpo, CORPO_MIN) - 1e-9]:
                pk = max(8, int(round(W * corpo * k)))
                fk = _font(pk, corpo * k < PIENO_SOTTO)
                c, rr = righe_e_costo(testo, fk.getlength, max_px)
                prove.append((c + COSTO_CORPO * (1 - k) * 100, -k, pk, fk, rr))
            _, meno_k, px, font, righe = min(prove, key=lambda x: (x[0], x[1]))   # a parita' il corpo piu' grande
            corpo, lun = corpo * -meno_k, font.getlength
        lh = px * INTERLINEA
        _, cima, _, _ = font.getbbox("H", anchor="ls")             # cima delle maiuscole (dalla linea di base, < 0)
        _, _, _, fondo = font.getbbox("gjpqy", anchor="ls")         # fondo delle discendenti (> 0)
        alto = -cima + (len(righe) - 1) * lh + 0.25 * fondo         # blocco: dalle maiuscole all'ultima base (+ un po')
        larga = max(lun(r) for r in righe)
        # 7/11/2026: la frase resta sempre intera e dentro la zona sicura: sotto CORPO_FONDO solo se non ci starebbe
        # (oltre le ~70 parole o una parola piu' larga della colonna), mai sotto CORPO_ULTIMO
        troppo = alto > sicura or larga > max_px + 1
        if corpo <= CORPO_ULTIMO + 1e-9 or (not troppo and (alto <= H * ALTEZZA_MAX or corpo <= CORPO_FONDO + 1e-9)):
            break
        corpo = max(CORPO_ULTIMO if troppo else CORPO_FONDO, corpo * 0.95)
    top = H * CENTRO_Y - alto / 2
    top = min(max(top, H * ZONA_SICURA[0]), H * ZONA_SICURA[1] - alto)
    return {"font": font, "corpo": px, "righe": righe, "lh": lh, "base0": top - cima, "top": top, "alto": alto,
            "larga": larga, "lista": lista, "testo": testo}


def disegna(W, H, imp):
    """Immagine trasparente W x H con la frase: bianco, centrato riga per riga, ombra morbida leggerissima."""
    font, righe, lh, base0 = imp["font"], imp["righe"], imp["lh"], imp["base0"]
    px = imp["corpo"]
    mask = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(mask)
    for i, r in enumerate(righe):
        d.text((W / 2, base0 + i * lh), r, font=font, fill=255, anchor="ms")
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    box = mask.getbbox()
    strati = ([(0.0,) + tuple(ALONE)] if ALONE and ALONE[1] > 0 else []) + ([OMBRA] if OMBRA and OMBRA[2] > 0 else [])
    for dy, sf, a in strati if box else []:                         # prima l'alone largo, poi l'ombra stretta
        m = int(px * (sf * 3 + dy) + 4)                             # margine per la sfocatura
        x0, y0, x1, y1 = max(0, box[0] - m), max(0, box[1] - m), min(W, box[2] + m), min(H, box[3] + m)
        pezzo = Image.new("L", (x1 - x0, y1 - y0), 0)
        pezzo.paste(mask.crop((x0, y0, x1, y1 - int(px * dy))), (0, int(px * dy)))
        pezzo = pezzo.filter(ImageFilter.GaussianBlur(px * sf)).point(lambda v, a=a: int(v * a))
        ombra = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
        ombra.putalpha(pezzo)
        img.alpha_composite(ombra, (x0, y0))
    bianco = Image.new("RGBA", (W, H), BIANCO[:3] + (0,))
    bianco.putalpha(mask)
    img.alpha_composite(bianco)
    return img


def scritta(W, H, testo):
    """La frase nello stile al centro. Stessa forma di overlay.build_testo_giallo: (immagine, y in frazione, punti)."""
    imp = impagina(W, H, testo)
    img = disegna(W, H, imp)
    ULTIMO.clear()
    ULTIMO.update(font=nome_font(getattr(imp["font"], "percorso", None)), corpo=int(imp["corpo"]),
                  righe=len(imp["righe"]), lista=bool(imp["lista"]))
    return img, imp["top"] / H, 0.0


def dati(scurito=0.0, luce=None, sfuma=0.0):
    """montaggio.stile_centro: carattere, corpo in px, righe, quanto e' stato scurito il video (0 = per niente), luce
    misurata prima nella zona della frase, opacita' dell'ombra dietro la frase (0 = niente)."""
    d = {k: ULTIMO[k] for k in ("font", "corpo", "righe") if k in ULTIMO}
    d["scurito"] = round(float(scurito or 0.0), 2)
    if luce is not None:
        d["luce"] = round(float(luce), 2)
    d["sfumatura"] = round(float(sfuma or 0.0), 2)
    return d


# ------------------------------------------------------------------ video piu' scuro sotto la frase
# 7/11/2026 (Alessandro: "tutto scuro ... colore bianco sopra", "se il video e' troppo luminoso scuriscilo un po'";
# coordinatore alle 07:30: le prime anteprime erano ancora troppo chiare, soffitto dell'auto grigio chiaro dietro la
# frase, la clip chiara all'aperto solo da 1,00 a 0,54). Obiettivi misurati: luce media (0-1) della zona della frase al
# massimo OBIETTIVO_TESTO, di tutto il fotogramma al massimo OBIETTIVO_TUTTO. Due mezzi, tutti e due come
# un'esposizione piu' bassa (R, G e B moltiplicati per lo stesso numero: il nero resta nero, niente dominanti, MAI piu'
# chiaro): (1) ogni scena piu' scura per intero (fattore -> filtro lutyuv, costa pochissimo); (2) un'ombra rotonda,
# grandissima e morbidissima dietro la frase (una gaussiana: nessun bordo, nessun riquadro), dentro l'immagine della
# scritta, quindi nel montaggio non costa niente. Le scene gia' scure (le sue nuove a luce bassa, le foto col filtro
# drammatico) restano come sono.
OBIETTIVO_TESTO, OBIETTIVO_TUTTO = 0.20, 0.26   # un filo sotto 0,22 / 0,28: la misura e' su pochi fotogrammi
# le luci alte (il 10% piu' chiaro del fotogramma: pareti gialle, finestre, cielo) al massimo OBIETTIVO_ALTE, solo se la
# scena va scurita comunque: sulle foto "virali" molto contrastate la media era giusta ma il fotogramma restava chiaro
OBIETTIVO_ALTE = 0.40
SFUMATURA_MAX = 0.45                 # opacita' dell'ombra al centro al massimo (0,45: il centro al 55% della luce)
SFUMA_SX, SFUMA_SY = 0.40, 0.20      # ampiezza dell'ombra (sigma): 40% della larghezza, 20% dell'altezza
FATTORE_MIN = 0.36                   # una scena non scende mai sotto il 36% (una clip bianchissima non diventa nera)
ZONA_LUCE = (0.14, 0.24, 0.86, 0.70)  # dove si misura: la zona della frase (x0, y0, x1, y1 in frazioni)


def _misura(p, zona, bgr):
    """(luce della zona, luce di tutto, luci alte = 90o percentile) di un'immagine 160x90x3 float (luma Rec.709)."""
    import numpy as np
    b, g, r = (0, 1, 2) if bgr else (2, 1, 0)
    y = (0.0722 * p[..., b] + 0.7152 * p[..., g] + 0.2126 * p[..., r]) / 255
    x0, y0, x1, y1 = int(zona[0] * 90), int(zona[1] * 160), int(zona[2] * 90), int(zona[3] * 160)
    return float(y[y0:y1, x0:x1].mean()), float(y.mean()), float(np.percentile(y, 90))


def misura(frames, zona=ZONA_LUCE):
    """(luce media della zona della frase, luce media di tutto il fotogramma, luci alte), 0-1, dei fotogrammi BGR
    (numpy, gia' nel taglio 9:16). (None, None, None) se non si misura."""
    import numpy as np
    vals = []
    for f in frames or []:
        try:
            import cv2
            p = cv2.resize(f, (90, 160), interpolation=cv2.INTER_AREA).astype(np.float32)
        except Exception:
            p = np.asarray(Image.fromarray(f[..., ::-1]).resize((90, 160))).astype(np.float32)[..., ::-1]
        vals.append(_misura(p, zona, True))
    if not vals:
        return None, None, None
    return tuple(float(np.mean([v[k] for v in vals])) for k in range(3))


def luce_centro(frames, zona=ZONA_LUCE):
    """Luce media (0-1) nella zona della frase dei fotogrammi (vedi misura). None se non si misura."""
    return misura(frames, zona)[0]


def misura_immagine(img, zona=ZONA_LUCE):
    """Come misura per un'immagine PIL (foto gia' nel taglio 9:16)."""
    import numpy as np
    return _misura(np.asarray(img.convert("RGB").resize((90, 160))).astype(np.float32), zona, False)


def luce_immagine(img, zona=ZONA_LUCE):
    return misura_immagine(img, zona)[0]


def _profilo(W, H):
    """L'ombra dietro la frase a opacita' 1 (W x H, 0-1): gaussiana centrata sulla frase, separabile (veloce a 4K)."""
    import numpy as np
    x = (np.arange(W, dtype=np.float32) + 0.5) / W - 0.5
    y = (np.arange(H, dtype=np.float32) + 0.5) / H - CENTRO_Y
    return np.exp(-0.5 * (y / SFUMA_SY) ** 2)[:, None] * np.exp(-0.5 * (x / SFUMA_SX) ** 2)[None, :]


_PESI = []


def pesi():
    """Quanto copre in media l'ombra (a opacita' 1) la zona della frase e tutto il fotogramma."""
    if not _PESI:
        p = _profilo(90, 160)
        x0, y0, x1, y1 = (int(ZONA_LUCE[0] * 90), int(ZONA_LUCE[1] * 160), int(ZONA_LUCE[2] * 90),
                          int(ZONA_LUCE[3] * 160))
        _PESI.extend([float(p[y0:y1, x0:x1].mean()), float(p.mean())])
    return _PESI


def sfumatura_per(luci):
    """Opacita' al centro dell'ombra dietro la frase per tutto il video (0 = niente), dalla scena piu' chiara nella zona
    della frase: le scene gia' scure (luce <= OBIETTIVO_TESTO) non la hanno."""
    l = max([float(x) for x in luci or [] if x is not None] or [0.0])
    if l <= OBIETTIVO_TESTO + 0.01:
        return 0.0
    return round(min(SFUMATURA_MAX, 0.6 * (1 - OBIETTIVO_TESTO / l)), 3)


def fattore(luce, tutto=None, sfuma=0.0, alte=None):
    """Fattore dell'esposizione della scena (1 = com'e', mai sopra 1): la zona della frase scende a OBIETTIVO_TESTO e
    tutto il fotogramma a OBIETTIVO_TUTTO, contando anche l'ombra dietro la frase (sfuma); se la scena va scurita, anche
    le luci alte fino a OBIETTIVO_ALTE (una scena gia' scura resta com'e'); mai sotto FATTORE_MIN."""
    m = 1.0
    zona, intero = pesi() if sfuma else (0.0, 0.0)
    if luce:
        m = min(m, OBIETTIVO_TESTO / (float(luce) * (1 - sfuma * zona)))
    if tutto:
        m = min(m, OBIETTIVO_TUTTO / (float(tutto) * (1 - sfuma * intero)))
    if alte and m < 0.995 and OBIETTIVO_ALTE / float(alte) < m:
        # per gradi: piena quando la scena va scurita di almeno il 35%, cosi' una scena appena sopra gli obiettivi
        # (stanza scura con una finestra) non salta di colpo a meta' luce
        m -= (m - OBIETTIVO_ALTE / float(alte)) * min(1.0, (1 - m) / 0.35)
    return round(max(FATTORE_MIN, min(1.0, m)), 3)


def con_sfumatura(img, sfuma):
    """L'immagine della scritta (RGBA W x H) con sotto l'ombra rotonda dietro la frase (opacita' sfuma al centro).
    Un filo di rumore (mezzo livello) evita gli scalini della sfumatura sui fondi uniformi."""
    if not sfuma or sfuma <= 0.005:
        return img
    import numpy as np
    W, H = img.size
    a = _profilo(W, H) * np.float32(255.0 * sfuma) + np.random.default_rng(7).random((H, W), dtype=np.float32)
    ombra = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ombra.putalpha(Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)))
    ombra.alpha_composite(img)
    return ombra


def filtro(m):
    """Filtro ffmpeg (su yuv420p a 8 bit) che moltiplica R, G e B per m: luma e colore insieme, quindi niente
    dominanti; il nero (16) resta nero. "" se non serve."""
    if m is None or m >= 0.995:
        return ""
    return f"lutyuv=y=16+(val-16)*{m:.3f}:u=128+(val-128)*{m:.3f}:v=128+(val-128)*{m:.3f}"


def senza_scuro(cmd):
    """Lo stesso comando ffmpeg senza i filtri di scurimento (quelli di filtro()); None se non ce ne sono. Se ffmpeg
    non riuscisse a montare con lo scurimento, il reel si rifa' senza (deve uscire sempre)."""
    if "-filter_complex" not in cmd:
        return None
    i = cmd.index("-filter_complex") + 1
    g = re.sub(r",lutyuv=y=16\+\(val-16\)\*[\d.]+:u=128\+\(val-128\)\*[\d.]+:v=128\+\(val-128\)\*[\d.]+", "", cmd[i])
    return None if g == cmd[i] else cmd[:i] + [g] + cmd[i + 1:]
