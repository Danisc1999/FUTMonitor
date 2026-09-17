"""FUT Monitor ES - escaner semanal de candidatos a TOTW.

Se ejecuta una vez por semana (lunes) via GitHub Actions. Usa API-Football
(https://www.api-football.com/, plan gratis: 100 peticiones/dia) para leer
los resultados REALES del fin de semana en las 5 grandes ligas y sacar quien
ha rendido mejor - goles, asistencias, nota del partido.

IMPORTANTE - esto NO es una prediccion oficial del TOTW. EA no elige solo por
estadisticas: pesa el equipo, la audiencia y decisiones editoriales que no
siguen ninguna formula publica. Esto es "quien lo hizo mejor este fin de
semana", una pista real para adelantarte a comprar su carta de oro (que suele
dejar de salir en sobres, o subir de precio, cuando el jugador saca una carta
especial) - no una garantia.

Variable de entorno necesaria:
  API_FOOTBALL_KEY   tu clave gratuita de https://dashboard.api-football.com
"""

import json
import os
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
API = "https://v3.football.api-sports.io"

# Ids de liga estables de API-Football (documentados publicamente)
LEAGUES = {
    39: "Premier League",
    140: "La Liga",
    135: "Serie A",
    78: "Bundesliga",
    61: "Ligue 1",
}

MIN_RATING = 7.8       # nota minima de partido para entrar en la lista
MIN_GOAL_CONTRIB = 2   # o al menos goles+asistencias combinados


def totw_score(rating, goals, assists, won, drew):
    """Puntuacion 0-100 estimada de opciones de TOTW. NO es oficial de EA:
    EA pesa tambien el equipo, la audiencia y decisiones editoriales sin
    formula publica. Esto es solo una lectura transparente de datos reales:
      - nota de partido (lo que mas pesa)
      - goles + asistencias
      - si el equipo gano o empato
    """
    rating_component = max(0, min(45, ((rating or 6.0) - 6.0) * 15))
    contrib_component = min(30, (goals or 0) * 12 + (assists or 0) * 8)
    result_component = 15 if won else (7 if drew else 0)
    return round(min(100, rating_component + contrib_component + result_component))


def _get(path, params):
    key = os.environ.get("API_FOOTBALL_KEY", "")
    if not key:
        raise RuntimeError("Falta API_FOOTBALL_KEY")
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{API}/{path}?{qs}"
    req = urllib.request.Request(url, headers={"x-apisports-key": key})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def season_for(today):
    # API-Football usa el anio de inicio de temporada (ago-mayo)
    return today.year if today.month >= 7 else today.year - 1


def last_weekend(today):
    # viernes a lunes mas reciente que ya haya pasado
    days_since_friday = (today.weekday() - 4) % 7
    friday = today - timedelta(days=days_since_friday if days_since_friday else 7)
    monday = friday + timedelta(days=3)
    return friday, monday


def scan():
    today = date.today()
    season = season_for(today)
    frm, to = last_weekend(today)
    candidates = []

    for league_id, league_name in LEAGUES.items():
        try:
            fx = _get("fixtures", {
                "league": league_id, "season": season,
                "from": frm.isoformat(), "to": to.isoformat(),
            })
        except Exception as e:  # noqa: BLE001
            print(f"[totw] fallo fixtures {league_name}: {e}")
            continue
        fixtures = fx.get("response", [])
        print(f"[totw] {league_name}: {len(fixtures)} partidos")

        for match in fixtures:
            fixture_id = match["fixture"]["id"]
            home_id = match["teams"]["home"]["id"]
            away_id = match["teams"]["away"]["id"]
            home_goals = match["goals"]["home"] or 0
            away_goals = match["goals"]["away"] or 0
            try:
                pl = _get("fixtures/players", {"fixture": fixture_id})
            except Exception as e:  # noqa: BLE001
                print(f"[totw] fallo player-stats fixture {fixture_id}: {e}")
                continue
            time.sleep(0.3)  # cortesia con el limite diario

            for team_block in pl.get("response", []):
                team_id = team_block.get("team", {}).get("id")
                team_name = team_block.get("team", {}).get("name")
                won = (team_id == home_id and home_goals > away_goals) or (team_id == away_id and away_goals > home_goals)
                drew = home_goals == away_goals
                for p in team_block.get("players", []):
                    stats = (p.get("statistics") or [{}])[0]
                    games = stats.get("games", {}) or {}
                    goals = (stats.get("goals", {}) or {}).get("total") or 0
                    assists = (stats.get("goals", {}) or {}).get("assists") or 0
                    rating_raw = games.get("rating")
                    rating = round(float(rating_raw), 2) if rating_raw else None
                    minutes = games.get("minutes") or 0

                    if minutes < 45:
                        continue
                    contrib = (goals or 0) + (assists or 0)
                    if (rating is not None and rating >= MIN_RATING) or contrib >= MIN_GOAL_CONTRIB:
                        candidates.append({
                            "name": p.get("player", {}).get("name"),
                            "team": team_name,
                            "league": league_name,
                            "rating": rating,
                            "goals": goals,
                            "assists": assists,
                            "minutes": minutes,
                            "matchDate": match["fixture"]["date"][:10],
                            "score": totw_score(rating, goals, assists, won, drew),
                        })

    candidates.sort(key=lambda c: c["score"], reverse=True)
    seen = set()
    top = []
    for c in candidates:
        if c["name"] in seen:
            continue
        seen.add(c["name"])
        top.append(c)
        if len(top) >= 15:
            break

    out = {
        "generatedAt": int(time.time()),
        "weekendFrom": frm.isoformat(),
        "weekendTo": to.isoformat(),
        "leagues": list(LEAGUES.values()),
        "candidates": top,
    }
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, "totw_candidates.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[totw] {len(top)} candidatos guardados")


if __name__ == "__main__":
    scan()
