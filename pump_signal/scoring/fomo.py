"""Motor de scoring FOMO.

Cada sub-score se calcula por separado y luego se combina en un ``ScoreBreakdown``.
Todas las funciones son puras (sin I/O) para poder testearlas con datos sintéticos
y para que los pesos se puedan afinar sin tocar los conectores.

Filosofía del score (pensado para el objetivo "convertir capital pequeño en
grande", es decir: priorizar convexidad, no solo "está subiendo"):

- social_velocity   -> ¿la conversación está ACELERANDO, no solo activa?
- engagement_quality-> ¿son cuentas reales/orgánicas o farming de bots?
- cross_platform    -> ¿el hype aparece en más de un canal independiente?
- onchain_momentum  -> ¿el interés se traduce en compras reales en cadena?
- narrative         -> ¿encaja con narrativas que históricamente generan FOMO?
- timing            -> ¿todavía está temprano (market cap bajo, curva con
                        recorrido), que es la única forma de que un x1000 sea
                        matemáticamente posible?
- risk_penalty      -> señales de rug/manipulación que restan del total.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

from pump_signal.config import Weights
from pump_signal.models import (
    OnChainSnapshot,
    ScoreBreakdown,
    SocialMention,
    TokenCandidate,
    TokenScore,
)


def _saturating(x: float, k: float) -> float:
    """Mapea x en [0, inf) a [0, 1) con retornos decrecientes (evita que un
    outlier puntual dispare el score sin límite)."""
    if x <= 0:
        return 0.0
    return 1 - math.exp(-x / k)


def _in_window(
    items: Sequence[SocialMention], now: datetime, minutes: float
) -> list[SocialMention]:
    cutoff = now - timedelta(minutes=minutes)
    return [m for m in items if cutoff <= m.timestamp <= now]


def social_velocity_score(
    mentions: Sequence[SocialMention], now: datetime, window_minutes: float, max_points: float
) -> float:
    half = window_minutes / 2
    recent_cutoff = now - timedelta(minutes=half)
    prior_cutoff = now - timedelta(minutes=window_minutes)
    recent = [m for m in mentions if recent_cutoff <= m.timestamp <= now]
    prior = [m for m in mentions if prior_cutoff <= m.timestamp < recent_cutoff]

    recent_count = len(recent)
    prior_count = len(prior)
    unique_recent_authors = len({m.author_id for m in recent})

    growth = (recent_count - prior_count) / max(prior_count, 1)
    growth = max(0.0, min(growth, 5.0))

    raw = recent_count * (1 + growth) + unique_recent_authors * 0.5
    return max_points * _saturating(raw, k=20)


def engagement_quality_score(
    mentions: Sequence[SocialMention], now: datetime, window_minutes: float, max_points: float
) -> float:
    recent = _in_window(mentions, now, window_minutes)
    if not recent:
        return 0.0

    by_author: dict[str, list[SocialMention]] = {}
    for m in recent:
        by_author.setdefault(m.author_id, []).append(m)

    author_scores = []
    for author_mentions in by_author.values():
        avg_age = sum(m.author_account_age_days for m in author_mentions) / len(author_mentions)
        avg_followers = sum(m.author_followers for m in author_mentions) / len(author_mentions)
        avg_engagement = sum(m.engagement for m in author_mentions) / len(author_mentions)

        age_factor = min(avg_age / 180, 1.0)  # cuentas >= 6 meses cuentan como "maduras"
        follower_factor = _saturating(avg_followers, k=2000)
        author_scores.append(avg_engagement * (0.4 + 0.3 * age_factor + 0.3 * follower_factor))

    # más autores únicos = más orgánico (penaliza el farming de 2-3 cuentas)
    diversity_bonus = _saturating(len(by_author), k=8)
    raw = (sum(author_scores) / len(author_scores)) * diversity_bonus
    return max_points * _saturating(raw, k=50)


def cross_platform_score(
    mentions: Sequence[SocialMention], now: datetime, window_minutes: float, max_points: float
) -> float:
    recent = _in_window(mentions, now, window_minutes)
    counts: dict[str, int] = {}
    for m in recent:
        counts[m.platform] = counts.get(m.platform, 0) + 1

    # solo cuenta una plataforma si tiene señal mínima (evita 1 mención suelta)
    qualifying = {p for p, c in counts.items() if c >= 2}
    n = len(qualifying)
    fraction = {0: 0.0, 1: 0.0, 2: 0.6, 3: 0.85}.get(n, 1.0)
    return max_points * fraction


def narrative_score(
    mentions: Sequence[SocialMention],
    now: datetime,
    window_minutes: float,
    keywords: Sequence[str],
    max_points: float,
) -> float:
    recent = _in_window(mentions, now, window_minutes)
    if not recent or not keywords:
        return 0.0
    lowered = [k.lower() for k in keywords]
    hits = sum(1 for m in recent if any(k in m.text.lower() for k in lowered))
    return max_points * (hits / len(recent))


def onchain_momentum_score(snapshots: Sequence[OnChainSnapshot], max_points: float) -> float:
    if len(snapshots) < 2:
        return 0.0
    ordered = sorted(snapshots, key=lambda s: s.timestamp)
    first, last = ordered[0], ordered[-1]
    minutes = max((last.timestamp - first.timestamp).total_seconds() / 60, 0.5)

    mcap_growth_rate = (
        (last.market_cap_usd - first.market_cap_usd) / max(first.market_cap_usd, 1) / minutes
    )
    buyer_growth = (last.unique_buyers - first.unique_buyers) / max(first.unique_buyers, 1)
    buys = max(last.buy_count - first.buy_count, 0)
    sells = max(last.sell_count - first.sell_count, 0)
    buy_sell_ratio = buys / max(sells, 1)
    curve_rate = (last.bonding_curve_progress - first.bonding_curve_progress) / minutes

    raw = (
        _saturating(max(mcap_growth_rate, 0) * 100, k=20) * 0.4
        + _saturating(max(buyer_growth, 0), k=2) * 0.25
        + _saturating(max(buy_sell_ratio - 1, 0), k=3) * 0.2
        + _saturating(max(curve_rate, 0) * 100, k=10) * 0.15
    )
    return max_points * raw


def timing_score(
    candidate: TokenCandidate,
    snapshots: Sequence[OnChainSnapshot],
    now: datetime,
    max_points: float,
) -> float:
    age_minutes = max((now - candidate.created_at).total_seconds() / 60, 0)
    # ventana de 6h: para que un x1000 sea matemáticamente posible hace falta
    # entrar con market cap bajo y curva de bonding con recorrido.
    age_factor = max(0.0, 1 - age_minutes / 360)

    if not snapshots:
        runway_factor = 1.0  # sin datos aún = todavía en el arranque
    else:
        latest = max(snapshots, key=lambda s: s.timestamp)
        runway_factor = max(0.0, 1 - latest.bonding_curve_progress)

    return max_points * (0.5 * age_factor + 0.5 * runway_factor)


def risk_penalty_score(
    candidate: TokenCandidate,
    snapshots: Sequence[OnChainSnapshot],
    mentions: Sequence[SocialMention],
    now: datetime,
    window_minutes: float,
    max_penalty: float,
) -> tuple[float, list[str]]:
    penalty = 0.0
    notes: list[str] = []

    if candidate.dev_holding_pct >= 0.5:
        penalty += max_penalty * 0.5
        notes.append(f"dev wallet controla {candidate.dev_holding_pct:.0%} del supply")
    elif candidate.dev_holding_pct >= 0.2:
        penalty += max_penalty * 0.25
        notes.append(f"dev wallet controla {candidate.dev_holding_pct:.0%} del supply")

    if not candidate.website and not candidate.twitter_handle and not candidate.telegram_link:
        penalty += max_penalty * 0.2
        notes.append("sin website/twitter/telegram declarados")

    recent = _in_window(mentions, now, window_minutes)
    if snapshots:
        latest = max(snapshots, key=lambda s: s.timestamp)
        if len(recent) >= 10 and latest.unique_buyers <= 2:
            penalty += max_penalty * 0.3
            notes.append("mucho ruido social que no se traduce en compradores on-chain")

    return min(penalty, max_penalty), notes


def score_candidate(
    candidate: TokenCandidate,
    snapshots: Sequence[OnChainSnapshot],
    mentions: Sequence[SocialMention],
    *,
    now: datetime | None = None,
    window_minutes: float = 60.0,
    keywords: Sequence[str] = (),
    weights: Weights | None = None,
) -> TokenScore:
    """Calcula el score FOMO 0-100 para un candidato con su historial reciente."""

    now = now or datetime.now(timezone.utc)
    weights = weights or Weights()
    token_mentions = [m for m in mentions if m.token_ref in (candidate.mint, candidate.symbol)]
    token_snapshots = [s for s in snapshots if s.mint == candidate.mint]

    risk_penalty, risk_notes = risk_penalty_score(
        candidate,
        token_snapshots,
        token_mentions,
        now,
        window_minutes,
        weights.risk_penalty_max,
    )

    breakdown = ScoreBreakdown(
        social_velocity=social_velocity_score(
            token_mentions, now, window_minutes, weights.social_velocity
        ),
        engagement_quality=engagement_quality_score(
            token_mentions, now, window_minutes, weights.engagement_quality
        ),
        cross_platform=cross_platform_score(
            token_mentions, now, window_minutes, weights.cross_platform
        ),
        onchain_momentum=onchain_momentum_score(token_snapshots, weights.onchain_momentum),
        narrative=narrative_score(
            token_mentions, now, window_minutes, keywords, weights.narrative
        ),
        timing=timing_score(candidate, token_snapshots, now, weights.timing),
        risk_penalty=risk_penalty,
    )

    return TokenScore(candidate=candidate, breakdown=breakdown, computed_at=now, notes=risk_notes)
