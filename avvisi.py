"""Messaggi ad Alessandro sul bot Telegram. Se Telegram non e' collegato (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
mancanti) non fa niente.

3/11/2026 (sue parole): "non voglio questi messaggi su telegram ma solamente le visualizzazioni delle ultime 24 ore
con il giorno". Su Telegram arriva SOLO il messaggio delle statistiche (statistiche.py, manda_statistiche): gli avvisi
(manda) restano nei log e non partono piu'. Per riaccenderli: AVVISI_TELEGRAM = True.
6/11/2026: manda_statistiche accetta solo quel messaggio (inizia con TITOLO_STATISTICHE): un altro testo passato li'
per sbaglio resta nel log. Le risposte del bot ai suoi comandi e ai video che manda sono in ricevi_telegram.py."""
import html, os
import requests

ENV = os.environ.get
AVVISI_TELEGRAM = False
TITOLO_STATISTICHE = "VISUALIZZAZIONI ULTIME 24 ORE"


def _invia(testo):
    tok, chat = ENV("TELEGRAM_BOT_TOKEN"), ENV("TELEGRAM_CHAT_ID")
    if not tok or not chat:
        return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", timeout=30,
                          data={"chat_id": chat, "text": html.escape(testo)[:4000], "parse_mode": "HTML",
                                "disable_web_page_preview": "true"}).json()
        return bool(r.get("ok"))
    except Exception:
        return False


def manda(testo):
    """Avviso: con AVVISI_TELEGRAM spento finisce solo nel log. True come se fosse arrivato (nessuno deve riprovare)."""
    if not AVVISI_TELEGRAM:
        print("[avviso non inviato su Telegram]", testo)
        return True
    return _invia(testo)


def manda_statistiche(testo):
    """L'unico messaggio che arriva su Telegram: le visualizzazioni del giorno. True se arrivato."""
    if not str(testo).startswith(TITOLO_STATISTICHE):
        print("[messaggio non inviato su Telegram: su Telegram vanno solo le visualizzazioni]", testo)
        return False
    return _invia(testo)
