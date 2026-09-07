"""
BLAGOVA_SWEETS Content Agent — CLI entrypoint.

Examples:
  python agent.py --url https://example.com
  python agent.py --url https://example.com --style ironic
  python agent.py --text "Сегодня испекли..." --style warm --platform telegram
"""

from __future__ import annotations

import argparse
import sys

from app.config import get_settings
from app.content_agent import ContentAgent
from app.errors import AppError
from app.logging_setup import setup_logging
from app.models import Goal, KNOWN_STYLES, Platform


def build_parser() -> argparse.ArgumentParser:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        prog="agent.py",
        description="BLAGOVA_SWEETS Content Agent — генерация постов для соцсетей",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url", help="URL страницы-источника")
    source.add_argument("--text", help="Готовый текст-источник вместо URL")

    parser.add_argument(
        "--style",
        default=settings.default_style,
        help=f"Стиль поста (по умолчанию: {settings.default_style}). "
        f"Известные: {', '.join(KNOWN_STYLES)} или произвольная строка",
    )
    parser.add_argument(
        "--platform",
        default=settings.default_platform,
        choices=[p.value for p in Platform],
        help=f"Площадка (по умолчанию: {settings.default_platform})",
    )
    parser.add_argument(
        "--goal",
        default=settings.default_goal,
        choices=[g.value for g in Goal],
        help=f"Цель поста (по умолчанию: {settings.default_goal})",
    )
    parser.add_argument(
        "--max-length",
        type=int,
        default=settings.default_max_length,
        help=f"Максимальная длина поста (по умолчанию: {settings.default_max_length})",
    )
    parser.add_argument("--cta", action="store_true", help="Добавить естественный CTA")
    parser.add_argument("--hashtags", action="store_true", help="Добавить 3–5 хэштегов")
    return parser


def main(argv: list[str] | None = None) -> int:
    # Keep stdout clean for acceptance: only the post (or a short error on stderr).
    setup_logging("WARNING")
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.max_length < 50 or args.max_length > 4000:
        print("Ошибка: --max-length должен быть в диапазоне 50–4000", file=sys.stderr)
        return 1

    try:
        agent = ContentAgent()
        result = agent.generate_post(
            url=args.url,
            text=args.text,
            platform=args.platform,
            style=args.style,
            goal=args.goal,
            max_length=args.max_length,
            cta=args.cta,
            hashtags=args.hashtags,
        )
    except AppError as exc:
        print(f"Ошибка: {exc.message}", file=sys.stderr)
        return 1
    except Exception:  # noqa: BLE001
        import logging

        logging.getLogger(__name__).exception("Unhandled CLI error")
        print("Ошибка: произошёл внутренний сбой приложения", file=sys.stderr)
        return 1

    # Primarily print the ready post (course acceptance)
    print(result.post)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
