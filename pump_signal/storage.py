"""Persistencia ligera en SQLite: historial de scores para poder revisar
después qué candidatos detectó el sistema y cómo evolucionó su score
(útil para ir afinando pesos con datos reales)."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from pump_signal.models import TokenScore

_SCHEMA = """
CREATE TABLE IF NOT EXISTS score_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mint TEXT NOT NULL,
    symbol TEXT NOT NULL,
    computed_at TEXT NOT NULL,
    total_score REAL NOT NULL,
    social_velocity REAL NOT NULL,
    engagement_quality REAL NOT NULL,
    cross_platform REAL NOT NULL,
    onchain_momentum REAL NOT NULL,
    narrative REAL NOT NULL,
    timing REAL NOT NULL,
    risk_penalty REAL NOT NULL,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_score_history_mint ON score_history (mint);
CREATE INDEX IF NOT EXISTS idx_score_history_computed_at ON score_history (computed_at);
"""


class Storage:
    def __init__(self, db_path: str = "pump_signal.db") -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True) if Path(db_path).parent != Path(
            "."
        ) else None
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def save_score(self, score: TokenScore) -> None:
        b = score.breakdown
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO score_history (
                    mint, symbol, computed_at, total_score, social_velocity,
                    engagement_quality, cross_platform, onchain_momentum,
                    narrative, timing, risk_penalty, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    score.candidate.mint,
                    score.candidate.symbol,
                    score.computed_at.isoformat(),
                    b.total,
                    b.social_velocity,
                    b.engagement_quality,
                    b.cross_platform,
                    b.onchain_momentum,
                    b.narrative,
                    b.timing,
                    b.risk_penalty,
                    "; ".join(score.notes),
                ),
            )

    def history_for(self, mint: str, limit: int = 50) -> list[tuple]:
        with self._connect() as conn:
            cur = conn.execute(
                """
                SELECT computed_at, total_score FROM score_history
                WHERE mint = ? ORDER BY computed_at DESC LIMIT ?
                """,
                (mint, limit),
            )
            return cur.fetchall()

    def top_recent(self, since: datetime, limit: int = 20) -> list[tuple]:
        with self._connect() as conn:
            cur = conn.execute(
                """
                SELECT mint, symbol, MAX(total_score) as best_score
                FROM score_history
                WHERE computed_at >= ?
                GROUP BY mint
                ORDER BY best_score DESC
                LIMIT ?
                """,
                (since.isoformat(), limit),
            )
            return cur.fetchall()
