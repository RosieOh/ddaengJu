# -*- coding: utf-8 -*-
"""단독 HTML 리포트 생성.

CSS·JS·데이터를 전부 한 파일에 인라인해서 내보낸다. 서버 없이 더블클릭으로
열리고, 메일에 첨부해도 그대로 보인다. 차트는 대시보드와 **같은 charts.js** 를
쓰므로 화면과 리포트가 어긋나지 않는다.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

STATIC = Path(__file__).parent / "static"

BASE_CSS = """
:root {
  color-scheme: light;
  --bg: oklch(0.978 0 0);
  --surface: oklch(1 0 0);
  --surface-sunk: oklch(0.962 0 0);
  --line: oklch(0.905 0 0);
  --line-soft: oklch(0.945 0 0);
  --ink: oklch(0.24 0 0);
  --ink-2: oklch(0.44 0 0);
  --ink-3: oklch(0.56 0 0);
  --accent: oklch(0.53 0.155 34);
  --radius: 8px;
}
@media (prefers-color-scheme: dark) {
  :root {
    color-scheme: dark;
    --bg: oklch(0.185 0 0);
    --surface: oklch(0.225 0 0);
    --surface-sunk: oklch(0.205 0 0);
    --line: oklch(0.325 0 0);
    --line-soft: oklch(0.275 0 0);
    --ink: oklch(0.945 0 0);
    --ink-2: oklch(0.80 0 0);
    --ink-3: oklch(0.685 0 0);
    --accent: oklch(0.72 0.14 38);
  }
}
* , *::before, *::after { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--ink);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Pretendard",
               "Malgun Gothic", "Apple SD Gothic Neo", Roboto, sans-serif;
  font-size: 0.875rem; line-height: 1.55; -webkit-font-smoothing: antialiased;
}
main { max-width: 1100px; margin: 0 auto; padding: 2rem 1.25rem 4rem; display: grid; gap: 1.25rem; }
header.rpt { display: grid; gap: 0.3125rem; padding-bottom: 0.5rem; }
header.rpt h1 { margin: 0; font-size: 1.25rem; font-weight: 640; letter-spacing: -0.015em; }
header.rpt p { margin: 0; color: var(--ink-3); font-size: 0.8125rem; }
section.card { background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); }
section.card > h2 {
  margin: 0; padding: 0.875rem 1rem; font-size: 0.9375rem; font-weight: 620;
  border-bottom: 1px solid var(--line-soft);
}
.plain { padding: 1rem; overflow-x: auto; }
.plain table { width: 100%; border-collapse: collapse; font-size: 0.8125rem; }
.plain th, .plain td {
  padding: 0.4375rem 0.625rem; text-align: right; white-space: nowrap;
  border-bottom: 1px solid var(--line-soft);
}
.plain th:first-child, .plain td:first-child { text-align: left; }
.plain thead th { color: var(--ink-2); font-weight: 600; font-size: 0.75rem; }
.plain td { font-variant-numeric: tabular-nums; }
.plain tbody tr:last-child td { border-bottom: 0; }
.muted { color: var(--ink-3); }
.foot { color: var(--ink-3); font-size: 0.75rem; padding: 0 0.25rem; }
.trend-stack { display: grid; gap: 1.25rem; }
@media print {
  body { background: #fff; }
  section.card { break-inside: avoid; border-color: #ddd; }
  .viz-toggle { display: none; }
}
"""


def _read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def _esc(s) -> str:
    return (
        str(s if s is not None else "")
        .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _rank(v) -> str:
    return "순위밖" if v is None else f"{v}위"


def _delta_cell(delta) -> str:
    if delta is None:
        return '<span class="viz-delta flat">—</span>'
    if delta == 0:
        return '<span class="viz-delta flat">변화 없음</span>'
    cls = "up" if delta > 0 else "down"
    arrow = "▲" if delta > 0 else "▼"
    return f'<span class="viz-delta {cls}">{arrow} {abs(delta)}</span>'


def _current_table(analysis: dict) -> str:
    targets = analysis["targets"]
    primary = analysis["primary"]
    head = "".join(f"<th>{_esc(t)}</th>" for t in targets)
    rows = []
    for e in analysis["current"]:
        cells = "".join(f"<td>{_rank((e['ranks'].get(t) or {}).get('rank'))}</td>" for t in targets)
        delta = (e["ranks"].get(primary) or {}).get("delta")
        rows.append(
            f"<tr><td>{_esc(e['keyword'])}</td>{cells}"
            f"<td>{e.get('total_ads') or '-'}</td><td>{_delta_cell(delta)}</td></tr>"
        )
    return (
        f"<table><thead><tr><th>키워드</th>{head}<th>전체 광고</th>"
        f"<th>{_esc(primary)} 직전 대비</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )


def _competitive_table(analysis: dict) -> str:
    rows = []
    for c in analysis.get("competitive", []):
        ahead = c["ahead"]
        label = (
            '<span class="muted">앞선 경쟁사 없음</span>'
            if not ahead
            else ", ".join(f"{_esc(a['target'])} {a['rank']}위" for a in ahead)
        )
        rows.append(
            f"<tr><td>{_esc(c['keyword'])}</td><td>{_rank(c['rank'])}</td>"
            f"<td>{len(ahead)}</td><td style='text-align:left'>{label}</td></tr>"
        )
    if not rows:
        return '<p class="muted">데이터가 없습니다.</p>'
    return (
        "<table><thead><tr><th>키워드</th><th>내 순위</th><th>앞선 경쟁사</th>"
        "<th style='text-align:left'>상세</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _volatility_table(analysis: dict) -> str:
    rows = analysis.get("volatility", [])
    if not rows:
        return '<p class="muted">표본이 3회 미만이라 아직 계산할 수 없습니다.</p>'
    body = "".join(
        f"<tr><td>{_esc(v['keyword'])}</td><td style='text-align:left'>{_esc(v['target'])}</td>"
        f"<td>{v['stdev']}</td><td>{v['min']}위</td><td>{v['max']}위</td>"
        f"<td>{v['samples']}</td><td>{v['out_count']}</td></tr>"
        for v in rows
    )
    return (
        "<table><thead><tr><th>키워드</th><th style='text-align:left'>업체</th><th>표준편차</th>"
        "<th>최고</th><th>최저</th><th>표본</th><th>순위밖</th></tr></thead>"
        f"<tbody>{body}</tbody></table>"
    )


def render(analysis: dict, window_hours: int, xlsx_href: str | None = None) -> str:
    primary = analysis["primary"]
    hourly = analysis.get("hourly") or {}
    best, worst = hourly.get("best_hour"), hourly.get("worst_hour")
    hourly_note = ""
    if best and worst and best["hour"] != worst["hour"]:
        hourly_note = (
            f"<p class='foot'>{_esc(primary)} 기준 가장 좋은 시간대는 "
            f"<strong>{best['hour']:02d}시(평균 {best['avg']}위)</strong>, "
            f"가장 밀리는 시간대는 <strong>{worst['hour']:02d}시(평균 {worst['avg']}위)</strong>입니다.</p>"
        )

    trend_slots = "".join(
        f'<div class="card viz" data-trend="{_esc(kw)}"></div>'
        for kw in (analysis.get("trend") or {})
    ) or '<p class="muted" style="padding:1rem">추이를 그리려면 같은 키워드로 2회 이상 수집되어야 합니다.</p>'

    payload = json.dumps(analysis, ensure_ascii=False)

    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>파워링크 노출순위 리포트 — {_esc(primary)}</title>
<style>{BASE_CSS}</style>
<style>{_read("viz.css")}</style>
</head>
<body>
<main>
  <header class="rpt">
    <h1>네이버 파워링크 노출순위 리포트</h1>
    <p>기준 업체 <strong>{_esc(primary)}</strong> · 최근 {window_hours}시간 ·
       생성 {datetime.now():%Y-%m-%d %H:%M} · 모바일 파워링크(1페이지 {analysis['first_page']}개) 기준</p>
    {f'<p><a href="{_esc(xlsx_href)}" download>엑셀로 내려받기</a></p>' if xlsx_href else ''}
  </header>

  <section class="card viz" id="kpi"></section>

  <section class="card">
    <h2>현재 노출순위</h2>
    <div class="plain">{_current_table(analysis)}</div>
  </section>

  <section class="card viz" id="heatmap"></section>
  <section class="card viz" id="dumbbell"></section>

  <section class="card viz" id="hourly"></section>
  {hourly_note}

  <div class="trend-stack">{trend_slots}</div>

  <section class="card">
    <h2>경쟁 구도 — {_esc(primary)}보다 위에 있는 업체</h2>
    <div class="plain">{_competitive_table(analysis)}</div>
  </section>

  <section class="card">
    <h2>순위 변동성</h2>
    <div class="plain">{_volatility_table(analysis)}</div>
  </section>

  <p class="foot">
    순위는 키워드당 반복 측정 후 중앙값입니다. 파워링크는 호출할 때마다 광고가 로테이션되어
    순위가 흔들리므로, 단일 시점 값보다 추이와 중앙값을 함께 보셔야 합니다.
  </p>
</main>

<script>{_read("charts.js")}</script>
<script>
(function () {{
  const A = {payload};
  Viz.renderKpis(document.getElementById("kpi"), A.kpi, A.kpi_spark);
  Viz.renderHeatmap(document.getElementById("heatmap"), {{ heatmap: A.heatmap, firstPage: A.first_page }});
  Viz.renderDumbbell(document.getElementById("dumbbell"),
    {{ current: A.current, primary: A.primary, firstPage: A.first_page }});
  Viz.renderHourly(document.getElementById("hourly"),
    {{ hourly: A.hourly, primary: A.primary, firstPage: A.first_page }});
  document.querySelectorAll("[data-trend]").forEach((el) => {{
    const kw = el.dataset.trend;
    Viz.renderTrend(el, {{ keyword: kw, series: A.trend[kw] || {{}}, targets: A.targets, firstPage: A.first_page }});
  }});
}})();
</script>
</body>
</html>
"""
