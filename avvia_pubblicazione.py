"""
Sveglia dal PC (ogni ora, attivita' "Reel Alessandro - avvio pubblicazione" dell'Utilita' di pianificazione):
chiede a GitHub di fare SUBITO il controllo di pubblicazione, perche' le esecuzioni programmate di GitHub a volte
ritardano. E' un controllo normale (forza = false): pubblica solo se e' l'ora giusta.

Dal 20/10/2026 non tocca piu' la cartella del progetto (niente pull/commit/push): il 19/10 un pull automatico si era
bloccato a meta' e da allora la sveglia non funzionava piu' (e poteva interferire con le modifiche in corso).
Usa il collegamento a GitHub gia' salvato sul PC (git credential), lo stesso di git push. Registro in avvia_log.txt.
"""
import datetime, os, subprocess
import requests

REPO = "guarracinoalessandro96/reel-automazione"
QUI = os.path.dirname(os.path.abspath(__file__))


def token():
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")     # mai finestre di accesso
    r = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n", capture_output=True,
                       text=True, timeout=60, env=env, cwd=QUI)
    for riga in r.stdout.splitlines():
        if riga.startswith("password="):
            return riga.split("=", 1)[1]
    raise RuntimeError("collegamento a GitHub non trovato sul PC")


def avvia():
    r = requests.post(f"https://api.github.com/repos/{REPO}/actions/workflows/pubblica.yml/dispatches",
                      json={"ref": "main", "inputs": {"forza": "false"}}, timeout=30,
                      headers={"Authorization": "Bearer " + token(), "Accept": "application/vnd.github+json"})
    if r.status_code != 204:
        raise RuntimeError(f"GitHub ha risposto {r.status_code}: {r.text[:200]}")


if __name__ == "__main__":
    try:
        avvia()
        esito = "avviato"
    except Exception as e:
        esito = f"NON avviato: {e}"
    with open(os.path.join(QUI, "avvia_log.txt"), "a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now():%d/%m/%Y %H:%M:%S} {esito}\n")
    print(esito)
