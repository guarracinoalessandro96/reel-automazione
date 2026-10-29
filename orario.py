"""Decide se adesso tocca pubblicare. Dal 29/10/2026: 10 AL GIORNO (scelta di Alessandro, "come dice Gary Vee"), alle
00, 06, 08, 10, 12, 14, 16, 18, 20, 22 ora di Roma (niente 02 e 04: in Italia dormono tutti).
(21-29/10: uno ogni 2 ore, 12 al giorno.)
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
RITARDO_MAX = 40                     # minuti: oltre, lo slot si salta e si prepara il successivo. 25/10/2026: era 10,
                                     # ma col PC che si sveglia alle :12 e GitHub in ritardo di ore lo slot si perdeva
                                     # (12:00 saltato per 2 minuti); in ritardo esce subito, mai due volte (slot_fatti)
OGNI_ORE = 2                         # 21/10/2026: uno ogni 2 ore ...
ORE = (0, 6, 8, 10, 12, 14, 16, 18, 20, 22)   # ... 29/10/2026: 10 al giorno, senza le 02 e le 04
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


SLOTS = [(h, 0, fascia_ora(h)) for h in ORE]      # (ora, minuti, fascia)


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
        if c.hour not in ORE:                                         # solo gli orari della giornata
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
