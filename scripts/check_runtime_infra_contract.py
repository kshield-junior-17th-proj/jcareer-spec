#!/usr/bin/env python3
"""Check J-Career runtime/Terraform declarations for internal consistency.

This is a source-only contract check.  It does not contact AWS, start the
runtime, assess a control, or claim that the Terraform model is deployable.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROUTE_RE = re.compile(
    r'@app\.(get|post|put|patch|delete)\(\s*"([^"]+)"', re.MULTILINE
)
WEB_ROUTE_RE = re.compile(r'\{\s*path:\s*"([^"]+)"\s*,\s*element:', re.MULTILINE)
ENV_RE_TEMPLATE = r'name\s*=\s*"{name}"'


def read(root: Path, relative: str, errors: list[str]) -> str:
    path = root / relative
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"{relative}: 읽기 실패: {exc}")
        return ""


def require_fragments(
    text: str, relative: str, fragments: dict[str, str], errors: list[str]
) -> None:
    for label, fragment in fragments.items():
        if fragment not in text:
            errors.append(f"{relative}: {label} 계약 누락 ({fragment!r})")


def check_observation_cleanup_safety(source: str, errors: list[str]) -> None:
    require_fragments(
        source,
        "src/runtime/tests/two_sided_asis_observations.py",
        {
            "canonical UUID gate": "def validated_uuid(value: object)",
            "recruiter cache UUID scope": "validated_uuid(cleanup['job_id'])",
            "candidate cache UUID scope": "validated_uuid(candidate_id)",
            "cache exact identifier guard": 'not key.startswith("asis:") or not any(identifier in key for identifier in identifiers)',
            "cache mutation exact job guard": 'not key.startswith("asis:") or job not in key',
            "cache mutation unique entry": "if len(matches) != 1",
            "cache mutation bounded TTL": '"SETEX",',
            "member DB residue value": 'member_residue.stdout.strip() != "0"',
            "company DB residue value": 'company_residue.stdout.strip() != "0"',
            "gateway prompt log read-only probe": '"llm-gateway",\n            "python",\n            "-c"',
            "prompt exact correlation": "record.get('correlation_id') == sys.argv[1]",
            "prompt exact subject": "record.get('subject_ref') == sys.argv[2]",
            "prompt exact count": 'observed.stdout.strip() != "1"',
            "모든 miss prompt pair 추적": "prompt_records.extend(",
            "prompt pair 중복 거부": "len(pairs) != len(set(pairs))",
            "audit actor canonical UUID": "actor = validated_uuid(recruiter_user_id)",
        },
        errors,
    )
    forbidden = {
        "Redis 전체 flush": r"\b(?:FLUSHDB|FLUSHALL)\b",
        "Redis KEYS wildcard": r"redis_cli\(\s*[\"']KEYS[\"']\s*,\s*[\"']\*[\"']",
        "cleanup shell 실행": r"shell\s*=\s*True",
    }
    for label, pattern in forbidden.items():
        if re.search(pattern, source, flags=re.IGNORECASE):
            errors.append(
                f"src/runtime/tests/two_sided_asis_observations.py: {label} cleanup 금지"
            )


def check_bedrock_live_smoke_safety(
    source: str, request_source: str, errors: list[str]
) -> None:
    relative = "src/runtime/tests/bedrock_live_smoke.py"
    require_fragments(
        source,
        relative,
        {
            "live 명시 잠금": 'os.getenv("ALLOW_BEDROCK_LIVE", "false").lower() != "true"',
            "합성 호출 이중 확인": 'os.getenv("CONFIRM_SYNTHETIC_BEDROCK_CALL") != "JCAREER_SYNTHETIC_ONLY"',
            "고정 Bedrock 명령": '"bedrock-runtime",',
            "Converse 명령": '"converse",',
            "region flag": '"--region",',
            "서울 리전 고정": '"ap-northeast-2",',
            "shell 미사용 subprocess": "subprocess.run(",
            "출력 capture": "stdout=subprocess.PIPE",
            "오류 capture": "stderr=subprocess.PIPE",
        },
        errors,
    )
    forbidden = {
        "shell 실행": r"shell\s*=\s*True",
        "CLI profile 강제": r'["\']--profile["\']',
        "자격증명 이름": r"AWS_(?:ACCESS_KEY|SECRET_ACCESS_KEY|SESSION_TOKEN)",
        "무서명 호출": r'["\']--no-sign-request["\']',
    }
    for label, pattern in forbidden.items():
        if re.search(pattern, source, flags=re.IGNORECASE):
            errors.append(f"{relative}: {label} 금지")

    try:
        request = json.loads(request_source)
    except json.JSONDecodeError as exc:
        errors.append(f"src/runtime/tests/bedrock_live_smoke.json: JSON parse 실패 ({exc})")
        return
    if not isinstance(request, dict) or set(request) != {
        "modelId",
        "messages",
        "inferenceConfig",
    }:
        errors.append("src/runtime/tests/bedrock_live_smoke.json: 최상위 exact 계약 불일치")
        return
    try:
        messages = request["messages"]
        text = messages[0]["content"][0]["text"]
        inference = request["inferenceConfig"]
    except (IndexError, KeyError, TypeError):
        errors.append("src/runtime/tests/bedrock_live_smoke.json: 합성 prompt 구조 불일치")
        return
    if (
        not isinstance(messages, list)
        or len(messages) != 1
        or messages[0].get("role") != "user"
        or not isinstance(text, str)
        or "synthetic J-Career recruiting demo" not in text
        or "No real personal data is present" not in text
    ):
        errors.append("src/runtime/tests/bedrock_live_smoke.json: 고정 합성 입력 경계 누락")
    if (
        not isinstance(inference, dict)
        or not isinstance(inference.get("maxTokens"), int)
        or not 1 <= inference["maxTokens"] <= 256
        or inference.get("temperature") != 0
    ):
        errors.append("src/runtime/tests/bedrock_live_smoke.json: bounded deterministic inference 계약 불일치")
    combined = source + "\n" + request_source
    if re.search(
        r"(?:AKIA|ASIA)[A-Z0-9]{16}|AWS_(?:ACCESS_KEY|SECRET_ACCESS_KEY|SESSION_TOKEN)",
        combined,
        flags=re.IGNORECASE,
    ):
        errors.append("Bedrock live smoke: 자격증명 형태 또는 이름 금지")


def require_routes(
    text: str,
    relative: str,
    required: set[tuple[str, str]],
    errors: list[str],
) -> None:
    actual = {(method.upper(), path) for method, path in ROUTE_RE.findall(text)}
    for method, path in sorted(required - actual):
        errors.append(f"{relative}: {method} {path} 라우트 누락")


def require_web_routes(
    text: str, relative: str, required: set[str], errors: list[str]
) -> None:
    actual = set(WEB_ROUTE_RE.findall(text))
    for path in sorted(required - actual):
        errors.append(f"{relative}: browser route {path} 누락")


def javascript_api_calls(source: str) -> list[str]:
    calls: list[str] = []
    for match in re.finditer(r"\bapi\(", source):
        depth = 1
        quote: str | None = None
        escaped = False
        index = match.end()
        while index < len(source):
            character = source[index]
            if quote:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == quote:
                    quote = None
            elif character in {'"', "'", "`"}:
                quote = character
            elif character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
                if depth == 0:
                    calls.append(source[match.start() : index + 1])
                    break
            index += 1
    return calls


def require_web_api_call(
    source: str,
    label: str,
    path_fragments: tuple[str, ...],
    expected_methods: set[str],
    errors: list[str],
) -> None:
    matching = [
        call
        for call in javascript_api_calls(source)
        if all(fragment in call for fragment in path_fragments)
    ]
    if not matching:
        errors.append(f"src/runtime/web/src/App.jsx: {label} API 호출 누락")
        return
    actual_methods: set[str] = set()
    for call in matching:
        if "method:" not in call:
            actual_methods.add("GET")
            continue
        method_expression = call.split("method:", 1)[1].split("body:", 1)[0][:200]
        actual_methods.update(
            re.findall(r'"(GET|POST|PUT|PATCH|DELETE)"', method_expression)
        )
    if actual_methods != expected_methods:
        errors.append(
            f"src/runtime/web/src/App.jsx: {label} method 계약 불일치 "
            f"(expected={sorted(expected_methods)}, actual={sorted(actual_methods)})"
        )


def compose_service_block(
    compose: str, service: str, errors: list[str]
) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(service)}:\s*\n(.*?)(?=^  [a-zA-Z0-9_-]+:\s*\n|^volumes:)",
        compose,
    )
    if not match:
        errors.append(f"src/runtime/compose.yaml: {service} service 블록 누락")
        return ""
    return match.group(1)


def terraform_service_block(
    compute: str, service: str, errors: list[str]
) -> str:
    match = re.search(
        rf'(?s)each\.key\s*==\s*"{re.escape(service)}"\s*\?\s*\[(.*?)\]\s*:\s*\[\]',
        compute,
    )
    if not match:
        errors.append(
            f"terraform/asis/compute/main.tf: {service} environment 분기 누락"
        )
        return ""
    return match.group(1)


def terraform_local_service_block(
    locals_text: str, service: str, errors: list[str]
) -> str:
    match = re.search(
        rf"(?ms)^    {re.escape(service)}\s*=\s*\{{\s*\n(.*?)(?=^    [a-zA-Z0-9_-]+\s*=\s*\{{|^  \}})",
        locals_text,
    )
    if not match:
        errors.append(f"terraform/asis/compute/locals.tf: {service} service 누락")
        return ""
    return match.group(1)


def terraform_variable_block(
    variables_text: str, variable: str, errors: list[str]
) -> str:
    match = re.search(
        rf'(?ms)^variable\s+"{re.escape(variable)}"\s*\{{\s*\n(.*?)(?=^variable\s+"|\Z)',
        variables_text,
    )
    if not match:
        errors.append(f"terraform/asis/variables.tf: {variable} variable 블록 누락")
        return ""
    return match.group(1)


def terraform_string_default(
    variable_block: str, variable: str, errors: list[str]
) -> str | None:
    match = re.search(r'\bdefault\s*=\s*"([^"]+)"', variable_block)
    if not match:
        errors.append(f"terraform/asis/variables.tf: {variable} 문자열 default 누락")
        return None
    return match.group(1)


def declaration_value(outputs: str, key: str, errors: list[str]) -> str | None:
    match = re.search(rf"\b{re.escape(key)}\s*=\s*\"([^\"]+)\"", outputs)
    if not match:
        errors.append(f"terraform/asis/outputs.tf: {key} 상태 선언 누락")
        return None
    return match.group(1)


def check_wiring_declaration(
    *,
    outputs: str,
    compute: str,
    key: str,
    env_names: tuple[str, ...],
    errors: list[str],
) -> None:
    state = declaration_value(outputs, key, errors)
    present = [
        bool(re.search(ENV_RE_TEMPLATE.format(name=re.escape(name)), compute))
        for name in env_names
    ]
    if any(present) and not all(present):
        errors.append(
            f"terraform/asis/compute/main.tf: {key} 배선이 일부만 존재함 "
            f"({dict(zip(env_names, present))})"
        )
        return
    if state is None:
        return
    declared_missing = state.startswith("not-modeled")
    actually_modeled = all(present)
    if declared_missing == actually_modeled:
        errors.append(
            f"terraform/asis: {key} 선언({state})과 ECS 환경변수 배선 상태가 다름"
        )


def check(root: Path) -> list[str]:
    errors: list[str] = []
    api = read(root, "src/runtime/api/app/main.py", errors)
    database = read(root, "src/runtime/api/app/database.py", errors)
    models = read(root, "src/runtime/api/app/models.py", errors)
    outcome_store = read(root, "src/runtime/api/app/outcome_store.py", errors)
    db_init = read(root, "src/runtime/db-init/01-create-domain-databases.sql", errors)
    agent = read(root, "src/runtime/agent/app/main.py", errors)
    gateway = read(root, "src/runtime/llm_gateway/app/main.py", errors)
    bedrock_broker_client = read(
        root, "src/runtime/llm_gateway/app/aws_broker_client.py", errors
    )
    bedrock_response = read(
        root, "src/runtime/llm_gateway/app/bedrock_response.py", errors
    )
    bedrock_live_smoke = read(root, "src/runtime/tests/bedrock_live_smoke.py", errors)
    bedrock_live_request = read(
        root, "src/runtime/tests/bedrock_live_smoke.json", errors
    )
    web = read(root, "src/runtime/web/src/App.jsx", errors)
    web_api = read(root, "src/runtime/web/src/api.js", errors)
    web_css = read(root, "src/runtime/web/src/styles.css", errors)
    runtime_readme = read(root, "src/runtime/README.md", errors)
    runtime_spec = read(root, "src/runtime/ASIS_RUNTIME_SPEC.md", errors)
    requirements_trace = read(
        root, "context/findings/ASIS_RUNTIME_REQUIREMENTS_TRACE.md", errors
    )
    scoring_policy_design = read(
        root, "context/findings/JOB_SCORING_POLICY_DESIGN_REVIEW.md", errors
    )
    compose = read(root, "src/runtime/compose.yaml", errors)
    outputs = read(root, "terraform/asis/outputs.tf", errors)
    asis_main = read(root, "terraform/asis/main.tf", errors)
    tf_variables = read(root, "terraform/asis/variables.tf", errors)
    compute = read(root, "terraform/asis/compute/main.tf", errors)
    compute_locals = read(root, "terraform/asis/compute/locals.tf", errors)
    data_outputs = read(root, "terraform/asis/data/outputs.tf", errors)
    api_security = read(root, "src/runtime/api/app/security.py", errors)
    observation = read(root, "src/runtime/tests/two_sided_asis_observations.py", errors)
    runtime_smoke = read(root, "src/runtime/tests/smoke.py", errors)
    security_smoke = read(root, "src/runtime/tests/security_smoke.py", errors)
    database_boundary_test = read(root, "src/runtime/tests/database_boundary.py", errors)
    asis_tf = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in sorted((root / "terraform/asis").rglob("*.tf"))
    ) if (root / "terraform/asis").exists() else ""

    require_routes(
        api,
        "src/runtime/api/app/main.py",
        {
            ("GET", "/health"),
            ("GET", "/api/v1/runtime"),
            ("POST", "/api/v1/auth/signup"),
            ("POST", "/api/v1/auth/signup/recruiter"),
            ("POST", "/api/v1/auth/login"),
            ("GET", "/api/v1/auth/me"),
            ("POST", "/api/v1/candidates/me/consents"),
            ("GET", "/api/v1/candidates/me/consents"),
            ("DELETE", "/api/v1/candidates/me/consents/{consent_type}"),
            ("GET", "/api/v1/candidates/me/applications"),
            ("GET", "/api/v1/candidates/me/recommendations"),
            ("GET", "/api/v1/candidates/me/resume"),
            ("POST", "/api/v1/candidates/me/resume"),
            ("DELETE", "/api/v1/candidates/me"),
            ("GET", "/api/v1/jobs"),
            ("GET", "/api/v1/jobs/{job_id}"),
            ("POST", "/api/v1/jobs/{job_id}/applications"),
            ("GET", "/api/v1/recruiter/overview"),
            ("GET", "/api/v1/recruiter/company-profile"),
            ("PUT", "/api/v1/recruiter/company-profile"),
            ("GET", "/api/v1/recruiter/jobs"),
            ("POST", "/api/v1/recruiter/jobs"),
            ("PUT", "/api/v1/recruiter/jobs/{job_id}"),
            ("GET", "/api/v1/recruiter/jobs/{job_id}/pipeline"),
            ("GET", "/api/v1/recruiter/jobs/{job_id}/recommendations"),
            ("PATCH", "/api/v1/recruiter/applications/{application_id}"),
            ("GET", "/api/v1/admin/audit"),
        },
        errors,
    )
    require_routes(
        agent,
        "src/runtime/agent/app/main.py",
        {
            ("GET", "/health"),
            ("GET", "/agent/health"),
            ("POST", "/internal/match/jobs"),
            ("POST", "/internal/match/candidates"),
            ("POST", "/agent/internal/match/jobs"),
            ("POST", "/agent/internal/match/candidates"),
        },
        errors,
    )
    require_routes(
        gateway,
        "src/runtime/llm_gateway/app/main.py",
        {
            ("GET", "/health"),
            ("GET", "/llm/health"),
            ("POST", "/internal/explanations"),
            ("POST", "/llm/internal/explanations"),
        },
        errors,
    )
    require_web_routes(
        web,
        "src/runtime/web/src/App.jsx",
        {
            "/",
            "/jobs",
            "/jobs/:id",
            "/login",
            "/signup",
            "/signup/consent",
            "/candidate/resume",
            "/candidate/applications",
            "/candidate/recommendations",
            "/candidate/withdraw",
            "/recruiter/signup",
            "/recruiter/overview",
            "/recruiter/jobs",
            "/recruiter/jobs/:id/pipeline",
            "/recruiter/jobs/:id/recommendations",
            "/admin/audit",
            "/privacy",
            "/terms",
            "*",
        },
        errors,
    )
    require_fragments(
        web,
        "src/runtime/web/src/App.jsx",
        {
            "공개 공고 API": 'api(`/api/v1/jobs?',
            "공고 상세 API": 'api(`/api/v1/jobs/${id}`)',
            "지원 API": 'api(`/api/v1/jobs/${id}/applications`',
            "지원자 가입 API": 'api("/api/v1/auth/signup"',
            "기업 가입 API": 'api("/api/v1/auth/signup/recruiter"',
            "로그인 API": 'api("/api/v1/auth/login"',
            "동의 API": 'api("/api/v1/candidates/me/consents"',
            "이력서 API": 'api("/api/v1/candidates/me/resume"',
            "지원 현황 API": 'api("/api/v1/candidates/me/applications")',
            "지원자 추천 API": 'api("/api/v1/candidates/me/recommendations")',
            "탈퇴 API": 'api("/api/v1/candidates/me"',
            "기업 프로필 API": 'api("/api/v1/recruiter/company-profile"',
            "기업 공고 API": 'api("/api/v1/recruiter/jobs")',
            "기업 파이프라인 API": 'api(`/api/v1/recruiter/jobs/${id}/pipeline`)',
            "기업 추천 API": 'api(`/api/v1/recruiter/jobs/${id}/recommendations`)',
            "전형 변경 API": 'api(`/api/v1/recruiter/applications/${applicationId}`',
            "감사 조회 API": 'api(`/api/v1/admin/audit',
        },
        errors,
    )
    web_call_contracts = (
        ("공개 공고 검색", ('`/api/v1/jobs?${params}`',), {"GET"}),
        ("공고 상세", ('`/api/v1/jobs/${id}`',), {"GET"}),
        ("공고 지원", ('`/api/v1/jobs/${id}/applications`',), {"POST"}),
        ("로그인", ('"/api/v1/auth/login"',), {"POST"}),
        ("지원자 가입", ('"/api/v1/auth/signup"',), {"POST"}),
        ("기업 가입", ('"/api/v1/auth/signup/recruiter"',), {"POST"}),
        ("동의 기록·조회", ('"/api/v1/candidates/me/consents"',), {"GET", "POST"}),
        ("이력서 조회·저장", ('"/api/v1/candidates/me/resume"',), {"GET", "POST"}),
        ("지원 현황", ('"/api/v1/candidates/me/applications"',), {"GET"}),
        ("지원자 추천", ('"/api/v1/candidates/me/recommendations"',), {"GET"}),
        ("필수·선택 동의 철회", ('`/api/v1/candidates/me/consents/${consentType}`',), {"DELETE"}),
        ("지원자 탈퇴", ('"/api/v1/candidates/me"',), {"DELETE"}),
        ("기업 운영 홈", ('"/api/v1/recruiter/overview"',), {"GET"}),
        ("기업 프로필 조회·저장", ('"/api/v1/recruiter/company-profile"',), {"GET", "PUT"}),
        ("기업 공고 조회·생성·수정", ('"/api/v1/recruiter/jobs"',), {"GET", "POST", "PUT"}),
        ("기업 공고 상태", ('`/api/v1/recruiter/jobs/${job.id}`',), {"PUT"}),
        ("기업 파이프라인", ('`/api/v1/recruiter/jobs/${id}/pipeline`',), {"GET"}),
        ("전형 상태 저장", ('`/api/v1/recruiter/applications/${applicationId}`',), {"PATCH"}),
        ("기업 추천", ('`/api/v1/recruiter/jobs/${id}/recommendations`',), {"GET"}),
        ("감사 이벤트", ('`/api/v1/admin/audit',), {"GET"}),
    )
    for label, path_fragments, methods in web_call_contracts:
        require_web_api_call(web, label, path_fragments, methods, errors)
    overview_state = (
        "/recruiter/overview" in set(WEB_ROUTE_RE.findall(web)),
        ("GET", "/api/v1/recruiter/overview") in {
            (method.upper(), path) for method, path in ROUTE_RE.findall(api)
        },
        '"company-operations-overview"' in outputs,
    )
    if any(overview_state) and not all(overview_state):
        errors.append(
            "기업 overview 확장 화면의 web/API/Terraform 선언이 일부 계층에만 존재함"
        )
    require_fragments(
        web,
        "src/runtime/web/src/App.jsx",
        {
            "단일 router blocker": "const blocker = useBlocker(shouldBlock)",
            "요청 세대 보호": "function useRequestEpoch()",
            "동의 이동 draft 원자화": 'allowNextNavigation("/signup/consent")',
            "401 재인증 dirty 확인": "로그인 정보를 다시 확인해야 합니다. 로그인 화면으로 이동하면 저장하지 않은 입력은 사라집니다.",
            "동일 공고 상태/편집 충돌 차단": "이 공고의 편집기를 닫거나 변경 내용을 저장한 뒤 공개 상태를 바꿔 주세요.",
            "새 공고 전환 dirty 확인": "버리고 새 공고를 작성할까요?",
            "필수 동의 철회 도달성": 'revoke("privacy_core")',
            "선택 동의 철회 도달성": 'revoke("marketing")',
            "재시도 버튼 form 오동작 차단": '<button type="button" className="text-button" onClick={onRetry}>',
            "지원일 machine-readable time": '<time dateTime={item.applied_at}>',
            "파이프라인 초기 오류 재시도": '<ErrorNotice error={error} onRetry={load} />',
            "플랫폼 우선요인 요약": "이 점수의 우선요인",
            "기업별 가중치 미적용 경계": "기업별 가중치나 가산점 정책은 적용되지 않았습니다",
        },
        errors,
    )
    require_fragments(
        web_api,
        "src/runtime/web/src/api.js",
        {"401 전역 신호": 'window.dispatchEvent(new Event("jcareer:unauthorized"))'},
        errors,
    )
    require_fragments(
        web_css,
        "src/runtime/web/src/styles.css",
        {
            "동적 viewport": "min-height: 100dvh",
            "검색 패널 focus": ".jobs-hero .search-panel :focus-visible",
            "모바일 터치 높이": ".button.small { min-height: 44px; }",
        },
        errors,
    )
    require_fragments(
        agent,
        "src/runtime/agent/app/main.py",
        {
            "matcher version getenv": 'os.getenv("MATCHER_VERSION", "deterministic-0.2.0")',
            "formula version getenv": 'os.getenv("SCORING_FORMULA_VERSION", "deterministic-70-20-10-v1")',
            "breakdown version getenv": 'os.getenv("SCORE_BREAKDOWN_SCHEMA_VERSION", "score-breakdown-v1")',
            "skills weight getenv": 'os.getenv("SKILL_MAX_POINTS", "70")',
            "experience weight getenv": 'os.getenv("EXPERIENCE_MAX_POINTS", "20")',
            "role weight getenv": 'os.getenv("ROLE_MAX_POINTS", "10")',
        },
        errors,
    )
    require_fragments(
        gateway,
        "src/runtime/llm_gateway/app/main.py",
        {
            "provider getenv": 'os.getenv("LLM_PROVIDER", "local-synthetic-stub")',
            "Bedrock lock getenv": 'os.getenv("ALLOW_BEDROCK_LIVE", "false")',
            "explanation version": '"score-explanation-v1"',
            "Bedrock capability broker 호출": "return generate_explanations(",
            "provider 구성 지문": "def _provider_config_metadata()",
            "provider 구성 지문 기록": '"provider_config_fingerprint"',
        },
        errors,
    )
    require_fragments(
        bedrock_broker_client,
        "src/runtime/llm_gateway/app/aws_broker_client.py",
        {
            "Bedrock 응답 parser import": "from .bedrock_response import parse_bedrock_explanations",
            "Bedrock 응답 parser 호출": "return parse_bedrock_explanations(",
            "broker UDS 고정": 'socket_path != "/run/jcareer-bedrock/broker.sock"',
            "환경 proxy 비신뢰": "trust_env=False",
        },
        errors,
    )
    require_fragments(
        bedrock_response,
        "src/runtime/llm_gateway/app/bedrock_response.py",
        {
            "최상위 exact object": 'set(payload) != {"items"}',
            "items list 형식": "not isinstance(output_items, list)",
            "subject allowlist": "subject_ref not in expected_refs",
            "subject 중복 거부": "subject_ref in mapped",
            "설명 길이 상한": "len(text) > 1_000",
            "요청·응답 subject 일치": "set(mapped) != expected_refs",
        },
        errors,
    )
    check_bedrock_live_smoke_safety(
        bedrock_live_smoke, bedrock_live_request, errors
    )
    require_fragments(
        runtime_readme,
        "src/runtime/README.md",
        {
            "지원자 cache 변경 재료": "후보자 추천 캐시 키는 이력서 갱신 시점과 열린 공고의 식별자",
            "기업 cache stale 분리": "기업 추천 캐시는 지원자 집합·이력서 version을 키에 포함하지",
            "위험 관찰 미실행 경계": "`DRAFT_NOT_APPROVED`·`NOT_EXECUTED`",
            "receipt schema 비증거 경계": "실제 receipt,",
        },
        errors,
    )
    require_fragments(
        runtime_spec,
        "src/runtime/ASIS_RUNTIME_SPEC.md",
        {
            "지원자 cache canonical hash": "상태·갱신 시점의 canonical hash가 들어간다",
            "기업 cache AS-IS 경계": "지원자 집합·이력서 version 누락과 stale 관찰",
            "receipt validator 부재": "실제 receipt와 archive 포함관계",
        },
        errors,
    )
    require_fragments(
        outputs,
        "terraform/asis/outputs.tf",
        {
            "앱 artifact manifest": "src/runtime/contracts/application_artifacts.yaml",
            "앱 artifact 미빌드 상태": "UNBUILT_UNPUBLISHED",
            "endpoint 표본 manifest": "src/runtime/contracts/endpoint_test_sample.yaml",
            "endpoint 표본 미실행 상태": "NOT_EXECUTED_NOT_TERRAFORM_MANAGED",
            "API source 계약": "src/runtime/contracts/api_surface.json",
            "API source 비실행 상태": "SOURCE_DECLARATION_NOT_EXECUTION_EVIDENCE",
            "위험 관찰 계획": "src/runtime/contracts/risk_observation_plan.yaml",
            "위험 관찰 미승인·미실행 상태": "DRAFT_NOT_APPROVED_NOT_EXECUTED",
            "lab receipt schema": "src/runtime/contracts/lab_run_receipt.schema.json",
            "lab receipt 부재 상태": "SCHEMA_ONLY_NO_RECEIPT",
        },
        errors,
    )
    require_fragments(
        requirements_trace,
        "context/findings/ASIS_RUNTIME_REQUIREMENTS_TRACE.md",
        {
            "지원자 추적": "| RT-02 |",
            "기업 고객 추적": "| RT-03 |",
            "양 DB 추적": "| RT-04 |",
            "기업 우선요인 공백 추적": "| RT-06 |",
            "Bedrock 실행 경계 추적": "| RT-08 |",
            "Terraform model-only 추적": "| RT-11 |",
            "Windows/Mac 표본 공백 추적": "| RT-13 |",
            "dashboard 운영 공백 추적": "| RT-16 |",
            "향후 lab receipt 추적": "| RT-22 |",
            "PNG 공백 추적": "| RT-18 |",
            "TRACE 신규 서비스 보류 추적": "| RT-19 |",
        },
        errors,
    )
    require_fragments(
        scoring_policy_design,
        "context/findings/JOB_SCORING_POLICY_DESIGN_REVIEW.md",
        {
            "현재 고정 산식 경계": "플랫폼 공통 70/20/10",
            "허용 직무요인": "`skills`, `experience`, `role`",
            "임의 가중치 금지 제안": "자유 가중치나 LLM이 고른 가중치 대신",
            "점수와 Bedrock 분리": "Bedrock은 선택적 문장 표현만 맡고",
            "사람 결정 항목": "사람이 확정할 항목은 preset 수치와 상한",
        },
        errors,
    )
    require_fragments(
        observation,
        "src/runtime/tests/two_sided_asis_observations.py",
        {
            "stub-only provider guard": 'gateway["provider"] == "local-synthetic-stub"',
            "Bedrock live guard": 'gateway["bedrock_live_enabled"] == "false"',
            "recruiter cache miss": 'initial_recommendations["cache"] == "miss"',
            "recruiter stale hit": 'stale_recommendations["cache"] == "hit"',
            "new applicant omission": "candidate_b_email not in stale_by_email",
            "finally cleanup": "finally:",
            "cleanup failure isolation": "strict=not scenario_failed",
            "두 DB 합성 레코드 cleanup": "delete_observation_database_records",
            "실행별 cache cleanup": "delete_observation_cache_keys",
            "raw prompt 보존 실측 경계": "raw-prompt-log=observed-retained",
            "raw prompt exact probe": "verify_retained_prompt_records",
            "DB cleanup 잔존 검증": "database residue verification failed",
            "Redis cleanup 잔존 검증": "cache residue verification failed",
        },
        errors,
    )
    check_observation_cleanup_safety(observation, errors)
    require_fragments(
        runtime_smoke,
        "src/runtime/tests/smoke.py",
        {
            "기업 홈 회원 DB 계정 경계": '"계정·인증"',
            "기업 홈 회원 DB 동의 경계": '"동의 이벤트"',
            "기업 홈 회원 DB 이력서 경계": '"지원자 이력서"',
            "기업 홈 회원 DB 지원 경계": '"지원 내역"',
            "기업 홈 회원 DB 감사 경계": '"감사 이벤트"',
            "기업 홈 기업 DB 경계": '"company_database": ["기업", "기업 방향 프로필", "채용공고"]',
        },
        errors,
    )
    require_fragments(
        security_smoke,
        "src/runtime/tests/security_smoke.py",
        {
            "기업 전형 정상 경로": 'expect(status, 200, own_tenant_update, "own-tenant application status update")',
            "기업 전형 정상 감사": 'event_type=application_status_changed&limit=500',
            "현재 실행 거부 exact 집합": "required_denial_facts <= denial_facts",
            "현재 실행 공고 거부 ref": 'test_job["id"], "view_pipeline"',
            "audit self-log 현재 호출": "current_audit_view_ids - prior_audit_view_ids",
            "기업 홈 공고 delta": 'job_overview["metrics"]["open_jobs"]',
            "기업 홈 지원 delta": 'applied_overview["metrics"]["total_applications"]',
            "기업 홈 단계 delta": 'stage_counts(interview_overview)["interview"]',
            "거부 감사 tenant 식별자": 'recruiter["company_id"]',
            "정상 감사 tenant 식별자": 'beta_recruiter["company_id"]',
        },
        errors,
    )
    require_fragments(
        database_boundary_test,
        "src/runtime/tests/database_boundary.py",
        {
            "psql SQL 오류 전파": '"ON_ERROR_STOP=1"',
            "합성결과 DB 테이블 경계": 'outcome_tables = table_names("jcareer_outcome_app", "jcareer_outcome")',
            "세 role 여섯 방향 연결 거부": 'denied_connections = (',
            "합성결과 role의 회원 DB 연결 거부": '("jcareer_outcome_app", "jcareer_member")',
            "합성결과 role의 기업 DB 연결 거부": '("jcareer_outcome_app", "jcareer_company")',
            "교차 연결 거부 오류 검증": '"permission denied for database" in denial.stderr.lower()',
            "회원 DB 정확한 논리 연결 검증": 'member_row.stdout.strip() == f"{signup_user_id}|recruiter|{signup_company_id}"',
            "기업 DB 정확한 논리 연결 검증": 'company_row.stdout.strip() == f"{signup_company_id}|{company_name}"',
            "회원 DB 합성 행 정리 검증": 'member_residue.stdout.strip() == "0"',
            "기업 DB 합성 행 정리 검증": 'company_residue.stdout.strip() == "0"',
        },
        errors,
    )

    require_fragments(
        models,
        "src/runtime/api/app/models.py",
        {
            "기업 고객 엔터티": "class Company(CompanyBase)",
            "기업 공고 엔터티": "class Job(CompanyBase)",
            "통합 identity 엔터티": "class User(MemberBase)",
            "동의 엔터티": "class ConsentEvent(MemberBase)",
            "이력서 엔터티": "class Resume(MemberBase)",
            "지원 관계 엔터티": "class Application(MemberBase)",
            "감사 엔터티": "class AuditEvent(MemberBase)",
            "identity의 기업 논리 참조": "company_id: Mapped[str | None]",
        },
        errors,
    )
    require_fragments(
        database,
        "src/runtime/api/app/database.py",
        {
            "회원 DB URL": "MEMBER_DATABASE_URL = os.getenv(",
            "기업 DB URL": "COMPANY_DATABASE_URL = os.getenv(",
            "outcome DB URL": "OUTCOME_DATABASE_URL = os.getenv(",
            "실제 DB target 정규화": "def database_target(database_url: str)",
            "three distinct DB targets fail-closed": "if len(database_targets) != 3:",
            "회원 engine": "member_engine = _engine(MEMBER_DATABASE_URL)",
            "기업 engine": "company_engine = _engine(COMPANY_DATABASE_URL)",
            "outcome engine": "outcome_engine = _engine(OUTCOME_DATABASE_URL)",
            "company and outcome model binds": "binds={CompanyBase: company_engine, OutcomeBase: outcome_engine}",
        },
        errors,
    )
    require_fragments(
        outcome_store,
        "src/runtime/api/app/outcome_store.py",
        {
            "outcome dataset model": "class OutcomeDataset(OutcomeBase)",
            "synthetic outcome model": "class SyntheticDocumentOutcome(OutcomeBase)",
            "runtime effect fixed to NONE": "runtime_effect = 'NONE'",
            "ranking effect fixed to NONE": "ranking_effect = 'NONE'",
            "outcome row-set cache revision": "def outcome_observation_revision(session: Session)",
        },
        errors,
    )
    require_fragments(
        db_init,
        "src/runtime/db-init/01-create-domain-databases.sql",
        {
            "회원 app role": "CREATE ROLE jcareer_member_app LOGIN",
            "기업 app role": "CREATE ROLE jcareer_company_app LOGIN",
            "outcome app role": "CREATE ROLE jcareer_outcome_app LOGIN",
            "회원 database": "CREATE DATABASE jcareer_member OWNER jcareer_member_app;",
            "기업 database": "CREATE DATABASE jcareer_company OWNER jcareer_company_app;",
            "outcome database": "CREATE DATABASE jcareer_outcome OWNER jcareer_outcome_app;",
            "회원 PUBLIC CONNECT 회수": "REVOKE CONNECT, TEMPORARY ON DATABASE jcareer_member FROM PUBLIC;",
            "기업 PUBLIC CONNECT 회수": "REVOKE CONNECT, TEMPORARY ON DATABASE jcareer_company FROM PUBLIC;",
            "outcome PUBLIC CONNECT 회수": "REVOKE CONNECT, TEMPORARY ON DATABASE jcareer_outcome FROM PUBLIC;",
        },
        errors,
    )
    require_fragments(
        compose,
        "src/runtime/compose.yaml",
        {
            "회원 DB 배선": "MEMBER_DATABASE_URL:",
            "기업 DB 배선": "COMPANY_DATABASE_URL:",
            "outcome DB 배선": "OUTCOME_DATABASE_URL:",
            "Redis 배선": "REDIS_URL:",
            "matcher 배선": "AGENT_BASE_URL:",
            "설명 gateway 배선": "LLM_GATEWAY_BASE_URL:",
            "세션 서명키 배선": "SESSION_SIGNING_KEY:",
            "합성 데이터 표시": "DATASET_PROFILE: demo_not_for_measurement",
            "Bedrock 실호출 기본 잠금": "ALLOW_BEDROCK_LIVE: ${ALLOW_BEDROCK_LIVE:-false}",
        },
        errors,
    )
    compose_api = compose_service_block(compose, "api", errors)
    compose_agent = compose_service_block(compose, "agent", errors)
    compose_gateway = compose_service_block(compose, "llm-gateway", errors)
    require_fragments(
        compose_api,
        "src/runtime/compose.yaml::api",
        {
            "회원 DB": "MEMBER_DATABASE_URL:",
            "기업 DB": "COMPANY_DATABASE_URL:",
            "outcome DB": "OUTCOME_DATABASE_URL:",
            "Redis": "REDIS_URL:",
            "matcher": "AGENT_BASE_URL:",
            "gateway": "LLM_GATEWAY_BASE_URL:",
            "provider": "LLM_PROVIDER:",
            "Bedrock region": "BEDROCK_REGION:",
            "Bedrock model": "BEDROCK_MODEL_ID:",
            "세션키": "SESSION_SIGNING_KEY:",
            "합성 dataset": "DATASET_PROFILE: demo_not_for_measurement",
        },
        errors,
    )
    require_fragments(
        compose_agent,
        "src/runtime/compose.yaml::agent",
        {
            "matcher version": "MATCHER_VERSION: deterministic-0.2.0",
            "formula version": "SCORING_FORMULA_VERSION: deterministic-70-20-10-v1",
            "breakdown version": "SCORE_BREAKDOWN_SCHEMA_VERSION: score-breakdown-v1",
            "skills weight": 'SKILL_MAX_POINTS: "70"',
            "experience weight": 'EXPERIENCE_MAX_POINTS: "20"',
            "role weight": 'ROLE_MAX_POINTS: "10"',
        },
        errors,
    )
    require_fragments(
        compose_gateway,
        "src/runtime/compose.yaml::llm-gateway",
        {
            "provider": "LLM_PROVIDER:",
            "Bedrock lock": "ALLOW_BEDROCK_LIVE:",
            "Bedrock region": "BEDROCK_REGION:",
            "Bedrock model": "BEDROCK_MODEL_ID:",
            "explanation version": "EXPLANATION_CONTRACT_VERSION: score-explanation-v1",
            "prompt path": "PROMPT_LOG_PATH: /data/prompt-log.jsonl",
        },
        errors,
    )
    require_fragments(
        api,
        "src/runtime/api/app/main.py",
        {
            "API email/DB length boundary": "email: str = Field(min_length=3, max_length=254)",
            "동의 version/DB length boundary": 'policy_version: str = Field(default="2026-05", min_length=1, max_length=40)',
            "공고 요구기술 boundary": "def normalise_required_skills",
            "이력서 기술 boundary": "def normalise_resume_skills",
            "provider cache partition": "def explanation_provider_config()",
            "provider-independent attempt metadata": "def explanation_attempt_metadata(",
            "warm cache boundary": '"CACHE_HIT_PROVIDER_NOT_REVALIDATED"',
            "현재 요청 필드 집합 상태": '"CURRENT_REQUEST_PREPARED_BY_API"',
            "캐시 원본 필드 집합 미검증 상태": '"CACHE_ORIGIN_FIELD_SET_NOT_VERIFIED"',
            "빈 대상 필드 미준비 상태": '"NOT_PREPARED_EMPTY_SUBJECT_SET"',
            "캐시 원본 gateway 미검증 상태": '"CACHE_ENTRY_ACCEPTED_ORIGIN_NOT_VERIFIED"',
            "공고·이력서 기술 공통 key": "def normalise_skill_values",
            "matcher feature envelope": "matcher matched feature envelope",
            "matcher 표시 metadata": "matcher factor display contract",
            "matcher order envelope": "matcher ranking order",
            "explanation envelope": "def _validate_explanation_response",
            "설명 metadata envelope": "explanation metadata contract",
            "빈 설명 요청 단락": "if not items:\n        return \"AVAILABLE\", {}",
            "이력서 동시 생성 경계": "이력서가 동시에 변경되었습니다. 다시 저장해 주세요",
            "중복 지원 동시성 경계": "raise HTTPException(status_code=409, detail=\"이미 지원한 공고입니다\") from exc",
            "cache object envelope": 'decoded.get("recommendation_status") != "AVAILABLE"',
            "지원자 추천 공고 cache contract": "def candidate_job_cache_contract",
            "outcome dataset and row-set cache partition": 'f"outcome:{OUTCOME_DATASET_VERSION}:{outcome_revision}:"',
            "outcome DB independent session": "with Session(bind=outcome_engine) as outcome_db:",
            "outcome DB failure isolation": '"state": "UNAVAILABLE_OBSERVATION_STORE"',
            "degraded outcome response cache bypass": 'if explanation_status == "AVAILABLE" and not outcome_observation_degraded:',
            "역할 중립 사용자 감사 참조": "def pseudonymous_user_ref",
            "기업 연결 공통 검사": "def recruiter_company",
            "기업 권한 거부 action 구분": 'denied_action: str = "read"',
            "전형 변경 기업 연결 검사": ') -> dict[str, object]:\n    recruiter_company(db, user)\n    application = db.get(Application, application_id)',
        },
        errors,
    )
    consent_order = ".order_by(ConsentEvent.occurred_at.desc(), ConsentEvent.id.desc())"
    if api.count(consent_order) < 2:
        errors.append(
            "src/runtime/api/app/main.py: 동의 게이트·조회 최신 이벤트 tie-break 계약 불일치"
        )
    seed = read(root, "src/runtime/api/app/seed.py", errors)
    require_fragments(
        seed,
        "src/runtime/api/app/seed.py",
        {
            "결정론 seed sentinel": "def required_seed_ids()",
            "기존 seed 완전성 검사": "def assert_existing_seed_complete",
            "부분 seed 자동복구 차단": "automatic repair is disabled",
        },
        errors,
    )
    require_fragments(
        api_security,
        "src/runtime/api/app/security.py",
        {"세션 환경변수 계약": 'os.getenv("SESSION_SIGNING_KEY"'},
        errors,
    )
    require_fragments(
        outputs,
        "terraform/asis/outputs.tf",
        {
            "배포 미구현 상태": 'implementation_state = "model-only-runtime-images-not-provisioned"',
            "지원자 고객 표면": "candidate = [",
            "기업 고객 표면": "company = [",
            "기업 매칭 프로필": '"company-declared-matching-profile"',
            "기업 파이프라인": '"candidate-pipeline"',
            "담당자-기업 논리 연결": 'implemented_identity_model = "recruiter-company-logical-link"',
            "가입 시 첫 담당자 생성": 'signup_recruiter_creation  = "one-recruiter-with-new-company"',
            "담당자 수 카디널리티 미강제": 'company_recruiter_cardinality_constraint = "not-enforced-in-source"',
            "조직 멤버십 한계": 'organization_membership    = "not-implemented"',
            "초대·역할 생명주기 한계": 'invite_and_role_lifecycle   = "not-implemented"',
            "기업 계정 탈퇴 한계": 'company_account_withdrawal = "not-implemented"',
            "기업 소유권 이전 한계": 'company_ownership_transfer = "not-implemented"',
            "기업 동의 생명주기 한계": 'company_consent_lifecycle   = "not-implemented"',
            "기업 상태 전환 한계": 'company_status_transition  = "not-implemented"',
            "기업 가입 초기 상태": 'company_signup_initial_status = "approved-model-default-without-review-transition"',
            "기업 검증 게이트 한계": 'company_verification_gate   = "not-enforced-in-source"',
            "가입 작업 ID 한계": 'company_signup_operation_id         = "not-modeled"',
            "가입 멱등 키 한계": 'company_signup_idempotency_key      = "not-modeled"',
            "교차 저장소 보상 한계": 'cross_store_compensation            = "not-modeled"',
            "교차 저장소 사후 조정 한계": 'cross_store_reconciliation          = "not-modeled"',
            "교차 저장소 outbox 한계": 'cross_store_outbox                  = "not-modeled"',
            "지원 시점 snapshot 한계": 'application_material_binding       = "current-references-no-immutable-application-snapshot"',
            "추천 실행 감사 한계": 'recommendation_run_audit_event     = "not-implemented"',
            "cache hit 감사 한계": 'recommendation_cache_hit_audit     = "not-implemented"',
            "cache item schema 한계": 'cache_operation_item_schema        = "not-validated"',
            "회원 DB 소유": 'member_database  = ["identity", "consent", "resume", "application", "audit"]',
            "기업 DB 소유": 'company_database = ["company", "company-profile", "job"]',
            "점수·설명 분리": "explanation_changes_score    = false",
            "독립 TRACE 서비스 없음": "independent_trace_service    = false",
            "Bedrock provider 요청값": 'bedrock_provider_requested    = var.llm_provider == "bedrock"',
            "Bedrock live 요청값": "bedrock_live_requested        = var.allow_bedrock_live",
            "이력서 객체 저장 간극": 'resume_object_storage    = "terraform-model-only-runtime-upload-not-implemented"',
        },
        errors,
    )
    require_fragments(
        api,
        "src/runtime/api/app/main.py",
        {
            "API 담당자-기업 논리 연결": '"identity_model": "recruiter-company-logical-link-no-cardinality-constraint"',
            "API 가입 시 첫 담당자 생성": '"signup_recruiter_creation": "one-recruiter-with-new-company"',
            "API 담당자 수 카디널리티 미강제": '"company_recruiter_cardinality_constraint": False',
            "API 조직 멤버십 한계": '"organization_membership_implemented": False',
            "API 초대·역할 한계": '"invite_and_role_lifecycle_implemented": False',
            "API 기업 계정 탈퇴 한계": '"company_account_withdrawal_implemented": False',
            "API 기업 소유권 이전 한계": '"company_ownership_transfer_implemented": False',
            "API 기업 동의 한계": '"company_consent_lifecycle_implemented": False',
            "API 기업 상태 전환 한계": '"company_status_transition_implemented": False',
            "API 기업 상태 행위자 한계": '"company_status_actor_modeled": False',
            "API 기업 가입 초기 상태": '"company_signup_initial_status_source": "approved-model-default-without-review-transition"',
            "API 기업 상태 게이트 한계": '"company_status_gate_enforced": False',
            "API 논리 공고 참조": '"application_job_reference": "logical_id_without_cross_database_foreign_key"',
            "API 교차 DB 원자성 한계": '"cross_database_atomic_commit": False',
            "API 가입 작업 ID 한계": '"company_signup_operation_id_implemented": False',
            "API 가입 멱등 키 한계": '"company_signup_idempotency_key_implemented": False',
            "API 교차 DB 보상 한계": '"cross_database_compensation_implemented": False',
            "API 교차 DB 사후 조정 한계": '"cross_database_reconciliation_implemented": False',
            "API 교차 DB outbox 한계": '"cross_database_outbox_implemented": False',
        },
        errors,
    )
    llm_provider_variable = terraform_variable_block(tf_variables, "llm_provider", errors)
    bedrock_live_variable = terraform_variable_block(tf_variables, "allow_bedrock_live", errors)
    require_fragments(
        llm_provider_variable,
        "terraform/asis/variables.tf::llm_provider",
        {"합성 stub 기본값": 'default     = "local-synthetic-stub"'},
        errors,
    )
    require_fragments(
        bedrock_live_variable,
        "terraform/asis/variables.tf::allow_bedrock_live",
        {"Bedrock live 기본 잠금": "default     = false"},
        errors,
    )
    database_variables = {
        name: terraform_variable_block(tf_variables, name, errors)
        for name in (
            "member_db_name",
            "company_db_name",
            "member_db_app_username",
            "company_db_app_username",
        )
    }
    for name, block in database_variables.items():
        require_fragments(
            block,
            f"terraform/asis/variables.tf::{name}",
            {"PostgreSQL 식별자 경계": 'can(regex("^[a-z][a-z0-9_]{0,62}$"'},
            errors,
        )
    member_db_default = terraform_string_default(
        database_variables["member_db_name"], "member_db_name", errors
    )
    company_db_default = terraform_string_default(
        database_variables["company_db_name"], "company_db_name", errors
    )
    member_role_default = terraform_string_default(
        database_variables["member_db_app_username"], "member_db_app_username", errors
    )
    company_role_default = terraform_string_default(
        database_variables["company_db_app_username"], "company_db_app_username", errors
    )
    if member_db_default == company_db_default:
        errors.append("terraform/asis: 회원·기업 DB 기본값이 같음")
    if member_role_default == company_role_default:
        errors.append("terraform/asis: 회원·기업 app role 기본값이 같음")
    require_fragments(
        outputs,
        "terraform/asis/outputs.tf",
        {
            "DB 이름 교차 precondition": "var.member_db_name != var.company_db_name",
            "DB role 교차 precondition": "var.member_db_app_username != var.company_db_app_username",
        },
        errors,
    )
    require_fragments(
        asis_main,
        "terraform/asis/main.tf",
        {
            "gateway 공유 task role": "llm-gateway = module.security.ecs_task_role_arn",
            "API 공유 task role": "api         = module.security.ecs_task_role_arn",
            "회원 DB URL 조합": "member_database_url    = \"postgresql+psycopg://${var.member_db_app_username}:${var.member_db_app_password}@${module.data.db_primary_endpoint}/${var.member_db_name}\"",
            "기업 DB URL 조합": "company_database_url   = \"postgresql+psycopg://${var.company_db_app_username}:${var.company_db_app_password}@${module.data.db_primary_endpoint}/${var.company_db_name}\"",
        },
        errors,
    )
    require_fragments(
        compute_locals,
        "terraform/asis/compute/locals.tf",
        {
            "web 포트": "port              = 3000",
            "API 포트": "port              = 8000",
            "agent 공개 AS-IS 경로": 'path_patterns     = ["/agent", "/agent/*"]',
            "gateway 공개 AS-IS 경로": 'path_patterns     = ["/llm", "/llm/*"]',
        },
        errors,
    )
    local_web = terraform_local_service_block(compute_locals, "web", errors)
    local_api = terraform_local_service_block(compute_locals, "api", errors)
    local_agent = terraform_local_service_block(compute_locals, "agent", errors)
    local_gateway = terraform_local_service_block(compute_locals, "llm-gateway", errors)
    for relative, block, fragments in (
        (
            "terraform/asis/compute/locals.tf::web",
            local_web,
            {"port": "port              = 3000", "route": 'path_patterns     = ["/*"]'},
        ),
        (
            "terraform/asis/compute/locals.tf::api",
            local_api,
            {"port": "port              = 8000", "route": 'path_patterns     = ["/api", "/api/*"]'},
        ),
        (
            "terraform/asis/compute/locals.tf::agent",
            local_agent,
            {"port": "port              = 8100", "route": 'path_patterns     = ["/agent", "/agent/*"]'},
        ),
        (
            "terraform/asis/compute/locals.tf::llm-gateway",
            local_gateway,
            {"port": "port              = 8200", "route": 'path_patterns     = ["/llm", "/llm/*"]'},
        ),
    ):
        require_fragments(block, relative, fragments, errors)
    require_fragments(
        data_outputs,
        "terraform/asis/data/outputs.tf",
        {
            "회원 논리 DB": "member_database         = var.member_db_name",
            "기업 논리 DB": "company_database        = var.company_db_name",
            "공유 RDS 경계": 'physical_boundary       = "shared-rds-instance"',
            "기업 DB bootstrap 간극": 'company_bootstrap       = "database-and-dedicated-app-roles-required-outside-terraform"',
            "이력서 S3 모델": 'output "resume_bucket_id"',
        },
        errors,
    )

    require_fragments(
        compute,
        "terraform/asis/compute/main.tf",
        {
            "회원 DB ECS 배선": 'name  = "MEMBER_DATABASE_URL"',
            "기업 DB ECS 배선": 'name  = "COMPANY_DATABASE_URL"',
            "matcher 산식 버전": 'name  = "SCORING_FORMULA_VERSION"',
            "설명 계약 버전": 'name  = "EXPLANATION_CONTRACT_VERSION"',
            "Bedrock 실호출 잠금": 'name  = "ALLOW_BEDROCK_LIVE"',
        },
        errors,
    )
    tf_api = terraform_service_block(compute, "api", errors)
    tf_agent = terraform_service_block(compute, "agent", errors)
    tf_gateway = terraform_service_block(compute, "llm-gateway", errors)
    require_fragments(
        tf_api,
        "terraform/asis/compute/main.tf::api",
        {
            "회원 DB": 'name  = "MEMBER_DATABASE_URL"',
            "기업 DB": 'name  = "COMPANY_DATABASE_URL"',
            "provider 표시": 'name  = "LLM_PROVIDER"',
            "Bedrock region": 'name  = "BEDROCK_REGION"',
            "Bedrock model": 'name  = "BEDROCK_MODEL_ID"',
            "gateway timeout": 'name  = "LLM_GATEWAY_TIMEOUT_SECONDS"',
        },
        errors,
    )
    require_fragments(
        tf_agent,
        "terraform/asis/compute/main.tf::agent",
        {
            "matcher version": 'name  = "MATCHER_VERSION"',
            "formula version": 'name  = "SCORING_FORMULA_VERSION"',
            "breakdown version": 'name  = "SCORE_BREAKDOWN_SCHEMA_VERSION"',
            "skills weight": 'name  = "SKILL_MAX_POINTS"',
            "experience weight": 'name  = "EXPERIENCE_MAX_POINTS"',
            "role weight": 'name  = "ROLE_MAX_POINTS"',
        },
        errors,
    )
    require_fragments(
        tf_gateway,
        "terraform/asis/compute/main.tf::llm-gateway",
        {
            "provider": 'name  = "LLM_PROVIDER"',
            "Bedrock lock": 'name  = "ALLOW_BEDROCK_LIVE"',
            "Bedrock region": 'name  = "BEDROCK_REGION"',
            "Bedrock model": 'name  = "BEDROCK_MODEL_ID"',
            "explanation version": 'name  = "EXPLANATION_CONTRACT_VERSION"',
        },
        errors,
    )
    check_wiring_declaration(
        outputs=outputs,
        compute=tf_api,
        key="service_discovery",
        env_names=("AGENT_BASE_URL", "LLM_GATEWAY_BASE_URL"),
        errors=errors,
    )
    check_wiring_declaration(
        outputs=outputs,
        compute=tf_api,
        key="redis_endpoint_injection",
        env_names=("REDIS_URL",),
        errors=errors,
    )
    check_wiring_declaration(
        outputs=outputs,
        compute=tf_api,
        key="session_key_injection",
        env_names=("SESSION_SIGNING_KEY",),
        errors=errors,
    )
    check_wiring_declaration(
        outputs=outputs,
        compute=tf_gateway,
        key="prompt_persistence",
        env_names=("PROMPT_LOG_PATH",),
        errors=errors,
    )

    invoke_state = declaration_value(outputs, "bedrock_invoke_permission", errors)
    has_invoke = bool(re.search(r"bedrock:(?:InvokeModel|InvokeModelWithResponseStream)", asis_tf))
    if invoke_state is not None and invoke_state.startswith("not-modeled") == has_invoke:
        errors.append(
            "terraform/asis: bedrock_invoke_permission 선언과 IAM action 존재 여부가 다름"
        )

    if re.search(r"\b(?:boto3|aioboto3)\b|put_object\s*\(", api):
        errors.append(
            "src/runtime/api/app/main.py: resume_object_storage는 미구현으로 선언됐지만 AWS 객체 저장 호출이 존재함"
        )

    return errors


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent).resolve()
    errors = check(root)
    print("J-Career runtime ↔ Terraform source contract (판정 아님)")
    for error in errors:
        print(f"::error::{error}")
    if errors:
        print(f"source contract mismatch: {len(errors)}")
        return 1
    web = (root / "src/runtime/web/src/App.jsx").read_text(encoding="utf-8")
    if 'path: "/recruiter/overview"' in web:
        print(
            "::warning::사람 결정: /recruiter/overview 확장은 web/API/Terraform 내부에는 "
            "정렬돼 있으나 승인된 화면 상한의 예외인지 별도 판단이 필요함"
        )
    print(
        "::warning::사람 결정: Terraform의 이력서 S3 모델과 DB-only runtime upload 간극은 "
        "유지·구현 범위를 별도 확정해야 함"
    )
    print(
        "::warning::사람 결정: 양면 관찰 실행의 합성 DB 레코드와 해당 cache key는 정리하지만 "
        "raw prompt log line은 AS-IS 보존 관찰면에 남음"
    )
    print("지원자·기업 소스 표면, 데이터 소유, 서비스별 배선 선언의 정적 대조 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
