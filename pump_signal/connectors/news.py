"""Conector de noticias/agregadores (opcional). Las memecoins casi nunca
salen en medios "serios", pero CryptoPanic agrega también posts de la
comunidad cripto y puede servir como señal narrativa adicional."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import aiohttp

from pump_signal.connectors.base import Connector, Registry
from pump_signal.models import Platform, SocialMention

logger = logging.getLogger(__name__)

_CRYPTOPANIC_URL = "https://cryptopanic.com/api/v1/posts/"


class CryptoPanicConnector(Connector):
    name = "news"

    def __init__(
        self,
        registry: Registry,
        auth_token: str,
        poll_interval_seconds: int = 120,
    ) -> None:
        super().__init__(registry)
        self.auth_token = auth_token
        self.poll_interval_seconds = poll_interval_seconds
        self._seen_ids: set[str] = set()

    async def run(self) -> None:
        while True:
            candidates, _, _ = await self.registry.snapshot_state()
            symbols = {c.symbol.upper() for c in candidates if c.symbol}
            if symbols:
                await self._poll(symbols)
            await asyncio.sleep(self.poll_interval_seconds)

    async def _poll(self, symbols: set[str]) -> None:
        params = {"auth_token": self.auth_token, "public": "true", "kind": "news"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(_CRYPTOPANIC_URL, params=params, timeout=15) as resp:
                    data = await resp.json()
        except Exception:
            logger.exception("fallo consultando CryptoPanic")
            return

        for post in data.get("results", []):
            post_id = str(post.get("id"))
            if post_id in self._seen_ids:
                continue
            title = post.get("title", "")
            matched = next((s for s in symbols if s.lower() in title.lower()), None)
            if not matched:
                continue
            self._seen_ids.add(post_id)
            mention = SocialMention(
                platform=Platform.NEWS,
                token_ref=matched,
                timestamp=datetime.now(timezone.utc),
                author_id=post.get("source", {}).get("title", "cryptopanic"),
                engagement=post.get("votes", {}).get("positive", 0),
                text=title,
            )
            await self.registry.add_mention(mention)
