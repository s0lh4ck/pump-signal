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

- Cada ciclo consulta **varias fuentes independientes (10+)** repartidas en
  **6 categorías**, no solo precio técnico:
  1. Técnico/precio (RSI, MACD, medias móviles, Bollinger Bands, soporte/resistencia)
  2. Sentimiento (Fear & Greed Index)
  3. Derivados (funding rate, open interest)
  4. On-chain (flujos a/desde exchanges, actividad de ballenas)
  5. Correlación con BTC (ETH suele seguir a BTC de cerca — una señal de ETH
     que ignora lo que hace BTC es una señal incompleta)
  6. Calendario macro (eventos como CPI/FOMC que pueden invalidar el
     análisis técnico en minutos)
  7. Ballenas individuales y figuras públicas — **peso bajo, explícito**.
     Transferencias de whale-alert (dirección casi siempre ambigua: una
     transferencia entre wallets desconocidas no dice si es venta, custodia
     o un movimiento OTC) y declaraciones de figuras conocidas del sector
     (funds, CEOs, cuentas influyentes). Esta categoría **nunca decide la
     dirección por sí sola** — solo matiza la confianza cuando coincide o
     contradice a las demás. Motivo: es la categoría con más ruido y más
     riesgo de manipulación (shilling pagado, pump-and-dumps, declaraciones
     que no coinciden con las acciones reales de quien las hace — hay un
     caso real documentado en `signals/history.jsonl` de alguien pidiendo
     públicamente "nunca vendas" el mismo día que su empresa declaraba una
     venta ante el regulador).
- **Siempre se da una dirección clara (long o short)**, la que pese más
  según la evidencia — como haría un analista real. `neutral` se reserva
  solo para un empate genuino (evidencia repartida ~50/50), no como refugio
  cómodo ante cualquier duda.
- Si las fuentes **coinciden** en lo importante, la señal tiene confianza
  alta. Si **discrepan** en un factor decisivo, la confianza baja a
  media/baja — pero la dirección se decide igual por el peso de la mayoría
  de evidencia. La discrepancia se deja anotada en `data_quality` y en
  `reasoning`, nunca oculta: **la incertidumbre se refleja en la confianza,
  no en la falta de señal.** Si una fuente tiene datos claramente obsoletos
  o inconsistentes (p. ej. un precio que no cuadra con el resto), se
  descarta y se anota por qué.
- **Todo trade lleva una relación riesgo/recompensa calculada explícitamente**
  (`trade.risk_reward` en el JSON) — entrada, stop, objetivo, pérdida máxima
  en $, ganancia potencial en $, y el ratio. Si con los niveles técnicos el
  ratio sale malo (arriesgar más de lo que se puede ganar), se ajusta el
  stop/objetivo antes de publicar la señal en vez de operar con una relación
  desfavorable solo porque "los niveles técnicos dan eso".
- Cada ciclo revisa qué pasó con el trade del ciclo anterior — si tocó el
  objetivo, el stop, o sigue pendiente — y lo registra en
  `previous_signal_outcome`. Así hay un histórico verificable de aciertos
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
