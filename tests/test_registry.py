from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from pump_signal.connectors.base import Registry
from pump_signal.models import OnChainSnapshot, Platform, SocialMention, TokenCandidate

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _candidate(mint="mint-1", symbol="ABC", created_at=NOW) -> TokenCandidate:
    return TokenCandidate(mint=mint, symbol=symbol, name="Abc Coin", created_at=created_at)


@pytest.mark.asyncio
async def test_mention_by_symbol_resolves_to_mint_after_candidate_registered():
    registry = Registry()
    await registry.upsert_candidate(_candidate())

    await registry.add_mention(
        SocialMention(
            platform=Platform.TWITTER,
            token_ref="ABC",
            timestamp=NOW,
            author_id="u1",
        )
    )

    assert "mint-1" in registry.mentions
    assert registry.mentions["mint-1"][0].token_ref == "mint-1"


@pytest.mark.asyncio
async def test_prune_removes_candidates_without_recent_activity():
    registry = Registry(candidate_ttl_minutes=60)
    old_candidate = _candidate(
        mint="mint-old", symbol="OLD", created_at=NOW - timedelta(minutes=200)
    )
    fresh_candidate = _candidate(
        mint="mint-fresh", symbol="FRESH", created_at=NOW - timedelta(minutes=5)
    )
    await registry.upsert_candidate(old_candidate)
    await registry.upsert_candidate(fresh_candidate)

    await registry.prune(now=NOW)

    candidates, _, _ = await registry.snapshot_state()
    symbols = {c.symbol for c in candidates}
    assert symbols == {"FRESH"}


@pytest.mark.asyncio
async def test_prune_keeps_candidate_with_recent_snapshot_even_if_old():
    registry = Registry(candidate_ttl_minutes=60)
    candidate = _candidate(mint="mint-active", symbol="ACTIVE", created_at=NOW - timedelta(hours=5))
    await registry.upsert_candidate(candidate)
    await registry.add_snapshot(
        OnChainSnapshot(
            mint="mint-active",
            timestamp=NOW - timedelta(minutes=1),
            market_cap_usd=5000,
            buy_count=1,
            sell_count=0,
            unique_buyers=1,
            bonding_curve_progress=0.1,
        )
    )

    await registry.prune(now=NOW)

    candidates, _, _ = await registry.snapshot_state()
    assert {c.symbol for c in candidates} == {"ACTIVE"}
