"""
Classifica delle frasi (26/10/2026, richiesta di Alessandro): le frasi da usare sono ordinate per quanto pensiamo
possano andare virali, e pubblica.py usa prima quelle in cima. Il punteggio (0-100) sta in classifica_frasi.json
({id: punteggio}); una frase senza punteggio vale 50.

Come si da' il punteggio (dati dei suoi Shorts + giudizio di Claude):
- lunghezza: 15-25 parole rendono di piu' (la gente si ferma a leggere); sotto 8 parole vale poco;
- temi che funzionano per lui: persone, lealta', rispetto di se', silenzio, stare da soli, situazioni concrete;
- [virale] = andata virale altrove: bonus;
- frasi generiche da poster ("Insegui i tuoi sogni") valgono poco.
Le ricerche nuove (attivita' frasi-virali) danno il punteggio alle frasi trovate con:
    python classifica_frasi.py aggiungi punteggi.txt     (righe "punteggio<TAB>frase")
"""
import hashlib, json, os, re, sys

FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "classifica_frasi.json")
TEMI_FORTI = re.compile(r"\b(person|leal|rispett|silenzi|da sol|valore|amic|fiducia|ignor|resta|andar via|"
                        r"tratta|cuore|ferit|vend|dimostr|nessuno|chi ti|chi non)", re.I)
GENERICHE = re.compile(r"^(insegui|sogna|credi|non mollare|il meglio|ogni problema|la vita continua)", re.I)


def id_frase(testo):
    """Stesso id di mie_citazioni.frasi (impronta del testo)."""
    r = re.sub(r"^\[\w+\]\s*", "", testo.strip()).strip('"“”').strip()
    return "MIE-" + hashlib.md5(r.lower().encode()).hexdigest()[:8]


def stima(testo, virale=False):
    """Punteggio automatico 0-100 (Claude lo corregge a mano sulle frasi migliori)."""
    n = len(testo.split())
    p = 40
    p += 25 if 15 <= n <= 25 else 15 if 12 <= n <= 28 else 5 if 9 <= n <= 11 else -15 if n < 7 else -5
    p += 15 if TEMI_FORTI.search(testo) else 0
    p += 12 if virale else 0
    p -= 15 if GENERICHE.search(testo) else 0
    return max(0, min(100, p))


def carica():
    try:
        return json.load(open(FILE, encoding="utf-8"))
    except Exception:
        return {}


def salva(d):
    json.dump(dict(sorted(d.items(), key=lambda x: -x[1])), open(FILE, "w", encoding="utf-8"), indent=0)


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "aggiungi":
        d = carica()
        for riga in open(sys.argv[2], encoding="utf-8"):
            if "\t" in riga:
                p, t = riga.rstrip("\n").split("\t", 1)
                d[id_frase(t)] = max(0, min(100, int(float(p))))
        salva(d)
        print("classifica:", len(d), "frasi")
