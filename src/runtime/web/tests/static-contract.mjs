import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const app = readFileSync(resolve(webRoot, "src/App.jsx"), "utf8");
const main = readFileSync(resolve(webRoot, "src/main.jsx"), "utf8");
const css = readFileSync(resolve(webRoot, "src/styles.css"), "utf8").replace(/\r\n/g, "\n");
const index = readFileSync(resolve(webRoot, "index.html"), "utf8");
const api = readFileSync(resolve(webRoot, "../api/app/main.py"), "utf8");
const openDart = readFileSync(resolve(webRoot, "../api/app/opendart.py"), "utf8");
const observation = readFileSync(resolve(webRoot, "../tests/two_sided_asis_observations.py"), "utf8");
const clientApi = readFileSync(resolve(webRoot, "src/api.js"), "utf8");
const candidateWorkspace = readFileSync(resolve(webRoot, "src/candidate-workspace.jsx"), "utf8");
const recruiterEvidence = readFileSync(resolve(webRoot, "src/recruiter-evidence.js"), "utf8");

const between = (start, end) => {
  const from = app.indexOf(start);
  const to = app.indexOf(end, from + start.length);
  return from >= 0 && to > from ? app.slice(from, to) : "";
};
const candidateRecommendations = between(
  "function CandidateRecommendationsPage()",
  "function WithdrawPage()"
);
const recruiterRecommendations = between(
  "function RecruiterRecommendationsPage()",
  "function AdminAuditPage()"
);
const recommendationPages = [candidateRecommendations, recruiterRecommendations];
const consentPage = between("function ConsentPage()", "const blankResume");
const resumeContract = between("const blankResume", "function CandidateApplicationsPage()");
const withdrawPage = between("function WithdrawPage()", "function RecruiterSignupPage()");
const pipelineSurface = between("function CandidateRecordDetails", "function RecruiterRecommendationsPage()");
const adminAuditPage = between("function AdminAuditPage()", "function LegalPage");
const legalPage = between("function LegalPage", "function NotFoundPage()");
const authProvider = between("function AuthProvider({ children })", "function useAuth()");
const shell = between("function Shell({ children })", "function ErrorNotice");
const sessionNotice = between("function SessionNotice", "function ConsentRecovery");
const loginPage = between("function LoginPage()", "function SignupPage()");
const signupPage = between("function SignupPage()", "function ConsentPage()");
const recruiterSignupPage = between("function RecruiterSignupPage()", "const blankJob");
const inOrder = (source, markers) => {
  let cursor = -1;
  return markers.every((marker) => {
    cursor = source.indexOf(marker, cursor + 1);
    return cursor >= 0;
  });
};

const required = [
  [recruiterEvidence.includes("export function isValidRecruiterEvidenceClaim")
    && recruiterEvidence.includes('claim.score_effect !== "NONE"')
    && recruiterEvidence.includes('claim.support_state !== "DIRECT_TEXT_EVIDENCE"')
    && recruiterEvidence.includes("exactObjectKeys(claim, CLAIM_KEYS)"), "cached recruiter evidence validator source keeps exact shape and no-score boundaries"],
  [app.includes("function OpenDartCompanyFacts") && app.includes("OpenDART 공개 기업정보") && app.includes("추천 점수·정렬·기업 적합성 판단에는 사용하지 않습니다") && app.includes("function OpenDartProfileEditor"), "OpenDART facts remain a separate candidate and recruiter profile surface"],
  [api.includes('/api/v1/recruiter/company-profile/opendart/refresh') && api.includes('include_opendart_linkage=True') && openDart.includes('mode: str = "fixture"') && openDart.includes('"score_effect": "NONE"') && openDart.includes("follow_redirects=False"), "OpenDART uses explicit tenant refresh, synthetic default, score separation, and fixed-host request policy"],
  [openDart.includes("def public_snapshot") && openDart.includes("SENSITIVE") === false && !app.includes("ceo_nm") && !app.includes("jurir_no") && !app.includes("bizr_no"), "OpenDART UI excludes representative and registration identifiers"],
  [app.includes('candidate: "/candidate/home"') && app.includes('["나의 홈", "/candidate/home"]') && app.includes('path: "/candidate/home"'), "candidate command center is the authenticated home"],
  [candidateWorkspace.includes("Promise.allSettled") && candidateWorkspace.includes('api("/api/v1/candidates/me/resume")') && candidateWorkspace.includes('api("/api/v1/candidates/me/applications")') && candidateWorkspace.includes('api("/api/v1/candidates/me/consents")') && candidateWorkspace.includes("일부 정보를 불러오지 못했습니다"), "candidate command center composes three existing APIs with partial-failure disclosure"],
  [candidateWorkspace.includes("추천 점수가 아닌 5개 구조화 입력의 진행률") && candidateWorkspace.includes("합격 가능성이나 선발 결론이 아닙니다") && !candidateWorkspace.includes('api("/api/v1/candidates/me/recommendations")'), "candidate home avoids silent recommendation generation and separates profile progress from hiring outcomes"],
  [candidateWorkspace.includes('aria-label="현재 점수 모델 요약"') && candidateWorkspace.includes("결정론적 매처가 점수와 순서를 계산합니다") && candidateWorkspace.includes("생성형 설명은 별도 계층"), "candidate command center preserves matcher and generated-explanation boundaries"],
  [app.includes("current.length < 3") && app.includes("<CandidateJobComparison") && candidateWorkspace.includes('scope="row"') && candidateWorkspace.includes('scope="col"') && candidateWorkspace.includes("비교 선택은 이 브라우저 화면에만 임시로 유지됩니다"), "candidate comparison is capped, tabular, and explicitly session-local"],
  [css.includes("touch-action: manipulation") && css.includes(".candidate-command-hero") && css.includes(".candidate-vitals") && css.includes(".candidate-job-comparison") && css.includes("@media (prefers-reduced-motion: reduce)"), "candidate workspace includes touch, responsive, and reduced-motion foundations"],
  [api.includes("cast(Job.required_skills, String).ilike(like)"), "required-skills search"],
  [app.includes('!user && <NavLink to="/recruiter/signup"'), "public enterprise entry"],
  [app.includes("function JobActionPanel"), "role-aware job action"],
  [app.includes("pageLocation.state?.notice"), "withdrawal completion notice"],
  [app.includes("function CacheObservation") && app.includes("결과 새로 불러오기"), "cache reload wording"],
  [app.includes("현재 이력서 자료 펼쳐 보기") && app.includes("지원 시점 스냅샷은 아닙니다"), "current resume boundary"],
  [app.includes("draftStatuses") && app.includes("saveStatus(item.id, selectedStatus"), "staged status edit"],
  [app.includes("<SuccessNotice>{statusMessage}</SuccessNotice>") && app.includes("?.focus()"), "status feedback and focus restore"],
  [css.includes(".pipeline-card-grid") && css.includes("@media (max-width: 680px)"), "responsive pipeline cards"],
  [app.includes("기본 비활성화된 Bedrock 외부 호출 모드"), "provider boundary wording"],
  [app.includes('className="boundary-facts"') && app.includes("data.customer_boundary.identity_model") && app.includes("data.customer_boundary.signup_recruiter_creation") && app.includes("data.customer_boundary.company_recruiter_cardinality_constraint") && app.includes("data.customer_boundary.company_signup_initial_status_source") && app.includes("소스 상태 · 모델 기본값") && app.includes("별도 검토 전환 없음") && app.includes("data.customer_boundary.company_status_gate_enforced") && app.includes("data.customer_boundary.company_account_withdrawal_implemented") && app.includes("data.customer_boundary.company_ownership_transfer_implemented") && app.includes("data.customer_boundary.company_consent_lifecycle_implemented") && app.includes("data.data_boundary.company_signup_operation_id_implemented") && app.includes("data.data_boundary.company_signup_idempotency_key_implemented") && app.includes("data.data_boundary.cross_database_compensation_implemented") && app.includes("data.data_boundary.cross_database_reconciliation_implemented") && app.includes("data.data_boundary.cross_database_outbox_implemented") && app.includes("다른 저장소·절차의 부재") && app.includes("충분성을 판정하지 않습니다") && css.includes(".boundary-facts { margin: 0; display: grid") && css.includes(".boundary-facts .boundary-span { grid-column: auto; }"), "semantic responsive enterprise account continuity and cross-store boundary"],
  [index.includes('rel="icon" href="/favicon.svg"') && existsSync(resolve(webRoot, "public/favicon.svg")), "favicon asset"],
  [app.includes("function routeTitle") && app.includes('pathname === "/privacy"') && app.includes("if (job?.title) document.title"), "route and dynamic document titles"],
  [app.includes("error ? null : jobs.length") && app.includes("<ErrorNotice error={error} onRetry={() => load(query, location)} />"), "exclusive jobs error state"],
  [app.includes("검증 상태 확인 필요") && app.includes('<span className="verify-badge">{validationLabel}</span>'), "fail-closed explanation validation label"],
  [app.includes("function ConsentRecovery") && app.includes("safeConsentReturnTo") && app.includes("동의 계속하기") && app.includes("resumeDraft"), "return-aware consent recovery with in-memory resume draft"],
  [app.includes("editorToggleRef") && app.includes("firstEditorFieldRef") && app.includes("<SuccessNotice>{message}</SuccessNotice>"), "job editor focus and success feedback"],
  [observation.includes('request("/llm/health")') && observation.includes('gateway["provider"] == "local-synthetic-stub"') && observation.includes('gateway["raw_prompt_log_enabled"] == "true"') && observation.includes('gateway["bedrock_live_enabled"] == "false"'), "stub-only observation scenario guard"],
  [app.includes("if (loadError) return") && app.includes("기존 이력서를 확인하지 못해 편집을 중단했습니다"), "resume load failure blocks empty editor"],
  [app.includes("function useUnsavedChanges") && app.includes("useBlocker(shouldBlock)") && app.includes("useBeforeUnload") && app.includes("createBrowserRouter") && main.includes("<App />"), "router and browser unsaved form exit warnings"],
  [app.includes('eyebrow="Job not available"') && app.includes("<ErrorNotice error={error} /><EmptyState"), "job detail failure live alert"],
  [app.includes("if (editorDirty && !window.confirm") && app.includes("다른 공고를 열까요"), "dirty job editor switch guard"],
  [app.includes("function useRequestEpoch") && app.includes("const isCurrent = beginRequest()"), "late request generation guard"],
  [app.includes('allowNextNavigation("/signup/consent")') && app.includes("onContinue?.()"), "atomic consent draft navigation"],
  [app.includes("이 공고의 편집기를 닫거나 변경 내용을 저장한 뒤") && app.includes("statusBusyId === job.id"), "job edit and status race guard"],
  [clientApi.includes('window.dispatchEvent(new Event("jcareer:unauthorized"))') && app.includes('allowNextNavigation("/login")'), "central unauthorized navigation source markers"],
  [clientApi.includes("export async function decodeResponsePayload") && clientApi.includes('"RESPONSE_BODY_READ_FAILED"') && clientApi.includes('"EMPTY_RESPONSE_BODY"') && clientApi.includes('"INVALID_JSON_RESPONSE"') && !clientApi.includes("await response.json()") && inOrder(clientApi, ['readStoredToken() === token', "decodeResponsePayload(response)"]), "current-token 401 signaling precedes bounded response decoding and malformed bodies become safe ApiError metadata"],
  [clientApi.includes("DEFAULT_REQUEST_TIMEOUT_MS") && clientApi.includes('error_code: "REQUEST_TIMEOUT"') && clientApi.includes('error_code: "REQUEST_ABORTED"') && clientApi.includes('error_code: "NETWORK_UNAVAILABLE"'), "API requests have bounded timeout, caller cancellation, and sanitized network errors"],
  [css.includes("min-height: 100dvh") && css.includes(".jobs-hero .search-panel :focus-visible") && css.includes(".button.small { min-height: 44px; }"), "mobile viewport touch and focus visibility"],
  [app.includes("const searchKey = searchParams.toString()") && app.includes("else setSearchParams(params)") && app.includes("new URLSearchParams(searchKey)") && app.includes('aria-live="polite" aria-atomic="true"'), "bidirectional search URL state and live result count"],
  [app.includes('const authLayoutPaths = new Set(["/login", "/signup", "/recruiter/signup"])') && app.includes("const isAuthLayoutRoute = authLayoutPaths.has(normalizedPath)") && app.includes('{!isAuthLayoutRoute && <header className="topbar">') && app.includes('{!isAuthLayoutRoute && <footer className="footer">') && !css.includes(".auth-layout + .footer"), "auth layouts avoid duplicate global chrome"],
  [app.includes("loadConsentState") && app.includes('latestCore?.action === "grant"') && app.includes("필수 동의는 기록됐지만 선택 동의 기록에 실패했습니다") && app.includes("coreRecorded || consentStateLoading"), "persisted core consent prevents duplicate grant events"],
  [app.includes("검증되지 않은 생성 설명 원문 보기") && app.includes("이 생성 설명은 의미 검증을 거치지 않았습니다") && css.includes(".generated-explanation"), "unvalidated generated explanation is collapsed and warned"],
  [app.includes("function clearStoredSession") && app.includes("function readStoredSession") && app.includes("function writeStoredSession") && app.includes("incomplete local session"), "partial or unavailable local auth storage follows the declared source-state branch"],
  [app.includes('if (!token && !storedUser) return { user: null, notice: "" }') && authProvider.includes('const [sessionNotice, setSessionNotice] = useState("")') && authProvider.includes("if (initialSession.notice)") && authProvider.includes("initialSession.clearStored") && authProvider.includes("const cleared = clearStoredSession()") && app.includes("저장된 로그인 정보를 확인할 수 없어 다시 로그인이 필요합니다") && app.includes("이 브라우저에 저장된 로그인 정보를 삭제했습니다") && app.includes("브라우저 저장소에서 로그인 정보 삭제 여부를 확인하지 못했습니다") && sessionNotice.includes('className="sr-only" role="status" aria-live="polite"') && sessionNotice.includes('aria-hidden="true"') && sessionNotice.includes('aria-label="로그인 상태 안내 닫기"') && shell.includes("dismissSessionNotice") && shell.includes("target?.focus({ preventScroll: true })") && app.includes('logout("")') && css.includes(".notice.session") && css.includes(".session-notice-wrap"), "session recovery and local logout feedback remain truthful, announced, dismissible, and focus-safe"],
  [loginPage.includes('<form className="stack-form" onSubmit={submit} aria-busy={busy}>') && inOrder(loginPage, ['</form>', "로그인 요청을 처리하고 있습니다", 'className="demo-logins"']) && loginPage.includes('<button type="submit" className="button full" disabled={busy}>') && loginPage.includes('<button type="button" key={email} className="demo-login" disabled={busy}'), "login request exposes a live status outside its busy form and prevents duplicate demo submission"],
  [[signupPage, recruiterSignupPage].every((source) => source.includes('<form className="stack-form" onSubmit={submit} aria-busy={busy}>') && source.includes('spellCheck={false}') && source.includes('minLength={3} maxLength={254}') && source.includes('minLength={8} maxLength={128}') && inOrder(source, ['</form>', 'role="status" aria-live="polite"'])) && signupPage.includes('minLength={2} maxLength={100}') && recruiterSignupPage.includes('minLength={2} maxLength={120}') && recruiterSignupPage.includes('minLength={2} maxLength={240}') && [signupPage, recruiterSignupPage].every((source) => source.includes('<button type="submit" className="button full" disabled={busy}>')), "candidate and recruiter signup forms align API lengths and announce busy state outside the form"],
  [app.includes('api("/api/v1/candidates/me/consents")') && app.includes('revoke("marketing")') && app.includes("marketingGranted"), "marketing consent status and withdrawal are reachable"],
  [app.includes("errorAction") && app.includes("retryFailedAction") && app.includes("기록된 필수 동의 이벤트가 없습니다"), "consent load and action failures remain distinguishable"],
  [app.includes("function RecommendationLoadStatus") && recommendationPages.every((source) => source.includes("aria-busy={loading && !data}")) && app.includes("조건 일치 결과가 준비되었습니다") && app.includes('disabled={loading} onClick={() => load()}'), "recommendation completion and request epoch prevent stale UI commits"],
  [css.includes(".text-button { min-height: 44px") && css.includes(".generated-explanation summary { min-height: 44px") && css.includes('.generated-explanation[open] summary::after { content: "−"; }'), "text and disclosure controls expose consistent touch targets"],
  [css.includes("scroll-behavior: smooth") && css.includes("text-wrap: balance") && css.includes(".job-card:hover, .job-card:focus-within") && css.includes(".recent-job-grid article:focus-within"), "typography, link navigation, and keyboard card polish"],
  [app.includes('<button type="button" className="text-button" onClick={onRetry}>') && app.includes('<time dateTime={item.applied_at}>') && app.includes('<ErrorNotice error={error} onRetry={load} />'), "retry controls and application dates retain accessible semantics"],
  [app.includes("이 점수의 우선요인") && app.includes("기업별 가중치나 가산점 정책은 적용되지 않았습니다") && css.includes(".score-policy-summary"), "score priority summary distinguishes platform defaults from company policy"],
  [app.includes('className="pipeline-list" role="list"') && app.includes('role="listitem" aria-labelledby={`candidate-${item.id}`}') && app.includes('aria-hidden="true">공고 보기') && css.includes('.job-card .arrow-link[aria-hidden="true"] { pointer-events: none; }'), "pipeline card names and single job-card tab stop without a dead click zone"],
  [app.includes('className="explanation-unavailable" role="note"') && app.includes('className="explanation-warning" role="note"') && app.includes("unavailableCount"), "recommendation degradation is announced once rather than once per card"],
  [app.includes("const [loadError, setLoadError]") && app.includes("const [actionError, setActionError]") && app.includes("const refreshed = await load()"), "enterprise job list and mutation failures remain distinct and awaited"],
  [css.includes(":where(\n  .chips,") && css.includes(".chip, .value-chip { white-space: normal; word-break: break-word; }"), "long unbroken customer content wraps on narrow screens"],
  [recommendationPages.every((source) => source.includes("preserve = true") && source.includes("if (!preserve) setData(null)") && source.includes("loading && data") && source.includes("loading && !data") && source.includes("error && data") && source.includes('role="status" aria-live="polite" aria-atomic="true">갱신에 실패해 직전 성공 결과를 유지하고 있습니다')), "recommendation refresh retains loaded results and announces stale fallback"],
  [app.includes("function ResumeRecovery") && app.includes('to="/candidate/resume">이력서 작성하기') && candidateRecommendations.includes("const resumeRequired") && candidateRecommendations.includes("<ResumeRecovery error={error} />") && candidateRecommendations.includes("resumeRequired ? undefined"), "candidate resume prerequisite recovery"],
  [candidateRecommendations.includes("현재 응답에 열린 공고가 없습니다") && candidateRecommendations.includes("캐시 생성 당시의 공고 집합") && candidateRecommendations.includes("이력서 내용 부족을 뜻하지 않습니다"), "candidate no-open-job empty state"],
  [app.includes("function RecommendationMeta") && app.includes('AVAILABLE: "설명 제공됨"') && app.includes('UNAVAILABLE_PROVIDER: "설명 생성 불가"') && app.includes('hit: "캐시 응답"') && app.includes('miss: "새로 계산한 응답"') && recommendationPages.every((source) => source.includes("<RecommendationMeta data={data} />")), "localized recommendation metadata"],
  [recommendationPages.every((source) => source.indexOf("<RecommendationMeta data={data} />") < source.indexOf("data?.items?.length")) && recruiterRecommendations.includes('audience="recruiter"') && recruiterRecommendations.includes("캐시 생성 당시 조회된 지원자 집합") && recruiterRecommendations.includes("현재 지원자가 없다는 단정은 아닙니다"), "recommendation metadata and stale-cache boundary remain visible for empty results"],
  [recruiterRecommendations.includes("이 공고에 지원한 활성 지원자만 표시") && recruiterRecommendations.includes("전체 인재 데이터베이스 검색 아님") && recruiterRecommendations.includes("화면 필터는 서버가 준 순서를 바꾸지 않음"), "recruiter talent workbench keeps the applied-candidate scope visible"],
  [app.includes("function CandidateComparison") && recruiterRecommendations.includes("current.length < 3") && app.includes("화면 안에서만 유지") && app.includes("저장·공유하거나 선발 결정을 기록하지 않습니다"), "temporary comparison is capped and non-persistent"],
  [app.includes("function RecruiterEvidenceReview") && recruiterRecommendations.includes("<RecruiterEvidenceReview reviewSupport={item.recruiter_review_support}") && app.includes("recruiter-evidence-review-v1") && app.includes("candidate_source_material_review") && app.includes("점수·추천 순서 반영 없음") && app.includes("캐시 응답이면 생성 당시 자료") && css.includes(".recruiter-evidence-review"), "recruiter literal evidence review remains separate, non-evaluative, and cache-bounded"],
  [recruiterRecommendations.includes("visibleItems.map(({ item, index })") && recruiterRecommendations.includes("이름·직무·기술") && recruiterRecommendations.includes("최소 표시 점수") && recruiterRecommendations.includes("새 후보를 찾거나 점수를 다시 계산하지 않습니다"), "client-only recruiter filters preserve server ranking semantics"],
  [app.includes("prepared_field_set_state") && app.includes("CACHE_ORIGIN_FIELD_SET_NOT_VERIFIED") && app.includes("현재 캐시 응답 구조로 검증되지 않습니다") && app.includes("이번 조회에서 해당 필드를 다시 준비하거나 외부 공급자가 수신했다는 뜻도 아닙니다") && app.includes("candidate_fields_prepared") && app.includes("외부 공급자의 실제 수신을 뜻하지 않습니다") && recommendationPages.every((source) => source.includes("explanationAttempt={data.explanation_attempt}")), "provider-independent current-versus-cache explanation preparation disclosure"],
  [app.includes("CACHE_HIT_PROVIDER_NOT_REVALIDATED") && app.includes("설명 공급자 상태도 이번 요청에서 다시 확인하지 않았습니다"), "warm cache provider state boundary"],
  [app.includes("function ProfileSource") && app.includes("synthetic_recruiter_declared") && app.includes("profileSource={item.job.company_profile?.source}") && app.includes("profileSource={data.job?.company_profile?.source}") && app.includes("기업 방향 프로필에 저장된 합성 선언") && css.includes(".profile-source"), "company profile provenance remains visible across customer views"],
  [app.includes("successLinkRef") && app.includes("ref={successLinkRef}") && app.includes('document.getElementById(`job-status-${job.id}`)?.focus()') && app.includes("setJobs((current) => current?.map"), "application and job-status mutations restore focus without clearing the list"],
  [app.includes('aria-label={`${job.title} 지원자 파이프라인 보기`}') && app.includes('aria-label={`${job.title} 공고 수정`}') && app.includes('aria-label={`${item.candidate.display_name} 전형 상태 변경 저장`}'), "repeated enterprise actions include record names"],
  [app.includes('className="auth-promo-title"') && app.includes('aria-label="J-Career 채용공고 홈"') && app.includes('className="brand-mark" aria-hidden="true"') && !app.includes(".auth-aside h2"), "auth layout avoids heading inversion and duplicate brand mark speech"],
  [app.indexOf("실제 지원자·기업 정보 입력 금지") < app.indexOf("AS-IS 재현환경") && css.includes(".environment-strip span:first-child { flex-basis: 100%; }"), "mobile environment boundary exposes the no-real-data warning first"],
  [consentPage.includes("const [marketingRecorded, setMarketingRecorded]") && consentPage.includes('latestMarketing?.action === "grant"') && consentPage.includes("setMarketing(marketingAlreadyGranted)") && consentPage.includes("marketing && !marketingRecorded") && consentPage.includes('disabled={marketingRecorded || consentStateLoading || Boolean(consentStateError)}') && consentPage.includes("기존 동의로 계속"), "persisted marketing consent is hydrated and bound without duplicate UI grant"],
  [consentPage.includes("setCorePolicyVersion(latestCore?.policy_version || null)") && consentPage.includes("setMarketingPolicyVersion(latestMarketing?.policy_version || null)") && consentPage.includes('corePolicyVersion || "확인 필요"') && consentPage.includes('marketingPolicyVersion || "확인 필요"'), "consent UI preserves recorded policy versions"],
  [inOrder(resumeContract, ["const saved = await api", "const normalized = resumeFormFromResponse(saved)", "setForm(normalized)", "baselineRef.current = JSON.stringify(normalized)"]), "resume form adopts normalized save response in order"],
  [app.includes('subjectLabel = ""') && app.includes('className="sr-only"> · {subjectLabel}') && candidateRecommendations.includes("data.items.map((item, index)") && candidateRecommendations.includes("조건 일치 결과 ${index + 1}") && candidateRecommendations.includes("<CandidateDecisionSupport") && candidateRecommendations.split("subjectLabel={subjectLabel}").length === 4 && recruiterRecommendations.includes("data.items.map((item, index)") && recruiterRecommendations.includes("조건 일치 결과 ${index + 1}") && recruiterRecommendations.split("subjectLabel={subjectLabel}").length === 4 && pipelineSurface.includes("{candidate.display_name} · {candidate.email}"), "repeated recommendation and candidate disclosures have unique visible-list names"],
  [pipelineSurface.includes("clearDraft(applicationId, { restoreFocus: false })") && pipelineSurface.includes("if (restoreFocus)") && pipelineSurface.includes('document.getElementById(`stage-${applicationId}`)?.focus()') && pipelineSurface.includes("onClick={() => clearDraft(item.id)}"), "pipeline draft cancel uses default focus restore while save avoids duplicate focus work"],
  [pipelineSurface.includes("지원 레코드가 있어도 현재 이력서를 찾지 못하면") && pipelineSurface.includes("지원 레코드 자체가 없다는 뜻은 아닙니다"), "pipeline response discloses missing-current-resume omission"],
  [adminAuditPage.includes('name="event_type" autoComplete="off"') && adminAuditPage.includes('<time role="cell" dateTime={event.occurred_at}>'), "audit filter and event timestamps retain form and machine-readable semantics"],
  [withdrawPage.includes("새 지원, 조건 일치 추천과 이력서 변경이 제한됩니다") && withdrawPage.includes("기업 화면 열람은 현재 API에서 별도로 차단되지 않습니다"), "core-consent withdrawal warning states candidate and enterprise boundaries"],
  [app.includes("previousLocation") && app.includes("decodeURIComponent(location.hash.slice(1))") && app.includes("target?.focus({ preventScroll: !hashTarget })") && app.includes('location.hash !== "#company-profile"') && css.includes("scroll-margin-top: 96px"), "hash navigation and company profile restore keyboard focus"],
  [legalPage.includes("구직자 계정에서 동의 철회와 회원 탈퇴") && legalPage.includes("기업 계정의 동의·탈퇴 수명주기는 구현되지 않았습니다"), "draft privacy copy separates candidate and enterprise account lifecycle"],
];

const forbidden = [
  [app.includes("원 지원자료"), "support-time snapshot overstatement"],
  [app.includes("원 지원 자료"), "spaced support-time snapshot overstatement"],
  [app.includes(">다시 계산</button>"), "forced-recalculation overstatement"],
  [app.includes("현재 런타임은 로컬 합성 Stub만 사용"), "hard-coded provider overstatement"],
  [css.includes(".account-area .text-link { display: none; }"), "hidden mobile login entry"],
  [css.includes(".pipeline-head, .pipeline-row { min-width: 900px"), "fixed-width mobile pipeline"],
  [css.includes(".main-nav { order: 3"), "visual and DOM navigation order mismatch"],
  [observation.includes("application_snapshot=absent"), "observation claim stronger than assertions"],
  [clientApi.includes('localStorage.removeItem("jcareer_token")'), "API helper bypasses centralized session-expiry handling"],
  [recommendationPages.some((source) => /setLoading\(true\);\s*setData\(null\);\s*setError\(null\)/.test(source)), "recommendation refresh discards loaded results"],
  [app.includes("<span>Matcher {data.matcher_version}</span>") || app.includes("<span>Cache · {data.cache}</span>"), "raw recommendation metadata labels"],
  [candidateRecommendations.includes("이력서 기술과 희망 직무를 보완한 뒤"), "misattributed candidate empty state"],
  [app.includes("세션이 만료되었습니다."), "401 cause overstatement"],
];

const failures = [
  ...required.filter(([observed]) => !observed).map(([, label]) => `missing: ${label}`),
  ...forbidden.filter(([observed]) => observed).map(([, label]) => `forbidden: ${label}`),
];

if (failures.length) {
  failures.forEach((failure) => console.error(failure));
  process.exitCode = 1;
} else {
  console.log(`J-Career two-sided web static contract: OK (${required.length} required, ${forbidden.length} forbidden)`);
}
