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

  function polar(cx, cy, radius, index, count) {
    const angle = -Math.PI / 2 + index * Math.PI * 2 / count;
    return [cx + Math.cos(angle) * radius, cy + Math.sin(angle) * radius];
  }

  function points(values, scale, radius, cx, cy) {
    return values.map((value, index) => polar(cx, cy, radius * value / scale, index, values.length).join(",")).join(" ");
  }

  Object.entries(data.metrics).forEach(([key, value]) => {
    const node = document.querySelector(`[data-metric="${key}"]`);
    if (node) node.textContent = value;
  });

  function renderRadar() {
    const { labels, baseline, targetProjection, scale } = data.radar;
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
      <polygon points="${points(targetProjection, scale, radius, cx, cy)}" class="radar-target"/>
      <polygon points="${points(baseline, scale, radius, cx, cy)}" class="radar-baseline"/>
      ${baseline.map((value, index) => {
        const [x, y] = polar(cx, cy, radius * value / scale, index, count);
        return `<circle cx="${x}" cy="${y}" r="5" class="radar-dot"/>`;
      }).join("")}
      ${labelNodes}
    </svg>`;

    document.querySelector("#radar-values").innerHTML = labels.map((label, index) => `<div>
      <dt>${escapeHtml(label)}</dt>
      <dd><span>AS-IS</span> <b>${baseline[index].toFixed(2).replace(/0$/, "")}</b><span>목표 투영</span> ${targetProjection[index].toFixed(1)}<span>실제 AFTER</span> 없음</dd>
    </div>`).join("");
  }

  function renderPostureStatus() {
    document.querySelector("#posture-status").innerHTML = `
      <article class="measured"><small>BEFORE · AS-IS</small><strong>제한 측정값 있음</strong><span>설계평가·격리 Lab 표본</span></article>
      <article class="projected"><small>TO-BE TARGET</small><strong>목표 투영치</strong><span>${escapeHtml(data.meta.targetStatus)} · 구현/효과성 미검증</span></article>
      <article class="missing"><small>ACTUAL AFTER</small><strong>실측값 없음</strong><span>${escapeHtml(data.radar.actualAfterStatus)}</span></article>`;
  }

  function renderEvidence() {
    document.querySelector("#evidence-bars").innerHTML = data.evidence.map((item) => {
      const percent = Math.round(item.count / data.metrics.controls * 100);
      return `<div class="evidence-row" role="listitem">
        <div class="evidence-label"><span>${escapeHtml(item.label)}</span><b>${item.count}<small> / ${data.metrics.controls}</small></b></div>
        <progress class="bar ${escapeHtml(item.tone)}" max="${data.metrics.controls}" value="${item.count}" aria-label="${escapeHtml(item.label)} ${item.count}개, 전체 ${data.metrics.controls}개 중 ${percent}%">${percent}%</progress>
      </div>`;
    }).join("");
  }

  function renderFindingDetail(item, tabId) {
    const detail = document.querySelector("#finding-detail");
    detail.setAttribute("aria-labelledby", tabId);
    detail.innerHTML = `
      <div class="detail-top"><span>${escapeHtml(item.id)} · 발표용 그룹 · HUMAN REVIEW PENDING</span><b class="priority ${escapeHtml(item.priority.toLowerCase())}">${escapeHtml(item.priority)}</b></div>
      <h3>${escapeHtml(item.title)}</h3>
      <dl>
        <div><dt>직접 자산</dt><dd>${escapeHtml(item.asset)}</dd></div>
        <div><dt>프로젝트 기술항목</dt><dd>${item.controls.map(escapeHtml).join(" · ")} · NIST 공식 통제 ID 아님</dd></div>
        <div><dt>위험 시나리오</dt><dd>${escapeHtml(item.scenario)}</dd></div>
        <div><dt>AS-IS 근거</dt><dd>${escapeHtml(item.evidence)}</dd></div>
        <div><dt>Remediation 상태</dt><dd>${escapeHtml(item.remediation.state)}</dd></div>
        <div><dt>TO-BE 보호조치</dt><dd>${escapeHtml(item.remediation.action)} · ${escapeHtml(item.remediation.targetStatus)}</dd></div>
        <div class="gate"><dt>사람 재검증 게이트</dt><dd>${escapeHtml(item.remediation.verificationGate)}</dd></div>
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

  function renderTraceability() {
    const labels = {
      CHECKLIST: "27개 프로젝트 기술항목",
      FINDING: "6개 검토대기 위험 그룹",
      REMEDIATION: "OPEN_UNVERIFIED 조치",
      UNVERIFIED_TARGET: "미검증 목표 투영",
      HUMAN_REVALIDATION: "동일 조건 재검증·사람 판정"
    };
    document.querySelector("#traceability-chain").innerHTML = data.traceability.chain.map((step, index) => `
      <article class="trace-step">
        <small>0${index + 1}</small>
        <strong>${escapeHtml(labels[step])}</strong>
        <span>${escapeHtml(step)}</span>
      </article>`).join("");

    const binding = data.traceability.sourceBinding;
    document.querySelector("#source-binding").innerHTML = `
      <div><small>SOURCE WORKBOOK</small><strong>${escapeHtml(binding.sourceArtifact)}</strong><code>${escapeHtml(binding.sourceSha256)}</code></div>
      <span aria-hidden="true">→</span>
      <div><small>MAPPED WORKBOOK</small><strong>${escapeHtml(binding.mappedArtifact)}</strong><code>${escapeHtml(binding.mappedSha256)}</code></div>
      <p><b>${escapeHtml(binding.status)}</b> · digest는 입력 파일을 결속하지만 내용의 의미 검토나 사람 승인을 대신하지 않습니다.</p>`;
  }

  function renderRoadmap() {
    document.querySelector("#roadmap-track").innerHTML = data.roadmap.map((item, index) => `<article>
      <div class="phase"><strong>${escapeHtml(item.phase)}</strong><span>${escapeHtml(item.window)}</span></div>
      <div class="roadmap-copy"><small>0${index + 1}</small><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.body)}</p><b>${escapeHtml(item.deliverable)}</b></div>
    </article>`).join("");
  }

  function renderDeployment() {
    document.querySelector("#deployment-gates").innerHTML = data.deployment.requiredGates.map((item) => `
      <li><span>${escapeHtml(item.id)}</span><strong>${escapeHtml(item.label)}</strong><b>OPEN</b></li>`).join("");
    document.querySelector("#aws-deployment-status").textContent = data.deployment.status;
    document.querySelector("#actual-after-status").textContent = data.deployment.actualAfterStatus;
  }

  renderRadar();
  renderPostureStatus();
  renderEvidence();
  renderFindingList();
  renderTraceability();
  renderRoadmap();
  renderDeployment();
})();
