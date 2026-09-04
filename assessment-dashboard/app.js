(function () {
  "use strict";
  const data = window.JCAREER_ASSESSMENT;

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
    const cx = 320, cy = 250, radius = 166, count = labels.length;
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
      return `<text x="${x}" y="${y}" text-anchor="${anchor}" class="radar-label">${label}</text>`;
    }).join("");
    document.querySelector("#radar").innerHTML = `<svg viewBox="0 0 640 500" aria-hidden="true">
      ${rings}${axes}
      <polygon points="${points(target, scale, radius, cx, cy)}" class="radar-target"/>
      <polygon points="${points(baseline, scale, radius, cx, cy)}" class="radar-baseline"/>
      ${baseline.map((value, i) => { const [x,y]=polar(cx,cy,radius*value/scale,i,count); return `<circle cx="${x}" cy="${y}" r="5" class="radar-dot"/>`; }).join("")}
      ${labelNodes}
    </svg>`;
  }

  function renderEvidence() {
    document.querySelector("#evidence-bars").innerHTML = data.evidence.map(item => {
      const percent = Math.round(item.count / data.metrics.controls * 100);
      return `<div class="evidence-row">
        <div class="evidence-label"><span>${item.label}</span><b>${item.count}<small> / 27</small></b></div>
        <div class="bar"><i class="${item.tone}" style="width:${percent}%"></i></div>
      </div>`;
    }).join("");
  }

  function renderFindingList() {
    const list = document.querySelector("#finding-list");
    list.innerHTML = data.findings.map((item, index) => `<button class="finding-row${index === 0 ? " active" : ""}" data-index="${index}">
      <span class="finding-id">${item.id}</span>
      <span class="priority ${item.priority.toLowerCase()}">${item.priority}</span>
      <strong>${item.title}</strong>
      <small>${item.asset}</small>
      <i>↗</i>
    </button>`).join("");
    list.querySelectorAll("button").forEach(button => button.addEventListener("click", () => {
      list.querySelectorAll("button").forEach(item => item.classList.remove("active"));
      button.classList.add("active");
      renderFindingDetail(data.findings[Number(button.dataset.index)]);
    }));
    renderFindingDetail(data.findings[0]);
  }

  function renderFindingDetail(item) {
    document.querySelector("#finding-detail").innerHTML = `
      <div class="detail-top"><span>${item.id}</span><b class="priority ${item.priority.toLowerCase()}">${item.priority}</b></div>
      <h3>${item.title}</h3>
      <dl>
        <div><dt>직접 자산</dt><dd>${item.asset}</dd></div>
        <div><dt>통제 묶음</dt><dd>${item.controls}</dd></div>
        <div><dt>위험 시나리오</dt><dd>${item.scenario}</dd></div>
        <div><dt>AS-IS 근거</dt><dd>${item.evidence}</dd></div>
        <div><dt>TO-BE 보호조치</dt><dd>${item.target}</dd></div>
        <div class="gate"><dt>종료 게이트</dt><dd>${item.gate}</dd></div>
      </dl>`;
  }

  function renderRoadmap() {
    document.querySelector("#roadmap-track").innerHTML = data.roadmap.map((item, index) => `<article>
      <div class="phase"><strong>${item.phase}</strong><span>${item.window}</span></div>
      <div class="roadmap-copy"><small>0${index + 1}</small><h3>${item.title}</h3><p>${item.body}</p><b>${item.deliverable}</b></div>
    </article>`).join("");
  }

  renderRadar();
  renderEvidence();
  renderFindingList();
  renderRoadmap();
})();
