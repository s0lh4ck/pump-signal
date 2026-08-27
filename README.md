# pump-signal

Orquestador que vigila los tokens nuevos de **pump.fun** y cruza su actividad
on-chain con la actividad social en **X/Twitter**, **Telegram** y noticias
para calcular un **score FOMO (0-100)** por token: una estimación de cuánto
"hype" real y creciente hay detrás de cada uno.

## ⚠️ Antes de nada: qué es esto y qué NO es

- Esto es una herramienta de **detección y ranking de momentum**, no una bola
  de cristal. Convertir 50$ en 50.000$ es un **x1000**: incluso acertando con
  la memecoin "correcta", eso requiere entrar prácticamente en el minuto uno
  y con timing de salida perfecto. La inmensísima mayoría de tokens de
  pump.fun van a 0.
- El score prioriza **convexidad** (tokens muy tempranos, con market cap bajo
  y con aceleración social+on-chain real), que es la única forma de que un
  retorno así sea matemáticamente posible — pero eso no cambia que la base de
  probabilidad de acertar es muy baja y el riesgo es perder el 100% del
  capital en la mayoría de intentos.
- No es asesoramiento financiero. Es una herramienta para **priorizar dónde
  mirar**, no una señal de compra automática. Idealmente se usa junto con tu
  propio criterio (contrato verificado, liquidez, holders, redes sociales
  reales del proyecto, etc.).
- Los pesos del score son un punto de partida razonable, **pensado para
  irse afinando** con datos reales (por eso todo queda guardado en SQLite).

## Cómo funciona

```
pump.fun (PumpPortal ws) ─┐
X / Twitter (polling)     ├─► Registry (memoria) ─► Motor de scoring FOMO ─► Ranking ─► Notificaciones
Telegram (Telethon)       │        │                                                    (consola/Discord/
Noticias (CryptoPanic)    ┘        └─► SQLite (historial de scores)                       Telegram bot)
```

1. **Conectores** (`pump_signal/connectors/`) escuchan cada fuente en
   paralelo y vuelcan eventos a un `Registry` compartido en memoria:
   - `pumpfun.py`: se conecta al websocket público de
     [PumpPortal](https://pumpportal.fun) (`wss://pumpportal.fun/api/data`),
     que emite en tiempo real la creación de tokens nuevos y cada compra/venta.
   - `twitter.py`: hace polling a la API v2 de X buscando cashtags (`$SYMBOL`)
     de los tokens en seguimiento.
   - `telegram.py`: escucha mensajes nuevos (vía Telethon) en los
     canales/grupos que configures, buscando menciones de esos símbolos.
   - `news.py`: opcional, agrega titulares de CryptoPanic que mencionen algún
     símbolo en seguimiento.
   - `demo.py`: genera actividad sintética (sin credenciales) para poder
     ejecutar y ver el sistema funcionando de punta a punta.

2. **Motor de scoring** (`pump_signal/scoring/fomo.py`) calcula, para cada
   token y sobre una ventana temporal deslizante (por defecto 60 min), siete
   componentes:

   | Componente | Máx. pts | Qué mide |
   |---|---|---|
   | `social_velocity` | 25 | ¿La conversación está **acelerando**, no solo activa? Compara la primera vs. segunda mitad de la ventana. |
   | `engagement_quality` | 15 | ¿Son cuentas reales (antigüedad, followers, diversidad de autores) o farming de 2-3 bots? |
   | `cross_platform` | 15 | Bonus si el mismo token está trending en ≥2 canales independientes a la vez (X + Telegram + noticias). |
   | `onchain_momentum` | 25 | Crecimiento real de market cap, compradores únicos, ratio compra/venta y avance de la bonding curve. |
   | `narrative` | 10 | Densidad de keywords asociadas a narrativas que históricamente generan FOMO (`moon`, `100x`, `gem`, `viral`, configurable). |
   | `timing` | 10 | Premia tokens **muy tempranos** (poco tiempo desde creación, bonding curve con recorrido) — condición necesaria para que un x1000 sea posible. |
   | `risk_penalty` | −30 | Resta por señales de riesgo: dev wallet concentrada, sin website/socials, mucho ruido social sin compradores reales. |

   El total se clampa a `[0, 100]`. Todo el motor es puro (sin I/O) y está
   cubierto por tests con datos sintéticos en `tests/test_fomo_scoring.py`.

3. **Orquestador** (`pump_signal/orchestrator.py`) arranca todos los
   conectores en paralelo (con reconexión automática con backoff si una
   fuente falla) y, cada `POLL_INTERVAL_SECONDS`, recalcula el score de todos
   los candidatos activos, rankea el top N y lo:
   - imprime en consola (tabla con `rich`),
   - guarda en SQLite (`pump_signal.db`) para poder revisar el histórico,
   - opcionalmente envía por webhook (Discord/Slack) y/o por un bot de
     Telegram.

4. Los tokens sin actividad reciente se **podan** automáticamente
   (`CANDIDATE_TTL_MINUTES`) para no seguir puntuando tokens muertos.

## Instalación

Requiere Python 3.11+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Probarlo sin ninguna credencial (modo demo)

Genera datos sintéticos: varios tokens "ruido" y un token diseñado para
acelerar su hype y sus compras con el tiempo, para comprobar que el score
efectivamente lo distingue del resto.

```bash
python -m pump_signal run --demo
```

Verás una tabla en consola que se refresca cada `POLL_INTERVAL_SECONDS`
(30s por defecto; bájalo para ver resultados más rápido:
`POLL_INTERVAL_SECONDS=5 python -m pump_signal run --demo`).

## Modo real (`--live`)

1. Copia `.env.example` a `.env` y rellena lo que tengas:

   ```bash
   cp .env.example .env
   ```

2. **pump.fun**: no necesita credenciales, usa el feed público de PumpPortal.

3. **X/Twitter** (opcional): crea un proyecto en
   [developer.x.com](https://developer.x.com), consigue un `Bearer Token` y
   ponlo en `TWITTER_BEARER_TOKEN`. El endpoint de búsqueda reciente tiene
   cuota limitada en los planes bajos — si te da 429, sube
   `POLL_INTERVAL_SECONDS`.

4. **Telegram** (opcional): consigue `api_id`/`api_hash` gratis en
   [my.telegram.org](https://my.telegram.org), y genera una *session string*
   una vez (para no tener que hacer login interactivo dentro del contenedor):

   ```bash
   python -c "
   from telethon.sync import TelegramClient
   from telethon.sessions import StringSession
   with TelegramClient(StringSession(), api_id=TU_API_ID, api_hash='TU_API_HASH') as client:
       print(client.session.save())
   "
   ```

   Copia el string resultante en `TELEGRAM_SESSION_STRING`, y lista los
   canales/grupos públicos a vigilar en `TELEGRAM_CHANNELS` (usernames
   separados por coma).

5. **Noticias** (opcional): token gratuito de
   [CryptoPanic](https://cryptopanic.com/developers/api/) en
   `CRYPTOPANIC_TOKEN`.

6. **Alertas** (opcional): `DISCORD_WEBHOOK_URL` para un webhook de
   Discord/Slack, o `TELEGRAM_BOT_TOKEN` + `TELEGRAM_ALERT_CHAT_ID` (crea un
   bot con [@BotFather](https://t.me/BotFather)) para recibir el top N por
   Telegram.

7. Arranca:

   ```bash
   python -m pump_signal run --live
   ```

## Afinar el score

Los pesos viven en `pump_signal/config.py` (`Weights`) y se pueden ajustar
por variable de entorno o directamente en el código. Como cada score
calculado queda guardado en `pump_signal.db` (tabla `score_history`), puedes
revisar después qué combinación de pesos habría detectado antes a los
tokens que efectivamente pumpearon, e iterar desde ahí.

Otras variables útiles:

- `ROLLING_WINDOW_MINUTES`: ventana temporal para medir velocidad/engagement.
- `MIN_MARKET_CAP_USD` / `MAX_MARKET_CAP_USD`: filtra el universo de
  candidatos por market cap (para no puntuar tokens ya demasiado grandes,
  donde un x1000 ya no es posible).
- `TRENDING_KEYWORDS`: lexicón de narrativa, sepáralo por comas.
- `TOP_N`: cuántos candidatos se notifican por ciclo.

## Tests

```bash
pytest
```

Los tests cubren el motor de scoring (con datos sintéticos deterministas:
aceleración vs. actividad plana, cross-platform, penalización de riesgo,
timing, narrativa) y el `Registry` compartido (resolución de menciones por
símbolo, poda de candidatos inactivos).

## Estructura del proyecto

```
pump_signal/
├── cli.py                 # entrypoint: python -m pump_signal run [--demo|--live]
├── orchestrator.py        # arranca conectores + bucle de scoring/notificación
├── config.py               # Settings + Weights, desde variables de entorno
├── models.py               # dataclasses compartidas
├── storage.py               # persistencia en SQLite del historial de scores
├── connectors/
│   ├── base.py             # Connector base + Registry compartido en memoria
│   ├── pumpfun.py           # PumpPortal websocket (tokens nuevos + trades)
│   ├── twitter.py           # X API v2 (cashtags)
│   ├── telegram.py          # Telethon (canales/grupos configurados)
│   ├── news.py               # CryptoPanic (opcional)
│   └── demo.py               # datos sintéticos, sin credenciales
├── scoring/
│   └── fomo.py               # el motor de scoring en sí, puro y testeado
└── notify/
    ├── console.py, webhook.py, telegram_bot.py
tests/
├── test_fomo_scoring.py
└── test_registry.py
```
