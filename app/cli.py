# -*- coding: utf-8 -*-
"""서버 없이 1회 수집하고 정적 리포트를 굽는다.

GitHub Actions 가 매시 이걸 돌린다:
    python -m app.cli --window 720 --keep-days 90

  1. config.json 의 키워드로 순위 수집
  2. data/history.jsonl 에 append (git 에 diff 로 남는 텍스트)
  3. docs/index.html + docs/report.xlsx 생성 → GitHub Pages 가 서빙

로컬에서 서버를 안 띄우고 리포트만 뽑고 싶을 때도 그대로 쓸 수 있다.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from . import analytics, archive, config as config_mod, excel, report
from .collector import PowerLinkCollector, measure

ROOT = Path(__file__).resolve().parent.parent
HISTORY = ROOT / "data" / "history.jsonl"
DOCS = ROOT / "docs"

# 윈도우 콘솔 기본 코드페이지(cp949)에서는 한글·기호 출력이 터진다.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="파워링크 순위 1회 수집 + 정적 리포트 생성")
    ap.add_argument("--window", type=int, default=720, help="리포트에 담을 기간(시간). 기본 30일")
    ap.add_argument("--keep-days", type=int, default=90, help="이력 보관 일수")
    ap.add_argument("--source", default="schedule", help="수집 방식 표기")
    ap.add_argument("--skip-collect", action="store_true", help="수집 없이 리포트만 다시 굽는다")
    args = ap.parse_args(argv)

    cfg = config_mod.load()
    if not cfg.keywords or not cfg.targets:
        log("config.json 에 키워드나 추적 업체가 없습니다.")
        return 2

    if not args.skip_collect:
        log(f"수집 시작 — 키워드 {len(cfg.keywords)}개 × {cfg.repeat}회 측정")
        collector = PowerLinkCollector(max_pages=cfg.max_pages, max_workers=cfg.max_workers)
        results = measure(collector, cfg.keywords, cfg.targets, repeat=cfg.repeat)

        failed = [m.keyword for m in results if m.error]
        for m in results:
            ranks = " · ".join(
                f"{tr.name} {'순위밖' if tr.rank is None else str(tr.rank) + '위'}" for tr in m.ranks
            )
            log(f"  {m.keyword} (광고 {m.total_ads}개) — {ranks}")
        if failed:
            # 전부 실패면 네트워크나 차단을 의심해야 한다. 이력을 더럽히지 않고 멈춘다.
            log(f"수집 실패: {', '.join(failed)}")
            if len(failed) == len(results):
                log("모든 키워드가 실패했습니다. 이력을 남기지 않고 종료합니다.")
                return 1

        added = archive.append(HISTORY, archive.to_rows(results, source=args.source))
        log(f"이력 {added}행 추가 → {HISTORY.relative_to(ROOT)}")

    dropped = archive.prune(HISTORY, args.keep_days)
    if dropped:
        log(f"보관 기간({args.keep_days}일) 지난 {dropped}행 정리")

    rows = archive.load(HISTORY, hours=args.window)
    targets = [t.name for t in cfg.targets]
    rows = [r for r in rows if r["target"] in targets]
    if not rows:
        log("리포트로 만들 이력이 없습니다.")
        return 1

    data = analytics.build(rows, targets)
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")

    html = report.render(data, args.window, xlsx_href="report.xlsx")
    (DOCS / "index.html").write_text(html, encoding="utf-8", newline="\n")
    log(f"리포트 생성 → docs/index.html ({len(html):,} bytes)")

    (DOCS / "report.xlsx").write_bytes(excel.build_workbook(data, rows, args.window).getvalue())
    log("엑셀 생성 → docs/report.xlsx")

    kpi = data.get("kpi") or {}
    log(f"완료 — {data['primary']} 평균 {kpi.get('avg_rank')}위 · "
        f"첫 페이지 {kpi.get('first_page')}/{kpi.get('keywords')} · 측정 {data['sample_count']}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
