"""Notificaciones. Canal principal: Telegram (gratis, entrega en segundos).

Alta (una sola vez):
  1. En Telegram habla con @BotFather -> /newbot -> nombre y username.
  2. Guarda el token (formato 1234567:AAAbbb...).
  3. Abre la conversacion con TU bot y mandale cualquier mensaje ("hola").
  4. Saca tu chat_id abriendo en el navegador:
       https://api.telegram.org/bot<TU_TOKEN>/getUpdates
     y copia el numero de "chat":{"id": ...}
  5. Guardalo en los secrets del repo: TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID.
"""

import os
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from push import send_push
except Exception:  # noqa: BLE001
    def send_push(*a, **k):
        return None


def _http_get(url, timeout=30):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8", errors="ignore")


def send_telegram(text, token=None, chat_id=None):
    token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return None
    if os.environ.get("DRY_RUN"):
        print(f"[DRY_RUN] Telegram -> {chat_id}:\n{text}\n")
        return True
    url = (
        f"https://api.telegram.org/bot{token}/sendMessage?"
        + urllib.parse.urlencode({"chat_id": chat_id, "text": text})
    )
    try:
        status, body = _http_get(url)
        ok = status == 200 and '"ok":true' in body.replace(" ", "")
        print(f"[notify] telegram status={status} ok={ok}")
        return ok
    except Exception as e:  # noqa: BLE001
        print(f"[notify] telegram fallo: {e}")
        return False


def send_whatsapp(text, phone=None, apikey=None):
    """Fallback opcional via CallMeBot. Puede tardar unos minutos."""
    phone = phone or os.environ.get("WHATSAPP_PHONE", "")
    apikey = apikey or os.environ.get("CALLMEBOT_APIKEY", "")
    if not phone or not apikey:
        return None
    if os.environ.get("DRY_RUN"):
        print(f"[DRY_RUN] WhatsApp -> {phone}:\n{text}\n")
        return True
    url = (
        "https://api.callmebot.com/whatsapp.php?"
        + urllib.parse.urlencode({"phone": phone, "text": text, "apikey": apikey})
    )
    try:
        status, body = _http_get(url)
        ok = status == 200 and "ERROR" not in body.upper()
        print(f"[notify] whatsapp status={status} ok={ok}")
        return ok
    except Exception as e:  # noqa: BLE001
        print(f"[notify] whatsapp fallo: {e}")
        return False


def send_notification(text, url=None, title=None, tag=None):
    """Manda por TODOS los canales configurados.

    Push nativo y Telegram no se excluyen: si tienes los dos, te llega por los
    dos, asi que un fallo de uno no te deja sin aviso. WhatsApp solo entra si
    no hay ningun otro canal.
    """
    sent = False

    first, _, rest = text.partition("\n")
    if send_push(title or "FUT Monitor", (first + ("\n" + rest if rest else "")).strip(),
                 url=url, tag=tag):
        sent = True

    if send_telegram(text):
        sent = True

    if not sent and send_whatsapp(text):
        sent = True

    if not sent:
        print("[notify] ningun canal configurado - no envio nada.")
    return sent


def fmt_coins(v):
    """1234567 -> '1.234.567'. Devuelve 'sin precio' si es None."""
    if v is None:
        return "sin precio"
    return f"{v:,.0f}".replace(",", ".")
