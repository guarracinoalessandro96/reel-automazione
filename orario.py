"""Decide se adesso tocca pubblicare. Dal 21/10/2026: UNO SHORT OGNI 2 ORE, 12 al giorno (00, 02, ... 22), ora di Roma.
(18-21/10: uno ogni ora, ma YouTube ne faceva vedere solo ~10-14 al giorno: gli altri restavano sotto 25 views.)
(8-11/10: 10 al giorno; 11-13/10: 5; 13-18/10: 4 alle 9, 13, 17, 21.)

GitHub avvia il controllo ogni 10 minuti (a volte in ritardo). Uno slot (es. "2026-10-18 22:00") si prepara fino a
ANTICIPO minuti prima (YouTube lo programma all'ora esatta, poi si aspetta l'ora esatta per il resto) e si accetta
ancora fino a RITARDO_MAX minuti dopo. Stampa lo slot da fare oppure niente.
Solo libreria standard: gira in un secondo, prima di installare qualsiasi cosa.
"""
import datetime, json, os, sys
from zoneinfo import ZoneInfo

ANTICIPO = 50                        # minuti: si prepara tutto prima, poi si pubblica all'ora ESATTA
RITARDO_MAX = 10                     # minuti: oltre, lo slot si salta e si prepara il successivo
OGNI_ORE = 2                         # 21/10/2026: scelta di Alessandro (12 al giorno, tutti spinti da YouTube)
STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stato.json")


def fascia_ora(h):
    """Momento della giornata di Alessandro a quell'ora (per scegliere un video che c'entri):
    8-9 macchina, 9-13 ufficio, 13-14 pranzo, 14-19 ufficio, 19 rientro, 21-23 palestra, poi notte."""
    if 5 <= h <= 8:
        return "mattina"
    if 9 <= h <= 12 or 14 <= h <= 18:
        return "ufficio"
    if h == 13:
        return "pranzo"
    if 19 <= h <= 20:
        return "sera"
    if 21 <= h <= 22:
        return "palestra"
    return "notte"


SLOTS = [(h, 0, fascia_ora(h)) for h in range(0, 24, OGNI_ORE)]      # (ora, minuti, fascia): uno ogni 2 ore


def etichetta(h, m):
    return f"{h:02d}:{m:02d}"


def fascia(ora_slot):
    """'08:00' -> 'mattina' ecc. None se non e' un orario valido."""
    try:
        return fascia_ora(int(str(ora_slot)[:2]))
    except ValueError:
        return None


def slot_da_fare(now=None):
    now = now or datetime.datetime.now(ZoneInfo("Europe/Rome"))
    fatti = set()
    if os.path.exists(STATE):
        fatti = set(json.load(open(STATE, encoding="utf-8")).get("slot_fatti", []))
    questa = now.replace(minute=0, second=0, microsecond=0)
    prossima = questa + datetime.timedelta(hours=1)
    candidati = []
    if now - questa <= datetime.timedelta(minutes=RITARDO_MAX):      # appena passata: si fa subito
        candidati.append(questa)
    if prossima - now <= datetime.timedelta(minutes=ANTICIPO):       # in arrivo: si prepara e si aspetta
        candidati.append(prossima)
    for c in candidati:
        if c.hour % OGNI_ORE:                                         # solo le ore pari
            continue
        key = f"{c:%Y-%m-%d %H:%M}"
        if key not in fatti:
            return key
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
