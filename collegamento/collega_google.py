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
          "https://www.googleapis.com/auth/youtube.readonly"]


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

    root = cartella("Reel Alessandro")
    s["DRIVE_FOLDER_DA_PUBBLICARE"] = cartella("Da pubblicare", root)
    s["DRIVE_FOLDER_PUBBLICATI"] = cartella("Pubblicati", root)
    s["DRIVE_FOLDER_PRONTI"] = cartella("Pronti", root)

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
