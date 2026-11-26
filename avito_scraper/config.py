from __future__ import annotations

import os
from dataclasses import dataclass, field

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


BASE_URL = "https://www.avito.ru"
CITY_SLUG = "sochi"


@dataclass(frozen=True)
class Category:
    key: str
    title: str
    slug: str
    code: str


CATEGORIES: dict[str, Category] = {
    c.key: c
    for c in [
        Category("kvartiry", "Квартиры", "kvartiry", "ASgBAgICAUSSA8YQ"),
        Category("komnaty", "Комнаты", "komnaty", "ASgBAgICAUSQA7wQ"),
        Category(
            "doma", "Дома, дачи, коттеджи", "doma_dachi_kottedzhi", "ASgBAgICAUSUA9AQ"
        ),
        Category(
            "uchastki", "Земельные участки", "zemelnye_uchastki", "ASgBAgICAUSWA9oQ"
        ),
        Category(
            "garazhi",
            "Гаражи и машиноместа",
            "garazhi_i_mashinomesta",
            "ASgBAgICAUSYA~QQ",
        ),
        Category(
            "kommercheskaya",
            "Коммерческая недвижимость",
            "kommercheskaya_nedvizhimost",
            "ASgBAgICAUSwCNJW",
        ),
    ]
}


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def build_proxies() -> dict[str, str] | None:
    single = os.getenv("AVITO_PROXY", "").strip()
    http = os.getenv("AVITO_PROXY_HTTP", "").strip()
    https = os.getenv("AVITO_PROXY_HTTPS", "").strip()

    if single:
        return {"http://": single, "https://": single}

    http = http or https
    https = https or http
    if http or https:
        return {"http://": http, "https://": https}
    return None


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


@dataclass
class Settings:
    delay_min: float = field(default_factory=lambda: _get_float("AVITO_DELAY_MIN", 2.0))
    delay_max: float = field(default_factory=lambda: _get_float("AVITO_DELAY_MAX", 5.0))
    timeout: float = field(default_factory=lambda: _get_float("AVITO_TIMEOUT", 30.0))
    retries: int = field(default_factory=lambda: _get_int("AVITO_RETRIES", 2))
    user_agent: str = field(
        default_factory=lambda: os.getenv("AVITO_USER_AGENT", DEFAULT_USER_AGENT)
    )
    proxies: dict[str, str] | None = field(default_factory=build_proxies)
    block_cooldown: float = field(
        default_factory=lambda: _get_float("AVITO_BLOCK_COOLDOWN", 60.0)
    )
    block_max_retries: int = field(
        default_factory=lambda: _get_int("AVITO_BLOCK_MAX_RETRIES", 3)
    )
    rotate_ip_url: str = field(
        default_factory=lambda: os.getenv("AVITO_ROTATE_IP_URL", "").strip()
    )
    rotate_fail_wait: float = field(
        default_factory=lambda: _get_float("AVITO_ROTATE_FAIL_WAIT", 130.0)
    )
