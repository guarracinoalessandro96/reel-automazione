"""Messaggi ad Alessandro sul bot Telegram (avvisi, promemoria, riassunto settimanale). Se Telegram non e'
collegato (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID mancanti) non fa niente."""
import html, os
import requests

ENV = os.environ.get


def manda(testo):
    """Manda un messaggio (testo semplice; *grassetto* non serve). True se arrivato."""
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
