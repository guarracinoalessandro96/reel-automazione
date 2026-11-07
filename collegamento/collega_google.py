"""
PASSO 2 - Collega Google Drive e YouTube (account guarracino.alessandro96@gmail.com).

Prima: scarica da Google Cloud il file delle credenziali OAuth ("client_secret_....json", tipo "App desktop")
e mettilo in questa cartella. Poi doppio clic su "collega_google.bat".
Si apre il browser: fai login con l'account guarracino e clicca "Consenti".
Lo script salva i codici in C:\\Users\\<tu>\\reel-segreti.json (fuori da Drive) e trova da solo le cartelle.
"""
import glob, json, os, sys
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

HERE = os.path.dirname(os.path.abspath(__file__))
SEGRETI = os.path.join(os.path.expanduser("~"), "reel-segreti.json")
SCOPES = ["https://www.googleapis.com/auth/drive",
          "https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.force-ssl",
          "https://www.googleapis.com/auth/youtube.readonly",
          # 25/10/2026: statistiche di visione (quanto guardano, dove smettono): servono all'agente per migliorare
          "https://www.googleapis.com/auth/yt-analytics.readonly"]


def carica():
    return json.load(open(SEGRETI, encoding="utf-8")) if os.path.exists(SEGRETI) else {}


def salva(d):
    json.dump(d, open(SEGRETI, "w", encoding="utf-8"), indent=1)


def main():
    files = glob.glob(os.path.join(HERE, "client_secret*.json"))
    if not files:
        print("Non trovo il file client_secret_....json in questa cartella. Scaricalo da Google Cloud (vedi GUIDA).")
        return
    cfg = json.load(open(files[0], encoding="utf-8"))
    cfg = cfg.get("installed") or cfg.get("web")
    flow = InstalledAppFlow.from_client_secrets_file(files[0], SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline",
                                  success_message="Collegato! Puoi chiudere questa pagina e tornare alla finestra nera.")
    s = carica()
    s.update(GOOGLE_CLIENT_ID=cfg["client_id"], GOOGLE_CLIENT_SECRET=cfg["client_secret"],
             GOOGLE_REFRESH_TOKEN=creds.refresh_token)

    drive = build("drive", "v3", credentials=creds)

    def cartella(nome, parent=None):
        q = f"name = '{nome}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        if parent:
            q += f" and '{parent}' in parents"
        r = drive.files().list(q=q, fields="files(id,name)").execute().get("files", [])
        if r:
            return r[0]["id"]
        body = {"name": nome, "mimeType": "application/vnd.google-apps.folder"}
        if parent:
            body["parents"] = [parent]
        return drive.files().create(body=body, fields="id").execute()["id"]

    # 7/11/2026 (riordino del Drive chiesto da Alessandro): la cartella principale si chiama "0. Reel Alessandro",
    # "Da pubblicare" e' "Video da pubblicare", Pronti e Pubblicati stanno dentro "Sistema (non toccare)". Si cercano
    # con i nomi nuovi e vecchi: le cartelle si creano solo se non ci sono da nessuna parte (prima, dopo il riordino,
    # si sarebbe creato un albero nuovo vuoto e la macchina avrebbe lavorato su cartelle vuote).
    sys.path.insert(0, os.path.dirname(HERE))
    import cartelle

    def elenca(q):
        return drive.files().list(q=q, fields=f"files({cartelle.CAMPI})").execute().get("files", [])

    def crea(nome, dentro):
        return drive.files().create(body={"name": nome, "mimeType": cartelle.CARTELLA, "parents": [dentro]},
                                    fields="id").execute()["id"]
    radici = elenca("(" + " or ".join(f"name = '{n}'" for n in cartelle.nomi(cartelle.PRINCIPALE)) +
                    f") and mimeType = '{cartelle.CARTELLA}' and trashed = false")
    root = cartelle.scegli(radici, cartelle.PRINCIPALE) or cartella(cartelle.PRINCIPALE)
    s["DRIVE_FOLDER_DA_PUBBLICARE"] = cartelle.trova(cartelle.VIDEO, root, elenca, crea)
    s["DRIVE_FOLDER_PUBBLICATI"] = cartelle.trova("Pubblicati", root, elenca, crea)
    s["DRIVE_FOLDER_PRONTI"] = cartelle.trova("Pronti", root, elenca, crea)

    yt = build("youtube", "v3", credentials=creds)
    ch = yt.channels().list(part="snippet", mine=True).execute().get("items", [])
    salva(s)
    print("\nOK! Google collegato.")
    print("Canale YouTube:", ch[0]["snippet"]["title"] if ch else "NESSUN CANALE trovato su questo account!")
    print("Codici salvati in", SEGRETI)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("ERRORE:", e)
    input("\nPremi Invio per chiudere...")
