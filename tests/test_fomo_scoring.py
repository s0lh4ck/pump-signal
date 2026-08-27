from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pump_signal.config import Weights
from pump_signal.models import OnChainSnapshot, Platform, SocialMention, TokenCandidate
from pump_signal.scoring.fomo import score_candidate

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
WINDOW = 60.0


def _candidate(symbol: str = "HOT", created_minutes_ago: float = 30, dev_holding_pct: float = 0.05) -> TokenCandidate:
    return TokenCandidate(
        mint=f"mint-{symbol.lower()}",
        symbol=symbol,
        name=symbol,
        created_at=NOW - timedelta(minutes=created_minutes_ago),
        dev_holding_pct=dev_holding_pct,
        website="https://example.com",
        twitter_handle=f"@{symbol.lower()}",
    )


def _mention(symbol: str, minutes_ago: float, platform: Platform = Platform.TWITTER, author: str = "a1", followers=500, age_days=200, engagement=20, text="") -> SocialMention:
    return SocialMention(
        platform=platform,
        token_ref=symbol,
        timestamp=NOW - timedelta(minutes=minutes_ago),
        author_id=author,
        author_followers=followers,
        author_account_age_days=age_days,
        engagement=engagement,
        text=text,
    )


def _snapshot(mint: str, minutes_ago: float, market_cap: float, buys: int, sells: int, buyers: int, progress: float) -> OnChainSnapshot:
    return OnChainSnapshot(
        mint=mint,
        timestamp=NOW - timedelta(minutes=minutes_ago),
        market_cap_usd=market_cap,
        buy_count=buys,
        sell_count=sells,
        unique_buyers=buyers,
        bonding_curve_progress=progress,
    )


def test_accelerating_candidate_outscores_flat_candidate():
    hot = _candidate("HOT")
    cold = _candidate("COLD")

    # HOT: pocas menciones hace tiempo, muchas ahora (aceleración real)
    hot_mentions = [_mention("HOT", m, author=f"u{m}") for m in [50, 45]] + [
        _mention("HOT", m, author=f"u{m}") for m in [10, 8, 6, 5, 4, 3, 2, 1]
    ]
    # COLD: mismo volumen total pero constante, sin aceleración
    cold_mentions = [_mention("COLD", m, author=f"u{m}") for m in [55, 50, 45, 40, 30, 20, 10, 5]]

    hot_snapshots = [
        _snapshot("mint-hot", 50, 5000, 1, 0, 1, 0.05),
        _snapshot("mint-hot", 1, 40000, 40, 3, 25, 0.4),
    ]
    cold_snapshots = [
        _snapshot("mint-cold", 50, 5000, 1, 0, 1, 0.05),
        _snapshot("mint-cold", 1, 5200, 3, 2, 2, 0.06),
    ]

    hot_score = score_candidate(
        hot, hot_snapshots, hot_mentions, now=NOW, window_minutes=WINDOW
    )
    cold_score = score_candidate(
        cold, cold_snapshots, cold_mentions, now=NOW, window_minutes=WINDOW
    )

    assert hot_score.breakdown.total > cold_score.breakdown.total
    assert hot_score.breakdown.social_velocity > cold_score.breakdown.social_velocity
    assert hot_score.breakdown.onchain_momentum > cold_score.breakdown.onchain_momentum


def test_cross_platform_bonus_rewards_multi_channel_hype():
    candidate = _candidate("MULTI")
    multi_platform_mentions = [
        _mention("MULTI", 5, platform=Platform.TWITTER, author="a1"),
        _mention("MULTI", 5, platform=Platform.TWITTER, author="a2"),
        _mention("MULTI", 4, platform=Platform.TELEGRAM, author="a3"),
        _mention("MULTI", 4, platform=Platform.TELEGRAM, author="a4"),
        _mention("MULTI", 3, platform=Platform.NEWS, author="a5"),
        _mention("MULTI", 3, platform=Platform.NEWS, author="a6"),
    ]
    single_platform_mentions = [
        _mention("MULTI", 5, platform=Platform.TWITTER, author="a1"),
        _mention("MULTI", 5, platform=Platform.TWITTER, author="a2"),
        _mention("MULTI", 4, platform=Platform.TWITTER, author="a3"),
        _mention("MULTI", 4, platform=Platform.TWITTER, author="a4"),
        _mention("MULTI", 3, platform=Platform.TWITTER, author="a5"),
        _mention("MULTI", 3, platform=Platform.TWITTER, author="a6"),
    ]

    multi_score = score_candidate(candidate, [], multi_platform_mentions, now=NOW, window_minutes=WINDOW)
    single_score = score_candidate(candidate, [], single_platform_mentions, now=NOW, window_minutes=WINDOW)

    assert multi_score.breakdown.cross_platform > single_score.breakdown.cross_platform


def test_high_dev_holding_triggers_risk_penalty_and_lowers_total():
    safe = _candidate("SAFE", dev_holding_pct=0.03)
    risky = _candidate("RISKY", dev_holding_pct=0.7)

    mentions_safe = [_mention("SAFE", m, author=f"u{m}") for m in range(1, 6)]
    mentions_risky = [_mention("RISKY", m, author=f"u{m}") for m in range(1, 6)]

    safe_score = score_candidate(safe, [], mentions_safe, now=NOW, window_minutes=WINDOW)
    risky_score = score_candidate(risky, [], mentions_risky, now=NOW, window_minutes=WINDOW)

    assert risky_score.breakdown.risk_penalty > safe_score.breakdown.risk_penalty
    assert risky_score.breakdown.total < safe_score.breakdown.total
    assert any("dev wallet" in note for note in risky_score.notes)


def test_timing_score_favors_early_low_progress_over_late_stage():
    early = _candidate("EARLY", created_minutes_ago=10)
    late = _candidate("LATE", created_minutes_ago=300)

    early_snapshots = [_snapshot("mint-early", 5, 6000, 5, 1, 3, 0.1)]
    late_snapshots = [_snapshot("mint-late", 5, 140000, 5, 1, 3, 0.95)]

    early_score = score_candidate(early, early_snapshots, [], now=NOW, window_minutes=WINDOW)
    late_score = score_candidate(late, late_snapshots, [], now=NOW, window_minutes=WINDOW)

    assert early_score.breakdown.timing > late_score.breakdown.timing


def test_narrative_score_reflects_keyword_density():
    candidate = _candidate("NARR")
    hype_mentions = [
        _mention("NARR", 5, author="a1", text="this is the next 100x moon gem, ape in"),
        _mention("NARR", 4, author="a2", text="going viral, send it to the moon"),
    ]
    flat_mentions = [
        _mention("NARR", 5, author="a1", text="saw this token today"),
        _mention("NARR", 4, author="a2", text="not sure about this one"),
    ]

    hype_score = score_candidate(
        candidate, [], hype_mentions, now=NOW, window_minutes=WINDOW, keywords=["moon", "100x", "gem", "viral"]
    )
    flat_score = score_candidate(
        candidate, [], flat_mentions, now=NOW, window_minutes=WINDOW, keywords=["moon", "100x", "gem", "viral"]
    )

    assert hype_score.breakdown.narrative > flat_score.breakdown.narrative


def test_score_stays_within_bounds():
    candidate = _candidate("EXTREME", dev_holding_pct=0.9)
    mentions = [_mention("EXTREME", m, author=f"u{m}", engagement=10000, followers=1_000_000) for m in range(60)]
    snapshots = [_snapshot("mint-extreme", m, 1_000_000 * (m + 1), m * 50, 0, m * 20, 1.0) for m in range(30, 0, -1)]

    score = score_candidate(candidate, snapshots, mentions, now=NOW, window_minutes=WINDOW, weights=Weights())
    assert 0.0 <= score.breakdown.total <= 100.0
