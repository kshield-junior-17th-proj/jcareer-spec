const API_BASE = import.meta.env?.VITE_API_BASE || "";
const DEFAULT_REQUEST_TIMEOUT_MS = 30_000;

export class ApiError extends Error {
  constructor(status, message, payload) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

function responseFailureMetadata(response, errorCode) {
  return {
    error_code: errorCode,
    content_type: response.headers.get("content-type") || null
  };
}

function readStoredToken() {
  try {
    return localStorage.getItem("jcareer_token");
  } catch {
    return null;
  }
}

export async function decodeResponsePayload(response) {
  let text;
  try {
    text = await response.text();
  } catch {
    throw new ApiError(
      response.status,
      "서버 응답을 읽을 수 없습니다. 잠시 후 다시 시도해 주세요.",
      responseFailureMetadata(response, "RESPONSE_BODY_READ_FAILED")
    );
  }

  if (text.length === 0) {
    if (!response.ok || response.status === 204 || response.status === 205) return null;
    throw new ApiError(
      response.status,
      "서버가 필요한 응답 내용을 보내지 않았습니다. 다시 시도해 주세요.",
      responseFailureMetadata(response, "EMPTY_RESPONSE_BODY")
    );
  }

  const isJson = response.headers.get("content-type")?.includes("application/json");
  if (!isJson) return text;
  try {
    return JSON.parse(text);
  } catch {
    throw new ApiError(
      response.status,
      response.ok
        ? "서버 응답 형식을 확인할 수 없습니다. 다시 시도해 주세요."
        : "요청 오류 응답의 형식을 확인할 수 없습니다. 다시 시도해 주세요.",
      responseFailureMetadata(response, "INVALID_JSON_RESPONSE")
    );
  }
}

export async function api(path, options = {}) {
  const token = readStoredToken();
  const {
    timeoutMs: requestedTimeoutMs,
    signal: callerSignal,
    ...requestOptions
  } = options;
  const timeoutMs = Number.isFinite(requestedTimeoutMs) && requestedTimeoutMs > 0
    ? requestedTimeoutMs
    : DEFAULT_REQUEST_TIMEOUT_MS;
  const headers = new Headers(requestOptions.headers || {});
  if (requestOptions.body && !(requestOptions.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const controller = new AbortController();
  let timedOut = false;
  const relayCallerAbort = () => controller.abort();
  if (callerSignal?.aborted) {
    relayCallerAbort();
  } else {
    callerSignal?.addEventListener("abort", relayCallerAbort, { once: true });
  }
  const timeout = window.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);

  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...requestOptions,
      headers,
      signal: controller.signal
    });

    if (
      !response.ok
      && response.status === 401
      && token
      && readStoredToken() === token
    ) {
      window.dispatchEvent(new Event("jcareer:unauthorized"));
    }
    const payload = await decodeResponsePayload(response);
    if (!response.ok) {
      const detail = typeof payload === "object" ? payload?.detail : null;
      const message = Array.isArray(detail)
        ? detail.map((item) => item?.msg || "입력값을 확인해 주세요.").join(" ")
        : typeof detail === "string"
          ? detail
          : "요청을 처리하지 못했습니다.";
      throw new ApiError(response.status, message, payload);
    }
    return payload;
  } catch (error) {
    if (timedOut) {
      throw new ApiError(
        0,
        "요청 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.",
        { error_code: "REQUEST_TIMEOUT" }
      );
    }
    if (callerSignal?.aborted) {
      throw new ApiError(0, "요청이 취소되었습니다.", { error_code: "REQUEST_ABORTED" });
    }
    if (error instanceof ApiError) throw error;
    throw new ApiError(
      0,
      "서비스에 연결할 수 없습니다. 실행 상태를 확인해 주세요.",
      { error_code: "NETWORK_UNAVAILABLE" }
    );
  } finally {
    window.clearTimeout(timeout);
    callerSignal?.removeEventListener("abort", relayCallerAbort);
  }
}

export function jsonBody(value) {
  return JSON.stringify(value);
}
