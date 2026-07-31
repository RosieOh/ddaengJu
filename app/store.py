# -*- coding: utf-8 -*-
"""순위 이력 저장소 (SQLite).

한 번의 수집 = run 한 건, 그 안에 (키워드 × 추적업체) 순위가 rank 로 쌓인다.
시간대별 추이 그래프와 엑셀 내보내기가 모두 이 두 테이블에서 나온다.
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Sequence

from .collector import MeasuredKeyword

_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS run (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT NOT NULL,
    source      TEXT NOT NULL,          -- 'manual' | 'schedule'
    keyword_cnt INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS rank (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL REFERENCES run(id) ON DELETE CASCADE,
    collected_at TEXT NOT NULL,
    keyword     TEXT NOT NULL,
    target      TEXT NOT NULL,
    rank        INTEGER,                -- NULL = 순위밖(미노출)
    total_ads   INTEGER NOT NULL DEFAULT 0,
    unstable    INTEGER NOT NULL DEFAULT 0,
    samples     TEXT NOT NULL DEFAULT '',
    error       TEXT
);

CREATE INDEX IF NOT EXISTS idx_rank_lookup ON rank(keyword, target, collected_at);
CREATE INDEX IF NOT EXISTS idx_rank_time   ON rank(collected_at);
"""


class RankStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    # ------------------------------------------------------------------ 쓰기

    def save_run(self, measurements: Sequence[MeasuredKeyword], source: str) -> int:
        """수집 결과 한 묶음을 저장하고 run_id 를 돌려준다."""
        if not measurements:
            return 0
        started = min(m.fetched_at for m in measurements)
        with _lock, self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO run (started_at, source, keyword_cnt) VALUES (?, ?, ?)",
                (started.isoformat(timespec="seconds"), source, len(measurements)),
            )
            run_id = int(cur.lastrowid)
            rows = [
                (
                    run_id,
                    m.fetched_at.isoformat(timespec="seconds"),
                    m.keyword,
                    tr.name,
                    tr.rank,
                    m.total_ads,
                    1 if tr.unstable else 0,
                    ",".join("-" if s is None else str(s) for s in tr.samples),
                    m.error,
                )
                for m in measurements
                for tr in m.ranks
            ]
            conn.executemany(
                """INSERT INTO rank
                   (run_id, collected_at, keyword, target, rank, total_ads, unstable, samples, error)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                rows,
            )
            return run_id

    def purge_older_than(self, days: int) -> int:
        """오래된 이력을 정리한다. 기본 운영에서는 호출하지 않는다."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
        with _lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM rank WHERE collected_at < ?", (cutoff,))
            conn.execute(
                "DELETE FROM run WHERE id NOT IN (SELECT DISTINCT run_id FROM rank)"
            )
            return cur.rowcount

    # ------------------------------------------------------------------ 읽기

    def latest_run(self) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM run ORDER BY id DESC LIMIT 1"
            ).fetchone()
            return dict(row) if row else None

    def rows_of_run(self, run_id: int) -> list[dict]:
        with self._connect() as conn:
            return [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM rank WHERE run_id = ? ORDER BY id", (run_id,)
                )
            ]

    def history(
        self,
        keyword: str | None = None,
        targets: Iterable[str] | None = None,
        hours: int = 72,
    ) -> list[dict]:
        """추이 그래프용 시계열."""
        since = (datetime.now() - timedelta(hours=hours)).isoformat(timespec="seconds")
        sql = ["SELECT collected_at, keyword, target, rank, total_ads FROM rank WHERE collected_at >= ?"]
        args: list = [since]
        if keyword:
            sql.append("AND keyword = ?")
            args.append(keyword)
        targets = list(targets or [])
        if targets:
            sql.append(f"AND target IN ({','.join('?' * len(targets))})")
            args.extend(targets)
        sql.append("ORDER BY collected_at")
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(" ".join(sql), args)]

    def export_rows(self, hours: int = 24 * 30) -> list[dict]:
        since = (datetime.now() - timedelta(hours=hours)).isoformat(timespec="seconds")
        with self._connect() as conn:
            return [
                dict(r)
                for r in conn.execute(
                    """SELECT r.collected_at, r.keyword, r.target, r.rank, r.total_ads,
                              r.unstable, r.samples, run.source
                       FROM rank r JOIN run ON run.id = r.run_id
                       WHERE r.collected_at >= ?
                       ORDER BY r.collected_at DESC, r.keyword, r.target""",
                    (since,),
                )
            ]

    def stats(self) -> dict:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT (SELECT COUNT(*) FROM run)  AS runs,
                          (SELECT COUNT(*) FROM rank) AS ranks,
                          (SELECT MAX(collected_at) FROM rank) AS last_at"""
            ).fetchone()
            return dict(row)
