"""Configuración del orquestador, cargada desde variables de entorno / .env."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_list(name: str, default: list[str] | None = None) -> list[str]:
    raw = os.getenv(name)
    if not raw:
        return default or []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw else default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw else default


@dataclass
class Weights:
    """Pesos máximos de cada componente del score FOMO (0-100 en total)."""

    social_velocity: float = 25.0
    engagement_quality: float = 15.0
    cross_platform: float = 15.0
    onchain_momentum: float = 25.0
    narrative: float = 10.0
    timing: float = 10.0
    risk_penalty_max: float = 30.0


@dataclass
class Settings:
    # pump.fun / PumpPortal (feed público en tiempo real de tokens y trades)
    pumpfun_ws_url: str = field(
        default_factory=lambda: os.getenv("PUMPFUN_WS_URL", "wss://pumpportal.fun/api/data")
    )

    # X / Twitter (API v2, requiere bearer token)
    twitter_bearer_token: str | None = field(
        default_factory=lambda: os.getenv("TWITTER_BEARER_TOKEN") or None
    )

    # Telegram (Telethon, requiere api_id/api_hash + session string generada una vez)
    telegram_api_id: int | None = field(
        default_factory=lambda: (
            int(os.environ["TELEGRAM_API_ID"]) if os.getenv("TELEGRAM_API_ID") else None
        )
    )
    telegram_api_hash: str | None = field(
        default_factory=lambda: os.getenv("TELEGRAM_API_HASH") or None
    )
    telegram_session_string: str | None = field(
        default_factory=lambda: os.getenv("TELEGRAM_SESSION_STRING") or None
    )
    telegram_channels: list[str] = field(
        default_factory=lambda: _env_list("TELEGRAM_CHANNELS")
    )

    # Noticias (opcional, CryptoPanic)
    cryptopanic_token: str | None = field(
        default_factory=lambda: os.getenv("CRYPTOPANIC_TOKEN") or None
    )

    # Notificaciones
    discord_webhook_url: str | None = field(
        default_factory=lambda: os.getenv("DISCORD_WEBHOOK_URL") or None
    )
    telegram_bot_token: str | None = field(
        default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN") or None
    )
    telegram_alert_chat_id: str | None = field(
        default_factory=lambda: os.getenv("TELEGRAM_ALERT_CHAT_ID") or None
    )

    # Comportamiento del orquestador
    poll_interval_seconds: int = field(
        default_factory=lambda: _env_int("POLL_INTERVAL_SECONDS", 30)
    )
    rolling_window_minutes: int = field(
        default_factory=lambda: _env_int("ROLLING_WINDOW_MINUTES", 60)
    )
    candidate_ttl_minutes: int = field(
        default_factory=lambda: _env_int("CANDIDATE_TTL_MINUTES", 180)
    )
    top_n: int = field(default_factory=lambda: _env_int("TOP_N", 5))
    min_market_cap_usd: float = field(
        default_factory=lambda: _env_float("MIN_MARKET_CAP_USD", 3000)
    )
    max_market_cap_usd: float = field(
        default_factory=lambda: _env_float("MAX_MARKET_CAP_USD", 150000)
    )
    db_path: str = field(default_factory=lambda: os.getenv("DB_PATH", "pump_signal.db"))
    trending_keywords: list[str] = field(
        default_factory=lambda: _env_list(
            "TRENDING_KEYWORDS",
            ["moon", "100x", "1000x", "gem", "ape", "send it", "next pepe", "viral"],
        )
    )

    weights: Weights = field(default_factory=Weights)


def load_settings() -> Settings:
    """Carga la configuración desde el entorno (usa python-dotenv si hay .env)."""
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    return Settings()
