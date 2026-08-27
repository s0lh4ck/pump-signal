"""Estructuras de datos compartidas por todo el pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Platform(str, Enum):
    PUMPFUN = "pumpfun"
    TWITTER = "twitter"
    TELEGRAM = "telegram"
    NEWS = "news"


@dataclass
class TokenCandidate:
    """Un token de pump.fun bajo seguimiento."""

    mint: str
    symbol: str
    name: str
    created_at: datetime
    dev_wallet: str | None = None
    dev_holding_pct: float = 0.0
    website: str | None = None
    twitter_handle: str | None = None
    telegram_link: str | None = None


@dataclass
class OnChainSnapshot:
    """Foto del estado on-chain de un token en un instante dado."""

    mint: str
    timestamp: datetime
    market_cap_usd: float
    buy_count: int
    sell_count: int
    unique_buyers: int
    bonding_curve_progress: float  # 0.0 - 1.0


@dataclass
class SocialMention:
    """Una mención de un token en una red social."""

    platform: Platform
    token_ref: str  # símbolo, mint o texto que hizo match
    timestamp: datetime
    author_id: str
    author_followers: int = 0
    author_account_age_days: int = 0
    engagement: int = 0  # likes + retweets + respuestas / reacciones
    text: str = ""


@dataclass
class ScoreBreakdown:
    """Desglose del score FOMO. Cada campo ya viene escalado a su rango máximo."""

    social_velocity: float
    engagement_quality: float
    cross_platform: float
    onchain_momentum: float
    narrative: float
    timing: float
    risk_penalty: float

    @property
    def total(self) -> float:
        raw = (
            self.social_velocity
            + self.engagement_quality
            + self.cross_platform
            + self.onchain_momentum
            + self.narrative
            + self.timing
            - self.risk_penalty
        )
        return max(0.0, min(100.0, raw))

    def as_dict(self) -> dict[str, float]:
        return {
            "social_velocity": round(self.social_velocity, 2),
            "engagement_quality": round(self.engagement_quality, 2),
            "cross_platform": round(self.cross_platform, 2),
            "onchain_momentum": round(self.onchain_momentum, 2),
            "narrative": round(self.narrative, 2),
            "timing": round(self.timing, 2),
            "risk_penalty": round(-self.risk_penalty, 2),
            "total": round(self.total, 2),
        }


@dataclass
class TokenScore:
    candidate: TokenCandidate
    breakdown: ScoreBreakdown
    computed_at: datetime
    notes: list[str] = field(default_factory=list)
