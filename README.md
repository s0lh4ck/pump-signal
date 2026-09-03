# pump-signal

Herramienta de señales **long/short para SOL** pensada para operar
perpetuos con apalancamiento en **Phantom**, donde se puede abrir posición
desde **$5**.

**No ejecuta operaciones.** Genera una lectura razonada (long / short /
neutral) con niveles de entrada, stop loss y take profit orientativos, que
tú ejecutas manualmente en Phantom.

## Cómo funciona

1. No hay acceso desde este entorno a APIs de precios (Binance, CoinGecko,
   etc.) ni a la mayoría de webs — el único canal disponible es búsqueda web.
2. Cada ciclo, Claude busca precio actual, tendencia (1h/24h/7d), niveles
   técnicos y noticias relevantes de SOL, y **razona** sobre esa información
   (no es una fórmula fija) para dar una lectura long/short/neutral con
   niveles orientativos de entrada, stop loss y take profit.
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
  varias categorías, no solo precio técnico:
  1. Técnico/precio (RSI, MACD, medias móviles, Bollinger Bands, soporte/resistencia)
  2. Sentimiento (Fear & Greed Index)
  3. Derivados (funding rate, open interest)
  4. On-chain (flujos a/desde exchanges, actividad de ballenas)
  5. Correlación con BTC/ETH (SOL suele seguir el ánimo general del
     mercado — una señal que ignora lo que hace BTC es una señal incompleta)
  6. Calendario macro (eventos como CPI/FOMC/NFP que pueden invalidar el
     análisis técnico en minutos)
  7. Ballenas individuales y figuras públicas — **peso bajo, explícito**.
     Transferencias on-chain (dirección casi siempre ambigua: una
     transferencia entre wallets desconocidas no dice si es venta, custodia
     o un movimiento OTC) y declaraciones de figuras conocidas del sector
     (funds, CEOs, cuentas influyentes). Esta categoría **nunca decide la
     dirección por sí sola** — solo matiza la confianza cuando coincide o
     contradice a las demás. Motivo: es la categoría con más ruido y más
     riesgo de manipulación (shilling pagado, pump-and-dumps, declaraciones
     que no coinciden con las acciones reales de quien las hace).
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
- **Todo trade lleva entrada, stop loss y take profit explícitos**
  (`trade` en el JSON), con el ratio riesgo/recompensa calculado sobre esos
  niveles de precio. Si el ratio sale malo (arriesgar más de lo que se
  puede ganar), se ajusta el stop/objetivo antes de publicar la señal en
  vez de operar con una relación desfavorable solo porque "los niveles
  técnicos dan eso".
- **El ratio se calcula sobre niveles de precio, no en dólares exactos.**
  Phantom permite abrir posición desde $5 con apalancamiento — el tamaño
  exacto de posición y el apalancamiento los decides tú en la app. Esta
  herramienta no conoce las comisiones/funding exactos de Phantom (no están
  confirmados), así que no calcula P&L en dólares como se hacía antes con
  el coste de apertura de eToro — da dirección y niveles de precio, y tú
  aplicas el tamaño y apalancamiento que decidas. Ten en cuenta que el
  funding rate de un perpetuo apalancado puede comerse una parte relevante
  de la ganancia en posiciones mantenidas muchas horas.
- Cada ciclo revisa qué pasó con el trade del ciclo anterior — si tocó el
  objetivo, el stop, o sigue pendiente — y lo registra en
  `previous_signal_outcome`. Así hay un histórico verificable de aciertos
  reales, no solo la palabra de la IA.
- **Umbral mínimo de verificación (formalizado):** ningún dato técnico
  puntual (precio, RSI, niveles) se da por bueno con una sola fuente si hay
  forma de contrastarlo — se buscan 2-3 fuentes independientes antes de
  confiar en una lectura. Si una fuente cita niveles técnicos inconsistentes
  con el precio actual (p. ej. una resistencia por debajo del precio), es
  señal de dato cacheado/desactualizado y se descarta explícitamente, nunca
  se promedia con las buenas.
- **La dirección no es lo mismo que "listo para operar":** se da dirección
  clara todos los ciclos (regla de arriba), pero cuando la confianza es
  `media` o `baja` de forma sostenida, el dashboard lo señala explícitamente
  como "esperaría mejor confirmación antes de operar esto" en vez de
  presentar ese ciclo como igual de accionable que uno de confianza `alta`.
- **Sin entradas nuevas en la ventana previa a eventos macro binarios**
  (NFP, FOMC, CPI): en las ~24h antes de una publicación de ese tipo, el
  riesgo de que el resultado sea puro azar (no análisis) es demasiado alto
  para abrir una posición nueva — se puede seguir gestionando una posición
  ya abierta, pero no abrir una nueva justo antes.

## Apalancamiento — advertencia explícita

Operar con apalancamiento en un perpetuo (aunque el tamaño de entrada sea
solo $5) multiplica tanto las ganancias como las pérdidas, y una posición
apalancada puede liquidarse (perder el margen por completo) si el precio se
mueve en tu contra lo suficiente antes de que el stop loss se ejecute —
sobre todo en momentos de alta volatilidad o poca liquidez, donde el precio
puede saltar sin ejecutar el stop al nivel exacto. **El stop loss es tu
protección real, no la confianza de la señal: configúralo siempre en la
plataforma en cuanto abras la posición.**

## Limitaciones importantes

- Los datos vienen de resúmenes de búsqueda web, no de series de velas exactas.
  No hay RSI/MACD calculado con precisión matemática propia — son lecturas
  técnicas citadas por las fuentes consultadas, por eso se contrastan varias
  antes de confiar en ellas.
- **El precio del dashboard es un spot agregado, no la cotización exacta
  del perpetuo de SOL en Phantom.** Pueden diferir. **Verifica siempre el
  precio y las condiciones (funding rate, apalancamiento disponible) en la
  app de Phantom antes de ejecutar** — el dashboard es una referencia para
  decidir la dirección, no la fuente de verdad del precio de entrada exacto.
- Esto **no es asesoramiento financiero**. Los perpetuos apalancados son
  productos de alto riesgo, con riesgo de liquidación. La decisión y
  ejecución final es siempre tuya.

## Estructura

- `signals/latest.json` — última señal generada, incluye `data_quality`
  (fuentes consultadas y nivel de acuerdo) y `previous_signal_outcome`
  (seguimiento del escenario anterior).
- `signals/history.jsonl` — histórico de señales de SOL (una por línea).
- `signals/eth_archive/` — histórico completo de la etapa anterior de la
  herramienta (señales ETH/eToro, hasta el 3 sep 2026), conservado como
  referencia. No se actualiza más.
