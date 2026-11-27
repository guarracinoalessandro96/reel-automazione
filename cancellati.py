"""27/11/2026: registro dei reel cancellati (pulizia.py, la pulizia TikTok dal PC, le cancellazioni a mano del 27/11).
cancellati.json = {"cancellati": {social: {id: {"views", "uscito", "cancellato", "titolo"}}}, "visti": {...}}.
somma(social) = visualizzazioni dei reel cancellati: statistiche.py e andamento.py le aggiungono ai totali del canale,
cosi' le visualizzazioni del giorno (differenza tra due totali) non diventano negative quando i video spariscono."""
import datetime, json, os

QUI = os.path.dirname(os.path.abspath(__file__))
FILE = os.path.join(QUI, "cancellati.json")


def carica():
    try:
        with open(FILE, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        d = {}
    d.setdefault("cancellati", {})
    d.setdefault("visti", {})
    return d


def salva(d):
    for s, ids in d.get("cancellati", {}).items():         # i cancellati non servono piu' tra i "visti"
        for i in ids:
            d.get("visti", {}).get(s, {}).pop(i, None)
    with open(FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=0, sort_keys=True)


def segna(d, social, pid, views, uscito=None, titolo=None):
    d["cancellati"].setdefault(social, {})[pid] = {
        "views": int(views or 0), "uscito": uscito,
        "cancellato": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="minutes"),
        **({"titolo": titolo} if titolo else {})}


def togli(d, social, pid):
    d["cancellati"].get(social, {}).pop(pid, None)


def somma(social, d=None):
    try:
        d = d or carica()
        return sum(int(v.get("views") or 0) for v in d["cancellati"].get(social, {}).values())
    except Exception:
        return 0
