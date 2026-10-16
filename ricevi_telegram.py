"""
Video mandati da Alessandro al bot Telegram -> cartella Drive "Da pubblicare" (16/10/2026).
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
         "Per mettere video in coda: mandali qui come video normali")

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


def carica_su_drive(token, nome, contenuto, mime):
    confine = uuid.uuid4().hex
    meta = json.dumps({"name": nome, "parents": [ENV("DRIVE_FOLDER_DA_PUBBLICARE")]}).encode()
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
              ["git", "add", "-A", "PAUSA"], ["git", "commit", "-m", "Pausa da Telegram" if attiva else "Ripresa da Telegram"],
              ["git", "pull", "--rebase", "-q"], ["git", "push", "-q"]):
        subprocess.run(c, cwd=QUI, capture_output=True)


def main():
    if not (ENV("TELEGRAM_BOT_TOKEN") and ENV("TELEGRAM_CHAT_ID") and ENV("DRIVE_FOLDER_DA_PUBBLICARE")):
        return
    agg = tg("getUpdates", timeout=0).get("result", [])
    if not agg:
        return
    token, caricati, problemi = None, [], []
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
        f = m.get("video") or (m.get("document") if (m.get("document") or {}).get("mime_type", "").startswith("video/")
                               else None)
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
            carica_su_drive(token, nome, dati, f.get("mime_type") or "video/mp4")
            caricati.append(nome)
        except Exception as e:
            problemi.append(f"un video non e' stato salvato ({str(e)[:120]})")
    tg("getUpdates", offset=agg[-1]["update_id"] + 1, timeout=0)      # messaggi letti: non si rielaborano
    if caricati or problemi:
        righe = ["VIDEO RICEVUTI"] if caricati else ["ATTENZIONE"]
        if caricati:
            righe += [f"{len(caricati)} video messi in coda", "Usciranno nei prossimi orari"]
        righe += problemi
        scrivi("\n".join(righe))
    print(f"Telegram: {len(caricati)} video in coda, {len(problemi)} problemi")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("Telegram: ricezione non riuscita:", e)      # non deve mai bloccare la pubblicazione
