from __future__ import annotations

import json
import logging
import re
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Iterator

logger = logging.getLogger("avito_scraper.listing")

_MFE_STATE_OPEN = re.compile(r'<script\b[^>]*\bdata-mfe-state="true"[^>]*>', re.I)
_PRELOADED_STATE = re.compile(
    r'window\.__preloadedState__\s*=\s*"((?:[^"\\]|\\.)*)"'
)


def _iter_balanced_json_objects(text: str) -> Iterator[str]:
    depth = 0
    start = -1
    in_string = False
    escape = False

    for i, ch in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start != -1:
                    yield text[start : i + 1]
                    start = -1


def _find_catalog_items(node: Any) -> list[dict] | None:
    if isinstance(node, dict):
        catalog = node.get("catalog")
        if isinstance(catalog, dict):
            items = catalog.get("items")
            if isinstance(items, list):
                return items
        for value in node.values():
            found = _find_catalog_items(value)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find_catalog_items(value)
            if found is not None:
                return found
    return None


def _iter_state_candidates(html: str) -> Iterator[str]:
    for m in _MFE_STATE_OPEN.finditer(html):
        start = m.end()
        end = html.find("</script>", start)
        content = (html[start:end] if end != -1 else html[start:]).strip()
        if content:
            yield content

    m = _PRELOADED_STATE.search(html)
    if m:
        try:
            js_unescaped = json.loads('"' + m.group(1) + '"')
            yield urllib.parse.unquote(js_unescaped)
        except (json.JSONDecodeError, ValueError):
            pass


def _parse_candidate(text: str) -> list[dict] | None:
    if "catalog" not in text:
        return None
    try:
        return _find_catalog_items(json.loads(text))
    except (json.JSONDecodeError, ValueError):
        pass
    for candidate in _iter_balanced_json_objects(text):
        if '"catalog"' not in candidate:
            continue
        try:
            data = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        items = _find_catalog_items(data)
        if items is not None:
            return items
    return None


def extract_catalog_items(html: str) -> list[dict]:
    for text in _iter_state_candidates(html):
        items = _parse_candidate(text)
        if items is not None:
            return items

    logger.warning("Не удалось найти catalog.items в HTML страницы списка")
    return []


def _timestamp_to_iso(ts_ms: Any) -> str | None:
    try:
        seconds = int(ts_ms) / 1000
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()


def _seller_name(iva: dict) -> str | None:
    steps = (iva or {}).get("UserInfoStep") or []
    for step in steps:
        title = (step.get("payload") or {}).get("profile", {}).get("title")
        if title:
            return title
    return None


def _seller_type(iva: dict) -> str | None:
    steps = (iva or {}).get("SecondLineStep") or []
    for step in steps:
        value = (step.get("payload") or {}).get("value")
        if value:
            return value
    return None


_TITLE_AREA = re.compile(r"([\d]+(?:[.,]\d+)?)\s*м²")
_TITLE_FLOOR = re.compile(r"(\d+)\s*/\s*(\d+)\s*эт")
_TITLE_ROOMS = re.compile(r"(\d+)\s*-?\s*к")


def _parse_title(title: str) -> dict:
    title = title or ""
    rooms: int | str | None = None
    if "студи" in title.lower():
        rooms = "студия"
    else:
        m = _TITLE_ROOMS.search(title)
        if m:
            rooms = int(m.group(1))

    area = None
    m = _TITLE_AREA.search(title)
    if m:
        try:
            area = float(m.group(1).replace(",", "."))
        except ValueError:
            area = None

    floor = floors = None
    m = _TITLE_FLOOR.search(title)
    if m:
        floor, floors = int(m.group(1)), int(m.group(2))

    return {"rooms": rooms, "area": area, "floor": floor, "floors": floors}


def parse_listing_item(item: dict) -> dict:
    price_detailed = item.get("priceDetailed") or {}
    location = item.get("location") or {}
    address_detailed = item.get("addressDetailed") or {}
    geo = item.get("geo") or {}
    coords = item.get("coords") or {}
    iva = item.get("iva") or {}

    timestamp = item.get("sortTimeStamp") or item.get("allowTimeStamp")
    title = item.get("title")

    record = {
        "id": item.get("id"),
        "url": item.get("urlPath"),
        "title": title,
        "description": item.get("description"),
        "price": price_detailed.get("value"),
        "price_per_m2": item.get("normalizedPrice"),
        "discount_percent": item.get("discountPercent"),
        "address": coords.get("address_user") or geo.get("formattedAddress"),
        "lat": coords.get("lat"),
        "lng": coords.get("lng"),
        "location": location.get("name") or address_detailed.get("locationName"),
        "development": item.get("developmentName"),
        "published_at": _timestamp_to_iso(timestamp),
        "seller_name": _seller_name(iva),
        "seller_type": _seller_type(iva),
        "is_reserved": item.get("isReserved"),
    }
    record.update(_parse_title(title))
    return record


def parse_listing(html: str) -> list[dict]:
    return [parse_listing_item(it) for it in extract_catalog_items(html)]
