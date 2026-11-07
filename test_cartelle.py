"""
Prova del riordino del Drive (7/11/2026) con un Drive FINTO, senza rete: python test_cartelle.py
Controlla che il codice trovi le cartelle giuste PRIMA del riordino, DOPO e in tutti i passaggi a meta' (cartelle
spostate una alla volta, rinominate o no), che non crei mai una cartella che c'e' gia' da qualche parte e che, quando
ci sono doppioni, usi quella vera (la piu' vecchia). Prova anche i percorsi del PC (H:) con cartelle finte.
Non legge reel-segreti.json e non tocca Drive: requests e urllib vengono sostituiti da un Drive in memoria.
"""
import contextlib, io, itertools, json, os, re, shutil, sys, tempfile, types, urllib.parse, urllib.request

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, QUI)
os.chdir(QUI)
import cartelle

CARTELLA, DOC = cartelle.CARTELLA, cartelle.DOCUMENTO
errori = []


def check(ok, cosa):
    if not ok:
        errori.append(cosa)
        print("ERRORE:", cosa)


# ------------------------------------------------------------------------------------------------ Drive finto

class FintoDrive:
    """File in memoria e la parte del linguaggio delle ricerche di Drive che usa il codice."""

    def __init__(self):
        self.f, self.n, self.creati, self.ora = {}, 0, [], 0

    def nuovo(self, nome, padre=None, tipo=CARTELLA, **extra):
        self.n += 1
        self.ora += 1
        fid = f"id{self.n:03d}"
        self.f[fid] = dict(id=fid, name=nome, mimeType=tipo, parents=[padre] if padre else ["root"], trashed=False,
                           createdTime=f"2026-10-{1 + self.ora // 24:02d}T{self.ora % 24:02d}:00:00.000Z", **extra)
        return fid

    def cartelle_vive(self):
        return sum(1 for f in self.f.values() if f["mimeType"] == CARTELLA and not f["trashed"])

    # --- ricerche (q di Drive v3): and, or, not, parentesi, 'x' in parents, campo = / != / < / > / contains 'x'
    def cerca(self, q):
        toks = re.findall(r"'(?:\\.|[^'\\])*'|\(|\)|!=|<=|>=|=|<|>|[A-Za-z_]+", q)
        pos = [0]

        def guarda():
            return toks[pos[0]] if pos[0] < len(toks) else None

        def prendi():
            pos[0] += 1
            return toks[pos[0] - 1]

        def valore(t):
            if t.startswith("'"):
                return re.sub(r"\\(.)", r"\1", t[1:-1])
            if t in ("true", "false"):
                return t == "true"
            raise ValueError(f"valore strano nella ricerca: {t} ({q})")

        def fattore():
            t = prendi()
            if t == "not":
                f = fattore()
                return lambda r: not f(r)
            if t == "(":
                e = espressione()
                assert prendi() == ")", q
                return e
            if t.startswith("'"):
                v = valore(t)
                assert prendi() == "in" and prendi() == "parents", q
                return lambda r: v in r["parents"]
            campo, op, v = t, prendi(), valore(prendi())
            if campo not in ("name", "mimeType", "trashed", "createdTime"):
                raise ValueError(f"campo non previsto nella ricerca: {campo} ({q})")
            return {"=": lambda r: r[campo] == v, "!=": lambda r: r[campo] != v, "<": lambda r: r[campo] < v,
                    ">": lambda r: r[campo] > v, "contains": lambda r: v in r[campo]}[op]

        def termine():
            f = fattore()
            while guarda() == "and":
                prendi()
                a, b = f, fattore()
                f = (lambda a, b: lambda r: a(r) and b(r))(a, b)
            return f

        def espressione():
            f = termine()
            while guarda() == "or":
                prendi()
                a, b = f, termine()
                f = (lambda a, b: lambda r: a(r) or b(r))(a, b)
            return f
        filtro = espressione()
        assert pos[0] == len(toks), f"ricerca non capita fino in fondo: {q}"
        return [dict(r) for r in self.f.values() if filtro(r)]

    @staticmethod
    def campi(fields, r):
        """Solo i campi chiesti (files(id,name,...)): cosi' si vede se il codice chiede createdTime."""
        m = re.search(r"files\((.*)\)", fields or "")
        if not m:
            return r
        nomi, prof, pezzo = [], 0, ""
        for c in m.group(1):
            if c == "," and prof == 0:
                nomi.append(pezzo)
                pezzo = ""
                continue
            prof += (c == "(") - (c == ")")
            pezzo += c
        nomi.append(pezzo)
        nomi = [n.split("(")[0].strip() for n in nomi]
        return {k: v for k, v in r.items() if k in nomi}

    # --- operazioni
    def crea(self, body):
        fid = self.nuovo(body["name"], (body.get("parents") or [None])[0], body.get("mimeType", "application/octet-stream"))
        self.f[fid].update({k: v for k, v in body.items() if k in ("appProperties", "description")})
        self.creati.append(fid)
        return fid

    def aggiorna(self, fid, add=None, remove=None, body=None):
        r = self.f[fid]
        if remove:
            r["parents"] = [p for p in r["parents"] if p not in remove.split(",")]
        if add:
            r["parents"] += [p for p in add.split(",") if p not in r["parents"]]
        for k, v in (body or {}).items():
            if k == "appProperties":
                r.setdefault("appProperties", {}).update(v)
            else:
                r[k] = v


class _Esegui:
    def __init__(self, fn):
        self.fn = fn

    def execute(self, **kw):
        return self.fn()


class FintoApi:
    """Come googleapiclient (pubblica.Drive.api, mie_citazioni, salute, report)."""

    def __init__(self, d):
        self.d = d

    def files(self):
        return self

    def get(self, fileId, fields=None):
        return _Esegui(lambda: {k: v for k, v in self.d.f[fileId].items() if k in (fields or "").split(",")})

    def list(self, q, fields=None, pageSize=None, pageToken=None, orderBy=None):
        return _Esegui(lambda: {"files": [FintoDrive.campi(fields, r) for r in self.d.cerca(q)]})

    def create(self, body, fields=None, media_body=None):
        return _Esegui(lambda: {"id": self.d.crea(body)})

    def update(self, fileId, addParents=None, removeParents=None, body=None, fields=None, media_body=None):
        return _Esegui(lambda: self.d.aggiorna(fileId, addParents, removeParents, body) or {"id": fileId})

    def export(self, fileId, mimeType):
        return _Esegui(lambda: self.d.f[fileId].get("testo", "").encode("utf-8"))


class _Risposta:
    def __init__(self, dati, codice=200):
        self.dati, self.status_code = dati, codice

    def json(self):
        return self.dati

    def read(self):
        return json.dumps(self.dati).encode()

    def raise_for_status(self):
        if self.status_code != 200:
            raise RuntimeError(f"HTTP {self.status_code}")


API = "https://www.googleapis.com/drive/v3/files"


def finto_requests(d):
    """requests.get/post/patch per sposta_su_pc.py e tiktok_prepara.py."""
    def get(url, params=None, headers=None, timeout=None, **kw):
        params = params or {}
        if url == API:
            return _Risposta({"files": [FintoDrive.campi(params.get("fields"), r) for r in d.cerca(params["q"])]})
        fid = url[len(API) + 1:]
        return _Risposta({k: v for k, v in d.f[fid].items() if k in params.get("fields", "").split(",")})

    def post(url, data=None, timeout=None, **kw):
        return _Risposta({"access_token": "finto"})

    def patch(url, json=None, headers=None, timeout=None, **kw):
        d.aggiorna(url[len(API) + 1:], body=json)
        return _Risposta({})
    return types.SimpleNamespace(get=get, post=post, patch=patch)


def finto_urlopen(d):
    """urllib.request.urlopen per coda.py e ricevi_telegram.py."""
    def urlopen(req, data=None, timeout=None):
        url = req.full_url if isinstance(req, urllib.request.Request) else req
        if "oauth2" in url:
            return _Risposta({"access_token": "finto"})
        parti = urllib.parse.urlsplit(url)
        p = dict(urllib.parse.parse_qsl(parti.query))
        if parti.path.endswith("/files"):
            return _Risposta({"files": [FintoDrive.campi(p.get("fields"), r) for r in d.cerca(p["q"])]})
        fid = parti.path.rsplit("/", 1)[1]
        return _Risposta({k: v for k, v in d.f[fid].items() if k in p.get("fields", "").split(",")})
    return urlopen


# ------------------------------------------------------------------------------------------------ alberi di prova

SERVIZIO = ["Archivio", "TikTok - da pubblicare", "Instagram temporanei", "Pronti per Instagram",
            "Archivio - verso il PC", "Foto usate", "Pronti", "Pubblicati", "Automazione", "Raccolta"]


def albero_oggi():
    """Il Drive com'e' oggi (7/11/2026), in piccolo: id veri da ritrovare in ogni passaggio."""
    d = FintoDrive()
    vero = {}
    vero["principale"] = d.nuovo("Reel Alessandro", None)
    r = vero["principale"]
    vero["video"] = d.nuovo("Da pubblicare", r)
    vero["foto"] = d.nuovo("Foto della giornata", r)
    vero["frasi"] = d.nuovo("Frasi da usare", r)
    vero["fatte"] = d.nuovo("Fatte", vero["frasi"])
    for n in SERVIZIO:
        vero[n] = d.nuovo(n, r)
    vero["vecchie"] = d.nuovo("Vecchie versioni - non ripubblicare", vero["Foto usate"])
    vero["doc"] = d.nuovo("Le mie citazioni", r, DOC, testo="# note\nLa disciplina batte il talento ogni giorno.\n"
                                                         "Ogni mattina scegli chi vuoi diventare davvero.\n")
    for i in range(5):
        d.nuovo(f"IMG_49{i}.heic", vero["foto"], "image/heic", imageMediaMetadata={"time": "2026:11:06 10:0" + str(i)})
    for i in range(3):
        d.nuovo(f"IMG_48{i}.MOV", vero["Archivio"], "video/quicktime", appProperties={"scena": "ufficio"})
    for i in range(2):
        d.nuovo(f"2026-11-07 1{i}00 - MIE-x.mp4", vero["TikTok - da pubblicare"], "video/mp4")
    d.nuovo("IMG_4700.HEIC", vero["vecchie"], "image/heic")
    return d, vero


def riordina(d, vero, sposta=(), rinomina=(), principale=False, sistema=True):
    """Un passaggio del riordino: crea "Sistema (non toccare)" e sposta/rinomina solo cio' che e' indicato."""
    if sistema and not any(f["name"] == cartelle.SISTEMA for f in d.f.values()):
        vero["sistema"] = d.nuovo(cartelle.SISTEMA, vero["principale"])
    for chiave in sposta:
        d.aggiorna(vero[chiave], add=vero["sistema"], remove=vero["principale"])
    for chiave in rinomina:
        d.aggiorna(vero[chiave], body={"name": cartelle.nomi(d.f[vero[chiave]]["name"])[0]})
    if principale:
        d.aggiorna(vero["principale"], body={"name": cartelle.PRINCIPALE})


# ------------------------------------------------------------------------------------------------ chi legge il Drive

import pubblica, foto_giornata, mie_citazioni, coda, ricevi_telegram, sposta_su_pc, tiktok_prepara


def drive_pubblica(d):
    x = object.__new__(pubblica.Drive)
    x.local, x.creds, x.api = None, None, FintoApi(d)
    return x


def tutti_trovano(d, vero, cosa=""):
    """Ogni programma trova la cartella vera, senza crearne nessuna."""
    prima = d.cartelle_vive()
    x = drive_pubblica(d)
    for nome in ("Archivio", pubblica.CARTELLA_TIKTOK, "Instagram temporanei", pubblica.CARTELLA_DOPO,
                 pubblica.VERSO_PC, foto_giornata.USATE):
        check(x.cartella(nome) == vero[nome], f"{cosa}: pubblica trova '{nome}'")
    check(x.cartella(foto_giornata.CARTELLA) == vero["foto"], f"{cosa}: foto_giornata trova le foto (nome nuovo)")
    check(x.cartella("Foto della giornata") == vero["foto"], f"{cosa}: foto (nome vecchio)")
    check([a["id"] for a in x.lista_archivio()] == [f["id"] for f in d.f.values() if vero["Archivio"] in f["parents"]],
          f"{cosa}: lista_archivio")
    pronte = foto_giornata.pronte(x)
    check(len(pronte) >= 4 and all(d.f[f["id"]]["parents"] == [vero["foto"]] for f in pronte),
          f"{cosa}: foto_giornata.pronte vede le foto della cartella vera")
    check(mie_citazioni.leggi(x.api, vero["video"]).count("\n") == 3, f"{cosa}: mie_citazioni legge il Documento")
    check(mie_citazioni.trova_doc(x.api, vero["video"]) == vero["doc"], f"{cosa}: aggiungi_mie trova il Documento")
    with contextlib.redirect_stdout(io.StringIO()) as uscita:
        n = coda.conta()
    check(n == 3, f"{cosa}: coda.py conta l'archivio ({n})")
    check(uscita.getvalue() == "", f"{cosa}: coda.py non stampa altro che il numero")
    check(ricevi_telegram.cartella_foto("finto") == vero["foto"], f"{cosa}: bot Telegram trova le foto")
    check(tiktok_prepara.collega()[1] == vero["TikTok - da pubblicare"], f"{cosa}: tiktok_prepara trova la cartella")
    check(sposta_su_pc.sposta()[0] == 0, f"{cosa}: sposta_su_pc (cartella vuota, niente da fare)")
    pubblica.pulisci_temporanei(x)
    check(d.cartelle_vive() == prima, f"{cosa}: nessuna cartella creata ({d.cartelle_vive() - prima} in piu')")


def prepara_ambiente(d, cartella_pc):
    """Collega i programmi al Drive finto (mai rete, mai reel-segreti.json)."""
    segreti = os.path.join(cartella_pc, "segreti_finti.json")
    json.dump({"GOOGLE_CLIENT_ID": "x", "GOOGLE_CLIENT_SECRET": "x", "GOOGLE_REFRESH_TOKEN": "x",
               "DRIVE_FOLDER_DA_PUBBLICARE": VIDEO_ID[0]}, open(segreti, "w"))
    finto = finto_requests(d)
    for m in (sposta_su_pc, tiktok_prepara):
        m.requests = finto
        m.SEGRETI = segreti
    sposta_su_pc.CARTELLA_PC = os.path.join(cartella_pc, "Archivio reel (4K)")
    urllib.request.urlopen = finto_urlopen(d)
    os.environ.update(GOOGLE_CLIENT_ID="x", GOOGLE_CLIENT_SECRET="x", GOOGLE_REFRESH_TOKEN="x",
                      DRIVE_FOLDER_DA_PUBBLICARE=VIDEO_ID[0])
    pubblica.log = lambda *a: AVVISI.append(" ".join(str(x) for x in a))


VIDEO_ID, AVVISI = [None], []
tmp = tempfile.mkdtemp(prefix="prova_cartelle_")
vero_urlopen = urllib.request.urlopen
try:
    # 1. PRIMA del riordino (oggi), DOPO, e tutti i 1024 passaggi a meta' (10 cose che cambiano, in ogni combinazione)
    cambi = ["Archivio", "TikTok - da pubblicare", "Instagram temporanei", "Pronti per Instagram",
             "Archivio - verso il PC", "Foto usate", "doc", "video", "foto", "frasi"]
    casi = [("prima, senza Sistema", None)] + [(None, c) for c in itertools.product((0, 1), repeat=len(cambi))]
    for nome_caso, combo in casi:
        d, vero = albero_oggi()
        VIDEO_ID[0] = vero["video"]
        prepara_ambiente(d, tmp)
        if combo is None:
            tutti_trovano(d, vero, nome_caso)
            continue
        scelti = [c for c, si in zip(cambi, combo) if si]
        riordina(d, vero, sposta=[c for c in scelti if c not in ("video", "foto", "frasi")],
                 rinomina=[c for c in scelti if c in ("video", "foto", "frasi")], principale=sum(combo) % 2 == 1)
        tutti_trovano(d, vero, "meta': " + (", ".join(scelti) or "solo Sistema creata"))
    print(f"passaggi provati: {len(casi)}")

    # 2. doppioni: una cartella vuota creata per sbaglio (piu' nuova) non deve mai vincere su quella vera
    d, vero = albero_oggi()
    VIDEO_ID[0] = vero["video"]
    prepara_ambiente(d, tmp)
    riordina(d, vero, sposta=SERVIZIO + ["doc"], rinomina=["video", "foto", "frasi"], principale=True)
    finta_arch = d.nuovo("Archivio", vero["principale"])                       # codice vecchio: Archivio vuoto in cima
    finta_foto = d.nuovo("Foto della giornata", vero["principale"])           # codice vecchio: foto col nome vecchio
    finta_tt = d.nuovo("TikTok - da pubblicare", vero["sistema"])             # a mano, per sbaglio
    AVVISI.clear()
    tutti_trovano(d, vero, "doppioni")
    check(any("ATTENZIONE" in a and "'Archivio'" in a for a in AVVISI), "doppioni: avviso nel log")
    with contextlib.redirect_stderr(io.StringIO()) as err, contextlib.redirect_stdout(io.StringIO()):
        coda.conta()
    check("ATTENZIONE" in err.getvalue(), "doppioni: coda.py avvisa su stderr")

    # 3. una cartella che non c'e' da nessuna parte si crea UNA volta, nel posto giusto, col nome nuovo
    for dopo in (False, True):
        d, vero = albero_oggi()
        VIDEO_ID[0] = vero["video"]
        prepara_ambiente(d, tmp)
        if dopo:
            riordina(d, vero, sposta=SERVIZIO + ["doc"], rinomina=["video", "foto", "frasi"], principale=True)
        x = drive_pubblica(d)
        video = d.nuovo("IMG_4990.MOV", vero["video"], "video/quicktime")      # un video che non si monta
        with contextlib.redirect_stdout(io.StringIO()):
            n = coda.conta()
        check(n == 1, "coda.py: con un video nuovo conta la coda")
        x.sposta_in_sottocartella(video, "Da controllare")
        nuove = [d.f[i] for i in d.creati if d.f[i]["mimeType"] == CARTELLA]
        dove = vero["sistema"] if dopo else vero["principale"]
        check(len(nuove) == 1 and nuove[0]["name"] == "Da controllare" and nuove[0]["parents"] == [dove],
              f"creazione {'dopo' if dopo else 'prima'}: 'Da controllare' nel posto giusto")
        check(d.f[video]["parents"] == [nuove[0]["id"]] if nuove else False, "il video e' finito in 'Da controllare'")
        y = drive_pubblica(d)                                                  # un altro giro: la ritrova
        check(y.cartella("Da controllare") == (nuove[0]["id"] if nuove else None) and len(d.creati) == 1,
              "un altro giro non crea un secondo 'Da controllare'")
        x.cartella("Studio di prova")
        x.cartella("Foto da pubblicare")
        check(len(d.creati) == 2 and d.f[d.creati[1]]["parents"] == [dove], "creazione: una cartella di servizio")
        # le tre di Alessandro, se mancassero, nascono in cima (mai dentro Sistema), col nome nuovo
        d.aggiorna(vero["frasi"], body={"trashed": True})
        x.cartella("Frasi da usare")
        check(d.f[d.creati[-1]]["name"] == "Frasi da pubblicare" and d.f[d.creati[-1]]["parents"] == [vero["principale"]],
              "creazione: 'Frasi da pubblicare' in cima")

    # 4. pulizie: crea=False non fa rinascere una cartella tolta (Pronti per Instagram nel cestino)
    d, vero = albero_oggi()
    VIDEO_ID[0] = vero["video"]
    prepara_ambiente(d, tmp)
    riordina(d, vero, sposta=SERVIZIO + ["doc"], rinomina=["video", "foto", "frasi"], principale=True)
    d.aggiorna(vero["Pronti per Instagram"], body={"trashed": True})
    os.environ.update(DRIVE_FOLDER_PRONTI=vero["Pronti"], DRIVE_FOLDER_PUBBLICATI=vero["Pubblicati"])
    drive_pubblica(d).pulisci_pronti(7)
    check(d.creati == [], "pulisci_pronti non ricrea 'Pronti per Instagram'")

    # 5. foto usate: dopo il reel le foto vanno nella "Foto usate" vera, anche spostata dentro Sistema
    x = drive_pubblica(d)
    foto = [f["id"] for f in d.f.values() if vero["foto"] in f["parents"]][:2]
    foto_giornata.segna_usate(x, foto)
    check(all(d.f[i]["parents"] == [vero["Foto usate"]] for i in foto), "segna_usate sposta nella Foto usate vera")
    check(d.creati == [], "segna_usate non crea cartelle")

    # 6. Documento sparito: nessun reel come prima (None), aggiungi_mie si ferma, niente creato
    d.aggiorna(vero["doc"], body={"trashed": True})
    check(mie_citazioni.leggi(x.api, vero["video"]) is None and d.creati == [], "Documento mancante: None, niente creato")

    # 7. tiktok_prepara si ferma (non crea) se la cartella TikTok non c'e'
    d.aggiorna(vero["TikTok - da pubblicare"], body={"trashed": True})
    try:
        tiktok_prepara.collega()
        check(False, "tiktok_prepara doveva fermarsi senza cartella")
    except RuntimeError:
        pass
    check(d.creati == [], "tiktok_prepara non crea cartelle")

    # 8. nomi e ricerche
    check(cartelle.nomi("Da pubblicare") == ("Video da pubblicare", "Da pubblicare"), "nomi: Da pubblicare")
    check(cartelle.nomi("Archivio") == ("Archivio",), "nomi: Archivio")
    check(cartelle.in_cima("Foto della giornata") and not cartelle.in_cima("Foto usate"), "in_cima")
    check("name = 'l\\'altro'" in cartelle.query("l'altro", ["a"]), "apostrofo nella ricerca")

    # 9. percorsi del PC (H:) prima, a meta' e dopo
    h = os.path.join(tmp, "H")
    def fai(*p):
        os.makedirs(os.path.join(h, *p), exist_ok=True)
    def via(*p):
        shutil.rmtree(os.path.join(h, *p), ignore_errors=True)
    os.environ["REEL_DRIVE_H"] = h
    fai("Reel Alessandro", "Automazione")
    fai("Reel Alessandro", "Raccolta")
    fai("Reel Alessandro", "Frasi da usare", "Fatte")
    fai("Reel Alessandro", "Pronti")
    open(os.path.join(h, "Reel Alessandro", "Agente - diario.md"), "w").write("diario")
    RA, ZRA = os.path.join(h, "Reel Alessandro"), os.path.join(h, "0. Reel Alessandro")
    S = os.path.join(ZRA, cartelle.SISTEMA)
    check(cartelle.percorso_h("Automazione") == os.path.join(RA, "Automazione"), "H: prima, Automazione")
    check(cartelle.percorso_h("Frasi da pubblicare", "Fatte", "registro.txt") ==
          os.path.join(RA, "Frasi da usare", "Fatte", "registro.txt"), "H: prima, Frasi (nome vecchio)")
    check(cartelle.percorso_h("Agente - diario.md") == os.path.join(RA, "Agente - diario.md"), "H: prima, diario")
    check(cartelle.posto_nuovo_h("Studio viralità") == os.path.join(RA, "Studio viralità"), "H: prima, cartella nuova")
    os.rename(RA, ZRA)                                                       # meta': solo la principale rinominata
    check(cartelle.percorso_h("Raccolta") == os.path.join(ZRA, "Raccolta"), "H: meta', principale nuova")
    fai("0. Reel Alessandro", cartelle.SISTEMA)
    os.rename(os.path.join(ZRA, "Raccolta"), os.path.join(S, "Raccolta"))   # meta': Raccolta spostata, Automazione no
    check(cartelle.percorso_h("Raccolta") == os.path.join(S, "Raccolta"), "H: meta', Raccolta in Sistema")
    check(cartelle.percorso_h("Automazione") == os.path.join(ZRA, "Automazione"), "H: meta', Automazione ancora su")
    check(cartelle.posto_nuovo_h("Studio viralità") == os.path.join(S, "Studio viralità"), "H: cartella nuova in Sistema")
    os.rename(os.path.join(ZRA, "Automazione"), os.path.join(S, "Automazione"))
    os.rename(os.path.join(ZRA, "Frasi da usare"), os.path.join(ZRA, "Frasi da pubblicare"))
    os.rename(os.path.join(ZRA, "Agente - diario.md"), os.path.join(S, "Agente - diario.md"))
    check(cartelle.percorso_h("Automazione") == os.path.join(S, "Automazione"), "H: dopo, Automazione")
    check(cartelle.percorso_h("Frasi da usare") == os.path.join(ZRA, "Frasi da pubblicare"), "H: dopo, Frasi")
    check(cartelle.percorso_h("Agente - diario.md") == os.path.join(S, "Agente - diario.md"), "H: dopo, diario")
    check(cartelle.posto_nuovo_h("Foto da pubblicare") == os.path.join(ZRA, "Foto da pubblicare"), "H: le tre in cima")
    import importlib, sincronizza
    importlib.reload(sincronizza)
    check(sincronizza.DST == os.path.join(S, "Automazione"), "sincronizza.py: Automazione dopo il riordino")
    via("0. Reel Alessandro", cartelle.SISTEMA, "Automazione")
    importlib.reload(sincronizza)
    check(sincronizza.DST is None, "sincronizza.py: Automazione tolta, nessun posto")
    if sincronizza.DST is None:          # solo cosi' main() non copia niente (mai il repository in una cartella vera)
        with contextlib.redirect_stdout(io.StringIO()) as uscita:
            sincronizza.main()
        check("non copio niente" in uscita.getvalue(), "sincronizza.py: Automazione tolta, non la ricrea")
    check(not os.path.exists(os.path.join(S, "Automazione")) and not os.path.exists(os.path.join(ZRA, "Automazione")),
          "sincronizza.py: nessuna cartella ricreata")

    # 10. stati a meta' fra i passi 5, 6 e 7 del riordino (principale ancora "Reel Alessandro") e il comando
    #     "python cartelle.py <nome>" che usano gli SKILL: trova sempre il posto vero, in ogni combinazione
    h2 = os.path.join(tmp, "H2")
    os.environ["REEL_DRIVE_H"] = h2
    RA2 = os.path.join(h2, "Reel Alessandro")
    S2 = os.path.join(RA2, cartelle.SISTEMA)
    for p in ("Frasi da pubblicare", os.path.join("Frasi da pubblicare", "Fatte"), os.path.join(cartelle.SISTEMA, "Raccolta"),
              os.path.join(cartelle.SISTEMA, "Frasi da foto")):
        os.makedirs(os.path.join(RA2, p), exist_ok=True)
    check(cartelle.percorso_h("Frasi da usare") == os.path.join(RA2, "Frasi da pubblicare"),
          "H: passo 6 fatto e 7 no, Frasi da pubblicare in Reel Alessandro")
    check(cartelle.percorso_h("Raccolta") == os.path.join(S2, "Raccolta"), "H: passo 5 fatto e 7 no, Raccolta")
    check(cartelle.percorso_h("Frasi da foto") == os.path.join(S2, "Frasi da foto"), "H: passo 5 fatto e 7 no, Frasi da foto")
    tutti_i_posti = cartelle.candidati_h("Frasi da foto", h2)
    check(len(set(tutti_i_posti)) == 4 and os.path.join(S2, "Frasi da foto") in tutti_i_posti and
          os.path.join(RA2, "Frasi da foto") in tutti_i_posti, "candidati_h: le 4 combinazioni")
    import subprocess
    for nome, atteso in (("Frasi da pubblicare", os.path.join(RA2, "Frasi da pubblicare")),
                         ("Raccolta", os.path.join(S2, "Raccolta")), ("Studio viralità", None)):
        r = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "cartelle.py"), nome],
                           capture_output=True, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        out = r.stdout.decode("utf-8", "replace")
        if atteso:
            check(r.returncode == 0 and out.strip() == f"{nome}: {atteso}", f"python cartelle.py \"{nome}\" a meta'")
        else:
            check(r.returncode == 0 and os.path.join(S2, nome) in out and "non c'e'" in out,
                  f"python cartelle.py \"{nome}\": dice dove crearla (in Sistema)")
    check(not os.path.exists(os.path.join(h2, cartelle.PRINCIPALE)), "nessuna principale nuova creata")
finally:
    urllib.request.urlopen = vero_urlopen
    shutil.rmtree(tmp, ignore_errors=True)

print("TUTTO OK" if not errori else f"ERRORI: {len(errori)}")
sys.exit(1 if errori else 0)
