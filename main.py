from __future__ import annotations

import argparse
import logging
import sys

from avito_scraper.config import CATEGORIES, Settings
from avito_scraper.scraper import scrape_category


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Парсер недвижимости Авито (Сочи)")
    parser.add_argument(
        "--category",
        default="kvartiry",
        help=f"Ключ категории (по умолчанию kvartiry). Доступно: {', '.join(CATEGORIES)}",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=2,
        help="Лимит страниц списка (по умолчанию 2; 0 = без лимита, до конца пагинации)",
    )
    parser.add_argument(
        "--max-listings",
        type=int,
        default=None,
        help="Лимит числа объявлений (по умолчанию без лимита)",
    )
    parser.add_argument(
        "--no-cards",
        action="store_true",
        help="Не загружать карточки (только данные из списка, без точного адреса/параметров)",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Не сохранять результат в JSON (только лог)",
    )
    parser.add_argument(
        "--list-categories",
        action="store_true",
        help="Показать доступные категории и выйти",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Подробный лог")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    _setup_logging(args.verbose)

    if args.list_categories:
        for key, cat in CATEGORIES.items():
            print(f"{key:16} {cat.title}")
        return 0

    category = CATEGORIES.get(args.category)
    if category is None:
        print(
            f"Неизвестная категория '{args.category}'. Доступно: {', '.join(CATEGORIES)}",
            file=sys.stderr,
        )
        return 2

    settings = Settings()
    max_pages = None if args.max_pages == 0 else args.max_pages

    records = scrape_category(
        category=category,
        settings=settings,
        max_pages=max_pages,
        max_listings=args.max_listings,
        fetch_cards=not args.no_cards,
        save=not args.no_save,
    )

    print(f"Готово: собрано {len(records)} объявлений по категории '{category.title}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
