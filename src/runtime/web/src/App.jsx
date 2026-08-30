import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import {
  createBrowserRouter,
  Link,
  Navigate,
  NavLink,
  Outlet,
  RouterProvider,
  useBeforeUnload,
  useBlocker,
  useLocation,
  useNavigate,
  useParams,
  useSearchParams
} from "react-router-dom";
import { api, jsonBody } from "./api.js";
import { CandidateHomePage, CandidateJobComparison } from "./candidate-workspace.jsx";

const AuthContext = createContext(null);
const UnsavedContext = createContext(null);

const statusLabels = {
  applied: "지원 완료",
  reviewing: "서류 검토",
  interview: "인터뷰",
  offered: "처우 협의",
  rejected: "전형 종료",
  open: "채용 중",
  closed: "마감"
};

const roleHome = {
  candidate: "/candidate/home",
  recruiter: "/recruiter/overview",
  admin: "/admin/audit"
};
const authLayoutPaths = new Set(["/login", "/signup", "/recruiter/signup"]);

function routeTitle(pathname) {
  if (/^\/jobs\/[^/]+$/.test(pathname)) return "채용공고 상세";
  if (pathname === "/jobs" || pathname === "/") return "채용공고";
  if (pathname === "/login") return "로그인";
  if (pathname === "/signup") return "구직자 회원가입";
  if (pathname === "/signup/consent") return "서비스 이용 동의";
  if (pathname === "/recruiter/signup") return "기업회원 가입";
  if (pathname === "/candidate/home") return "지원자 홈";
  if (pathname === "/candidate/resume") return "내 이력서";
  if (pathname === "/candidate/applications") return "지원 현황";
  if (pathname === "/candidate/recommendations") return "조건 일치 공고";
  if (pathname === "/candidate/withdraw") return "동의와 계정 관리";
  if (pathname === "/recruiter/overview") return "기업 홈";
  if (/^\/recruiter\/jobs\/[^/]+\/pipeline$/.test(pathname)) return "지원자 파이프라인";
  if (/^\/recruiter\/jobs\/[^/]+\/recommendations$/.test(pathname)) return "지원자 조건 일치 순위";
  if (pathname === "/recruiter/jobs") return "채용 관리";
  if (pathname === "/admin/audit") return "감사 이벤트";
  if (pathname === "/privacy") return "개인정보 처리방침";
  if (pathname === "/terms") return "이용약관";
  return "페이지를 찾을 수 없습니다";
}

function safeConsentReturnTo(value) {
  if (typeof value !== "string") return "/candidate/resume";
  if (/^\/jobs\/[^/?#]+$/.test(value)) return value;
  if (["/candidate/home", "/candidate/resume", "/candidate/recommendations"].includes(value)) return value;
  return "/candidate/resume";
}

function clearStoredSession() {
  try {
    localStorage.removeItem("jcareer_token");
    localStorage.removeItem("jcareer_user");
    return true;
  } catch {
    // Storage can be unavailable in hardened or sandboxed browser contexts.
    return false;
  }
}

function readStoredSession() {
  try {
    const token = localStorage.getItem("jcareer_token");
    const storedUser = localStorage.getItem("jcareer_user");
    if (!token && !storedUser) return { user: null, notice: "" };
    if (!token || !storedUser) throw new Error("incomplete local session");
    const parsed = JSON.parse(storedUser);
    if (!parsed?.id || !parsed?.role) throw new Error("invalid local session");
    return { user: parsed, notice: "" };
  } catch {
    return {
      user: null,
      notice: "저장된 로그인 정보를 확인할 수 없어 다시 로그인이 필요합니다.",
      clearStored: true
    };
  }
}

function writeStoredSession(result) {
  try {
    localStorage.setItem("jcareer_token", result.access_token);
    localStorage.setItem("jcareer_user", JSON.stringify(result.user));
  } catch {
    clearStoredSession();
    throw new Error("브라우저 세션 저장소를 사용할 수 없습니다.");
  }
}

function AuthProvider({ children }) {
  const unsaved = useContext(UnsavedContext);
  const [initialSession] = useState(readStoredSession);
  const [user, setUser] = useState(initialSession.user);
  const [sessionNotice, setSessionNotice] = useState("");
  const [resumeDraft, setResumeDraft] = useState(null);

  useEffect(() => {
    const cleared = initialSession.clearStored ? clearStoredSession() : true;
    if (!cleared) {
      setSessionNotice("브라우저 저장소에서 로그인 정보 삭제 여부를 확인하지 못했습니다. 저장소 설정을 확인해 주세요.");
    } else if (initialSession.notice) {
      setSessionNotice(initialSession.notice);
    }
  }, [initialSession]);

  const establish = (result) => {
    writeStoredSession(result);
    setSessionNotice("");
    setResumeDraft(null);
    setUser(result.user);
  };

  const logout = (notice = "이 브라우저에 저장된 로그인 정보를 삭제했습니다.") => {
    const cleared = clearStoredSession();
    setSessionNotice(
      cleared
        ? notice
        : "브라우저 저장소에서 로그인 정보 삭제 여부를 확인하지 못했습니다. 저장소 설정을 확인해 주세요."
    );
    setResumeDraft(null);
    setUser(null);
  };

  useEffect(() => {
    const clearExpiredSession = () => {
      if (
        unsaved?.hasDirty
        && !window.confirm(
          "로그인 정보를 다시 확인해야 합니다. 로그인 화면으로 이동하면 저장하지 않은 입력은 사라집니다. 이동할까요?"
        )
      ) return;
      unsaved?.allowNextNavigation("/login");
      const cleared = clearStoredSession();
      setSessionNotice(
        cleared
          ? "저장된 로그인 정보를 확인할 수 없어 다시 로그인이 필요합니다."
          : "로그인 정보를 다시 확인해야 하며 브라우저 저장소 삭제 여부도 확인하지 못했습니다. 저장소 설정을 확인해 주세요."
      );
      setResumeDraft(null);
      setUser(null);
    };
    window.addEventListener("jcareer:unauthorized", clearExpiredSession);
    return () => window.removeEventListener("jcareer:unauthorized", clearExpiredSession);
  }, [unsaved]);

  return (
    <AuthContext.Provider value={{ user, establish, logout, setUser, sessionNotice, clearSessionNotice: () => setSessionNotice(""), resumeDraft, setResumeDraft }}>
      {children}
    </AuthContext.Provider>
  );
}

function useAuth() {
  return useContext(AuthContext);
}

function CandidateHomeRoute() {
  const { user } = useAuth();
  return <CandidateHomePage user={user} />;
}

function UnsavedProvider({ children }) {
  const [dirtyEntries, setDirtyEntries] = useState(() => new Map());
  const bypassRef = useRef(false);
  const setDirty = useCallback((key, dirty, message) => {
    setDirtyEntries((current) => {
      if ((!dirty && !current.has(key)) || (dirty && current.get(key) === message)) return current;
      const next = new Map(current);
      if (dirty) next.set(key, message); else next.delete(key);
      return next;
    });
  }, []);
  const hasDirty = dirtyEntries.size > 0;
  const promptMessage = dirtyEntries.size === 1
    ? dirtyEntries.values().next().value
    : "저장하지 않은 변경 내용이 여러 곳에 있습니다. 다른 화면으로 이동할까요?";
  const shouldBlock = useCallback(({ currentLocation, nextLocation }) => {
    const bypass = bypassRef.current;
    if (bypass) {
      if (Date.now() <= bypass.expiresAt && nextLocation.pathname === bypass.pathname) {
        bypassRef.current = null;
        return false;
      }
      if (Date.now() > bypass.expiresAt) bypassRef.current = null;
    }
    return (
      hasDirty
      && `${currentLocation.pathname}${currentLocation.search}${currentLocation.hash}`
        !== `${nextLocation.pathname}${nextLocation.search}${nextLocation.hash}`
    );
  }, [hasDirty]);
  const blocker = useBlocker(shouldBlock);
  useEffect(() => {
    if (blocker.state !== "blocked") return;
    if (window.confirm(promptMessage)) blocker.proceed(); else blocker.reset();
  }, [blocker, promptMessage]);
  useBeforeUnload(useCallback((event) => {
    if (!hasDirty) return;
    event.preventDefault();
    event.returnValue = "";
  }, [hasDirty]), { capture: true });
  const allowNextNavigation = useCallback((pathname) => {
    bypassRef.current = { pathname, expiresAt: Date.now() + 1500 };
  }, []);
  const value = useMemo(() => ({
    hasDirty,
    setDirty,
    allowNextNavigation
  }), [allowNextNavigation, hasDirty, setDirty]);
  return <UnsavedContext.Provider value={value}>{children}</UnsavedContext.Provider>;
}

function useUnsavedChanges(isDirty, message) {
  const registry = useContext(UnsavedContext);
  const registerDirty = registry?.setDirty;
  const keyRef = useRef(Symbol("unsaved-form"));
  useEffect(() => {
    registerDirty?.(keyRef.current, isDirty, message);
    return () => registerDirty?.(keyRef.current, false, message);
  }, [isDirty, message, registerDirty]);
}

function useRequestEpoch() {
  const epochRef = useRef(0);
  useEffect(() => () => { epochRef.current += 1; }, []);
  return useCallback(() => {
    const epoch = ++epochRef.current;
    return () => epochRef.current === epoch;
  }, []);
}

function Protected({ roles, children }) {
  const { user } = useAuth();
  const location = useLocation();
  if (!user) return <Navigate to="/login" replace state={{ from: `${location.pathname}${location.search}${location.hash}` }} />;
  if (roles && !roles.includes(user.role)) return <Navigate to={roleHome[user.role] || "/jobs"} replace />;
  return children;
}

function Shell({ children }) {
  const { user, logout, sessionNotice, clearSessionNotice } = useAuth();
  const unsaved = useContext(UnsavedContext);
  const navigate = useNavigate();
  const location = useLocation();
  const previousLocation = useRef(`${location.pathname}${location.hash}`);
  const normalizedPath = location.pathname.replace(/\/+$/, "") || "/";
  const isAuthLayoutRoute = authLayoutPaths.has(normalizedPath);
  const nav = user?.role === "candidate"
    ? [
        ["나의 홈", "/candidate/home"],
        ["조건 일치 공고", "/candidate/recommendations"],
        ["지원 현황", "/candidate/applications"],
        ["내 이력서", "/candidate/resume"],
        ["계정·동의", "/candidate/withdraw"]
      ]
    : user?.role === "recruiter"
      ? [
          ["기업 홈", "/recruiter/overview"],
          ["채용 관리", "/recruiter/jobs"]
        ]
      : user?.role === "admin"
        ? [["감사 이벤트", "/admin/audit"]]
        : [];

  const signOut = () => {
    if (unsaved?.hasDirty && !window.confirm("저장하지 않은 변경 내용이 있습니다. 로그아웃할까요?")) return;
    unsaved?.allowNextNavigation("/jobs");
    logout();
    navigate("/jobs");
  };

  const dismissSessionNotice = () => {
    clearSessionNotice();
    window.requestAnimationFrame(() => {
      const target = document.querySelector("#main-content h1") || document.getElementById("main-content");
      target?.setAttribute("tabindex", "-1");
      target?.focus({ preventScroll: true });
    });
  };

  useEffect(() => {
    const locationKey = `${location.pathname}${location.hash}`;
    if (previousLocation.current === locationKey) return undefined;
    previousLocation.current = locationKey;
    if (!location.hash) window.scrollTo(0, 0);
    const frame = window.requestAnimationFrame(() => {
      let hashTarget = null;
      if (location.hash) {
        try {
          hashTarget = document.getElementById(decodeURIComponent(location.hash.slice(1)));
        } catch {
          hashTarget = null;
        }
      }
      const target = hashTarget || document.querySelector("#main-content h1") || document.getElementById("main-content");
      target?.setAttribute("tabindex", "-1");
      target?.focus({ preventScroll: !hashTarget });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [location.hash, location.pathname]);

  useEffect(() => {
    document.title = `${routeTitle(location.pathname)} · J-Career AS-IS`;
  }, [location.pathname]);

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">본문 바로가기</a>
      <div className="environment-strip" role="note">
        <span>실제 지원자·기업 정보 입력 금지</span>
        <span>AS-IS 재현환경</span>
        <span>합성 데이터 전용</span>
      </div>
      {!isAuthLayoutRoute && <header className="topbar">
        <div className="topbar-inner">
          <Link className="brand" to="/jobs" aria-label="J-Career 공고 홈">
            <span className="brand-mark" aria-hidden="true">J</span>
            <span>J-Career</span>
          </Link>
          <nav className="main-nav" aria-label="주요 메뉴">
            <NavLink to="/jobs">채용공고</NavLink>
            {!user && <NavLink to="/recruiter/signup">기업회원</NavLink>}
            {nav.map(([label, href]) => <NavLink key={href} to={href}>{label}</NavLink>)}
          </nav>
          <div className="account-area">
            {user ? (
              <>
                <div className="account-copy">
                  <strong>{user.display_name}</strong>
                  <span>{user.company_name || ({ candidate: "구직자", recruiter: "채용담당자", admin: "운영자" }[user.role] || "사용자")}</span>
                </div>
                <button type="button" className="button quiet small" onClick={signOut}>로그아웃</button>
              </>
            ) : (
              <>
                <Link className="text-link" to="/login">로그인</Link>
                <Link className="button small" to="/signup">시작하기</Link>
              </>
            )}
          </div>
        </div>
      </header>}
      <main id="main-content" tabIndex="-1">
        <SessionNotice onDismiss={dismissSessionNotice}>{sessionNotice}</SessionNotice>
        {children}
      </main>
      {!isAuthLayoutRoute && <footer className="footer">
        <div>
          <strong>J-Career synthetic operations lab</strong>
          <p>기존 채용·추천 흐름을 검증하기 위한 합성 재현환경입니다.</p>
        </div>
        <div className="footer-links">
          <Link to="/privacy">개인정보 처리방침</Link>
          <Link to="/terms">이용약관</Link>
        </div>
      </footer>}
    </div>
  );
}

function ErrorNotice({ error, onRetry }) {
  if (!error) return null;
  return <div className="notice error" role="alert" aria-live="assertive"><span>{error.message || String(error)}</span>{onRetry && <button type="button" className="text-button" onClick={onRetry}>다시 시도</button>}</div>;
}

function SuccessNotice({ children }) {
  if (!children) return null;
  return <div className="notice success" role="status" aria-live="polite">{children}</div>;
}

function SessionNotice({ children, onDismiss }) {
  return (
    <>
      <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">{children || ""}</p>
      {children && (
        <div className="session-notice-wrap">
          <div className="notice session">
            <p aria-hidden="true">{children}</p>
            <button type="button" className="text-button" onClick={onDismiss} aria-label="로그인 상태 안내 닫기">닫기</button>
          </div>
        </div>
      )}
    </>
  );
}

function ConsentRecovery({ error, onContinue }) {
  const location = useLocation();
  const unsaved = useContext(UnsavedContext);
  const needsConsent = error?.status === 409 && /동의/.test(error.message || "");
  if (!needsConsent) return null;
  const returnTo = safeConsentReturnTo(location.pathname);
  const continueToConsent = () => {
    onContinue?.();
    if (onContinue) unsaved?.allowNextNavigation("/signup/consent");
  };
  return <div className="recovery-action"><Link className="button small" to="/signup/consent" state={{ returnTo }} onClick={continueToConsent}>동의 계속하기</Link><span>필수 동의 상태를 다시 확인한 뒤 현재 기능으로 돌아옵니다.</span></div>;
}

function ResumeRecovery({ error }) {
  const needsResume = error?.status === 409 && /이력서/.test(error.message || "");
  if (!needsResume) return null;
  return <div className="recovery-action"><Link className="button small" to="/candidate/resume">이력서 작성하기</Link><span>이력서를 저장한 뒤 조건 일치 공고를 다시 불러오세요.</span></div>;
}

function Loading({ label = "불러오는 중" }) {
  return <div className="loading" role="status" aria-live="polite"><span className="spinner" aria-hidden="true" />{label}</div>;
}

function EmptyState({ title, body, action }) {
  return (
    <div className="empty-state">
      <span className="empty-symbol" aria-hidden="true">↳</span>
      <h2>{title}</h2>
      <p>{body}</p>
      {action}
    </div>
  );
}

function PageHeader({ eyebrow, title, description, actions }) {
  return (
    <div className="page-header">
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {description && <p className="page-description">{description}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  );
}

function SkillList({ skills = [] }) {
  return <div className="chips">{skills.map((skill) => <span className="chip" key={skill}>{skill}</span>)}</div>;
}

function Score({ value }) {
  const numeric = Number(value);
  const display = Number.isFinite(numeric) ? numeric.toFixed(1) : null;
  return (
    <p className="score">
      <span className="sr-only">{display ? `조건 일치 점수 100점 만점에 ${display}점` : "조건 일치 점수를 확인할 수 없음"}</span>
      <strong aria-hidden="true">{display || "—"}</strong>
      <span aria-hidden="true">/ 100</span>
    </p>
  );
}

const factorLabels = {
  skills: "요구 기술 일치",
  experience: "경력 조건",
  role: "희망 직무 연관"
};

const dataFieldLabels = {
  name: "이름",
  phone: "전화번호",
  email: "이메일",
  birthdate: "생년월일",
  address: "거주지역",
  school: "학교·학력",
  certificates: "자격증",
  self_intro: "자기소개"
};

function ScoreDisclosure({ breakdown, explanation, explanationAttempt, audience = "candidate", subjectLabel = "" }) {
  if (!breakdown?.factors?.length) {
    return <div className="score-disclosure-missing" role="note">점수 계산 내역을 불러오지 못했습니다. 총점을 화면에서 재계산하지 않습니다.</div>;
  }
  const configuredPriority = breakdown.factors.find((factor) => factor.factor_id === breakdown.configured_priority_factor_id);
  const largestContributions = breakdown.factors.filter((factor) => (breakdown.largest_contribution_factor_ids || []).includes(factor.factor_id));
  const preparedFieldSetState = explanationAttempt?.prepared_field_set_state;
  const preparedFields = explanationAttempt?.candidate_fields_prepared || explanation?.prompt_fields_prepared || [];
  const excludedFields = breakdown.excluded_input_fields || [];
  const excludedButPrepared = excludedFields.filter((field) => preparedFields.includes(field));

  return (
    <>
      <p className="score-boundary">{audience === "recruiter" ? "구조화 3개 항목의 조건 일치 점수입니다. 선발 순서나 채용 결정이 아니며 지원 자료는 담당자가 직접 검토합니다." : "공고와 이력서의 구조화 항목 비교 결과입니다. 합격·탈락 결정이 아닙니다."}</p>
      {preparedFieldSetState === "CACHE_ORIGIN_FIELD_SET_NOT_VERIFIED" && <p className="asis-observation always-visible"><span>AS-IS 관찰</span> 캐시 원본 요청에서 준비된 필드 집합은 현재 캐시 응답 구조로 검증되지 않습니다. 이번 조회에서 해당 필드를 다시 준비하거나 외부 공급자가 수신했다는 뜻도 아닙니다.</p>}
      {excludedButPrepared.length > 0 && <p className="asis-observation always-visible"><span>AS-IS 관찰</span> 점수에 쓰지 않은 {excludedButPrepared.map((field) => dataFieldLabels[field] || field).join(", ")} 정보가 현재 설명 요청용으로 준비됐습니다. 이 표시는 외부 공급자의 실제 수신을 뜻하지 않습니다.</p>}
      <details className="score-disclosure">
        <summary>점수 계산 근거 보기{subjectLabel && <span className="sr-only"> · {subjectLabel}</span>}</summary>
        <div className="score-disclosure-body">
          <div className="score-policy">
            <div><span>계산 기준</span><strong>{breakdown.formula}</strong></div>
            <div><span>기준 출처</span><strong>플랫폼 공통 기본값</strong></div>
            <div><span>설계상 최대 비중</span><strong>{configuredPriority?.label || factorLabels[breakdown.configured_priority_factor_id]}</strong></div>
            <div><span>이번 결과 기여 최대</span><strong>{largestContributions.map((factor) => factor.label).join(" · ") || "계산 내역 확인 필요"}</strong></div>
          </div>
          <p className="score-policy-summary" role="note"><strong>이 점수의 우선요인</strong> 현재 플랫폼 공통 기준에서는 {configuredPriority?.label || factorLabels[breakdown.configured_priority_factor_id]}가 최대 {Number(configuredPriority?.max_points || 0).toFixed(0)}점으로 가장 큰 비중입니다. 이번 결과에서 가장 크게 기여한 요인은 {largestContributions.map((factor) => factor.label).join(" · ") || "확인되지 않음"}입니다. 기업별 가중치나 가산점 정책은 적용되지 않았습니다.</p>
          <div className="factor-list" aria-label="요인별 점수">
            {breakdown.factors.map((factor) => (
              <div className="factor-row" key={factor.factor_id}>
                <div className="factor-heading">
                  <strong>{factor.label}</strong>
                  <span>{Number(factor.display_points).toFixed(1)} / {Number(factor.max_points).toFixed(0)}점</span>
                </div>
                <progress value={factor.raw_points} max={factor.max_points} aria-label={`${factor.label} ${factor.display_points}점, 최대 ${factor.max_points}점`} />
                <p>{factor.calculation}</p>
              </div>
            ))}
          </div>
          <p className="rounding-note">각 항목은 소수 첫째 자리 표시값입니다. 총점은 반올림 전 기여도를 합산한 뒤 소수 첫째 자리로 표시합니다.</p>
          <div className="data-use-boundary">
            <strong>점수 산정에 사용하지 않은 정보</strong>
            <p>{excludedFields.length ? excludedFields.map((field) => dataFieldLabels[field] || field).join(", ") : "별도 표시 항목 없음"}</p>
          </div>
          <span className="contract-version">{breakdown.formula_version} · {breakdown.schema_version}</span>
        </div>
      </details>
    </>
  );
}

const companyProfileSourceLabels = {
  unset: "미설정 상태",
  synthetic_recruiter_declared: "합성 시드 데이터",
  recruiter_declared: "기업 담당자 저장"
};

function ProfileSource({ source }) {
  return <span className="profile-source">출처 · {companyProfileSourceLabels[source] || "확인 필요"}</span>;
}

const openDartStateLabels = {
  AVAILABLE_SYNTHETIC_FIXTURE: "합성 예시 저장됨",
  AVAILABLE_LIVE: "외부 조회의 최근 저장본",
  REFRESH_QUEUED: "갱신 요청 대기 중",
  STALE_LAST_KNOWN_GOOD: "직전 저장본 유지 중",
  UNAVAILABLE_NO_SNAPSHOT: "조회 가능한 저장본 없음",
  UNAVAILABLE_INVALID_SNAPSHOT: "저장본 형식 확인 필요",
  NOT_LINKED: "연결되지 않음"
};

function compactDate(value) {
  if (!/^\d{8}$/.test(value || "")) return "확인 필요";
  return `${value.slice(0, 4)}.${value.slice(4, 6)}.${value.slice(6, 8)}`;
}

function snapshotTime(value) {
  if (!value || Number.isNaN(new Date(value).getTime())) return "확인 필요";
  return new Intl.DateTimeFormat("ko-KR", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function OpenDartCompanyFacts({ opendart, headingLevel = "h2" }) {
  const snapshot = opendart?.snapshot;
  if (!snapshot?.company) return null;
  const Heading = headingLevel;
  const company = snapshot.company;
  const disclosures = snapshot.disclosures?.items || [];
  const stateLabel = openDartStateLabels[opendart.state] || "상태 확인 필요";
  return (
    <section className="opendart-facts" aria-labelledby={`opendart-heading-${headingLevel}`}>
      <div className="opendart-heading">
        <div>
          <p className="eyebrow">공시 출처 복사본</p>
          <Heading id={`opendart-heading-${headingLevel}`}>OpenDART 공개 기업정보</Heading>
        </div>
        <div className="opendart-state"><span>{stateLabel}</span><strong>{snapshot.synthetic ? "합성 예시" : "외부 조회 복사본"}</strong></div>
      </div>
      <p className="opendart-boundary"><strong>점수 반영 없음.</strong> 기업 담당자의 방향 선언과 분리된 공시 출처 복사본이며 추천 점수·정렬·기업 적합성 판단에는 사용하지 않습니다.</p>
      <dl className="opendart-fact-grid">
        <div><dt>정식 회사명</dt><dd>{company.legal_name || "확인 필요"}</dd></div>
        <div><dt>시장 구분</dt><dd>{company.market_label || "확인 필요"}</dd></div>
        <div><dt>업종 코드</dt><dd>{company.industry_code || "확인 필요"}</dd></div>
        <div><dt>설립일</dt><dd>{compactDate(company.established_on)}</dd></div>
        <div><dt>결산월</dt><dd>{company.fiscal_month ? `${company.fiscal_month}월` : "확인 필요"}</dd></div>
        <div><dt>조회 시각</dt><dd>{snapshotTime(snapshot.retrieved_at)}</dd></div>
      </dl>
      <div className="opendart-disclosures">
        <div className="opendart-section-title"><strong>최근 공시</strong><span>최대 5건 · 최근 1년 조회</span></div>
        {disclosures.length ? <ul>{disclosures.map((item) => {
          const liveDocument = !snapshot.synthetic && /^\d{14}$/.test(item.receipt_ref || "");
          return <li key={item.receipt_ref}><div><strong>{item.report_name}</strong><time dateTime={item.submitted_on}>{compactDate(item.submitted_on)}</time></div>{liveDocument ? <a href={`https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${item.receipt_ref}`} target="_blank" rel="noreferrer">원문 공시 열기<span className="sr-only"> · 새 창</span></a> : <span>{item.receipt_ref}</span>}</li>;
        })}</ul> : <p>{snapshot.disclosures?.state === "NO_DATA" ? "조회 기간에 표시할 공시가 없습니다." : "공시 목록을 불러오지 못했습니다. 기업 기본 저장본은 유지됩니다."}</p>}
      </div>
      <footer><span>{snapshot.snapshot_version || opendart.snapshot_version}</span><a href={snapshot.source_guides?.company} target="_blank" rel="noreferrer">공식 API 항목 보기<span className="sr-only"> · 새 창</span></a></footer>
    </section>
  );
}

function CompanyAlignment({ alignment, profileSource }) {
  if (!alignment) return <div className="alignment-unavailable"><strong>기업 방향 분석을 불러오지 못했습니다.</strong><span>이 상태는 기존 점수에 영향을 주지 않습니다.</span><ProfileSource source={profileSource} /></div>;
  const matched = alignment.matched_declared_values || [];
  const stateCopy = {
    COMPANY_PROFILE_UNAVAILABLE: {
      headline: "기업 방향 프로필이 아직 등록되지 않았습니다",
      body: "비교할 기업 선언 가치가 없어 자소서 대조를 수행하지 않았습니다. 지원자 자료의 부족을 뜻하지 않습니다."
    },
    NO_DIRECT_DECLARED_VALUE_EVIDENCE: {
      headline: "선언 가치와 문자열이 직접 겹치는 표현은 없습니다",
      body: "표현이 겹치지 않았을 뿐이며 의미상 부합 여부는 판단하지 않았습니다."
    },
    DIRECT_DECLARED_VALUE_EVIDENCE_FOUND: {
      headline: "선언 가치와 겹치는 표현을 찾았습니다",
      body: `직접 겹친 표현: ${matched.join(", ")}. 실제 경험의 부합 여부는 담당자가 확인합니다.`
    }
  };
  const copy = stateCopy[alignment.state] || {
    headline: "기업 방향 대조 상태를 확인할 수 없습니다",
    body: "이 상태만으로 지원자 또는 기업 방향의 부합 여부를 판단하지 않습니다."
  };
  return (
    <section className="company-alignment" aria-label="기업 방향과 자소서 근거">
      <div className="alignment-heading"><div><span>자소서 분석 · 점수와 별도</span><strong>기업 방향과 자소서 근거</strong></div><div className="profile-provenance"><span className="profile-version">{alignment.profile_version || "프로필 미설정"}</span><ProfileSource source={profileSource} /></div></div>
      <div className="alignment-badges"><span>점수 반영 없음</span>{alignment.human_review_required && <span>담당자 확인 필요</span>}</div>
      {alignment.direction_statement ? <p className="direction-statement">“{alignment.direction_statement}”</p> : <p className="direction-statement muted">기업이 선언한 방향이 아직 없습니다.</p>}
      {alignment.declared_values?.length > 0 && <div className="declared-values" aria-label="기업 선언 가치">{alignment.declared_values.map((value) => <span className={matched.includes(value) ? "value-chip matched" : "value-chip"} key={value}>{value}{matched.includes(value) ? " · 자소서 근거" : ""}</span>)}</div>}
      <p className="alignment-result"><strong>{copy.headline}</strong><span>{copy.body}</span></p>
      <small>문자열 근거 비교의 관찰 결과입니다. 활용 여부는 담당자가 별도로 검토합니다.</small>
    </section>
  );
}

function JobsPage() {
  const pageLocation = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const searchKey = searchParams.toString();
  const beginRequest = useRequestEpoch();
  const [jobs, setJobs] = useState([]);
  const [query, setQuery] = useState(() => searchParams.get("q") || "");
  const [location, setLocation] = useState(() => searchParams.get("location") || "");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = async (nextQuery, nextLocation) => {
    const isCurrent = beginRequest();
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (nextQuery) params.set("q", nextQuery);
      if (nextLocation) params.set("location", nextLocation);
      const result = await api(`/api/v1/jobs?${params}`);
      if (isCurrent()) setJobs(result);
    } catch (caught) {
      if (isCurrent()) setError(caught);
    } finally {
      if (isCurrent()) setLoading(false);
    }
  };

  const submit = (event) => {
    event.preventDefault();
    const params = new URLSearchParams();
    if (query) params.set("q", query);
    if (location) params.set("location", location);
    if (params.toString() === searchKey) load(query, location);
    else setSearchParams(params);
  };

  useEffect(() => {
    const applied = new URLSearchParams(searchKey);
    const nextQuery = applied.get("q") || "";
    const nextLocation = applied.get("location") || "";
    setQuery(nextQuery);
    setLocation(nextLocation);
    load(nextQuery, nextLocation);
  }, [searchKey]);

  return (
    <>
      <section className="jobs-hero">
        <div className="jobs-hero-inner">
          <div className="hero-copy">
            <p className="eyebrow light">오늘의 채용 신호</p>
            <h1>조건보다 먼저,<br />일의 결을 찾으세요.</h1>
            <p>구조화된 직무 조건과 경력을 연결해 탐색부터 지원까지 이어갑니다.</p>
          </div>
          <form className="search-panel" onSubmit={submit} aria-label="채용공고 검색">
            <label>
              <span>직무 또는 기술</span>
              <input name="q" autoComplete="off" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="예: 백엔드, Python" />
            </label>
            <label>
              <span>근무 지역</span>
              <input name="location" autoComplete="address-level1" value={location} onChange={(e) => setLocation(e.target.value)} placeholder="예: 서울, 성남" />
            </label>
            <button className="button accent" type="submit">공고 찾기</button>
          </form>
        </div>
      </section>
      <section className="content wide">
        <SuccessNotice>{pageLocation.state?.notice}</SuccessNotice>
        {!loading && !error && <div className="result-heading" role="status" aria-live="polite" aria-atomic="true">
          <div><span className="result-number">{jobs.length}</span><span>개의 열린 포지션</span></div>
          <p>합성기업의 데모 공고만 표시됩니다.</p>
        </div>}
        <ErrorNotice error={error} onRetry={() => load(query, location)} />
        {loading ? <Loading label="채용공고를 불러오는 중" /> : error ? null : jobs.length ? (
          <div className="job-grid">
            {jobs.map((job) => (
              <article className="job-card" key={job.id}>
                <div className="job-company">
                  <span className="company-avatar">{job.company_name.slice(0, 1)}</span>
                  <div><strong>{job.company_name}</strong><span>{job.location}</span></div>
                </div>
                <div>
                  <h2><Link to={`/jobs/${job.id}`}>{job.title}</Link></h2>
                  <p className="clamp">{job.summary}</p>
                </div>
                <SkillList skills={job.required_skills.slice(0, 4)} />
                <div className="job-meta">
                  <span>{job.employment_type}</span>
                  <span>경력 {job.min_experience}년 이상</span>
                  <span className="arrow-link" aria-hidden="true">공고 보기 <span>→</span></span>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState title="검색 결과가 없습니다" body="직무나 지역 조건을 줄여 다시 검색해 보세요." />
        )}
      </section>
    </>
  );
}

function JobActionPanel({ job, user, error, message, submitting, onApply }) {
  const successLinkRef = useRef(null);
  useEffect(() => {
    if (!message) return undefined;
    const frame = window.requestAnimationFrame(() => successLinkRef.current?.focus());
    return () => window.cancelAnimationFrame(frame);
  }, [message]);
  if (user?.role === "recruiter") {
    const ownsJob = user.company_id === job.company_id;
    return (
      <aside className="apply-panel">
        <span className={`status-pill status-${job.status}`}>{statusLabels[job.status]}</span>
        <h2>{ownsJob ? "내 회사 공고입니다" : "기업 담당자 계정입니다"}</h2>
        <p>{ownsJob ? "지원자 파이프라인과 조건 일치 결과는 기업 업무 화면에서 확인합니다." : "다른 합성 기업의 공개 공고에는 기업 업무 권한이 적용되지 않습니다."}</p>
        {ownsJob && <Link className="button full" to={`/recruiter/jobs/${job.id}/pipeline`}>지원자 파이프라인</Link>}
        <Link className="button quiet full" to="/recruiter/jobs">채용공고 관리</Link>
      </aside>
    );
  }
  if (user?.role === "admin") {
    return (
      <aside className="apply-panel">
        <span className={`status-pill status-${job.status}`}>{statusLabels[job.status]}</span>
        <h2>운영자 계정입니다</h2>
        <p>운영자 역할에서는 지원 작업을 수행하지 않습니다.</p>
        <Link className="button quiet full" to="/admin/audit">감사 이벤트 보기</Link>
      </aside>
    );
  }
  const closed = job.status !== "open";
  return (
    <aside className="apply-panel">
      <span className={`status-pill status-${job.status}`}>{statusLabels[job.status]}</span>
      <h2>{closed ? "접수가 마감된 공고입니다" : "지원할 준비가 되었나요?"}</h2>
      <p>{closed ? "공고 내용은 확인할 수 있지만 새 지원은 받지 않습니다." : "저장된 구조화 이력서로 바로 지원합니다."}</p>
      <ErrorNotice error={error} />
      <ConsentRecovery error={error} />
      <SuccessNotice>{message}</SuccessNotice>
      {message ? <Link ref={successLinkRef} className="button full" to="/candidate/applications">지원 현황 보기</Link> : <button className="button full" onClick={onApply} disabled={submitting || closed}>{closed ? "마감된 공고" : submitting ? "지원 중…" : "이 공고에 지원하기"}</button>}
      <Link className="button quiet full" to="/candidate/resume">이력서 확인</Link>
    </aside>
  );
}

function JobDetailPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let active = true;
    setJob(null);
    setError(null);
    setMessage("");
    api(`/api/v1/jobs/${id}`)
      .then((result) => { if (active) setJob(result); })
      .catch((caught) => { if (active) setError(caught); });
    return () => { active = false; };
  }, [id]);

  useEffect(() => {
    if (job?.title) document.title = `${job.title} · J-Career AS-IS`;
  }, [job?.title]);

  const apply = async () => {
    if (!user) {
      navigate("/login", { state: { from: `/jobs/${id}` } });
      return;
    }
    if (user.role !== "candidate") {
      setError(new Error("구직자 계정으로 로그인해야 지원할 수 있습니다."));
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await api(`/api/v1/jobs/${id}/applications`, { method: "POST" });
      setMessage("지원이 접수되었습니다. 지원 현황에서 진행 상태를 확인할 수 있습니다.");
    } catch (caught) {
      setError(caught);
    } finally {
      setSubmitting(false);
    }
  };

  if (!job && !error) return <section className="content narrow"><PageHeader eyebrow="Job detail" title="채용공고 상세" description="합성기업의 공고 내용을 불러오고 있습니다." /><Loading label="공고를 불러오는 중" /></section>;
  if (!job) return <section className="content narrow"><PageHeader eyebrow="Job not available" title="공고를 불러올 수 없습니다" description="요청한 공고의 상태를 확인하지 못했습니다." /><ErrorNotice error={error} /><EmptyState title="다른 열린 공고를 확인해 주세요" body="주소가 바뀌었거나 현재 공개되지 않은 합성 공고일 수 있습니다." action={<Link className="button" to="/jobs">채용공고 목록</Link>} /></section>;

  return (
    <section className="content detail-layout">
      <article className="detail-main">
        <Link className="back-link" to="/jobs">← 채용공고</Link>
        <p className="eyebrow">{job.company_name}</p>
        <h1>{job.title}</h1>
        <div className="detail-facts">
          <span>{job.location}</span><span>{job.employment_type}</span><span>경력 {job.min_experience}년 이상</span>
        </div>
        <hr />
        <h2>함께할 일</h2>
        <p className="detail-copy">{job.summary}</p>
        <h2>주요 기술</h2>
        <SkillList skills={job.required_skills} />
        {job.company_profile?.direction_statement && <section className="job-company-direction" aria-labelledby="company-direction-heading"><h2 id="company-direction-heading">이 기업이 밝힌 방향</h2><ProfileSource source={job.company_profile.source} /><p className="direction-statement">“{job.company_profile.direction_statement}”</p><SkillList skills={job.company_profile.declared_values || []} /><small>기업 방향 프로필에 저장된 합성 선언입니다. 자소서와 표현이 겹치는지는 별도 결과로 제공되며 의미상 부합 여부를 대신 판단하지 않습니다.</small></section>}
        <OpenDartCompanyFacts opendart={job.company_profile?.opendart} />
        <div className="detail-note">
          <strong>이 공고는 합성 데이터입니다.</strong>
          <p>실제 기업·근무지·채용 의사와 관련이 없는 AS-IS 재현환경용 공고입니다.</p>
        </div>
      </article>
      <JobActionPanel job={job} user={user} error={error} message={message} submitting={submitting} onApply={apply} />
    </section>
  );
}

function AuthLayout({ title, description, children, aside }) {
  return (
    <section className="auth-layout">
      <div className="auth-aside">
        <Link className="brand inverse" to="/jobs" aria-label="J-Career 채용공고 홈"><span className="brand-mark" aria-hidden="true">J</span><span>J-Career</span></Link>
        <div>{aside || <><p className="eyebrow light">합성 운영 시나리오</p><p className="auth-promo-title">채용의 시작과 끝을 직접 확인하세요.</p><p>가입, 동의, 지원, 추천, 기업 검토까지 하나의 데이터 흐름으로 이어집니다.</p></>}</div>
        <p className="auth-footnote">실제 개인정보를 입력하지 마세요.</p>
      </div>
      <div className="auth-form-wrap">
        <div className="auth-form">
          <p className="eyebrow">J-Career account</p>
          <h1>{title}</h1>
          <p className="page-description">{description}</p>
          {children}
        </div>
      </div>
    </section>
  );
}

function LoginPage() {
  const { establish, user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [form, setForm] = useState({ email: "candidate@jcareer.test", password: "Demo123!" });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  if (user) return <Navigate to={roleHome[user.role] || "/jobs"} replace />;

  const submit = async (event, override) => {
    event?.preventDefault();
    const credentials = override || form;
    setBusy(true);
    setError(null);
    try {
      const result = await api("/api/v1/auth/login", { method: "POST", body: jsonBody(credentials) });
      establish(result);
      navigate(location.state?.from || roleHome[result.user.role] || "/jobs", { replace: true });
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  };

  const demos = [
    ["구직자", "candidate@jcareer.test"],
    ["채용담당자", "recruiter@jcareer.test"],
    ["운영자", "admin@jcareer.test"]
  ];
  return (
    <AuthLayout title="로그인" description="계정 역할에 맞는 업무 화면으로 이동합니다.">
      <form className="stack-form" onSubmit={submit} aria-busy={busy}>
        <label><span>이메일</span><input name="email" type="email" autoComplete="email" spellCheck={false} value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required /></label>
        <label><span>비밀번호</span><input name="password" type="password" autoComplete="current-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required /></label>
        <ErrorNotice error={error} />
        <button type="submit" className="button full" disabled={busy}>{busy ? "확인 중…" : "로그인"}</button>
      </form>
      <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">{busy ? "로그인 요청을 처리하고 있습니다." : ""}</p>
      <div className="demo-logins">
        <p>데모 계정으로 바로 보기</p>
        <div>{demos.map(([label, email]) => <button type="button" key={email} className="demo-login" disabled={busy} onClick={() => submit(null, { email, password: "Demo123!" })}>{label}<span>→</span></button>)}</div>
      </div>
      <p className="form-switch">구직자 계정이 없나요? <Link to="/signup">회원가입</Link></p>
      <p className="form-switch">기업 담당자인가요? <Link to="/recruiter/signup">기업회원 가입</Link></p>
    </AuthLayout>
  );
}

function SignupPage() {
  const { establish } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ display_name: "", email: "", password: "" });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const submit = async (event) => {
    event.preventDefault();
    setBusy(true); setError(null);
    try {
      const result = await api("/api/v1/auth/signup", { method: "POST", body: jsonBody(form) });
      establish(result);
      navigate("/signup/consent");
    } catch (caught) { setError(caught); } finally { setBusy(false); }
  };
  return (
    <AuthLayout title="구직자 회원가입" description="화면 검증용 합성 정보만 입력해 주세요.">
      <form className="stack-form" onSubmit={submit} aria-busy={busy}>
        <label><span>이름</span><input name="display_name" autoComplete="name" value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} placeholder="예: 합성 지원자" required minLength={2} maxLength={100} /></label>
        <label><span>이메일</span><input name="email" type="email" autoComplete="email" spellCheck={false} aria-describedby="candidate-email-help" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="name@example.invalid" required minLength={3} maxLength={254} /><small id="candidate-email-help">합성 전용 @jcareer.test 또는 @example.invalid 주소만 입력하세요.</small></label>
        <label><span>비밀번호</span><input name="password" type="password" autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} minLength={8} maxLength={128} required /><small>8자 이상 입력하세요.</small></label>
        <ErrorNotice error={error} />
        <button type="submit" className="button full" disabled={busy}>{busy ? "계정 생성 중…" : "동의 화면으로 계속"}</button>
      </form>
      <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">{busy ? "구직자 계정 생성 요청을 처리하고 있습니다." : ""}</p>
      <p className="form-switch">이미 계정이 있나요? <Link to="/login">로그인</Link></p>
    </AuthLayout>
  );
}

function ConsentPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const beginRequest = useRequestEpoch();
  const returnTo = safeConsentReturnTo(location.state?.returnTo);
  const [required, setRequired] = useState(false);
  const [marketing, setMarketing] = useState(false);
  const [coreRecorded, setCoreRecorded] = useState(false);
  const [marketingRecorded, setMarketingRecorded] = useState(false);
  const [corePolicyVersion, setCorePolicyVersion] = useState(null);
  const [marketingPolicyVersion, setMarketingPolicyVersion] = useState(null);
  const [consentStateLoading, setConsentStateLoading] = useState(true);
  const [consentStateError, setConsentStateError] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const loadConsentState = async () => {
    const isCurrent = beginRequest();
    setConsentStateLoading(true);
    setConsentStateError(null);
    try {
      const events = await api("/api/v1/candidates/me/consents");
      const latestCore = events.find((event) => event.consent_type === "privacy_core");
      const latestMarketing = events.find((event) => event.consent_type === "marketing");
      if (isCurrent()) {
        const alreadyGranted = latestCore?.action === "grant";
        const marketingAlreadyGranted = latestMarketing?.action === "grant";
        setCoreRecorded(alreadyGranted);
        setRequired(alreadyGranted);
        setMarketingRecorded(marketingAlreadyGranted);
        setMarketing(marketingAlreadyGranted);
        setCorePolicyVersion(latestCore?.policy_version || null);
        setMarketingPolicyVersion(latestMarketing?.policy_version || null);
      }
    } catch (caught) {
      if (isCurrent()) setConsentStateError(caught);
    } finally {
      if (isCurrent()) setConsentStateLoading(false);
    }
  };
  useEffect(() => { loadConsentState(); }, []);
  const submit = async (event) => {
    event.preventDefault();
    if (consentStateLoading || consentStateError) return;
    if (!required) { setError(new Error("필수 동의 항목을 확인해 주세요.")); return; }
    setBusy(true); setError(null);
    try {
      if (!coreRecorded) {
        await api("/api/v1/candidates/me/consents", { method: "POST", body: jsonBody({ action: "grant", consent_type: "privacy_core", policy_version: "2026-05" }) });
        setCoreRecorded(true);
        setCorePolicyVersion("2026-05");
      }
      if (marketing && !marketingRecorded) {
        try {
          await api("/api/v1/candidates/me/consents", { method: "POST", body: jsonBody({ action: "grant", consent_type: "marketing", policy_version: "2026-05" }) });
          setMarketingRecorded(true);
          setMarketingPolicyVersion("2026-05");
        } catch {
          setError(new Error("필수 동의는 기록됐지만 선택 동의 기록에 실패했습니다. 선택 동의를 다시 시도하거나 체크를 해제하고 계속해 주세요."));
          return;
        }
      }
      navigate(returnTo, { replace: true });
    } catch (caught) { setError(caught); } finally { setBusy(false); }
  };
  return (
    <section className="content narrow">
      <PageHeader eyebrow="가입 2/2" title="서비스 이용 동의" description="AS-IS 시나리오의 통합 동의 구조를 재현합니다." />
      <form className="consent-form" onSubmit={submit}>
        <div className="consent-card required">
          <label className="check-row"><input name="privacy_core" type="checkbox" checked={required} disabled={coreRecorded || consentStateLoading || Boolean(consentStateError)} onChange={(e) => setRequired(e.target.checked)} /><span><strong>[필수] 이용약관 및 개인정보 수집·이용</strong><small>{consentStateLoading ? "기존 동의 확인 중" : coreRecorded ? `기록 완료 · 정책 버전 ${corePolicyVersion || "확인 필요"}` : "정책 버전 2026-05"}</small></span></label>
          <div className="consent-detail">
            <p><strong>수집 항목</strong> 성명, 이메일, 연락처, 생년월일, 주소, 학력, 경력, 자격증</p>
            <p><strong>이용 목적</strong> 회원관리, 채용정보 제공, AI 추천 서비스 제공</p>
            <p><strong>보유 기간</strong> 회원 탈퇴 시까지</p>
          </div>
        </div>
        <div className="consent-card">
          <label className="check-row"><input name="marketing" type="checkbox" checked={marketing} disabled={marketingRecorded || consentStateLoading || Boolean(consentStateError)} onChange={(e) => setMarketing(e.target.checked)} /><span><strong>[선택] 마케팅 정보 수신</strong><small>{marketingRecorded ? `기록 완료 · 정책 버전 ${marketingPolicyVersion || "확인 필요"} · 철회는 동의와 계정 관리에서 할 수 있습니다.` : "선택하지 않아도 서비스를 이용할 수 있습니다."}</small></span></label>
        </div>
        <p className="inline-legal">동의 전에 <Link to="/privacy">개인정보 처리방침</Link>과 <Link to="/terms">이용약관</Link>을 확인할 수 있습니다.</p>
        <ErrorNotice error={consentStateError} onRetry={loadConsentState} />
        <ErrorNotice error={error} />
        <SuccessNotice>{coreRecorded && marketingRecorded ? "필수 동의와 선택 동의가 이미 기록되어 있습니다." : coreRecorded ? "필수 동의는 이미 기록되어 있습니다. 선택 동의를 추가로 기록할 수 있습니다." : ""}</SuccessNotice>
        <button className="button full" disabled={busy || consentStateLoading || Boolean(consentStateError)}>{consentStateLoading ? "기존 동의 확인 중…" : busy ? "동의 기록 중…" : coreRecorded && marketingRecorded ? "기존 동의로 계속" : coreRecorded && marketing ? "선택 동의 기록하고 계속" : returnTo === "/candidate/resume" ? "동의하고 이력서 작성" : "동의하고 이전 화면으로 돌아가기"}</button>
      </form>
    </section>
  );
}

const blankResume = { phone: "", birth_date: "", address_region: "", education: "", desired_role: "", years_experience: 0, skills: "", certificates: "", self_intro: "" };

function resumeFormFromResponse(data = {}) {
  return {
    phone: data.phone || "",
    birth_date: data.birth_date || "",
    address_region: data.address_region || "",
    education: data.education || "",
    desired_role: data.desired_role || "",
    years_experience: Number(data.years_experience ?? 0),
    skills: Array.isArray(data.skills) ? data.skills.join(", ") : "",
    certificates: Array.isArray(data.certificates) ? data.certificates.join(", ") : "",
    self_intro: data.self_intro || ""
  };
}

function ResumePage() {
  const { resumeDraft, setResumeDraft } = useAuth();
  const beginRequest = useRequestEpoch();
  const [form, setForm] = useState(blankResume);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [loadError, setLoadError] = useState(null);
  const [error, setError] = useState(null);
  const [message, setMessage] = useState("");
  const baselineRef = useRef(JSON.stringify(blankResume));
  const pendingDraftRef = useRef(resumeDraft);
  const applyLoadedResume = (baseline) => {
    baselineRef.current = JSON.stringify(baseline);
    const pendingDraft = pendingDraftRef.current;
    setForm(pendingDraft ? { ...pendingDraft } : baseline);
    if (pendingDraft) {
      pendingDraftRef.current = null;
      setResumeDraft(null);
    }
  };
  const load = () => {
    const isCurrent = beginRequest();
    setLoading(true);
    setLoadError(null);
    setError(null);
    setMessage("");
    api("/api/v1/candidates/me/resume")
      .then((data) => {
        if (!isCurrent()) return;
        applyLoadedResume(resumeFormFromResponse(data));
      })
      .catch((caught) => {
        if (!isCurrent()) return;
        if (caught.status === 404) {
          applyLoadedResume({ ...blankResume });
        } else {
          setLoadError(caught);
        }
      })
      .finally(() => { if (isCurrent()) setLoading(false); });
  };
  useEffect(() => { load(); }, []);
  const dirty = !loading && !loadError && JSON.stringify(form) !== baselineRef.current;
  useUnsavedChanges(dirty, "저장하지 않은 이력서 변경 내용이 있습니다. 다른 화면으로 이동할까요?");
  const update = (field) => (event) => setForm({ ...form, [field]: event.target.value });
  const submit = async (event) => {
    event.preventDefault(); setBusy(true); setError(null); setMessage("");
    const payload = { ...form, years_experience: Number(form.years_experience), birth_date: form.birth_date || null, skills: form.skills.split(",").map((v) => v.trim()).filter(Boolean), certificates: form.certificates.split(",").map((v) => v.trim()).filter(Boolean) };
    delete payload.id; delete payload.user_id; delete payload.updated_at; delete payload.display_name; delete payload.email;
    try {
      const saved = await api("/api/v1/candidates/me/resume", { method: "POST", body: jsonBody(payload) });
      const normalized = resumeFormFromResponse(saved);
      setForm(normalized);
      baselineRef.current = JSON.stringify(normalized);
      setResumeDraft(null);
      setMessage("이력서를 저장했습니다.");
    }
    catch (caught) { setError(caught); } finally { setBusy(false); }
  };
  if (loading) return <section className="content form-page"><PageHeader eyebrow="Candidate profile" title="구조화 이력서" description="저장된 합성 이력서 정보를 불러오고 있습니다." /><Loading label="이력서를 불러오는 중" /></section>;
  if (loadError) return <section className="content form-page"><PageHeader eyebrow="Candidate profile" title="구조화 이력서" description="기존 이력서를 확인하지 못해 편집을 중단했습니다." /><ErrorNotice error={loadError} onRetry={load} /><ConsentRecovery error={loadError} /></section>;
  return (
    <section className="content form-page">
      <PageHeader eyebrow="Candidate profile" title="구조화 이력서" description="조건 일치 점수에는 직무·기술·경력 구조화 항목이 사용됩니다." actions={<Link className="button quiet" to="/candidate/recommendations">조건 일치 공고 보기</Link>} />
      <form className="resume-form" onSubmit={submit}>
        <fieldset><legend>기본 정보</legend><div className="form-grid three">
          <label><span>연락처</span><input name="phone" type="tel" autoComplete="tel" inputMode="tel" pattern="010-0000-[0-9]{4}" value={form.phone} onChange={update("phone")} placeholder="010-0000-0000" required /></label>
          <label><span>생년월일</span><input name="birth_date" type="date" autoComplete="bday" value={form.birth_date} onChange={update("birth_date")} /></label>
          <label><span>거주 지역</span><input name="address_region" autoComplete="address-level2" value={form.address_region} onChange={update("address_region")} placeholder="시/도 시군구" required /></label>
        </div></fieldset>
        <fieldset><legend>직무 정보</legend><div className="form-grid two">
          <label><span>희망 직무</span><input name="desired_role" autoComplete="organization-title" value={form.desired_role} onChange={update("desired_role")} placeholder="백엔드 엔지니어" required /></label>
          <label><span>관련 경력</span><div className="suffix-input"><input name="years_experience" type="number" min="0" max="60" value={form.years_experience} onChange={update("years_experience")} /><span>년</span></div></label>
          <label className="wide-field"><span>보유 기술</span><input name="skills" autoComplete="off" value={form.skills} onChange={update("skills")} placeholder="Python, FastAPI, PostgreSQL" required /><small>쉼표로 구분해 주세요.</small></label>
          <label><span>학력</span><input name="education" autoComplete="organization" value={form.education} onChange={update("education")} placeholder="합성 교육기관 · 전공" required /></label>
          <label><span>자격증</span><input name="certificates" autoComplete="off" value={form.certificates} onChange={update("certificates")} placeholder="합성 자격증 A" /></label>
        </div></fieldset>
        <fieldset><legend>자기소개</legend><label><span>경험과 강점</span><textarea name="self_intro" rows="7" value={form.self_intro} onChange={update("self_intro")} placeholder="실제 개인정보가 아닌 합성 문장을 입력하세요." /></label></fieldset>
        <ErrorNotice error={error} /><ConsentRecovery error={error} onContinue={() => setResumeDraft({ ...form })} /><SuccessNotice>{message}</SuccessNotice>
        <div className="form-actions"><button className="button" disabled={busy}>{busy ? "저장 중…" : "이력서 저장"}</button></div>
      </form>
    </section>
  );
}

function CandidateApplicationsPage() {
  const [items, setItems] = useState(null); const [error, setError] = useState(null);
  const load = () => { setItems(null); setError(null); api("/api/v1/candidates/me/applications").then(setItems).catch(setError); };
  useEffect(load, []);
  return <section className="content"><PageHeader eyebrow="Application tracker" title="지원 현황" description="지원한 공고와 현재 전형 단계를 확인합니다." />
    <ErrorNotice error={error} onRetry={load} />{!items && !error ? <Loading /> : items?.length ? <div className="application-list">{items.map((item) => <article key={item.id} className="application-row"><div className="application-date"><time dateTime={item.applied_at}>{new Intl.DateTimeFormat("ko-KR", { month: "short", day: "numeric" }).format(new Date(item.applied_at))}</time><small>지원일</small></div><div className="application-main"><span>{item.job.company_name}</span><h2><Link to={`/jobs/${item.job.id}`}>{item.job.title}</Link></h2><p>{item.job.location} · {item.job.employment_type}</p></div><span className={`status-pill status-${item.status}`}>{statusLabels[item.status]}</span></article>)}</div> : items ? <EmptyState title="아직 지원한 공고가 없습니다" body="열린 포지션을 살펴보고 첫 지원을 시작해 보세요." action={<Link className="button" to="/jobs">채용공고 보기</Link>} /> : null}</section>;
}

function SignalRail({ features }) {
  return <div className="signal-rail">{features.length ? features.map((feature, index) => <div className="signal-item" key={`${feature}-${index}`}><span className="signal-node" /><span>{feature}</span></div>) : <div className="signal-item muted"><span className="signal-node" /><span>확인된 일치 항목 없음</span></div>}</div>;
}

function Explanation({ explanation, subjectLabel = "" }) {
  if (explanation?.status === "AVAILABLE" && explanation.text) {
    const validationLabel = explanation.output_validation_state === "NOT_IMPLEMENTED_ASIS"
      ? "근거 검증 미적용"
      : "검증 상태 확인 필요";
    const injected = explanation.generation_mode === "synthetic-overclaim-injection";
    return (
      <div className={injected ? "explanation flagged" : "explanation"}>
        <div className="explanation-heading"><strong>점수 설명 문장</strong><span className="verify-badge">{validationLabel}</span></div>
        <p className="explanation-warning" role="note">
          {injected
            ? "과장 표현 주입 모드로 생성된 시연 문장입니다. 채용 우선순위나 선발 의미로 사용하지 마세요."
            : "이 생성 설명은 의미 검증을 거치지 않았습니다. 사실이나 채용 판단 근거로 확정하지 마세요."}
        </p>
        <details className="generated-explanation">
          <summary>검증되지 않은 생성 설명 원문 보기{subjectLabel && <span className="sr-only"> · {subjectLabel}</span>}</summary>
          <p>{explanation.text}</p>
          <small>생성기: {explanation.generation_mode || explanation.provider || "미상"} · 이 문장은 점수와 정렬을 바꾸지 않습니다.</small>
        </details>
      </div>
    );
  }
  return <div className="explanation-unavailable" role="note"><strong>점수 설명 문장을 생성하지 못했습니다.</strong><span>조건 일치 점수와 요인별 기여도는 결정론적 매처 결과로 유지됩니다.</span></div>;
}

function CacheObservation({ cache, audience = "candidate" }) {
  if (cache !== "hit") return null;
  const dataBoundary = audience === "recruiter"
    ? "지원자 수와 후보자 자료는 캐시 생성 당시 조회된 지원자 집합입니다. 신규 지원·동의 철회·탈퇴·이력서 변경을 이번 요청에서 다시 조회했다는 뜻이 아닙니다."
    : "공고와 점수 자료는 캐시 생성 당시 응답입니다. 이력서·공고 변경을 이번 요청에서 다시 계산했다는 뜻이 아닙니다.";
  return <p className="asis-observation cache-observation"><span>AS-IS 관찰</span> {dataBoundary} 모든 무효화 경로가 연결됐다고 보장하지 않으며, 설명 공급자 상태도 이번 요청에서 다시 확인하지 않았습니다.</p>;
}

const explanationStatusLabels = {
  AVAILABLE: "설명 제공됨",
  UNAVAILABLE_PROVIDER: "설명 생성 불가"
};

const cacheLabels = {
  hit: "캐시 응답",
  miss: "새로 계산한 응답"
};

function RecommendationMeta({ data }) {
  const explanationLabel = data.explanation_freshness === "CACHE_HIT_PROVIDER_NOT_REVALIDATED"
    ? "캐시된 설명 · 현재 공급자 상태 미확인"
    : explanationStatusLabels[data.explanation_status] || "상태 확인 필요";
  return <div className="recommendation-meta"><span>점수 엔진 · <span translate="no">{data.matcher_version}</span></span><span>설명 · {explanationLabel}</span><span>응답 · {cacheLabels[data.cache] || "출처 확인 필요"}</span></div>;
}

function RecommendationLoadStatus({ data, noun }) {
  if (!data) return null;
  const items = Array.isArray(data.items) ? data.items : [];
  const unavailableCount = items.filter((item) => item.explanation?.status !== "AVAILABLE").length;
  const injectedCount = items.filter((item) => item.explanation?.generation_mode === "synthetic-overclaim-injection").length;
  const explanationSummary = unavailableCount
    ? ` 점수 설명을 생성하지 못한 결과 ${unavailableCount}건이 있습니다.`
    : injectedCount
      ? ` 과장 표현 주입 시연 결과 ${injectedCount}건이 있습니다.`
      : "";
  return <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">{noun} {items.length}건의 조건 일치 결과가 준비되었습니다.{explanationSummary}</p>;
}

function CandidateRecommendationsPage() {
  const beginRequest = useRequestEpoch();
  const [data, setData] = useState(null); const [error, setError] = useState(null); const [loading, setLoading] = useState(true);
  const [comparisonIds, setComparisonIds] = useState([]);
  const load = async ({ preserve = true } = {}) => {
    const isCurrent = beginRequest();
    setLoading(true); setError(null);
    if (!preserve) setData(null);
    try {
      const result = await api("/api/v1/candidates/me/recommendations");
      if (isCurrent()) setData(result);
    } catch (caught) {
      if (isCurrent()) setError(caught);
    } finally {
      if (isCurrent()) setLoading(false);
    }
  };
  useEffect(() => { load({ preserve: false }); }, []);
  useEffect(() => {
    const availableIds = new Set((data?.items || []).map((item) => item.job.id));
    setComparisonIds((current) => current.filter((id) => availableIds.has(id)));
  }, [data]);
  const toggleComparison = (jobId) => {
    setComparisonIds((current) => current.includes(jobId)
      ? current.filter((id) => id !== jobId)
      : current.length < 3 ? [...current, jobId] : current);
  };
  const comparisonItems = comparisonIds
    .map((jobId) => data?.items?.find((item) => item.job.id === jobId))
    .filter(Boolean);
  const resumeRequired = error?.status === 409 && /이력서/.test(error.message || "");
  return <section className="content wide candidate-match-workbench" aria-busy={loading && !data}><PageHeader eyebrow="Structured match" title="내 조건과 일치하는 공고" description="직무 관련 구조화 항목만으로 점수를 계산하고, 최대 3개 공고의 일치 근거를 같은 화면에서 비교합니다." actions={<button type="button" className="button quiet" disabled={loading} onClick={() => load()}>{loading ? "결과 불러오는 중…" : "결과 새로 불러오기"}</button>} /><ErrorNotice error={error} onRetry={resumeRequired ? undefined : () => load()} /><RecommendationLoadStatus data={data} noun="공고" />
    <ConsentRecovery error={error} />
    <ResumeRecovery error={error} />
    {loading && data && <p className="ranking-basis" role="status" aria-live="polite" aria-atomic="true">기존 결과를 표시한 채 새 결과를 불러오는 중…</p>}
    {error && data && <p className="ranking-basis" role="status" aria-live="polite" aria-atomic="true">갱신에 실패해 직전 성공 결과를 유지하고 있습니다.</p>}
    {data && <><RecommendationMeta data={data} /><CacheObservation cache={data.cache} audience="candidate" /></>}
    <CandidateJobComparison items={comparisonItems} onRemove={toggleComparison} onClear={() => setComparisonIds([])} />
    {loading && !data ? <Loading label="조건 일치 점수와 설명을 불러오는 중" /> : data?.items?.length ? <div className="recommendation-list candidate-ranking">{data.items.map((item, index) => {
      const subjectLabel = `조건 일치 결과 ${index + 1}, ${item.job.company_name} ${item.job.title}`;
      const selected = comparisonIds.includes(item.job.id);
      const selectionDisabled = !selected && comparisonIds.length >= 3;
      return <article className={`recommendation-card candidate-recommendation${selected ? " is-selected" : ""}`} key={item.job.id}>
        <div className="candidate-match-tools"><span>추천 순서 {String(index + 1).padStart(2, "0")}</span><label className="candidate-compare"><input type="checkbox" checked={selected} disabled={selectionDisabled} onChange={() => toggleComparison(item.job.id)} /><span>{selected ? "비교에 담김" : selectionDisabled ? "최대 3개" : "근거 비교"}</span></label></div>
        <div className="recommendation-top"><div><span className="company-label">{item.job.company_name}</span><h2><Link to={`/jobs/${item.job.id}`}>{item.job.title}</Link></h2><p>{item.job.location} · 경력 {item.job.min_experience}년 이상</p></div><Score value={item.score} /></div>
        <ScoreDisclosure breakdown={item.score_breakdown} explanation={item.explanation} explanationAttempt={data.explanation_attempt} audience="candidate" subjectLabel={subjectLabel} />
        <CompanyAlignment alignment={item.explanation?.company_alignment} profileSource={item.job.company_profile?.source} />
        <SignalRail features={item.matched_feature_labels} />
        <Explanation explanation={item.explanation} subjectLabel={subjectLabel} />
        <div className="card-actions"><Link className="button small" to={`/jobs/${item.job.id}`} aria-label={`${item.job.title} 공고 상세 보기`}>공고 상세</Link></div>
      </article>;
    })}</div> : data ? <EmptyState title="현재 응답에 열린 공고가 없습니다" body="캐시 응답이면 캐시 생성 당시의 공고 집합입니다. 이력서 내용 부족을 뜻하지 않습니다." action={<Link className="button" to="/jobs">채용공고 목록 보기</Link>} /> : null}
  </section>;
}

function WithdrawPage() {
  const { logout } = useAuth(); const navigate = useNavigate(); const beginRequest = useRequestEpoch();
  const [confirmed, setConfirmed] = useState(false); const [error, setError] = useState(null); const [message, setMessage] = useState("");
  const [errorAction, setErrorAction] = useState(null);
  const [actionBusy, setActionBusy] = useState(null); const [consents, setConsents] = useState(null); const [consentLoading, setConsentLoading] = useState(true);
  const loadConsents = async () => {
    const isCurrent = beginRequest();
    setConsentLoading(true); setError(null); setErrorAction(null);
    try {
      const result = await api("/api/v1/candidates/me/consents");
      if (isCurrent()) setConsents(result);
    } catch (caught) {
      if (isCurrent()) { setError(caught); setErrorAction("load"); }
    } finally {
      if (isCurrent()) setConsentLoading(false);
    }
  };
  useEffect(() => { loadConsents(); }, []);
  const latestAction = (consentType) => consents?.find((event) => event.consent_type === consentType)?.action || null;
  const coreGranted = latestAction("privacy_core") === "grant";
  const marketingGranted = latestAction("marketing") === "grant";
  const revoke = async (consentType) => {
    const core = consentType === "privacy_core";
    const prompt = core
      ? "필수 동의를 철회하면 새 지원, 조건 일치 추천과 이력서 변경이 제한됩니다. 기존 지원 정보의 기업 화면 열람은 현재 API에서 별도로 차단되지 않습니다. 계속할까요?"
      : "선택 마케팅 정보 수신 동의를 철회할까요?";
    if (!window.confirm(prompt)) return;
    setActionBusy(consentType); setError(null); setErrorAction(null); setMessage("");
    try {
      await api(`/api/v1/candidates/me/consents/${consentType}`, { method: "DELETE" });
      setConsents((current) => [{ consent_type: consentType, action: "revoke" }, ...(current || [])]);
      setMessage(core ? "통합 동의 철회 이벤트를 기록했습니다." : "선택 마케팅 동의 철회 이벤트를 기록했습니다.");
    }
    catch (caught) { setError(caught); setErrorAction(consentType); } finally { setActionBusy(null); }
  };
  const withdraw = async () => {
    if (!confirmed) { setError(new Error("탈퇴 내용을 확인해 주세요.")); setErrorAction(null); return; }
    setActionBusy("withdraw"); setError(null); setErrorAction(null); setMessage("");
    try { await api("/api/v1/candidates/me", { method: "DELETE" }); logout(""); navigate("/jobs", { state: { notice: "탈퇴 처리가 접수되었습니다." } }); }
    catch (caught) { setError(caught); setErrorAction("withdraw"); } finally { setActionBusy(null); }
  };
  const retryFailedAction = errorAction === "load"
    ? loadConsents
    : errorAction === "withdraw"
      ? withdraw
      : errorAction
        ? () => revoke(errorAction)
        : undefined;
  const latestCoreAction = latestAction("privacy_core");
  const latestMarketingAction = latestAction("marketing");
  return (
    <section className="content narrow">
      <PageHeader eyebrow="Privacy controls" title="동의와 계정 관리" description="필수·선택 동의의 최신 이벤트와 회원 탈퇴를 각각 관리합니다." />
      <div className="danger-stack">
        <article className="control-card">
          <div><h2>선택 마케팅 정보 수신</h2><p role="status">{consentLoading ? "최신 동의 이벤트를 확인하는 중입니다." : marketingGranted ? "현재 최신 이벤트는 수신 동의입니다." : latestMarketingAction === "revoke" ? "현재 최신 이벤트는 수신 철회입니다." : "기록된 선택 동의 이벤트가 없습니다."}</p></div>
          <button className="button quiet" disabled={Boolean(actionBusy) || consentLoading || !marketingGranted} onClick={() => revoke("marketing")}>{actionBusy === "marketing" ? "철회 처리 중…" : marketingGranted ? "선택 동의 철회" : latestMarketingAction === "revoke" ? "선택 동의 철회됨" : "철회할 동의 없음"}</button>
        </article>
        <article className="control-card">
          <div><h2>개인정보 수집·이용 동의 철회</h2><p role="status">{consentLoading ? "최신 동의 이벤트를 확인하는 중입니다." : coreGranted ? "현재 최신 이벤트는 필수 동의입니다." : latestCoreAction === "revoke" ? "현재 최신 이벤트는 필수 동의 철회입니다." : "기록된 필수 동의 이벤트가 없습니다."}</p></div>
          <button className="button quiet" disabled={Boolean(actionBusy) || consentLoading || !coreGranted} onClick={() => revoke("privacy_core")}>{actionBusy === "privacy_core" ? "철회 처리 중…" : coreGranted ? "필수 동의 철회" : latestCoreAction === "revoke" ? "필수 동의 철회됨" : "철회할 동의 없음"}</button>
        </article>
        <article className="control-card danger"><div><h2>회원 탈퇴</h2><p>주 데이터베이스의 계정·이력서·지원정보 처리를 시작합니다. 모든 저장면에서 완전 삭제됐다고 이 화면에서 단정하지 않습니다.</p><label className="check-row compact"><input name="withdraw_confirmed" type="checkbox" checked={confirmed} disabled={Boolean(actionBusy)} onChange={(e) => setConfirmed(e.target.checked)} /><span>탈퇴 후 현재 계정으로 로그인할 수 없음을 확인했습니다.</span></label></div><button className="button danger-button" disabled={Boolean(actionBusy)} onClick={withdraw}>{actionBusy === "withdraw" ? "탈퇴 처리 중…" : "회원 탈퇴"}</button></article>
      </div>
      <ErrorNotice error={error} onRetry={retryFailedAction} /><SuccessNotice>{message}</SuccessNotice>
    </section>
  );
}

function RecruiterSignupPage() {
  const { establish } = useAuth(); const navigate = useNavigate();
  const [form, setForm] = useState({ display_name: "", email: "", password: "", company_name: "", company_address: "" }); const [error, setError] = useState(null); const [busy, setBusy] = useState(false);
  const update = (field) => (event) => setForm({ ...form, [field]: event.target.value });
  const submit = async (event) => { event.preventDefault(); setBusy(true); setError(null); try { const result = await api("/api/v1/auth/signup/recruiter", { method: "POST", body: jsonBody(form) }); establish(result); navigate("/recruiter/overview"); } catch (caught) { setError(caught); } finally { setBusy(false); } };
  return (
    <AuthLayout title="기업회원 가입" description="합성 기업과 첫 담당자 계정을 만듭니다. 가입 경로는 담당자 1명을 만들지만 기업별 담당자 수를 제한하는 DB 제약은 없습니다." aside={<><p className="eyebrow light">Recruiter workspace</p><p className="auth-promo-title">공고부터 조건 일치 검토까지 한곳에서.</p><p>지원자 파이프라인과 결정론적 조건 일치 결과를 직접 확인할 수 있습니다.</p></>}>
      <form className="stack-form" onSubmit={submit} aria-busy={busy}>
        <label><span>담당자 이름</span><input name="display_name" autoComplete="name" value={form.display_name} onChange={update("display_name")} required minLength={2} maxLength={100} /></label>
        <label><span>업무 이메일</span><input name="email" type="email" autoComplete="email" spellCheck={false} aria-describedby="recruiter-email-help" value={form.email} onChange={update("email")} placeholder="recruiter@example.invalid" required minLength={3} maxLength={254} /><small id="recruiter-email-help">합성 전용 @jcareer.test 또는 @example.invalid 주소만 입력하세요.</small></label>
        <label><span>비밀번호</span><input name="password" type="password" autoComplete="new-password" minLength={8} maxLength={128} value={form.password} onChange={update("password")} required /></label>
        <label><span>기업명</span><input name="company_name" autoComplete="organization" value={form.company_name} onChange={update("company_name")} placeholder="합성기업 이름" required minLength={2} maxLength={120} /></label>
        <label><span>근무지 주소</span><input name="company_address" autoComplete="street-address" value={form.company_address} onChange={update("company_address")} placeholder="시/도 시군구" required minLength={2} maxLength={240} /></label>
        <ErrorNotice error={error} />
        <button type="submit" className="button full" disabled={busy}>{busy ? "기업 계정 생성 중…" : "기업 계정 만들기"}</button>
      </form>
      <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">{busy ? "기업 계정 생성 요청을 처리하고 있습니다." : ""}</p>
      <p className="form-switch">이미 기업 계정이 있나요? <Link to="/login">로그인</Link></p>
    </AuthLayout>
  );
}

const blankJob = { title: "", summary: "", location: "", employment_type: "정규직", required_skills: "", min_experience: 0, status: "open" };

function RecruiterOverviewPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const load = () => { setError(null); api("/api/v1/recruiter/overview").then(setData).catch(setError); };
  useEffect(load, []);

  if (!data && !error) return <section className="content"><PageHeader eyebrow="Company workspace" title="기업 채용 운영 홈" description="기업 고객의 합성 운영 현황을 불러오고 있습니다." /><Loading label="기업 워크스페이스를 불러오는 중" /></section>;
  const metrics = data?.metrics || {};
  const company = data?.company || {};
  return (
    <section className="content">
      <PageHeader eyebrow="Company workspace" title="기업 채용 운영 홈" description="기업 고객의 공고와 지원자 흐름을 회사 단위로 확인합니다. 아래 수치는 합성 운영 현황이며 채용 판단이나 규제 판정이 아닙니다." actions={<><Link className="button quiet" to="/recruiter/jobs#company-profile">기업 방향 편집</Link><Link className="button" to="/recruiter/jobs">채용공고 관리</Link></>} />
      <ErrorNotice error={error} onRetry={load} />
      {data && <>
        <article className="company-overview-hero">
          <div className="company-monogram" aria-hidden="true">{company.company_name?.slice(0, 1)}</div>
          <div className="company-overview-copy">
            <span>합성 기업 고객 워크스페이스</span>
            <h2>{company.company_name}</h2>
            <p>{company.company_address || "등록된 기업 주소 없음"}</p>
          </div>
          <div className="company-profile-snapshot">
            <span>기업 선언 프로필</span>
            <strong>{company.profile_version}</strong>
            <ProfileSource source={company.source} />
            <p>{company.direction_statement || "기업 방향을 아직 등록하지 않았습니다."}</p>
            <SkillList skills={company.declared_values || []} />
          </div>
        </article>

        <OpenDartCompanyFacts opendart={company.opendart} />

        <div className="overview-metrics" aria-label="기업 채용 운영 지표">
          <article><span>공개 공고</span><strong>{metrics.open_jobs ?? 0}</strong><small>현재 지원 가능한 공고</small></article>
          <article><span>마감 공고</span><strong>{metrics.closed_jobs ?? 0}</strong><small>회사 소유 전체 공고 기준</small></article>
          <article><span>누적 지원</span><strong>{metrics.total_applications ?? 0}</strong><small>중복 지원 관계를 포함한 건수</small></article>
          <article><span>진행 중 관계</span><strong>{metrics.active_pipeline ?? 0}</strong><small>전형 종료를 제외한 운영 건수</small></article>
        </div>

        <div className="overview-columns">
          <section className="overview-panel" aria-labelledby="stage-heading">
            <div className="panel-heading"><div><p className="eyebrow">Pipeline facts</p><h2 id="stage-heading">전형 단계 현황</h2></div><span>회사 범위</span></div>
            <div className="stage-list">
              {data.application_stages.map((stage) => <div className="stage-row" key={stage.status}><div><span className={`stage-dot stage-${stage.status}`} aria-hidden="true" /><strong>{stage.label}</strong></div><span>{stage.count}건</span></div>)}
            </div>
          </section>

          <aside className="boundary-panel" aria-labelledby="boundary-heading">
            <p className="eyebrow light">Customer & data boundary</p>
            <h2 id="boundary-heading">기업 고객과 데이터 경계</h2>
            <dl className="boundary-facts">
              <div><dt>현재 연결 모델</dt><dd>{data.customer_boundary.identity_model === "recruiter-company-logical-link-no-cardinality-constraint" ? "담당자 사용자에서 기업을 가리키는 논리 참조" : `알 수 없는 계약 · ${data.customer_boundary.identity_model}`}</dd></div>
              <div><dt>가입 생성 단위</dt><dd>{data.customer_boundary.signup_recruiter_creation === "one-recruiter-with-new-company" ? "새 기업과 첫 담당자 1명 생성" : `알 수 없는 계약 · ${data.customer_boundary.signup_recruiter_creation}`}</dd></div>
              <div><dt>기업별 담당자 수 제약</dt><dd>{data.customer_boundary.company_recruiter_cardinality_constraint ? "DB 제약 존재 · 별도 확인 필요" : "DB 제약 없음 · 가입 동작을 기업당 1인 불변식으로 해석하지 않음"}</dd></div>
              <div><dt>가입 초기 상태</dt><dd>{data.customer_boundary.company_signup_initial_status_source === "approved-model-default-without-review-transition" ? <>소스 상태 · 모델 기본값 <code>approved</code>, 별도 검토 전환 없음</> : `알 수 없는 계약 · ${data.customer_boundary.company_signup_initial_status_source}`}</dd></div>
              <div><dt>조직 멤버십·역할</dt><dd>{data.customer_boundary.organization_membership_implemented || data.customer_boundary.invite_and_role_lifecycle_implemented ? "응답 선언 true · 범위 별도 확인 필요" : "응답 선언 false · 이 런타임 소스에서 초대, 세분 역할, 퇴사자 권한 회수 경로를 확인하지 못함"}</dd></div>
              <div><dt>기업 계정 연속성</dt><dd>{data.customer_boundary.company_account_withdrawal_implemented || data.customer_boundary.company_ownership_transfer_implemented ? "응답 선언 true · 범위 별도 확인 필요" : "응답 선언 false · 이 런타임 소스에서 담당자 탈퇴와 기업 소유권 이전 경로를 확인하지 못함"}</dd></div>
              <div><dt>기업 동의·상태 변경</dt><dd>{data.customer_boundary.company_consent_lifecycle_implemented ? "응답 선언 true · 범위 별도 확인 필요" : "응답 선언 false · 기업 동의 이벤트 경로 미확인"} · {data.customer_boundary.company_status_transition_implemented || data.customer_boundary.company_status_actor_modeled ? "응답 선언 true · 범위 별도 확인 필요" : "응답 선언 false · 상태 전환 API와 전환 행위자 모델 미확인"}</dd></div>
              <div><dt>기업 상태 게이트</dt><dd>원본 레코드 <code>{data.customer_boundary.company_status_record}</code> · {data.customer_boundary.company_status_gate_enforced ? "응답 선언 true · 적용 범위 별도 확인 필요" : "응답 선언 false · 이 런타임 업무 API 권한 판단에서 사용되지 않음"}</dd></div>
              <div><dt>기업 DB</dt><dd>{data.data_boundary.company_database.join(" · ")}</dd></div>
              <div><dt>회원 DB</dt><dd>{data.data_boundary.member_database.join(" · ")}</dd></div>
              <div className="boundary-span"><dt>교차 DB 참조·복구</dt><dd>{data.data_boundary.application_job_reference === "logical_id_without_cross_database_foreign_key" ? "지원은 공고 UUID를 논리 참조" : "참조 방식 확인 필요"} · {data.data_boundary.cross_database_atomic_commit ? "원자적 커밋 응답 선언 true · 범위 확인 필요" : "원자적 커밋 응답 선언 false"} · {data.data_boundary.company_signup_operation_id_implemented ? "가입 operation ID 응답 선언 true · 범위 확인 필요" : "가입 operation ID 응답 선언 false"} · {data.data_boundary.company_signup_idempotency_key_implemented ? "가입 멱등 키 응답 선언 true · 범위 확인 필요" : "가입 멱등 키 응답 선언 false"} · {data.data_boundary.cross_database_compensation_implemented ? "보상 경로 응답 선언 true · 범위 확인 필요" : "보상 경로 응답 선언 false"} · {data.data_boundary.cross_database_reconciliation_implemented ? "사후 조정 경로 응답 선언 true · 범위 확인 필요" : "사후 조정 경로 응답 선언 false"} · {data.data_boundary.cross_database_outbox_implemented ? "outbox 응답 선언 true · 범위 확인 필요" : "outbox 응답 선언 false"}</dd></div>
            </dl>
            <small>현재 런타임 응답의 source-state 선언을 보여 주는 AS-IS 관찰면입니다. 다른 저장소·절차의 부재나 계정 수명주기·데이터 정합성의 충분성을 판정하지 않습니다.</small>
          </aside>
        </div>

        <section className="recent-jobs" aria-labelledby="recent-jobs-heading">
          <div className="panel-heading"><div><p className="eyebrow">Recent jobs</p><h2 id="recent-jobs-heading">최근 채용공고</h2></div><Link className="text-link" to="/recruiter/jobs">전체 관리 →</Link></div>
          {data.recent_jobs.length ? <div className="recent-job-grid">{data.recent_jobs.map((job) => <article key={job.id}><div><span className={`status-pill status-${job.status}`}>{statusLabels[job.status]}</span><h3>{job.title}</h3><p>{job.location} · 경력 {job.min_experience}년 이상</p></div><div className="recent-job-footer"><strong>{job.application_count}</strong><span>지원자</span><Link to={`/recruiter/jobs/${job.id}/pipeline`} aria-label={`${job.title} 지원자 파이프라인 보기`}>파이프라인 →</Link></div></article>)}</div> : <EmptyState title="등록한 공고가 없습니다" body="첫 공고를 등록하면 기업 홈에 운영 현황이 표시됩니다." action={<Link className="button" to="/recruiter/jobs">공고 등록하기</Link>} />}
        </section>
      </>}
    </section>
  );
}

function OpenDartProfileEditor({ profile, onUpdated }) {
  const [corpCode, setCorpCode] = useState(profile?.opendart?.corp_code || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [message, setMessage] = useState("");
  useEffect(() => { setCorpCode(profile?.opendart?.corp_code || ""); }, [profile?.opendart?.corp_code]);
  const submit = async (event) => {
    event.preventDefault();
    setBusy(true); setError(null); setMessage("");
    try {
      const result = await api("/api/v1/recruiter/company-profile/opendart/refresh", {
        method: "POST",
        body: jsonBody({ corp_code: corpCode })
      });
      onUpdated(result.company_profile);
      setMessage(result.refresh?.state === "QUEUED" ? "OpenDART 공개정보 갱신 요청을 대기열에 등록했습니다." : "OpenDART 공개정보의 합성 예시를 새로 저장했습니다.");
    } catch (caught) {
      setError(caught);
      api("/api/v1/recruiter/company-profile").then(onUpdated).catch(() => {});
    } finally { setBusy(false); }
  };
  const dart = profile?.opendart || {};
  return (
    <section className="opendart-editor" aria-labelledby="opendart-editor-heading">
      <div className="opendart-editor-copy">
        <p className="eyebrow">기업 공개정보 연결</p>
        <h2 id="opendart-editor-heading">공시 기업정보 연결</h2>
        <p>OpenDART 고유번호로 회사개황과 최근 공시를 조회해 별도 복사본으로 저장합니다. 기업명·주소·채용 방향을 자동 덮어쓰지 않으며 기업 인증 수단도 아닙니다.</p>
        <dl className="opendart-link-meta">
          <div><dt>연결 상태</dt><dd>{openDartStateLabels[dart.state] || "상태 확인 필요"}</dd></div>
          <div><dt>저장본 버전</dt><dd>{dart.snapshot_version || "없음"}</dd></div>
          <div><dt>마지막 시도</dt><dd>{snapshotTime(dart.last_attempt_at)}</dd></div>
        </dl>
      </div>
      <form className="opendart-link-form" onSubmit={submit} aria-busy={busy}>
        <label><span>OpenDART 고유번호</span><input name="corp_code" inputMode="numeric" autoComplete="off" minLength="8" maxLength="8" pattern="[0-9]{8}" value={corpCode} onChange={(event) => setCorpCode(event.target.value.replace(/\D/g, "").slice(0, 8))} placeholder="숫자 8자리" required /><small>합성 데모 기업은 90000001~90000003 예시를 사용합니다. 외부 조회 모드는 별도 키와 사람 승인 없이 동작하지 않습니다.</small></label>
        <p className="opendart-score-boundary" role="note"><strong>점수 반영 없음</strong> 이 정보는 기업 상세를 설명하는 공시 출처이며 조건 일치 점수나 생성형 설명 입력에 포함되지 않습니다.</p>
        <ErrorNotice error={error} />
        <SuccessNotice>{message}</SuccessNotice>
        <button className="button small" disabled={busy || corpCode.length !== 8}>{busy ? "조회 중…" : "공개정보 새로고침"}</button>
      </form>
      <OpenDartCompanyFacts opendart={dart} headingLevel="h3" />
    </section>
  );
}

function CompanyProfileEditor() {
  const beginRequest = useRequestEpoch();
  const location = useLocation();
  const [profile, setProfile] = useState(null);
  const [form, setForm] = useState({ direction_statement: "", declared_values: "" });
  const [error, setError] = useState(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const baselineRef = useRef(null);
  const headingRef = useRef(null);
  const load = () => {
    const isCurrent = beginRequest();
    setError(null);
    api("/api/v1/recruiter/company-profile").then((result) => {
      if (!isCurrent()) return;
      const next = { direction_statement: result.direction_statement || "", declared_values: (result.declared_values || []).join(", ") };
      setProfile(result);
      setForm(next);
      baselineRef.current = JSON.stringify(next);
    }).catch((caught) => { if (isCurrent()) setError(caught); });
  };
  useEffect(() => { load(); }, []);
  useEffect(() => {
    if (location.hash !== "#company-profile" || (!profile && !error)) return undefined;
    const frame = window.requestAnimationFrame(() => headingRef.current?.focus());
    return () => window.cancelAnimationFrame(frame);
  }, [error, location.hash, profile]);
  const dirty = Boolean(profile) && JSON.stringify(form) !== baselineRef.current;
  useUnsavedChanges(dirty, "저장하지 않은 기업 방향 프로필 변경 내용이 있습니다. 다른 화면으로 이동할까요?");
  const submit = async (event) => {
    event.preventDefault(); setBusy(true); setError(null); setMessage("");
    try {
      const result = await api("/api/v1/recruiter/company-profile", {
        method: "PUT",
        body: jsonBody({ direction_statement: form.direction_statement, declared_values: form.declared_values.split(",").map((value) => value.trim()).filter(Boolean) })
      });
      const next = { direction_statement: result.direction_statement, declared_values: result.declared_values.join(", ") };
      setProfile(result);
      setForm(next);
      baselineRef.current = JSON.stringify(next);
      setMessage(`기업 방향 프로필을 저장했습니다. 새 버전 ${result.profile_version}`);
    } catch (caught) { setError(caught); } finally { setBusy(false); }
  };
  if (!profile && !error) return <div id="company-profile" className="company-profile-editor"><Loading label="기업 방향 프로필을 불러오는 중" /></div>;
  if (!profile) return <div id="company-profile" className="company-profile-editor"><div className="company-profile-copy"><p className="eyebrow">Company-declared profile</p><h2 ref={headingRef} tabIndex="-1">기업 방향 프로필</h2><p>기존 값을 불러오지 못한 상태에서는 덮어쓰지 않습니다.</p></div><ErrorNotice error={error} onRetry={load} /></div>;
  return <><form id="company-profile" className="company-profile-editor" onSubmit={submit}><div className="company-profile-copy"><p className="eyebrow">Company-declared profile</p><h2 ref={headingRef} tabIndex="-1">기업 방향 프로필</h2><p>AI가 추측한 기업 성향이 아니라 기업 방향 프로필에 저장된 방향과 가치만 자소서 비교에 사용합니다. 현재 100점 점수에는 합산하지 않습니다.</p>{profile && <div className="profile-provenance"><span className="profile-version">{profile.profile_version}</span><ProfileSource source={profile.source} /></div>}</div><div className="company-profile-fields"><label><span>기업이 추구하는 방향</span><textarea name="direction_statement" rows="3" minLength="20" maxLength="2000" value={form.direction_statement} onChange={(event) => setForm({ ...form, direction_statement: event.target.value })} required /></label><label><span>핵심가치</span><input name="declared_values" autoComplete="off" value={form.declared_values} onChange={(event) => setForm({ ...form, declared_values: event.target.value })} placeholder="신뢰, 협업, 자동화" required /><small>쉼표로 구분해 1~10개를 입력합니다.</small></label><ErrorNotice error={error} /><SuccessNotice>{message}</SuccessNotice><button className="button small" disabled={busy}>{busy ? "저장 중…" : "기업 방향 저장"}</button></div></form><OpenDartProfileEditor profile={profile} onUpdated={setProfile} /></>;
}

function RecruiterJobsPage() {
  const beginRequest = useRequestEpoch();
  const [jobs, setJobs] = useState(null);
  const [form, setForm] = useState({ ...blankJob });
  const [editingId, setEditingId] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [loadError, setLoadError] = useState(null);
  const [actionError, setActionError] = useState(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [statusBusyId, setStatusBusyId] = useState(null);
  const editorToggleRef = useRef(null);
  const firstEditorFieldRef = useRef(null);
  const editorBaselineRef = useRef(JSON.stringify(blankJob));
  const load = async () => {
    const isCurrent = beginRequest();
    setJobs(null); setLoadError(null); setMessage("");
    try {
      const result = await api("/api/v1/recruiter/jobs");
      if (isCurrent()) setJobs(result);
      return isCurrent();
    } catch (caught) {
      if (isCurrent()) setLoadError(caught);
      return false;
    }
  };
  useEffect(() => { load(); }, []);
  const editorDirty = showForm && JSON.stringify(form) !== editorBaselineRef.current;
  useUnsavedChanges(editorDirty, "저장하지 않은 채용공고 변경 내용이 있습니다. 다른 화면으로 이동할까요?");
  const update = (field) => (event) => setForm({ ...form, [field]: event.target.value });
  const focusEditor = () => window.requestAnimationFrame(() => firstEditorFieldRef.current?.focus());
  const resetEditor = (force = false) => {
    if (!force && editorDirty && !window.confirm("저장하지 않은 채용공고 변경 내용을 버릴까요?")) return false;
    setForm({ ...blankJob });
    editorBaselineRef.current = JSON.stringify(blankJob);
    setEditingId(null);
    setActionError(null);
    setShowForm(false);
    window.requestAnimationFrame(() => editorToggleRef.current?.focus());
    return true;
  };
  const beginCreate = () => {
    if (editorDirty && !window.confirm("현재 편집 중인 저장하지 않은 변경 내용을 버리고 새 공고를 작성할까요?")) return;
    const next = { ...blankJob };
    setForm(next);
    editorBaselineRef.current = JSON.stringify(next);
    setEditingId(null);
    setActionError(null);
    setMessage("");
    setShowForm(true);
    focusEditor();
  };
  const beginEdit = (job) => {
    if (editorDirty && !window.confirm("현재 편집 중인 저장하지 않은 변경 내용을 버리고 다른 공고를 열까요?")) return;
    const next = { ...job, required_skills: job.required_skills.join(", ") };
    setForm(next);
    editorBaselineRef.current = JSON.stringify(next);
    setEditingId(job.id);
    setActionError(null);
    setMessage("");
    setShowForm(true);
    window.scrollTo({ top: 0, behavior: "smooth" });
    focusEditor();
  };
  const payload = (source) => ({
    ...source,
    min_experience: Number(source.min_experience),
    required_skills: source.required_skills.split(",").map((value) => value.trim()).filter(Boolean)
  });
  const submit = async (event) => {
    event.preventDefault(); setBusy(true); setActionError(null); setMessage("");
    const wasEditing = Boolean(editingId);
    try {
      await api(editingId ? `/api/v1/recruiter/jobs/${editingId}` : "/api/v1/recruiter/jobs", {
        method: editingId ? "PUT" : "POST",
        body: jsonBody(payload(form))
      });
      resetEditor(true);
      const refreshed = await load();
      if (refreshed) setMessage(wasEditing ? "채용공고 변경 내용을 저장했습니다." : "새 채용공고를 공개했습니다.");
    } catch (caught) { setActionError(caught); } finally { setBusy(false); }
  };
  const changeStatus = async (job, nextStatus) => {
    if (showForm && editingId === job.id) {
      setActionError(new Error("이 공고의 편집기를 닫거나 변경 내용을 저장한 뒤 공개 상태를 바꿔 주세요."));
      focusEditor();
      return;
    }
    if (nextStatus === "closed" && !window.confirm(`‘${job.title}’ 공고를 마감할까요?`)) return;
    setStatusBusyId(job.id);
    setActionError(null);
    setMessage("");
    try {
      const updated = await api(`/api/v1/recruiter/jobs/${job.id}`, {
        method: "PUT",
        body: jsonBody({ ...job, status: nextStatus })
      });
      setJobs((current) => current?.map((row) => row.id === job.id ? { ...row, ...updated } : row));
      setMessage(nextStatus === "closed" ? "채용공고를 마감했습니다." : "채용공고를 다시 공개했습니다.");
    } catch (caught) { setActionError(caught); } finally {
      setStatusBusyId(null);
      window.requestAnimationFrame(() => document.getElementById(`job-status-${job.id}`)?.focus());
    }
  };
  return <section className="content"><PageHeader eyebrow="Recruiter workspace" title="채용공고 관리" description="공고를 등록·수정하고 지원자 파이프라인과 조건 일치 결과로 이동합니다." actions={<button ref={editorToggleRef} className="button" onClick={() => { if (showForm) resetEditor(); else beginCreate(); }}>{showForm ? "편집 닫기" : "새 공고 등록"}</button>} /><CompanyProfileEditor /><ErrorNotice error={actionError} /><SuccessNotice>{message}</SuccessNotice>
    {showForm && <form className="job-editor" onSubmit={submit}><h2>{editingId ? "채용공고 수정" : "새 채용공고"}</h2><div className="form-grid two"><label><span>포지션명</span><input name="title" autoComplete="off" ref={firstEditorFieldRef} value={form.title} onChange={update("title")} required /></label><label><span>근무 지역</span><input name="location" autoComplete="address-level1" value={form.location} onChange={update("location")} required /></label><label><span>고용 형태</span><select name="employment_type" value={form.employment_type} onChange={update("employment_type")}><option>정규직</option><option>계약직</option><option>인턴</option></select></label><label><span>최소 경력</span><div className="suffix-input"><input name="min_experience" type="number" min="0" value={form.min_experience} onChange={update("min_experience")} /><span>년</span></div></label><label className="wide-field"><span>요구 기술</span><input name="required_skills" autoComplete="off" value={form.required_skills} onChange={update("required_skills")} placeholder="Python, PostgreSQL, AWS" required /></label><label className="wide-field"><span>주요 업무</span><textarea name="summary" rows="5" value={form.summary} onChange={update("summary")} required minLength="10" /></label></div><div className="form-actions"><button type="button" className="button quiet" onClick={() => resetEditor()}>취소</button><button className="button" disabled={busy}>{busy ? "저장 중…" : editingId ? "변경 저장" : "공고 공개"}</button></div></form>}
    <ErrorNotice error={loadError} onRetry={load} />
    {!jobs && !loadError ? <Loading /> : jobs?.length ? <div className="recruiter-job-list">{jobs.map((job) => <article className="recruiter-job" key={job.id}><div className="recruiter-job-main"><div><span className={`status-pill status-${job.status}`}>{statusLabels[job.status]}</span><h2>{job.title}</h2><p>{job.location} · {job.employment_type} · 경력 {job.min_experience}년 이상</p><SkillList skills={job.required_skills} /></div><div className="application-count"><strong>{job.application_count}</strong><span>지원자</span></div></div><div className="recruiter-job-actions"><Link className="button small" to={`/recruiter/jobs/${job.id}/pipeline`} aria-label={`${job.title} 지원자 파이프라인 보기`}>지원자 파이프라인</Link><Link className="button quiet small" to={`/recruiter/jobs/${job.id}/recommendations`} aria-label={`${job.title} 조건 일치 순위 보기`}>조건 일치 순위</Link><button className="text-button" aria-label={`${job.title} 공고 수정`} onClick={() => beginEdit(job)}>공고 수정</button>{job.status === "open" ? <button id={`job-status-${job.id}`} className="text-button" aria-label={`${job.title} 공고 마감`} disabled={statusBusyId === job.id || (showForm && editingId === job.id)} onClick={() => changeStatus(job, "closed")}>공고 마감</button> : <button id={`job-status-${job.id}`} className="text-button" aria-label={`${job.title} 공고 다시 열기`} disabled={statusBusyId === job.id || (showForm && editingId === job.id)} onClick={() => changeStatus(job, "open")}>다시 열기</button>}</div></article>)}</div> : jobs ? <EmptyState title="등록한 공고가 없습니다" body="첫 공고를 등록하면 지원자 흐름을 확인할 수 있습니다." action={!showForm ? <button className="button" onClick={beginCreate}>공고 등록</button> : null} /> : null}
  </section>;
}

function CandidateRecordDetails({ candidate }) {
  const value = (candidateValue) => candidateValue || "미입력";
  return (
    <details className="candidate-record">
      <summary>현재 이력서 자료 펼쳐 보기<span className="sr-only"> · {candidate.display_name} · {candidate.email}</span></summary>
      <dl className="candidate-record-grid">
        <div><dt>이메일</dt><dd>{value(candidate.email)}</dd></div>
        <div><dt>연락처</dt><dd>{value(candidate.phone)}</dd></div>
        <div><dt>생년월일</dt><dd>{value(candidate.birth_date)}</dd></div>
        <div><dt>거주 지역</dt><dd>{value(candidate.address_region)}</dd></div>
        <div><dt>학력</dt><dd>{value(candidate.education)}</dd></div>
        <div><dt>자격증</dt><dd>{candidate.certificates?.length ? candidate.certificates.join(", ") : "미입력"}</dd></div>
        <div className="record-wide"><dt>자기소개</dt><dd>{value(candidate.self_intro)}</dd></div>
      </dl>
      <p>조회 시점의 현재 이력서이며 지원 시점 스냅샷은 아닙니다. 이 자료는 파이프라인 응답에 이미 포함되고, 펼침 동작 자체를 별도 감사 이벤트로 남기지는 않습니다.</p>
    </details>
  );
}

function RecruiterPipelinePage() {
  const { id } = useParams();
  const beginRequest = useRequestEpoch();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [statusMessage, setStatusMessage] = useState("");
  const [draftStatuses, setDraftStatuses] = useState({});
  const [busyId, setBusyId] = useState(null);
  const statusOptions = Object.entries(statusLabels).filter(([key]) => !["open", "closed"].includes(key));
  const load = () => {
    const isCurrent = beginRequest();
    setData(null);
    setError(null);
    setStatusMessage("");
    return api(`/api/v1/recruiter/jobs/${id}/pipeline`)
      .then((result) => { if (isCurrent()) { setData(result); setDraftStatuses({}); } })
      .catch((caught) => { if (isCurrent()) setError(caught); });
  };
  useEffect(() => { load(); }, [id]);
  const pipelineDirty = Boolean(data?.items?.some((item) => draftStatuses[item.id] && draftStatuses[item.id] !== item.status));
  useUnsavedChanges(pipelineDirty, "저장하지 않은 전형 상태 변경이 있습니다. 다른 화면으로 이동할까요?");
  const saveStatus = async (applicationId, value, candidateName) => {
    setBusyId(applicationId);
    setError(null);
    setStatusMessage("");
    try {
      await api(`/api/v1/recruiter/applications/${applicationId}`, { method: "PATCH", body: jsonBody({ status: value }) });
      setData((current) => ({ ...current, items: current.items.map((item) => item.id === applicationId ? { ...item, status: value } : item) }));
      clearDraft(applicationId, { restoreFocus: false });
      setStatusMessage(`${candidateName} 지원자의 전형 상태를 ‘${statusLabels[value]}’ 상태로 저장했습니다.`);
      window.requestAnimationFrame(() => document.getElementById(`stage-${applicationId}`)?.focus());
    } catch (caught) {
      setError(caught);
    } finally {
      setBusyId(null);
    }
  };
  const clearDraft = (applicationId, { restoreFocus = true } = {}) => {
    setDraftStatuses((current) => {
      const next = { ...current };
      delete next[applicationId];
      return next;
    });
    if (restoreFocus) {
      window.requestAnimationFrame(() => document.getElementById(`stage-${applicationId}`)?.focus());
    }
  };
  return (
    <section className="content">
      <Link className="back-link" to="/recruiter/jobs">← 채용공고 관리</Link>
      <PageHeader eyebrow="Candidate pipeline" title={data?.job?.title || "지원자 파이프라인"} description="지원자 이력과 전형 상태를 한 화면에서 검토합니다. 파이프라인 응답의 지원자 열람은 감사 이벤트로 기록됩니다." actions={data && <Link className="button" to={`/recruiter/jobs/${id}/recommendations`}>조건 일치 순위 보기</Link>} />
      <ErrorNotice error={error} onRetry={load} />
      <SuccessNotice>{statusMessage}</SuccessNotice>
      {!data && !error ? <Loading /> : data?.items?.length ? (
        <>
          <p className="asis-observation pipeline-observation"><span>응답 경계</span> 지원 레코드가 있어도 현재 이력서를 찾지 못하면 이 응답의 지원자 목록에서 제외됩니다.</p>
          <p className="asis-observation pipeline-observation"><span>AS-IS 관찰</span> 전형 상태는 저장 시 즉시 커밋됩니다. 현재 감사 상세에는 이전 상태와 변경 사유가 포함되지 않습니다.</p>
          <div className="pipeline-list" role="list" aria-label="지원자 파이프라인">
            {data.items.map((item) => {
              const selectedStatus = draftStatuses[item.id] ?? item.status;
              const changed = selectedStatus !== item.status;
              return (
                <article className="pipeline-card" role="listitem" aria-labelledby={`candidate-${item.id}`} key={item.id}>
                  <div className="pipeline-card-grid">
                    <div className="pipeline-cell"><span>지원자</span><h2 id={`candidate-${item.id}`}>{item.candidate.display_name}</h2><small>{item.candidate.email}</small><time dateTime={item.applied_at}>{new Intl.DateTimeFormat("ko-KR", { dateStyle: "medium" }).format(new Date(item.applied_at))} 지원</time></div>
                    <div className="pipeline-cell"><span>경력·희망 직무</span><strong>{item.candidate.years_experience}년</strong><small>{item.candidate.desired_role}</small></div>
                    <div className="pipeline-cell"><span>보유 기술</span><SkillList skills={item.candidate.skills.slice(0, 4)} /></div>
                    <div className="pipeline-cell stage-editor">
                      <span>전형 상태</span>
                      <select id={`stage-${item.id}`} aria-label={`${item.candidate.display_name} 전형 상태`} value={selectedStatus} disabled={busyId === item.id} onChange={(event) => setDraftStatuses((current) => ({ ...current, [item.id]: event.target.value }))}>{statusOptions.map(([statusValue, label]) => <option key={statusValue} value={statusValue}>{label}</option>)}</select>
                      {changed && <div className="stage-actions"><button type="button" className="button small" aria-label={`${item.candidate.display_name} 전형 상태 변경 저장`} disabled={busyId === item.id} onClick={() => saveStatus(item.id, selectedStatus, item.candidate.display_name)}>{busyId === item.id ? "저장 중…" : "변경 저장"}</button><button type="button" className="text-button" aria-label={`${item.candidate.display_name} 전형 상태 변경 취소`} disabled={busyId === item.id} onClick={() => clearDraft(item.id)}>취소</button></div>}
                    </div>
                  </div>
                  <CandidateRecordDetails candidate={item.candidate} />
                </article>
              );
            })}
          </div>
        </>
      ) : data ? <EmptyState title="현재 응답에 표시할 지원자가 없습니다" body="지원 레코드 자체가 없다는 뜻은 아닙니다. 현재 이력서를 찾지 못한 지원자는 이 응답에서 제외됩니다." /> : null}
    </section>
  );
}

function recommendationFactor(item, factorId) {
  const factor = item.score_breakdown?.factors?.find((entry) => entry.factor_id === factorId);
  const points = Number(factor?.display_points);
  return Number.isFinite(points) ? points : null;
}

function CandidateComparison({ items, onRemove, onClear }) {
  if (!items.length) return null;
  const factorCell = (item, factorId, maximum) => {
    const points = recommendationFactor(item, factorId);
    return points === null ? "확인 필요" : `${points.toFixed(1)} / ${maximum}점`;
  };
  return (
    <section className="candidate-comparison" aria-labelledby="candidate-comparison-title">
      <div className="comparison-heading">
        <div>
          <p className="section-kicker">화면 안에서만 유지</p>
          <h2 id="candidate-comparison-title">임시 비교 · {items.length}/3명</h2>
          <p>현재 응답의 계산 내역을 나란히 볼 뿐, 저장·공유하거나 선발 결정을 기록하지 않습니다.</p>
        </div>
        <button type="button" className="text-button" onClick={onClear}>비교 비우기</button>
      </div>
      <div className="comparison-table-wrap" role="region" aria-label="선택한 지원자 비교표" tabIndex="0">
        <table className="comparison-table">
          <thead>
            <tr>
              <th scope="col">비교 항목</th>
              {items.map((item) => (
                <th scope="col" key={item.candidate.user_id}>
                  <span>{item.candidate.display_name}</span>
                  <small>{item.candidate.desired_role}</small>
                  <button type="button" onClick={() => onRemove(item.candidate.user_id)} aria-label={`${item.candidate.display_name} 비교에서 빼기`}>빼기</button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr><th scope="row">조건 일치 총점</th>{items.map((item) => <td key={item.candidate.user_id}>{Number(item.score).toFixed(1)} / 100점</td>)}</tr>
            <tr><th scope="row">요구 기술</th>{items.map((item) => <td key={item.candidate.user_id}>{factorCell(item, "skills", 70)}</td>)}</tr>
            <tr><th scope="row">경력 조건</th>{items.map((item) => <td key={item.candidate.user_id}>{factorCell(item, "experience", 20)}</td>)}</tr>
            <tr><th scope="row">희망 직무</th>{items.map((item) => <td key={item.candidate.user_id}>{factorCell(item, "role", 10)}</td>)}</tr>
            <tr><th scope="row">등록 기술</th>{items.map((item) => <td key={item.candidate.user_id}>{item.candidate.skills?.join(", ") || "등록 없음"}</td>)}</tr>
          </tbody>
        </table>
      </div>
      <p className="comparison-boundary" role="note">이 표는 담당자의 자료 검토를 돕는 임시 보기입니다. 지원자 간 우열·합격 가능성·기업 적합성을 판정하지 않습니다.</p>
    </section>
  );
}

function RecruiterRecommendationsPage() {
  const { id } = useParams(); const beginRequest = useRequestEpoch();
  const [data, setData] = useState(null); const [error, setError] = useState(null); const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState(""); const [skillFilter, setSkillFilter] = useState(""); const [minimumScore, setMinimumScore] = useState(0);
  const [comparisonIds, setComparisonIds] = useState([]);
  const load = async ({ preserve = true } = {}) => {
    const isCurrent = beginRequest();
    setLoading(true); setError(null);
    if (!preserve) setData(null);
    try {
      const result = await api(`/api/v1/recruiter/jobs/${id}/recommendations`);
      if (isCurrent()) {
        setData(result);
        setComparisonIds((current) => current.filter((candidateId) => result.items?.some((item) => item.candidate.user_id === candidateId)));
      }
    } catch (caught) {
      if (isCurrent()) setError(caught);
    } finally {
      if (isCurrent()) setLoading(false);
    }
  };
  useEffect(() => {
    setQuery(""); setSkillFilter(""); setMinimumScore(0); setComparisonIds([]);
    load({ preserve: false });
  }, [id]);

  const rankedItems = Array.isArray(data && data.items) ? data.items.map((item, index) => ({ item, index })) : [];
  const skillOptions = [...new Set(rankedItems.flatMap(({ item }) => item.candidate.skills || []))]
    .sort((left, right) => String(left).localeCompare(String(right), "ko"));
  const normalizedQuery = query.trim().toLocaleLowerCase("ko-KR");
  const visibleItems = rankedItems.filter(({ item }) => {
    const searchable = [item.candidate.display_name, item.candidate.desired_role, ...(item.candidate.skills || [])]
      .join(" ").toLocaleLowerCase("ko-KR");
    const queryMatches = !normalizedQuery || searchable.includes(normalizedQuery);
    const skillMatches = !skillFilter || item.candidate.skills?.includes(skillFilter);
    return queryMatches && skillMatches && Number(item.score) >= minimumScore;
  });
  const selectedItems = comparisonIds.map((candidateId) => rankedItems.find(({ item }) => item.candidate.user_id === candidateId)?.item).filter(Boolean);
  const availableExplanationCount = rankedItems.filter(({ item }) => item.explanation?.status === "AVAILABLE").length;
  const filtersActive = Boolean(query || skillFilter || minimumScore);
  const clearFilters = () => { setQuery(""); setSkillFilter(""); setMinimumScore(0); };
  const toggleComparison = (candidateId) => {
    setComparisonIds((current) => current.includes(candidateId)
      ? current.filter((item) => item !== candidateId)
      : current.length < 3 ? [...current, candidateId] : current);
  };

  return (
    <section className="content wide talent-workbench" aria-busy={loading && !data}>
      <Link className="back-link" to={`/recruiter/jobs/${id}/pipeline`}>← 지원자 파이프라인</Link>
      <div className="talent-hero">
        <PageHeader
          eyebrow="기업 채용 · 지원자 검토"
          title={data?.job?.title ? `${data.job.title} · 지원자 조건 비교` : "지원자 조건 비교"}
          description="이 공고에 지원한 활성 지원자의 기술·경력·희망 직무를 같은 기준으로 살펴봅니다. 담당자가 원문 자료를 검토하기 전의 보조 화면입니다."
          actions={<button type="button" className="button light" disabled={loading} onClick={() => load()}>{loading ? "결과 불러오는 중…" : "결과 새로 불러오기"}</button>}
        />
        <div className="talent-scope" role="note" aria-label="이 화면의 범위">
          <strong>이 화면이 다루는 범위</strong>
          <ul>
            <li>이 공고에 지원한 활성 지원자만 표시</li>
            <li>전체 인재 데이터베이스 검색 아님</li>
            <li>화면 필터는 서버가 준 순서를 바꾸지 않음</li>
          </ul>
        </div>
      </div>
      <ErrorNotice error={error} onRetry={() => load()} />
      <RecommendationLoadStatus data={data} noun="지원자" />
      {loading && data && <p className="ranking-basis" role="status" aria-live="polite" aria-atomic="true">기존 결과를 표시한 채 새 결과를 불러오는 중…</p>}
      {error && data && <p className="ranking-basis" role="status" aria-live="polite" aria-atomic="true">갱신에 실패해 직전 성공 결과를 유지하고 있습니다.</p>}
      {data && <><RecommendationMeta data={data} /><CacheObservation cache={data.cache} audience="recruiter" /></>}
      {loading && !data ? <Loading label="지원자 조건 일치 점수와 설명을 불러오는 중" /> : data?.items?.length ? (
        <>
          <section className="talent-summary" aria-label="현재 응답 요약">
            <div className="summary-intro">
              <p className="section-kicker">현재 응답</p>
              <h2>지원자 검토 현황</h2>
              <p>숫자는 현재 API 응답과 화면 선택 상태를 요약합니다. 채용 성과나 지원자 품질 지표가 아닙니다.</p>
            </div>
            <dl className="talent-metrics">
              <div><dt>응답 지원자</dt><dd>{rankedItems.length}<small>명</small></dd></div>
              <div><dt>현재 표시</dt><dd>{visibleItems.length}<small>명</small></dd></div>
              <div><dt>설명 제공</dt><dd>{availableExplanationCount}<small>건</small></dd></div>
              <div><dt>임시 비교</dt><dd>{selectedItems.length}<small>/ 3명</small></dd></div>
            </dl>
          </section>

          <fieldset className="talent-filters">
            <legend>지원자 좁혀 보기</legend>
            <div className="filter-grid">
              <label className="filter-search" htmlFor="talent-query"><span>이름·직무·기술</span><input id="talent-query" name="candidate_filter" type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="예: 보안, Python…" autoComplete="off" /></label>
              <label htmlFor="talent-skill"><span>등록 기술</span><select id="talent-skill" name="skill_filter" value={skillFilter} onChange={(event) => setSkillFilter(event.target.value)}><option value="">모든 기술</option>{skillOptions.map((skill) => <option value={skill} key={skill}>{skill}</option>)}</select></label>
              <label htmlFor="talent-score"><span>최소 표시 점수</span><select id="talent-score" name="minimum_score" value={minimumScore} onChange={(event) => setMinimumScore(Number(event.target.value))}><option value={0}>전체 점수</option><option value={40}>40점 이상</option><option value={60}>60점 이상</option><option value={80}>80점 이상</option></select></label>
              <button type="button" className="button quiet filter-reset" onClick={clearFilters} disabled={!filtersActive}>필터 지우기</button>
            </div>
            <p className="filter-footnote">현재 받은 결과를 화면에서만 좁힙니다. 새 후보를 찾거나 점수를 다시 계산하지 않습니다.</p>
          </fieldset>

          <CandidateComparison items={selectedItems} onRemove={toggleComparison} onClear={() => setComparisonIds([])} />

          <div className="result-heading">
            <div><p className="section-kicker">기존 순서 유지</p><h2>검토할 지원자</h2></div>
            <p role="status" aria-live="polite" aria-atomic="true">전체 {rankedItems.length}명 중 <strong>{visibleItems.length}명</strong> 표시</p>
          </div>
          <p className="ranking-basis" role="note"><strong>구조화 조건 정렬</strong> · 이 응답에 포함된 후보자를 같은 산식으로 비교합니다. 캐시 응답은 캐시 생성 당시 조회된 지원자 집합이며, 담당자는 현재 자료와 전형 맥락을 별도로 확인해야 합니다.</p>
          {visibleItems.length ? (
            <div className="recommendation-list recruiter-ranking">
              {visibleItems.map(({ item, index }) => {
                const subjectLabel = `조건 일치 결과 ${index + 1}, ${item.candidate.display_name}, ${item.candidate.email}`;
                const selected = comparisonIds.includes(item.candidate.user_id);
                const selectionDisabled = !selected && comparisonIds.length >= 3;
                return (
                  <article className={`recommendation-card recruiter-rec${selected ? " is-selected" : ""}`} key={item.candidate.user_id}>
                    <div className="rank"><span className="sr-only">조건 일치 순서 </span>{String(index + 1).padStart(2, "0")}<small>번째</small></div>
                    <div className="candidate-card-tools">
                      <label className="candidate-compare">
                        <input type="checkbox" name="comparison_candidates" value={item.candidate.user_id} checked={selected} disabled={selectionDisabled} onChange={() => toggleComparison(item.candidate.user_id)} />
                        <span>{selected ? "비교에 담김" : selectionDisabled ? "최대 3명" : "임시 비교"}</span>
                      </label>
                    </div>
                    <div className="recommendation-top"><div><span className="company-label">{item.candidate.desired_role}</span><h2>{item.candidate.display_name}</h2><p>경력 {item.candidate.years_experience}년 · 프로필 거주지역 {item.candidate.address_region} (점수 미사용)</p></div><Score value={item.score} /></div>
                    <ScoreDisclosure breakdown={item.score_breakdown} explanation={item.explanation} explanationAttempt={data.explanation_attempt} audience="recruiter" subjectLabel={subjectLabel} />
                    <CompanyAlignment alignment={item.explanation?.company_alignment} profileSource={data.job?.company_profile?.source} />
                    <SignalRail features={item.matched_feature_labels} />
                    <Explanation explanation={item.explanation} subjectLabel={subjectLabel} />
                    <div className="candidate-skills"><strong>등록 기술</strong><SkillList skills={item.candidate.skills} /></div>
                  </article>
                );
              })}
            </div>
          ) : (
            <EmptyState title="현재 필터에 맞는 지원자가 없습니다" body="필터를 지우거나 범위를 넓혀 보세요. 원래 응답의 지원자와 순위는 바뀌지 않았습니다." action={<button type="button" className="button" onClick={clearFilters}>필터 지우기</button>} />
          )}
        </>
      ) : data ? <EmptyState title="현재 응답에 조건 일치 지원자가 없습니다" body="캐시 응답이면 캐시 생성 당시의 지원자 집합입니다. 현재 지원자가 없다는 단정은 아닙니다." action={<Link className="button" to={`/recruiter/jobs/${id}/pipeline`}>현재 파이프라인 보기</Link>} /> : null}
    </section>
  );
}

function AdminAuditPage() {
  const [events, setEvents] = useState(null); const [filter, setFilter] = useState(""); const [error, setError] = useState(null);
  const load = async (event) => { event?.preventDefault(); setEvents(null); setError(null); try { setEvents(await api(`/api/v1/admin/audit${filter ? `?event_type=${encodeURIComponent(filter)}` : ""}`)); } catch (caught) { setError(caught); } };
  useEffect(() => { load(); }, []);
  return <section className="content wide"><PageHeader eyebrow="Operations" title="감사 이벤트" description="사용자 행동과 업무 이벤트의 메타데이터를 확인합니다. 추천 적합성 판정은 이 화면에서 하지 않습니다." /><form className="audit-filter" onSubmit={load}><label><span>이벤트 유형</span><input name="event_type" autoComplete="off" value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="예: candidate_view" /></label><button className="button quiet">필터 적용</button></form><ErrorNotice error={error} />{!events && !error ? <Loading /> : events?.length ? <div className="audit-table" role="table" aria-label="감사 이벤트 목록" tabIndex="0"><div className="audit-head" role="row"><span role="columnheader">시간</span><span role="columnheader">이벤트</span><span role="columnheader">행위자</span><span role="columnheader">대상</span><span role="columnheader">결과</span><span role="columnheader">Correlation</span></div>{events.map((event) => <div className="audit-row" role="row" key={event.id}><time role="cell" dateTime={event.occurred_at}>{new Intl.DateTimeFormat("ko-KR", { dateStyle: "short", timeStyle: "short" }).format(new Date(event.occurred_at))}</time><strong role="cell">{event.event_type}</strong><span role="cell">{event.actor_role}</span><span className="mono" role="cell">{event.target_type}<small>{event.target_ref}</small></span><span role="cell">{event.result}</span><code role="cell">{event.correlation_id.slice(0, 8)}</code></div>)}</div> : events ? <EmptyState title="조건에 맞는 이벤트가 없습니다" body="필터를 지우거나 다른 이벤트 유형을 입력해 보세요." /> : null}</section>;
}

function LegalPage({ type }) {
  const privacy = type === "privacy";
  return <section className="content legal"><PageHeader eyebrow="합성 재현환경 초안" title={privacy ? "개인정보 처리방침" : "이용약관"} description="아래 문구는 재현환경 안내이며 실제 법률 문서나 승인된 고지가 아닙니다." /><div className="legal-copy"><div className="notice warning">사람 검토 전 초안입니다. 실제 서비스 공지로 사용하지 마세요.</div>{privacy ? <><h2>처리 목적과 항목</h2><p>합성 구직자 계정, 구조화 이력서, 지원 내역을 채용 흐름 재현 목적으로 처리합니다. 실제 개인정보를 입력해서는 안 됩니다.</p><h2>외부 AI 처리</h2><p>코드에는 로컬 가짜 응답과 기본 비활성화된 Bedrock 외부 호출 모드가 함께 있습니다. 이 안내만으로 현재 공급자 호출 여부, 처리 국가·지역 또는 계약상 지위를 확정하지 않습니다.</p><h2>권리 행사</h2><p>구직자 계정에서 동의 철회와 회원 탈퇴 기능을 시험할 수 있습니다. 기업 계정의 동의·탈퇴 수명주기는 구현되지 않았습니다. 화면은 모든 저장면의 완전 삭제를 보증하지 않습니다.</p></> : <><h2>재현환경의 성격</h2><p>본 환경은 가상 기업 J-Career의 채용 업무를 합성 데이터로 재현하는 기술 검증용 서비스입니다.</p><h2>금지 사항</h2><p>실제 지원자 정보, 실제 기업 비밀, 계정 자격증명 또는 제3자의 개인정보를 입력하지 마세요.</p><h2>결과의 한계</h2><p>추천 점수와 설명은 채용 결정을 대신하지 않으며 인증 또는 법적 판단을 제공하지 않습니다.</p></>}</div></section>;
}

function NotFoundPage() {
  return <section className="content narrow"><PageHeader eyebrow="404" title="페이지를 찾을 수 없습니다" description="요청한 주소에 해당하는 화면이 없습니다." /><EmptyState title="다른 화면으로 이동해 주세요" body="주소를 확인하거나 채용공고 목록으로 이동해 주세요." action={<Link className="button" to="/jobs">채용공고 보기</Link>} /></section>;
}

function AppLayout() {
  return (
    <UnsavedProvider>
      <AuthProvider>
        <Shell><Outlet /></Shell>
      </AuthProvider>
    </UnsavedProvider>
  );
}

const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      { path: "/", element: <Navigate to="/jobs" replace /> },
      { path: "/jobs", element: <JobsPage /> },
      { path: "/jobs/:id", element: <JobDetailPage /> },
      { path: "/login", element: <LoginPage /> },
      { path: "/signup", element: <SignupPage /> },
      { path: "/signup/consent", element: <Protected roles={["candidate"]}><ConsentPage /></Protected> },
      { path: "/candidate/home", element: <Protected roles={["candidate"]}><CandidateHomeRoute /></Protected> },
      { path: "/candidate/resume", element: <Protected roles={["candidate"]}><ResumePage /></Protected> },
      { path: "/candidate/applications", element: <Protected roles={["candidate"]}><CandidateApplicationsPage /></Protected> },
      { path: "/candidate/recommendations", element: <Protected roles={["candidate"]}><CandidateRecommendationsPage /></Protected> },
      { path: "/candidate/withdraw", element: <Protected roles={["candidate"]}><WithdrawPage /></Protected> },
      { path: "/recruiter/signup", element: <RecruiterSignupPage /> },
      { path: "/recruiter/overview", element: <Protected roles={["recruiter"]}><RecruiterOverviewPage /></Protected> },
      { path: "/recruiter/jobs", element: <Protected roles={["recruiter"]}><RecruiterJobsPage /></Protected> },
      { path: "/recruiter/jobs/:id/pipeline", element: <Protected roles={["recruiter"]}><RecruiterPipelinePage /></Protected> },
      { path: "/recruiter/jobs/:id/recommendations", element: <Protected roles={["recruiter"]}><RecruiterRecommendationsPage /></Protected> },
      { path: "/admin/audit", element: <Protected roles={["admin"]}><AdminAuditPage /></Protected> },
      { path: "/privacy", element: <LegalPage type="privacy" /> },
      { path: "/terms", element: <LegalPage type="terms" /> },
      { path: "*", element: <NotFoundPage /> }
    ]
  }
]);

export default function App() {
  return <RouterProvider router={router} />;
}
