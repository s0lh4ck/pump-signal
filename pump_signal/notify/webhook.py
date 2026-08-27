"""Notificador vía webhook genérico (Discord/Slack aceptan JSON con campo
"content" para un mensaje de texto simple)."""

from __future__ import annotations

import logging

import aiohttp

from pump_signal.models import TokenScore

logger = logging.getLogger(__name__)


class WebhookNotifier:
    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url

    async def notify(self, ranked: list[TokenScore]) -> None:
        if not ranked:
            return
        lines = ["**Top candidatos FOMO (pump.fun)**"]
        for i, score in enumerate(ranked, start=1):
            b = score.breakdown.as_dict()
            lines.append(
                f"{i}. `{score.candidate.symbol}` score={b['total']:.1f} "
                f"(social={b['social_velocity']:.1f} onchain={b['onchain_momentum']:.1f} "
                f"cross={b['cross_platform']:.1f} risk={b['risk_penalty']:.1f})"
            )
        content = "\n".join(lines)
        try:
            async with aiohttp.ClientSession() as session:
                await session.post(self.webhook_url, json={"content": content}, timeout=10)
        except Exception:
            logger.exception("fallo enviando notificación por webhook")
