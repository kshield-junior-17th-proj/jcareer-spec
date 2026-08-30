const CONTRACT_URL = "../contracts/mentor_feedback_2026_08_28.json";

const stateLabels = new Map([
  ["DRAFT_FOR_HUMAN_DECISION", "사람 결정 전 초안"],
  ["OBSERVED_WHITEBOARD_2026_08_28_NOT_BASELINE", "화이트보드 관찰 · 기준선 아님"],
  ["MENTOR_PROPOSED_HUMAN_DECISION_PENDING", "멘토 제안 · 사람 결정 대기"],
  ["SOURCE_IMPLEMENTED_SYNTHETIC_RUNTIME", "합성 런타임 source 구현"],
  ["NOT_CLAIMED_AS_PRODUCTION", "운영 서비스로 주장하지 않음"],
  ["OBSERVED_WHITEBOARD_NOT_BASELINE", "화이트보드 관찰 · 기준선 아님"],
  ["PRESENCE_UNVERIFIED", "존재 미확인"],
  ["MENTOR_REQUESTED_INVENTORY_DIMENSION", "멘토 요청 자산 차원"],
  ["SCENARIO_BASELINE_AND_MENTOR_REQUIRED_DIMENSION", "기존 시나리오 + 멘토 필수 대장"],
  ["SCENARIO_BASELINE", "기존 시나리오 기록"],
  ["SCENARIO_BASELINE_AND_TERRAFORM_MODELED", "기존 시나리오 + Terraform 모델"],
  ["TERRAFORM_ASIS_MODELED", "Terraform AS-IS 모델"],
  ["DEPLOYMENT_NOT_INFERRED_FROM_SOURCE", "source로 배포 여부 추론 안 함"],
  ["SCENARIO_DECLARED_WINDOWS_ONLY", "Windows 시나리오에만 기록"],
  ["DOCUMENTED_NOT_LAB_EVIDENCE", "문서 기록 · 실험 증적 아님"],
  ["SCENARIO_DECLARED_NOT_INTRODUCED", "시나리오상 미도입"],
  ["ABSENCE_NOT_EXECUTION_TESTED", "실행 검증 안 됨"],
  ["USER_REQUESTED_MENTOR_SAAS_EXAMPLE", "SaaS 후보로 추가"],
  ["SCENARIO_USE_UNVERIFIED", "시나리오 사용 미확인"],
  ["SOURCE_IMPLEMENTED_LOGICAL_DATABASE", "논리 DB source 구현"],
  ["SYNTHETIC_RUNTIME_ONLY", "합성 런타임 전용"],
  ["SCENARIO_INVENTORY_180_NOT_LAB_FLEET", "시나리오 180대 · lab 아님"],
  ["DOCUMENTED_NOT_PROVISIONED", "문서 기록 · 조달 안 함"],
  ["LOGICALLY_SEPARATE_SOURCE_IMPLEMENTED", "논리 분리 source 구현"],
  ["NOT_IMPLEMENTED_HUMAN_DECISION_PENDING", "미구현 · 사람 결정 대기"],
  ["DISABLED", "기본 비활성"],
  ["NOT_IMPLEMENTED", "구현되지 않음"],
  ["OFFLINE_DEMONSTRATOR_NOT_RUNTIME", "오프라인 합성 시연 · 런타임 아님"],
  ["EXPLANATION_ONLY_NOT_SCORING", "설명 전용 · 점수 변경 안 함"],
  ["synthetic_data_generation", "합성 데이터 생성"],
  ["manifest_and_hash", "manifest · hash 고정"],
  ["offline_training", "오프라인 학습"],
  ["evaluation_observation", "평가값 관찰"],
  ["manual_approval_placeholder", "수동 승인 자리"],
  ["runtime_release_not_implemented", "런타임 배포 미구현"],
  ["HUMAN_ASSIGNMENT_PENDING", "사람 지정 대기"],
  ["HUMAN_DECISION_NOT_RECORDED", "사람 결정 기록 없음"],
  ["NOT_COLLECTED", "자료 미수집"],
  ["PROPOSAL_RECORDED", "제안 기록"],
  ["SOURCE_OBSERVED", "source 관찰"],
  ["SOURCE_CATALOG_AVAILABLE", "source 목록 있음"],
  ["SOURCE_AND_TESTS_AVAILABLE", "source · 테스트 있음"],
  ["OFFLINE_DEMONSTRATOR_AVAILABLE", "오프라인 시연 있음"],
  ["SOURCE_CANDIDATE_AVAILABLE", "source 후보 있음"],
  ["INVENTORY_DIMENSIONS_RECORDED", "자산 차원 기록"],
  ["NOT_INCLUDED_IN_FETCHED_MEETING_NOTE", "회의록에 97개 원문 목록 없음"],
]);

const categoryLabels = {
  INFORMATION_PROCESSING_SYSTEM: "정보처리",
  INFORMATION_PROTECTION_SYSTEM: "정보보호",
  PHYSICAL_ASSET: "물리",
  SAAS: "SaaS",
  DATA_ASSET: "데이터",
  ENDPOINT_ASSET: "단말",
};

const classificationLabels = {
  MANAGEMENT: "관리",
  TECHNICAL: "기술",
  PHYSICAL: "물리",
};

let contract = null;
let activeOrgView = "proposed";
let activeScenarioFilter = "ALL";

function element(tagName, className, text) {
  const node = document.createElement(tagName);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function replace(target, ...children) {
  target.replaceChildren(...children.filter(Boolean));
}

function stateLabel(value) {
  return stateLabels.get(value) || String(value).replaceAll("_", " ").toLowerCase();
}

function stateTone(value) {
  const normalized = String(value);
  if (
    normalized.includes("PENDING") ||
    normalized.includes("UNVERIFIED") ||
    normalized.includes("NOT_RECORDED") ||
    normalized.includes("NOT_INFERRED")
  ) {
    return "pending";
  }
  if (
    normalized.includes("EXCLUDED") ||
    normalized.includes("DISABLED") ||
    normalized.includes("NOT_IMPLEMENTED") ||
    normalized.includes("ABSENCE") ||
    normalized.includes("NOT_INTRODUCED") ||
    normalized.includes("NOT_PROVISIONED") ||
    normalized.includes("NOT_CLAIMED")
  ) {
    return "muted";
  }
  if (
    normalized.includes("OBSERVED") ||
    normalized.includes("MODELED") ||
    normalized.includes("SOURCE") ||
    normalized.includes("DOCUMENTED") ||
    normalized.includes("SCENARIO_BASELINE") ||
    normalized.includes("SYNTHETIC_RUNTIME_ONLY")
  ) {
    return "observed";
  }
  return "proposed";
}

function pill(text, tone = "neutral") {
  return element("span", `pill pill--${tone}`, text);
}

function renderMasterplan() {
  const target = document.querySelector("#masterplan");
  const nodes = contract.ceo_brief.masterplan.map((phase) => {
    const item = element("li", "phase-item");
    item.append(
      element("span", "phase-item__marker", phase.phase.replace("_", " · ")),
      element("h3", "phase-item__title", phase.label),
      element("p", "phase-item__objective", phase.objective),
      pill(stateLabel(phase.approval_state), "pending"),
    );
    return item;
  });
  replace(target, ...nodes);
}

function orgNode(title, state, functions, modifier = "") {
  const node = element("article", `org-node ${modifier}`.trim());
  const heading = element("div", "org-node__heading");
  heading.append(element("h3", "", title), pill(stateLabel(state), stateTone(state)));
  const list = element("ul", "org-node__functions");
  functions.forEach((item) => list.append(element("li", item.moved ? "is-moved" : "", item.label)));
  node.append(heading, list);
  return node;
}

function renderObservedOrganization() {
  const observed = contract.organization.observed_whiteboard;
  const fragment = document.createDocumentFragment();
  const note = element("div", "org-context");
  note.append(
    pill("OBSERVED", "observed"),
    element("p", "", `총 ${observed.total_headcount}명으로 판독됐지만 조직 기준선 교체는 승인되지 않았습니다.`),
  );

  const root = orgNode(
    "명칭 미해결 80명 부서",
    observed.state,
    observed.unresolved_labels.map((label) => ({ label })),
    "org-node--root",
  );
  const branches = element("div", "org-branches org-branches--two");
  branches.append(
    orgNode(
      `AI서비스 · ${observed.ai_service.headcount}명`,
      observed.state,
      observed.ai_service.observed_functions.map((label) => ({ label })),
    ),
    orgNode(
      `정보보안팀 · ${observed.information_security.headcount}명`,
      observed.state,
      observed.information_security.observed_functions.map((label) => ({ label })),
    ),
  );
  fragment.append(note, root, branches);
  return fragment;
}

function renderProposedOrganization() {
  const proposal = contract.organization.mentor_target_proposal;
  const fragment = document.createDocumentFragment();
  const note = element("div", "org-context org-context--proposal");
  note.append(
    pill("MENTOR PROPOSAL", "proposed"),
    element("p", "", proposal.interpretation),
  );

  const root = orgNode(
    "목표 조직 후보",
    proposal.state,
    [
      { label: "인원 · 보고선 · RACI는 사람 결정 대기" },
      { label: "현재 기술 배포 단위는 자동 변경하지 않음" },
    ],
    "org-node--root org-node--proposal",
  );

  const aiFunctions = proposal.ai_service.retained_functions.map((label) => ({ label }));
  proposal.ai_service.moved_out_functions.forEach((label) => {
    aiFunctions.push({ label: `${label} · 인프라팀으로 이동`, moved: true });
  });
  proposal.ai_service.explicitly_not_modeled.forEach((label) => {
    aiFunctions.push({ label: `${label} · 현재 범위 아님`, moved: true });
  });

  const branches = element("div", "org-branches org-branches--three");
  branches.append(
    orgNode("AI서비스", proposal.state, aiFunctions),
    orgNode(
      proposal.infrastructure_team.label,
      proposal.state,
      proposal.infrastructure_team.functions.map((item) => ({ label: item.label })),
      "org-node--highlight",
    ),
    orgNode(
      proposal.information_security_team.label,
      proposal.state,
      proposal.information_security_team.capabilities.map((item) => ({ label: item.label })),
    ),
  );
  fragment.append(note, root, branches);
  return fragment;
}

function renderOrganization() {
  const target = document.querySelector("#org-map");
  replace(target, activeOrgView === "observed" ? renderObservedOrganization() : renderProposedOrganization());

  document.querySelectorAll("[data-org-view]").forEach((button) => {
    const selected = button.dataset.orgView === activeOrgView;
    button.classList.toggle("is-active", selected);
    button.setAttribute("aria-pressed", String(selected));
  });
}

function renderAssetRegister() {
  const target = document.querySelector("#asset-register");
  const tableWrap = element("div", "table-wrap");
  const table = element("table", "asset-table");
  const caption = element("caption", "sr-only", "정보보호시스템과 8월 28일 멘토 자산 후보의 근거 상태");
  const head = element("thead");
  const headRow = element("tr");
  ["자산", "분류", "범위", "현재 확인 상태", "소유자"].forEach((label) => headRow.append(element("th", "", label)));
  head.append(headRow);

  const body = element("tbody");
  contract.assets.items.forEach((asset) => {
    const row = element("tr");
    const labelCell = element("th", "asset-name", asset.label);
    labelCell.scope = "row";
    const categoryCell = element("td");
    categoryCell.dataset.label = "분류";
    categoryCell.append(pill(categoryLabels[asset.category] || asset.category, "neutral"));
    const scopeCell = element("td", "asset-state", stateLabel(asset.scope_state));
    scopeCell.dataset.label = "범위";
    const operationCell = element("td", "asset-state");
    operationCell.dataset.label = "현재 확인 상태";
    operationCell.append(pill(stateLabel(asset.operational_state), stateTone(asset.operational_state)));
    const ownerCell = element("td", "asset-owner", stateLabel(asset.owner));
    ownerCell.dataset.label = "소유자";
    row.append(labelCell, categoryCell, scopeCell, operationCell, ownerCell);
    body.append(row);
  });
  table.append(caption, head, body);
  tableWrap.append(table);

  const exclusions = element("aside", "exclusion-note");
  exclusions.append(element("h3", "", "이번 멘토 제안 범위에서 제외"));
  const list = element("ul");
  contract.assets.scope_exclusions.forEach((item) => {
    const listItem = element("li");
    listItem.append(element("strong", "", item.label), element("span", "", item.note));
    list.append(listItem);
  });
  exclusions.append(list);
  replace(target, tableWrap, exclusions);
}

function definitionRow(term, value, tone, badgeText) {
  const row = element("div", "definition-row");
  row.append(element("dt", "", term), element("dd", "", value));
  if (tone && badgeText) row.append(pill(badgeText, tone));
  return row;
}

function renderTrainingBoundary() {
  const target = document.querySelector("#training-boundary");
  const training = contract.training_and_mlops;

  const matcher = element("article", "boundary-card boundary-card--score");
  matcher.append(
    element("p", "boundary-card__code", "RUNTIME SCORE"),
    element("h3", "", "결정론 매처"),
    element("p", "boundary-card__lead", "점수는 고정 산식이 만들고 Bedrock은 설명만 담당합니다."),
  );
  const matcherFacts = element("dl", "definition-list");
  matcherFacts.append(
    definitionRow("산식", training.runtime_matcher.mode),
    definitionRow(
      "Agent 학습",
      training.runtime_matcher.trains_agent ? "사용" : "사용하지 않음",
      "muted",
      "비활성",
    ),
    definitionRow("Bedrock", stateLabel(training.runtime_matcher.bedrock_role)),
  );
  matcher.append(matcherFacts);

  const transfer = element("article", "boundary-card boundary-card--data");
  transfer.append(
    element("p", "boundary-card__code", "DB → EXPLANATION"),
    element("h3", "", "전송 key를 먼저 계수"),
    element(
      "p",
      "boundary-card__lead",
      "회원DB와 기업DB는 분리되어 있지만 승인된 최소화 allowlist는 아직 없습니다.",
    ),
  );
  const transferFacts = element("dl", "definition-list");
  transferFacts.append(
    definitionRow("지원자 context", `${training.data_transfer.candidate_context_key_count} keys`),
    definitionRow("기업 context", `${training.data_transfer.company_context_key_count} keys`),
    definitionRow("현재 counter", `${training.data_transfer.counter_flagged_key_count} keys`),
    definitionRow(
      "승인 allowlist",
      stateLabel(training.data_transfer.allowlist_state),
      "pending",
      "결정 대기",
    ),
  );
  transfer.append(transferFacts);

  const mlops = element("article", "boundary-card boundary-card--mlops");
  mlops.append(
    element("p", "boundary-card__code", "SYNTHETIC MLOPS"),
    element("h3", "", "오프라인 생명주기"),
    element("p", "boundary-card__lead", "실제 회원·기업 데이터 없이 hash 가능한 합성 artifact만 만듭니다."),
  );
  const lifecycle = element("ol", "lifecycle-list");
  training.synthetic_mlops.lifecycle.forEach((stage) => lifecycle.append(element("li", "", stateLabel(stage))));
  mlops.append(lifecycle, pill(stateLabel(training.synthetic_mlops.state), "observed"));

  const userData = element("article", "boundary-card boundary-card--consent");
  userData.append(
    element("p", "boundary-card__code", "USER DATA TRAINING"),
    element("h3", "", "별도 안내·동의 전 비활성"),
    element("p", "boundary-card__lead", "추천 목적 동의를 학습 동의로 바꾸어 읽지 않습니다."),
  );
  const userFacts = element("dl", "definition-list");
  userFacts.append(
    definitionRow("기본 상태", stateLabel(training.user_data_training.default_state), "muted", "비활성"),
    definitionRow(
      "학습 동의 유형",
      stateLabel(training.user_data_training.current_training_consent_type),
      "pending",
      "미구현",
    ),
    definitionRow("현재 동의", training.user_data_training.current_runtime_consent_types.join(" · ")),
  );
  const gates = element("details", "gate-details");
  gates.append(element("summary", "", "활성화 전에 필요한 7개 경계"));
  const gateList = element("ol");
  training.user_data_training.required_gates_before_any_enablement.forEach((gate) => gateList.append(element("li", "", gate)));
  gates.append(gateList);
  userData.append(userFacts, gates);

  replace(target, matcher, transfer, mlops, userData);
}

function renderScenarios() {
  const target = document.querySelector("#scenario-list");
  const scenarios = contract.ceo_brief.candidate_scenarios.filter(
    (item) => activeScenarioFilter === "ALL" || item.classification === activeScenarioFilter,
  );
  const items = scenarios.map((scenario) => {
    const item = element("li", "scenario-card");
    item.dataset.classification = scenario.classification;

    const ordinal = element("span", "scenario-card__ordinal", scenario.id);
    const heading = element("div", "scenario-card__heading");
    heading.append(
      pill(classificationLabels[scenario.classification], scenario.classification.toLowerCase()),
      element("h3", "", scenario.title),
    );
    const journey = element("div", "scenario-card__journey");
    const observed = element("div", "journey-block");
    observed.append(element("span", "journey-block__label", "관찰"), element("p", "", scenario.observation));
    const arrow = element("span", "journey-arrow", "→");
    arrow.setAttribute("aria-hidden", "true");
    const candidate = element("div", "journey-block journey-block--candidate");
    candidate.append(
      element("span", "journey-block__label", "개선 후보"),
      element("p", "", scenario.improvement_candidate),
    );
    journey.append(observed, arrow, candidate);

    const metadata = element("div", "scenario-card__meta");
    metadata.append(
      pill(scenario.phase.replaceAll("_", " · "), "neutral"),
      pill(stateLabel(scenario.owner), "pending"),
      pill(stateLabel(scenario.evidence_state), stateTone(scenario.evidence_state)),
    );
    item.append(ordinal, heading, journey, metadata);
    return item;
  });
  replace(target, ...items);

  document.querySelectorAll("[data-scenario-filter]").forEach((button) => {
    const selected = button.dataset.scenarioFilter === activeScenarioFilter;
    button.classList.toggle("is-active", selected);
    button.setAttribute("aria-pressed", String(selected));
  });
}

function renderChecklist() {
  const target = document.querySelector("#checklist-state");
  const checklist = contract.checklist;
  const count = element("div", "checklist-count");
  count.append(
    element("strong", "", checklist.declared_item_count),
    element("span", "", "개 원본 유지"),
  );
  const explanation = element("div", "checklist-copy");
  explanation.append(
    element("p", "", checklist.display_policy),
    element(
      "p",
      "checklist-copy__warning",
      `현재 원문 항목 import ${checklist.full_items_imported}개 · ${stateLabel(checklist.full_item_source_state)} · 완료 주장 안 함`,
    ),
  );
  replace(target, count, explanation);
}

function renderSource() {
  const sourceLink = document.querySelector("#source-link");
  sourceLink.href = contract.source.notion_url;
  sourceLink.setAttribute("aria-label", `${contract.source.title} 노션 원문 새 탭에서 열기`);
  document.querySelector("#contract-version").textContent = contract.schema_version;
}

function renderAll() {
  renderSource();
  renderMasterplan();
  renderOrganization();
  renderAssetRegister();
  renderTrainingBoundary();
  renderScenarios();
  renderChecklist();
  const state = document.querySelector("#load-state");
  state.textContent = `${contract.source.title} · ${contract.source.section} 기준 초안을 표시했습니다.`;
  state.classList.add("is-ready");
}

function bindInteractions() {
  document.querySelectorAll("[data-org-view]").forEach((button) => {
    button.addEventListener("click", () => {
      activeOrgView = button.dataset.orgView;
      renderOrganization();
    });
  });
  document.querySelectorAll("[data-scenario-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      activeScenarioFilter = button.dataset.scenarioFilter;
      renderScenarios();
    });
  });
}

async function loadContract() {
  bindInteractions();
  try {
    const response = await fetch(CONTRACT_URL, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    if (payload.schema_version !== "jcareer-mentor-feedback-2026-08-28-v1") {
      throw new Error("지원하지 않는 계약 버전입니다.");
    }
    contract = payload;
    renderAll();
  } catch (error) {
    const state = document.querySelector("#load-state");
    state.setAttribute("role", "alert");
    state.classList.add("is-error");
    state.textContent = `브리프 계약을 읽지 못했습니다: ${error.message}. README의 로컬 서버 실행 방법을 확인해 주세요.`;
  }
}

loadContract();
