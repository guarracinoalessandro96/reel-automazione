"""
Pubblicazione automatica dei Reel (GitHub Actions, alle 9, 12, 15, 18, 21 ora italiana).

Ad ogni esecuzione:
  0. riprova le piattaforme fallite nelle esecuzioni precedenti (max 3 tentativi)
  1. analizza i video nuovi della cartella Drive "Da pubblicare": scena (scena.py) e ora di registrazione
     -> ogni video ha il suo orario: mattina alle 9, pranzo alle 12, palestra e uscite la sera...
  2. prende il video che corrisponde a questo orario (se un video aspetta da piu' di 36 ore, esce comunque)
  3. sceglie una frase adatta alla scena (frasi.json: cibo -> dieta, palestra -> fisico, pacchi -> imprenditore...)
     alternando i temi, e una musica adatta al tema
  4. monta il video (taglio, colore, testo, musica) e lo pubblica su Instagram, Facebook, YouTube, TikTok
     con descrizione breve: la stessa frase + 3-4 hashtag
  5. archivia su Drive e aggiorna stato.json

Credenziali: variabili d'ambiente (GitHub Secrets). DRY_RUN=1 fa tutto tranne pubblicare.
"""
import io, json, os, sys, time, datetime, random, traceback, subprocess, shutil
import requests
import overlay
import scena as scene_mod

HERE = os.path.dirname(os.path.abspath(__file__))
FRASI = os.path.join(HERE, "frasi.json")
STATE = os.path.join(HERE, "stato.json")
GRAPH = "https://graph.facebook.com/v23.0"
ENV = os.environ.get
DRY = ENV("DRY_RUN") == "1"
PLATFORMS = ["instagram", "facebook", "youtube", "tiktok"]
MAX_TENTATIVI = 3
GIORNI_PRONTI = 30            # i reel montati restano su Drive 30 giorni, poi vanno nel Cestino
QUALITA_MINIMA = 720          # lato corto minimo (pixel): sotto l'HD il video non si pubblica
CARTELLA_BASSA = "Da controllare - bassa qualità"
ATTESA_MAX_ORE = 36          # oltre questa attesa un video esce al primo orario libero
PRIMO_COMMENTO = False       # disattivato su richiesta: niente commento automatico sotto i reel

# Temi preferiti per ogni scena (il primo e' il piu' adatto)
TEMI_PER_SCENA = {
    "cibo": ["dieta"],
    "palestra": ["palestra", "disciplina", "imprenditore"],
    "lavoro": ["imprenditore", "disciplina"],
    "pacchi": ["imprenditore"],
    "macchina": ["imprenditore", "positivita", "mentalita", "abitudini", "disciplina"],
    "specchio": ["lifestyle", "positivita", "mentalita", "abitudini"],
    "casa": ["famiglia", "abitudini", "mentalita", "positivita"],
    "uscita": ["amicizia", "lifestyle", "positivita", "famiglia"],
}
# Umore della musica per tema (cartelle in musica/, create da genera_musica.py)
MOOD = {"dieta": "luminoso", "palestra": "energia", "imprenditore": "deciso", "disciplina": "deciso",
        "abitudini": "calmo", "positivita": "luminoso", "famiglia": "caldo", "amicizia": "caldo",
        "mentalita": "calmo", "lifestyle": "luminoso"}


GENERE_PER_SCENA = {   # un genere diverso per ogni contesto (genera_generi.py)
    "palestra": "phonk", "macchina": "drive", "lavoro": "house", "pacchi": "house",
    "cibo": "lofi", "uscita": "tropical", "specchio": "trap", "casa": "caldo"}


def scegli_musica(tema, recenti, scena=None):
    """Un brano del genere della scena (o dell'umore del tema), evitando quelli usati di recente."""
    for mood in (GENERE_PER_SCENA.get(scena), MOOD.get(tema, "luminoso"), "deciso", "luminoso"):
        if not mood:
            continue
        d = os.path.join(HERE, "musica", mood)
        brani = sorted(f for f in os.listdir(d) if f.endswith(".flac")) if os.path.isdir(d) else []
        if brani:
            liberi = [b for b in brani if b not in recenti] or brani
            return os.path.join(d, random.choice(liberi))
    return None


GIORNI_RIUSO = 150            # una citazione puo' tornare dopo 5 mesi (prima escono sempre quelle mai usate)


def scegli_frase(frasi, scena, usi, temi_recenti, pesi=None):
    """Citazione adatta alla scena. usi = {id: data ISO dell'ultimo utilizzo}.
    Prima quelle mai uscite, poi quelle uscite da piu' di GIORNI_RIUSO giorni (le piu' vecchie per prime):
    la scorta non finisce mai."""
    pref = TEMI_PER_SCENA.get(scena, [])
    limite = (datetime.date.today() - datetime.timedelta(days=GIORNI_RIUSO)).isoformat()
    libere = [f for f in frasi if f["id"] not in usi or usi[f["id"]] < limite]
    cand = [f for f in libere if scena in f["scene"]] or libere
    if not cand:                              # caso estremo: tutte usate di recente -> la meno recente
        return min(frasi, key=lambda f: usi.get(f["id"], ""))

    def punteggio(f):
        s = 10 - 2 * pref.index(f["tema"]) if f["tema"] in pref else 0
        if f["tema"] in temi_recenti[-2:]:
            s -= 6                      # non lo stesso tema due volte di fila
        s += 5 * ((pesi or {}).get(f["tema"], 1.0) - 1)   # report settimanale: i temi che rendono di piu' salgono
        if f["id"] not in usi:
            s += 20                     # le citazioni mai uscite hanno sempre la precedenza
        return s + random.random() * 3  # un po' di varieta'
    return max(cand, key=punteggio)


def testo_breve(cap):
    """Descrizione pubblicata: la stessa frase del video + 3-4 hashtag (niente dettagli personali)."""
    tags = cap.get("hashtag") or ["#citazioni", "#motivazione"]
    testo = cap["gancio"].strip()
    if cap.get("autore"):
        testo = "“" + testo.strip('"“”') + "” — " + cap["autore"]
    else:
        testo = testo.rstrip(" .")
    return testo + "\n\n" + " ".join(dict.fromkeys(tags[:4]))


def log(*a):
    print(datetime.datetime.now().strftime("%H:%M:%S"), *a, flush=True)


CREDENZIALI = {"instagram": "META_PAGE_TOKEN", "facebook": "META_PAGE_TOKEN",
               "youtube": "GOOGLE_REFRESH_TOKEN", "tiktok": "TIKTOK_REFRESH_TOKEN"}


def attive():
    """Piattaforme da usare: non saltate a mano (SALTA_X=1) e con le credenziali gia' collegate."""
    return [p for p in PLATFORMS
            if ENV(f"SALTA_{p.upper()}") != "1" and (DRY or ENV(CREDENZIALI[p]))]


# ------------------------------------------------------------------ Google (Drive + YouTube)
def google_creds():
    from google.oauth2.credentials import Credentials
    return Credentials(None, refresh_token=ENV("GOOGLE_REFRESH_TOKEN"),
                       client_id=ENV("GOOGLE_CLIENT_ID"), client_secret=ENV("GOOGLE_CLIENT_SECRET"),
                       token_uri="https://oauth2.googleapis.com/token")


class Drive:
    """Accesso a Drive. In DRY_RUN usa una cartella locale (DRY_DIR) al posto di Drive."""

    def __init__(self, creds):
        self.local = ENV("DRY_DIR") if DRY else None
        if not self.local:
            from googleapiclient.discovery import build
            self.api = build("drive", "v3", credentials=creds, cache_discovery=False)

    def list_videos(self):
        """Tutti i video in coda: [{id, name, createdTime}], dal piu' vecchio."""
        if self.local:
            d = os.path.join(self.local, "Da pubblicare")
            vids = sorted((f for f in os.listdir(d) if f.lower().endswith((".mov", ".mp4", ".m4v"))),
                          key=lambda f: os.path.getmtime(os.path.join(d, f)))
            return [{"id": v, "name": v, "createdTime": datetime.datetime.fromtimestamp(
                os.path.getmtime(os.path.join(d, v)), datetime.timezone.utc).isoformat()} for v in vids]
        q = (f"'{ENV('DRIVE_FOLDER_DA_PUBBLICARE')}' in parents and trashed = false "
             "and mimeType contains 'video/'")
        res = self.api.files().list(q=q, orderBy="createdTime", pageSize=100,
                                    fields="files(id,name,createdTime)").execute()
        return res.get("files", [])

    def download(self, file_id, dest, folder="Da pubblicare"):
        if self.local:
            shutil.copy(os.path.join(self.local, folder, file_id), dest)
            return
        from googleapiclient.http import MediaIoBaseDownload
        with io.FileIO(dest, "wb") as fh:
            dl = MediaIoBaseDownload(fh, self.api.files().get_media(fileId=file_id), chunksize=50 * 1024 * 1024)
            done = False
            while not done:
                _, done = dl.next_chunk()

    def testo_tiktok(self, testo, nome_video):
        """Aggiunge in cima al file 'TIKTOK - testi da incollare.txt' (cartella Pronti) la frase del reel appena inviato."""
        titolo = "TIKTOK - testi da incollare.txt"
        riga = f"{datetime.datetime.now():%d/%m %H:%M}  |  {nome_video}\n{testo}\n\n{'-' * 40}\n\n"
        if self.local:
            path = os.path.join(self.local, "Pronti", titolo)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            vecchio = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
            open(path, "w", encoding="utf-8").write(riga + vecchio)
            return
        from googleapiclient.http import MediaIoBaseUpload
        folder = ENV("DRIVE_FOLDER_PRONTI")
        q = f"'{folder}' in parents and trashed = false and name = '{titolo}'"
        found = self.api.files().list(q=q, fields="files(id)").execute().get("files", [])
        vecchio = self.api.files().get_media(fileId=found[0]["id"]).execute().decode("utf-8") if found else ""
        media = MediaIoBaseUpload(io.BytesIO((riga + vecchio)[:200000].encode("utf-8")), mimetype="text/plain")
        if found:
            self.api.files().update(fileId=found[0]["id"], media_body=media).execute()
        else:
            self.api.files().create(body={"name": titolo, "parents": [folder]}, media_body=media).execute()

    def cestino(self, file_id):
        """Mette il video nel Cestino di Drive (recuperabile per 30 giorni, poi Google lo elimina da solo)."""
        if self.local:
            os.remove(os.path.join(self.local, "Da pubblicare", file_id))
            return
        self.api.files().update(fileId=file_id, body={"trashed": True}, fields="id").execute()

    def sposta_in_sottocartella(self, file_id, nome):
        """Sposta un video da 'Da pubblicare' a una cartella accanto (creata se manca)."""
        if self.local:
            dest = os.path.join(self.local, nome)
            os.makedirs(dest, exist_ok=True)
            shutil.move(os.path.join(self.local, "Da pubblicare", file_id), os.path.join(dest, file_id))
            return
        origine = ENV("DRIVE_FOLDER_DA_PUBBLICARE")
        padre = self.api.files().get(fileId=origine, fields="parents").execute()["parents"][0]
        nome_q = nome.replace("'", "\\'")
        q = (f"'{padre}' in parents and name = '{nome_q}' and trashed = false "
             "and mimeType = 'application/vnd.google-apps.folder'")
        found = self.api.files().list(q=q, fields="files(id)").execute().get("files", [])
        cartella = found[0]["id"] if found else self.api.files().create(
            body={"name": nome, "parents": [padre], "mimeType": "application/vnd.google-apps.folder"},
            fields="id").execute()["id"]
        self.api.files().update(fileId=file_id, addParents=cartella, removeParents=origine, fields="id").execute()

    def archive(self, file_id, final_path, final_name):
        """Dopo la pubblicazione: l'originale va nel Cestino (una copia resta nella galleria dell'iPhone)
        e il reel montato va in Pronti, dove resta GIORNI_PRONTI giorni. Restituisce l'id del montato."""
        if self.local:
            os.makedirs(os.path.join(self.local, "Pronti"), exist_ok=True)
            os.remove(os.path.join(self.local, "Da pubblicare", file_id))
            shutil.copy(final_path, os.path.join(self.local, "Pronti", final_name))
            return final_name
        from googleapiclient.http import MediaFileUpload
        self.api.files().update(fileId=file_id, body={"trashed": True}, fields="id").execute()
        f = self.api.files().create(body={"name": final_name, "parents": [ENV("DRIVE_FOLDER_PRONTI")]},
                                    media_body=MediaFileUpload(final_path, mimetype="video/mp4"),
                                    fields="id").execute()
        return f["id"]

    def pulisci_pronti(self, giorni):
        """Mette nel Cestino i reel montati piu' vecchi di `giorni` (e gli eventuali vecchi originali in Pubblicati)."""
        limite = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=giorni)
        if self.local:
            return 0
        n = 0
        for cartella, soglia in ((ENV("DRIVE_FOLDER_PRONTI"), limite),
                                 (ENV("DRIVE_FOLDER_PUBBLICATI"), datetime.datetime.now(datetime.timezone.utc))):
            if not cartella:
                continue
            q = f"'{cartella}' in parents and trashed = false and mimeType contains 'video/'"
            for f in self.api.files().list(q=q, fields="files(id,createdTime)", pageSize=200).execute().get("files", []):
                if datetime.datetime.fromisoformat(f["createdTime"].replace("Z", "+00:00")) < soglia:
                    self.api.files().update(fileId=f["id"], body={"trashed": True}, fields="id").execute()
                    n += 1
        return n


def youtube_upload(creds, path, cap):
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    title = cap["gancio"]
    if len(title) > 90:
        title = title[:87].rsplit(" ", 1)[0] + "..."
    privacy = ENV("YOUTUBE_PRIVACY") or "public"
    body = {"snippet": {"title": title + " #shorts", "description": testo_breve(cap), "categoryId": "22",
                        "defaultLanguage": "it", "defaultAudioLanguage": "it"},
            "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}}
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(path, mimetype="video/mp4", resumable=True))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    vid = resp["id"]
    if PRIMO_COMMENTO and cap.get("commento") and privacy == "public":
        try:
            yt.commentThreads().insert(part="snippet", body={"snippet": {"videoId": vid, "topLevelComment": {
                "snippet": {"textOriginal": cap["commento"]}}}}).execute()
        except Exception as e:
            log("youtube: commento non pubblicato:", e)
    return vid


# ------------------------------------------------------------------ Meta (Instagram + Facebook)
def _rupload(url, token, path):
    with open(path, "rb") as f:
        r = requests.post(url, headers={"Authorization": f"OAuth {token}", "offset": "0",
                                        "file_size": str(os.path.getsize(path))}, data=f, timeout=600)
    return r.json()


def _ig_carica_e_pubblica(path, dati):
    """Crea il contenitore Instagram (reel o storia), carica il video, aspetta l'elaborazione e pubblica."""
    token, ig = ENV("META_PAGE_TOKEN"), ENV("IG_USER_ID")
    r = requests.post(f"{GRAPH}/{ig}/media", data={**dati, "upload_type": "resumable", "access_token": token}).json()
    if "id" not in r:
        raise RuntimeError(r)
    cid = r["id"]
    up = _rupload(r.get("uri", f"https://rupload.facebook.com/ig-api-upload/v23.0/{cid}"), token, path)
    if up.get("success") is False or "error" in up:
        raise RuntimeError(up)
    for _ in range(60):                      # attende l'elaborazione (max ~10 minuti)
        st = requests.get(f"{GRAPH}/{cid}", params={"fields": "status_code,status", "access_token": token}).json()
        if st.get("status_code") == "FINISHED":
            break
        if st.get("status_code") == "ERROR":
            raise RuntimeError(st)
        time.sleep(10)
    pub = requests.post(f"{GRAPH}/{ig}/media_publish", data={"creation_id": cid, "access_token": token}).json()
    if "id" not in pub:
        raise RuntimeError(pub)
    return pub["id"]


def instagram_storia(path):
    """Lo stesso reel anche nelle Storie di Instagram: piu' persone lo vedono."""
    return _ig_carica_e_pubblica(path, {"media_type": "STORIES"})


def instagram_upload(path, cap):
    token, ig = ENV("META_PAGE_TOKEN"), ENV("IG_USER_ID")
    dati = {"media_type": "REELS", "caption": testo_breve(cap), "share_to_feed": "true"}
    if cap.get("copertina_ms") is not None:
        dati["thumb_offset"] = str(cap["copertina_ms"])
    r = requests.post(f"{GRAPH}/{ig}/media", data={**dati, "upload_type": "resumable",
                                                     "access_token": token}).json()
    if "id" not in r:
        raise RuntimeError(r)
    cid = r["id"]
    up = _rupload(r.get("uri", f"https://rupload.facebook.com/ig-api-upload/v23.0/{cid}"), token, path)
    if up.get("success") is False or "error" in up:
        raise RuntimeError(up)
    for _ in range(60):                      # attende l'elaborazione (max ~10 minuti)
        st = requests.get(f"{GRAPH}/{cid}", params={"fields": "status_code,status", "access_token": token}).json()
        if st.get("status_code") == "FINISHED":
            break
        if st.get("status_code") == "ERROR":
            raise RuntimeError(st)
        time.sleep(10)
    pub = requests.post(f"{GRAPH}/{ig}/media_publish", data={"creation_id": cid, "access_token": token}).json()
    if "id" not in pub:
        raise RuntimeError(pub)
    if PRIMO_COMMENTO and cap.get("commento"):
        c = requests.post(f"{GRAPH}/{pub['id']}/comments", data={"message": cap["commento"], "access_token": token}).json()
        if "id" not in c:
            log("instagram: commento non pubblicato:", c)
    return pub["id"]


def facebook_upload(path, cap):
    token, page = ENV("META_PAGE_TOKEN"), ENV("FB_PAGE_ID")
    start = requests.post(f"{GRAPH}/{page}/video_reels", data={"upload_phase": "start", "access_token": token}).json()
    vid = start.get("video_id")
    if not vid:
        raise RuntimeError(start)
    up = _rupload(start.get("upload_url", f"https://rupload.facebook.com/video-upload/v23.0/{vid}"), token, path)
    if not up.get("success"):
        raise RuntimeError(up)
    fin = requests.post(f"{GRAPH}/{page}/video_reels",
                        data={"upload_phase": "finish", "video_id": vid, "video_state": "PUBLISHED",
                              "description": testo_breve(cap), "access_token": token}).json()
    if not fin.get("success"):
        raise RuntimeError(fin)
    if PRIMO_COMMENTO and cap.get("commento"):
        for _ in range(12):                  # il reel deve finire l'elaborazione prima di accettare commenti
            c = requests.post(f"{GRAPH}/{vid}/comments", data={"message": cap["commento"], "access_token": token}).json()
            if "id" in c:
                break
            time.sleep(15)
        else:
            log("facebook: commento non pubblicato:", c)
    return vid


# ------------------------------------------------------------------ TikTok
def tiktok_token():
    r = requests.post("https://open.tiktokapis.com/v2/oauth/token/",
                      data={"client_key": ENV("TIKTOK_CLIENT_KEY"), "client_secret": ENV("TIKTOK_CLIENT_SECRET"),
                            "grant_type": "refresh_token", "refresh_token": ENV("TIKTOK_REFRESH_TOKEN")}).json()
    if "access_token" not in r:
        raise RuntimeError(r)
    new_rt = r.get("refresh_token")
    if new_rt and new_rt != ENV("TIKTOK_REFRESH_TOKEN") and ENV("GH_PAT"):
        # TikTok puo' cambiare il refresh token: aggiorna il Secret per le esecuzioni successive
        subprocess.run(["gh", "secret", "set", "TIKTOK_REFRESH_TOKEN", "--body", new_rt],
                       env={**os.environ, "GH_TOKEN": ENV("GH_PAT")}, check=False)
    return r["access_token"]


def tiktok_upload(path, cap):
    """Due modalita' (variabile TIKTOK_MODO):
    - "bozze" (predefinita): il reel arriva nelle bozze/notifiche di TikTok e Alessandro lo pubblica con un tocco.
      Serve finche' l'app TikTok non e' approvata: le bozze le pubblica lui, quindi escono PUBBLICHE.
    - "diretto": pubblicazione diretta (privata finche' l'app non e' approvata; privacy da TIKTOK_PRIVACY)."""
    token = tiktok_token()
    size = os.path.getsize(path)
    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"}
    source = {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": size, "total_chunk_count": 1}
    if (ENV("TIKTOK_MODO") or "bozze") == "diretto":
        init = requests.post("https://open.tiktokapis.com/v2/post/publish/video/init/", headers=h,
                             json={"post_info": {"title": testo_breve(cap)[:2200],
                                                 "privacy_level": ENV("TIKTOK_PRIVACY") or "SELF_ONLY",
                                                 "disable_comment": False, "disable_duet": False,
                                                 "disable_stitch": False,
                                                 "video_cover_timestamp_ms": cap.get("copertina_ms", 1000)},
                                   "source_info": source}).json()
    else:
        init = requests.post("https://open.tiktokapis.com/v2/post/publish/inbox/video/init/", headers=h,
                             json={"source_info": source}).json()
    data = init.get("data", {})
    if "upload_url" not in data:
        raise RuntimeError(init)
    with open(path, "rb") as f:
        up = requests.put(data["upload_url"], data=f, timeout=600,
                          headers={"Content-Type": "video/mp4", "Content-Length": str(size),
                                   "Content-Range": f"bytes 0-{size - 1}/{size}"})
    if up.status_code >= 300:
        raise RuntimeError(up.text)
    return data["publish_id"]


# ------------------------------------------------------------------ orchestrazione
def publish_all(path, cap, creds, only):
    fns = {"instagram": lambda: instagram_upload(path, cap),
           "facebook": lambda: facebook_upload(path, cap),
           "youtube": lambda: youtube_upload(creds, path, cap),
           "tiktok": lambda: tiktok_upload(path, cap)}
    results = {}
    for name in only:
        if DRY:
            results[name] = {"ok": True, "id": "prova"}
            log(name, "(prova) ok")
            continue
        try:
            results[name] = {"ok": True, "id": fns[name]()}
            log(name, "pubblicato")
        except Exception as e:
            results[name] = {"ok": False, "errore": str(e)[:500]}
            log(name, "ERRORE:", e)
            traceback.print_exc()
    return results


def analizza_video(drive, v, work):
    """Scarica il video, riconosce la scena e l'ora di registrazione, calcola l'orario di uscita."""
    src = os.path.join(work, "analisi" + os.path.splitext(v["name"])[1])
    drive.download(v["id"], src)
    info = subprocess.run([overlay.FFMPEG, "-hide_banner", "-i", src], capture_output=True, text=True,
                          errors="ignore").stderr
    seconds, hdr = overlay.probe(src)
    start, length = overlay.segmento(seconds)
    frames = overlay.extract_frames(src, length, n=8, start=start, vf=overlay.HDR_TO_SDR if hdr else None)
    sc, conf, motivo = scene_mod.riconosci(frames, v["name"])
    quando = scene_mod.ora_registrazione(info)
    os.remove(src)
    lato_corto = min(frames[0].shape[:2]) if frames else 0
    return {"nome": v["name"], "scena": sc, "sicurezza": conf, "motivo": motivo, "lato_corto": lato_corto,
            "registrato": quando.isoformat(timespec="minutes") if quando else None,
            "slot": scene_mod.slot_per(sc, quando), "caricato": v["createdTime"]}


def scegli_video(videos, analisi, slot_ora):
    """Il video giusto per questo orario; se nessuno, quello che aspetta da troppo."""
    if not videos:
        return None
    if slot_ora is None:                       # esecuzione manuale: il piu' vecchio
        return videos[0]
    adatti = [v for v in videos if analisi[v["id"]]["slot"] == slot_ora]
    if adatti:
        return adatti[0]
    ora = datetime.datetime.now(datetime.timezone.utc)
    vecchi = [v for v in videos if (ora - datetime.datetime.fromisoformat(
        v["createdTime"].replace("Z", "+00:00"))).total_seconds() > ATTESA_MAX_ORE * 3600]
    return vecchi[0] if vecchi else None


def main():
    slot = sys.argv[1] if len(sys.argv) > 1 else "manuale"
    slot_ora = None if "manuale" in slot else int(slot.split()[-1])
    frasi = json.load(open(FRASI, encoding="utf-8"))
    state = json.load(open(STATE, encoding="utf-8")) if os.path.exists(STATE) else {}
    for k, v in (("usate", []), ("storico", []), ("riprova", []), ("slot_fatti", []), ("musica_recenti", []),
                 ("frasi_usate", []), ("temi_recenti", []), ("analisi", {})):
        state.setdefault(k, v)

    def save():
        json.dump(state, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)

    if not DRY and not ENV("GOOGLE_REFRESH_TOKEN"):
        log("Account non ancora collegati (Secrets mancanti): niente da fare.")
        return
    creds = None if DRY else google_creds()
    drive = Drive(creds)
    work = os.path.join(HERE, "_lavoro")
    os.makedirs(work, exist_ok=True)

    # 0. nuovi tentativi per le piattaforme fallite
    for job in list(state["riprova"]):
        if "frase" not in job:                 # formato vecchio: si scarta
            state["riprova"].remove(job)
            continue
        path = os.path.join(work, "riprova.mp4")
        try:
            drive.download(job["pronti_id"], path, folder="Pronti")
        except Exception as e:
            log("riprova: download fallito", e)
            continue
        res = publish_all(path, job["frase"], creds, job["piattaforme"])
        job["tentativi"] += 1
        job["piattaforme"] = [p for p, r in res.items() if not r["ok"]]
        state["storico"].append({"quando": datetime.datetime.now().isoformat(timespec="minutes"),
                                 "riprova": job["frase"]["id"], "risultati": res})
        if not job["piattaforme"] or job["tentativi"] >= MAX_TENTATIVI:
            state["riprova"].remove(job)
        save()

    # pulizia di Drive (una volta al giorno, alla prima esecuzione della giornata)
    oggi = datetime.date.today().isoformat()
    if state.get("pulizia") != oggi and not DRY:
        try:
            n = drive.pulisci_pronti(GIORNI_PRONTI)
            log(f"Pulizia Drive: {n} file nel cestino")
        except Exception as e:
            log("pulizia Drive non riuscita:", e)
        state["pulizia"] = oggi
        save()

    # 1. analisi dei video nuovi in coda
    videos = drive.list_videos()
    for v in videos:
        if v["id"] not in state["analisi"]:
            try:
                state["analisi"][v["id"]] = analizza_video(drive, v, work)
                log("Analizzato:", state["analisi"][v["id"]])
            except Exception as e:
                log("Analisi fallita per", v["name"], e)
                state["analisi"][v["id"]] = {"nome": v["name"], "scena": "casa", "slot": 15,
                                             "errore": str(e)[:200], "caricato": v["createdTime"]}
    for v in list(videos):
        a = state["analisi"].get(v["id"], {})
        if 0 < a.get("lato_corto", 9999) < QUALITA_MINIMA:
            log(f"{v['name']}: qualità troppo bassa ({a['lato_corto']}p), messo nel cestino di Drive")
            try:
                drive.cestino(v["id"])
            except Exception as e:
                log("cestino non riuscito:", e)
            videos.remove(v)
    in_coda = {v["id"] for v in videos}
    state["analisi"] = {k: a for k, a in state["analisi"].items() if k in in_coda}   # dimentica quelli usciti
    save()

    # 2. il video giusto per questo orario
    video = scegli_video(videos, state["analisi"], slot_ora)
    if video is None:
        log(f"Nessun video per l'orario {slot} (in coda: {len(videos)}).")
        return
    an = state["analisi"][video["id"]]

    # 3. frase e musica adatte
    pesi_file = os.path.join(HERE, "pesi.json")
    pesi = json.load(open(pesi_file, encoding="utf-8")).get("temi", {}) if os.path.exists(pesi_file) else {}
    usi = {h["frase"]: h["quando"][:10] for h in state["storico"] if h.get("frase") and h.get("quando")}
    frase = scegli_frase(frasi, an["scena"], usi, state["temi_recenti"], pesi)
    music = None if ENV("SENZA_MUSICA") == "1" else scegli_musica(frase["tema"], state["musica_recenti"], an["scena"])
    log(f"Slot {slot} | {video['name']} | scena {an['scena']} | frase {frase['id']} ({frase['tema']}): {frase['gancio']}")

    # 4. montaggio e pubblicazione
    src = os.path.join(work, "originale" + os.path.splitext(video["name"])[1])
    out = os.path.join(work, "reel.mp4")
    try:
        drive.download(video["id"], src)
        info = overlay.make_video(src, frase["gancio"], out, preview=os.path.join(work, "anteprima.jpg"), music=music,
                                  autore=frase.get("autore"),
                                  colore=ENV("SENZA_COLORE") != "1", nome=video["name"],
                                  scena_rilevata=an["scena"])
    except Exception as e:      # un video "rotto" non deve bloccare la coda: dopo 2 tentativi va in "Da controllare"
        an["fallimenti"] = an.get("fallimenti", 0) + 1
        an["errore"] = str(e)[:300]
        log(f"Montaggio fallito per {video['name']} (tentativo {an['fallimenti']}): {e}")
        if an["fallimenti"] >= 2:
            try:
                drive.sposta_in_sottocartella(video["id"], "Da controllare")
                state["analisi"].pop(video["id"], None)
                log(f"{video['name']} spostato in 'Da controllare': la coda prosegue con gli altri video.")
            except Exception as e2:
                log("spostamento non riuscito:", e2)
        save()
        shutil.rmtree(work, ignore_errors=True)
        raise
    log("Montato:", info)
    frase = dict(frase, copertina_ms=info.get("copertina_ms"))
    results = publish_all(out, frase, creds, attive())
    if results.get("instagram", {}).get("ok") and ENV("SENZA_STORIE") != "1" and not DRY:
        try:
            results["instagram_storia"] = {"ok": True, "id": instagram_storia(out)}
            log("instagram storia pubblicata")
        except Exception as e:
            results["instagram_storia"] = {"ok": False, "errore": str(e)[:300]}
            log("instagram storia non pubblicata:", e)
    if not any(r["ok"] for r in results.values()):
        log("Nessuna piattaforma ha funzionato: il video resta in coda per il prossimo orario.")
        sys.exit(1)

    # 5. archivio e stato
    pronti_id = drive.archive(video["id"], out, f"{frase['id']} - {os.path.splitext(video['name'])[0]}.mp4")
    failed = [p for p, r in results.items() if not r["ok"] and p in PLATFORMS]
    if results.get("tiktok", {}).get("ok") and (ENV("TIKTOK_MODO") or "bozze") != "diretto":
        try:                                  # la frase da incollare quando pubblica la bozza su TikTok
            drive.testo_tiktok(testo_breve(frase), video["name"])
        except Exception as e:
            log("testo TikTok non salvato su Drive:", e)
    if failed:
        state["riprova"].append({"frase": frase, "pronti_id": pronti_id, "piattaforme": failed, "tentativi": 0})
    state["frasi_usate"].append(frase["id"])
    state["temi_recenti"] = (state["temi_recenti"] + [frase["tema"]])[-10:]
    if info.get("musica"):
        state["musica_recenti"] = (state["musica_recenti"] + [info["musica"]])[-8:]
    state["slot_fatti"] = (state["slot_fatti"] + [slot])[-60:]
    state["analisi"].pop(video["id"], None)
    state["storico"].append({"quando": datetime.datetime.now().isoformat(timespec="minutes"), "slot": slot,
                             "video": video["name"], "scena": an["scena"], "registrato": an.get("registrato"),
                             "frase": frase["id"], "tema": frase["tema"], "montaggio": info, "risultati": results})
    save()
    shutil.rmtree(work, ignore_errors=True)
    log("Fatto." + (f" Da riprovare: {failed}" if failed else ""))


if __name__ == "__main__":
    main()
