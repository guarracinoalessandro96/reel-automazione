"""
Pubblicazione automatica di un Reel (gira su GitHub Actions alle 9, 12, 15, 18, 21 ora italiana).

Ad ogni esecuzione:
  0. riprova le piattaforme fallite nelle esecuzioni precedenti (max 3 tentativi)
  1. prende il video piu' vecchio dalla cartella Drive "Da pubblicare"
  2. prende la prossima caption della coda (captions.json, gia' in ordine di calendario)
  3. mette il gancio sul video senza coprire il viso (overlay.py)
  4. pubblica su Instagram, Facebook, YouTube Shorts, TikTok + primo commento dove possibile
  5. archivia su Drive e aggiorna stato.json

Ogni piattaforma e' indipendente: se una fallisce, le altre pubblicano comunque.
Credenziali: variabili d'ambiente (GitHub Secrets). DRY_RUN=1 fa tutto tranne pubblicare.
"""
import io, json, os, sys, time, datetime, traceback, subprocess, shutil
import requests
import overlay

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTIONS = os.path.join(HERE, "captions.json")
STATE = os.path.join(HERE, "stato.json")
GRAPH = "https://graph.facebook.com/v23.0"
ENV = os.environ.get
DRY = ENV("DRY_RUN") == "1"
PLATFORMS = ["instagram", "facebook", "youtube", "tiktok"]
MAX_TENTATIVI = 3


# Umore della musica per ogni tema (cartelle in musica/, create da genera_musica.py)
MOOD = {"Disciplina e costanza": "deciso", "Lavoro e ambizione": "deciso", "Le persone giuste": "caldo",
        "Famiglia e gratitudine": "caldo", "I 30 anni": "luminoso", "Salute e cura di sé": "calmo",
        "Ripartire con energia": "luminoso", "Soldi e libertà": "caldo", "Stare bene con sé stessi": "calmo",
        "Positività ed energia": "luminoso", "Daily habits": "calmo"}


def scegli_musica(tema, recenti):
    """Un brano dell'umore giusto, evitando quelli usati di recente (cosi' non si ripete nei video vicini)."""
    import random
    d = os.path.join(HERE, "musica", MOOD.get(tema, "luminoso"))
    if not os.path.isdir(d):
        return None
    brani = sorted(f for f in os.listdir(d) if f.endswith(".flac"))
    if not brani:
        return None
    liberi = [b for b in brani if b not in recenti] or brani
    return os.path.join(d, random.choice(liberi))


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

    def next_video(self):
        if self.local:
            vids = sorted(f for f in os.listdir(os.path.join(self.local, "Da pubblicare"))
                          if f.lower().endswith((".mov", ".mp4", ".m4v")))
            return {"id": vids[0], "name": vids[0]} if vids else None
        q = (f"'{ENV('DRIVE_FOLDER_DA_PUBBLICARE')}' in parents and trashed = false "
             "and mimeType contains 'video/'")
        res = self.api.files().list(q=q, orderBy="createdTime", pageSize=1, fields="files(id,name)").execute()
        files = res.get("files", [])
        return files[0] if files else None

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

    def archive(self, file_id, final_path, final_name):
        """Sposta l'originale in Pubblicati e carica il montato in Pronti. Restituisce l'id del montato."""
        if self.local:
            for d in ("Pubblicati", "Pronti"):
                os.makedirs(os.path.join(self.local, d), exist_ok=True)
            shutil.move(os.path.join(self.local, "Da pubblicare", file_id), os.path.join(self.local, "Pubblicati", file_id))
            shutil.copy(final_path, os.path.join(self.local, "Pronti", final_name))
            return final_name
        from googleapiclient.http import MediaFileUpload
        self.api.files().update(fileId=file_id, addParents=ENV("DRIVE_FOLDER_PUBBLICATI"),
                                removeParents=ENV("DRIVE_FOLDER_DA_PUBBLICARE"), fields="id").execute()
        f = self.api.files().create(body={"name": final_name, "parents": [ENV("DRIVE_FOLDER_PRONTI")]},
                                    media_body=MediaFileUpload(final_path, mimetype="video/mp4"),
                                    fields="id").execute()
        return f["id"]


def youtube_upload(creds, path, cap):
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    title = cap["gancio"]
    if len(title) > 90:
        title = title[:87].rsplit(" ", 1)[0] + "..."
    privacy = ENV("YOUTUBE_PRIVACY") or "public"
    body = {"snippet": {"title": title + " #shorts", "description": cap["descrizione"], "categoryId": "22",
                        "defaultLanguage": "it", "defaultAudioLanguage": "it"},
            "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}}
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(path, mimetype="video/mp4", resumable=True))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    vid = resp["id"]
    if cap.get("commento") and privacy == "public":
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


def instagram_upload(path, cap):
    token, ig = ENV("META_PAGE_TOKEN"), ENV("IG_USER_ID")
    r = requests.post(f"{GRAPH}/{ig}/media", data={"media_type": "REELS", "upload_type": "resumable",
                                                     "caption": cap["descrizione"], "share_to_feed": "true",
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
    if cap.get("commento"):
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
                              "description": cap["descrizione"], "access_token": token}).json()
    if not fin.get("success"):
        raise RuntimeError(fin)
    if cap.get("commento"):
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
    """TikTok non permette commenti via API: la domanda resta in fondo alla descrizione."""
    token = tiktok_token()
    size = os.path.getsize(path)
    init = requests.post("https://open.tiktokapis.com/v2/post/publish/video/init/",
                         headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"},
                         json={"post_info": {"title": cap["descrizione"][:2200],
                                             "privacy_level": ENV("TIKTOK_PRIVACY", "SELF_ONLY"),
                                             "disable_comment": False, "disable_duet": False,
                                             "disable_stitch": False, "video_cover_timestamp_ms": 1000},
                               "source_info": {"source": "FILE_UPLOAD", "video_size": size,
                                               "chunk_size": size, "total_chunk_count": 1}}).json()
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


def main():
    slot = sys.argv[1] if len(sys.argv) > 1 else "manuale"
    captions = json.load(open(CAPTIONS, encoding="utf-8"))
    by_id = {c["id"]: c for c in captions}
    state = json.load(open(STATE, encoding="utf-8")) if os.path.exists(STATE) else {}
    for k, v in (("usate", []), ("storico", []), ("riprova", []), ("slot_fatti", []), ("musica_recenti", [])):
        state.setdefault(k, v)

    def save():
        json.dump(state, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)

    if not ENV("DRY_RUN") == "1" and not ENV("GOOGLE_REFRESH_TOKEN"):
        print("Account non ancora collegati (Secrets mancanti): niente da fare.")
        return
    creds = None if DRY else google_creds()
    drive = Drive(creds)
    work = os.path.join(HERE, "_lavoro")
    os.makedirs(work, exist_ok=True)

    # 0. nuovi tentativi per le piattaforme fallite
    for job in list(state["riprova"]):
        cap = by_id[job["caption"]]
        path = os.path.join(work, "riprova.mp4")
        try:
            drive.download(job["pronti_id"], path, folder="Pronti")
        except Exception as e:
            log("riprova: download fallito", e)
            continue
        res = publish_all(path, cap, creds, job["piattaforme"])
        job["tentativi"] += 1
        job["piattaforme"] = [p for p, r in res.items() if not r["ok"]]
        state["storico"].append({"quando": datetime.datetime.now().isoformat(timespec="minutes"),
                                 "riprova": job["caption"], "risultati": res})
        if not job["piattaforme"] or job["tentativi"] >= MAX_TENTATIVI:
            state["riprova"].remove(job)
        save()

    # 1-5. nuovo reel
    cap = next((c for c in captions if c["id"] not in state["usate"]), None)
    if cap is None:
        log("Caption finite: aggiungere nuove caption a captions.json.")
        return
    video = drive.next_video()
    if video is None:
        log("Nessun video in coda: niente da pubblicare in questo slot.")
        return
    log(f"Slot {slot} | video {video['name']} | caption {cap['id']} ({cap['tema']})")

    src = os.path.join(work, "originale" + os.path.splitext(video["name"])[1])
    out = os.path.join(work, "reel.mp4")
    drive.download(video["id"], src)
    music = None if ENV("SENZA_MUSICA") == "1" else scegli_musica(cap["tema"], state["musica_recenti"])
    info = overlay.make_video(src, cap["gancio"], out, preview=os.path.join(work, "anteprima.jpg"), music=music,
                              colore=ENV("SENZA_COLORE") != "1", nome=video["name"])
    log("Montato:", info)

    results = publish_all(out, cap, creds, attive())
    if not any(r["ok"] for r in results.values()):
        log("Nessuna piattaforma ha funzionato: il video resta in coda per il prossimo slot.")
        sys.exit(1)

    pronti_id = drive.archive(video["id"], out, f"{cap['id']} - {os.path.splitext(video['name'])[0]}.mp4")
    failed = [p for p, r in results.items() if not r["ok"]]
    if failed:
        state["riprova"].append({"caption": cap["id"], "pronti_id": pronti_id, "piattaforme": failed, "tentativi": 0})
    state["usate"].append(cap["id"])
    if info.get("musica"):
        state["musica_recenti"] = (state["musica_recenti"] + [info["musica"]])[-8:]
    state["slot_fatti"].append(slot)
    state["slot_fatti"] = state["slot_fatti"][-60:]
    state["storico"].append({"quando": datetime.datetime.now().isoformat(timespec="minutes"), "slot": slot,
                             "video": video["name"], "caption": cap["id"], "montaggio": info, "risultati": results})
    save()
    shutil.rmtree(work, ignore_errors=True)
    log("Fatto." + (f" Da riprovare: {failed}" if failed else ""))


if __name__ == "__main__":
    main()
