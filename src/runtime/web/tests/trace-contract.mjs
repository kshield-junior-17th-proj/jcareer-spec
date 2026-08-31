import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const view = readFileSync(resolve(webRoot, "src/trace-workspace.jsx"), "utf8");
const app = readFileSync(resolve(webRoot, "src/App.jsx"), "utf8");
const css = readFileSync(resolve(webRoot, "src/styles.css"), "utf8");

const required = [
  [view.includes("Decision Receipt") && view.includes("Recourse Twin"), "receipt and twin labels"],
  [view.includes('<table className="trace-twin-table">') && view.includes("<caption>"), "semantic comparison table"],
  [view.includes('scope="col"') && view.includes('scope="row"'), "table header scopes"],
  [view.includes('role="status" aria-live="polite"'), "review status live region"],
  [view.includes('role="note"') && view.includes("자동 채용 결정") && view.includes("자동 이의판정"), "non-decision boundary"],
  [view.includes('headers: { "Idempotency-Key"') && view.includes("base_integrity_sha256"), "idempotent correction binding"],
  [view.includes("UPHOLD") && view.includes("CHANGE") && view.includes("REQUEST_INFO") && view.includes("ESCALATE"), "human disposition options"],
  [view.includes("연락처·주소·자기소개 원문은 입력하지 마세요"), "no-PII correction warning"],
  [app.includes('path: "/candidate/trace"') && app.includes('path: "/recruiter/trace"') && app.includes('path: "/admin/trace"'), "role-scoped routes"],
  [app.includes('<NavLink to={`/${user.role}/trace`}>'), "keyboard-reachable navigation"],
  [css.includes(".trace-table-wrap") && css.includes(":focus-visible") && css.includes("@media (max-width: 600px)"), "focus and responsive styling"]
];

const failures = required.filter(([condition]) => !condition).map(([, label]) => label);
assert.deepEqual(failures, [], `missing TRACE UI contracts: ${failures.join(", ")}`);
console.log(`J-Career TRACE web contract: OK (${required.length}/${required.length})`);
