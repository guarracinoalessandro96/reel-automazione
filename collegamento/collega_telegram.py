"""
Collega Telegram: a ogni reel ti arriva sul telefono il video per TikTok (senza musica) + il testo da copiare.

1. Su Telegram apri @BotFather, scrivi /newbot, scegli un nome e un username (finisce con "bot"):
   BotFather ti da' un TOKEN. Copialo (NON incollarlo in chat con Claude: solo qui).
2. Apri il tuo nuovo bot su Telegram e premi AVVIA (o scrivi /start).
3. Lancia questo script e incolla il token quando lo chiede.
Lo script trova da solo la tua chat, ti manda un messaggio di prova, salva tutto in reel-segreti.json
e carica i 2 codici nei Secrets di GitHub (con l'accesso a GitHub gia' salvato su questo PC).
"""
import base64, json, os, subprocess, time
import requests
from nacl import encoding, public

SEGRETI = os.path.join(os.path.expanduser("~"), "reel-segreti.json")
REPO = "guarracinoalessandro96/reel-automazione"


def token_github():
    """L'accesso a GitHub gia' salvato su questo PC (quello che usa git per fare push)."""
    r = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
                       capture_output=True, text=True, timeout=60)
    for riga in r.stdout.splitlines():
        if riga.startswith("password="):
            return riga.split("=", 1)[1]
    return input("Token GitHub (non trovato sul PC): ").strip()


def carica_secrets(valori):
    pat = token_github()
    h = {"Authorization": f"Bearer {pat}", "Accept": "application/vnd.github+json"}
    key = requests.get(f"https://api.github.com/repos/{REPO}/actions/secrets/public-key", headers=h).json()
    if "key" not in key:
        print("GitHub: accesso non riuscito:", key.get("message"))
        return False
    box = public.SealedBox(public.PublicKey(key["key"].encode(), encoding.Base64Encoder()))
    ok = True
    for name, value in valori.items():
        enc = base64.b64encode(box.encrypt(str(value).encode())).decode()
        r = requests.put(f"https://api.github.com/repos/{REPO}/actions/secrets/{name}", headers=h,
                         json={"encrypted_value": enc, "key_id": key["key_id"]})
        print(("OK   " if r.status_code in (201, 204) else "ERR  ") + name)
        ok = ok and r.status_code in (201, 204)
    return ok


def main():
    tok = input("Token del bot (da BotFather): ").strip()
    me = requests.get(f"https://api.telegram.org/bot{tok}/getMe").json()
    if not me.get("ok"):
        print("Token non valido. Ricontrolla quello che ti ha dato BotFather.")
        return
    print(f"Bot trovato: @{me['result']['username']}. Ora apri il bot su Telegram e premi AVVIA (o scrivi /start)...")
    chat = None
    for _ in range(60):
        up = requests.get(f"https://api.telegram.org/bot{tok}/getUpdates").json().get("result", [])
        for u in reversed(up):
            m = u.get("message") or {}
            if m.get("chat", {}).get("type") == "private":
                chat = m["chat"]["id"]
                break
        if chat:
            break
        time.sleep(3)
    if not chat:
        print("Non ho ricevuto il tuo /start in 3 minuti. Riprova.")
        return
    requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                  data={"chat_id": chat, "text": "Collegato! Da ora ti mando qui ogni reel per TikTok."})
    s = json.load(open(SEGRETI, encoding="utf-8")) if os.path.exists(SEGRETI) else {}
    s.update(TELEGRAM_BOT_TOKEN=tok, TELEGRAM_CHAT_ID=str(chat))
    json.dump(s, open(SEGRETI, "w", encoding="utf-8"), indent=1)
    print("Salvato sul PC. Carico i codici su GitHub...")
    if carica_secrets({"TELEGRAM_BOT_TOKEN": tok, "TELEGRAM_CHAT_ID": str(chat)}):
        print("\nTUTTO FATTO! Controlla Telegram: ti e' arrivato il messaggio di prova.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("ERRORE:", e)
    input("\nPremi Invio per chiudere...")
