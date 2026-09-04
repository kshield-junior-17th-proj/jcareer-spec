(function () {
  "use strict";

  const data = window.JCAREER_ASSESSMENT;
  if (!data) return;

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  Object.entries(data.metrics).forEach(([key, value]) => {
    const node = document.querySelector(`[data-metric="${key}"]`);
    if (node) node.textContent = value;
  });

  function polar(cx, cy, radius, index, count) {
    const angle = -Math.PI / 2 + index * Math.PI * 2 / count;
    return [cx + Math.cos(angle) * radius, cy + Math.sin(angle) * radius];
  }

  function points(values, scale, radius, cx, cy) {
    return values.map((value, index) => polar(cx, cy, radius * value / scale, index, values.length).join(",")).join(" ");
  }

  function renderRadar() {
    const { labels, baseline, target, scale } = data.radar;
    const cx = 320;
    const cy = 250;
    const radius = 166;
    const count = labels.length;
    const rings = Array.from({ length: scale }, (_, level) => {
      const ringPoints = labels.map((_, index) => polar(cx, cy, radius * (level + 1) / scale, index, count).join(",")).join(" ");
      return `<polygon points="${ringPoints}" class="radar-ring"/>`;
    }).join("");
    const axes = labels.map((_, index) => {
      const end = polar(cx, cy, radius, index, count);
      return `<line x1="${cx}" y1="${cy}" x2="${end[0]}" y2="${end[1]}" class="radar-axis"/>`;
    }).join("");
    const labelNodes = labels.map((label, index) => {
      const [x, y] = polar(cx, cy, radius + 48, index, count);
      const anchor = Math.abs(x - cx) < 25 ? "middle" : (x < cx ? "end" : "start");
      return `<text x="${x}" y="${y}" text-anchor="${anchor}" class="radar-label">${escapeHtml(label)}</text>`;
    }).join("");
    const radar = document.querySelector("#radar");
    radar.innerHTML = `<svg viewBox="0 0 640 500" aria-hidden="true" focusable="false">
      ${rings}${axes}
      <polygon points="${points(target, scale, radius, cx, cy)}" class="radar-target"/>
      <polygon points="${points(baseline, scale, radius, cx, cy)}" class="radar-baseline"/>
      ${baseline.map((value, index) => {
        const [x, y] = polar(cx, cy, radius * value / scale, index, count);
        return `<circle cx="${x}" cy="${y}" r="5" class="radar-dot"/>`;
      }).join("")}
      ${labelNodes}
    </svg>`;

    document.querySelector("#radar-values").innerHTML = labels.map((label, index) => `<div>
      <dt>${escapeHtml(label)}</dt>
      <dd><span>현재</span> <b>${baseline[index].toFixed(2).replace(/0$/, "")}</b><span>제안 목표</span> ${target[index].toFixed(1)}</dd>
    </div>`).join("");
  }

  function renderEvidence() {
    document.querySelector("#evidence-bars").innerHTML = data.evidence.map((item) => {
      const percent = Math.round(item.count / data.metrics.controls * 100);
      return `<div class="evidence-row" role="listitem">
        <div class="evidence-label"><span>${escapeHtml(item.label)}</span><b>${item.count}<small> / ${data.metrics.controls}</small></b></div>
        <div class="bar" role="img" aria-label="${escapeHtml(item.label)} ${item.count}개, 전체 ${data.metrics.controls}개 중 ${percent}%"><i class="${escapeHtml(item.tone)}" style="--bar-size:${percent}%"></i></div>
      </div>`;
    }).join("");
  }

  function renderFindingDetail(item, tabId) {
    const detail = document.querySelector("#finding-detail");
    detail.setAttribute("aria-labelledby", tabId);
    detail.innerHTML = `
      <div class="detail-top"><span>${escapeHtml(item.id)}</span><b class="priority ${escapeHtml(item.priority.toLowerCase())}">${escapeHtml(item.priority)}</b></div>
      <h3>${escapeHtml(item.title)}</h3>
      <dl>
        <div><dt>직접 자산</dt><dd>${escapeHtml(item.asset)}</dd></div>
        <div><dt>프로젝트 기술항목</dt><dd>${escapeHtml(item.controls)} · NIST 하위범주 ID 아님</dd></div>
        <div><dt>위험 시나리오</dt><dd>${escapeHtml(item.scenario)}</dd></div>
        <div><dt>현재 근거</dt><dd>${escapeHtml(item.evidence)}</dd></div>
        <div><dt>제안 보호조치</dt><dd>${escapeHtml(item.target)}</dd></div>
        <div class="gate"><dt>종료 게이트</dt><dd>${escapeHtml(item.gate)}</dd></div>
      </dl>`;
  }

  function selectFinding(button, focus) {
    const list = document.querySelector("#finding-list");
    const buttons = Array.from(list.querySelectorAll("[role=tab]"));
    buttons.forEach((item) => {
      const selected = item === button;
      item.setAttribute("aria-selected", String(selected));
      item.tabIndex = selected ? 0 : -1;
    });
    renderFindingDetail(data.findings[Number(button.dataset.index)], button.id);
    if (focus) button.focus();
  }

  function renderFindingList() {
    const list = document.querySelector("#finding-list");
    list.innerHTML = data.findings.map((item, index) => `<button class="finding-row" type="button" role="tab" id="finding-tab-${index}" aria-selected="${index === 0}" aria-controls="finding-detail" tabindex="${index === 0 ? 0 : -1}" data-index="${index}">
      <span class="finding-id">${escapeHtml(item.id)}</span>
      <span class="priority ${escapeHtml(item.priority.toLowerCase())}">${escapeHtml(item.priority)}</span>
      <strong>${escapeHtml(item.title)}</strong>
      <small>${escapeHtml(item.asset)}</small>
      <i aria-hidden="true">↗</i>
    </button>`).join("");

    const buttons = Array.from(list.querySelectorAll("[role=tab]"));
    buttons.forEach((button) => {
      button.addEventListener("click", () => selectFinding(button, false));
      button.addEventListener("keydown", (event) => {
        const current = buttons.indexOf(button);
        const nextIndex = event.key === "ArrowDown" || event.key === "ArrowRight"
          ? (current + 1) % buttons.length
          : event.key === "ArrowUp" || event.key === "ArrowLeft"
            ? (current - 1 + buttons.length) % buttons.length
            : event.key === "Home"
              ? 0
              : event.key === "End"
                ? buttons.length - 1
                : -1;
        if (nextIndex < 0) return;
        event.preventDefault();
        selectFinding(buttons[nextIndex], true);
      });
    });
    renderFindingDetail(data.findings[0], buttons[0].id);
  }

  function renderRoadmap() {
    document.querySelector("#roadmap-track").innerHTML = data.roadmap.map((item, index) => `<article>
      <div class="phase"><strong>${escapeHtml(item.phase)}</strong><span>${escapeHtml(item.window)}</span></div>
      <div class="roadmap-copy"><small>0${index + 1}</small><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.body)}</p><b>${escapeHtml(item.deliverable)}</b></div>
    </article>`).join("");
  }

  renderRadar();
  renderEvidence();
  renderFindingList();
  renderRoadmap();
})();
