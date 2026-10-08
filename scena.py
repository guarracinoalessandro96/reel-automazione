"""
Riconosce COSA c'e' nel video e QUANDO e' stato registrato.

- Scena: modello CLIP (open source, gira gratis sul computer di GitHub) che confronta alcuni fotogrammi
  con descrizioni in inglese ("a plate of food", "a man lifting weights in a gym"...).
  Categorie: specchio, cibo, lavoro, pacchi, macchina, palestra, casa, uscita.
  Si puo' forzare con una parola nel nome del file (es. "palestra", "cibo", "pacchi").
- Ora di registrazione: letta dai metadati dell'iPhone (com.apple.quicktime.creationdate).
- Slot di pubblicazione: mattina 9, pranzo 12, pomeriggio 15, tardo pomeriggio 18, sera 21.
"""
import datetime, re, subprocess
from zoneinfo import ZoneInfo

SCENE = {
    "specchio": ["a man taking a mirror selfie", "a man checking his outfit in front of a mirror",
                 "a man getting dressed in a bedroom"],
    "cibo": ["a plate of food on a table", "a healthy meal with meat and vegetables", "breakfast on a table",
             "a person cooking food in a kitchen"],
    "lavoro": ["a man working on a laptop computer", "an office desk with a computer screen",
               "a person recording video content with a camera or smartphone on a tripod"],
    "pacchi": ["hands packing a cardboard box with tape", "shipping boxes and parcels ready for delivery",
               "a warehouse table with packages"],
    "macchina": ["a man driving a car", "the interior of a car", "a man in an elevator"],
    "palestra": ["a man lifting weights in a gym", "gym equipment and dumbbells", "a man training at the gym"],
    "casa": ["a cozy living room at home", "a man relaxing on a sofa at home", "a family dinner at home"],
    "uscita": ["people at a bar or cafe", "a football stadium", "a shopping mall", "a city street at night",
               "friends having dinner at a restaurant", "a walk by the sea",
               "people sitting on a terrace or lounge bar in the evening", "a man sitting outdoors with family at night"],
}
PAROLE = {"palestra": "palestra", "gym": "palestra", "cibo": "cibo", "pranzo": "cibo", "cena": "cibo",
          "colazione": "cibo", "pacchi": "pacchi", "ordini": "pacchi", "ufficio": "lavoro", "lavoro": "lavoro",
          "pc": "lavoro", "macchina": "macchina", "auto": "macchina", "specchio": "specchio", "outfit": "specchio",
          "casa": "casa", "uscita": "uscita", "bar": "uscita", "stadio": "uscita"}
SLOTS = [9, 12, 15, 18, 21]

_model = None


def _clip():
    global _model
    if _model is None:
        import open_clip, torch
        model, _, pre = open_clip.create_model_and_transforms("ViT-B-32-quickgelu", pretrained="openai")
        tok = open_clip.get_tokenizer("ViT-B-32-quickgelu")
        labels, texts = [], []
        for k, frasi in SCENE.items():
            for f in frasi:
                labels.append(k)
                texts.append(f)
        with torch.no_grad():
            tf = model.encode_text(tok(texts))
            tf = tf / tf.norm(dim=-1, keepdim=True)
        model.eval()
        _model = (model, pre, tf, labels, torch)
    return _model


def riconosci(frames_bgr, nome_file=""):
    """Restituisce (scena, sicurezza 0-1, motivo)."""
    n = nome_file.lower()
    for parola, s in PAROLE.items():
        if re.search(rf"(?<![a-z]){parola}(?![a-z])", n):     # anche "palestra_1", "cibo-pranzo", "IMG palestra"
            return s, 1.0, "dal nome del file"
    try:
        from PIL import Image
        model, pre, tf, labels, torch = _clip()
        punteggi = {k: 0.0 for k in SCENE}
        scelti = frames_bgr[:: max(1, len(frames_bgr) // 6)][:6]
        with torch.no_grad():
            imgs = torch.stack([pre(Image.fromarray(f[:, :, ::-1])) for f in scelti])
            fi = model.encode_image(imgs)
            fi = fi / fi.norm(dim=-1, keepdim=True)
            prob = (100 * fi @ tf.T).softmax(dim=-1).mean(dim=0)
        for p, lab in zip(prob.tolist(), labels):
            punteggi[lab] += p
        best = max(punteggi, key=punteggi.get)
        return best, round(punteggi[best], 2), "riconosciuta dalle immagini"
    except Exception as e:   # senza modello: scena generica, la frase sara' "universale"
        return "casa", 0.0, f"riconoscimento non disponibile ({e.__class__.__name__}: {str(e)[:200]})"


COMPAGNIA = {   # con chi e' Alessandro nel video: serve a scegliere citazioni su famiglia o amicizia solo quando hanno senso
    "famiglia": ["a young man sitting with his mother", "a young man with his parents", "a family together at home",
                 "a young man with an older woman", "a family dinner with parents"],
    "amici": ["a group of young male friends", "young friends laughing together", "two young men hanging out",
              "friends at a bar"],
    "solo": ["a man alone", "a single young man by himself", "a man alone in a car", "a man training alone at the gym"],
}
_comp = None


def compagnia(frames_bgr):
    """('famiglia' | 'amici' | 'solo', sicurezza 0-1). In caso di problemi: (None, 0)."""
    global _comp
    try:
        from PIL import Image
        model, pre, _, _, torch = _clip()
        if _comp is None:
            import open_clip
            tok = open_clip.get_tokenizer("ViT-B-32-quickgelu")
            labels = [k for k, v in COMPAGNIA.items() for _ in v]
            with torch.no_grad():
                tf = model.encode_text(tok([f for v in COMPAGNIA.values() for f in v]))
                tf = tf / tf.norm(dim=-1, keepdim=True)
            _comp = (tf, labels)
        tf, labels = _comp
        scelti = frames_bgr[:: max(1, len(frames_bgr) // 6)][:6]
        with torch.no_grad():
            fi = model.encode_image(torch.stack([pre(Image.fromarray(f[:, :, ::-1])) for f in scelti]))
            fi = fi / fi.norm(dim=-1, keepdim=True)
            prob = (100 * fi @ tf.T).softmax(dim=-1).mean(dim=0)
        tot = {k: 0.0 for k in COMPAGNIA}
        for p, lab in zip(prob.tolist(), labels):
            tot[lab] += p
        best = max(tot, key=tot.get)
        return best, round(tot[best], 2)
    except Exception:
        return None, 0.0


def ora_registrazione(info_ffmpeg):
    """Data/ora locale di registrazione dai metadati iPhone; None se assente."""
    m = re.search(r"com\.apple\.quicktime\.creationdate\s*:\s*(\S+)", info_ffmpeg)
    if m:
        try:
            return datetime.datetime.fromisoformat(m.group(1).replace("Z", "+00:00")).astimezone(ZoneInfo("Europe/Rome"))
        except ValueError:
            pass
    m = re.search(r"creation_time\s*:\s*(\S+)", info_ffmpeg)
    if m:
        try:
            return datetime.datetime.fromisoformat(m.group(1).replace("Z", "+00:00")).astimezone(ZoneInfo("Europe/Rome"))
        except ValueError:
            pass
    return None


def fascia_per(scena, quando):
    """Fascia della giornata di Alessandro in cui il video sta meglio (dal 8/10/2026, 10 reel al giorno).
    Giornata: 8-9 macchina, 9-13 ufficio, 13-14 pranzo a casa, 14-19 ufficio, 19 macchina verso casa,
    21-23 palestra, 23 macchina verso casa. Fasce: mattina 8:00 | ufficio 9:45 11:30 15:00 16:45 |
    pranzo 13:15 | sera 18:30 20:15 | palestra 22:00 | notte 23:45."""
    h = quando.hour + quando.minute / 60 if quando else None
    if scena == "palestra":
        return "palestra"
    if scena in ("lavoro", "pacchi", "specchio"):
        return "ufficio"
    if scena == "cibo":
        return "pranzo"
    if scena == "uscita":
        return "sera"
    if h is None:
        return {"macchina": "mattina", "casa": "sera"}.get(scena, "ufficio")
    if h >= 22.5 or h < 5:
        return "notte"
    if h < 10.5:
        return "mattina" if scena == "macchina" else "ufficio"
    if 12 <= h < (15.5 if scena == "macchina" else 14.5):     # pausa pranzo a casa, andata e ritorno in macchina
        return "pranzo"
    if h >= 18:
        return "sera"
    return "pranzo" if scena == "casa" else ("sera" if scena == "macchina" and h >= 16 else "ufficio")


def slot_per(scena, quando):
    """Orario di pubblicazione adatto al video."""
    if scena in ("palestra", "uscita"):
        return 21 if (quando is None or quando.hour >= 20 or quando.hour < 6) else 18
    if quando is None:
        return {"specchio": 9, "macchina": 9, "cibo": 12, "lavoro": 15, "pacchi": 12, "casa": 21}.get(scena, 15)
    h = quando.hour + quando.minute / 60
    if h < 10.5:
        return 9
    if h < 13.5:
        return 12
    if h < 16.5:
        return 15
    if h < 19.5:
        return 18
    return 21
