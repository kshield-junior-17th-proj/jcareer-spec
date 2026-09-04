const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const root = path.resolve(__dirname, "..");
const source = fs.readFileSync(
  path.join(root, "assessment-dashboard", "assessment-snapshot.js"),
  "utf8"
);
const context = { window: {} };
vm.runInNewContext(source, context, { filename: "assessment-snapshot.js" });
const data = JSON.parse(JSON.stringify(context.window.JCAREER_ASSESSMENT));

function sorted(values) {
  return [...values].sort();
}

function countBy(values, key) {
  return values.reduce((counts, item) => {
    const value = item[key];
    counts[value] = (counts[value] || 0) + 1;
    return counts;
  }, {});
}

test("27 project T-IDs map exactly once into six review-pending NF groups", () => {
  assert.equal(data.meta.framework, "NIST AI RMF");
  assert.equal(data.meta.projectControlIds, "PROJECT_T_ID_NOT_NIST_CONTROL_ID");
  assert.equal(data.traceability.namespace, "PROJECT_T_ID_NOT_NIST_CONTROL_ID");
  assert.equal(data.traceability.findingNamespace, "PRESENTATION_GROUP_NOT_PERSISTENT_FINDING_ID");
  assert.equal(data.checklistItems.length, 27);

  const itemIds = data.checklistItems.map((item) => item.id);
  assert.equal(new Set(itemIds).size, 27);
  itemIds.forEach((id) => assert.match(id, /^T\.[1-9]\.[1-9]$/));

  const findingIds = data.findings.map((finding) => finding.id);
  assert.deepEqual(findingIds, ["NF-01", "NF-02", "NF-03", "NF-04", "NF-05", "NF-06"]);
  const groupedIds = data.findings.flatMap((finding) => finding.controls);
  assert.equal(groupedIds.length, 27);
  assert.equal(new Set(groupedIds).size, 27);
  assert.deepEqual(sorted(groupedIds), sorted(itemIds));

  const findingById = new Map(data.findings.map((finding) => [finding.id, finding]));
  data.checklistItems.forEach((item) => {
    assert.ok(findingById.has(item.findingId));
    assert.ok(findingById.get(item.findingId).controls.includes(item.id));
  });
});

test("evidence classes reconcile to 4/13/6/4 globally and per NF group", () => {
  const expected = Object.fromEntries(data.evidence.map((entry) => [entry.code, entry.count]));
  assert.deepEqual(expected, {
    OBSERVED_ADVERSE_BEHAVIOR: 4,
    PARTIALLY_OBSERVED: 13,
    DESIGN_EVIDENCE_ONLY: 6,
    EVIDENCE_GAP: 4
  });
  assert.deepEqual(countBy(data.checklistItems, "evidenceClass"), expected);
  assert.equal(Object.values(expected).reduce((sum, value) => sum + value, 0), 27);

  data.findings.forEach((finding) => {
    const itemCounts = countBy(
      data.checklistItems.filter((item) => item.findingId === finding.id),
      "evidenceClass"
    );
    assert.deepEqual(itemCounts, finding.evidenceGradeCounts);
  });
});

test("remediation and radar never promote an unverified target to actual AFTER", () => {
  assert.deepEqual(data.traceability.chain, [
    "CHECKLIST", "FINDING", "REMEDIATION", "UNVERIFIED_TARGET", "HUMAN_REVALIDATION"
  ]);
  assert.equal(data.traceability.currentStage, "REMEDIATION_OPEN_UNVERIFIED");
  data.findings.forEach((finding) => {
    assert.equal(finding.remediation.state, "OPEN_UNVERIFIED");
    assert.equal(finding.remediation.targetStatus, "UNVERIFIED_TARGET");
    assert.ok(finding.remediation.action.length > 0);
    assert.ok(finding.remediation.verificationGate.length > 0);
  });
  assert.deepEqual(data.radar.targetProjection, [4, 4, 4, 4, 4, 4]);
  assert.equal(data.radar.actualAfter, null);
  assert.equal(data.radar.actualAfterStatus, "NOT_MEASURED_NO_ACCEPTED_REVALIDATION");
  assert.equal(data.meta.actualAfterStatus, data.radar.actualAfterStatus);
  assert.equal(data.deployment.actualAfterStatus, data.radar.actualAfterStatus);
});

test("source and mapped workbook digests bind the frozen external snapshot", () => {
  const binding = data.traceability.sourceBinding;
  assert.equal(binding.status, "EXTERNAL_SNAPSHOT_DIGEST_HUMAN_REVIEW_PENDING");
  assert.match(binding.sourceSha256, /^[0-9a-f]{64}$/);
  assert.match(binding.mappedSha256, /^[0-9a-f]{64}$/);
  assert.notEqual(binding.sourceSha256, binding.mappedSha256);
  assert.doesNotMatch(binding.sourceArtifact, /[\\/]/);
  assert.doesNotMatch(binding.mappedArtifact, /[\\/]/);
});

test("GitHub Pages public specification stays separate from AWS deployment", () => {
  assert.equal(data.deployment.currentSurface, "GITHUB_PAGES_PUBLIC_SPEC_REFERENCE");
  assert.equal(data.deployment.targetSurface, "AWS_ISOLATED_STATIC_S3_CLOUDFRONT_WAF");
  assert.equal(data.deployment.status, "NOT_DEPLOYED");
  assert.equal(data.deployment.githubPagesRelationship, "SEPARATE_PUBLIC_SPEC_REFERENCE_ONLY");
  assert.deepEqual(data.deployment.requiredGates.map((gate) => gate.id), [
    "DG-01", "DG-02", "DG-03", "DG-04", "DG-05", "DG-06"
  ]);

  const serialized = JSON.stringify(data);
  assert.doesNotMatch(serialized, /arn:(aws|aws-us-gov|aws-cn):/i);
  assert.doesNotMatch(serialized, /AKIA[0-9A-Z]{16}/);
  assert.doesNotMatch(serialized, /\b\d{12}\b/);
  assert.doesNotMatch(serialized, /https?:\/\//i);
});
