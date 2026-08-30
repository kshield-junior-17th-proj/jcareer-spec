import { isValidRecruiterEvidenceClaim } from "../src/recruiter-evidence.js";

const valid = {
  claim_id: "claim-0123456789abcdef0123",
  relation_type: "exact_overlap",
  matched_term: "Python",
  candidate_source_type: "SELF_INTRO",
  candidate_source_ref: "self_intro",
  candidate_excerpt: "Python",
  candidate_span_start: 0,
  candidate_span_end: 6,
  employer_source_type: "REQUIRED_SKILL",
  employer_source_ref: "required_skills[0]",
  employer_excerpt: "Python",
  employer_span_start: null,
  employer_span_end: null,
  support_state: "DIRECT_TEXT_EVIDENCE",
  score_effect: "NONE",
  human_review_required: true
};

const cases = [
  [valid, true],
  [{ ...valid, support_state: "MODEL_INFERENCE" }, false],
  [{ ...valid, score_effect: "INFLUENCES_SCORE" }, false],
  [{ ...valid, human_review_required: false }, false],
  [{ ...valid, candidate_source_type: "ARBITRARY_CACHE_FIELD" }, false],
  [{ ...valid, candidate_excerpt: "different text" }, false],
  [{ ...valid, candidate_span_end: 0 }, false],
  [{ ...valid, extra_cache_field: "unexpected" }, false]
];

for (const [claim, expected] of cases) {
  if (isValidRecruiterEvidenceClaim(claim) !== expected) {
    throw new Error("recruiter evidence validator contract mismatch");
  }
}

console.log(`recruiter evidence validator: ${cases.length}/${cases.length}`);
