const CANDIDATE_SOURCE_REFS = {
  SELF_INTRO: /^self_intro$/,
  PROJECT_TITLE: /^projects\[\d+\]\.title$/,
  PROJECT_ROLE: /^projects\[\d+\]\.role$/,
  PROJECT_SUMMARY: /^projects\[\d+\]\.summary$/,
  PROJECT_OUTCOME: /^projects\[\d+\]\.outcome$/,
  PROJECT_TECHNOLOGY: /^projects\[\d+\]\.technologies\[\d+\]$/
};

const EMPLOYER_SOURCE_REFS = {
  JOB_SUMMARY: /^job_summary$/,
  REQUIRED_SKILL: /^required_skills\[\d+\]$/,
  DIRECTION_STATEMENT: /^direction_statement$/,
  DECLARED_VALUE: /^declared_values\[\d+\]$/
};

const CLAIM_KEYS = [
  "claim_id",
  "relation_type",
  "matched_term",
  "candidate_source_type",
  "candidate_source_ref",
  "candidate_excerpt",
  "candidate_span_start",
  "candidate_span_end",
  "employer_source_type",
  "employer_source_ref",
  "employer_excerpt",
  "employer_span_start",
  "employer_span_end",
  "support_state",
  "score_effect",
  "human_review_required"
].sort();

function exactObjectKeys(value, expected) {
  return value !== null
    && typeof value === "object"
    && !Array.isArray(value)
    && JSON.stringify(Object.keys(value).sort()) === JSON.stringify(expected);
}

function boundedDisplayText(value, maximum = 160) {
  return typeof value === "string"
    && value.length > 0
    && value.length <= maximum
    && !/[\u0000-\u001f\u007f]/u.test(value);
}

function normalizedText(value) {
  return value.normalize("NFC").toLocaleLowerCase("ko-KR");
}

function validSpanPair(start, end, spanRequired) {
  if (!spanRequired) return start === null && end === null;
  return Number.isInteger(start) && Number.isInteger(end) && start >= 0 && end > start;
}

export function isValidRecruiterEvidenceClaim(claim) {
  if (!exactObjectKeys(claim, CLAIM_KEYS)) return false;
  if (!/^claim-[0-9a-f]{20}$/u.test(claim.claim_id)) return false;
  if (claim.relation_type !== "exact_overlap") return false;
  if (claim.support_state !== "DIRECT_TEXT_EVIDENCE") return false;
  if (claim.score_effect !== "NONE" || claim.human_review_required !== true) return false;
  if (!boundedDisplayText(claim.matched_term, 120)) return false;
  if (!boundedDisplayText(claim.candidate_excerpt, 120)) return false;
  if (!boundedDisplayText(claim.employer_excerpt, 120)) return false;
  if (!boundedDisplayText(claim.candidate_source_ref)) return false;
  if (!boundedDisplayText(claim.employer_source_ref)) return false;

  const candidateRef = CANDIDATE_SOURCE_REFS[claim.candidate_source_type];
  const employerRef = EMPLOYER_SOURCE_REFS[claim.employer_source_type];
  if (!candidateRef?.test(claim.candidate_source_ref)) return false;
  if (!employerRef?.test(claim.employer_source_ref)) return false;

  const matched = normalizedText(claim.matched_term);
  if (normalizedText(claim.candidate_excerpt) !== matched) return false;
  if (normalizedText(claim.employer_excerpt) !== matched) return false;

  const candidateSpanRequired = claim.candidate_source_type !== "PROJECT_TECHNOLOGY";
  const employerSpanRequired = ["JOB_SUMMARY", "DIRECTION_STATEMENT"].includes(
    claim.employer_source_type
  );
  return validSpanPair(
    claim.candidate_span_start,
    claim.candidate_span_end,
    candidateSpanRequired
  ) && validSpanPair(
    claim.employer_span_start,
    claim.employer_span_end,
    employerSpanRequired
  );
}
