"""Notificaciones push nativas (Web Push / VAPID).

Segundo canal, junto a Telegram. Funciona en iPhone solo si la app esta
anadida a la pantalla de inicio (iOS 16.4+).

Secrets que necesita en el repositorio:
  VAPID_PRIVATE_KEY   la clave privada (ver vapid-keys.txt)
  VAPID_SUBJECT       mailto:tu@correo.com  (opcional pero recomendado)
  PUSH_SUBSCRIPTION   el JSON que te da la app al activar las notificaciones.
                      Si tienes varios dispositivos, pega un array de JSONs.

Depende de pywebpush, que el workflow instala con pip. Si no esta instalada,
este canal se salta en silencio y Telegram sigue funcionando.
"""

import json
import os

try:
    from pywebpush import webpush, WebPushException
    AVAILABLE = True
except Exception:  # noqa: BLE001
    AVAILABLE = False


def _subscriptions():
    raw = (os.environ.get("PUSH_SUBSCRIPTION") or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:  # noqa: BLE001
        print("[push] PUSH_SUBSCRIPTION no es JSON valido")
        return []
    if isinstance(data, dict):
        data = [data]
    return [s for s in data if isinstance(s, dict) and s.get("endpoint")]


def send_push(title, body, url=None, tag=None):
    """Devuelve True/False si hay canal configurado, None si no lo hay."""
    subs = _subscriptions()
    private = os.environ.get("VAPID_PRIVATE_KEY", "").strip()
    if not subs or not private:
        return None
    if not AVAILABLE:
        print("[push] pywebpush no instalada - salto el canal push")
        return None
    if os.environ.get("DRY_RUN"):
        print(f"[DRY_RUN] Push a {len(subs)} dispositivo(s): {title} / {body}")
        return True

    payload = json.dumps({
        "title": title, "body": body,
        "url": url or "./", "tag": tag,
    }, ensure_ascii=False)
    claims = {"sub": os.environ.get("VAPID_SUBJECT", "mailto:fut-monitor@example.com")}

    ok_any = False
    for sub in subs:
        try:
            webpush(
                subscription_info=sub,
                data=payload,
                vapid_private_key=private,
                vapid_claims=dict(claims),
                ttl=1800,
            )
            ok_any = True
            print("[push] enviado")
        except WebPushException as e:  # noqa: BLE001
            code = getattr(getattr(e, "response", None), "status_code", None)
            if code in (404, 410):
                print("[push] suscripcion caducada (410/404). Vuelve a activar "
                      "las notificaciones en el movil y actualiza PUSH_SUBSCRIPTION.")
            else:
                print(f"[push] fallo ({code}): {e}")
        except Exception as e:  # noqa: BLE001
            print(f"[push] fallo: {e}")
    return ok_any
