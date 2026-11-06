"""Messaggi ad Alessandro sul bot Telegram. Se Telegram non e' collegato (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
mancanti) non fa niente.

3/11/2026 (sue parole): "non voglio questi messaggi su telegram ma solamente le visualizzazioni delle ultime 24 ore
con il giorno". Su Telegram arriva SOLO il messaggio delle statistiche (statistiche.py, manda_statistiche): gli avvisi
(manda) restano nei log e non partono piu'. Per riaccenderli: AVVISI_TELEGRAM = True.
6/11/2026: manda_statistiche accetta solo quel messaggio (inizia con TITOLO_STATISTICHE): un altro testo passato li'
per sbaglio resta nel log. Le risposte del bot ai suoi comandi e ai video che manda sono in ricevi_telegram.py."""
import html, os
import requests
import urllib3

ENV = os.environ.get
AVVISI_TELEGRAM = False
TITOLO_STATISTICHE = "VISUALIZZAZIONI ULTIME 24 ORE"


def _mai_partito(e):
    """La richiesta non e' mai uscita: nome non trovato, connessione rifiutata o scaduta prima di collegarsi."""
    if isinstance(e, (requests.exceptions.ConnectTimeout, requests.exceptions.SSLError)):
        return True
    motivo = getattr(e.args[0], "reason", None) if e.args else None
    return isinstance(motivo, (urllib3.exceptions.NewConnectionError, urllib3.exceptions.ConnectTimeoutError))


def _invia(testo):
    """True arrivato, False di sicuro non partito, None non si sa. 6/11/2026 (revisione): una risposta persa DOPO
    l'invio (timeout, connessione chiusa) puo' voler dire messaggio arrivato: statistiche.py non lo rimanda."""
    tok, chat = ENV("TELEGRAM_BOT_TOKEN"), ENV("TELEGRAM_CHAT_ID")
    if not tok or not chat:
        return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", timeout=30,
                          data={"chat_id": chat, "text": html.escape(testo)[:4000], "parse_mode": "HTML",
                                "disable_web_page_preview": "true"})
    except requests.RequestException as e:
        return False if _mai_partito(e) else None
    except Exception:
        return None
    try:
        j = r.json()
    except ValueError:
        return None          # risposta non di Telegram (un proxy?): non si sa
    return bool(j.get("ok")) if isinstance(j, dict) else None     # ok false: Telegram l'ha rifiutato, non partito


def manda(testo):
    """Avviso: con AVVISI_TELEGRAM spento finisce solo nel log. True come se fosse arrivato (nessuno deve riprovare)."""
    if not AVVISI_TELEGRAM:
        print("[avviso non inviato su Telegram]", testo)
        return True
    return _invia(testo)


def manda_statistiche(testo):
    """L'unico messaggio che arriva su Telegram: le visualizzazioni del giorno. True arrivato, False non partito,
    None non si sa (vedi _invia)."""
    if not str(testo).startswith(TITOLO_STATISTICHE):
        print("[messaggio non inviato su Telegram: su Telegram vanno solo le visualizzazioni]", testo)
        return False
    return _invia(testo)
