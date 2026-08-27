"""Conector de demostración: genera tokens y actividad sintética para poder
ejecutar y ver el orquestador funcionando de punta a punta sin necesitar
ninguna credencial real. Útil también como base para tests manuales.

Simula un puñado de tokens "ruido" con actividad plana/aleatoria y un token
"ganador" cuyo hype y compras aceleran con el tiempo, para comprobar que el
score FOMO efectivamente lo distingue del resto.
"""

from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone

from pump_signal.connectors.base import Connector, Registry
from pump_signal.models import OnChainSnapshot, Platform, SocialMention, TokenCandidate

_WORDS = ["DOGE", "PEPE", "WOJAK", "CHAD", "FROG", "MOON", "BASED", "SIGMA"]


class DemoConnector(Connector):
    name = "demo"

    def __init__(self, registry: Registry, tick_seconds: float = 3.0) -> None:
        super().__init__(registry)
        self.tick_seconds = tick_seconds
        self._tick = 0

    async def run(self) -> None:
        winner = await self._spawn_token("WINCOIN", "The Winning Coin", dev_holding_pct=0.05)
        noise_tokens = [
            await self._spawn_token(f"{w}{random.randint(1,999)}", w, dev_holding_pct=random.uniform(0.1, 0.6))
            for w in random.sample(_WORDS, 4)
        ]

        while True:
            self._tick += 1
            now = datetime.now(timezone.utc)
            await self._simulate_winner(winner, now)
            for token in noise_tokens:
                await self._simulate_noise(token, now)
            await asyncio.sleep(self.tick_seconds)

    async def _spawn_token(self, symbol: str, name: str, dev_holding_pct: float) -> TokenCandidate:
        candidate = TokenCandidate(
            mint=f"demo-{symbol.lower()}",
            symbol=symbol,
            name=name,
            created_at=datetime.now(timezone.utc),
            dev_holding_pct=dev_holding_pct,
            website="https://example.com" if random.random() > 0.3 else None,
            twitter_handle=f"@{symbol.lower()}" if random.random() > 0.3 else None,
        )
        await self.registry.upsert_candidate(candidate)
        return candidate

    async def _simulate_winner(self, token: TokenCandidate, now: datetime) -> None:
        # el hype y las compras aceleran con cada tick
        n_mentions = 1 + self._tick // 2
        for _ in range(n_mentions):
            await self.registry.add_mention(
                SocialMention(
                    platform=random.choice([Platform.TWITTER, Platform.TELEGRAM]),
                    token_ref=token.symbol,
                    timestamp=now,
                    author_id=f"user-{random.randint(1, 500)}",
                    author_followers=random.randint(100, 20000),
                    author_account_age_days=random.randint(30, 900),
                    engagement=random.randint(5, 200),
                    text=f"${token.symbol} to the moon, this is the next 100x gem, ape in now",
                )
            )
        existing = self.registry.snapshots.get(token.mint)
        last_mcap = existing[-1].market_cap_usd if existing else 4000.0
        buys = existing[-1].buy_count if existing else 0
        sells = existing[-1].sell_count if existing else 0
        buyers = existing[-1].unique_buyers if existing else 0
        await self.registry.add_snapshot(
            OnChainSnapshot(
                mint=token.mint,
                timestamp=now,
                market_cap_usd=last_mcap * random.uniform(1.05, 1.25),
                buy_count=buys + random.randint(3, 10),
                sell_count=sells + random.randint(0, 2),
                unique_buyers=buyers + random.randint(2, 6),
                bonding_curve_progress=min(0.9, (existing[-1].bonding_curve_progress if existing else 0.05) + 0.03),
            )
        )

    async def _simulate_noise(self, token: TokenCandidate, now: datetime) -> None:
        if random.random() > 0.4:
            await self.registry.add_mention(
                SocialMention(
                    platform=random.choice([Platform.TWITTER, Platform.TELEGRAM]),
                    token_ref=token.symbol,
                    timestamp=now,
                    author_id=f"user-{random.randint(1, 50)}",
                    author_followers=random.randint(0, 300),
                    author_account_age_days=random.randint(0, 10),
                    engagement=random.randint(0, 5),
                    text=f"{token.symbol} lol",
                )
            )
        existing = self.registry.snapshots.get(token.mint)
        last_mcap = existing[-1].market_cap_usd if existing else 5000.0
        buys = existing[-1].buy_count if existing else 0
        sells = existing[-1].sell_count if existing else 0
        buyers = existing[-1].unique_buyers if existing else 0
        await self.registry.add_snapshot(
            OnChainSnapshot(
                mint=token.mint,
                timestamp=now,
                market_cap_usd=last_mcap * random.uniform(0.95, 1.05),
                buy_count=buys + random.randint(0, 2),
                sell_count=sells + random.randint(0, 2),
                unique_buyers=buyers + random.randint(0, 1),
                bonding_curve_progress=existing[-1].bonding_curve_progress if existing else 0.05,
            )
        )
