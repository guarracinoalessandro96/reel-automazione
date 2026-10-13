"""Decide se adesso tocca pubblicare. Dal 13/10/2026: 4 reel al giorno, alle 9, 13, 17 e 21 (ora di Roma). (8-11/10: 10 al giorno; 11-13/10: 5.)

GitHub avvia il controllo ogni 10 minuti (e a volte con ritardo): qui si guarda l'ora di Roma e si pubblica
se c'e' un orario scaduto (o che scade entro 10 minuti) e non ancora fatto, entro la sua finestra (fino all'orario successivo; l'ultimo
dura fino all'01:30). Stampa lo slot (es. "2026-10-08 09:45") oppure niente.
Solo libreria standard: gira in un secondo, prima di installare qualsiasi cosa.
"""
import datetime, json, os, sys
from zoneinfo import ZoneInfo

# (ora, minuti, fascia della giornata di Alessandro)
# giornata di Alessandro: 8-9 macchina, 9-13 ufficio, 13-14 pranzo a casa (in macchina), 14-19 ufficio,
# 19 macchina verso casa, 21-23 palestra, 23 macchina verso casa
SLOTS = [(9, 0, "mattina"), (13, 0, "pranzo"), (17, 0, "ufficio"), (21, 0, "palestra")]   # dal 13/10/2026: dalle 9 ogni 4 ore
FINE_ULTIMO = 25 * 60 + 30           # l'ultimo orario (21:00) resta valido fino all'01:30
ANTICIPO = 10                        # minuti: GitHub parte spesso in ritardo, quindi uno slot si puo' fare fino a 10' prima
STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stato.json")


def etichetta(h, m):
    return f"{h:02d}:{m:02d}"


def fascia(ora_slot):
    """'08:00' -> 'mattina' ecc. None se l'orario non e' uno slot."""
    return next((f for h, m, f in SLOTS if etichetta(h, m) == ora_slot), None)


def slot_da_fare(now=None):
    now = now or datetime.datetime.now(ZoneInfo("Europe/Rome"))
    fatti = set()
    if os.path.exists(STATE):
        fatti = set(json.load(open(STATE, encoding="utf-8")).get("slot_fatti", []))
    minuti, giorno = now.hour * 60 + now.minute, now.date()
    if minuti < FINE_ULTIMO - 24 * 60:            # tra mezzanotte e l'01:30 vale ancora l'ultimo orario di ieri
        minuti += 24 * 60
        giorno -= datetime.timedelta(days=1)
    inizi = [h * 60 + m - ANTICIPO for h, m, _ in SLOTS]
    for i in reversed(range(len(SLOTS))):
        fine = inizi[i + 1] if i + 1 < len(SLOTS) else FINE_ULTIMO
        if inizi[i] <= minuti < fine:
            key = f"{giorno:%Y-%m-%d} {etichetta(*SLOTS[i][:2])}"
            return None if key in fatti else key
    return None


if __name__ == "__main__":
    if os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), "PAUSA")):
        sys.exit(0)          # file PAUSA presente: automazione ferma (nessuna pubblicazione)
    if os.environ.get("FORZA") == "1":
        print(datetime.datetime.now(ZoneInfo("Europe/Rome")).strftime("%Y-%m-%d %H:%M") + " manuale")
        sys.exit(0)
    s = slot_da_fare()
    if s:
        print(s)
