# -*- coding: utf-8 -*-
"""네이버 파워링크 노출순위 모니터 — 웹 서버.

실행:  python -m uvicorn app.main:app --host 0.0.0.0 --port 8200
또는:  run.bat  (포트는 그 파일의 set PORT= 한 줄에서 정한다)
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import analytics, config as config_mod, excel, report
from .collector import PAGE_SIZE, PowerLinkCollector, Target, measure
from .scheduler import HourlyScheduler
from .store import RankStore

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s"
)
log = logging.getLogger("ddaengju")

STATIC_DIR = Path(__file__).parent / "static"
store = RankStore(config_mod.DB_PATH)
scheduler = HourlyScheduler(store)


@asynccontextmanager
async def lifespan(_: FastAPI):
    cfg = config_mod.load()
    if cfg.schedule_enabled:
        scheduler.start()
        log.info("자동 수집 스케줄러 기동 (매시 %02d분)", cfg.schedule_minute)
    yield
    scheduler.stop()


app = FastAPI(title="네이버 파워링크 노출순위 모니터", lifespan=lifespan)


# ------------------------------------------------------------------ 요청 모델


class SearchRequest(BaseModel):
    keywords: str = Field(default="", description="콤마/줄바꿈 구분 키워드")
    repeat: int | None = Field(default=None, ge=1, le=5)
    save: bool = True


class TargetIn(BaseModel):
    name: str
    patterns: list[str] = []


class ConfigIn(BaseModel):
    keywords: list[str] | None = None
    targets: list[TargetIn] | None = None
    repeat: int | None = Field(default=None, ge=1, le=5)
    max_workers: int | None = Field(default=None, ge=1, le=10)
    max_pages: int | None = Field(default=None, ge=1, le=30)
    schedule_enabled: bool | None = None
    schedule_minute: int | None = Field(default=None, ge=0, le=59)


# ---------------------------------------------------------------------- 화면


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


# ------------------------------------------------------------------ 순위조회


def _measurements_to_json(measurements) -> list[dict]:
    return [
        {
            "keyword": m.keyword,
            "total_ads": m.total_ads,
            "fetched_at": m.fetched_at.isoformat(timespec="seconds"),
            "error": m.error,
            "ranks": [
                {
                    "target": tr.name,
                    "rank": tr.rank,
                    "samples": tr.samples,
                    "unstable": tr.unstable,
                }
                for tr in m.ranks
            ],
        }
        for m in measurements
    ]


@app.post("/api/search")
def search(req: SearchRequest) -> dict:
    """지금 즉시 순위를 조회한다."""
    cfg = config_mod.load()
    keywords = config_mod.parse_keywords(req.keywords) or cfg.keywords
    if not keywords:
        raise HTTPException(400, "키워드를 입력해 주세요.")
    if not cfg.targets:
        raise HTTPException(400, "추적할 업체가 설정되어 있지 않습니다.")
    if len(keywords) > 100:
        raise HTTPException(400, "키워드는 한 번에 100개까지 조회할 수 있습니다.")

    collector = PowerLinkCollector(max_pages=cfg.max_pages, max_workers=cfg.max_workers)
    started = datetime.now()
    results = measure(collector, keywords, cfg.targets, repeat=req.repeat or cfg.repeat)
    if req.save:
        store.save_run(results, source="manual")

    return {
        "keywords": keywords,
        "targets": [t.name for t in cfg.targets],
        "elapsed_sec": round((datetime.now() - started).total_seconds(), 1),
        "results": _measurements_to_json(results),
    }


@app.get("/api/detail")
def detail(keyword: str) -> dict:
    """키워드 하나의 파워링크 광고 목록 전체(1위부터)를 그대로 보여준다."""
    cfg = config_mod.load()
    collector = PowerLinkCollector(max_pages=cfg.max_pages, max_workers=1)
    result = collector.collect_keyword(keyword, targets=())  # 조기종료 없이 전량
    return {
        "keyword": result.keyword,
        "total_ads": result.total_ads,
        "fetched_at": result.fetched_at.isoformat(timespec="seconds"),
        "error": result.error,
        # 화면이 '몇 위부터 더보기를 눌러야 보이는지' 를 페이지 단위로 끊어 보여준다.
        # 15 를 프런트에 또 박아 두면 수집기와 어긋날 수 있으니 여기서 내려준다.
        "page_size": PAGE_SIZE,
        "items": [
            {
                "rank": i.rank,
                "site": i.site,
                "domain": i.domain,
                "title": i.title,
                "desc": i.desc,
                "is_target": [t.name for t in cfg.targets if t.matches(i)],
            }
            for i in result.items
        ],
    }


# -------------------------------------------------------------------- 이력


@app.get("/api/history")
def history(keyword: str | None = None, hours: int = 72) -> dict:
    hours = max(1, min(24 * 90, hours))
    rows = store.history(keyword=keyword, hours=hours)
    return {"hours": hours, "keyword": keyword, "rows": rows}


@app.get("/api/latest")
def latest() -> dict:
    run = store.latest_run()
    return {"run": run, "rows": store.rows_of_run(run["id"]) if run else []}


# ------------------------------------------------------------------ 분석/리포트


def _analysis(hours: int) -> tuple[dict, list[dict], int]:
    """분석에 필요한 이력을 읽어 지표를 계산한다."""
    hours = max(1, min(24 * 90, hours))
    cfg = config_mod.load()
    targets = [t.name for t in cfg.targets]
    if not targets:
        raise HTTPException(400, "추적할 업체가 설정되어 있지 않습니다.")
    rows = store.export_rows(hours=hours)
    if not rows:
        raise HTTPException(404, "분석할 이력이 없습니다. 먼저 순위를 조회해 주세요.")
    # 설정에서 지워진 옛 업체가 이력에 남아 있어도 현재 설정 기준으로만 본다.
    rows = [r for r in rows if r["target"] in targets]
    if not rows:
        raise HTTPException(404, "현재 설정된 업체의 이력이 없습니다. 순위를 다시 조회해 주세요.")
    return analytics.build(rows, targets), rows, hours


@app.get("/api/analytics")
def get_analytics(hours: int = 72) -> dict:
    """대시보드 차트가 쓰는 지표 묶음 (KPI·현재순위·히트맵·시간대별·변동성·추이)."""
    data, _, hours = _analysis(hours)
    data["window_hours"] = hours
    return data


def _attach(stamp: str, korean: str, ext: str) -> dict:
    """한글 파일명은 latin-1 헤더에 담기지 않으므로 RFC 5987 로 인코딩한다."""
    return {
        "Content-Disposition": (
            f"attachment; filename=powerlink_{stamp}.{ext}; "
            f"filename*=UTF-8''{quote(f'{korean}_{stamp}.{ext}')}"
        )
    }


@app.get("/api/export.xlsx")
def export_xlsx(hours: int = 24 * 7):
    """엑셀 리포트. 이미지가 아니라 엑셀 네이티브 차트를 심어 내보낸다."""
    data, rows, hours = _analysis(hours)
    buf = excel.build_workbook(data, rows, hours)
    stamp = f"{datetime.now():%Y%m%d_%H%M}"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=_attach(stamp, "파워링크리포트", "xlsx"),
    )


@app.get("/api/report.html")
def export_report(hours: int = 24 * 7, download: bool = True):
    """단독 HTML 리포트. 서버 없이 열리고 메일 첨부로 그대로 공유된다."""
    data, _, hours = _analysis(hours)
    html = report.render(data, hours)
    stamp = f"{datetime.now():%Y%m%d_%H%M}"
    headers = _attach(stamp, "파워링크리포트", "html") if download else {}
    return HTMLResponse(html, headers=headers)


# -------------------------------------------------------------------- 설정


@app.get("/api/config")
def get_config() -> dict:
    return config_mod.load().to_dict()


@app.post("/api/config")
def set_config(body: ConfigIn) -> dict:
    cfg = config_mod.load()
    if body.keywords is not None:
        cfg.keywords = [k.strip() for k in body.keywords if k.strip()]
    if body.targets is not None:
        cfg.targets = [
            Target(name=t.name.strip(), patterns=[p.strip() for p in (t.patterns or [t.name]) if p.strip()])
            for t in body.targets
            if t.name.strip()
        ]
    for field_name in ("repeat", "max_workers", "max_pages", "schedule_enabled", "schedule_minute"):
        value = getattr(body, field_name)
        if value is not None:
            setattr(cfg, field_name, value)

    config_mod.save(cfg)
    if cfg.schedule_enabled and not scheduler.running:
        scheduler.start()
    return cfg.to_dict()


# -------------------------------------------------------------------- 상태


@app.get("/api/status")
def status() -> dict:
    return {"scheduler": scheduler.status(), "store": store.stats()}


@app.post("/api/run-now")
def run_now() -> dict:
    run_id = scheduler.run_once(source="manual")
    if not run_id:
        raise HTTPException(500, scheduler.last_error or "수집에 실패했습니다.")
    return {"run_id": run_id, "rows": store.rows_of_run(run_id)}


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
