import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";


const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const [css, app] = await Promise.all([
  readFile(resolve(webRoot, "src/styles.css"), "utf8"),
  readFile(resolve(webRoot, "src/App.jsx"), "utf8")
]);

function token(name) {
  const match = css.match(new RegExp(`${name}:\\s*(#[0-9a-f]{6})`, "i"));
  assert.ok(match, `missing color token ${name}`);
  return match[1];
}

function luminance(hex) {
  const channels = [1, 3, 5].map((offset) => Number.parseInt(hex.slice(offset, offset + 2), 16) / 255);
  const linear = channels.map((value) => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4);
  return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
}

function contrast(first, second) {
  const values = [luminance(first), luminance(second)].sort((a, b) => b - a);
  return (values[0] + 0.05) / (values[1] + 0.05);
}

function balancedBlock(source, marker) {
  const markerIndex = source.indexOf(marker);
  assert.notEqual(markerIndex, -1, `missing CSS marker ${marker}`);
  const opening = source.indexOf("{", markerIndex + marker.length);
  assert.notEqual(opening, -1, `missing CSS block for ${marker}`);
  let depth = 0;
  for (let index = opening; index < source.length; index += 1) {
    if (source[index] === "{") depth += 1;
    if (source[index] === "}") depth -= 1;
    if (depth === 0) return source.slice(opening + 1, index);
  }
  assert.fail(`unclosed CSS block for ${marker}`);
}

function lastDeclaration(source, selector, property) {
  let cursor = 0;
  let value = null;
  while (cursor < source.length) {
    const index = source.indexOf(selector, cursor);
    if (index < 0) break;
    const between = source.slice(index + selector.length, source.indexOf("{", index));
    if (!between.trim()) {
      const block = balancedBlock(source.slice(index), selector);
      const matches = [...block.matchAll(new RegExp(`${property}\\s*:\\s*([^;]+);`, "g"))];
      if (matches.length) value = matches.at(-1)[1].trim();
    }
    cursor = index + selector.length;
  }
  assert.notEqual(value, null, `missing ${property} for ${selector}`);
  return value;
}

for (const name of ["--field-line", "--field-line-hover", "--cobalt"]) {
  assert.ok(contrast(token(name), "#ffffff") >= 3, `${name} must retain at least 3:1 against white`);
}

assert.equal(lastDeclaration(css, "input, textarea, select", "border"), "1px solid var(--field-line)");
assert.equal(lastDeclaration(css, ".button.quiet", "border-color"), "var(--field-line)");
assert.equal(lastDeclaration(css, ".button.quiet:hover", "border-color"), "var(--field-line-hover)");
assert.equal(lastDeclaration(css, ".score-disclosure summary:focus-visible", "outline"), "3px solid var(--cobalt)");
assert.equal(lastDeclaration(css, ".recommendation-top > div", "min-width"), "0");
assert.equal(lastDeclaration(css, ".recommendation-top h2", "overflow-wrap"), "anywhere");
assert.equal(lastDeclaration(css, '.job-card .arrow-link[aria-hidden="true"]', "pointer-events"), "none");

const mobile = balancedBlock(css, "@media (max-width: 680px)");
assert.equal(lastDeclaration(mobile, ".topbar", "position"), "static");
const narrow = balancedBlock(css, "@media (max-width: 420px)");
assert.equal(lastDeclaration(narrow, ".recommendation-top", "flex-direction"), "column");
assert.match(app, /className="pipeline-list" role="list" aria-label="지원자 파이프라인"/);
assert.match(app, /role="listitem" aria-labelledby=\{`candidate-\$\{item\.id\}`\}/);

console.log("J-Career web non-text contrast and narrow-layout source contract: PASS (render not executed)");
