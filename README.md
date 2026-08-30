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
4. Una tarea programada despierta la sesión cada pocas horas para repetir el
   ciclo y republicar el dashboard con datos frescos.

## Limitaciones importantes

- Los datos vienen de resúmenes de búsqueda web, no de series de velas exactas.
  No hay RSI/MACD calculado con precisión matemática — son lecturas técnicas
  citadas por las fuentes consultadas.
- Esto **no es asesoramiento financiero**. Los futuros/CFDs son productos
  apalancados de alto riesgo. La decisión y ejecución final es siempre tuya.

## Estructura

- `signals/latest.json` — última señal generada.
- `signals/history.jsonl` — histórico de señales (una por línea).
