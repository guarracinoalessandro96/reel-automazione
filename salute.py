"""
Controllo della salute (ogni mattina, GitHub Actions).
Oltre ai collegamenti controlla che i reel escano davvero (coda ferma, video che non si montano, scorta citazioni).
Verifica che tutti i collegamenti funzionino. Se qualcosa non va l'esecuzione FALLISCE
e GitHub manda un'email ad Alessandro con il dettaglio: cosi' si sistema prima che i reel smettano di uscire.
"""
import datetime, os, sys
import requests

ENV = os.environ.get
GRAPH = "https://graph.facebook.com/v23.0"
problemi, ok = [], []


def controlla(nome, fn):
    try:
        esito = fn()
        ok.append(f"{nome}: {esito}")
    except Exception as e:
        problemi.append(f"{nome}: {str(e)[:300]}")


def meta():
    t = ENV("META_PAGE_TOKEN")
    ig = requests.get(f"{GRAPH}/{ENV('IG_USER_ID')}", params={"fields": "username", "access_token": t}).json()
    fb = requests.get(f"{GRAPH}/{ENV('FB_PAGE_ID')}", params={"fields": "name", "access_token": t}).json()
    if "username" not in ig:
        raise RuntimeError(f"Instagram non risponde: {ig.get('error', {}).get('message')}")
    if "name" not in fb:
        raise RuntimeError(f"Pagina Facebook non risponde: {fb.get('error', {}).get('message')}")
    info = requests.get(f"{GRAPH}/debug_token", params={"input_token": t, "access_token": t}).json().get("data", {})
    scade = info.get("expires_at") or 0
    if scade and datetime.datetime.fromtimestamp(scade) < datetime.datetime.now() + datetime.timedelta(days=14):
        raise RuntimeError(f"il token Meta scade il {datetime.datetime.fromtimestamp(scade):%d/%m/%Y}: ricollegare Meta")
    return f"@{ig['username']} e Pagina '{fb['name']}' ok, token {'senza scadenza' if not scade else 'valido'}"


def google():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    c = Credentials(None, refresh_token=ENV("GOOGLE_REFRESH_TOKEN"), client_id=ENV("GOOGLE_CLIENT_ID"),
                    client_secret=ENV("GOOGLE_CLIENT_SECRET"), token_uri="https://oauth2.googleapis.com/token")
    d = build("drive", "v3", credentials=c, cache_discovery=False)
    for k in ("DRIVE_FOLDER_DA_PUBBLICARE", "DRIVE_FOLDER_PRONTI"):
        f = d.files().get(fileId=ENV(k), fields="name,trashed").execute()
        if f.get("trashed"):
            raise RuntimeError(f"la cartella Drive '{f['name']}' e' nel cestino")
    quota = d.about().get(fields="storageQuota").execute()["storageQuota"]
    libero = (int(quota.get("limit", 0)) - int(quota.get("usage", 0))) / 1e9 if quota.get("limit") else None
    if libero is not None and libero < 2:
        raise RuntimeError(f"spazio Drive quasi finito: {libero:.1f} GB liberi")
    yt = build("youtube", "v3", credentials=c, cache_discovery=False)
    ch = yt.channels().list(part="snippet", mine=True).execute().get("items", [])
    if not ch:
        raise RuntimeError("nessun canale YouTube collegato")
    return f"Drive ok{f' ({libero:.0f} GB liberi)' if libero is not None else ''}, YouTube '{ch[0]['snippet']['title']}' ok"


def tiktok():
    r = requests.post("https://open.tiktokapis.com/v2/oauth/token/", data={
        "client_key": ENV("TIKTOK_CLIENT_KEY"), "client_secret": ENV("TIKTOK_CLIENT_SECRET"),
        "grant_type": "refresh_token", "refresh_token": ENV("TIKTOK_REFRESH_TOKEN")}).json()
    if "access_token" not in r:
        raise RuntimeError(f"collegamento TikTok non valido: {r.get('error_description') or r}")
    giorni = r.get("refresh_expires_in", 0) / 86400
    if giorni and giorni < 30:
        raise RuntimeError(f"il collegamento TikTok scade tra {giorni:.0f} giorni: ricollegare TikTok")
    return f"ok (collegamento valido ancora {giorni:.0f} giorni)"


def pubblicazioni():
    """I reel escono davvero? Video fermi in coda, video che non si montano, scorta di citazioni."""
    import json
    here = os.path.dirname(os.path.abspath(__file__))
    st = json.load(open(os.path.join(here, "stato.json"), encoding="utf-8"))
    ora = datetime.datetime.now(datetime.timezone.utc)
    def quando(s):
        d = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)
    ultima = max((quando(h["quando"]) for h in st.get("storico", []) if h.get("quando")), default=None)
    coda = list(st.get("analisi", {}).values())
    fermi = [a for a in coda if a.get("caricato") and (ora - quando(a["caricato"])).total_seconds() > 30 * 3600]
    if fermi and (ultima is None or (ora - ultima).total_seconds() > 30 * 3600):
        raise RuntimeError(f"{len(fermi)} video in coda da oltre 30 ore e nessun reel pubblicato: la pubblicazione e' ferma")
    if ultima and (ora - ultima).total_seconds() > 26 * 3600:   # con l'archivio deve uscire qualcosa ogni giorno
        raise RuntimeError(f"nessun reel pubblicato dal {ultima:%d/%m %H:%M}: la pubblicazione sembra ferma")
    rotti = [a["nome"] for a in coda if a.get("fallimenti")]
    if rotti:
        raise RuntimeError(f"video che non si riescono a montare: {', '.join(rotti)} (vedi anche la cartella 'Da controllare')")
    usate = {h.get("frase") for h in st.get("storico", [])}
    import mie_citazioni                 # citazioni scelte da Alessandro (Google Doc "Le mie citazioni")
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    c = Credentials(None, refresh_token=ENV("GOOGLE_REFRESH_TOKEN"), client_id=ENV("GOOGLE_CLIENT_ID"),
                    client_secret=ENV("GOOGLE_CLIENT_SECRET"), token_uri="https://oauth2.googleapis.com/token")
    api = build("drive", "v3", credentials=c, cache_discovery=False)
    mie = mie_citazioni.frasi(mie_citazioni.leggi(api, ENV("DRIVE_FOLDER_DA_PUBBLICARE")))
    nuove = sum(1 for f in mie if f["id"] not in usate)
    if nuove < 70:     # con 10 reel al giorno e' una settimana di preavviso: poi si riusano le meno recenti
        raise RuntimeError(f"restano solo {nuove} citazioni nuove nel documento 'Le mie citazioni' su Drive: "
                           "aggiungine altre (dopo si ripetono quelle uscite da piu' tempo)")
    giorni = (ora - ultima).days if ultima else None
    return f"{len(coda)} video in coda, ultimo reel {'mai' if giorni is None else f'{giorni} giorni fa'}, {nuove} citazioni nuove nel documento 'Le mie citazioni'"


def main():
    if not ENV("META_PAGE_TOKEN"):
        print("Account non collegati: niente da controllare.")
        return
    controlla("Pubblicazioni", pubblicazioni)
    controlla("Instagram e Facebook", meta)
    controlla("Google Drive e YouTube", google)
    if ENV("TIKTOK_REFRESH_TOKEN"):
        controlla("TikTok", tiktok)
    for r in ok:
        print("OK      ", r)
    for r in problemi:
        print("PROBLEMA", r)
    if problemi:
        print("\nScrivi a Claude: 'il controllo della salute ha trovato un problema' e incolla queste righe.")
        sys.exit(1)
    print("\nTutto a posto.")


if __name__ == "__main__":
    main()
