"""FUT Monitor ES - recolector de precios de fut.gg para EA FC 27.

Lo ejecuta GitHub Actions cada 30 min (o a mano). Flujo:
1. Lee la watchlist en data/players.json
2. Pide el mapa de precios actual (CDN publico de fut.gg)
3. Asegura metadatos de cada carta (un scrape unico por carta)
4. Registra historico en data/history/<cardId>.json
5. Calcula media, min/max y BENEFICIO NETO (5% de impuesto de EA ya restado)
6. Cruza con data/events.json (tu calendario de promos)
7. Evalua alertas y las manda por Telegram
8. Genera data/summary.json para la interfaz

Variables de entorno:
  PLATFORM             ps5 (consola, por defecto) o pc
  TELEGRAM_BOT_TOKEN   token del bot
  TELEGRAM_CHAT_ID     tu chat id
  DRY_RUN              si esta definida, imprime en vez de enviar
"""

import json
import os
import sys
import time
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import futgg  # noqa: E402
from notify import send_notification, fmt_coins  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
HISTORY_DIR = os.path.join(DATA, "history")
META_DIR = os.path.join(DATA, "meta")
MAX_POINTS = 6000          # ~4 meses a intervalos de 30 min
EA_TAX = 0.05              # impuesto de venta de EA


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return default


def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")


def ensure_meta(player, core, playstyles_map):
    card_id = player["cardId"]
    path = os.path.join(META_DIR, f"{card_id}.json")
    meta = load_json(path, None)
    if meta and meta.get("name"):
        return meta
    try:
        print(f"[meta] pidiendo metadatos de {player['url']}")
        meta = futgg.scrape_player_meta(player["url"], core=core, playstyles_map=playstyles_map)
        save_json(path, meta)
        return meta
    except Exception as e:  # noqa: BLE001
        print(f"[meta] fallo ({card_id}): {e}")
        return meta or {"cardId": card_id, "eaId": player.get("eaId"), "name": None}


def append_history(card_id, ts, price):
    path = os.path.join(HISTORY_DIR, f"{card_id}.json")
    hist = load_json(path, {"cardId": card_id, "points": []})
    pts = hist["points"]
    if pts and pts[-1][0] == ts:
        pts[-1][1] = price
    else:
        pts.append([ts, price])
    if len(pts) > MAX_POINTS:
        hist["points"] = pts[-MAX_POINTS:]
    save_json(path, hist)
    return hist


def price_at(hist, seconds_ago, now):
    """Precio valido mas reciente con al menos seconds_ago de antiguedad."""
    target = now - seconds_ago
    best = None
    for ts, price in hist["points"]:
        if ts <= target and price:
            best = price
    return best


def window_stats(hist, days, now):
    """Media y min/max de los ultimos N dias. None si aun no hay datos."""
    cut = now - days * 86400
    vals = [p for ts, p in hist["points"] if ts >= cut and p]
    if not vals:
        return None
    return {
        "avg": round(sum(vals) / len(vals)),
        "min": min(vals),
        "max": max(vals),
        "points": len(vals),
    }


def net_after_tax(price):
    """Lo que te queda de verdad al vender a ese precio."""
    return None if not price else round(price * (1 - EA_TAX))


def next_event(events, today=None):
    """Proximo evento del calendario: {name, date, daysAway} o None."""
    today = today or date.today()
    best = None
    for ev in events or []:
        try:
            d = datetime.strptime(ev["date"], "%Y-%m-%d").date()
        except Exception:  # noqa: BLE001
            continue
        days = (d - today).days
        if days < 0:
            continue
        if best is None or days < best["daysAway"]:
            best = {"name": ev.get("name", "Evento"), "date": ev["date"],
                    "daysAway": days, "note": ev.get("note")}
    return best


def build_verdict(row, ev):
    """Lectura en una frase: por que ahora y no otro dia.

    Solo usa numeros medidos (precio actual, media de 30d, tu precio de compra)
    y el calendario que TU has rellenado. No predice nada.
    """
    price = row.get("price")
    avg30 = (row.get("stats30d") or {}).get("avg")
    bits = []
    if price and avg30:
        pct = round((price - avg30) / avg30 * 100)
        if pct <= -8:
            bits.append(f"{abs(pct)}% por debajo de su media de 30 dias")
        elif pct >= 8:
            bits.append(f"{pct}% por encima de su media de 30 dias")
        else:
            bits.append(f"en su media de 30 dias ({pct:+d}%)")
    if row.get("netProfitUnit") is not None:
        n = row["netProfitUnit"]
        verb = "ganas " if n >= 0 else "pierdes "
        bits.append(verb + fmt_coins(abs(n)) + " netas por carta")
    if ev and ev["daysAway"] <= 7:
        if ev["daysAway"] == 0:
            when = "hoy"
        elif ev["daysAway"] == 1:
            when = "manana"
        else:
            when = f"en {ev['daysAway']} dias"
        bits.append(f"{ev['name']} {when}")
    return " - ".join(bits) if bits else None


def check_alert(player, row, ev):
    """Texto del alerta o None. Modos: every | below | above | off.

    Los alertas de objetivo solo saltan cuando el precio CRUZA el valor,
    no cada 30 min mientras siga al otro lado.
    """
    mode = player.get("alertMode", "off")
    target = player.get("targetPrice")
    price = row.get("price")
    prev = row.get("prevPrice")
    name = row.get("name") or f"Carta {row['cardId']}"
    verdict = row.get("verdict")
    tail = (f"\n{verdict}" if verdict else "") + f"\n{row.get('url', '')}"

    if not price:
        return None
    if mode == "every":
        return f"{name}: {fmt_coins(price)} monedas{tail}"
    if mode in ("below", "above") and target:
        if mode == "below":
            crossed = price <= target and (prev is None or prev > target)
            verb = "ha bajado a"
        else:
            crossed = price >= target and (prev is None or prev < target)
            verb = "ha subido a"
        if crossed:
            net = net_after_tax(price)
            return (
                f"{name} {verb} {fmt_coins(price)} monedas "
                f"(objetivo: {fmt_coins(target)})\n"
                f"Neto si vendes ahora: {fmt_coins(net)}{tail}"
            )
    return None


def main():
    platform = os.environ.get("PLATFORM", "ps5")
    now = int(time.time())

    cfg_path = os.path.join(DATA, "players.json")
    cfg = load_json(cfg_path, {"settings": {}, "players": []})
    platform = cfg.get("settings", {}).get("platform") or platform
    players = cfg.get("players", [])
    events = load_json(os.path.join(DATA, "events.json"), {"events": []}).get("events", [])
    ev = next_event(events)

    changed_cfg = False
    for p in players:
        if not p.get("cardId"):
            ids = futgg.parse_player_url(p.get("url", ""))
            if ids:
                p["eaId"], p["cardId"] = ids
                changed_cfg = True
    players = [p for p in players if p.get("cardId")]

    if not players:
        print("Watchlist vacia. Anade jugadores desde la app o en data/players.json")
        save_json(os.path.join(DATA, "summary.json"), {
            "generatedAt": now, "platform": platform, "players": [],
            "nextEvent": ev, "portfolio": None, "eaTax": EA_TAX,
        })
        return

    manifest = futgg.get_manifest()
    price_map = futgg.get_price_map(platform, manifest)
    published_at = futgg.get_prices_published_at(manifest, platform) or now
    print(f"[precios] {len(price_map)} cartas | publicado hace {(now - published_at) // 60} min")

    core = playstyles_map = None
    need_meta = [p for p in players if not load_json(
        os.path.join(META_DIR, f"{p['cardId']}.json"), {}).get("name")]
    if need_meta:
        try:
            core = futgg.get_core_data(manifest)
            playstyles_map = futgg.get_playstyles_map(manifest)
        except Exception as e:  # noqa: BLE001
            print(f"[meta] core data no disponible: {e}")

    rows = []
    alerts = []
    inv_cost = 0
    inv_value = 0

    for p in players:
        meta = ensure_meta(p, core, playstyles_map)
        price = price_map.get(p["cardId"]) or None
        hist = append_history(p["cardId"], published_at, price or 0)

        valid = [pt for pt in hist["points"][:-1] if pt[1]]
        prev = valid[-1][1] if valid else None
        p24 = price_at(hist, 24 * 3600, now)
        p7 = price_at(hist, 7 * 86400, now)

        buy = p.get("buyPrice") or None
        qty = p.get("qty") or (1 if buy else 0)
        net = net_after_tax(price)
        net_profit_unit = (net - buy) if (net and buy) else None

        if buy and qty:
            inv_cost += buy * qty
            if net:
                inv_value += net * qty

        row = {
            "cardId": p["cardId"],
            "eaId": p.get("eaId"),
            "url": p.get("url"),
            "name": meta.get("name"),
            "rating": meta.get("overall"),
            "position": meta.get("positionName"),
            "rarityName": meta.get("rarityName"),
            "clubName": meta.get("clubName"),
            "cardImageUrl": meta.get("cardImageUrl"),
            "price": price,
            "prevPrice": prev,
            "netNow": net,
            "price24hAgo": p24,
            "change24h": (price - p24) if (price and p24) else None,
            "change7d": (price - p7) if (price and p7) else None,
            "stats7d": window_stats(hist, 7, now),
            "stats30d": window_stats(hist, 30, now),
            "buyPrice": buy,
            "qty": qty,
            "netProfitUnit": net_profit_unit,
            "netProfitTotal": (net_profit_unit * qty) if (net_profit_unit is not None and qty) else None,
            "targetPrice": p.get("targetPrice"),
            "alertMode": p.get("alertMode", "off"),
            "tag": p.get("tag", "watch"),   # squad | watch | invest
            "note": p.get("note"),
            "extinct": price is None,
        }
        row["verdict"] = build_verdict(row, ev)

        alert = check_alert(p, row, ev)
        if alert:
            alerts.append((alert, row["cardId"], row.get("url")))
        rows.append(row)

    for text, card_id, url in alerts:
        send_notification(text, url=url, tag=f"card-{card_id}")

    portfolio = None
    if inv_cost:
        portfolio = {
            "cost": inv_cost,
            "netValue": inv_value,
            "netProfit": inv_value - inv_cost,
            "pct": round((inv_value - inv_cost) / inv_cost * 100, 1),
        }

    save_json(os.path.join(DATA, "summary.json"), {
        "generatedAt": now,
        "pricesPublishedAt": published_at,
        "platform": platform,
        "eaTax": EA_TAX,
        "nextEvent": ev,
        "portfolio": portfolio,
        "players": rows,
    })

    if changed_cfg:
        cfg["players"] = [
            {k: v for k, v in p.items() if not k.startswith("_")} for p in players
        ]
        save_json(cfg_path, cfg)

    print(f"[ok] {len(players)} jugador(es), {len(alerts)} alerta(s)")


if __name__ == "__main__":
    main()
