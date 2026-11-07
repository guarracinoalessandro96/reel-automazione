"""
Video mandati da Alessandro al bot Telegram -> cartella Drive "Da pubblicare" (16/10/2026).
Foto (5/11/2026) -> cartella "Foto della giornata" (foto_giornata.py).
Caricare su Drive dall'iPhone era lento: su Telegram basta condividere i video al bot, l'invio e' velocissimo.
Gira a ogni controllo di GitHub (ogni 10 minuti), prima di tutto il resto. Solo libreria standard.

Limite di Telegram per i bot: file fino a 20 MB. I video mandati "normalmente" (non come file) vengono
compressi da Telegram in HD e stanno quasi sempre sotto; se uno e' troppo grande il bot lo dice.
Accetta solo messaggi dalla chat di Alessandro (TELEGRAM_CHAT_ID).

COMANDI (scritti al bot, maiuscolo o minuscolo, anche con /): STATO, PAUSA, RIPRENDI, AIUTO.
Risposta entro ~10 minuti (al prossimo controllo di GitHub).
"""
import datetime, json, os, subprocess, time, urllib.parse, urllib.request, uuid

QUI = os.path.dirname(os.path.abspath(__file__))
AIUTO = ("COMANDI DEL BOT\n\n"
         "STATO\nquanti video in coda, ultimo e prossimo reel\n\n"
         "PAUSA\nferma le pubblicazioni\n\n"
         "RIPRENDI\nriparte con le pubblicazioni\n\n"
         "Per mettere video in coda: mandali qui come video normali\n\n"
         "FOTO\nmandale qui come FILE (graffetta > File): diventano i reel con le foto delle 12 e delle 18\n\n"
         "MOMENTO\nse sotto il video scrivi cosa sta succedendo (es. 'Roccaraso oggi, 500 persone in fila'), "
         "esce al prossimo orario con il tuo titolo e il suono vero")

ENV = os.environ.get
LIMITE = 20 * 1024 * 1024


def tg(metodo, **param):
    url = f"https://api.telegram.org/bot{ENV('TELEGRAM_BOT_TOKEN')}/{metodo}"
    dati = urllib.parse.urlencode(param).encode() if param else None
    return json.load(urllib.request.urlopen(url, dati, timeout=60))


def scrivi(testo):
    try:
        tg("sendMessage", chat_id=ENV("TELEGRAM_CHAT_ID"), text=testo)
    except Exception:
        pass


def token_google():
    dati = urllib.parse.urlencode({"client_id": ENV("GOOGLE_CLIENT_ID"), "client_secret": ENV("GOOGLE_CLIENT_SECRET"),
                                   "refresh_token": ENV("GOOGLE_REFRESH_TOKEN"), "grant_type": "refresh_token"}).encode()
    return json.load(urllib.request.urlopen("https://oauth2.googleapis.com/token", dati, timeout=30))["access_token"]


def cartella_foto(token):
    """La cartella Drive delle foto (foto_giornata.py): "Foto da pubblicare", prima "Foto della giornata".
    7/11/2026 (riordino del Drive chiesto da Alessandro): si cerca con tutti e due i nomi nella cartella che contiene
    "Video da pubblicare" (e dentro "Sistema (non toccare)", cartelle.py); se li' non c'e', in tutto il Drive come
    prima. Mai creata: se non c'e' da nessuna parte, errore (la foto va rimandata)."""
    import cartelle
    H = {"Authorization": "Bearer " + token}

    def elenca(q):
        url = "https://www.googleapis.com/drive/v3/files?" + urllib.parse.urlencode({"q": q, "fields": f"files({cartelle.CAMPI})"})
        return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=30)).get("files", [])
    try:
        url = f"https://www.googleapis.com/drive/v3/files/{ENV('DRIVE_FOLDER_DA_PUBBLICARE')}?fields=parents"
        padre = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=30))["parents"][0]
        trovata = cartelle.trova(cartelle.FOTO, padre, elenca, avvisa=None)
        if trovata:
            return trovata
    except Exception as e:
        print("Foto: ricerca accanto a 'Video da pubblicare' non riuscita, cerco in tutto il Drive:", e)
    nomi = " or ".join(f"name = '{n}'" for n in cartelle.nomi(cartelle.FOTO))
    trovata = cartelle.scegli(elenca(f"({nomi}) and mimeType = '{cartelle.CARTELLA}' and trashed = false"),
                              cartelle.FOTO, None)
    if not trovata:
        raise RuntimeError(f"cartella '{cartelle.FOTO}' non trovata su Drive")
    return trovata


def carica_su_drive(token, nome, contenuto, mime, titolo="", cartella=None):
    """titolo = la scritta sotto il video su Telegram: il video diventa un MOMENTO (pubblica.monta_momento)."""
    confine = uuid.uuid4().hex
    dati_file = {"name": nome, "parents": [cartella or ENV("DRIVE_FOLDER_DA_PUBBLICARE")]}
    if titolo:
        dati_file.update(description=titolo, appProperties={"momento": "1"})
    meta = json.dumps(dati_file).encode()
    corpo = (f"--{confine}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode() + meta +
             f"\r\n--{confine}\r\nContent-Type: {mime}\r\n\r\n".encode() + contenuto + f"\r\n--{confine}--".encode())
    req = urllib.request.Request("https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id",
                                 data=corpo, headers={"Authorization": "Bearer " + token,
                                                      "Content-Type": f"multipart/related; boundary={confine}"})
    return json.load(urllib.request.urlopen(req, timeout=300))["id"]


def video_in_coda(token):
    q = f"'{ENV('DRIVE_FOLDER_DA_PUBBLICARE')}' in parents and trashed = false and mimeType contains 'video/'"
    url = "https://www.googleapis.com/drive/v3/files?" + urllib.parse.urlencode({"q": q, "fields": "files(id)",
                                                                               "pageSize": 200})
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
    return len(json.load(urllib.request.urlopen(req, timeout=30)).get("files", []))


def testo_stato(token):
    import orario
    st = json.load(open(os.path.join(QUI, "stato.json"), encoding="utf-8"))
    ultimi = [h for h in st.get("storico", []) if h.get("slot") and not h.get("in_corso")]
    righe = ["STATO DEL SISTEMA", "In pausa" if os.path.exists(os.path.join(QUI, "PAUSA")) else "Attivo", ""]
    righe += ["VIDEO NUOVI IN CODA", str(video_in_coda(token)), ""]
    try:                         # 5/11/2026: anche le foto per i reel delle 12 e delle 18
        q = (f"'{cartella_foto(token)}' in parents and trashed = false and mimeType contains 'image/' "
             "and not appProperties has { key='usata' and value='1' }")
        url = "https://www.googleapis.com/drive/v3/files?" + urllib.parse.urlencode({"q": q, "fields": "files(id)",
                                                                                   "pageSize": 1000})
        req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
        righe += ["FOTO DA USARE", str(len(json.load(urllib.request.urlopen(req, timeout=30)).get("files", []))), ""]
    except Exception:
        pass
    if ultimi:
        h = ultimi[-1]
        esiti = ", ".join(f"{p} {'ok' if r.get('ok') else 'ERRORE'}" for p, r in h.get("risultati", {}).items())
        righe += ["ULTIMO REEL", h["slot"], esiti, ""]
    from zoneinfo import ZoneInfo
    adesso = datetime.datetime.now(ZoneInfo("Europe/Rome"))
    prossimi = [f"{o:02d}:{m:02d}" for o, m, _ in orario.SLOTS if (o, m) > (adesso.hour, adesso.minute)]
    righe += ["PROSSIMO REEL", prossimi[0] if prossimi else f"domani alle {orario.SLOTS[0][0]:02d}:{orario.SLOTS[0][1]:02d}"]
    return "\n".join(righe)


def pausa(attiva):
    """Crea o toglie il file PAUSA nel repository (solo su GitHub)."""
    f = os.path.join(QUI, "PAUSA")
    if attiva == os.path.exists(f) or not ENV("GITHUB_ACTIONS"):
        return
    if attiva:
        open(f, "w").write("Pausa chiesta su Telegram\n")
    else:
        os.remove(f)
    for c in (["git", "config", "user.name", "reel-bot"], ["git", "config", "user.email", "reel-bot@users.noreply.github.com"],
              ["git", "add", "-A", "PAUSA"], ["git", "commit", "-m", "Pausa da Telegram" if attiva else "Ripresa da Telegram"]):
        subprocess.run(c, cwd=QUI, capture_output=True)
    for i in range(5):          # 18/10/2026: con un reel ogni ora i push sono tanti, uno puo' arrivare insieme
        if (subprocess.run(["git", "pull", "--rebase", "-q"], cwd=QUI, capture_output=True).returncode == 0
                and subprocess.run(["git", "push", "-q"], cwd=QUI, capture_output=True).returncode == 0):
            return
        subprocess.run(["git", "rebase", "--abort"], cwd=QUI, capture_output=True)
        time.sleep(5 * (i + 1))
    raise RuntimeError("non sono riuscito a salvare su GitHub, riprova tra qualche minuto")


def main():
    if not (ENV("TELEGRAM_BOT_TOKEN") and ENV("TELEGRAM_CHAT_ID") and ENV("DRIVE_FOLDER_DA_PUBBLICARE")):
        return
    agg = tg("getUpdates", timeout=0).get("result", [])
    if not agg:
        return
    token, caricati, problemi, momenti, foto_salvate, cartella_f = None, [], [], [], [], None
    for u in agg:
        m = u.get("message") or {}
        if str(m.get("chat", {}).get("id")) != str(ENV("TELEGRAM_CHAT_ID")):
            continue
        comando = (m.get("text") or "").strip().lstrip("/").split(" ")[0].lower()
        if comando in ("stato", "pausa", "riprendi", "aiuto", "start", "help"):
            try:
                if comando == "pausa":
                    pausa(True)
                    scrivi("PAUSA ATTIVA\nNessun reel uscira' finche' non scrivi RIPRENDI")
                elif comando == "riprendi":
                    pausa(False)
                    scrivi("RIPARTITO\nI reel tornano a uscire agli orari normali")
                elif comando == "stato":
                    token = token or token_google()
                    scrivi(testo_stato(token))
                else:
                    scrivi(AIUTO)
            except Exception as e:
                scrivi(f"ATTENZIONE\nComando non riuscito: {str(e)[:150]}")
            continue
        # 5/11/2026: anche le FOTO mandate al bot vanno nei reel con le foto (cartella "Foto della giornata").
        # Meglio mandarle "come file": cosi' Telegram non le comprime e resta la data dello scatto.
        doc = m.get("document") or {}
        foto = (m.get("photo") or [None])[-1] or (doc if doc.get("mime_type", "").startswith("image/") else None)
        if foto:
            try:
                path = tg("getFile", file_id=foto["file_id"])["result"]["file_path"]
                dati = urllib.request.urlopen(f"https://api.telegram.org/file/bot{ENV('TELEGRAM_BOT_TOKEN')}/{path}",
                                              timeout=300).read()
                token = token or token_google()
                cartella_f = cartella_f or cartella_foto(token)
                est = os.path.splitext(foto.get("file_name") or path)[1] or ".jpg"
                nome = f"TG_{time.strftime('%Y%m%d_%H%M%S', time.gmtime(m.get('date', time.time())))}_{m['message_id']}{est}"
                carica_su_drive(token, nome, dati, foto.get("mime_type") or "image/jpeg", cartella=cartella_f)
                foto_salvate.append(nome)
            except Exception as e:
                problemi.append(f"una foto non e' stata salvata ({str(e)[:120]})")
            continue
        f = m.get("video") or (doc if doc.get("mime_type", "").startswith("video/") else None)
        if not f:
            continue
        if f.get("file_size", 0) > LIMITE:
            problemi.append("un video supera 20 MB: rimandalo come video normale (non come file)")
            continue
        try:
            path = tg("getFile", file_id=f["file_id"])["result"]["file_path"]
            dati = urllib.request.urlopen(f"https://api.telegram.org/file/bot{ENV('TELEGRAM_BOT_TOKEN')}/{path}",
                                          timeout=300).read()
            token = token or token_google()
            est = os.path.splitext(f.get("file_name") or path)[1] or ".mp4"
            nome = f"TG_{time.strftime('%Y%m%d_%H%M%S', time.gmtime(m.get('date', time.time())))}_{m['message_id']}{est}"
            titolo = " ".join((m.get("caption") or "").split())
            carica_su_drive(token, nome, dati, f.get("mime_type") or "video/mp4", titolo)
            caricati.append(nome)
            if titolo:
                momenti.append(titolo)
        except Exception as e:
            problemi.append(f"un video non e' stato salvato ({str(e)[:120]})")
    tg("getUpdates", offset=agg[-1]["update_id"] + 1, timeout=0)      # messaggi letti: non si rielaborano
    if caricati or problemi:
        righe = ["VIDEO RICEVUTI"] if caricati else ["ATTENZIONE"]
        if caricati:
            righe += [f"{len(caricati)} video messi in coda", "Usciranno nei prossimi orari"]
        for t in momenti:
            righe += ["", "MOMENTO", "Esce al prossimo orario con il tuo titolo:", t]
        righe += problemi
        scrivi("\n".join(righe))
    print(f"Telegram: {len(caricati)} video in coda, {len(foto_salvate)} foto, {len(problemi)} problemi")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("Telegram: ricezione non riuscita:", e)      # non deve mai bloccare la pubblicazione
