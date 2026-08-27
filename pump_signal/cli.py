"""Punto de entrada CLI: `python -m pump_signal run [--demo|--live]`."""

from __future__ import annotations

import asyncio
import logging

import click

from pump_signal.config import load_settings
from pump_signal.orchestrator import run as run_orchestrator


@click.group()
@click.option("--verbose", is_flag=True, default=False, help="Logging en modo DEBUG")
def main(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


@main.command()
@click.option(
    "--demo/--live",
    default=True,
    show_default=True,
    help="--demo genera datos sintéticos (no requiere credenciales). --live usa pump.fun/X/Telegram reales.",
)
def run(demo: bool) -> None:
    """Arranca el orquestador."""
    settings = load_settings()
    try:
        asyncio.run(run_orchestrator(settings, demo=demo))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
