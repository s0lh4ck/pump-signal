"""Notificador vía Bot API de Telegram (distinto del conector Telethon: aquí
solo se usa un bot token para *enviar* alertas a un chat/canal propio)."""

from __future__ import annotations

import logging

import aiohttp

from pump_signal.models import TokenScore

logger = logging.getLogger(__name__)


class TelegramBotNotifier:
    def __init__(self, bot_token: str, chat_id: str) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self._url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    async def notify(self, ranked: list[TokenScore]) -> None:
        if not ranked:
            return
        lines = ["🚀 <b>Top candidatos FOMO (pump.fun)</b>"]
        for i, score in enumerate(ranked, start=1):
            b = score.breakdown.as_dict()
            lines.append(f"{i}. <b>{score.candidate.symbol}</b> score={b['total']:.1f}")
        text = "\n".join(lines)
        try:
            async with aiohttp.ClientSession() as session:
                await session.post(
                    self._url,
                    json={"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"},
                    timeout=10,
                )
        except Exception:
            logger.exception("fallo enviando alerta al bot de Telegram")
