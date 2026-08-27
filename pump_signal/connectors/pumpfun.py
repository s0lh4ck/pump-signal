"""Conector de pump.fun vía el feed público de PumpPortal
(wss://pumpportal.fun/api/data) — websocket gratuito de terceros pensado
para desarrolladores, que emite en tiempo real creación de tokens y trades.

Nota: PumpPortal es un servicio de terceros y su esquema de payloads puede
cambiar. El parseo de abajo es defensivo (usa .get con defaults) y registra
en logs cualquier tipo de mensaje que no reconozca, para poder ajustarlo
rápido si cambia el formato.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

import aiohttp
import websockets

from pump_signal.connectors.base import Connector, Registry
from pump_signal.models import OnChainSnapshot, TokenCandidate

logger = logging.getLogger(__name__)

# Umbral aproximado (en SOL virtuales) al que se considera completada la
# bonding curve de pump.fun. Es un valor de referencia de la comunidad, no un
# valor "oficial" garantizado: ajústalo en tu .env si pump.fun cambia la curva.
BONDING_CURVE_COMPLETION_SOL = 85.0

_COINGECKO_SOL_PRICE_URL = (
    "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd"
)


class SolPriceFeed:
    """Precio de SOL/USD cacheado, con fallback si la API externa falla."""

    def __init__(self, refresh_seconds: float = 120.0, fallback_usd: float = 150.0) -> None:
        self.refresh_seconds = refresh_seconds
        self.fallback_usd = fallback_usd
        self._price = fallback_usd
        self._last_fetch = 0.0

    async def get_price(self) -> float:
        now = time.monotonic()
        if now - self._last_fetch < self.refresh_seconds:
            return self._price
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(_COINGECKO_SOL_PRICE_URL, timeout=10) as resp:
                    data = await resp.json()
                    self._price = float(data["solana"]["usd"])
                    self._last_fetch = now
        except Exception:
            logger.warning("no se pudo refrescar el precio de SOL, usando el último conocido")
        return self._price


class PumpPortalConnector(Connector):
    name = "pumpfun"

    def __init__(
        self,
        registry: Registry,
        ws_url: str = "wss://pumpportal.fun/api/data",
        min_market_cap_usd: float = 0.0,
        max_market_cap_usd: float = float("inf"),
    ) -> None:
        super().__init__(registry)
        self.ws_url = ws_url
        self.min_market_cap_usd = min_market_cap_usd
        self.max_market_cap_usd = max_market_cap_usd
        self.price_feed = SolPriceFeed()

    async def run(self) -> None:
        async with websockets.connect(self.ws_url, ping_interval=20, ping_timeout=20) as ws:
            logger.info("conectado a PumpPortal (%s)", self.ws_url)
            await ws.send(json.dumps({"method": "subscribeNewToken"}))
            async for raw in ws:
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                await self._handle_message(ws, data)

    async def _handle_message(self, ws, data: dict) -> None:
        tx_type = data.get("txType")
        mint = data.get("mint")
        if not mint:
            return

        sol_price = await self.price_feed.get_price()
        v_sol = float(data.get("vSolInBondingCurve", 0.0) or 0.0)
        market_cap_sol = data.get("marketCapSol")
        market_cap_usd = (
            float(market_cap_sol) * sol_price if market_cap_sol is not None else v_sol * sol_price
        )
        progress = min(1.0, v_sol / BONDING_CURVE_COMPLETION_SOL) if v_sol else 0.0

        if tx_type == "create":
            candidate = TokenCandidate(
                mint=mint,
                symbol=data.get("symbol", mint[:6]),
                name=data.get("name", data.get("symbol", mint[:6])),
                created_at=datetime.now(timezone.utc),
                dev_wallet=data.get("traderPublicKey"),
                website=data.get("website"),
                twitter_handle=data.get("twitter"),
                telegram_link=data.get("telegram"),
            )
            await self.registry.upsert_candidate(candidate)
            # nos suscribimos a los trades de este mint concreto para poder
            # calcular momentum on-chain
            try:
                await ws.send(json.dumps({"method": "subscribeTokenTrade", "keys": [mint]}))
            except Exception:
                logger.debug("no se pudo suscribir a trades de %s", mint)
            logger.info("nuevo token detectado: %s (%s)", candidate.symbol, mint)

        if tx_type in ("create", "buy", "sell"):
            if mint not in self.registry.candidates and tx_type != "create":
                # trade de un token que no está registrado como candidato activo
                return
            snapshot = OnChainSnapshot(
                mint=mint,
                timestamp=datetime.now(timezone.utc),
                market_cap_usd=market_cap_usd,
                buy_count=1 if tx_type == "buy" else 0,
                sell_count=1 if tx_type == "sell" else 0,
                unique_buyers=1 if tx_type in ("buy", "create") else 0,
                bonding_curve_progress=progress,
            )
            await self._accumulate_snapshot(snapshot)

    async def _accumulate_snapshot(self, snapshot: OnChainSnapshot) -> None:
        """PumpPortal manda eventos de trade individuales; los acumulamos en
        contadores crecientes para que onchain_momentum_score pueda medir
        velocidad comparando el primer y último snapshot de la ventana."""
        existing = self.registry.snapshots.get(snapshot.mint)
        if existing:
            last = existing[-1]
            snapshot.buy_count += last.buy_count
            snapshot.sell_count += last.sell_count
            snapshot.unique_buyers = max(snapshot.unique_buyers + last.unique_buyers, last.unique_buyers)
        await self.registry.add_snapshot(snapshot)
