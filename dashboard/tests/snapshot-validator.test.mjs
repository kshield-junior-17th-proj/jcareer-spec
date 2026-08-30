import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { validateSnapshot } from "../src/snapshot.js";

const snapshotSchema = JSON.parse(
  readFileSync(new URL("../snapshot.schema.json", import.meta.url), "utf8")
);

function validSnapshot() {
  return {
    schema_version: "jcareer-consulting-snapshot/v1",
    snapshot_id: "snap-contract-fixture-01",
    title: "합성 계약 검증 fixture",
    tenant: {
      tenant_ref: "tenant-synthetic-j",
      display_label: "합성 J사"
    },
    audience: "INTERNAL_REVIEW",
    approval: {
      state: "APPROVED_FOR_INTERNAL_REVIEW",
      approved_by_ref: "reviewer-contract-fixture",
      approved_at: "2026-08-28T01:00:00Z",
      source_ref: "tests/fixture-approval.json#release"
    },
    redaction: {
      state: "REDACTED",
      contains_direct_identifiers: false,
      method_version: "fixture-redaction-v1",
      reviewed_by_ref: "reviewer-redaction-fixture"
    },
    provenance: {
      generated_at: "2026-08-28T00:50:00Z",
      generator_version: "fixture-generator-v1",
      source_commit: "abcdef1234567",
      source_artifacts: [
        {
          tenant_ref: "tenant-synthetic-j",
          artifact_ref: "measurement/out/fixture.json",
          kind: "measurement",
          sha256: "a".repeat(64),
          captured_at: "2026-08-28T00:45:00Z"
        },
        {
          tenant_ref: "tenant-synthetic-j",
          artifact_ref: "tests/fixture-approval.json",
          kind: "document",
          sha256: "b".repeat(64),
          captured_at: "2026-08-28T00:40:00Z"
        }
      ]
    },
    scope: {
      environment: "AS_IS_SYNTHETIC",
      deployment_state: "MODEL_ONLY",
      customer_sides: ["candidate", "company"]
    },
    observations: [
      {
        tenant_ref: "tenant-synthetic-j",
        observation_id: "obs-data-boundary-fixture",
        domain: "data-boundary",
        customer_side: "platform",
        title: "논리 데이터 경계 fixture",
        statement: "이 문장은 validator 계약만 시험하며 실제 측정 결과가 아니다.",
        collection_state: "UNVERIFIED",
        source_refs: ["measurement/out/fixture.json#source-fixture"],
        evidence_refs: [],
        measured_facts: [
          { label: "fixture count", value: 2, unit: "logical databases" }
        ],
        human_decision: {
          owner: "HUMAN",
          display_text: "테스트에서만 사용하는 사람 입력 형식 fixture",
          decided_by_ref: "reviewer-decision-fixture",
          decided_at: "2026-08-28T00:40:00Z",
          source_ref: "tests/fixture-approval.json#human-decision"
        }
      },
      {
        tenant_ref: "tenant-synthetic-j",
        observation_id: "obs-company-lifecycle-fixture",
        domain: "customer-journey",
        customer_side: "company",
        title: "기업 계정 수명주기 계약 fixture",
        statement: "기업 고객의 조직과 계정 경계를 표현할 수 있는지만 시험한다.",
        collection_state: "NOT_IMPLEMENTED",
        source_refs: ["measurement/out/fixture.json#company-lifecycle"],
        evidence_refs: [],
        measured_facts: [
          { label: "organization membership modeled", value: false },
          { label: "ownership transfer modeled", value: false }
        ]
      },
      {
        tenant_ref: "tenant-synthetic-j",
        observation_id: "obs-company-status-gate-fixture",
        domain: "access-and-audit",
        customer_side: "company",
        customer_sides: ["candidate", "company"],
        title: "기업 상태 게이트 관찰 fixture",
        statement: "지원자와 기업 경로에 대한 상태 게이트 관찰 구조만 시험한다.",
        collection_state: "UNVERIFIED",
        source_refs: ["measurement/out/fixture.json#company-status-gate"],
        evidence_refs: [],
        measured_facts: [
          { label: "observation scope", value: "candidate-and-company-paths" }
        ]
      },
      {
        tenant_ref: "tenant-synthetic-j",
        observation_id: "obs-cross-store-recovery-fixture",
        domain: "data-boundary",
        customer_side: "platform",
        title: "교차 저장소 복구 계약 fixture",
        statement: "논리 참조와 사후 조정 상태를 판정 없이 표현할 수 있는지만 시험한다.",
        collection_state: "NOT_IMPLEMENTED",
        source_refs: ["measurement/out/fixture.json#cross-store"],
        evidence_refs: [],
        measured_facts: [
          { label: "atomic commit declared", value: false },
          { label: "reconciliation modeled", value: false }
        ]
      },
      {
        tenant_ref: "tenant-synthetic-j",
        observation_id: "obs-provider-boundary-fixture",
        domain: "provider-boundary",
        customer_side: "platform",
        title: "설명 공급자 경계 fixture",
        statement: "캐시 원본과 외부 공급자 수신을 구분하는 표시 구조만 시험한다.",
        collection_state: "UNVERIFIED",
        source_refs: ["measurement/out/fixture.json#provider-boundary"],
        evidence_refs: [],
        measured_facts: [
          { label: "external receipt", value: "not-asserted" }
        ]
      }
    ]
  };
}

function issueCodes(result) {
  return new Set(result.issues.map((issue) => issue.code));
}

test("accepts a structurally complete, single-tenant redacted contract fixture", () => {
  const snapshot = validSnapshot();
  const result = validateSnapshot(snapshot);
  assert.equal(result.ok, true, JSON.stringify(result.issues));
  assert.equal(result.snapshot, snapshot);
});

test("keeps schema and validator tenant binding fields in parity", () => {
  assert.ok(snapshotSchema.$defs.sourceArtifact.required.includes("tenant_ref"));
  assert.ok(snapshotSchema.$defs.observation.required.includes("tenant_ref"));
  assert.equal(snapshotSchema.$defs.sourceArtifact.properties.tenant_ref.$ref, "#/$defs/tenantRef");
  assert.equal(snapshotSchema.$defs.observation.properties.tenant_ref.$ref, "#/$defs/tenantRef");
  assert.ok(snapshotSchema.$defs.logicalArtifactRef.pattern);
  assert.ok(snapshotSchema.$defs.logicalReference.pattern);
});

test("rejects artifact and observation records bound to another tenant", () => {
  const snapshot = validSnapshot();
  snapshot.provenance.source_artifacts[0].tenant_ref = "tenant-synthetic-other";
  snapshot.observations[0].tenant_ref = "tenant-synthetic-other";
  const result = validateSnapshot(snapshot);
  assert.equal(result.ok, false);
  assert.equal(
    result.issues.filter((issue) => issue.code === "TENANT_SCOPE_MISMATCH").length,
    2
  );
});

test("rejects URL, absolute and parent-traversal references", () => {
  const snapshot = validSnapshot();
  snapshot.provenance.source_artifacts[0].artifact_ref = "https://invalid.example/source.json";
  snapshot.approval.source_ref = "../approval.json#release";
  snapshot.observations[0].source_refs = ["C:/workspace/source.json#item"];
  const result = validateSnapshot(snapshot);
  assert.equal(result.ok, false);
  assert.ok(result.issues.filter((issue) => issue.code === "LOGICAL_REFERENCE_REQUIRED").length >= 3);
});

test("rejects UUID, cloud ARN, service endpoint, data URL and absolute path shapes", () => {
  const snapshot = validSnapshot();
  const syntheticUuid = ["123e4567", "e89b", "42d3", "a456", "426614174000"].join("-");
  const syntheticArn = ["arn", "aws", "bedrock", "ap-northeast-2", "", "foundation-model/example"].join(":");
  const syntheticDatabaseUrl = ["postgresql", "//fixture:placeholder@db.invalid/example"].join(":");
  const syntheticEndpoint = ["service", "ap-northeast-2", "amazonaws", "com"].join(".");
  const syntheticPath = ["C:", "Users", "fixture", "source.json"].join("/");
  snapshot.observations[0].statement = [
    syntheticUuid,
    syntheticArn,
    syntheticDatabaseUrl,
    syntheticEndpoint,
    syntheticPath
  ].join(" ");
  const result = validateSnapshot(snapshot);
  assert.equal(result.ok, false);
  assert.ok(result.issues.filter((issue) => issue.code === "SENSITIVE_VALUE_PATTERN").length >= 5);
});

test("fails closed for external preview until a minimal external contract is approved", () => {
  const snapshot = validSnapshot();
  snapshot.audience = "EXTERNAL_PREVIEW";
  snapshot.approval.state = "APPROVED_FOR_EXTERNAL_PREVIEW";
  const result = validateSnapshot(snapshot);
  assert.equal(result.ok, false);
  assert.ok(issueCodes(result).has("EXTERNAL_PROJECTION_REQUIRED"));
});

test("rejects an unredacted or direct-identifier snapshot", () => {
  const snapshot = validSnapshot();
  snapshot.redaction.state = "RAW";
  snapshot.redaction.contains_direct_identifiers = true;
  const result = validateSnapshot(snapshot);
  const codes = issueCodes(result);
  assert.ok(codes.has("REDACTION_REQUIRED"));
  assert.ok(codes.has("DIRECT_IDENTIFIER_FLAG"));
});

test("rejects sensitive field names even when the schema also sees them as unknown", () => {
  const snapshot = validSnapshot();
  snapshot.observations[0].email = "redacted-value";
  const result = validateSnapshot(snapshot);
  const codes = issueCodes(result);
  assert.ok(codes.has("UNKNOWN_FIELD"));
  assert.ok(codes.has("FORBIDDEN_SENSITIVE_FIELD"));
});

test("rejects direct identifier and cloud credential patterns nested in statements", () => {
  const snapshot = validSnapshot();
  const syntheticEmail = ["person", "example.com"].join("@");
  const syntheticAccessKey = ["AKIA", "ABCDEFGHIJKLMNOP"].join("");
  snapshot.observations[0].statement = `contact ${syntheticEmail} using ${syntheticAccessKey}`;
  const result = validateSnapshot(snapshot);
  assert.equal(result.ok, false);
  assert.ok(result.issues.filter((issue) => issue.code === "SENSITIVE_VALUE_PATTERN").length >= 2);
});

test("rejects a 12-digit AWS account-shaped value", () => {
  const snapshot = validSnapshot();
  const syntheticAccountShape = ["1234", "5678", "9012"].join("");
  snapshot.observations[0].statement = `source account ${syntheticAccountShape}`;
  const result = validateSnapshot(snapshot);
  assert.ok(issueCodes(result).has("SENSITIVE_VALUE_PATTERN"));
});

test("rejects invisible and bidirectional display controls in evidence text", () => {
  for (const unsafeCharacter of ["\u200b", "\u202e", "\u2066", "\u0007"]) {
    const snapshot = validSnapshot();
    snapshot.observations[0].statement = `trusted${unsafeCharacter}display`;
    const result = validateSnapshot(snapshot);
    assert.equal(result.ok, false);
    assert.ok(issueCodes(result).has("SENSITIVE_VALUE_PATTERN"));
  }
});

test("rejects non-human decisions and missing decision provenance", () => {
  const snapshot = validSnapshot();
  snapshot.observations[0].human_decision.owner = "AGENT";
  delete snapshot.observations[0].human_decision.source_ref;
  const result = validateSnapshot(snapshot);
  const codes = issueCodes(result);
  assert.ok(codes.has("HUMAN_OWNER_REQUIRED"));
  assert.ok(codes.has("STRING_REQUIRED"));
});

test("rejects duplicate observation identifiers and unknown top-level fields", () => {
  const snapshot = validSnapshot();
  snapshot.observations.push(structuredClone(snapshot.observations[0]));
  snapshot.result_summary = { passed: 1 };
  const result = validateSnapshot(snapshot);
  const codes = issueCodes(result);
  assert.ok(codes.has("DUPLICATE_OBSERVATION"));
  assert.ok(codes.has("UNKNOWN_FIELD"));
});

test("rejects a date without an ISO 8601 time and offset", () => {
  const snapshot = validSnapshot();
  snapshot.approval.approved_at = "2026-08-28";
  const result = validateSnapshot(snapshot);
  assert.ok(issueCodes(result).has("DATE_TIME_REQUIRED"));
});

test("rejects a calendar date that does not exist", () => {
  const snapshot = validSnapshot();
  snapshot.provenance.generated_at = "2026-02-30T00:50:00Z";
  const result = validateSnapshot(snapshot);
  assert.ok(issueCodes(result).has("DATE_TIME_REQUIRED"));
});

test("rejects source and decision references absent from the artifact inventory", () => {
  const snapshot = validSnapshot();
  snapshot.observations[0].source_refs = ["evidence/not-in-inventory.json#item"];
  snapshot.observations[0].human_decision.source_ref = "evidence/not-in-inventory.json#decision";
  const result = validateSnapshot(snapshot);
  assert.ok(result.issues.filter((issue) => issue.code === "UNRESOLVED_ARTIFACT_REFERENCE").length >= 2);
});

test("rejects capture, generation, human decision and approval time reversal", () => {
  const snapshot = validSnapshot();
  snapshot.provenance.source_artifacts[0].captured_at = "2026-08-28T00:55:00Z";
  snapshot.observations[0].human_decision.decided_at = "2026-08-28T00:56:00Z";
  snapshot.approval.approved_at = "2026-08-28T00:30:00Z";
  const result = validateSnapshot(snapshot);
  const codes = issueCodes(result);
  assert.ok(codes.has("ARTIFACT_AFTER_GENERATION"));
  assert.ok(codes.has("DECISION_AFTER_GENERATION"));
  assert.ok(codes.has("APPROVAL_BEFORE_GENERATION"));
});

test("rejects a candidate or company observation outside the declared customer scope", () => {
  const snapshot = validSnapshot();
  snapshot.scope.customer_sides = ["candidate"];
  snapshot.observations[2].customer_sides = ["candidate", "company"];
  const result = validateSnapshot(snapshot);
  assert.ok(issueCodes(result).has("CUSTOMER_SIDE_OUT_OF_SCOPE"));
});

test("accepts one observation routed to both customer lanes without duplicating its identity", () => {
  const snapshot = validSnapshot();
  const shared = snapshot.observations.find((item) => item.observation_id === "obs-company-status-gate-fixture");
  assert.deepEqual(shared.customer_sides, ["candidate", "company"]);
  const result = validateSnapshot(snapshot);
  assert.equal(result.ok, true, JSON.stringify(result.issues));
  assert.equal(new Set(snapshot.observations.map((item) => item.observation_id)).size, snapshot.observations.length);
});

test("rejects ambiguous, duplicate and platform-mixed customer side projections", () => {
  const missingPrimary = validSnapshot();
  missingPrimary.observations[1].customer_sides = ["candidate"];
  assert.ok(issueCodes(validateSnapshot(missingPrimary)).has("CUSTOMER_SIDE_PROJECTION_MISMATCH"));

  const duplicateSide = validSnapshot();
  duplicateSide.observations[1].customer_sides = ["company", "company"];
  assert.ok(issueCodes(validateSnapshot(duplicateSide)).has("DUPLICATE_VALUE"));

  const platformMixed = validSnapshot();
  platformMixed.observations[0].customer_sides = ["candidate"];
  assert.ok(issueCodes(validateSnapshot(platformMixed)).has("PLATFORM_SIDE_MIXED"));
});
