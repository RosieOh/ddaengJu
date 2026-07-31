# -*- coding: utf-8 -*-
"""매시 정각 자동 수집 스케줄러.

외부 스케줄러 라이브러리 없이 데몬 스레드 하나로 돌린다.
설정(config.json)은 매 사이클마다 다시 읽으므로, 웹에서 키워드를 바꾸면
다음 정각부터 바로 반영된다.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta

from . import config as config_mod
from .collector import PowerLinkCollector, measure
from .store import RankStore

log = logging.getLogger("ddaengju.scheduler")


class HourlyScheduler:
    def __init__(self, store: RankStore) -> None:
        self.store = store
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_run_at: datetime | None = None
        self.last_error: str | None = None
        self.next_run_at: datetime | None = None

    # ---------------------------------------------------------------- 제어

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="hourly", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def status(self) -> dict:
        cfg = config_mod.load()
        return {
            "running": self.running,
            "enabled": cfg.schedule_enabled,
            "minute": cfg.schedule_minute,
            "last_run_at": self.last_run_at.isoformat(timespec="seconds") if self.last_run_at else None,
            "next_run_at": self.next_run_at.isoformat(timespec="seconds") if self.next_run_at else None,
            "last_error": self.last_error,
        }

    # ---------------------------------------------------------------- 내부

    @staticmethod
    def _next_slot(now: datetime, minute: int) -> datetime:
        slot = now.replace(minute=minute, second=0, microsecond=0)
        if slot <= now:
            slot += timedelta(hours=1)
        return slot

    def _loop(self) -> None:
        while not self._stop.is_set():
            cfg = config_mod.load()
            now = datetime.now()
            target = self._next_slot(now, cfg.schedule_minute)
            self.next_run_at = target

            # 설정이 바뀔 수 있으니 최대 60초 단위로 끊어 기다린다.
            while not self._stop.is_set() and datetime.now() < target:
                self._stop.wait(min(60, max(1, (target - datetime.now()).total_seconds())))
            if self._stop.is_set():
                return

            cfg = config_mod.load()
            if not cfg.schedule_enabled or not cfg.keywords or not cfg.targets:
                continue
            self.run_once(cfg, source="schedule")

    def run_once(self, cfg=None, source: str = "schedule") -> int:
        """1회 수집 후 저장. run_id 를 돌려준다(실패 시 0)."""
        cfg = cfg or config_mod.load()
        try:
            collector = PowerLinkCollector(
                max_pages=cfg.max_pages, max_workers=cfg.max_workers
            )
            results = measure(collector, cfg.keywords, cfg.targets, repeat=cfg.repeat)
            run_id = self.store.save_run(results, source=source)
            self.last_run_at = datetime.now()
            self.last_error = None
            log.info("자동 수집 완료 run=%s 키워드=%d", run_id, len(results))
            return run_id
        except Exception as exc:  # noqa: BLE001 - 스케줄 스레드는 어떤 예외로도 죽으면 안 된다
            self.last_error = str(exc)
            log.exception("자동 수집 실패")
            return 0
