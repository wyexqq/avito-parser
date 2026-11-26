from __future__ import annotations

import logging
import threading
import traceback
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .config import CATEGORIES, DEFAULT_USER_AGENT, Settings
from .scraper import RunControl, RunParams, scrape_category

app = FastAPI(title="Авито парсер")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

RESULTS_DIR = Path("data/results")


class _SuppressStatusPolls(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if args and len(args) >= 5:
            path = str(args[2])
            status = args[4]
            if path.startswith("/status") and isinstance(status, int) and status < 400:
                return False
        return True


logging.getLogger("uvicorn.access").addFilter(_SuppressStatusPolls())


@dataclass
class RunState:
    status: str = "idle"
    progress: str = ""
    log: list[str] = field(default_factory=list)
    result_file: str | None = None
    total: int = 0
    done_count: int = 0
    est_total: int | None = None
    category: str = ""
    error_msg: str | None = None

    def reset(self) -> None:
        self.status = "idle"
        self.progress = ""
        self.log = []
        self.result_file = None
        self.total = 0
        self.done_count = 0
        self.est_total = None
        self.category = ""
        self.error_msg = None


_state = RunState()
_lock = threading.Lock()
_control: RunControl | None = None


def _on_progress(msg: str, current: int = 0, total: int | None = None) -> None:
    with _lock:
        _state.progress = msg
        _state.done_count = current
        _state.est_total = total
        _state.log.append(msg)
        if len(_state.log) > 200:
            _state.log = _state.log[-200:]


def _build_params(form) -> tuple[RunParams, str]:
    proxy = str(form.get("proxy", "")).strip()
    proxies = {"http://": proxy, "https://": proxy} if proxy else None

    settings = Settings(
        delay_min=float(form.get("delay_min", 5)),
        delay_max=float(form.get("delay_max", 10)),
        timeout=float(form.get("timeout", 60)),
        retries=int(form.get("retries", 2)),
        user_agent=str(form.get("user_agent", DEFAULT_USER_AGENT)),
        proxies=proxies,
        block_cooldown=float(form.get("block_cooldown", 60)),
        block_max_retries=int(form.get("block_max_retries", 3)),
        rotate_ip_url=str(form.get("rotate_ip_url", "")).strip(),
    )

    max_pages_raw = str(form.get("max_pages", "2")).strip()
    max_pages = int(max_pages_raw) if max_pages_raw and max_pages_raw != "0" else None

    max_listings_raw = str(form.get("max_listings", "")).strip()
    max_listings = int(max_listings_raw) if max_listings_raw else None

    params = RunParams(
        settings=settings,
        max_pages=max_pages,
        max_listings=max_listings,
        fetch_cards=form.get("fetch_cards") == "on",
    )
    return params, str(form.get("category", "kvartiry"))


def _run_scraper(category_key: str, control: RunControl) -> None:
    try:
        category = CATEGORIES[category_key]
        records = scrape_category(
            category=category,
            save=True,
            on_progress=_on_progress,
            control=control,
        )
        with _lock:
            _state.total = len(records)
            _state.status = "done"
            files = sorted(RESULTS_DIR.glob(f"{category_key}_*.json"))
            if files:
                _state.result_file = str(files[-1])
            if control.is_stopped:
                _state.progress = f"Остановлено: {len(records)} объявлений"
    except Exception:
        with _lock:
            _state.status = "error"
            _state.error_msg = traceback.format_exc()
            _state.progress = "Ошибка"


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "categories": CATEGORIES, "state": _state},
    )


@app.post("/start")
async def start(request: Request):
    global _control
    form = await request.form()

    with _lock:
        if _state.status in ("running", "paused"):
            return JSONResponse({"error": "Прогон уже запущен"}, status_code=409)
        _state.reset()
        _state.status = "running"
        _state.progress = "Запуск…"

    params, category_key = _build_params(form)
    _state.category = category_key
    _control = RunControl(params)

    threading.Thread(
        target=_run_scraper, args=(category_key, _control), daemon=True
    ).start()
    return RedirectResponse("/", status_code=303)


@app.post("/pause")
async def pause():
    with _lock:
        if _state.status != "running" or _control is None:
            return JSONResponse({"error": "Нет активного прогона"}, status_code=409)
        _control.pause()
        _state.status = "paused"
        _state.progress = "Пауза"
    return {"status": "paused"}


@app.post("/resume")
async def resume(request: Request):
    form = await request.form()
    with _lock:
        if _state.status != "paused" or _control is None:
            return JSONResponse({"error": "Прогон не на паузе"}, status_code=409)

    params, _ = _build_params(form)
    _control.resume(params)
    with _lock:
        _state.status = "running"
        _state.progress = "Продолжаю…"
    return {"status": "running"}


@app.post("/stop")
async def stop():
    with _lock:
        if _state.status not in ("running", "paused") or _control is None:
            return JSONResponse({"error": "Нет активного прогона"}, status_code=409)
        _control.stop()
        _state.progress = "Останавливаю…"
    return {"status": "stopping"}


@app.get("/status")
async def status():
    with _lock:
        return {
            "status": _state.status,
            "progress": _state.progress,
            "log": _state.log[-50:],
            "total": _state.total,
            "done_count": _state.done_count,
            "est_total": _state.est_total,
            "result_file": _state.result_file,
            "error": _state.error_msg,
        }


@app.get("/download")
async def download():
    with _lock:
        path = _state.result_file
    if not path or not Path(path).exists():
        return JSONResponse({"error": "Файл не найден"}, status_code=404)
    return FileResponse(
        path, media_type="application/json", filename=Path(path).name
    )
