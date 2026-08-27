"""Conector de X/Twitter. Usa la API v2 oficial (tweepy) buscando cashtags
($SYMBOL) de los tokens actualmente en seguimiento.

Requiere un Bearer Token de un proyecto de X API (el nivel "recent search"
tiene cuota limitada en los planes bajos; ajusta poll_interval_seconds si
te quedas sin cuota, 429 = rate limit).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from pump_signal.connectors.base import Connector, Registry
from pump_signal.models import Platform, SocialMention

logger = logging.getLogger(__name__)


class TwitterConnector(Connector):
    name = "twitter"

    def __init__(
        self,
        registry: Registry,
        bearer_token: str,
        poll_interval_seconds: int = 30,
        max_symbols_per_query: int = 10,
    ) -> None:
        super().__init__(registry)
        self.poll_interval_seconds = poll_interval_seconds
        self.max_symbols_per_query = max_symbols_per_query
        try:
            import tweepy
        except ImportError as exc:
            raise RuntimeError("instala 'tweepy' para usar TwitterConnector") from exc
        self._client = tweepy.Client(bearer_token=bearer_token, wait_on_rate_limit=True)
        self._seen_ids: set[str] = set()

    async def run(self) -> None:
        while True:
            candidates, _, _ = await self.registry.snapshot_state()
            symbols = [c.symbol for c in candidates if c.symbol][: self.max_symbols_per_query]
            if symbols:
                await self._poll_symbols(symbols)
            await asyncio.sleep(self.poll_interval_seconds)

    async def _poll_symbols(self, symbols: list[str]) -> None:
        query = " OR ".join(f"${s}" for s in symbols) + " -is:retweet"
        loop = asyncio.get_event_loop()
        try:
            response = await loop.run_in_executor(
                None,
                lambda: self._client.search_recent_tweets(
                    query=query,
                    max_results=50,
                    tweet_fields=["created_at", "public_metrics", "author_id"],
                    expansions=["author_id"],
                    user_fields=["public_metrics", "created_at"],
                ),
            )
        except Exception:
            logger.exception("fallo consultando X search_recent_tweets")
            return

        if not response or not response.data:
            return

        users_by_id = {u.id: u for u in (response.includes or {}).get("users", [])}

        for tweet in response.data:
            if tweet.id in self._seen_ids:
                continue
            self._seen_ids.add(tweet.id)

            author = users_by_id.get(tweet.author_id)
            followers = 0
            account_age_days = 0
            if author is not None:
                followers = (author.public_metrics or {}).get("followers_count", 0)
                if getattr(author, "created_at", None):
                    account_age_days = (datetime.now(timezone.utc) - author.created_at).days

            metrics = tweet.public_metrics or {}
            engagement = (
                metrics.get("like_count", 0)
                + metrics.get("retweet_count", 0) * 2
                + metrics.get("reply_count", 0)
            )

            matched_symbol = next((s for s in symbols if f"${s.lower()}" in tweet.text.lower()), None)
            if not matched_symbol:
                continue

            mention = SocialMention(
                platform=Platform.TWITTER,
                token_ref=matched_symbol,
                timestamp=tweet.created_at or datetime.now(timezone.utc),
                author_id=str(tweet.author_id),
                author_followers=followers,
                author_account_age_days=account_age_days,
                engagement=engagement,
                text=tweet.text,
            )
            await self.registry.add_mention(mention)

        # evita que _seen_ids crezca sin límite
        if len(self._seen_ids) > 5000:
            self._seen_ids = set(list(self._seen_ids)[-2000:])
