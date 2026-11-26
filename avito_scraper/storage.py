from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("avito_scraper.storage")

RESULTS_DIR = Path("data/results")


def save_json(
    records: list[dict],
    category_key: str,
    existing_path: Path | None = None,
    out_dir: Path = RESULTS_DIR,
) -> Path:
    if existing_path is not None:
        path = existing_path
    else:
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = out_dir / f"{category_key}_{stamp}.json"

    payload = {
        "category": category_key,
        "scraped_at": datetime.now(tz=timezone.utc).isoformat(),
        "count": len(records),
        "items": records,
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("Сохранено %d записей в %s", len(records), path)
    return path
