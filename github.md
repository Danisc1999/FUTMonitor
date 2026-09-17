repo: drizaogythub97/fut-monitor
branch: main

## Last sync

date: 2026-09-17T08:11:00Z

### Updated in this project

- Motor de recogida adaptado de EA FC 26 a FC 27 (`GAME = "27"`).
- Añadido precio de compra, cantidad y beneficio neto con el 5% de impuesto de EA.
- Añadido recorrido min/max y media de 30 días, y calendario de eventos propio (`data/events.json`).
- Interfaz rehecha como app móvil (`FUT Monitor.dc.html`); Telegram es el canal principal de alertas.

## Screen map

| Pantalla | Construida a partir de |
| --- | --- |
| FUT Monitor.dc.html | `data/summary.json` que genera `collector/collector.py` (origen: `collector/collector.py`, `index.html` del repo) |
| collector/futgg.py | `collector/futgg.py` del repo, con `GAME` en 27 y posiciones en español |
| collector/collector.py | `collector/collector.py` del repo, ampliado con cartera, stats y eventos |
| collector/notify.py | `collector/notify.py` del repo, textos en español |
| workflow-monitor.yml | `workflow-monitor.yml` del repo |
