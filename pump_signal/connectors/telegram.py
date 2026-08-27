"""Conector de Telegram vía Telethon, escuchando mensajes nuevos en una
lista configurada de canales/grupos públicos (por ejemplo, canales de
"gem calls" o de la propia comunidad de pump.fun) y buscando menciones de
los símbolos en seguimiento.

Requiere TELEGRAM_API_ID / TELEGRAM_API_HASH (se obtienen gratis en
https://my.telegram.org) y una session string generada una vez de forma
interactiva (ver README) para poder correr sin login manual en el contenedor.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from pump_signal.connectors.base import Connector, Registry
from pump_signal.models import Platform, SocialMention

logger = logging.getLogger(__name__)

_CASHTAG_RE = re.compile(r"\$([A-Za-z0-9]{2,15})")


class TelegramConnector(Connector):
    name = "telegram"

    def __init__(
        self,
        registry: Registry,
        api_id: int,
        api_hash: str,
        session_string: str,
        channels: list[str],
    ) -> None:
        super().__init__(registry)
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_string = session_string
        self.channels = channels
        try:
            from telethon import TelegramClient
            from telethon.sessions import StringSession
        except ImportError as exc:
            raise RuntimeError("instala 'telethon' para usar TelegramConnector") from exc
        self._client = TelegramClient(
            StringSession(session_string), api_id, api_hash
        )

    async def run(self) -> None:
        from telethon import events

        await self._client.start()
        logger.info("conectado a Telegram, escuchando %d canales", len(self.channels))

        @self._client.on(events.NewMessage(chats=self.channels or None))
        async def _handler(event) -> None:
            await self._handle_message(event)

        await self._client.run_until_disconnected()

    async def _handle_message(self, event) -> None:
        text = event.raw_text or ""
        candidates, _, _ = await self.registry.snapshot_state()
        known_symbols = {c.symbol.lower() for c in candidates}

        matches = {m.lower() for m in _CASHTAG_RE.findall(text)}
        # también intenta match directo de símbolos conocidos como palabra suelta
        matches |= {s for s in known_symbols if re.search(rf"\b{re.escape(s)}\b", text.lower())}
        matches &= known_symbols
        if not matches:
            return

        sender = await event.get_sender()
        author_id = str(getattr(sender, "id", "unknown"))
        author_age_days = 0  # Telegram no expone fecha de creación de cuenta vía API

        reactions = 0
        if getattr(event.message, "reactions", None):
            reactions = sum(r.count for r in event.message.reactions.results)

        views = getattr(event.message, "views", 0) or 0

        for symbol in matches:
            mention = SocialMention(
                platform=Platform.TELEGRAM,
                token_ref=symbol,
                timestamp=event.message.date or datetime.now(timezone.utc),
                author_id=author_id,
                author_followers=0,
                author_account_age_days=author_age_days,
                engagement=reactions * 3 + min(views, 5000) // 100,
                text=text,
            )
            await self.registry.add_mention(mention)
