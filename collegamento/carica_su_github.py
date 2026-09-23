"""
PASSO 5 - Carica tutti i codici salvati (reel-segreti.json) nei "Secrets" del repository GitHub.
I Secrets sono cifrati: nessuno li puo' leggere, nemmeno se il repository e' pubblico.

Ti chiede: nome del repository (es. alessandro/reel) e un token GitHub (vedi GUIDA, "Fine-grained token"
con permesso "Secrets: Read and write" solo su quel repository).
"""
import base64, json, os
import requests
from nacl import encoding, public

SEGRETI = os.path.join(os.path.expanduser("~"), "reel-segreti.json")


def main():
    s = json.load(open(SEGRETI, encoding="utf-8"))
    repo = input("Repository (utente/nome): ").strip()
    pat = input("Token GitHub: ").strip()
    h = {"Authorization": f"Bearer {pat}", "Accept": "application/vnd.github+json"}
    key = requests.get(f"https://api.github.com/repos/{repo}/actions/secrets/public-key", headers=h).json()
    if "key" not in key:
        print("Errore:", key)
        return
    box = public.SealedBox(public.PublicKey(key["key"].encode(), encoding.Base64Encoder()))
    s["GH_PAT"] = pat          # serve per aggiornare il token TikTok quando cambia
    for name, value in s.items():
        enc = base64.b64encode(box.encrypt(str(value).encode())).decode()
        r = requests.put(f"https://api.github.com/repos/{repo}/actions/secrets/{name}", headers=h,
                         json={"encrypted_value": enc, "key_id": key["key_id"]})
        print(("OK   " if r.status_code in (201, 204) else "ERR  ") + name)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("ERRORE:", e)
    input("\nPremi Invio per chiudere...")
