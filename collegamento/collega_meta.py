"""
PASSO 3 - Collega Instagram e la Pagina Facebook.

Ti chiede 3 cose che trovi su developers.facebook.com (vedi GUIDA):
  - ID app e Chiave segreta app  (App > Impostazioni > Di base)
  - un token utente preso da "Graph API Explorer" con i permessi indicati nella guida
Lo script lo trasforma in un token di Pagina che NON scade, e trova da solo gli ID di Pagina e Instagram.
"""
import json, os
import requests

GRAPH = "https://graph.facebook.com/v23.0"
SEGRETI = os.path.join(os.path.expanduser("~"), "reel-segreti.json")


def main():
    app_id = input("ID app: ").strip()
    app_secret = input("Chiave segreta app: ").strip()
    short = input("Token utente (da Graph API Explorer): ").strip()

    r = requests.get(f"{GRAPH}/oauth/access_token", params={
        "grant_type": "fb_exchange_token", "client_id": app_id, "client_secret": app_secret,
        "fb_exchange_token": short}).json()
    if "access_token" not in r:
        print("Errore nello scambio del token:", r)
        return
    long_user = r["access_token"]

    pages = requests.get(f"{GRAPH}/me/accounts", params={"access_token": long_user,
                                                          "fields": "id,name,access_token,instagram_business_account"}).json()
    pages = pages.get("data", [])
    if not pages:
        print("Nessuna Pagina trovata. Hai selezionato la Pagina quando hai concesso i permessi?")
        return
    for i, p in enumerate(pages):
        print(f"  {i + 1}. {p['name']}  (Instagram collegato: {'si' if p.get('instagram_business_account') else 'NO'})")
    n = int(input("Numero della tua Pagina: ") or "1") - 1
    page = pages[n]
    ig = (page.get("instagram_business_account") or {}).get("id")
    if not ig:
        print("Questa Pagina non ha un profilo Instagram professionale collegato. Collegalo e riprova.")
        return

    dbg = requests.get(f"{GRAPH}/debug_token", params={"input_token": page["access_token"],
                                                        "access_token": f"{app_id}|{app_secret}"}).json()
    scade = dbg.get("data", {}).get("expires_at")

    s = json.load(open(SEGRETI, encoding="utf-8")) if os.path.exists(SEGRETI) else {}
    s.update(META_PAGE_TOKEN=page["access_token"], FB_PAGE_ID=page["id"], IG_USER_ID=ig)
    json.dump(s, open(SEGRETI, "w", encoding="utf-8"), indent=1)
    info = requests.get(f"{GRAPH}/{ig}", params={"fields": "username,followers_count",
                                                  "access_token": page["access_token"]}).json()
    print(f"\nOK! Pagina '{page['name']}' e Instagram @{info.get('username')} collegati.")
    print("Scadenza token:", "mai" if not scade else scade)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("ERRORE:", e)
    input("\nPremi Invio per chiudere...")
