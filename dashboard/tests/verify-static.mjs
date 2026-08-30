import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const testsDirectory = path.dirname(fileURLToPath(import.meta.url));
const dashboardRoot = path.resolve(testsDirectory, "..");

const [html, appSource, validatorSource, viewModelSource, packagingSource, css, schemaSource] = await Promise.all([
  readFile(path.join(dashboardRoot, "index.html"), "utf8"),
  readFile(path.join(dashboardRoot, "src", "app.js"), "utf8"),
  readFile(path.join(dashboardRoot, "src", "snapshot.js"), "utf8"),
  readFile(path.join(dashboardRoot, "src", "view-model.js"), "utf8"),
  readFile(path.join(dashboardRoot, "tools", "package-snapshot.mjs"), "utf8"),
  readFile(path.join(dashboardRoot, "styles.css"), "utf8"),
  readFile(path.join(dashboardRoot, "snapshot.schema.json"), "utf8")
]);

assert.doesNotThrow(() => JSON.parse(schemaSource), "snapshot.schema.json must be valid JSON");
assert.match(html, /connect-src 'none'/, "CSP must prohibit network connections");
assert.match(html, /script-src 'self'/, "CSP must limit script execution to local files");
assert.match(html, /id="main-content" tabindex="-1"/, "skip-link target must be programmatically focusable");
assert.match(html, /aria-live="polite"/, "ingestion state must be announced");

const networkApi = /\b(?:fetch|XMLHttpRequest|WebSocket|EventSource)\b|sendBeacon\s*\(/;
assert.doesNotMatch(appSource, networkApi, "dashboard application must not have a network client");
assert.doesNotMatch(validatorSource, networkApi, "snapshot validator must not have a network client");
assert.doesNotMatch(viewModelSource, networkApi, "snapshot view model must not have a network client");
assert.doesNotMatch(packagingSource, networkApi, "snapshot packager must not have a network client");
assert.doesNotMatch(packagingSource, /node:child_process|\bexec(?:File)?\s*\(|\bspawn\s*\(/, "snapshot packager must not invoke external processes");
assert.match(packagingSource, /validateSnapshot\(snapshot\)/, "snapshot contract must be checked before artifact packaging");
assert.match(packagingSource, /createHash\("sha256"\)/, "declared source artifacts must be digest-bound");
assert.match(packagingSource, /flag: "wx"/, "snapshot packaging must not overwrite an existing output");
assert.match(packagingSource, /isWithin\(basePath, actualPath\)/, "resolved source artifacts must stay inside the reviewed directory");
assert.doesNotMatch(appSource, /\b(?:localStorage|sessionStorage|indexedDB)\b/, "snapshot data must not persist in browser storage");
assert.doesNotMatch(appSource, /\bfile\.name\b/, "local filenames must not be echoed into the evidence surface");
assert.doesNotMatch(appSource, /\b(?:isCompliant|complianceScore|residualRiskScore|passCount|failCount)\b/, "dashboard must not calculate assessment outcomes");
assert.match(appSource, /window\.addEventListener\("pagehide"[\s\S]*renderEmpty\(\)/, "pagehide must clear the rendered snapshot");
assert.match(appSource, /generation !== loadGeneration/, "stale asynchronous file reads must not replace the newest snapshot");
assert.match(appSource, /root\.setAttribute\("aria-busy", "true"\)/, "snapshot file reads must expose a busy state");
assert.match(appSource, /snapshot 파일을 읽고 검증하는 중…/, "snapshot file reads must announce pending state");
assert.doesNotMatch(appSource, /현재 저장소에는/, "empty state must not claim repository-wide knowledge");
assert.match(appSource, /현재 탭에 불러온 승인된/, "empty state must be scoped to the browser tab");
assert.match(validatorSource, /EXTERNAL_PROJECTION_REQUIRED/, "external preview must fail closed until a separate projection is approved");
assert.match(validatorSource, /TENANT_SCOPE_MISMATCH/, "artifact and observation records must bind to the snapshot tenant");
assert.match(validatorSource, /LOGICAL_REFERENCE_REQUIRED/, "snapshot references must remain relative logical references");
assert.match(appSource, /buildObservationLanes\(snapshot\)/, "loaded rendering must use the tested customer-lane view model");
assert.match(viewModelSource, /\["candidate", "company", "platform"\]/, "view model must retain all three observation lanes");
assert.match(viewModelSource, /observationCustomerSides\(item\)\.includes\(side\)/, "shared observations must route only from declared side metadata");
assert.match(appSource, /고유 관찰.*판정 집계 없음/, "global observation count must remain unique and non-judgmental");
assert.match(css, /\.file-trigger:focus-within/, "the visible file trigger must expose keyboard focus");
assert.match(css, /min-height:\s*100vh;[\s\S]*min-height:\s*100dvh;/, "viewport height must retain a legacy fallback");
assert.match(appSource, /capturedAt\.dateTime = artifact\.captured_at/, "artifact time must retain its machine-readable value");
assert.match(appSource, /snapshot\.redaction\.reviewed_by_ref/, "redaction reviewer provenance must be rendered");
assert.match(appSource, /snapshot\.approval\.source_ref/, "approval source provenance must be rendered");
assert.match(appSource, /timestamp: snapshot\.approval\.approved_at/, "approval time must be rendered");
assert.match(appSource, /time\.dateTime = timestamp/, "provenance times must retain machine-readable values");
assert.match(appSource, /snapshot\.provenance\.source_commit/, "optional source commit must be rendered when present");
assert.match(appSource, /snapshotHeading\.id = "loaded-snapshot-title"/, "loaded snapshot must expose a dynamic accessible title");
assert.match(appSource, /snapshotHeading\.focus\(\)/, "loaded snapshot title must receive visible focus");
assert.doesNotMatch(appSource, /focus\(\{ preventScroll: true \}\)/, "dashboard must not move focus outside the viewport without scrolling");
assert.match(css, /\.artifact-digest summary \{[\s\S]*?min-height:\s*44px;/, "digest disclosure must retain a touch target");
assert.match(css, /@media \(max-width: 420px\) \{[\s\S]*?\.spine-list \{[\s\S]*?grid-template-columns:\s*1fr;/, "provenance spine must collapse on narrow screens");
const mobileBoundary = css.match(/@media \(max-width: 760px\) \{[\s\S]*?\.boundary-strip \{([\s\S]*?)\}/)?.[1] || "";
assert.match(mobileBoundary, /flex-wrap:\s*wrap;/, "mobile boundary facts must wrap without a horizontal-only gesture");
assert.doesNotMatch(mobileBoundary, /white-space:\s*nowrap|overflow-x:\s*auto/, "mobile boundary facts must not require horizontal scrolling");
assert.doesNotMatch(html, /<script(?![^>]+src=)[^>]*>/, "inline scripts are not allowed");
assert.doesNotMatch(html, /<(?:script|link)[^>]+(?:src|href)="https?:/i, "remote runtime assets are not allowed");

const openBraces = (css.match(/\{/g) || []).length;
const closeBraces = (css.match(/\}/g) || []).length;
assert.equal(openBraces, closeBraces, "CSS braces must be balanced");

const declaredProperties = new Set([...css.matchAll(/(--[a-z0-9-]+)\s*:/gi)].map((match) => match[1]));
const usedProperties = new Set([...css.matchAll(/var\((--[a-z0-9-]+)/gi)].map((match) => match[1]));
for (const property of usedProperties) {
  assert.ok(declaredProperties.has(property), `CSS custom property ${property} must be declared`);
}

const schema = JSON.parse(schemaSource);
assert.ok(schema.$defs.sourceArtifact.required.includes("tenant_ref"), "artifact schema must include tenant binding");
assert.ok(schema.$defs.observation.required.includes("tenant_ref"), "observation schema must include tenant binding");
assert.deepEqual(schema.$defs.observation.properties.customer_sides.items.enum, ["candidate", "company"], "multi-side routing must remain a closed customer enum");
assert.ok(schema.$defs.logicalArtifactRef.pattern && schema.$defs.logicalReference.pattern, "schema must restrict snapshot references");

function luminance(hex) {
  const channels = [1, 3, 5].map((offset) => Number.parseInt(hex.slice(offset, offset + 2), 16) / 255);
  const linear = channels.map((value) => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4);
  return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
}

const controlLine = css.match(/--control-line:\s*(#[0-9a-f]{6})/i)?.[1];
assert.ok(controlLine, "dashboard must declare a clear-button boundary color");
const controlContrast = (luminance("#ffffff") + 0.05) / (luminance(controlLine) + 0.05);
assert.ok(controlContrast >= 3, "clear-button boundary must retain at least 3:1 against white");
assert.match(css, /\.clear-button \{[\s\S]*?border:\s*1px solid var\(--control-line\);/);

console.log("J-Career dashboard static boundary: PASS");
console.log("Observed contract: connect-src none, no network API, no browser persistence, no assessment calculation symbols.");
