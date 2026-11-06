"""Messaggi ad Alessandro sul bot Telegram. Se Telegram non e' collegato (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
mancanti) non fa niente.

3/11/2026 (sue parole): "non voglio questi messaggi su telegram ma solamente le visualizzazioni delle ultime 24 ore
con il giorno". Su Telegram arriva SOLO il messaggio delle statistiche (statistiche.py, manda_statistiche): gli avvisi
(manda) restano nei log e non partono piu'. Per riaccenderli: AVVISI_TELEGRAM = True.
6/11/2026: manda_statistiche accetta solo quel messaggio (inizia con TITOLO_STATISTICHE): un altro testo passato li'
per sbaglio resta nel log. Le risposte del bot ai suoi comandi e ai video che manda sono in ricevi_telegram.py."""
import html, os, ssl
import requests
import urllib3

ENV = os.environ.get
AVVISI_TELEGRAM = False
TITOLO_STATISTICHE = "VISUALIZZAZIONI ULTIME 24 ORE"


def _dentro(e):
    """L'errore e quelli che porta dentro (reason, args[0], causa), al massimo 8."""
    visti, coda = [], [e]
    while coda and len(visti) < 8:
        x = coda.pop(0)
        if isinstance(x, BaseException) and not any(x is v for v in visti):
            visti.append(x)
            coda += [getattr(x, "reason", None), x.args[0] if x.args else None, x.__cause__, x.__context__]
    return visti


def _mai_partito(e):
    """La richiesta non e' mai uscita: nome non trovato, connessione rifiutata o scaduta prima di collegarsi.
    6/11/2026 (revisione): un errore SSL vale "mai partito" solo se il certificato e' stato rifiutato (succede prima
    di mandare); gli altri (connessione chiusa, EOF) possono arrivare mentre torna la risposta: non si sa."""
    if isinstance(e, requests.exceptions.SSLError):
        return any(isinstance(x, ssl.SSLCertVerificationError) for x in _dentro(e))
    if isinstance(e, requests.exceptions.ConnectTimeout):
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
    if not isinstance(j, dict):
        return None
    if j.get("ok"):
        return True
    try:                     # 6/11/2026 (revisione): ok false 5xx = errore interno di Telegram, forse consegnato
        codice = int(j.get("error_code") or 0)
    except (TypeError, ValueError):
        codice = 0
    return None if codice >= 500 else False      # 4xx: Telegram l'ha rifiutato, non partito


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
