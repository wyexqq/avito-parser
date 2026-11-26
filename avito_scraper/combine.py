from __future__ import annotations

from .urls import absolutize


def combine(listing_item: dict, card_data: dict | None) -> dict:
    record = dict(listing_item)
    if record.get("url"):
        record["url"] = absolutize(record["url"])

    if not card_data:
        record["params"] = {}
        return record

    record["params"] = card_data.get("params") or {}

    fallbacks = {
        "address": "address",
        "title": "card_title",
        "price": "card_price",
        "description": "card_description",
        "seller_name": "card_seller_name",
        "seller_type": "card_seller_type",
    }
    for field, card_key in fallbacks.items():
        if record.get(field) in (None, "") and card_data.get(card_key):
            record[field] = card_data[card_key]

    return record
