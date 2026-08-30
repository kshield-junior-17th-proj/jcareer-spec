import {
  COLLECTION_STATE_LABELS,
  CUSTOMER_SIDE_LABELS,
  DOMAIN_LABELS,
  validateSnapshot
} from "./snapshot.js";
import { buildObservationLanes, observationCustomerSides } from "./view-model.js";

const MAX_FILE_BYTES = 2 * 1024 * 1024;
const root = document.querySelector("#snapshot-root");
const fileInput = document.querySelector("#snapshot-file");
const clearButton = document.querySelector("#clear-snapshot");
const ingestionStatus = document.querySelector("#ingestion-status");
const trigger = document.querySelector(".file-trigger");

let currentSnapshot = null;
let loadGeneration = 0;

function createElement(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = String(text);
  return element;
}

function append(parent, ...children) {
  children.filter(Boolean).forEach((child) => parent.append(child));
  return parent;
}

function formatDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "날짜 확인 필요";
  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Seoul"
  }).format(date);
}

function displayAudience(value) {
  return value === "INTERNAL_REVIEW" ? "입력 선언 · 내부 검토 승인" : "승인 범위 미지원";
}

function displayDeployment(value) {
  return ({
    MODEL_ONLY: "snapshot 선언 · Terraform 모델-only",
    LOCAL_RUNTIME_OBSERVED: "snapshot 선언 · 로컬 합성 런타임 관찰",
    LAB_RUNTIME_OBSERVED: "snapshot 선언 · 합성 lab 런타임 관찰",
    NOT_DECLARED: "실행 상태 미선언"
  })[value] || value;
}

function setStatus(message, kind = "neutral") {
  ingestionStatus.replaceChildren();
  if (!message) return;
  const notice = createElement("p", `status-message status-${kind}`, message);
  ingestionStatus.append(notice);
}

function renderEmpty() {
  currentSnapshot = null;
  clearButton.disabled = true;
  root.className = "snapshot-root empty-root";
  root.removeAttribute("aria-busy");
  root.removeAttribute("aria-labelledby");
  root.setAttribute("aria-label", "snapshot 표시 영역");
  root.replaceChildren();

  const spine = createElement("ol", "empty-spine");
  ["생성", "비식별 메타", "승인 메타", "표시"].forEach((label, index) => {
    const step = createElement("li", "empty-spine-step");
    append(step, createElement("span", "spine-node", String(index + 1)), createElement("strong", "", label));
    spine.append(step);
  });

  const copy = createElement("div", "empty-copy");
  append(
    copy,
    createElement("p", "eyebrow", "No snapshot loaded"),
    createElement("h2", "", "표시할 승인 데이터가 없습니다"),
    createElement("p", "", "현재 탭에 불러온 승인된 assessment·measurement snapshot이 없습니다. JSON을 만들거나 숫자를 추정하지 않고 이 상태를 그대로 보여 줍니다.")
  );

  const lanes = createElement("div", "empty-lanes");
  [
    ["지원자", "이력서·지원·설명 관찰"],
    ["기업 고객", "공고·파이프라인·열람 관찰"],
    ["플랫폼", "데이터·공급자·인프라 관찰"]
  ].forEach(([title, body]) => {
    const lane = createElement("section", "empty-lane");
    append(lane, createElement("h3", "", title), createElement("span", "", body), createElement("small", "", "snapshot 입력 대기"));
    lanes.append(lane);
  });

  append(root, append(createElement("div", "empty-intro"), spine, copy), lanes);
}

function renderIssues(issues) {
  root.className = "snapshot-root error-root";
  root.removeAttribute("aria-labelledby");
  root.setAttribute("aria-label", "snapshot 표시 오류");
  root.replaceChildren();
  const panel = createElement("section", "validation-panel");
  append(
    panel,
    createElement("p", "eyebrow", "Snapshot rejected"),
    createElement("h2", "", "이 파일은 표시 계약을 통과하지 못했습니다"),
    createElement("p", "validation-intro", "평가 결과가 잘못됐다는 뜻이 아니라, 이 읽기 화면에 필요한 승인·비식별·출처 필드가 확인되지 않았다는 뜻입니다.")
  );
  const list = createElement("ol", "issue-list");
  issues.slice(0, 20).forEach((issue) => {
    const item = createElement("li");
    append(
      item,
      createElement("code", "", issue.path),
      createElement("strong", "", issue.code),
      createElement("span", "", issue.message)
    );
    list.append(item);
  });
  panel.append(list);
  if (issues.length > 20) panel.append(createElement("p", "issue-overflow", `그 외 ${issues.length - 20}개 오류가 있습니다.`));
  root.append(panel);
  root.focus();
}

function renderMetaValue(label, value, mono = false) {
  const row = createElement("div", "meta-row");
  append(row, createElement("dt", "", label), createElement("dd", mono ? "mono" : "", value));
  return row;
}

function renderSpine(snapshot) {
  const aside = createElement("aside", "evidence-spine");
  aside.setAttribute("aria-label", "snapshot 출처 순서");
  append(aside, createElement("p", "eyebrow light", "Provenance spine"), createElement("h2", "", "표시 전 네 단계"));

  const steps = [
    { number: "01", title: "생성", primary: snapshot.provenance.generator_version, timestamp: snapshot.provenance.generated_at },
    { number: "02", title: "비식별 검토", primary: snapshot.redaction.state, secondary: `${snapshot.redaction.reviewed_by_ref} · ${snapshot.redaction.method_version}` },
    { number: "03", title: "승인 메타데이터", primary: snapshot.approval.approved_by_ref, secondary: snapshot.approval.source_ref, timestamp: snapshot.approval.approved_at },
    { number: "04", title: "현재 표시", primary: "브라우저 메모리", secondary: "저장·전송 없음" }
  ];
  const list = createElement("ol", "spine-list");
  steps.forEach(({ number, title, primary, secondary, timestamp }) => {
    const item = createElement("li");
    const detail = createElement("div");
    append(detail, createElement("strong", "", title), createElement("span", "", primary));
    if (timestamp) {
      const time = createElement("time", "", formatDate(timestamp));
      time.dateTime = timestamp;
      detail.append(time);
    }
    if (secondary) detail.append(createElement("small", "", secondary));
    append(
      item,
      createElement("span", "spine-index", number),
      detail
    );
    list.append(item);
  });
  aside.append(list);

  const integrity = createElement("dl", "integrity-meta");
  append(
    integrity,
    renderMetaValue("Snapshot", snapshot.snapshot_id, true),
    renderMetaValue("Tenant", snapshot.tenant.tenant_ref, true),
    renderMetaValue("실행 범위", displayDeployment(snapshot.scope.deployment_state)),
    renderMetaValue("직접 식별자", "입력 파일 선언 · 없음"),
    snapshot.provenance.source_commit
      ? renderMetaValue("Source commit", snapshot.provenance.source_commit, true)
      : null
  );
  aside.append(integrity);
  return aside;
}

function renderRefs(title, values) {
  const group = createElement("div", "reference-group");
  group.append(createElement("strong", "", title));
  if (!values.length) {
    group.append(createElement("span", "reference-empty", "참조 없음"));
    return group;
  }
  const list = createElement("ul");
  values.forEach((value) => {
    const item = createElement("li");
    item.append(createElement("code", "", value));
    list.append(item);
  });
  group.append(list);
  return group;
}

function renderFacts(facts) {
  if (!facts.length) return null;
  const list = createElement("dl", "fact-list");
  facts.forEach((fact) => {
    const row = createElement("div");
    const value = typeof fact.value === "boolean" ? (fact.value ? "true" : "false") : String(fact.value);
    append(row, createElement("dt", "", fact.label), createElement("dd", "", `${value}${fact.unit ? ` ${fact.unit}` : ""}`));
    list.append(row);
  });
  return list;
}

function renderObservation(observation) {
  const article = createElement("article", `observation state-${observation.collection_state.toLowerCase()}`);
  const heading = createElement("div", "observation-heading");
  const titleGroup = createElement("div");
  const routedSides = observationCustomerSides(observation);
  append(
    titleGroup,
    createElement("span", "domain-label", DOMAIN_LABELS[observation.domain]),
    createElement("h4", "", observation.title),
    routedSides.length > 1
      ? createElement("span", "shared-observation-label", `${routedSides.map((side) => CUSTOMER_SIDE_LABELS[side]).join(" · ")} 공동 관찰`)
      : null
  );
  const state = createElement("span", "collection-state", COLLECTION_STATE_LABELS[observation.collection_state]);
  append(heading, titleGroup, state);
  append(article, heading, createElement("p", "observation-statement", observation.statement));

  const facts = renderFacts(observation.measured_facts);
  if (facts) article.append(facts);

  if (observation.human_decision) {
    const decision = createElement("section", "human-decision");
    append(
      decision,
      createElement("h5", "", "입력 파일의 사람 판단문 · 그대로 표시"),
      createElement("p", "", observation.human_decision.display_text),
      createElement("small", "", `${observation.human_decision.decided_by_ref} · ${formatDate(observation.human_decision.decided_at)} · ${observation.human_decision.source_ref}`)
    );
    article.append(decision);
  }

  const refs = createElement("div", "reference-grid");
  append(refs, renderRefs("Source", observation.source_refs), renderRefs("Evidence", observation.evidence_refs));
  article.append(refs);
  return article;
}

function renderObservationLanes(snapshot) {
  const section = createElement("section", "observation-section");
  const header = createElement("div", "section-heading");
  append(
    header,
    append(createElement("div"), createElement("p", "eyebrow", "Two-sided evidence"), createElement("h2", "", "고객 측별 관찰 기록")),
    createElement("p", "section-count", `고유 관찰 ${snapshot.observations.length}건 · 판정 집계 없음`)
  );
  section.append(header);

  buildObservationLanes(snapshot).forEach(({ side, items }) => {
    const lane = createElement("section", "observation-lane");
    const laneHeader = createElement("header", "lane-header");
    append(laneHeader, createElement("h3", "", CUSTOMER_SIDE_LABELS[side]), createElement("span", "", `${items.length}개 표시`));
    lane.append(laneHeader);
    if (items.length) {
      const cards = createElement("div", "observation-list");
      items.forEach((item) => cards.append(renderObservation(item)));
      lane.append(cards);
    } else {
      lane.append(createElement("p", "lane-empty", "이 고객 측에 대해 snapshot에 기록된 관찰이 없습니다."));
    }
    section.append(lane);
  });
  return section;
}

function renderArtifactIndex(snapshot) {
  const section = createElement("section", "artifact-section");
  const header = createElement("div", "section-heading compact");
  append(
    header,
    append(createElement("div"), createElement("p", "eyebrow", "Source inventory"), createElement("h2", "", "snapshot 원본 목록")),
    createElement("p", "section-count", `${snapshot.provenance.source_artifacts.length}개 source`)
  );
  section.append(header);
  const list = createElement("div", "artifact-list");
  snapshot.provenance.source_artifacts.forEach((artifact, index) => {
    const row = createElement("article", "artifact-row");
    const identity = createElement("div");
    const artifactName = createElement("strong", "", artifact.artifact_ref);
    artifactName.id = `artifact-name-${index}`;
    row.setAttribute("aria-labelledby", artifactName.id);
    append(identity, createElement("span", "artifact-kind", artifact.kind), artifactName);
    const capturedAt = createElement("time", "", formatDate(artifact.captured_at));
    capturedAt.dateTime = artifact.captured_at;
    const digest = createElement("details", "artifact-digest");
    append(
      digest,
      createElement("summary", "", `SHA-256 ${artifact.sha256.slice(0, 12)}…${artifact.sha256.slice(-8)}`),
      createElement("code", "artifact-digest-full", artifact.sha256)
    );
    append(row, identity, capturedAt, digest);
    list.append(row);
  });
  section.append(list);
  return section;
}

function renderSnapshot(snapshot) {
  currentSnapshot = snapshot;
  clearButton.disabled = false;
  root.className = "snapshot-root loaded-root";
  root.replaceChildren();

  const spine = renderSpine(snapshot);
  const content = createElement("div", "snapshot-content");

  const title = createElement("section", "snapshot-title");
  const badges = createElement("div", "snapshot-badges");
  append(
    badges,
    createElement("span", "badge", "AS-IS synthetic"),
    createElement("span", "badge", displayAudience(snapshot.audience)),
    createElement("span", "badge badge-neutral", `${snapshot.observations.length} observations`)
  );
  const snapshotHeading = createElement("h2", "", snapshot.title);
  snapshotHeading.id = "loaded-snapshot-title";
  snapshotHeading.tabIndex = -1;
  append(
    title,
    badges,
    snapshotHeading,
    createElement("p", "", `${snapshot.tenant.display_label} · ${displayDeployment(snapshot.scope.deployment_state)}`),
    createElement("small", "", "이 화면은 collection_state와 사람이 입력한 판단문을 구분해 표시하며 자체 결론을 만들지 않습니다.")
  );

  append(content, title, renderObservationLanes(snapshot), renderArtifactIndex(snapshot));
  append(root, spine, content);
  root.removeAttribute("aria-label");
  root.setAttribute("aria-labelledby", snapshotHeading.id);
  snapshotHeading.focus();
}

async function loadFile(file) {
  if (!file) return;
  const generation = ++loadGeneration;
  currentSnapshot = null;
  clearButton.disabled = true;
  root.setAttribute("aria-busy", "true");
  setStatus("snapshot 파일을 읽고 검증하는 중…");
  if (file.size > MAX_FILE_BYTES) {
    const issues = [{ code: "FILE_SIZE", path: "$", message: "2MB 이하 JSON 파일만 허용합니다." }];
    renderIssues(issues);
    setStatus("파일 크기 제한으로 snapshot을 열지 않았습니다.", "error");
    fileInput.value = "";
    root.removeAttribute("aria-busy");
    return;
  }

  try {
    const parsed = JSON.parse(await file.text());
    if (generation !== loadGeneration) return;
    const result = validateSnapshot(parsed);
    if (!result.ok) {
      currentSnapshot = null;
      clearButton.disabled = true;
      renderIssues(result.issues);
      setStatus(`${result.issues.length}개 계약 오류로 snapshot을 표시하지 않았습니다.`, "error");
      fileInput.value = "";
      return;
    }
    renderSnapshot(result.snapshot);
    setStatus("검증된 snapshot을 브라우저 메모리에서 표시했습니다.", "success");
    fileInput.value = "";
  } catch (error) {
    if (generation !== loadGeneration) return;
    currentSnapshot = null;
    clearButton.disabled = true;
    renderIssues([{ code: "JSON_PARSE", path: "$", message: "유효한 JSON 문서가 아닙니다." }]);
    setStatus(`JSON을 읽지 못했습니다: ${error instanceof Error ? error.message : "형식 오류"}`, "error");
    fileInput.value = "";
  } finally {
    if (generation === loadGeneration) root.removeAttribute("aria-busy");
  }
}

fileInput.addEventListener("change", () => loadFile(fileInput.files?.[0]));

clearButton.addEventListener("click", () => {
  loadGeneration += 1;
  currentSnapshot = null;
  fileInput.value = "";
  setStatus("브라우저 메모리의 snapshot 표시를 비웠습니다.");
  renderEmpty();
  fileInput.focus();
});

["dragenter", "dragover"].forEach((eventName) => {
  trigger.addEventListener(eventName, (event) => {
    event.preventDefault();
    trigger.classList.add("drag-active");
  });
});

["dragleave", "drop"].forEach((eventName) => {
  trigger.addEventListener(eventName, (event) => {
    event.preventDefault();
    trigger.classList.remove("drag-active");
  });
});

trigger.addEventListener("drop", (event) => loadFile(event.dataTransfer?.files?.[0]));

window.addEventListener("pagehide", () => {
  loadGeneration += 1;
  currentSnapshot = null;
  fileInput.value = "";
  setStatus("");
  renderEmpty();
});

renderEmpty();
