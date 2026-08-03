/* ───────────────────────────────────────────────────────────────────────────
   공용 차트 모듈 (의존성 없음).
   웹 대시보드(index.html)와 단독 HTML 리포트가 같은 코드를 쓴다.

   모든 차트는 (1) 범례, (2) 호버 툴팁, (3) 표 보기 쌍둥이를 함께 낸다.
   라이트 모드에서 3:1 미만인 슬롯이 있어 직접 라벨 + 표 보기가 필수다.
   ─────────────────────────────────────────────────────────────────────────── */
(function (global) {
  "use strict";

  const SLOTS = 8;
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const uid = (() => { let n = 0; return () => `viz${++n}`; })();

  /* 색은 개체(업체)에 붙는다. 필터로 계열이 빠져도 남은 계열의 색은 그대로다. */
  function colorOf(name, order) {
    const i = order.indexOf(name);
    return `var(--viz-s${((i < 0 ? order.length : i) % SLOTS) + 1})`;
  }

  const RANK_OUT_LABEL = "순위밖";
  const fmtRank = (r) => (r === null || r === undefined ? RANK_OUT_LABEL : `${r}위`);
  const hhmm = (iso) => {
    const d = new Date(iso);
    return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  };
  const mmdd = (iso) => {
    const d = new Date(iso);
    return `${d.getMonth() + 1}/${d.getDate()}`;
  };

  /* ─────────────────────────────────────────────────────────────── 툴팁 */
  let tipEl = null;
  function tip() {
    if (!tipEl) {
      tipEl = document.createElement("div");
      tipEl.className = "viz-tip";
      document.body.appendChild(tipEl);
    }
    return tipEl;
  }
  function showTip(html, ev) {
    const t = tip();
    t.innerHTML = html;
    t.classList.add("on");
    const pad = 12;
    const r = t.getBoundingClientRect();
    let x = ev.clientX + pad;
    let y = ev.clientY + pad;
    if (x + r.width > window.innerWidth - 8) x = ev.clientX - r.width - pad;
    if (y + r.height > window.innerHeight - 8) y = ev.clientY - r.height - pad;
    t.style.left = `${Math.max(8, x)}px`;
    t.style.top = `${Math.max(8, y)}px`;
  }
  function hideTip() { if (tipEl) tipEl.classList.remove("on"); }

  /* ───────────────────────────────────────────────────────── 공통 조립 */
  function shell(el, { title, note, legend, svg, table, ariaLabel }) {
    const id = uid();
    el.classList.add("viz");
    el.innerHTML = `
      <div class="viz-head">
        <h3>${esc(title)}</h3>
        <div class="spacer"></div>
        ${note ? `<p class="note">${note}</p>` : ""}
        <button class="viz-toggle" type="button" aria-expanded="false" aria-controls="${id}">표로 보기</button>
      </div>
      ${legend || ""}
      <div class="viz-plot" style="padding:0 1rem 1rem">
        <svg viewBox="${svg.viewBox}" role="img" aria-label="${esc(ariaLabel || title)}"
             style="aspect-ratio:${svg.ratio}${svg.maxWidth ? `;max-width:${svg.maxWidth}px` : ""}${
               svg.minWidth ? `;min-width:${svg.minWidth}px` : ""}">${svg.body}</svg>
      </div>
      <div class="viz-table" id="${id}" hidden>${table}</div>`;

    const btn = el.querySelector(".viz-toggle");
    const tableEl = el.querySelector(`#${id}`);
    const plot = el.querySelector(".viz-plot");
    btn.addEventListener("click", () => {
      const open = tableEl.hidden;
      tableEl.hidden = !open;
      plot.hidden = open;
      btn.setAttribute("aria-expanded", String(open));
      btn.textContent = open ? "차트로 보기" : "표로 보기";
    });
    el.addEventListener("mouseleave", hideTip);
    return el;
  }

  function legendBox(names, order, onToggle) {
    const items = names.map((n) =>
      `<button type="button" data-name="${esc(n)}" aria-pressed="true">
         <i style="background:${colorOf(n, order)}"></i>${esc(n)}
       </button>`).join("");
    return `<div class="viz-legend" data-toggle="${onToggle ? "1" : "0"}">${items}</div>`;
  }

  function bindLegend(el, onToggle) {
    if (!onToggle) return;
    el.querySelectorAll(".viz-legend button").forEach((b) => {
      b.addEventListener("click", () => {
        const on = b.getAttribute("aria-pressed") !== "true";
        b.setAttribute("aria-pressed", String(on));
        onToggle(b.dataset.name, on);
      });
    });
  }

  function emptyState(el, title, msg) {
    el.classList.add("viz");
    el.innerHTML = `
      <div class="viz-head"><h3>${esc(title)}</h3></div>
      <div style="padding:1.5rem 1rem 2rem;text-align:center;color:var(--viz-muted);font-size:.8125rem">
        ${esc(msg)}
      </div>`;
  }

  /* ═══════════════════════════════════════════════════ 1. 순위 추이 (라인) */
  function renderTrend(el, opts) {
    const { keyword, series, targets, firstPage = 15 } = opts;
    const names = targets.filter((t) => (series[t] || []).length);
    if (!names.length) {
      return emptyState(el, `'${keyword}' 순위 추이`,
        "이 키워드의 이력이 아직 없습니다. 순위를 한 번 이상 조회하면 그려집니다.");
    }
    const moments = new Set(names.flatMap((n) => series[n].map((p) => p[0])));
    if (moments.size < 2) {
      return emptyState(el, `'${keyword}' 순위 추이`,
        "수집 시점이 한 번뿐이라 추이를 그릴 수 없습니다. 두 번째 수집부터 선이 이어집니다.");
    }

    // PR 은 오른쪽 직접 라벨이 앉을 자리다. '현대글로비스오토벨 12위' 같은
    // 긴 이름이 잘리지 않도록 이름 길이에 맞춰 넓힌다.
    const longest = Math.max(...names.map((n) => n.length), 4);
    const W = 1000, H = 300, PL = 46, PT = 14, PB = 30;
    const PR = Math.min(190, 46 + longest * 11);
    const all = names.flatMap((n) => series[n]);
    const times = all.map((p) => new Date(p[0]).getTime());
    const t0 = Math.min(...times), t1 = Math.max(...times);
    const ranks = all.map((p) => p[1]).filter((v) => v !== null);
    const maxRank = Math.max(firstPage, ...(ranks.length ? ranks : [firstPage]));
    const OUT = maxRank + Math.max(2, Math.round(maxRank * 0.14));

    const x = (t) => (t1 === t0 ? PL + (W - PL - PR) / 2 : PL + ((t - t0) / (t1 - t0)) * (W - PL - PR));
    const y = (r) => PT + (((r === null ? OUT : r) - 1) / (OUT - 1)) * (H - PT - PB);

    const ticks = [...new Set([1, 5, firstPage, maxRank].filter((v) => v >= 1 && v <= maxRank))]
      .sort((a, b) => a - b);
    let body = ticks.map((r) =>
      `<line class="v-grid" x1="${PL}" x2="${W - PR}" y1="${y(r).toFixed(1)}" y2="${y(r).toFixed(1)}"/>
       <text x="${PL - 8}" y="${(y(r) + 3.5).toFixed(1)}" text-anchor="end">${r}위</text>`).join("");

    // 첫 페이지 경계는 그리드가 아니라 기준선이므로 점선 + 라벨로 명시한다.
    body += `<line class="v-thresh" x1="${PL}" x2="${W - PR}" y1="${y(firstPage).toFixed(1)}" y2="${y(firstPage).toFixed(1)}"/>
             <text x="${W - PR + 6}" y="${(y(firstPage) + 3.5).toFixed(1)}">첫 페이지</text>
             <line class="v-thresh" x1="${PL}" x2="${W - PR}" y1="${y(null).toFixed(1)}" y2="${y(null).toFixed(1)}"/>
             <text x="${PL - 8}" y="${(y(null) + 3.5).toFixed(1)}" text-anchor="end">${RANK_OUT_LABEL}</text>`;

    const endLabels = [];
    names.forEach((n) => {
      const pts = series[n].slice().sort((a, b) => new Date(a[0]) - new Date(b[0]));
      const color = colorOf(n, targets);
      const d = pts.map((p, i) => `${i ? "L" : "M"}${x(new Date(p[0]).getTime()).toFixed(1)},${y(p[1]).toFixed(1)}`).join(" ");
      body += `<g data-series="${esc(n)}">
        <path class="v-line" d="${d}" stroke="${color}" pathLength="1"/>
        ${pts.map((p) => `<circle class="v-dot" cx="${x(new Date(p[0]).getTime()).toFixed(1)}"
             cy="${y(p[1]).toFixed(1)}" r="${p[1] === null ? 3 : 4.5}" fill="${color}"
             fill-opacity="${p[1] === null ? 0.45 : 1}"/>`).join("")}
      </g>`;
      // 계열이 4개 이하면 끝점 직접 라벨 (대비가 낮은 슬롯을 보완하는 필수 장치)
      if (names.length <= 4) {
        const last = pts[pts.length - 1];
        endLabels.push({
          name: n,
          x: x(new Date(last[0]).getTime()) + 9,
          y: y(last[1]),
          text: `${n} ${fmtRank(last[1])}`,
        });
      }
    });

    // 같은 순위로 끝나면 라벨이 포개진다. 위에서부터 최소 간격만큼 밀어낸다.
    const GAP = 13;
    endLabels.sort((a, b) => a.y - b.y);
    endLabels.forEach((lab, i) => {
      if (i && lab.y - endLabels[i - 1].y < GAP) lab.y = endLabels[i - 1].y + GAP;
    });
    const overflow = endLabels.length && endLabels[endLabels.length - 1].y - (H - PB);
    if (overflow > 0) endLabels.forEach((lab) => { lab.y -= overflow; });
    endLabels.forEach((lab) => {
      body += `<text class="v-label" data-label="${esc(lab.name)}" x="${lab.x.toFixed(1)}"
                y="${(lab.y + 3.5).toFixed(1)}">${esc(lab.text)}</text>`;
    });

    const stamps = [...new Set(all.map((p) => p[0]))].sort();
    const spanDays = (t1 - t0) / 86400000;
    const label = (s) => (spanDays > 1 ? `${mmdd(s)} ${hhmm(s)}` : hhmm(s));
    // 가운데 눈금은 양 끝과 충분히 떨어졌을 때만 찍는다. 시각이 몰리면 글자가 겹친다.
    const first = stamps[0], last = stamps[stamps.length - 1];
    const mid = stamps[Math.floor(stamps.length / 2)];
    const px = (s) => x(new Date(s).getTime());
    const MIN_GAP = 90;
    const marks = [[first, "start"], [last, "end"]];
    if (mid && px(mid) - px(first) > MIN_GAP && px(last) - px(mid) > MIN_GAP) {
      marks.push([mid, "middle"]);
    }
    marks.forEach(([s, anchor]) => {
      body += `<text x="${px(s).toFixed(1)}" y="${H - 8}" text-anchor="${anchor}">${label(s)}</text>`;
    });

    // 시점별 세로 히트존 — 마우스가 근처에만 가도 그 시점 전체를 읽어준다
    stamps.forEach((s) => {
      const px = x(new Date(s).getTime());
      const half = Math.max(12, (W - PL - PR) / Math.max(1, stamps.length) / 2);
      body += `<rect class="v-hit" data-at="${esc(s)}" x="${(px - half).toFixed(1)}" y="${PT}"
                width="${(half * 2).toFixed(1)}" height="${H - PT - PB}"/>`;
    });

    const rows = stamps.map((s) => `<tr><td>${mmdd(s)} ${hhmm(s)}</td>${
      names.map((n) => {
        const hit = series[n].find((p) => p[0] === s);
        return `<td>${hit ? fmtRank(hit[1]) : "-"}</td>`;
      }).join("")}</tr>`).join("");

    shell(el, {
      title: `'${keyword}' 순위 추이`,
      note: "위로 갈수록 상위 노출",
      legend: legendBox(names, targets, true),
      // 좁은 화면에서 줄이면 라벨이 뭉갠다. 폭을 지키고 컨테이너가 옆으로 구르게 둔다.
      svg: { viewBox: `0 0 ${W} ${H}`, ratio: `${W}/${H}`, minWidth: 660, body },
      table: `<table><thead><tr><th>조회시각</th>${names.map((n) => `<th>${esc(n)}</th>`).join("")}</tr></thead>
              <tbody>${rows}</tbody></table>`,
      ariaLabel: `${keyword} 키워드의 업체별 순위 추이`,
    });

    el.querySelectorAll("rect.v-hit").forEach((r) => {
      const at = r.dataset.at;
      const move = (ev) => {
        const lines = names.map((n) => {
          const hit = series[n].find((p) => p[0] === at);
          return `<div class="row"><i style="background:${colorOf(n, targets)}"></i>${esc(n)} <b>${
            hit ? fmtRank(hit[1]) : "-"}</b></div>`;
        }).join("");
        showTip(`<b>${mmdd(at)} ${hhmm(at)}</b>${lines}`, ev);
      };
      r.addEventListener("mousemove", move);
      r.addEventListener("mouseenter", move);
    });

    bindLegend(el, (name, on) => {
      el.querySelectorAll(`[data-series="${CSS.escape(name)}"], [data-label="${CSS.escape(name)}"]`)
        .forEach((node) => { node.style.display = on ? "" : "none"; });
    });
  }

  /* ═══════════════════════════════════════════ 2. 직전 대비 변화 (덤벨) */
  function renderDumbbell(el, opts) {
    const { current, primary, firstPage = 15 } = opts;
    const rows = current
      .map((r) => ({ keyword: r.keyword, ...(r.ranks[primary] || {}) }))
      .filter((r) => r.rank !== undefined && (r.rank !== null || r.prev !== null));
    const movable = rows.filter((r) => r.prev !== null && r.prev !== undefined);
    if (!movable.length) {
      return emptyState(el, `${primary} 순위 변화`,
        "직전 수집 기록이 아직 없습니다. 두 번째 수집부터 변화량이 표시됩니다.");
    }

    const ROW = 26, PT = 24, PB = 26, PL = 118, PR = 74, W = 1000;
    const H = PT + PB + movable.length * ROW;
    const vals = movable.flatMap((r) => [r.rank, r.prev]).filter((v) => v !== null);
    const maxRank = Math.max(firstPage, ...vals);
    const OUT = maxRank + Math.max(2, Math.round(maxRank * 0.12));
    const x = (r) => PL + (((r === null ? OUT : r) - 1) / (OUT - 1)) * (W - PL - PR);

    const ticks = [...new Set([1, 5, firstPage, maxRank])].filter((v) => v <= maxRank).sort((a, b) => a - b);
    let body = ticks.map((r) =>
      `<line class="${r === firstPage ? "v-thresh" : "v-grid"}" x1="${x(r).toFixed(1)}" x2="${x(r).toFixed(1)}" y1="${PT - 8}" y2="${H - PB + 4}"/>
       <text x="${x(r).toFixed(1)}" y="${PT - 12}" text-anchor="middle">${r}위</text>`).join("");
    body += `<text x="${x(null).toFixed(1)}" y="${PT - 12}" text-anchor="middle">${RANK_OUT_LABEL}</text>`;

    movable.forEach((r, i) => {
      const cy = PT + i * ROW + ROW / 2;
      const x1 = x(r.prev), x2 = x(r.rank);
      const improved = r.delta !== null && r.delta > 0;
      body += `
        <text class="v-label" x="${PL - 10}" y="${cy + 3.5}" text-anchor="end">${esc(r.keyword)}</text>
        <path class="v-line" d="M${x1.toFixed(1)},${cy}L${x2.toFixed(1)},${cy}" pathLength="1"
              stroke="var(--viz-axis)" stroke-width="2" stroke-linecap="round"/>
        <circle class="v-dot" cx="${x1.toFixed(1)}" cy="${cy}" r="4.5" fill="var(--viz-before)"/>
        <circle class="v-dot v-move" style="--from:${(x1 - x2).toFixed(1)}px"
                cx="${x2.toFixed(1)}" cy="${cy}" r="5.5" fill="var(--viz-after)"/>
        <text class="v-label" x="${W - PR + 10}" y="${cy + 3.5}"
              style="fill:${r.delta === null || r.delta === 0 ? "var(--viz-muted)" : improved ? "var(--viz-good)" : "var(--viz-bad)"}">${
          r.delta === null ? "—" : r.delta === 0 ? "변화 없음" : `${improved ? "▲" : "▼"} ${Math.abs(r.delta)}`}</text>
        <rect class="v-hit" data-i="${i}" x="${PL}" y="${cy - ROW / 2}" width="${W - PL - PR}" height="${ROW}"/>`;
    });

    shell(el, {
      title: `${primary} 순위 변화 (직전 수집 대비)`,
      note: "옅은 점 = 직전, 진한 점 = 현재",
      legend: `<div class="viz-legend">
          <button type="button" aria-pressed="true" tabindex="-1"><i style="background:var(--viz-before)"></i>직전</button>
          <button type="button" aria-pressed="true" tabindex="-1"><i style="background:var(--viz-after)"></i>현재</button>
        </div>`,
      svg: { viewBox: `0 0 ${W} ${H}`, ratio: `${W}/${H}`, minWidth: 560, body },
      table: `<table><thead><tr><th>키워드</th><th>직전</th><th>현재</th><th>변화</th></tr></thead><tbody>${
        movable.map((r) => `<tr><td>${esc(r.keyword)}</td><td>${fmtRank(r.prev)}</td><td>${fmtRank(r.rank)}</td>
          <td>${r.delta === null ? "-" : r.delta === 0 ? "0" : (r.delta > 0 ? "▲ " : "▼ ") + Math.abs(r.delta)}</td></tr>`).join("")
      }</tbody></table>`,
      ariaLabel: `${primary}의 키워드별 직전 수집 대비 순위 변화`,
    });

    el.querySelectorAll("rect.v-hit").forEach((rect) => {
      const r = movable[Number(rect.dataset.i)];
      const move = (ev) => showTip(
        `<b>${esc(r.keyword)}</b><div class="row"><i style="background:var(--viz-before)"></i>직전 <b>${fmtRank(r.prev)}</b></div>
         <div class="row"><i style="background:var(--viz-after)"></i>현재 <b>${fmtRank(r.rank)}</b></div>`, ev);
      rect.addEventListener("mousemove", move);
      rect.addEventListener("mouseenter", move);
    });
  }

  /* ═══════════════════════════════════════ 3. 키워드 × 업체 (히트맵) */
  const RAMP = ["--viz-q7", "--viz-q6", "--viz-q5", "--viz-q4", "--viz-q3", "--viz-q2", "--viz-q1"];

  function rampStep(rank, maxRank) {
    const span = Math.max(1, maxRank - 1);
    return Math.min(RAMP.length - 1, Math.floor(((rank - 1) / span) * RAMP.length));
  }
  function rampColor(rank, maxRank) {
    if (rank === null || rank === undefined) return "var(--viz-surface)";
    return `var(${RAMP[rampStep(rank, maxRank)]})`;
  }
  /* SVG 의 fill 속성은 `.viz text { fill: ... }` 같은 CSS 선언에 무조건 진다.
     그래서 글자색은 반드시 인라인 style 로 준다(속성으로 주면 회색으로 덮인다).
     글자색은 칸 색에 짝지어 둔 토큰을 쓴다. 밝기가 뒤집히는 지점에서 흰↔검이
     갈리고, 다크 모드는 램프가 뒤집히므로 토큰 쪽에서 함께 뒤집힌다.
     (최저 대비 5.06:1 — viz.css 주석에 단계별 실측값이 적혀 있다) */
  function rampInk(rank, maxRank) {
    if (rank === null || rank === undefined) return "var(--viz-muted)";
    return `var(${RAMP[rampStep(rank, maxRank)]}-ink)`;
  }

  function renderHeatmap(el, opts) {
    const { heatmap, firstPage = 15 } = opts;
    const { keywords, targets, cells } = heatmap;
    if (!keywords.length || !targets.length) {
      return emptyState(el, "키워드 × 업체 순위", "표시할 데이터가 없습니다.");
    }
    const maxRank = Math.max(firstPage, heatmap.max || firstPage);

    const CW = 96, CH = 30, PL = 150, PT = 26, W = PL + targets.length * CW + 8;
    const H = PT + keywords.length * CH + 6;

    let body = targets.map((t, c) =>
      `<text class="v-label" x="${PL + c * CW + CW / 2}" y="${PT - 10}" text-anchor="middle">${esc(t)}</text>`).join("");

    keywords.forEach((kw, r) => {
      body += `<text class="v-label" x="${PL - 12}" y="${PT + r * CH + CH / 2 + 3.5}" text-anchor="end">${esc(kw)}</text>`;
      targets.forEach((t, c) => {
        const v = cells[r][c];
        // 칸 사이 2px 간격 — 테두리를 그리지 않고 표면색으로 띄운다.
        // 격자가 격자로 나타나는 순간이라 행 단위 스태거만 준다(최대 200ms).
        body += `<rect class="v-cell" style="animation-delay:${Math.min(r, 8) * 25}ms"
                   x="${PL + c * CW + 1}" y="${PT + r * CH + 1}" width="${CW - 2}" height="${CH - 2}"
                   rx="4" fill="${rampColor(v, maxRank)}"
                   ${v === null ? 'stroke="var(--viz-grid)" stroke-width="1"' : ""}/>
                 <text x="${PL + c * CW + CW / 2}" y="${PT + r * CH + CH / 2 + 3.5}" text-anchor="middle"
                   style="fill:${rampInk(v, maxRank)};font-size:11px;font-weight:560">${fmtRank(v)}</text>
                 <rect class="v-hit" data-r="${r}" data-c="${c}" x="${PL + c * CW}" y="${PT + r * CH}"
                   width="${CW}" height="${CH}"/>`;
      });
    });

    shell(el, {
      title: "키워드 × 업체 노출순위",
      note: "진할수록 상위",
      legend: `<div class="viz-scale"><span>상위</span><span class="ramp">${
        RAMP.map((v) => `<i style="background:var(${v})"></i>`).join("")}</span><span>하위</span>
        <span style="margin-left:.5rem;display:inline-flex;align-items:center;gap:.375rem">
          <i style="width:16px;height:10px;border-radius:2px;border:1px solid var(--viz-grid);display:inline-block"></i>${RANK_OUT_LABEL}</span></div>`,
      // 칸 크기가 고정이라 늘려 봐야 글자만 커진다. 고유 폭에서 멈춘다.
      svg: { viewBox: `0 0 ${W} ${H}`, ratio: `${W}/${H}`, maxWidth: W, minWidth: W, body },
      table: `<table><thead><tr><th>키워드</th>${targets.map((t) => `<th>${esc(t)}</th>`).join("")}</tr></thead>
              <tbody>${keywords.map((kw, r) => `<tr><td>${esc(kw)}</td>${
                cells[r].map((v) => `<td>${fmtRank(v)}</td>`).join("")}</tr>`).join("")}</tbody></table>`,
      ariaLabel: "키워드별 업체 노출순위 히트맵",
    });

    el.querySelectorAll("rect.v-hit").forEach((rect) => {
      const r = Number(rect.dataset.r), c = Number(rect.dataset.c);
      const move = (ev) => showTip(
        `<b>${esc(keywords[r])}</b><div class="row">${esc(targets[c])} <b>${fmtRank(cells[r][c])}</b></div>`, ev);
      rect.addEventListener("mousemove", move);
      rect.addEventListener("mouseenter", move);
    });
  }

  /* ══════════════════════════════════════ 4. 시간대별 평균 순위 (막대) */
  function renderHourly(el, opts) {
    const { hourly, primary, firstPage = 15 } = opts;
    const vals = hourly.series[primary] || [];
    const filled = vals.filter((v) => v !== null);
    if (filled.length < 2) {
      return emptyState(el, `시간대별 평균 순위 — ${primary}`,
        "자동 수집이 여러 시간대에 걸쳐 돌면 '몇 시에 순위가 밀리는지'가 여기 나타납니다.");
    }

    const W = 1000, H = 250, PL = 42, PR = 14, PT = 16, PB = 34;
    const maxRank = Math.max(firstPage, ...filled);
    const y = (r) => PT + ((r - 1) / Math.max(1, maxRank - 1)) * (H - PT - PB);
    const slot = (W - PL - PR) / 24;
    const cx = (h) => PL + slot * h + slot / 2;

    const ticks = [...new Set([1, 5, firstPage, Math.round(maxRank)])].filter((v) => v <= maxRank).sort((a, b) => a - b);
    let body = ticks.map((r) =>
      `<line class="${r === firstPage ? "v-thresh" : "v-grid"}" x1="${PL}" x2="${W - PR}" y1="${y(r).toFixed(1)}" y2="${y(r).toFixed(1)}"/>
       <text x="${PL - 8}" y="${(y(r) + 3.5).toFixed(1)}" text-anchor="end">${r}위</text>`).join("");

    const best = hourly.best_hour, worst = hourly.worst_hour;
    hourly.hours.forEach((h) => {
      const v = vals[h];
      body += `<text x="${cx(h).toFixed(1)}" y="${H - 12}" text-anchor="middle">${h % 3 === 0 ? h : ""}</text>`;
      if (v === null) return;
      const isBest = best && best.hour === h, isWorst = worst && worst.hour === h;
      // 위(1위)에서 아래로 내려오는 얇은 스템 + 끝점. 짧을수록 상위.
      body += `<line x1="${cx(h).toFixed(1)}" x2="${cx(h).toFixed(1)}" y1="${PT}" y2="${y(v).toFixed(1)}"
                 stroke="var(--viz-s1)" stroke-width="2" stroke-opacity="${isBest || isWorst ? 1 : 0.45}" stroke-linecap="round"/>
               <circle class="v-dot" cx="${cx(h).toFixed(1)}" cy="${y(v).toFixed(1)}" r="4.5" fill="var(--viz-s1)"/>
               <rect class="v-hit" data-h="${h}" x="${(cx(h) - slot / 2).toFixed(1)}" y="${PT}" width="${slot.toFixed(1)}" height="${H - PT - PB}"/>`;
      if (isBest || isWorst) {
        body += `<text class="v-label" x="${cx(h).toFixed(1)}" y="${(y(v) + 17).toFixed(1)}" text-anchor="middle"
                   style="fill:${isBest ? "var(--viz-good)" : "var(--viz-bad)"}">${isBest ? "가장 좋음" : "가장 밀림"} ${v}</text>`;
      }
    });
    body += `<text x="${W - PR}" y="${H - 12}" text-anchor="end">시(時)</text>`;

    shell(el, {
      title: `시간대별 평균 순위 — ${primary}`,
      note: "스템이 짧을수록 상위",
      legend: "",
      svg: { viewBox: `0 0 ${W} ${H}`, ratio: `${W}/${H}`, minWidth: 620, body },
      table: `<table><thead><tr><th>시간</th><th>평균 순위</th><th>표본</th></tr></thead><tbody>${
        hourly.hours.filter((h) => vals[h] !== null)
          .map((h) => `<tr><td>${String(h).padStart(2, "0")}시</td><td>${vals[h]}</td><td>${hourly.counts[h]}</td></tr>`)
          .join("")}</tbody></table>`,
      ariaLabel: `${primary}의 시간대별 평균 노출순위`,
    });

    el.querySelectorAll("rect.v-hit").forEach((rect) => {
      const h = Number(rect.dataset.h);
      const move = (ev) => showTip(
        `<b>${String(h).padStart(2, "0")}시</b><div class="row">평균 <b>${vals[h]}위</b></div>
         <div class="row" style="color:var(--viz-muted)">표본 ${hourly.counts[h]}건</div>`, ev);
      rect.addEventListener("mousemove", move);
      rect.addEventListener("mouseenter", move);
    });
  }

  /* ══════════════════════════════════════════════════ 5. KPI 스탯 타일 */
  function sparkline(values, color) {
    const pts = values.filter((v) => v !== null && v !== undefined);
    if (pts.length < 2) return "";
    const W = 72, H = 18, max = Math.max(...pts), min = Math.min(...pts);
    const span = Math.max(1, max - min);
    const step = W / (values.length - 1);
    const d = values.map((v, i) => {
      if (v === null || v === undefined) return null;
      const y = 2 + ((v - min) / span) * (H - 4); // 값이 작을수록(상위) 위로
      return `${i * step},${y.toFixed(1)}`;
    }).filter(Boolean);
    return `<svg class="k-spark" viewBox="0 0 ${W} ${H}" aria-hidden="true">
      <polyline points="${d.join(" ")}" fill="none" stroke="${color || "var(--viz-s1)"}"
        stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/></svg>`;
  }

  /* 색만으로 뜻을 전하지 않도록 화살표 + 숫자 + 단위를 항상 붙인다. */
  function deltaHtml(delta, opts) {
    const { unit = "", invert = false, zero = "변화 없음" } = opts || {};
    if (delta === null || delta === undefined) return `<span class="viz-delta flat">—</span>`;
    if (delta === 0) return `<span class="viz-delta flat">${zero}</span>`;
    const good = invert ? delta < 0 : delta > 0;
    return `<span class="viz-delta ${good ? "up" : "down"}">${delta > 0 ? "▲" : "▼"} ${Math.abs(delta)}${unit}</span>`;
  }

  /* 증감은 직전 기록이 있는 키워드끼리만 비교한다(analytics.kpi 와 같은 기준). */
  function pairedDelta(kpi, key, invert) {
    if (!kpi.compared) return `<span class="viz-delta flat">비교할 직전 기록 없음</span>`;
    return deltaHtml(kpi[`${key}_now`] - kpi[`${key}_prev`], { unit: "개", invert });
  }

  function renderKpis(el, kpi, sparks) {
    if (!kpi || !kpi.keywords) { el.innerHTML = ""; return; }
    const tiles = [
      {
        label: `${kpi.target} 평균 순위`,
        value: kpi.avg_rank === null ? "—" : kpi.avg_rank,
        unit: kpi.avg_rank === null ? "" : "위",
        foot: kpi.compared
          ? deltaHtml(kpi.avg_rank_delta, { unit: "위" })
          : `<span class="viz-delta flat">비교할 직전 기록 없음</span>`,
        spark: sparkline(sparks || []),
      },
      {
        label: "첫 페이지 노출",
        value: kpi.first_page,
        unit: ` / ${kpi.keywords}`,
        foot: pairedDelta(kpi, "first_page"),
      },
      {
        label: "상위 3위 이내",
        value: kpi.top3,
        unit: ` / ${kpi.keywords}`,
        foot: pairedDelta(kpi, "top3"),
      },
      {
        label: "순위밖 (미노출)",
        value: kpi.out,
        unit: ` / ${kpi.keywords}`,
        foot: pairedDelta(kpi, "out", true),
      },
    ];
    el.classList.add("viz");
    el.innerHTML = `<div class="kpis">${tiles.map((t) => `
      <div class="kpi">
        <div class="k-label">${esc(t.label)}</div>
        <div class="k-value">${t.value}${t.unit ? `<small>${esc(t.unit)}</small>` : ""}</div>
        <div class="k-foot">${t.foot}${t.spark || ""}</div>
      </div>`).join("")}</div>`;
  }

  global.Viz = {
    colorOf, fmtRank, esc, sparkline, deltaHtml, hideTip,
    renderTrend, renderDumbbell, renderHeatmap, renderHourly, renderKpis,
  };
})(window);
