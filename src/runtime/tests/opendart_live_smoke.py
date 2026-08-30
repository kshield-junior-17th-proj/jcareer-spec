from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request


PUBLIC_BASE = os.getenv("JCAREER_PUBLIC_BASE", "http://127.0.0.1:3000")
CORP_CODE = os.getenv("OPENDART_DEMO_CORP_CODE", "").strip()
COMPANY_NAME = " ".join(os.getenv("OPENDART_DEMO_COMPANY_NAME", "").split())
PASSWORD = "Demo123!"


def request(path: str, *, method: str = "GET", body: object = None, token: str = ""):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    call = urllib.request.Request(PUBLIC_BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(call, timeout=45) as response:
            payload = response.read()
            return response.status, json.loads(payload) if payload else None
    except urllib.error.HTTPError as error:
        payload = error.read()
        try:
            return error.code, json.loads(payload) if payload else None
        except json.JSONDecodeError:
            return error.code, {"detail": "NON_JSON_RESPONSE"}


def main() -> None:
    if os.getenv("CONFIRM_SYNTHETIC_OPENDART_CALL") != "JCAREER_SYNTHETIC_ONLY":
        raise SystemExit("OpenDART live smoke requires its explicit synthetic-call acknowledgement")
    if not re.fullmatch(r"[0-9]{8}", CORP_CODE) or not 2 <= len(COMPANY_NAME) <= 120:
        raise SystemExit("OpenDART live smoke requires an 8-digit corp code and exact public company name")

    stable_ref = hashlib.sha256(f"{CORP_CODE}:{COMPANY_NAME}".encode()).hexdigest()[:16]
    email = f"opendart-{stable_ref}@jcareer.test"
    signup = {
        "email": email,
        "password": PASSWORD,
        "display_name": "공시연동 합성담당자",
        "company_name": COMPANY_NAME,
        "company_address": "공시연동 시연용 합성 주소",
    }
    status, body = request("/api/v1/auth/signup/recruiter", method="POST", body=signup)
    if status == 409:
        status, body = request(
            "/api/v1/auth/login",
            method="POST",
            body={"email": email, "password": PASSWORD},
        )
    if status not in {200, 201} or not isinstance(body, dict):
        raise AssertionError(f"synthetic demo recruiter setup failed with status={status}")
    token = body.get("access_token")
    if not isinstance(token, str) or not token:
        raise AssertionError("synthetic demo recruiter response omitted its session token")

    status, refresh = request(
        "/api/v1/recruiter/company-profile/opendart/refresh",
        method="POST",
        body={"corp_code": CORP_CODE},
        token=token,
    )
    if status not in {202, 409}:
        raise AssertionError(f"OpenDART refresh dispatch failed with status={status}")

    deadline = time.time() + 240
    final = None
    while time.time() < deadline:
        status, collected = request(
            "/api/v1/recruiter/company-profile/opendart/collect",
            method="POST",
            token=token,
        )
        if status == 202:
            time.sleep(5)
            continue
        if status != 200 or not isinstance(collected, dict):
            raise AssertionError(f"OpenDART result collection failed with status={status}")
        final = collected
        break
    if final is None:
        raise AssertionError("OpenDART result did not complete within the bounded smoke window")
    refresh_state = (final.get("refresh") or {}).get("state")
    profile = (final.get("company_profile") or {}).get("opendart") or {}
    snapshot = profile.get("snapshot") or {}
    if refresh_state != "UPDATED_EXTERNAL_SNAPSHOT":
        raise AssertionError(f"OpenDART live refresh ended without an update: state={refresh_state}")
    assert profile.get("state") == "AVAILABLE_LIVE", profile
    assert snapshot.get("synthetic") is False, snapshot
    assert snapshot.get("source_kind") == "live_open_api", snapshot
    assert snapshot.get("score_effect") == "NONE", snapshot
    assert isinstance(snapshot.get("content_sha256"), str), snapshot

    print("J-Career OpenDART live smoke: PASS")
    print("external_snapshot=true, synthetic=false, score_effect=NONE")
    print(f"snapshot_ref={snapshot['content_sha256'][:12]}")


if __name__ == "__main__":
    main()
