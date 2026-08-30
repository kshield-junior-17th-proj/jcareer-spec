import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

import { resolveLogicalArtifactPath, verifyAndPackageSnapshot } from "../tools/package-snapshot.mjs";

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function snapshotFor(runtimeDigest, approvalDigest) {
  return {
    schema_version: "jcareer-consulting-snapshot/v1",
    snapshot_id: "snap-package-fixture-01",
    title: "합성 내부 검토 snapshot",
    tenant: { tenant_ref: "tenant-synthetic-j", display_label: "가상 J사" },
    audience: "INTERNAL_REVIEW",
    approval: {
      state: "APPROVED_FOR_INTERNAL_REVIEW",
      approved_by_ref: "reviewer-synthetic-01",
      approved_at: "2026-08-29T00:20:00Z",
      source_ref: "approval/release.json#internal-review"
    },
    redaction: {
      state: "REDACTED",
      contains_direct_identifiers: false,
      method_version: "synthetic-redaction-v1",
      reviewed_by_ref: "reviewer-synthetic-02"
    },
    provenance: {
      generated_at: "2026-08-29T00:10:00Z",
      generator_version: "package-test-v1",
      source_artifacts: [
        { tenant_ref: "tenant-synthetic-j", artifact_ref: "evidence/runtime.json", kind: "runtime", sha256: runtimeDigest, captured_at: "2026-08-29T00:00:00Z" },
        { tenant_ref: "tenant-synthetic-j", artifact_ref: "approval/release.json", kind: "assessment", sha256: approvalDigest, captured_at: "2026-08-29T00:05:00Z" }
      ]
    },
    scope: { environment: "AS_IS_SYNTHETIC", deployment_state: "LAB_RUNTIME_OBSERVED", customer_sides: ["candidate", "company"] },
    observations: [
      {
        tenant_ref: "tenant-synthetic-j",
        observation_id: "obs-package-fixture-01",
        domain: "provider-boundary",
        customer_side: "platform",
        title: "합성 공급자 경계 관찰",
        statement: "입력 snapshot이 제공한 관찰문을 변경하지 않고 표시한다.",
        collection_state: "RECORDED",
        source_refs: ["evidence/runtime.json#provider"],
        evidence_refs: ["evidence/runtime.json#result"],
        measured_facts: [{ label: "관찰 건수", value: 1, unit: "건" }],
        human_decision: {
          owner: "HUMAN",
          display_text: "합성 내부 검토용으로 표시한다.",
          decided_by_ref: "reviewer-synthetic-01",
          decided_at: "2026-08-29T00:06:00Z",
          source_ref: "approval/release.json#human-decision"
        }
      }
    ]
  };
}

async function createArtifactDirectory() {
  const root = await mkdtemp(path.join(tmpdir(), "jcareer-snapshot-package-"));
  await mkdir(path.join(root, "evidence"));
  await mkdir(path.join(root, "approval"));
  const runtime = Buffer.from('{"synthetic":true,"result":"observed"}\n');
  const approval = Buffer.from('{"synthetic":true,"audience":"internal"}\n');
  await writeFile(path.join(root, "evidence", "runtime.json"), runtime);
  await writeFile(path.join(root, "approval", "release.json"), approval);
  return { root, runtime, approval };
}

test("packages an already approved snapshot only after exact artifact digest verification", async (context) => {
  const fixture = await createArtifactDirectory();
  context.after(() => rm(fixture.root, { recursive: true, force: true }));
  const snapshot = snapshotFor(sha256(fixture.runtime), sha256(fixture.approval));
  const result = await verifyAndPackageSnapshot(snapshot, fixture.root);
  assert.equal(result.ok, true);
  assert.equal(result.verified_artifact_count, 2);
  assert.deepEqual(result.snapshot, snapshot);
  assert.notEqual(result.snapshot, snapshot);
});

test("fails closed when a declared artifact digest drifts", async (context) => {
  const fixture = await createArtifactDirectory();
  context.after(() => rm(fixture.root, { recursive: true, force: true }));
  const snapshot = snapshotFor("0".repeat(64), sha256(fixture.approval));
  const result = await verifyAndPackageSnapshot(snapshot, fixture.root);
  assert.equal(result.ok, false);
  assert.equal(result.stage, "artifact_binding");
  assert.ok(result.issues.some((item) => item.code === "ARTIFACT_DIGEST_MISMATCH"));
});

test("fails closed when a declared artifact is absent", async (context) => {
  const fixture = await createArtifactDirectory();
  context.after(() => rm(fixture.root, { recursive: true, force: true }));
  const snapshot = snapshotFor(sha256(fixture.runtime), sha256(fixture.approval));
  snapshot.provenance.source_artifacts[0].artifact_ref = "evidence/missing.json";
  snapshot.observations[0].source_refs = ["evidence/missing.json#provider"];
  snapshot.observations[0].evidence_refs = ["evidence/missing.json#result"];
  const result = await verifyAndPackageSnapshot(snapshot, fixture.root);
  assert.equal(result.ok, false);
  assert.ok(result.issues.some((item) => item.code === "ARTIFACT_UNAVAILABLE"));
});

test("logical artifact resolution rejects traversal and backslash paths", () => {
  assert.throws(() => resolveLogicalArtifactPath("C:/synthetic", "../outside.json"));
  assert.throws(() => resolveLogicalArtifactPath("C:/synthetic", "nested\\outside.json"));
});
