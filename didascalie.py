"""
DIDASCALIE (6/11/2026, Alessandro: "piu' virali anche con i testi"): il testo intorno al video su tutte le piattaforme.

Cosa dicono le piattaforme (fonti in notte/didascalie_esempi.md):
- Instagram cerca anche nelle didascalie (parole chiave nella didascalia, non nei commenti) e dal 12/2025 accetta al
  massimo 5 hashtag; TikTok e' un motore di ricerca ma penalizza le parole ammucchiate o che non c'entrano col video;
  Meta toglie portata alle didascalie lunghe, con troppi hashtag o scollegate dal video (aprile 2025).
Quindi ogni didascalia e':
  1. la frase del video (il gancio, con le sue parole: e' la prima riga che si legge)
  2. UNA riga naturale con le parole che la gente cerca, prese dalla frase stessa
     ("Frasi motivazionali sulla costanza e sul lavoro.") - non piu' le stesse 5 parole su ogni video
  3. Giorno X/365 (la serie resta in descrizione, mai sul video)
  4. 4 hashtag pertinenti (#frasimotivazionali + quelli della frase + uno a giro)
Mai: palestra, eta', domande per i commenti, "seguimi per vedere dove arrivo", nomi di autori.
Solo funzioni semplici (nessuna libreria): lo usano pubblica.py su GitHub e tiktok_prepara.py sul PC.
"""
import hashlib, re

TESTA = "Frasi motivazionali"
# (radice cercata nella frase, "sul ..." per la riga di ricerca, hashtag o None): in ordine di importanza
CHIAVI = [
    (r"disciplin", "sulla disciplina", "#disciplina"),
    (r"costan", "sulla costanza", "#costanza"),
    (r"sacrific", "sul sacrificio", "#sacrificio"),
    (r"obiettiv|traguard", "sugli obiettivi", "#obiettivi"),
    (r"\bfutur", "sul futuro", "#futuro"),
    (r"\blavor", "sul lavoro", "#lavoro"),
    (r"\bsogn", "sui sogni", "#sogni"),
    (r"success", "sul successo", "#successo"),
    (r"non mollare|\bmoll[aoi]|arrender|determinaz", "sulla determinazione", "#nonmollare"),
    (r"mentalit", "sulla mentalità", "#mentalita"),
    (r"crescit|\bcresc|miglior", "sulla crescita personale", "#crescitapersonale"),
    (r"volont|\bforza\b", "sulla forza di volontà", "#forzadivolonta"),
    (r"pazien", "sulla pazienza", "#pazienza"),
    (r"\bcoraggi", "sul coraggio", "#coraggio"),      # 6/11: non "incoraggi"
    (r"abitudin", "sulle abitudini", "#abitudini"),
    (r"impegn|\bfatic", "sull'impegno", "#impegno"),
    (r"client|impres|imprendit|aziend|business", "sull'imprenditoria", "#imprenditore"),
    (r"rispett", "sul rispetto", "#rispetto"),
    (r"lealt|\bleal[ei]\b", "sulla lealtà", "#lealta"),
    (r"\bcambi", "sul cambiamento", "#cambiamento"),
    (r"\bvit[ae]\b", "sulla vita", "#frasidivita"),
    (r"\btemp[oi]\b", "sul tempo", None),
]
# se la frase non ha parole riconosciute: in base al tema (mai la parola "palestra", mai la famiglia)
PER_TEMA = {"imprenditore": ["sul lavoro", "sull'imprenditoria"], "disciplina": ["sulla disciplina", "sulla costanza"],
            "palestra": ["sulla disciplina", "sulla costanza"], "dieta": ["sulla disciplina", "sulla costanza"],
            "abitudini": ["sulle abitudini", "sulla costanza"]}
# "mentalita" e' il tema di quando il Doc non dice niente: argomenti generali a giro, cosi' i reel non sono tutti uguali
RISERVA = ["sulla vita", "sulla crescita personale", "sulla mentalità", "sul futuro"]
GIRO = ["#motivazione", "#crescitapersonale", "#mentalita", "#frasidivita", "#disciplina"]
MODELLI_2 = ["{t} {a} e {b}.", "{t} in italiano {a} e {b}.", "{t} {a} e {b}: ogni giorno un passo avanti.",
             "{t} {a} e {b}, per ripartire ogni giorno."]
MODELLI_1 = ["{t} {a}.", "{t} in italiano {a}.", "{t} {a}: ogni giorno un passo avanti.",
             "{t} {a}, per ripartire ogni giorno."]
NUMERO_TAG = 4          # Instagram dal 12/2025 ne accetta al massimo 5; Meta: con al massimo 5 si va meglio


def _giro(chiave):
    """Numero fisso per la stessa frase (stessa didascalia se il reel si riprova), diverso tra frasi diverse."""
    return int(hashlib.md5(str(chiave or "").encode("utf-8")).hexdigest(), 16)


def _trovate(frase):
    t = (frase or "").lower()
    return [c for c in CHIAVI if re.search(c[0], t)]


def tag_della_frase(frase):
    """Hashtag delle parole cercate che ci sono davvero nella frase (in ordine di importanza)."""
    return list(dict.fromkeys(c[2] for c in _trovate(frase) if c[2]))


def temi_ricerca(frase, tema=None, chiave=None):
    """I due argomenti della riga di ricerca: prima quelli della frase, poi quelli del tema (o a giro)."""
    usati = list(dict.fromkeys(c[1] for c in _trovate(frase)))
    riserva = PER_TEMA.get(tema) or RISERVA[_giro(chiave) % len(RISERVA):] + RISERVA[:_giro(chiave) % len(RISERVA)]
    for r in riserva:
        if len(usati) >= 2:
            break
        if r not in usati:
            usati.append(r)
    return usati[:2]


def riga_ricerca(frase, tema=None, chiave=None):
    """Es. 'Frasi motivazionali sulla costanza e sul lavoro.' (una riga sola, parole vere della frase)."""
    temi = temi_ricerca(frase, tema, chiave)
    k = _giro(chiave or frase)
    if len(temi) >= 2:
        return MODELLI_2[k % len(MODELLI_2)].format(t=TESTA, a=temi[0], b=temi[1])
    return MODELLI_1[k % len(MODELLI_1)].format(t=TESTA, a=(temi or RISERVA)[0])


def hashtag(frase, tema=None, chiave=None, n=NUMERO_TAG, escludi=()):
    """n hashtag: #frasimotivazionali, quelli della frase (max 2), poi a giro (fissi per la stessa frase)."""
    k = _giro(chiave or frase) % len(GIRO)
    tutti = ["#frasimotivazionali"] + tag_della_frase(frase)[:2] + GIRO[k:] + GIRO[:k]
    return [t for t in dict.fromkeys(tutti) if t not in escludi][:n]


def pulita(frase):
    """La frase come esce in didascalia: senza virgolette e senza il punto finale (come prima del 6/11)."""
    return (frase or "").strip().strip('"“”').strip().rstrip(" .")


def didascalia(frase, serie="", tema=None, chiave=None, n=NUMERO_TAG):
    """Instagram, TikTok e Facebook: frase / riga di ricerca + Giorno X/365 / hashtag."""
    # 7/11/2026 sera (Alessandro: "nelle descrizioni non mettere frasi motivazionali sul lavoro e sulla disciplina,
    # lascia solo quello che sta sopra e poi gli hashtag, ma ne metti solo 3"): solo la frase e 3 hashtag
    return pulita(frase) + "\n\n" + " ".join(hashtag(frase, tema, chiave, n)[:3])


def descrizione_youtube(frase, serie="", tema=None, chiave=None, tags=()):
    """YouTube: la stessa struttura, hashtag '#shorts' + quelli scelti dal chiamante (i primi 3 vanno sopra il titolo)."""
    # 7/11/2026 sera (Alessandro): solo la frase e 3 hashtag (#shorts + 2)
    return pulita(frase) + "\n\n" + " ".join(list(dict.fromkeys(["#shorts"] + list(tags)))[:3])


def ha_riga_ricerca(testo):
    """True se la didascalia ha gia' la riga di ricerca (didascalie dal 6/11/2026) o le vecchie parole fisse."""
    return any(r.strip().lower().startswith(TESTA.lower()) or "frasi motivazionali ·" in r.lower()
               for r in (testo or "").splitlines())


def frase_della_didascalia(testo):
    """La frase com'e' scritta (prima riga che non e' 'Giorno X/365' ne' hashtag), anche per le didascalie vecchie."""
    for r in (testo or "").splitlines():
        r = r.strip()
        if r and not r.startswith(("Giorno", "#")):
            return r
    return ""
