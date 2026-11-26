from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable

from .card import parse_card
from .client import AvitoClient, FetchResult, rotate_ip
from .combine import combine
from .config import Category, Settings
from .listing import parse_listing
from .storage import save_json
from .urls import absolutize, build_listing_url

logger = logging.getLogger("avito_scraper.scraper")

ProgressCallback = Callable[[str, int, "int | None"], None]


@dataclass
class RunParams:
    settings: Settings
    max_pages: int | None = None
    max_listings: int | None = None
    fetch_cards: bool = True


class RunControl:
    def __init__(self, params: RunParams):
        self.params = params
        self._run = threading.Event()
        self._run.set()
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._dirty = False

    def pause(self) -> None:
        self._run.clear()

    def resume(self, params: RunParams | None = None) -> None:
        with self._lock:
            if params is not None:
                self.params = params
                self._dirty = True
        self._run.set()

    def stop(self) -> None:
        self._stop.set()
        self._run.set()

    def checkpoint(self) -> bool:
        self._run.wait()
        return not self._stop.is_set()

    def pull_params(self) -> RunParams | None:
        with self._lock:
            if self._dirty:
                self._dirty = False
                return self.params
            return None

    def interruptible_sleep(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end and not self._stop.is_set():
            time.sleep(min(0.3, end - time.monotonic()))

    @property
    def is_paused(self) -> bool:
        return not self._run.is_set()

    @property
    def is_stopped(self) -> bool:
        return self._stop.is_set()


def _proxy_label(settings: Settings) -> str:
    if not settings.proxies:
        return "Прокси: не используется (запросы напрямую)"
    url = next(iter(settings.proxies.values()))
    masked = url
    if "@" in url:
        scheme_creds, _, host = url.rpartition("@")
        scheme = scheme_creds.split("://", 1)[0] if "://" in scheme_creds else ""
        masked = f"{scheme}://***@{host}" if scheme else f"***@{host}"
    return f"Прокси: {masked}"


def _cooldown_get(
    client: AvitoClient,
    url: str,
    settings: Settings,
    control: RunControl,
    on_progress: ProgressCallback | None = None,
) -> FetchResult:
    result = client.get(url)
    if not result.blocked:
        return result

    def emit(msg: str) -> None:
        logger.info("%s: %s", msg, url)
        if on_progress:
            on_progress(msg, 0, None)

    for attempt in range(1, settings.block_max_retries + 1):
        if control.is_stopped:
            return result

        emit(
            f"Блок (HTTP {result.status_code}) — попытка {attempt}/"
            f"{settings.block_max_retries}"
        )

        wait = settings.block_cooldown
        if settings.rotate_ip_url:
            emit("Меняю IP…")
            ok, info = rotate_ip(settings.rotate_ip_url, settings.timeout)
            emit(f"Смена IP: {info}")
            if not ok:
                wait = max(settings.block_cooldown, settings.rotate_fail_wait)
                emit("Смена IP не удалась — жду авто-ротацию")

        emit(f"Cooldown {wait:.0f} сек")
        control.interruptible_sleep(wait)
        if control.is_stopped:
            return result

        result = client.get(url)
        if not result.blocked:
            return result

    return result


def scrape_category(
    category: Category,
    settings: Settings | None = None,
    max_pages: int | None = None,
    max_listings: int | None = None,
    fetch_cards: bool = True,
    save: bool = True,
    on_progress: ProgressCallback | None = None,
    control: RunControl | None = None,
) -> list[dict]:
    if control is None:
        control = RunControl(
            RunParams(settings or Settings(), max_pages, max_listings, fetch_cards)
        )

    params = control.params
    records: list[dict] = []
    out_path = None
    est_total: int | None = params.max_listings

    def report(msg: str) -> None:
        if on_progress:
            on_progress(msg, len(records), est_total)

    client = AvitoClient(params.settings)
    report(_proxy_label(params.settings))

    def apply_updates() -> None:
        nonlocal params, client, est_total
        new = control.pull_params()
        if new is None:
            return
        params = new
        client.close()
        client = AvitoClient(params.settings)
        est_total = params.max_listings
        report("Настройки обновлены, продолжаю")
        report(_proxy_label(params.settings))

    try:
        page = 1
        while True:
            if not control.checkpoint():
                report("Остановлено")
                break
            apply_updates()

            if params.max_pages is not None and page > params.max_pages:
                report(f"Достигнут лимит страниц ({params.max_pages})")
                break

            url = build_listing_url(category, page)
            report(f"Загрузка страницы {page}…")
            result = _cooldown_get(client, url, params.settings, control, on_progress)

            if control.is_stopped:
                report("Остановлено")
                break
            if result.blocked:
                report(f"Страница {page} заблокирована после всех повторов")
                break
            if not result.ok:
                report(f"Страница {page} недоступна, пропускаем")
                page += 1
                continue

            items = parse_listing(result.text)
            if not items:
                report(f"Страница {page} пуста — конец пагинации")
                break

            if est_total is None and params.max_pages is not None:
                est_total = params.max_pages * len(items)

            report(f"Страница {page}: {len(items)} объявлений, загружаю карточки…")
            logger.info("Страница %d: получено %d объявлений", page, len(items))

            stopped = False
            for i, item in enumerate(items):
                if not control.checkpoint():
                    stopped = True
                    break
                apply_updates()

                if params.max_listings is not None and len(records) >= params.max_listings:
                    break

                card_data = None
                if params.fetch_cards and item.get("url"):
                    report(
                        f"Стр. {page} — карточка {i + 1}/{len(items)} "
                        f"(всего {len(records) + 1})"
                    )
                    card_data = _fetch_card(
                        client, item["url"], params.settings, control, on_progress
                    )

                records.append(combine(item, card_data))

            if save:
                out_path = save_json(records, category.key, out_path)
                report(f"Сохранено {len(records)} записей")

            if stopped:
                report("Остановлено")
                break
            if params.max_listings is not None and len(records) >= params.max_listings:
                report(f"Достигнут лимит объявлений ({params.max_listings})")
                break

            page += 1
    finally:
        client.close()

    logger.info(
        "Итого собрано %d объявлений по категории '%s'", len(records), category.title
    )

    if save and not out_path:
        out_path = save_json(records, category.key)

    est_total = len(records)
    if control.is_stopped:
        report(f"Остановлено: {len(records)} объявлений")
    else:
        report(f"Готово: {len(records)} объявлений")
    return records


def _fetch_card(
    client: AvitoClient,
    url_path: str,
    settings: Settings,
    control: RunControl,
    on_progress: ProgressCallback | None = None,
) -> dict | None:
    card_url = absolutize(url_path)
    result = _cooldown_get(client, card_url, settings, control, on_progress)
    if result.blocked:
        logger.warning("Карточка заблокирована: %s", card_url)
        return None
    if not result.ok:
        logger.warning("Карточка недоступна: %s", card_url)
        return None
    return parse_card(result.text)
