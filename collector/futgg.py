"""Cliente para los datos publicos de fut.gg (EA FC 27).

Fuentes:
- https://r2.fut.gg/27/manifest.json        -> hashes actuales de los ficheros de datos
- player-prices-index.v1.<hash>.json        -> lista de cardIds (delta-encoded)
- player-prices-<plat>-dyn.v1.<hash>.json   -> precios alineados al index (offset +1)
- pagina del jugador (HTML)                 -> metadatos de la carta (scrape unico)

Si un dia sale FC 28 y quieres migrar, cambia GAME y nada mas.
"""

import json
import re
import time
import urllib.request

GAME = "27"
R2 = f"https://r2.fut.gg/{GAME}"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

POSITIONS = {
    0: "POR", 2: "CAD", 3: "LD", 5: "DFC", 7: "LI", 8: "CAI",
    10: "MCD", 12: "MD", 14: "MC", 16: "MI", 18: "MCO",
    21: "SD", 23: "ED", 25: "DC", 27: "EI",
}

PLAYER_URL_RE = re.compile(r"fut\.gg/players/(\d+)-[^/]*/(?:%s)-(\d+)" % GAME)


def _get(url, retries=3, timeout=30):
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
                "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
            })
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Fallo al pedir {url}: {last}")


def get_json(url):
    return json.loads(_get(url).decode("utf-8"))


def get_manifest():
    return get_json(f"{R2}/manifest.json")


def parse_player_url(url):
    """Extrae (eaId, cardId) de un enlace de jugador de fut.gg."""
    m = PLAYER_URL_RE.search(url or "")
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def get_price_map(platform="ps5", manifest=None):
    """dict {cardId: precio} para la plataforma ('ps5' = consola, 'pc').

    Precio 0 = sin precio disponible (p.ej. carta extinta en el mercado).
    """
    manifest = manifest or get_manifest()
    idx_hash = manifest["player-prices-index"]
    dyn_hash = manifest[f"player-prices-{platform}-dyn"]
    idx = get_json(f"{R2}/player-prices-index.v1.{idx_hash}.json")
    dyn = get_json(f"{R2}/player-prices-{platform}-dyn.v1.{dyn_hash}.json")

    ids = []
    cur = idx.get("id0", 0)
    for delta in idx["d"]:
        cur += delta
        ids.append(cur)
    prices = dyn["p"]
    # prices tiene un elemento mas que ids: prices[k+1] corresponde a ids[k]
    return {cid: prices[k + 1] for k, cid in enumerate(ids) if k + 1 < len(prices)}


def get_prices_published_at(manifest, platform="ps5"):
    try:
        return int(manifest["_published_at"][f"player-prices-{platform}-dyn"])
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Metadatos de la carta (scrape de la pagina del jugador, una sola vez)
# ---------------------------------------------------------------------------

_NUM_KEYS = [
    "overall", "position", "skillMoves", "weakFoot", "foot", "height", "weight",
    "nationEaId", "leagueEaId", "clubEaId", "basePlayerEaId",
    "facePace", "faceShooting", "facePassing", "faceDribbling",
    "faceDefending", "facePhysicality",
]
_STR_KEYS = ["commonName", "firstName", "lastName", "accelerateType",
             "cardImagePath", "futggCardImagePath", "imagePath", "simpleCardImagePath"]


def _find_num(blob, key):
    m = re.search(re.escape(key) + r":(-?\d+)", blob)
    return int(m.group(1)) if m else None


def _find_str(blob, key):
    m = re.search(re.escape(key) + r':"([^"]*)"', blob)
    return m.group(1) if m else None


def _find_int_list(blob, key):
    m = re.search(re.escape(key) + r":(?:\$R\[\d+\]=)?\[([\d,\s]*)\]", blob)
    if not m:
        return []
    inner = m.group(1).strip()
    return [int(x) for x in inner.split(",") if x.strip()] if inner else []


def scrape_player_meta(url, core=None, playstyles_map=None):
    """Pide la pagina del jugador y extrae los metadatos de la carta."""
    ids = parse_player_url(url)
    if not ids:
        raise ValueError(f"Enlace de fut.gg no valido: {url}")
    ea_id, card_id = ids

    html = _get(url).decode("utf-8", errors="ignore")
    anchor = html.find(f"eaId:{card_id}")
    if anchor == -1:
        anchor = html.find("attributeGkDiving")
    if anchor == -1:
        raise RuntimeError("No encuentro los datos de la carta en la pagina")
    blob = html[max(0, anchor - 8000): anchor + 8000]

    meta = {"eaId": ea_id, "cardId": card_id, "url": url.split("?")[0]}
    for k in _NUM_KEYS:
        meta[k] = _find_num(blob, k)
    for k in _STR_KEYS:
        meta[k] = _find_str(blob, k)
    meta["playstyles"] = _find_int_list(blob, "playstyles")
    meta["playstylesPlus"] = _find_int_list(blob, "playstylesPlus")
    meta["alternativePositionIds"] = _find_int_list(blob, "alternativePositionIds")

    meta["name"] = meta.get("commonName") or " ".join(
        x for x in [meta.get("firstName"), meta.get("lastName")] if x
    )
    meta["positionName"] = POSITIONS.get(meta.get("position"), "?")
    meta["altPositionNames"] = [POSITIONS.get(p, "?") for p in meta["alternativePositionIds"]]

    m = re.search(r'rarityEaId:(\d+)', blob)
    meta["rarityEaId"] = int(m.group(1)) if m else None

    img = meta.get("futggCardImagePath") or meta.get("cardImagePath") or meta.get("imagePath")
    if img:
        meta["cardImageUrl"] = (
            "https://game-assets.fut.gg/cdn-cgi/image/quality=90,format=auto,width=500/" + img
        )

    if core:
        def _lookup(items, ea):
            for it in items or []:
                if it.get("eaId") == ea:
                    return it.get("name")
            return None
        meta["nationName"] = _lookup(core.get("nations"), meta.get("nationEaId"))
        meta["leagueName"] = _lookup(core.get("leagues"), meta.get("leagueEaId"))
        meta["clubName"] = _lookup(core.get("clubs"), meta.get("clubEaId"))
        meta["rarityName"] = _lookup(core.get("rarities"), meta.get("rarityEaId"))
    if playstyles_map:
        meta["playstyleNames"] = [playstyles_map.get(p) for p in meta["playstyles"] if playstyles_map.get(p)]
        meta["playstylePlusNames"] = [playstyles_map.get(p) for p in meta["playstylesPlus"] if playstyles_map.get(p)]

    meta["scrapedAt"] = int(time.time())
    return meta


def get_core_data(manifest=None):
    manifest = manifest or get_manifest()
    return get_json(f"{R2}/fc-core-data.v1.{manifest['fc-core-data']}.json")


def get_playstyles_map(manifest=None):
    manifest = manifest or get_manifest()
    data = get_json(f"{R2}/play-styles.v1.{manifest['play-styles']}.json")
    return {p["eaId"]: p["name"] for p in data}
