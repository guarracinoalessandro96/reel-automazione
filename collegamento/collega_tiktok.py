"""
PASSO 4 - Collega TikTok.

Ti chiede Client key e Client secret della tua app su developers.tiktok.com e l'indirizzo della
pagina "callback" del sito (https://<utente>.github.io/<repo>/callback.html, vedi GUIDA).
Si apre il browser: fai login su TikTok e autorizza. La pagina callback ti mostra un codice: copialo qui.
"""
import json, os, secrets, urllib.parse, webbrowser
import requests

SEGRETI = os.path.join(os.path.expanduser("~"), "reel-segreti.json")
SCOPES = "user.info.basic,video.upload,video.publish"


def main():
    key = input("Client key: ").strip()
    secret = input("Client secret: ").strip()
    redirect = input("Indirizzo callback (https://...github.io/.../callback.html): ").strip()
    state = secrets.token_urlsafe(8)
    url = "https://www.tiktok.com/v2/auth/authorize/?" + urllib.parse.urlencode({
        "client_key": key, "scope": SCOPES, "response_type": "code", "redirect_uri": redirect, "state": state})
    print("\nSi apre il browser. Se non si apre, copia questo indirizzo:\n", url)
    webbrowser.open(url)
    code = urllib.parse.unquote(input("\nIncolla il codice mostrato dalla pagina: ").strip())

    r = requests.post("https://open.tiktokapis.com/v2/oauth/token/", data={
        "client_key": key, "client_secret": secret, "code": code, "grant_type": "authorization_code",
        "redirect_uri": redirect}).json()
    if "refresh_token" not in r:
        print("Errore:", r)
        return
    s = json.load(open(SEGRETI, encoding="utf-8")) if os.path.exists(SEGRETI) else {}
    s.update(TIKTOK_CLIENT_KEY=key, TIKTOK_CLIENT_SECRET=secret, TIKTOK_REFRESH_TOKEN=r["refresh_token"])
    json.dump(s, open(SEGRETI, "w", encoding="utf-8"), indent=1)
    me = requests.get("https://open.tiktokapis.com/v2/user/info/?fields=display_name",
                      headers={"Authorization": f"Bearer {r['access_token']}"}).json()
    print("\nOK! TikTok collegato:", me.get("data", {}).get("user", {}).get("display_name"))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("ERRORE:", e)
    input("\nPremi Invio per chiudere...")
