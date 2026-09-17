# FUT Monitor ES — mercado de EA FC 27

Monitor de precios del mercado de FC 27 que corre solo y te avisa por Telegram.
Datos reales de los archivos públicos de fut.gg. Coste: 0 €.

No toca tu cuenta de EA en ningún momento, así que no hay riesgo de ban.

## Cómo funciona

```
GitHub Actions (cada 30 min)
  └─ collector/collector.py
       ├─ lee data/players.json (tu watchlist)
       ├─ pide los precios al CDN público de fut.gg (todas las cartas de FC 27)
       ├─ guarda histórico en data/history/<cardId>.json
       ├─ la 1ª vez, saca los metadatos de la carta (stats, imagen, club)
       ├─ calcula media 30d, recorrido min/max y beneficio NETO (−5% de EA)
       ├─ cruza con data/events.json (tu calendario de promos)
       ├─ evalúa tus alertas y las manda por Telegram
       └─ commitea los datos de vuelta al repositorio

GitHub Pages (gratis)
  └─ FUT Monitor.dc.html — la app, que lee data/summary.json
```

## Montaje (~10 minutos)

### 1. Crea el repositorio

En <https://github.com/new>. Nombre sugerido: `fut-monitor`. Déjalo **Public** —
GitHub Pages gratuito lo exige, y los repos públicos tienen minutos de Actions
ilimitados. Dentro solo hay precios de cartas: tu token y tu chat id **no** se
suben al repositorio, van en los secrets.

Sube todos los archivos de este proyecto **excepto ninguna clave** (siguen más
abajo, por chat, nunca como archivo). Sin instalar nada: *Add file → Upload
files* y arrastra: `index.html`, `sw.js`, `icon-180.png`, `icon-192.png`,
`icon-512.png`, `manifest.webmanifest`, `collector/`, `data/`.

El planificador ya está en su sitio correcto: `.github/workflows/monitor.yml`.
No hay que moverlo ni renombrarlo, solo subirlo tal cual (arrastra la carpeta
`.github` entera junto con el resto).

### 2. Crea el bot de Telegram

1. En Telegram habla con **@BotFather** → `/newbot` → nombre y username.
2. Guarda el **token** (formato `1234567:AAAbbb…`).
3. Abre la conversación con TU bot y mándale cualquier mensaje (`hola`).
   Sin esto el bot no puede escribirte.
4. Saca tu **chat id**: abre en el navegador
   `https://api.telegram.org/bot<TU_TOKEN>/getUpdates` y copia el número
   de `"chat":{"id": …}`.

### 3. Guarda los secretos

En el repo: **Settings → Secrets and variables → Actions → New repository secret**

| Nombre | Valor |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | el token de @BotFather |
| `TELEGRAM_CHAT_ID` | tu chat id (número) |

### 4. Activa la web

**Settings → Pages → Build and deployment:** Source `Deploy from a branch`,
rama `main`, carpeta `/ (root)`. En 1–2 minutos estará en
`https://TU_USUARIO.github.io/fut-monitor/`.

GitHub Pages sirve `index.html`, que ya está listo: es la app entera en un solo
archivo, sin dependencias externas. `sw.js` tiene que quedar también en la raíz
del sitio: es lo que registra el canal de notificaciones propio del paso 4c.

### 4b. El icono en el iPhone

1. Abre `https://TU_USUARIO.github.io/fut-monitor/` en **Safari** (en Chrome de
   iOS no sale la opción).
2. Botón de compartir → **Añadir a pantalla de inicio** → Añadir.
3. Se instala con el icono de la moneda y se abre a pantalla completa, sin barra
   de Safari.

El acceso directo es para **mirar** tus jugadores. Las **notificaciones las manda
Telegram**, a tu pantalla de bloqueo, y funcionan aunque nunca abras este icono.
Asegúrate de tener las notificaciones de Telegram activadas para el chat del bot.

### 4c. Notificaciones de la propia app (opcional)

Segundo canal, para no depender solo de Telegram. Los dos pueden convivir: si
tienes ambos configurados, la alerta te llega por los dos.

**Requisitos:** iOS 16.4 o superior, y la app **ya añadida a la pantalla de
inicio** (paso 4b). Sin instalar, iOS no concede el permiso.

1. Abre la app desde el icono de la pantalla de inicio (no desde Safari).
2. Abajo, **Notificaciones en este móvil** → *Activar notificaciones* → Permitir.
3. Te aparece un texto largo. Cópialo con el botón **Copiar**.
4. En el repo: **Settings → Secrets and variables → Actions** y crea:

| Nombre | Valor |
| --- | --- |
| `PUSH_SUBSCRIPTION` | el texto que acabas de copiar |
| `VAPID_PRIVATE_KEY` | la clave privada que te di por chat al montar esto (nunca va como archivo del repo, solo como secret) |
| `VAPID_SUBJECT` | `mailto:tu@correo.com` (opcional) |

**Importante:** esa clave privada no debe subirse nunca como archivo al
repositorio, ni público ni privado — solo pegada en el campo de un secret. La
clave pública ya va dentro de la app y no es secreta; la privada, si se filtra,
permite a otros mandarte notificaciones falsas.

Si algún día dejan de llegar y en el log de Actions ves `suscripcion caducada`,
repite los pasos 1–4: iOS ha rotado la suscripción. Pasa cuando borras el icono
o reinstalas.

### 5. Primera recogida

Pestaña **Actions** → acepta habilitar workflows si lo pide → workflow
**FUT Monitor** → **Run workflow**. A partir de ahí va solo cada 30 minutos.

## Tu watchlist: `data/players.json`

```json
{
  "settings": { "platform": "ps5" },
  "players": [
    {
      "url": "https://www.fut.gg/players/231747-kylian-mbappe/27-XXXXXXXXX/",
      "targetPrice": 900000,
      "alertMode": "below",
      "tag": "watch",
      "buyPrice": null,
      "qty": 0,
      "note": "esperando rebaja por SBC"
    }
  ]
}
```

Pega el enlace de la página del jugador en fut.gg y el recolector saca los ids solo.

| Campo | Qué hace |
| --- | --- |
| `alerts` | lista de reglas: `[{"mode": "below", "target": 300000}, {"mode": "above", "target": 450000}]`. Puedes tener varias a la vez en el mismo jugador — por ejemplo, que te avise si baja de un precio de compra Y si sube de un precio de venta, al mismo tiempo. `mode` es `below` (baja de) · `above` (sube de) · `every` (cada ronda, sin `target`) |
| `tag` | `squad` (lo tienes en el equipo) · `watch` (deseado) · `invest` (comprado para vender). Son las pestañas de la app |
| `buyPrice` | a cuánto lo compraste. **Este es el dato que ninguna web puede saber**, y sin él no hay beneficio neto |
| `qty` | cuántas unidades tienes |

Las alertas de objetivo solo saltan cuando el precio **cruza** el valor. No te
machacan cada 30 minutos mientras siga al otro lado. El formato viejo
(`alertMode`/`targetPrice` sueltos, una sola alerta) se sigue leyendo si ya
tenías jugadores guardados así.

## Tu calendario: `data/events.json`

```json
{
  "events": [
    { "date": "2026-09-25", "name": "TOTW", "note": "" }
  ]
}
```

Aquí solo van fechas que **tú** sepas. El proyecto no inventa ni predice promos.
Cuando un evento está a 7 días o menos, entra en el texto de la alerta: en vez de
"ha bajado a 340.000" recibes "ha bajado a 340.000 — 18% por debajo de su media
de 30 días, ganas 46.000 netas por carta, TOTW en 2 días".

## Ajustes

- **Intervalo:** el `cron` en `.github/workflows/monitor.yml`.
  `*/30 * * * *` = 30 min, `0 * * * *` = 1 h. GitHub puede retrasarse unos
  minutos en horas punta, es normal.
- **Mercado de PC:** cambia `PLATFORM: ps5` por `PLATFORM: pc` en el mismo
  archivo, o `platform` en `data/players.json`.
- **En tu ordenador:** `DRY_RUN=1 python collector/collector.py` imprime las
  alertas en vez de enviarlas. Sin dependencias, Python 3.9+ pelado.

## Límites, sin letra pequeña

- Los precios son los que publica fut.gg, actualizados cada pocos minutos. No es
  el mercado al segundo: para picos de minutos no sirve, para tendencias de días
  y eventos sobra.
- Las cartas **extintas**, sin ninguna a la venta, salen sin precio.
- El histórico y las medias empiezan vacíos. La media de 30 días no significa
  nada hasta que lleves unos días recogiendo.
- Uso personal y moderado de los datos de fut.gg. Una petición cada 30 minutos
  es carga insignificante para ellos; no bajes el cron a cada minuto.
- Actions gratis sobra: cada recogida gasta unos 20 segundos.
- El push nativo de iOS es más caprichoso que Telegram: exige la app instalada
  en la pantalla de inicio y la suscripción caduca si borras el icono. Por eso
  Telegram sigue siendo el canal recomendado y el push va como refuerzo.

## Crédito

El motor de recogida parte de [drizaogythub97/fut-monitor](https://github.com/drizaogythub97/fut-monitor)
(FC 26). Aquí está adaptado a FC 27 y ampliado con precio de compra, beneficio
neto, recorrido de 30 días y calendario de eventos.
