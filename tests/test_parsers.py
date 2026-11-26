from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from avito_scraper.card import parse_card
from avito_scraper.combine import combine
from avito_scraper.listing import (
    extract_catalog_items,
    parse_listing,
    parse_listing_item,
)
from avito_scraper.urls import build_listing_url
from avito_scraper.config import CATEGORIES


_ITEMS = [
    {
        "id": 123456,
        "urlPath": "/sochi/kvartiry/1-k._kvartira_30m_55et._123456?context=AbC",
        "title": "1-к. квартира, 30 м², 5/5 эт.",
        "description": 'Полное описание с { фигурными } скобками и "кавычками".',
        "priceDetailed": {"value": 5500000, "string": "5 500 000"},
        "normalizedPrice": "180 000 ₽ за м²",
        "location": {"name": "Сочи"},
        "addressDetailed": {"locationName": "Центральный район"},
        "coords": {"lat": "43.5", "lng": "39.7", "address_user": "ул. Ленина, 1"},
        "developmentName": "ЖК «Пример»",
        "isReserved": False,
        "sortTimeStamp": 1718900000000,
        "iva": {
            "UserInfoStep": [{"payload": {"profile": {"title": "Иван"}}}],
            "SecondLineStep": [{"payload": {"value": "Агентство"}}],
        },
    },
    {
        "id": 789,
        "urlPath": "/sochi/kvartiry/studiya_789",
        "title": "Студия",
        "description": "Без типа продавца",
        "priceDetailed": {"value": 3000000},
        "location": {"name": "Сочи"},
        "sortTimeStamp": 1718000000000,
        "iva": {"UserInfoStep": [{"payload": {"profile": {"title": "Пётр"}}}]},
    },
]

def _mfe_html(items: list[dict]) -> str:
    state = {"state": {"data": {"catalog": {"items": items}}}}
    payload = json.dumps(state, ensure_ascii=False)
    return (
        '<html><head></head><body>'
        '<script type="mime/invalid" data-mfe-state="true">'
        f"{payload}</script></body></html>"
    )


_LISTING_HTML = _mfe_html(_ITEMS)
_EMPTY_HTML = _mfe_html([])

_CARD_HTML = """
<html><body>
  <h1 data-marker="item-view/title-info">1-к. квартира, 30 м², 5/5 эт.</h1>
  <span data-marker="item-view/item-price" content="5500000">5 500 000 ₽</span>
  <div data-marker="item-view/item-description">Полное описание.</div>
  <ul data-marker="item-view/item-params">
    <li>Площадь: 30 м²</li>
    <li>Этаж: 5 из 5</li>
    <li>Количество комнат: 1</li>
  </ul>
  <span data-marker="item-view/item-id">№ 123456</span>
  <span data-marker="item-view/item-date">размещено вчера в 12:00</span>
  <div data-marker="seller-info/name">Иван</div>
  <div data-marker="seller-info/label">Агентство</div>
  <div itemtype="http://schema.org/PostalAddress">Сочи, ул. Примерная, 1</div>
</body></html>
"""


def test_extract_catalog_items():
    items = extract_catalog_items(_LISTING_HTML)
    assert len(items) == 2
    assert items[0]["id"] == 123456


def test_extract_empty():
    assert extract_catalog_items(_EMPTY_HTML) == []


def test_parse_listing_item():
    item = parse_listing_item(_ITEMS[0])
    assert item["id"] == 123456
    assert item["price"] == 5500000
    assert item["title"].startswith("1-к")
    assert item["location"] == "Сочи"
    assert item["seller_name"] == "Иван"
    assert item["seller_type"] == "Агентство"
    assert item["published_at"] is not None
    assert "{" in item["description"]
    assert item["address"] == "ул. Ленина, 1"
    assert item["lat"] == "43.5" and item["lng"] == "39.7"
    assert item["price_per_m2"] == "180 000 ₽ за м²"
    assert item["development"] == "ЖК «Пример»"
    assert item["rooms"] == 1
    assert item["area"] == 30.0
    assert item["floor"] == 5 and item["floors"] == 5


def test_title_studio():
    item = parse_listing_item(_ITEMS[1])
    assert item["rooms"] == "студия"


def test_seller_type_nullable():
    item = parse_listing_item(_ITEMS[1])
    assert item["seller_type"] is None


def test_parse_card():
    card = parse_card(_CARD_HTML)
    assert card["address"] == "Сочи, ул. Примерная, 1"
    assert card["params"]["Площадь"] == "30 м²"
    assert card["params"]["Этаж"] == "5 из 5"
    assert card["card_price"] == 5500000


def test_combine():
    items = parse_listing(_LISTING_HTML)
    card = parse_card(_CARD_HTML)
    record = combine(items[0], card)
    assert record["url"].startswith("https://www.avito.ru/")
    assert record["address"] == "ул. Ленина, 1"
    assert record["params"]["Количество комнат"] == "1"


def test_combine_no_card():
    items = parse_listing(_LISTING_HTML)
    record = combine(items[0], None)
    assert record["address"] == "ул. Ленина, 1"
    assert record["params"] == {}
    assert record["rooms"] == 1


def test_combine_card_address_fallback():
    items = parse_listing(_LISTING_HTML)
    card = parse_card(_CARD_HTML)
    item = dict(items[0])
    item["address"] = None
    record = combine(item, card)
    assert record["address"] == "Сочи, ул. Примерная, 1"


def test_build_listing_url():
    cat = CATEGORIES["kvartiry"]
    assert build_listing_url(cat, 1) == (
        "https://www.avito.ru/sochi/kvartiry/prodam-ASgBAgICAUSSA8YQ"
    )
    assert build_listing_url(cat, 2).endswith("?p=2")


def _run_all():
    funcs = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in funcs:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL  {fn.__name__}: {exc}")
    print(f"\n{len(funcs) - failed}/{len(funcs)} прошло")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
