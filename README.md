# pump-signal

Herramienta de señales **long/short para ETH** pensada para operar el Micro Ether
Future de eToro (`ETH.SEP26`) con poco capital (margen ~$115 por contrato).

**No ejecuta operaciones.** Genera una lectura razonada (long / short / neutral)
que tú ejecutas manualmente en eToro.

## Cómo funciona

1. No hay acceso desde este entorno a APIs de precios (Binance, CoinGecko, etc.)
   ni a la mayoría de webs — el único canal disponible es búsqueda web.
2. Cada ciclo, Claude busca precio actual, tendencia (1h/24h/7d), niveles técnicos
   y noticias relevantes de ETH, y **razona** sobre esa información (no es una
   fórmula fija) para dar una lectura long/short/neutral con niveles orientativos
   de entrada, stop loss y take profit.
3. El resultado se guarda en `signals/latest.json` y se anexa a
   `signals/history.jsonl`, y se publica como un dashboard web (Artifact) que
   puedes abrir en cualquier momento.
4. Una tarea programada despierta la sesión **cada hora** para repetir el
   ciclo y republicar el dashboard con datos frescos. No es tiempo real: cada
   punto del gráfico es un ciclo de análisis (uno por hora), no un tick de
   mercado — el dashboard no puede conectarse a APIs en vivo (ver
   limitaciones).

## Reglas de fiabilidad

**Ningún sistema es 100% fiable con mercados — ni este, ni ningún otro.** Lo que
sí se puede controlar es no forzar una respuesta cuando la información es débil
o contradictoria:

- Cada ciclo consulta **al menos 3 fuentes independientes** para precio,
  niveles técnicos y noticias.
- Si las fuentes **coinciden** en lo importante (soporte/resistencia,
  dirección del momentum), la señal puede tener confianza alta.
- Si las fuentes **discrepan** en un factor decisivo (p. ej. una dice RSI en
  sobrecompra extrema y otra dice RSI neutral), la señal baja a confianza
  media/baja y el sesgo se mantiene en `neutral` en vez de forzar long o
  short. La discrepancia se deja anotada en `data_quality` y en `reasoning`,
  no se oculta.
- Cada ciclo revisa qué pasó con el escenario (long/short) del ciclo
  anterior — si tocó el objetivo, el stop, o sigue pendiente — y lo registra
  en `previous_signal_outcome`. Así hay un histórico verificable de aciertos
  reales, no solo la palabra de la IA.

## Limitaciones importantes

- Los datos vienen de resúmenes de búsqueda web, no de series de velas exactas.
  No hay RSI/MACD calculado con precisión matemática propia — son lecturas
  técnicas citadas por las fuentes consultadas, por eso se contrastan varias
  antes de confiar en ellas.
- Esto **no es asesoramiento financiero**. Los futuros/CFDs son productos
  apalancados de alto riesgo. La decisión y ejecución final es siempre tuya.

## Estructura

- `signals/latest.json` — última señal generada, incluye `data_quality`
  (fuentes consultadas y nivel de acuerdo) y `previous_signal_outcome`
  (seguimiento del escenario anterior).
- `signals/history.jsonl` — histórico de señales (una por línea).
