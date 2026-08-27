"""Interfaz común para todos los conectores y el registro compartido en
memoria donde vuelcan sus eventos."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from pump_signal.models import OnChainSnapshot, SocialMention, TokenCandidate

logger = logging.getLogger(__name__)


class Registry:
    """Estado compartido en memoria: candidatos activos + su historial
    reciente de snapshots on-chain y menciones sociales. Los conectores
    escriben aquí; el orquestador lee para puntuar."""

    def __init__(self, window_minutes: int = 60, candidate_ttl_minutes: int = 180) -> None:
        self.window_minutes = window_minutes
        self.candidate_ttl_minutes = candidate_ttl_minutes
        self.candidates: dict[str, TokenCandidate] = {}
        self.snapshots: dict[str, deque[OnChainSnapshot]] = defaultdict(lambda: deque(maxlen=500))
        self.mentions: dict[str, deque[SocialMention]] = defaultdict(lambda: deque(maxlen=500))
        self._symbol_to_mint: dict[str, str] = {}
        self.lock = asyncio.Lock()

    async def upsert_candidate(self, candidate: TokenCandidate) -> None:
        async with self.lock:
            self.candidates[candidate.mint] = candidate
            self._symbol_to_mint[candidate.symbol.lower()] = candidate.mint

    async def add_snapshot(self, snapshot: OnChainSnapshot) -> None:
        async with self.lock:
            self.snapshots[snapshot.mint].append(snapshot)

    async def add_mention(self, mention: SocialMention) -> None:
        """token_ref puede venir como símbolo/cashtag; lo normalizamos a mint
        si conocemos ese símbolo, para poder cruzar con snapshots on-chain."""
        async with self.lock:
            ref = mention.token_ref
            mint = self._symbol_to_mint.get(ref.lower())
            if mint:
                mention.token_ref = mint
            self.mentions[mention.token_ref].append(mention)

    def resolve_mint(self, ref: str) -> str | None:
        return self._symbol_to_mint.get(ref.lower())

    async def prune(self, now: datetime | None = None) -> None:
        """Elimina candidatos sin actividad reciente para no puntuar tokens muertos
        indefinidamente."""
        now = now or datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=self.candidate_ttl_minutes)
        async with self.lock:
            stale = []
            for mint, candidate in self.candidates.items():
                snaps = self.snapshots.get(mint)
                last_activity = candidate.created_at
                if snaps:
                    last_activity = max(last_activity, snaps[-1].timestamp)
                mentions = self.mentions.get(mint)
                if mentions:
                    last_activity = max(last_activity, mentions[-1].timestamp)
                if last_activity < cutoff:
                    stale.append(mint)
            for mint in stale:
                self.candidates.pop(mint, None)
                self.snapshots.pop(mint, None)
                self.mentions.pop(mint, None)
                logger.info("pruned inactive candidate %s", mint)

    async def snapshot_state(self) -> tuple[list[TokenCandidate], dict, dict]:
        async with self.lock:
            return (
                list(self.candidates.values()),
                {k: list(v) for k, v in self.snapshots.items()},
                {k: list(v) for k, v in self.mentions.items()},
            )


class Connector(ABC):
    """Un conector alimenta el ``Registry`` con candidatos/snapshots/menciones.
    Debe ser resiliente: si su fuente falla, reintenta con backoff en vez de
    tumbar el orquestador entero."""

    name: str = "connector"

    def __init__(self, registry: Registry) -> None:
        self.registry = registry

    @abstractmethod
    async def run(self) -> None:
        """Bucle infinito (normalmente) que va escribiendo en el registry."""
        raise NotImplementedError

    async def run_forever_with_backoff(
        self, max_backoff_seconds: float = 60.0, initial_backoff_seconds: float = 2.0
    ) -> None:
        backoff = initial_backoff_seconds
        while True:
            try:
                await self.run()
                backoff = initial_backoff_seconds
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("%s crashed, reconnecting in %.1fs", self.name, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, max_backoff_seconds)
