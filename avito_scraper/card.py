from __future__ import annotations

import logging

from bs4 import BeautifulSoup, Tag

logger = logging.getLogger("avito_scraper.card")

_PARSER = "html.parser"


def _text(node: Tag | None) -> str | None:
    if node is None:
        return None
    text = node.get_text(strip=True)
    return text or None


def _by_marker(soup: BeautifulSoup, marker: str) -> Tag | None:
    return soup.select_one(f'[data-marker="{marker}"]')


def _parse_price(soup: BeautifulSoup) -> int | None:
    node = _by_marker(soup, "item-view/item-price")
    if node is None:
        return None
    content = node.get("content")
    if content:
        try:
            return int(float(content))
        except ValueError:
            pass
    text = _text(node)
    if text:
        digits = "".join(ch for ch in text if ch.isdigit())
        if digits:
            return int(digits)
    return None


def _parse_params(soup: BeautifulSoup) -> dict[str, str]:
    container = _by_marker(soup, "item-view/item-params")
    params: dict[str, str] = {}
    if container is None:
        return params
    for li in container.find_all("li"):
        raw = li.get_text(" ", strip=True)
        if ":" in raw:
            key, _, value = raw.partition(":")
            key = key.strip().rstrip(":").strip()
            value = value.strip()
            if key:
                params[key] = value
    return params


def _parse_address(soup: BeautifulSoup) -> str | None:
    node = soup.select_one('[itemtype="http://schema.org/PostalAddress"]')
    if node is None:
        node = soup.select_one('[itemtype="https://schema.org/PostalAddress"]')
    return _text(node)


def parse_card(html: str) -> dict:
    soup = BeautifulSoup(html, _PARSER)

    return {
        "address": _parse_address(soup),
        "params": _parse_params(soup),
        "card_title": _text(_by_marker(soup, "item-view/title-info")),
        "card_price": _parse_price(soup),
        "card_description": _text(_by_marker(soup, "item-view/item-description")),
        "card_id": _text(_by_marker(soup, "item-view/item-id")),
        "card_date": _text(_by_marker(soup, "item-view/item-date")),
        "card_seller_name": _text(_by_marker(soup, "seller-info/name")),
        "card_seller_type": _text(_by_marker(soup, "seller-info/label")),
    }
