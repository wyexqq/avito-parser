from __future__ import annotations

from .config import BASE_URL, CITY_SLUG, Category


def build_listing_url(category: Category, page: int = 1, city: str = CITY_SLUG) -> str:
    if page < 1:
        raise ValueError(f"Номер страницы должен быть >= 1, получено {page}")

    base = f"{BASE_URL}/{city}/{category.slug}/prodam-{category.code}"
    if page == 1:
        return base
    return f"{base}?p={page}"


def absolutize(url_path: str) -> str:
    if url_path.startswith("http://") or url_path.startswith("https://"):
        return url_path
    if not url_path.startswith("/"):
        url_path = "/" + url_path
    return BASE_URL + url_path
