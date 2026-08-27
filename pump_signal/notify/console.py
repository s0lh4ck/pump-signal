"""Notificador por consola: imprime una tabla rankeada de candidatos."""

from __future__ import annotations

from pump_signal.models import TokenScore

try:
    from rich.console import Console
    from rich.table import Table

    _HAS_RICH = True
except ImportError:
    _HAS_RICH = False


class ConsoleNotifier:
    def __init__(self) -> None:
        self._console = Console() if _HAS_RICH else None

    async def notify(self, ranked: list[TokenScore]) -> None:
        if not ranked:
            return
        if _HAS_RICH:
            self._print_rich(ranked)
        else:
            self._print_plain(ranked)

    def _print_rich(self, ranked: list[TokenScore]) -> None:
        table = Table(title="🚀 Top candidatos FOMO (pump.fun)")
        table.add_column("#", justify="right")
        table.add_column("Symbol")
        table.add_column("Score", justify="right")
        table.add_column("Social", justify="right")
        table.add_column("Engag.", justify="right")
        table.add_column("Cross", justify="right")
        table.add_column("OnChain", justify="right")
        table.add_column("Narr.", justify="right")
        table.add_column("Timing", justify="right")
        table.add_column("Risk", justify="right")
        table.add_column("Notas")

        for i, score in enumerate(ranked, start=1):
            b = score.breakdown.as_dict()
            table.add_row(
                str(i),
                score.candidate.symbol,
                f"{b['total']:.1f}",
                f"{b['social_velocity']:.1f}",
                f"{b['engagement_quality']:.1f}",
                f"{b['cross_platform']:.1f}",
                f"{b['onchain_momentum']:.1f}",
                f"{b['narrative']:.1f}",
                f"{b['timing']:.1f}",
                f"{b['risk_penalty']:.1f}",
                "; ".join(score.notes) or "-",
            )
        self._console.print(table)

    def _print_plain(self, ranked: list[TokenScore]) -> None:
        print("\n=== Top candidatos FOMO (pump.fun) ===")
        for i, score in enumerate(ranked, start=1):
            b = score.breakdown.as_dict()
            print(f"{i}. {score.candidate.symbol}  score={b['total']:.1f}  {b}")
            if score.notes:
                print(f"   notas: {'; '.join(score.notes)}")
