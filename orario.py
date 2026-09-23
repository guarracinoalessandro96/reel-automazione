"""Decide se adesso tocca pubblicare (orari italiani 9, 12, 15, 18, 21, ora legale inclusa).

GitHub avvia il controllo piu' volte al giorno (orari UTC fissi) e a volte con ritardo:
qui si guarda l'ora di Roma e si pubblica solo se c'e' uno slot scaduto da meno di 3 ore
e non ancora fatto oggi. Stampa lo slot (es. "2026-09-23 09") oppure niente.
Solo libreria standard: gira in un secondo, prima di installare qualsiasi cosa.
"""
import datetime, json, os, sys
from zoneinfo import ZoneInfo

SLOTS = [9, 12, 15, 18, 21]
STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stato.json")


def slot_da_fare(now=None):
    now = now or datetime.datetime.now(ZoneInfo("Europe/Rome"))
    fatti = set()
    if os.path.exists(STATE):
        fatti = set(json.load(open(STATE, encoding="utf-8")).get("slot_fatti", []))
    for h in reversed(SLOTS):
        if h <= now.hour < h + 3:
            key = f"{now:%Y-%m-%d} {h:02d}"
            return None if key in fatti else key
    return None


if __name__ == "__main__":
    if os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), "PAUSA")):
        sys.exit(0)          # file PAUSA presente: automazione ferma (nessuna pubblicazione)
    if os.environ.get("FORZA") == "1":
        print(datetime.datetime.now(ZoneInfo("Europe/Rome")).strftime("%Y-%m-%d %H") + " manuale")
        sys.exit(0)
    s = slot_da_fare()
    if s:
        print(s)
