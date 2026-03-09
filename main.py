#!/usr/bin/env python3
"""
JARVIS AI — Main Entry Point

Boot up the JARVIS AI assistant.

Usage:
    python main.py
    python main.py --debug
    python main.py --config path/to/settings.yaml
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Ensure project root is in path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))


def setup_logging(settings) -> None:
    """Configure loguru logging from settings."""
    from loguru import logger

    # Remove default handler
    logger.remove()

    # Console handler (stderr, colorized)
    if settings.jarvis.debug:
        logger.add(
            sys.stderr,
            level="DEBUG",
            format=(
                "<dim>{time:HH:mm:ss}</dim> | "
                "<level>{level:<8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
                "<level>{message}</level>"
            ),
            colorize=True,
        )
    else:
        # In non-debug, only show warnings+ on console to keep it clean
        logger.add(
            sys.stderr,
            level="WARNING",
            format="<level>{level:<8}</level> | <level>{message}</level>",
            colorize=True,
        )

    # File handler (always active)
    log_path = settings.log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger.add(
        str(log_path),
        level=settings.logging.level,
        format=settings.logging.format,
        rotation=settings.logging.rotation,
        retention=settings.logging.retention,
        backtrace=True,
        diagnose=True,
    )

    logger.info(f"Logging initialized → {log_path}")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="jarvis",
        description="JARVIS AI — Autonomous Desktop AI Assistant",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode (verbose console logging)",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to settings.yaml (default: config/settings.yaml)",
    )
    return parser.parse_args()


async def boot() -> None:
    """Boot sequence for JARVIS."""
    from loguru import logger

    args = parse_args()

    # ── Load Configuration ────────────────────────────
    from config import get_settings

    try:
        settings = get_settings(args.config)
    except FileNotFoundError as e:
        print(f"❌ Configuration error: {e}")
        sys.exit(1)

    # Apply CLI overrides
    if args.debug:
        settings.jarvis.debug = True
        settings.logging.level = "DEBUG"

    # ── Setup Logging ─────────────────────────────────
    setup_logging(settings)

    logger.info("=" * 60)
    logger.info(
        f"JARVIS v{settings.jarvis.version} booting on "
        f"{settings.resolve_platform()}"
    )
    logger.info("=" * 60)

    # ── Create & Start Assistant ──────────────────────
    from core.assistant import Assistant

    assistant = Assistant(settings)

    try:
        await assistant.start()
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)


def cli_entry() -> None:
    """CLI entry point (for pyproject.toml scripts)."""
    asyncio.run(boot())


if __name__ == "__main__":
    asyncio.run(boot())
