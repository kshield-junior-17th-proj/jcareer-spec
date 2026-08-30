import assert from "node:assert/strict";

import { ApiError, api, decodeResponsePayload } from "../src/api.js";

let checks = 0;

const valid = await decodeResponsePayload(new Response('{"status":"ok"}', {
  status: 200,
  headers: { "content-type": "application/json; charset=utf-8" }
}));
assert.deepEqual(valid, { status: "ok" });
checks += 1;

const plain = await decodeResponsePayload(new Response("maintenance", {
  status: 503,
  headers: { "content-type": "text/plain" }
}));
assert.equal(plain, "maintenance");
checks += 1;

const noContent = await decodeResponsePayload(new Response(null, { status: 204 }));
assert.equal(noContent, null);
checks += 1;

await assert.rejects(
  decodeResponsePayload(new Response(null, {
    status: 200,
    headers: { "content-type": "application/json" }
  })),
  (error) => {
    assert(error instanceof ApiError);
    assert.equal(error.status, 200);
    assert.equal(error.payload.error_code, "EMPTY_RESPONSE_BODY");
    return true;
  }
);
checks += 1;

await assert.rejects(
  decodeResponsePayload(new Response('{"detail":', {
    status: 200,
    headers: { "content-type": "application/json" }
  })),
  (error) => {
    assert(error instanceof ApiError);
    assert.equal(error.payload.error_code, "INVALID_JSON_RESPONSE");
    assert(!JSON.stringify(error.payload).includes('{"detail":'));
    return true;
  }
);
checks += 1;

await assert.rejects(
  decodeResponsePayload({
    status: 502,
    ok: false,
    headers: new Headers({ "content-type": "application/json" }),
    async text() { throw new Error("synthetic body read failure"); }
  }),
  (error) => {
    assert(error instanceof ApiError);
    assert.equal(error.status, 502);
    assert.equal(error.payload.error_code, "RESPONSE_BODY_READ_FAILED");
    assert(!JSON.stringify(error.payload).includes("synthetic body read failure"));
    return true;
  }
);
checks += 1;

let unauthorizedEvents = 0;
let authorizationHeader = null;
let storedToken = "synthetic-token";
globalThis.localStorage = {
  getItem(key) { return key === "jcareer_token" ? storedToken : null; }
};
globalThis.window = Object.assign(new EventTarget(), {
  setTimeout: globalThis.setTimeout,
  clearTimeout: globalThis.clearTimeout
});
window.addEventListener("jcareer:unauthorized", () => { unauthorizedEvents += 1; });
globalThis.fetch = async (_url, options) => {
  authorizationHeader = options.headers.get("Authorization");
  return new Response("{", {
    status: 401,
    headers: { "content-type": "application/json" }
  });
};

await assert.rejects(
  api("/api/v1/auth/me"),
  (error) => error instanceof ApiError
    && error.status === 401
    && error.payload.error_code === "INVALID_JSON_RESPONSE"
);
assert.equal(unauthorizedEvents, 1);
assert.equal(authorizationHeader, "Bearer synthetic-token");
checks += 1;

globalThis.fetch = async () => {
  storedToken = "replacement-token";
  return new Response('{"detail":"old token"}', {
    status: 401,
    headers: { "content-type": "application/json" }
  });
};
await assert.rejects(
  api("/api/v1/auth/me"),
  (error) => error instanceof ApiError && error.status === 401
);
assert.equal(unauthorizedEvents, 1, "a stale 401 must not clear a replacement session");
checks += 1;

globalThis.fetch = async (_url, options) => new Promise((_resolve, reject) => {
  options.signal.addEventListener(
    "abort",
    () => reject(new DOMException("synthetic abort", "AbortError")),
    { once: true }
  );
});
await assert.rejects(
  api("/api/v1/slow", { timeoutMs: 5 }),
  (error) => error instanceof ApiError
    && error.status === 0
    && error.payload.error_code === "REQUEST_TIMEOUT"
);
checks += 1;

const callerController = new AbortController();
const cancelledRequest = api("/api/v1/cancelled", {
  signal: callerController.signal,
  timeoutMs: 1_000
});
callerController.abort();
await assert.rejects(
  cancelledRequest,
  (error) => error instanceof ApiError
    && error.status === 0
    && error.payload.error_code === "REQUEST_ABORTED"
);
checks += 1;

globalThis.fetch = async () => {
  throw new Error("synthetic transport detail must not escape");
};
await assert.rejects(
  api("/api/v1/unreachable"),
  (error) => error instanceof ApiError
    && error.status === 0
    && error.payload.error_code === "NETWORK_UNAVAILABLE"
    && !JSON.stringify(error.payload).includes("synthetic transport detail")
);
checks += 1;

console.log(`J-Career web API client contract: OK (${checks}/${checks})`);
