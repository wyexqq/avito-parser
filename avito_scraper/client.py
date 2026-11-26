from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass

import httpx

from .config import Settings

logger = logging.getLogger("avito_scraper.client")

BLOCK_MARKER = "Доступ ограничен"
BLOCK_STATUS = {403, 429, 302}


@dataclass
class FetchResult:
    url: str
    status_code: int
    text: str
    blocked: bool
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and not self.blocked and self.status_code == 200


def rotate_ip(rotate_url: str, timeout: float = 30.0) -> tuple[bool, str]:
    try:
        with httpx.Client(trust_env=False, timeout=timeout) as c:
            resp = c.get(rotate_url)
    except httpx.HTTPError as exc:
        return False, f"ошибка: {type(exc).__name__}: {exc}"

    body = resp.text.strip().replace("\n", " ")
    low = body.lower()
    ok = resp.status_code == 200 and not (
        '"status":"err"' in low.replace(" ", "")
        or "failed" in low
        or '"error"' in low
    )
    return ok, f"HTTP {resp.status_code}: {body[:150]}"


def _is_blocked(status_code: int, text: str) -> bool:
    if status_code in BLOCK_STATUS:
        return True
    if status_code == 200 and BLOCK_MARKER in text:
        return True
    return False


class AvitoClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._first_request = True
        headers = {
            "User-Agent": settings.user_agent,
            "Accept-Language": "ru-RU,ru;q=0.9",
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,*/*;q=0.8"
            ),
        }
        mounts = None
        if settings.proxies:
            mounts = {
                pattern: httpx.HTTPTransport(proxy=url)
                for pattern, url in settings.proxies.items()
            }
        self._client = httpx.Client(
            headers=headers,
            timeout=settings.timeout,
            mounts=mounts,
            follow_redirects=True,
            trust_env=False,
        )

    def __enter__(self) -> "AvitoClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _sleep(self) -> None:
        if self._first_request:
            self._first_request = False
            return
        base = random.uniform(self.settings.delay_min, self.settings.delay_max)
        jitter = random.uniform(0, 0.5)
        time.sleep(base + jitter)

    def get(self, url: str) -> FetchResult:
        self._sleep()
        last_error: str | None = None

        for attempt in range(self.settings.retries + 1):
            try:
                resp = self._client.get(url)
            except httpx.HTTPError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                logger.warning(
                    "GET %s | попытка %d | сетевая ошибка: %s",
                    url,
                    attempt + 1,
                    last_error,
                )
                if attempt < self.settings.retries:
                    time.sleep(random.uniform(1, 3))
                continue

            text = resp.text
            blocked = _is_blocked(resp.status_code, text)
            logger.info(
                "GET %s | %d | %d байт | %s",
                url,
                resp.status_code,
                len(text),
                "БЛОК" if blocked else "ok",
            )
            return FetchResult(
                url=url,
                status_code=resp.status_code,
                text=text,
                blocked=blocked,
            )

        logger.error("GET %s | не удалось после %d попыток", url, self.settings.retries + 1)
        return FetchResult(url=url, status_code=0, text="", blocked=False, error=last_error)
