"""
TikTok Publisher: piccolo programma locale per pubblicare i reel su TikTok rispettando le regole di TikTok
(Content Posting API): l'utente vede il proprio profilo, l'anteprima del video, sceglie la privacy e le
interazioni, dichiara i contenuti commerciali, accetta le regole e SOLO ALLORA pubblica.

- L'interfaccia e' sul sito: https://guarracinoalessandro96.github.io/reel-automazione/app/
- Questo programma gira sul PC (http://localhost:8765) e parla con TikTok usando le chiavi salvate
  in C:\\Users\\<utente>\\reel-segreti.json (mai inviate al sito).
Avvio: doppio clic su "Apri TikTok Publisher.bat".
"""
import json, os, re, secrets, sys, threading, urllib.parse, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import requests

PORT = 8765
SITE = "https://guarracinoalessandro96.github.io"
APP_URL = SITE + "/reel-automazione/app/"
REDIRECT = SITE + "/reel-automazione/callback/"
SEGRETI = os.path.join(os.path.expanduser("~"), "reel-segreti.json")
HERE = os.path.dirname(os.path.abspath(__file__))
FRASI = os.path.join(os.path.dirname(HERE), "frasi.json")
_args = [a for a in sys.argv[1:] if not a.startswith("--")]
PRONTI = _args[0] if _args else r"H:\Il mio Drive\Reel Alessandro\Pronti"
SCOPES = "user.info.basic,video.upload,video.publish"
API = "https://open.tiktokapis.com"

S = {"state": None, "token": None}      # sessione (solo in memoria)


def segreti():
    return json.load(open(SEGRETI, encoding="utf-8"))


def salva_refresh(rt):
    s = segreti()
    if rt and rt != s.get("TIKTOK_REFRESH_TOKEN"):
        s["TIKTOK_REFRESH_TOKEN"] = rt
        json.dump(s, open(SEGRETI, "w", encoding="utf-8"), indent=1)


def tk(method, path, **kw):
    h = {"Authorization": f"Bearer {S['token']}", "Content-Type": "application/json; charset=UTF-8"}
    return requests.request(method, API + path, headers=h, timeout=60, **kw).json()


def creator():
    me = tk("GET", "/v2/user/info/?fields=display_name,avatar_url")
    ci = tk("POST", "/v2/post/publish/creator_info/query/")
    d = ci.get("data", {})
    return {"display_name": me.get("data", {}).get("user", {}).get("display_name"),
            "avatar_url": d.get("creator_avatar_url") or me.get("data", {}).get("user", {}).get("avatar_url"),
            "nickname": d.get("creator_nickname"), "username": d.get("creator_username"),
            "privacy_options": d.get("privacy_level_options", []),
            "comment_disabled": d.get("comment_disabled", False), "duet_disabled": d.get("duet_disabled", False),
            "stitch_disabled": d.get("stitch_disabled", False),
            "max_duration": d.get("max_video_post_duration_sec", 60), "error": ci.get("error", {})}


def reels():
    frasi = {f["id"]: f for f in json.load(open(FRASI, encoding="utf-8"))} if os.path.exists(FRASI) else {}
    out = []
    if os.path.isdir(PRONTI):
        files = sorted((f for f in os.listdir(PRONTI) if f.lower().endswith(".mp4")),
                       key=lambda f: os.path.getmtime(os.path.join(PRONTI, f)), reverse=True)
        for f in files[:30]:
            fr = frasi.get(f.split(" - ")[0], {})
            cap = (fr.get("gancio", "") + "\n\n" + " ".join(fr.get("hashtag", [])[:4])).strip()
            out.append({"file": f, "caption": cap})
    return out


def publish(p):
    path = os.path.join(PRONTI, os.path.basename(p["file"]))
    size = os.path.getsize(path)
    post = {"title": p.get("title", "")[:2200], "privacy_level": p["privacy"],
            "disable_comment": not p.get("comment"), "disable_duet": not p.get("duet"),
            "disable_stitch": not p.get("stitch"), "video_cover_timestamp_ms": 1000,
            "brand_content_toggle": bool(p.get("branded")), "brand_organic_toggle": bool(p.get("your_brand"))}
    init = tk("POST", "/v2/post/publish/video/init/", json={
        "post_info": post,
        "source_info": {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": size, "total_chunk_count": 1}})
    d = init.get("data", {})
    if "upload_url" not in d:
        return {"ok": False, "error": init.get("error", {})}
    with open(path, "rb") as f:
        up = requests.put(d["upload_url"], data=f, timeout=600,
                          headers={"Content-Type": "video/mp4", "Content-Length": str(size),
                                   "Content-Range": f"bytes 0-{size - 1}/{size}"})
    if up.status_code >= 300:
        return {"ok": False, "error": {"message": up.text[:300]}}
    return {"ok": True, "publish_id": d["publish_id"]}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def cors(self):
        origin = self.headers.get("Origin", "")
        if origin in (SITE, f"http://localhost:{PORT}"):
            self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Vary", "Origin")

    def out(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.cors()
        self.end_headers()

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        try:
            if u.path == "/api/status":
                if not S["token"]:
                    return self.out({"logged_in": False})
                return self.out({"logged_in": True, "creator": creator()})
            if u.path == "/api/login_url":
                s = segreti()
                S["state"] = "local-" + secrets.token_urlsafe(8)
                url = "https://www.tiktok.com/v2/auth/authorize/?" + urllib.parse.urlencode({
                    "client_key": s["TIKTOK_CLIENT_KEY"], "scope": SCOPES, "response_type": "code",
                    "redirect_uri": REDIRECT, "state": S["state"]})
                return self.out({"url": url})
            if u.path == "/callback":
                if q.get("state") != S["state"] or "code" not in q:
                    return self.out({"error": "login non valido, riprova"}, 400)
                s = segreti()
                r = requests.post(API + "/v2/oauth/token/", data={
                    "client_key": s["TIKTOK_CLIENT_KEY"], "client_secret": s["TIKTOK_CLIENT_SECRET"],
                    "code": urllib.parse.unquote(q["code"]), "grant_type": "authorization_code",
                    "redirect_uri": REDIRECT}, timeout=60).json()
                if "access_token" not in r:
                    return self.out({"error": r}, 400)
                S["token"] = r["access_token"]
                salva_refresh(r.get("refresh_token"))
                self.send_response(302)
                self.send_header("Location", APP_URL)
                self.end_headers()
                return
            if u.path == "/api/logout":
                S["token"] = None
                return self.out({"ok": True})
            if u.path == "/api/reels":
                return self.out(reels())
            if u.path == "/api/publish_status":
                st = tk("POST", "/v2/post/publish/status/fetch/", json={"publish_id": q.get("id")})
                return self.out(st.get("data", {}) or {"error": st.get("error")})
            if u.path.startswith("/video/"):
                name = os.path.basename(urllib.parse.unquote(u.path[len("/video/"):]))
                path = os.path.join(PRONTI, name)
                if not os.path.exists(path):
                    return self.out({"error": "file non trovato"}, 404)
                size = os.path.getsize(path)
                start, end = 0, size - 1
                m = re.match(r"bytes=(\d+)-(\d*)", self.headers.get("Range", ""))
                if m:
                    start = int(m.group(1))
                    end = int(m.group(2)) if m.group(2) else size - 1
                self.send_response(206 if m else 200)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Length", str(end - start + 1))
                if m:
                    self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.cors()
                self.end_headers()
                with open(path, "rb") as f:
                    f.seek(start)
                    self.wfile.write(f.read(end - start + 1))
                return
            self.out({"error": "non trovato"}, 404)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            self.out({"error": str(e)[:300]}, 500)

    def do_POST(self):
        try:
            data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)) or 0) or b"{}")
            if self.path == "/api/publish":
                if not S["token"]:
                    return self.out({"ok": False, "error": {"message": "non collegato"}}, 401)
                return self.out(publish(data))
            self.out({"error": "non trovato"}, 404)
        except Exception as e:
            self.out({"ok": False, "error": {"message": str(e)[:300]}}, 500)


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print(f"TikTok Publisher attivo su http://localhost:{PORT}")
    print("Cartella dei reel:", PRONTI)
    print("Lascia aperta questa finestra mentre usi la pagina. Per chiudere: Ctrl+C.")
    if "--no-browser" not in sys.argv:
        threading.Timer(1.0, lambda: webbrowser.open(APP_URL)).start()
    srv.serve_forever()


if __name__ == "__main__":
    main()
