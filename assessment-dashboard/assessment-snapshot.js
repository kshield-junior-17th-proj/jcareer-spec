window.JCAREER_ASSESSMENT = Object.freeze({
  meta: {
    framework: "NIST AI RMF",
    snapshotDate: "2026-09-05",
    status: "WORKING_DRAFT_HUMAN_REVIEW_PENDING",
    scope: "DESIGN_REVIEW_AND_ISOLATED_LAB_SAMPLING",
    targetStatus: "UNVERIFIED_TARGET",
    actualAfterStatus: "NOT_MEASURED_NO_ACCEPTED_REVALIDATION",
    deploymentStatus: "NOT_DEPLOYED",
    projectControlIds: "PROJECT_T_ID_NOT_NIST_CONTROL_ID"
  },
  metrics: { assets: 22, controls: 27, findings: 6, evidence: "4/13/6/4", pocResult: "3/2" },
  traceability: {
    source: "JCAREER_PROJECT_TECHNICAL_CHECKLIST_27",
    sourceBinding: {
      sourceArtifact: "JCAREER_MAP_SOURCE_WORKBOOK_20260905",
      sourceSha256: "60157ee6fe5ee4c03b725b94f114453b8affe6caf4e1371157781f6348102788",
      mappedArtifact: "JCAREER_MAP_D_TO_J_WORKBOOK_20260905",
      mappedSha256: "ab0219ac683e7da36393976322627703dd9ab628dd7a9bb791a5b5faf395c68e",
      status: "EXTERNAL_SNAPSHOT_DIGEST_HUMAN_REVIEW_PENDING"
    },
    namespace: "PROJECT_T_ID_NOT_NIST_CONTROL_ID",
    findingNamespace: "PRESENTATION_GROUP_NOT_PERSISTENT_FINDING_ID",
    chain: ["CHECKLIST", "FINDING", "REMEDIATION", "UNVERIFIED_TARGET", "HUMAN_REVALIDATION"],
    currentStage: "REMEDIATION_OPEN_UNVERIFIED"
  },
  evidence: [
    { code: "OBSERVED_ADVERSE_BEHAVIOR", label: "취약 동작 관찰", count: 4, tone: "critical" },
    { code: "PARTIALLY_OBSERVED", label: "부분 관찰", count: 13, tone: "warning" },
    { code: "DESIGN_EVIDENCE_ONLY", label: "설계 근거 확보", count: 6, tone: "positive" },
    { code: "EVIDENCE_GAP", label: "검증 공백", count: 4, tone: "neutral" }
  ],
  checklistItems: [
    { id: "T.1.1", findingId: "NF-03", evidenceClass: "OBSERVED_ADVERSE_BEHAVIOR" },
    { id: "T.1.2", findingId: "NF-03", evidenceClass: "PARTIALLY_OBSERVED" },
    { id: "T.1.3", findingId: "NF-03", evidenceClass: "PARTIALLY_OBSERVED" },
    { id: "T.2.1", findingId: "NF-02", evidenceClass: "EVIDENCE_GAP" },
    { id: "T.2.2", findingId: "NF-02", evidenceClass: "EVIDENCE_GAP" },
    { id: "T.2.3", findingId: "NF-02", evidenceClass: "EVIDENCE_GAP" },
    { id: "T.3.1", findingId: "NF-05", evidenceClass: "OBSERVED_ADVERSE_BEHAVIOR" },
    { id: "T.3.2", findingId: "NF-05", evidenceClass: "PARTIALLY_OBSERVED" },
    { id: "T.3.3", findingId: "NF-05", evidenceClass: "PARTIALLY_OBSERVED" },
    { id: "T.4.1", findingId: "NF-05", evidenceClass: "PARTIALLY_OBSERVED" },
    { id: "T.4.2", findingId: "NF-05", evidenceClass: "DESIGN_EVIDENCE_ONLY" },
    { id: "T.4.3", findingId: "NF-01", evidenceClass: "PARTIALLY_OBSERVED" },
    { id: "T.5.1", findingId: "NF-01", evidenceClass: "PARTIALLY_OBSERVED" },
    { id: "T.5.2", findingId: "NF-06", evidenceClass: "PARTIALLY_OBSERVED" },
    { id: "T.5.3", findingId: "NF-02", evidenceClass: "PARTIALLY_OBSERVED" },
    { id: "T.5.4", findingId: "NF-03", evidenceClass: "DESIGN_EVIDENCE_ONLY" },
    { id: "T.6.1", findingId: "NF-06", evidenceClass: "PARTIALLY_OBSERVED" },
    { id: "T.6.2", findingId: "NF-06", evidenceClass: "PARTIALLY_OBSERVED" },
    { id: "T.7.1", findingId: "NF-04", evidenceClass: "OBSERVED_ADVERSE_BEHAVIOR" },
    { id: "T.7.2", findingId: "NF-04", evidenceClass: "OBSERVED_ADVERSE_BEHAVIOR" },
    { id: "T.7.3", findingId: "NF-01", evidenceClass: "PARTIALLY_OBSERVED" },
    { id: "T.8.1", findingId: "NF-05", evidenceClass: "DESIGN_EVIDENCE_ONLY" },
    { id: "T.8.2", findingId: "NF-05", evidenceClass: "EVIDENCE_GAP" },
    { id: "T.8.3", findingId: "NF-02", evidenceClass: "DESIGN_EVIDENCE_ONLY" },
    { id: "T.9.1", findingId: "NF-04", evidenceClass: "DESIGN_EVIDENCE_ONLY" },
    { id: "T.9.2", findingId: "NF-04", evidenceClass: "DESIGN_EVIDENCE_ONLY" },
    { id: "T.9.3", findingId: "NF-04", evidenceClass: "PARTIALLY_OBSERVED" }
  ],
  radar: {
    scale: 4,
    labels: ["판정 책임·감독", "데이터·공정성", "입력·프롬프트", "점수·출력 신뢰", "접근·공급망", "복구·지속 운영"],
    baseline: [2.0, 0.6, 1.25, 0.8, 1.14, 2.0],
    targetProjection: [4.0, 4.0, 4.0, 4.0, 4.0, 4.0],
    actualAfter: null,
    actualAfterStatus: "NOT_MEASURED_NO_ACCEPTED_REVALIDATION",
    note: "DISPLAY_INDEX_WORKING_MODEL_NOT_COMPLIANCE_SCORE"
  },
  findings: [
    {
      id: "NF-01", priority: "P0", title: "판정 책임·변경 승인·사람 감독의 운영효과성 미확정",
      asset: "AI 추천 서비스 · Serverless MLOps · 승인 기록",
      controls: ["T.4.3", "T.5.1", "T.7.3"],
      scenario: "기준과 변경이 동일 책임선 안에서 승인되면 독립 검토와 예외 만료 없이 AI 결과가 업무 판단으로 승격될 수 있습니다.",
      evidenceGradeCounts: { PARTIALLY_OBSERVED: 3 },
      evidence: "부분 관찰 3건 · 승인·면책 경계",
      remediation: { state: "OPEN_UNVERIFIED", targetStatus: "UNVERIFIED_TARGET", action: "기준·승인자·예외 만료 동결 · distinct-human 승인", verificationGate: "실제 화면과 변경에서 서로 다른 사람의 승인·재검토 이력 결속" }
    },
    {
      id: "NF-02", priority: "P1", title: "개인정보·보존·편향·교차주체 격리의 비위험 상태 미입증",
      asset: "LLM Gateway · 증적 저장소 · 주체별 데이터 경계",
      controls: ["T.2.1", "T.2.2", "T.2.3", "T.5.3", "T.8.3"],
      scenario: "민감정보가 전송·로그·증적에 남거나 서로 다른 주체 사이에 혼입되고도 탐지되지 않을 수 있습니다.",
      evidenceGradeCounts: { EVIDENCE_GAP: 3, PARTIALLY_OBSERVED: 1, DESIGN_EVIDENCE_ONLY: 1 },
      evidence: "공백 3 · 부분 1 · 설계 1 · LLM02 검증 공백",
      remediation: { state: "OPEN_UNVERIFIED", targetStatus: "UNVERIFIED_TARGET", action: "합성 canary · 양방향 DLP · 삭제 전파 · 격리·편향 기준", verificationGate: "전송 전후 비도달·삭제 후 재조회 거부·교차주체 비혼입을 한 묶음으로 확인" }
    },
    {
      id: "NF-03", priority: "P1", title: "비신뢰 입력이 지시·점수 경계에 영향을 준 행동 관찰",
      asset: "AI 추천 API · LLM Gateway · 추천 점수 로직",
      controls: ["T.1.1", "T.1.2", "T.1.3", "T.5.4"],
      scenario: "데이터로 취급해야 할 입력이 지시문으로 승격되어 추천 점수와 후속 업무 문맥을 오염시킬 수 있습니다.",
      evidenceGradeCounts: { OBSERVED_ADVERSE_BEHAVIOR: 1, PARTIALLY_OBSERVED: 2, DESIGN_EVIDENCE_ONLY: 1 },
      evidence: "취약 동작 1 · 부분 2 · 설계 1 · LLM01 관찰 실패",
      remediation: { state: "OPEN_UNVERIFIED", targetStatus: "UNVERIFIED_TARGET", action: "서버 스키마 · 명령/데이터 분리 · 점수 불변 · 거부 로그", verificationGate: "동일 합성 입력을 거부하고 점수 불변·미저장·재실행 결과 결속" }
    },
    {
      id: "NF-04", priority: "P1", title: "채용 결론·실행형 출력·저장 무결성의 종단 검증 불완전",
      asset: "추천 서비스 · API 응답 렌더러 · Evidence Desk",
      controls: ["T.7.1", "T.7.2", "T.9.1", "T.9.2", "T.9.3"],
      scenario: "근거 없는 채용 결론이나 실행 가능한 마크업이 전달되고 점수·사유·저장 내용이 불일치할 수 있습니다.",
      evidenceGradeCounts: { OBSERVED_ADVERSE_BEHAVIOR: 2, DESIGN_EVIDENCE_ONLY: 2, PARTIALLY_OBSERVED: 1 },
      evidence: "취약 동작 2 · 설계 2 · 부분 1 · LLM07/LLM10",
      remediation: { state: "OPEN_UNVERIFIED", targetStatus: "UNVERIFIED_TARGET", action: "근거 없는 결론 보류 · 구조화 출력 · 무해화 · 변조 탐지", verificationGate: "점수-사유 불일치 거부·일반 텍스트 렌더·변조 후 읽기 거부와 복구" }
    },
    {
      id: "NF-05", priority: "P0", title: "역할·공급망·민감정보 경계의 비허용 거부 미검증",
      asset: "IAM · Capability Broker · GitHub Actions · LLM Gateway",
      controls: ["T.3.1", "T.3.2", "T.3.3", "T.4.1", "T.4.2", "T.8.1", "T.8.2"],
      scenario: "허용 경로만 확인하고 거부 경계를 시험하지 않으면 권한 우회·변경 오염·숨은 기준 노출을 놓칠 수 있습니다.",
      evidenceGradeCounts: { OBSERVED_ADVERSE_BEHAVIOR: 1, PARTIALLY_OBSERVED: 3, DESIGN_EVIDENCE_ONLY: 2, EVIDENCE_GAP: 1 },
      evidence: "취약 1 · 부분 3 · 설계 2 · 공백 1",
      remediation: { state: "OPEN_UNVERIFIED", targetStatus: "UNVERIFIED_TARGET", action: "cross-role deny · capability default-deny · 구성·의존성 차단 · secret canary", verificationGate: "403/비허용 capability 거부·검사 차단·합성 비밀 비도달" }
    },
    {
      id: "NF-06", priority: "P2", title: "복구·고비용 경로 제한·주체별 사용량 관찰은 부분적",
      asset: "API Gateway · SQS · Bedrock · Serverless MLOps",
      controls: ["T.5.2", "T.6.1", "T.6.2"],
      scenario: "반복·대량 요청과 변경 실패가 비용 증가·큐 적체·서비스 복구 실패로 이어질 수 있습니다.",
      evidenceGradeCounts: { PARTIALLY_OBSERVED: 3 },
      evidence: "부분 관찰 3 · 제한된 속도/rollback 관찰",
      remediation: { state: "OPEN_UNVERIFIED", targetStatus: "UNVERIFIED_TARGET", action: "주체별 quota · 계량·경보 · backpressure · exact-digest rollback", verificationGate: "실제 경로 한도·차단·주체별 경보·데이터 변조 탐지와 정확한 복구" }
    }
  ],
  roadmap: [
    { phase: "P0", window: "0–2주", title: "판정 무결성", body: "원본·시점·환경·분모 동결, 충돌의 사람 결정", deliverable: "증거 계약 · 책임자 · 예외 만료" },
    { phase: "P1", window: "2–6주", title: "측정 가능성", body: "canary, cross-role deny, 삭제·격리 positive/negative oracle", deliverable: "재현 세트 · owner · receipt 결속" },
    { phase: "P2", window: "6주–3개월", title: "예방 통제", body: "서버 검증, redaction, default-deny, 구조화 출력", deliverable: "UNVERIFIED_TARGET IaC · 정책팩 · 공격 회귀" },
    { phase: "P3", window: "3–6개월", title: "지속 보증", body: "릴리스별 drift·예외 만료·재검증·독립 승인", deliverable: "재진단 · 잔여위험 owner · 기한" }
  ],
  deployment: {
    currentSurface: "GITHUB_PAGES_PUBLIC_SPEC_REFERENCE",
    targetSurface: "AWS_ISOLATED_STATIC_S3_CLOUDFRONT_WAF",
    status: "NOT_DEPLOYED",
    githubPagesRelationship: "SEPARATE_PUBLIC_SPEC_REFERENCE_ONLY",
    actualAfterStatus: "NOT_MEASURED_NO_ACCEPTED_REVALIDATION",
    requiredGates: [
      { id: "DG-01", label: "보안·비용·메타데이터 범위 사람 승인" },
      { id: "DG-02", label: "bootstrap operator·reviewer·deployment actor 상호 분리" },
      { id: "DG-03", label: "main 전용 protected environment·self-review·admin bypass 차단" },
      { id: "DG-04", label: "보호 변수와 bootstrap approval digest 결속" },
      { id: "DG-05", label: "current main 수동 dispatch와 별도 environment reviewer 승인" },
      { id: "DG-06", label: "CloudFront 무효화 후 HTTPS/content smoke와 별도 운영 검증" }
    ]
  }
});
