"""Orquestador: arranca los conectores configurados en paralelo, y cada
poll_interval_seconds recalcula el score FOMO de todos los candidatos
activos, rankea y notifica."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from pump_signal.config import Settings
from pump_signal.connectors.base import Connector, Registry
from pump_signal.models import TokenScore
from pump_signal.scoring.fomo import score_candidate
from pump_signal.storage import Storage

logger = logging.getLogger(__name__)


def build_connectors(settings: Settings, registry: Registry, demo: bool) -> list[Connector]:
    connectors: list[Connector] = []

    if demo:
        from pump_signal.connectors.demo import DemoConnector

        connectors.append(DemoConnector(registry))
        return connectors

    from pump_signal.connectors.pumpfun import PumpPortalConnector

    connectors.append(
        PumpPortalConnector(
            registry,
            ws_url=settings.pumpfun_ws_url,
            min_market_cap_usd=settings.min_market_cap_usd,
            max_market_cap_usd=settings.max_market_cap_usd,
        )
    )

    if settings.twitter_bearer_token:
        from pump_signal.connectors.twitter import TwitterConnector

        connectors.append(
            TwitterConnector(
                registry,
                bearer_token=settings.twitter_bearer_token,
                poll_interval_seconds=settings.poll_interval_seconds,
            )
        )
    else:
        logger.warning("TWITTER_BEARER_TOKEN no configurado: conector de X desactivado")

    if settings.telegram_api_id and settings.telegram_api_hash and settings.telegram_session_string:
        from pump_signal.connectors.telegram import TelegramConnector

        connectors.append(
            TelegramConnector(
                registry,
                api_id=settings.telegram_api_id,
                api_hash=settings.telegram_api_hash,
                session_string=settings.telegram_session_string,
                channels=settings.telegram_channels,
            )
        )
    else:
        logger.warning(
            "TELEGRAM_API_ID/API_HASH/SESSION_STRING no configurados: conector de Telegram desactivado"
        )

    if settings.cryptopanic_token:
        from pump_signal.connectors.news import CryptoPanicConnector

        connectors.append(CryptoPanicConnector(registry, auth_token=settings.cryptopanic_token))

    return connectors


def build_notifiers(settings: Settings) -> list:
    from pump_signal.notify.console import ConsoleNotifier

    notifiers: list = [ConsoleNotifier()]

    if settings.discord_webhook_url:
        from pump_signal.notify.webhook import WebhookNotifier

        notifiers.append(WebhookNotifier(settings.discord_webhook_url))

    if settings.telegram_bot_token and settings.telegram_alert_chat_id:
        from pump_signal.notify.telegram_bot import TelegramBotNotifier

        notifiers.append(
            TelegramBotNotifier(settings.telegram_bot_token, settings.telegram_alert_chat_id)
        )

    return notifiers


async def scoring_loop(
    settings: Settings, registry: Registry, storage: Storage, notifiers: list
) -> None:
    while True:
        await asyncio.sleep(settings.poll_interval_seconds)
        await registry.prune()
        candidates, snapshots_by_mint, mentions_by_ref = await registry.snapshot_state()
        if not candidates:
            continue

        now = datetime.now(timezone.utc)
        all_snapshots = [s for snaps in snapshots_by_mint.values() for s in snaps]
        all_mentions = [m for mentions in mentions_by_ref.values() for m in mentions]

        scores: list[TokenScore] = []
        for candidate in candidates:
            market_cap = _latest_market_cap(snapshots_by_mint.get(candidate.mint, []))
            if market_cap and not (
                settings.min_market_cap_usd <= market_cap <= settings.max_market_cap_usd
            ):
                continue
            score = score_candidate(
                candidate,
                all_snapshots,
                all_mentions,
                now=now,
                window_minutes=settings.rolling_window_minutes,
                keywords=settings.trending_keywords,
                weights=settings.weights,
            )
            scores.append(score)
            storage.save_score(score)

        scores.sort(key=lambda s: s.breakdown.total, reverse=True)
        top = scores[: settings.top_n]

        for notifier in notifiers:
            try:
                await notifier.notify(top)
            except Exception:
                logger.exception("fallo notificando con %s", type(notifier).__name__)


def _latest_market_cap(snapshots: list) -> float | None:
    if not snapshots:
        return None
    return max(snapshots, key=lambda s: s.timestamp).market_cap_usd


async def run(settings: Settings, demo: bool = False) -> None:
    registry = Registry(
        window_minutes=settings.rolling_window_minutes,
        candidate_ttl_minutes=settings.candidate_ttl_minutes,
    )
    storage = Storage(settings.db_path)
    connectors = build_connectors(settings, registry, demo=demo)
    notifiers = build_notifiers(settings)

    if not connectors:
        raise RuntimeError(
            "no hay ningún conector activo: configura al menos pump.fun (siempre activo salvo "
            "en modo demo) o revisa tu .env"
        )

    logger.info(
        "arrancando orquestador con conectores: %s", [c.name for c in connectors]
    )

    tasks = [asyncio.create_task(c.run_forever_with_backoff()) for c in connectors]
    tasks.append(asyncio.create_task(scoring_loop(settings, registry, storage, notifiers)))

    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            task.cancel()
