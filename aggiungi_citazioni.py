"""
Aggiunge citazioni nuove a frasi.json in sicurezza.
Uso: python aggiungi_citazioni.py nuove1.json [nuove2.json ...]

Ogni file: lista di {"id","testo","autore","fonte","tema","sicurezza"} (formato di Documenti/regole-citazioni.md).
Tiene solo: sicurezza "alta", tema valido, 6-24 parole, niente parole vietate, niente autori esclusi,
nessun doppione (ne' tra le nuove ne' con quelle gia' presenti). Stampa cosa ha scartato e perche'.
"""
import collections, difflib, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
FRASI = os.path.join(HERE, "frasi.json")
TEMI_PER_SCENA = {
    "cibo": ["dieta"], "palestra": ["palestra", "disciplina", "imprenditore"], "lavoro": ["imprenditore", "disciplina"],
    "pacchi": ["imprenditore"], "macchina": ["imprenditore", "positivita", "mentalita", "abitudini", "disciplina"],
    "specchio": ["lifestyle", "positivita", "mentalita", "abitudini"], "casa": ["famiglia", "abitudini", "mentalita", "positivita"],
    "uscita": ["amicizia", "lifestyle", "positivita", "famiglia"],
}
TAG = {"dieta": ["#salute", "#alimentazione", "#benessere"], "palestra": ["#palestra", "#allenamento", "#disciplina"],
       "imprenditore": ["#imprenditore", "#business", "#successo"], "disciplina": ["#disciplina", "#costanza", "#mentalita"],
       "abitudini": ["#abitudini", "#costanza", "#crescitapersonale"], "positivita": ["#positivita", "#motivazione", "#vita"],
       "famiglia": ["#famiglia", "#gratitudine", "#valori"], "amicizia": ["#amicizia", "#valori", "#vita"],
       "mentalita": ["#mentalita", "#crescitapersonale", "#motivazione"], "lifestyle": ["#lifestyle", "#stile", "#vita"]}
VIETATE = re.compile(r"uccid|mort|muor|morir|guerra|\bdio\b|diavol|sangue|odio|suicid|fucil|arma\b", re.I)
AUTORI_ESCLUSI = re.compile(r"musk|trump|putin|mussolini|hitler|stalin|rocky|stallone", re.I)


def norm(s):
    return re.sub(r"[^a-zàèéìòù ]", "", s.lower())


def main(files):
    frasi = json.load(open(FRASI, encoding="utf-8"))
    presenti = [norm(f["gancio"]) for f in frasi]
    ids = {f["id"] for f in frasi}
    scarti, aggiunte = collections.Counter(), []
    for path in files:
        for q in json.load(open(path, encoding="utf-8")):
            testo = q["testo"].strip().strip('"“”')
            n = len(testo.split())
            if q.get("sicurezza") != "alta":
                scarti["fonte non documentata"] += 1; continue
            if q.get("tema") not in TAG:
                scarti["tema non valido"] += 1; continue
            if not 6 <= n <= 24:
                scarti["lunghezza"] += 1; continue
            if VIETATE.search(testo) or AUTORI_ESCLUSI.search(q["autore"] + " " + q.get("fonte", "")):
                scarti["parole o autori esclusi"] += 1; continue
            t = norm(testo)
            if any(difflib.SequenceMatcher(None, t, p).ratio() > 0.6 for p in presenti):
                scarti["doppione"] += 1; continue
            qid = q["id"] if q["id"] not in ids else q["id"] + "b"
            scene = [s for s, temi in TEMI_PER_SCENA.items() if q["tema"] in temi]
            aggiunte.append({"id": qid, "tema": q["tema"], "scene": scene, "gancio": testo, "autore": q["autore"].strip(),
                             "fonte": q.get("fonte", ""), "hashtag": ["#citazioni"] + TAG[q["tema"]]})
            presenti.append(t); ids.add(qid)
    json.dump(frasi + aggiunte, open(FRASI, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"Aggiunte {len(aggiunte)} citazioni. Totale ora: {len(frasi) + len(aggiunte)}. Scartate: {dict(scarti)}")
    print("Per tema:", dict(collections.Counter(a["tema"] for a in aggiunte)))


if __name__ == "__main__":
    main(sys.argv[1:])
