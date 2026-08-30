export const SNAPSHOT_SCHEMA_VERSION = "jcareer-consulting-snapshot/v1";

export const COLLECTION_STATE_LABELS = Object.freeze({
  RECORDED: "관찰값 있음",
  NOT_MEASURED: "측정하지 않음",
  NOT_IMPLEMENTED: "구현 표면 없음",
  UNVERIFIED: "검증 전",
  INPUT_MISSING: "입력 없음"
});

export const CUSTOMER_SIDE_LABELS = Object.freeze({
  candidate: "지원자",
  company: "기업 고객",
  platform: "플랫폼 운영"
});

export const DOMAIN_LABELS = Object.freeze({
  "customer-journey": "고객 여정",
  "data-boundary": "데이터 경계",
  "access-and-audit": "접근·감사",
  "ai-score-and-explanation": "점수·설명",
  "retention-and-deletion": "보존·삭제",
  "infrastructure-model": "인프라 모델",
  "provider-boundary": "외부 공급자 경계"
});

const TOP_LEVEL_KEYS = [
  "schema_version",
  "snapshot_id",
  "title",
  "tenant",
  "audience",
  "approval",
  "redaction",
  "provenance",
  "scope",
  "observations"
];

const AUDIENCE_APPROVAL = Object.freeze({
  INTERNAL_REVIEW: "APPROVED_FOR_INTERNAL_REVIEW"
});

const TENANT_REF_PATTERN = /^tenant-[a-z0-9][a-z0-9-]{2,47}$/;
const FORBIDDEN_KEY = /(?:^|_)(?:account_id|aws_account|access_key|secret|secret_access_key|session_token|authorization|password|credential|email|phone|birth_date|resident_number|candidate_name|company_registration_number|ip_address|raw_prompt|resume_text|self_intro|model_id|model_arn|database_url|redis_url|service_endpoint|resource_arn|db_dsn)(?:_|$)/i;

const SENSITIVE_VALUE_PATTERNS = [
  ["unsafe-display-control", /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F-\u009F\u200B-\u200F\u202A-\u202E\u2060-\u206F\uFEFF]/],
  ["aws-account-id", /\b\d{12}\b/],
  ["aws-access-key", /\b(?:AKIA|ASIA)[A-Z0-9]{16}\b/],
  ["private-key", /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/],
  ["bearer-token", /\bBearer\s+[A-Za-z0-9._~+\/-]+=*/i],
  ["email-address", /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/i],
  ["phone-number", /\b01[016789][ -]?\d{3,4}[ -]?\d{4}\b/],
  ["ipv4-address", /\b(?:\d{1,3}\.){3}\d{1,3}\b/],
  ["canonical-uuid", /\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b/i],
  ["cloud-resource-arn", /\barn:(?:aws|aws-us-gov|aws-cn):[a-z0-9-]+:/i],
  ["database-or-cache-url", /\b(?:postgres(?:ql)?|redis|mysql|mariadb|mongodb(?:\+srv)?):\/\//i],
  ["aws-service-endpoint", /\b(?:[a-z0-9-]+\.)+amazonaws\.com(?:\.cn)?\b/i],
  ["network-url", /\bhttps?:\/\/[^\s]+/i],
  ["windows-absolute-path", /(?:^|[\s("' ])(?:[a-z]:[\\/]|\\\\)[^\r\n]*/i],
  ["unix-absolute-path", /(?:^|[\s("' ])\/(?:Users|home|root|var|tmp|etc|opt|srv|mnt|data)(?:\/|\b)/i]
];

const ISO_DATE_TIME = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?(Z|([+-])(\d{2}):(\d{2}))$/;

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function addIssue(issues, code, path, message) {
  issues.push({ code, path, message });
}

function checkKeys(value, allowed, path, issues) {
  if (!isPlainObject(value)) {
    addIssue(issues, "TYPE_OBJECT_REQUIRED", path, "객체가 필요합니다.");
    return false;
  }
  const allowedSet = new Set(allowed);
  for (const key of Object.keys(value)) {
    if (!allowedSet.has(key)) {
      addIssue(issues, "UNKNOWN_FIELD", `${path}.${key}`, "계약에 없는 필드입니다.");
    }
  }
  return true;
}

function requiredString(value, path, issues, { min = 1, max = 240, pattern } = {}) {
  if (typeof value !== "string") {
    addIssue(issues, "STRING_REQUIRED", path, "문자열이 필요합니다.");
    return false;
  }
  if (value.length < min || value.length > max) {
    addIssue(issues, "STRING_LENGTH", path, `${min}~${max}자여야 합니다.`);
    return false;
  }
  if (pattern && !pattern.test(value)) {
    addIssue(issues, "STRING_PATTERN", path, "허용된 가명 참조 형식이 아닙니다.");
    return false;
  }
  return true;
}

function requiredLogicalReference(value, path, issues, { allowFragment = true } = {}) {
  if (!requiredString(value, path, issues, { max: 240 })) return false;
  const parts = value.split("#");
  const base = parts[0];
  const segments = base.split("/");
  const invalid = (
    parts.length > (allowFragment ? 2 : 1)
    || (parts.length === 2 && parts[1].length === 0)
    || /^[a-z][a-z0-9+.-]*:/i.test(base)
    || base.startsWith("/")
    || base.startsWith("\\")
    || base.includes("\\")
    || segments.some((segment) => !segment || segment === "." || segment === "..")
  );
  if (invalid) {
    addIssue(issues, "LOGICAL_REFERENCE_REQUIRED", path, "절대경로·URL·상위경로가 아닌 snapshot 내부 논리 상대 참조가 필요합니다.");
    return false;
  }
  return true;
}

function parseStrictDateTime(value) {
  if (typeof value !== "string") return null;
  const match = value.match(ISO_DATE_TIME);
  if (!match) return null;
  const [, yearText, monthText, dayText, hourText, minuteText, secondText, , zone, , offsetHourText, offsetMinuteText] = match;
  const year = Number(yearText);
  const month = Number(monthText);
  const day = Number(dayText);
  const hour = Number(hourText);
  const minute = Number(minuteText);
  const second = Number(secondText);
  if (month < 1 || month > 12) return null;
  const daysInMonth = new Date(Date.UTC(year, month, 0)).getUTCDate();
  if (day < 1 || day > daysInMonth || hour > 23 || minute > 59 || second > 59) return null;
  if (zone !== "Z") {
    const offsetHour = Number(offsetHourText);
    const offsetMinute = Number(offsetMinuteText);
    if (offsetHour > 14 || offsetMinute > 59 || (offsetHour === 14 && offsetMinute !== 0)) return null;
  }
  const timestamp = Date.parse(value);
  return Number.isNaN(timestamp) ? null : timestamp;
}

function requiredDate(value, path, issues) {
  if (!requiredString(value, path, issues, { max: 40 })) return false;
  if (parseStrictDateTime(value) === null) {
    addIssue(issues, "DATE_TIME_REQUIRED", path, "ISO 8601 date-time이 필요합니다.");
    return false;
  }
  return true;
}

function requiredEnum(value, options, path, issues) {
  if (!options.includes(value)) {
    addIssue(issues, "ENUM_VALUE", path, `허용값: ${options.join(", ")}`);
    return false;
  }
  return true;
}

function requiredArray(value, path, issues, { min = 0, max = 500 } = {}) {
  if (!Array.isArray(value)) {
    addIssue(issues, "ARRAY_REQUIRED", path, "배열이 필요합니다.");
    return false;
  }
  if (value.length < min || value.length > max) {
    addIssue(issues, "ARRAY_LENGTH", path, `${min}~${max}개 항목이어야 합니다.`);
    return false;
  }
  return true;
}

function checkUniqueReferences(value, path, issues, options = {}) {
  if (!requiredArray(value, path, issues, options)) return;
  const seen = new Set();
  value.forEach((item, index) => {
    if (requiredLogicalReference(item, `${path}[${index}]`, issues)) {
      if (seen.has(item)) addIssue(issues, "DUPLICATE_VALUE", `${path}[${index}]`, "중복 참조입니다.");
      seen.add(item);
    }
  });
}

function validateApproval(snapshot, issues) {
  const value = snapshot.approval;
  if (!checkKeys(value, ["state", "approved_by_ref", "approved_at", "source_ref"], "$.approval", issues)) return;
  requiredEnum(value.state, Object.values(AUDIENCE_APPROVAL), "$.approval.state", issues);
  requiredString(value.approved_by_ref, "$.approval.approved_by_ref", issues, {
    max: 56,
    pattern: /^reviewer-[a-z0-9][a-z0-9-]{2,47}$/
  });
  requiredDate(value.approved_at, "$.approval.approved_at", issues);
  requiredLogicalReference(value.source_ref, "$.approval.source_ref", issues);
  const expected = AUDIENCE_APPROVAL[snapshot.audience];
  if (expected && value.state !== expected) {
    addIssue(issues, "AUDIENCE_APPROVAL_MISMATCH", "$.approval.state", "audience와 사람 승인 범위가 다릅니다.");
  }
}

function validateRedaction(value, issues) {
  if (!checkKeys(value, ["state", "contains_direct_identifiers", "method_version", "reviewed_by_ref"], "$.redaction", issues)) return;
  if (value.state !== "REDACTED") addIssue(issues, "REDACTION_REQUIRED", "$.redaction.state", "REDACTED snapshot만 읽습니다.");
  if (value.contains_direct_identifiers !== false) addIssue(issues, "DIRECT_IDENTIFIER_FLAG", "$.redaction.contains_direct_identifiers", "직접 식별자 없음(false)이 필요합니다.");
  requiredString(value.method_version, "$.redaction.method_version", issues, { max: 80 });
  requiredString(value.reviewed_by_ref, "$.redaction.reviewed_by_ref", issues, {
    max: 56,
    pattern: /^reviewer-[a-z0-9][a-z0-9-]{2,47}$/
  });
}

function validateArtifact(value, index, issues) {
  const path = `$.provenance.source_artifacts[${index}]`;
  if (!checkKeys(value, ["tenant_ref", "artifact_ref", "kind", "sha256", "captured_at"], path, issues)) return;
  requiredString(value.tenant_ref, `${path}.tenant_ref`, issues, { max: 56, pattern: TENANT_REF_PATTERN });
  requiredLogicalReference(value.artifact_ref, `${path}.artifact_ref`, issues, { allowFragment: false });
  requiredEnum(value.kind, ["assessment", "measurement", "scanner", "runtime", "plan", "document"], `${path}.kind`, issues);
  requiredString(value.sha256, `${path}.sha256`, issues, { min: 64, max: 64, pattern: /^[a-f0-9]{64}$/ });
  requiredDate(value.captured_at, `${path}.captured_at`, issues);
}

function validateProvenance(value, issues) {
  const artifactRefs = new Set();
  if (!checkKeys(value, ["generated_at", "generator_version", "source_commit", "source_artifacts"], "$.provenance", issues)) return artifactRefs;
  requiredDate(value.generated_at, "$.provenance.generated_at", issues);
  requiredString(value.generator_version, "$.provenance.generator_version", issues, { max: 80 });
  if (value.source_commit !== undefined) {
    requiredString(value.source_commit, "$.provenance.source_commit", issues, { min: 7, max: 64, pattern: /^[a-f0-9]{7,64}$/ });
  }
  if (requiredArray(value.source_artifacts, "$.provenance.source_artifacts", issues, { min: 1, max: 100 })) {
    value.source_artifacts.forEach((artifact, index) => {
      validateArtifact(artifact, index, issues);
      if (isPlainObject(artifact) && typeof artifact.artifact_ref === "string") {
        if (artifactRefs.has(artifact.artifact_ref)) {
          addIssue(issues, "DUPLICATE_ARTIFACT", `$.provenance.source_artifacts[${index}].artifact_ref`, "artifact_ref가 중복됩니다.");
        }
        artifactRefs.add(artifact.artifact_ref);
      }
    });
  }
  return artifactRefs;
}

function validateReferenceIntegrity(snapshot, artifactRefs, issues) {
  const checkReference = (value, path) => {
    if (typeof value !== "string") return;
    const artifactRef = value.split("#", 1)[0];
    if (!artifactRefs.has(artifactRef)) {
      addIssue(issues, "UNRESOLVED_ARTIFACT_REFERENCE", path, "source artifact inventory에 연결되지 않은 참조입니다.");
    }
  };

  if (isPlainObject(snapshot.approval)) checkReference(snapshot.approval.source_ref, "$.approval.source_ref");
  if (!Array.isArray(snapshot.observations)) return;
  snapshot.observations.forEach((observation, observationIndex) => {
    if (!isPlainObject(observation)) return;
    if (Array.isArray(observation.source_refs)) {
      observation.source_refs.forEach((value, index) => checkReference(value, `$.observations[${observationIndex}].source_refs[${index}]`));
    }
    if (Array.isArray(observation.evidence_refs)) {
      observation.evidence_refs.forEach((value, index) => checkReference(value, `$.observations[${observationIndex}].evidence_refs[${index}]`));
    }
    if (isPlainObject(observation.human_decision)) {
      checkReference(observation.human_decision.source_ref, `$.observations[${observationIndex}].human_decision.source_ref`);
    }
  });
}

function validateChronology(snapshot, issues) {
  const generatedAt = parseStrictDateTime(snapshot.provenance?.generated_at);
  const approvedAt = parseStrictDateTime(snapshot.approval?.approved_at);
  if (generatedAt !== null && approvedAt !== null && approvedAt < generatedAt) {
    addIssue(issues, "APPROVAL_BEFORE_GENERATION", "$.approval.approved_at", "승인 시각이 snapshot 생성 시각보다 빠릅니다.");
  }
  if (generatedAt !== null && Array.isArray(snapshot.provenance?.source_artifacts)) {
    snapshot.provenance.source_artifacts.forEach((artifact, index) => {
      const capturedAt = parseStrictDateTime(artifact?.captured_at);
      if (capturedAt !== null && capturedAt > generatedAt) {
        addIssue(issues, "ARTIFACT_AFTER_GENERATION", `$.provenance.source_artifacts[${index}].captured_at`, "artifact 수집 시각이 snapshot 생성 시각보다 늦습니다.");
      }
    });
  }
  if (generatedAt !== null && Array.isArray(snapshot.observations)) {
    snapshot.observations.forEach((observation, index) => {
      const decidedAt = parseStrictDateTime(observation?.human_decision?.decided_at);
      if (decidedAt !== null && decidedAt > generatedAt) {
        addIssue(issues, "DECISION_AFTER_GENERATION", `$.observations[${index}].human_decision.decided_at`, "사람 판단 시각이 이를 포함한 snapshot 생성 시각보다 늦습니다.");
      }
    });
  }
}

function validateCustomerSideScope(snapshot, issues) {
  if (!Array.isArray(snapshot.scope?.customer_sides) || !Array.isArray(snapshot.observations)) return;
  const declaredCustomerSides = new Set(snapshot.scope.customer_sides);
  snapshot.observations.forEach((observation, index) => {
    const sides = Array.isArray(observation?.customer_sides)
      ? observation.customer_sides
      : [observation?.customer_side];
    sides.forEach((side, sideIndex) => {
      if ((side === "candidate" || side === "company") && !declaredCustomerSides.has(side)) {
        const suffix = Array.isArray(observation?.customer_sides) ? `.customer_sides[${sideIndex}]` : ".customer_side";
        addIssue(issues, "CUSTOMER_SIDE_OUT_OF_SCOPE", `$.observations[${index}]${suffix}`, "scope.customer_sides에 선언되지 않은 고객 측입니다.");
      }
    });
  });
}

function validateTenantBinding(snapshot, issues) {
  const tenantRef = snapshot.tenant?.tenant_ref;
  if (typeof tenantRef !== "string" || !TENANT_REF_PATTERN.test(tenantRef)) return;
  if (Array.isArray(snapshot.provenance?.source_artifacts)) {
    snapshot.provenance.source_artifacts.forEach((artifact, index) => {
      if (typeof artifact?.tenant_ref === "string" && artifact.tenant_ref !== tenantRef) {
        addIssue(issues, "TENANT_SCOPE_MISMATCH", `$.provenance.source_artifacts[${index}].tenant_ref`, "artifact가 snapshot tenant와 결속되지 않았습니다.");
      }
    });
  }
  if (Array.isArray(snapshot.observations)) {
    snapshot.observations.forEach((observation, index) => {
      if (typeof observation?.tenant_ref === "string" && observation.tenant_ref !== tenantRef) {
        addIssue(issues, "TENANT_SCOPE_MISMATCH", `$.observations[${index}].tenant_ref`, "관찰 항목이 snapshot tenant와 결속되지 않았습니다.");
      }
    });
  }
}

function validateScope(value, issues) {
  if (!checkKeys(value, ["environment", "deployment_state", "customer_sides"], "$.scope", issues)) return;
  if (value.environment !== "AS_IS_SYNTHETIC") addIssue(issues, "ENVIRONMENT_SCOPE", "$.scope.environment", "AS_IS_SYNTHETIC만 허용합니다.");
  requiredEnum(value.deployment_state, ["MODEL_ONLY", "LOCAL_RUNTIME_OBSERVED", "LAB_RUNTIME_OBSERVED", "NOT_DECLARED"], "$.scope.deployment_state", issues);
  if (requiredArray(value.customer_sides, "$.scope.customer_sides", issues, { min: 1, max: 2 })) {
    const seen = new Set();
    value.customer_sides.forEach((side, index) => {
      requiredEnum(side, ["candidate", "company"], `$.scope.customer_sides[${index}]`, issues);
      if (seen.has(side)) addIssue(issues, "DUPLICATE_VALUE", `$.scope.customer_sides[${index}]`, "중복 고객 측입니다.");
      seen.add(side);
    });
  }
}

function validateMeasuredFact(value, observationPath, index, issues) {
  const path = `${observationPath}.measured_facts[${index}]`;
  if (!checkKeys(value, ["label", "value", "unit"], path, issues)) return;
  requiredString(value.label, `${path}.label`, issues, { max: 80 });
  if (!["string", "number", "boolean"].includes(typeof value.value) || (typeof value.value === "number" && !Number.isFinite(value.value))) {
    addIssue(issues, "FACT_VALUE", `${path}.value`, "유한한 숫자, 문자열 또는 boolean만 허용합니다.");
  }
  if (value.unit !== undefined) requiredString(value.unit, `${path}.unit`, issues, { max: 40 });
}

function validateHumanDecision(value, path, issues) {
  if (!checkKeys(value, ["owner", "display_text", "decided_by_ref", "decided_at", "source_ref"], path, issues)) return;
  if (value.owner !== "HUMAN") addIssue(issues, "HUMAN_OWNER_REQUIRED", `${path}.owner`, "사람 소유 값만 표시할 수 있습니다.");
  requiredString(value.display_text, `${path}.display_text`, issues, { max: 300 });
  requiredString(value.decided_by_ref, `${path}.decided_by_ref`, issues, {
    max: 56,
    pattern: /^reviewer-[a-z0-9][a-z0-9-]{2,47}$/
  });
  requiredDate(value.decided_at, `${path}.decided_at`, issues);
  requiredLogicalReference(value.source_ref, `${path}.source_ref`, issues);
}

function validateObservation(value, index, issues, ids) {
  const path = `$.observations[${index}]`;
  const keys = ["tenant_ref", "observation_id", "domain", "customer_side", "customer_sides", "title", "statement", "collection_state", "source_refs", "evidence_refs", "measured_facts", "human_decision"];
  if (!checkKeys(value, keys, path, issues)) return;
  requiredString(value.tenant_ref, `${path}.tenant_ref`, issues, { max: 56, pattern: TENANT_REF_PATTERN });
  if (requiredString(value.observation_id, `${path}.observation_id`, issues, { max: 68, pattern: /^obs-[a-z0-9][a-z0-9-]{2,63}$/ })) {
    if (ids.has(value.observation_id)) addIssue(issues, "DUPLICATE_OBSERVATION", `${path}.observation_id`, "observation_id가 중복됩니다.");
    ids.add(value.observation_id);
  }
  requiredEnum(value.domain, Object.keys(DOMAIN_LABELS), `${path}.domain`, issues);
  requiredEnum(value.customer_side, Object.keys(CUSTOMER_SIDE_LABELS), `${path}.customer_side`, issues);
  if (value.customer_sides !== undefined && requiredArray(value.customer_sides, `${path}.customer_sides`, issues, { min: 1, max: 2 })) {
    const seenSides = new Set();
    value.customer_sides.forEach((side, sideIndex) => {
      requiredEnum(side, ["candidate", "company"], `${path}.customer_sides[${sideIndex}]`, issues);
      if (seenSides.has(side)) addIssue(issues, "DUPLICATE_VALUE", `${path}.customer_sides[${sideIndex}]`, "중복 고객 측입니다.");
      seenSides.add(side);
    });
    if (value.customer_side === "platform") {
      addIssue(issues, "PLATFORM_SIDE_MIXED", `${path}.customer_sides`, "플랫폼 관찰은 고객 측 배열과 섞을 수 없습니다.");
    } else if ((value.customer_side === "candidate" || value.customer_side === "company") && !seenSides.has(value.customer_side)) {
      addIssue(issues, "CUSTOMER_SIDE_PROJECTION_MISMATCH", `${path}.customer_sides`, "customer_sides에는 기존 customer_side가 포함되어야 합니다.");
    }
  }
  requiredString(value.title, `${path}.title`, issues, { max: 120 });
  requiredString(value.statement, `${path}.statement`, issues, { max: 1200 });
  requiredEnum(value.collection_state, Object.keys(COLLECTION_STATE_LABELS), `${path}.collection_state`, issues);
  checkUniqueReferences(value.source_refs, `${path}.source_refs`, issues, { min: 1, max: 20 });
  checkUniqueReferences(value.evidence_refs, `${path}.evidence_refs`, issues, { max: 20 });
  if (requiredArray(value.measured_facts, `${path}.measured_facts`, issues, { max: 20 })) {
    value.measured_facts.forEach((fact, factIndex) => validateMeasuredFact(fact, path, factIndex, issues));
  }
  if (value.human_decision !== undefined) validateHumanDecision(value.human_decision, `${path}.human_decision`, issues);
}

function scanSensitiveValues(value, path, issues, seen = new WeakSet()) {
  if (typeof value === "string") {
    for (const [kind, pattern] of SENSITIVE_VALUE_PATTERNS) {
      if (pattern.test(value)) addIssue(issues, "SENSITIVE_VALUE_PATTERN", path, `${kind} 패턴이 남아 있습니다.`);
    }
    return;
  }
  if (!value || typeof value !== "object") return;
  if (seen.has(value)) return;
  seen.add(value);
  for (const [key, nested] of Object.entries(value)) {
    const nestedPath = `${path}.${key}`;
    if (FORBIDDEN_KEY.test(key)) addIssue(issues, "FORBIDDEN_SENSITIVE_FIELD", nestedPath, "비식별 snapshot에서 금지된 필드명입니다.");
    scanSensitiveValues(nested, nestedPath, issues, seen);
  }
}

export function validateSnapshot(snapshot) {
  const issues = [];
  if (!checkKeys(snapshot, TOP_LEVEL_KEYS, "$", issues)) return { ok: false, issues };

  if (snapshot.schema_version !== SNAPSHOT_SCHEMA_VERSION) {
    addIssue(issues, "SCHEMA_VERSION", "$.schema_version", `${SNAPSHOT_SCHEMA_VERSION}만 허용합니다.`);
  }
  requiredString(snapshot.snapshot_id, "$.snapshot_id", issues, { max: 68, pattern: /^snap-[a-z0-9][a-z0-9-]{5,63}$/ });
  requiredString(snapshot.title, "$.title", issues, { max: 120 });

  if (checkKeys(snapshot.tenant, ["tenant_ref", "display_label"], "$.tenant", issues)) {
    requiredString(snapshot.tenant.tenant_ref, "$.tenant.tenant_ref", issues, { max: 56, pattern: TENANT_REF_PATTERN });
    requiredString(snapshot.tenant.display_label, "$.tenant.display_label", issues, { max: 80 });
  }

  if (snapshot.audience === "EXTERNAL_PREVIEW") {
    addIssue(issues, "EXTERNAL_PROJECTION_REQUIRED", "$.audience", "내부 참조를 제거한 별도 승인 외부용 계약이 없어 표시하지 않습니다.");
  } else {
    requiredEnum(snapshot.audience, Object.keys(AUDIENCE_APPROVAL), "$.audience", issues);
  }
  validateApproval(snapshot, issues);
  validateRedaction(snapshot.redaction, issues);
  const artifactRefs = validateProvenance(snapshot.provenance, issues);
  validateScope(snapshot.scope, issues);

  if (requiredArray(snapshot.observations, "$.observations", issues, { max: 500 })) {
    const ids = new Set();
    snapshot.observations.forEach((observation, index) => validateObservation(observation, index, issues, ids));
  }

  validateReferenceIntegrity(snapshot, artifactRefs, issues);
  validateChronology(snapshot, issues);
  validateCustomerSideScope(snapshot, issues);
  validateTenantBinding(snapshot, issues);

  scanSensitiveValues(snapshot, "$", issues);
  return { ok: issues.length === 0, issues, snapshot: issues.length === 0 ? snapshot : undefined };
}
