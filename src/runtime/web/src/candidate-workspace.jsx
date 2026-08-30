import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "./api.js";

const applicationStatusLabels = {
  applied: "지원 완료",
  reviewing: "서류 검토",
  interview: "인터뷰",
  offered: "처우 협의",
  rejected: "전형 종료"
};

const activeApplicationStatuses = new Set(["reviewing", "interview", "offered"]);
const profileSignals = [
  ["desired_role", "희망 직무"],
  ["skills", "보유 기술"],
  ["years_experience", "관련 경력"],
  ["education", "학력"],
  ["self_intro", "자기소개"]
];

function hasProfileValue(resume, key) {
  const value = resume?.[key];
  if (key === "years_experience") return Number.isFinite(Number(value));
  if (Array.isArray(value)) return value.length > 0;
  return Boolean(String(value || "").trim());
}

function latestConsent(events, consentType) {
  return (events || []).find((event) => event.consent_type === consentType) || null;
}

function compactDate(value) {
  if (!value) return "시각 확인 필요";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "시각 확인 필요";
  return new Intl.DateTimeFormat("ko-KR", { month: "short", day: "numeric" }).format(date);
}

function WorkspaceLoading() {
  return <div className="candidate-workspace-loading" role="status" aria-live="polite"><span aria-hidden="true" />지원 현황을 모으는 중…</div>;
}

function PartialDataNotice({ failures, onRetry }) {
  if (!failures.length) return null;
  return (
    <div className="workspace-partial-notice" role="alert">
      <div><strong>일부 정보를 불러오지 못했습니다.</strong><span>{failures.join(" · ")}</span></div>
      <button type="button" className="text-button" onClick={onRetry}>다시 불러오기</button>
    </div>
  );
}

function ActionCard({ index, title, body, href, label }) {
  return (
    <li>
      <span className="action-index" aria-hidden="true">{String(index).padStart(2, "0")}</span>
      <div><strong>{title}</strong><p>{body}</p></div>
      <Link to={href} aria-label={`${title}: ${label}`}>{label}<span aria-hidden="true">↗</span></Link>
    </li>
  );
}

function buildNextActions({ resume, applications, coreConsent, unavailable }) {
  const actions = [];
  if (unavailable.has("consents")) {
    actions.push({ title: "동의 기록 확인", body: "동의 API를 불러오지 못했습니다. 기록 상태를 다시 확인하세요.", href: "/candidate/withdraw", label: "기록 확인" });
  } else if (coreConsent?.action !== "grant") {
    actions.push({ title: "필수 동의 이어가기", body: "이력서 저장·지원·조건 일치 기능을 사용하려면 현재 기록을 확인해야 합니다.", href: "/signup/consent", label: "동의 화면" });
  }

  if (unavailable.has("resume")) {
    actions.push({ title: "이력서 상태 재확인", body: "현재 구조화 이력서를 불러오지 못해 입력 상태를 계산하지 않았습니다.", href: "/candidate/resume", label: "이력서 확인" });
  } else if (!resume) {
    actions.push({ title: "구조화 이력서 만들기", body: "희망 직무·기술·경력을 입력하면 공고 조건과 비교할 준비가 됩니다.", href: "/candidate/resume", label: "이력서 작성" });
  } else {
    const missing = profileSignals.filter(([key]) => !hasProfileValue(resume, key)).map(([, label]) => label);
    if (missing.length) actions.push({ title: "프로필 신호 보완", body: `${missing.slice(0, 2).join("·")} 입력을 확인하면 현재 프로필 설명이 더 분명해집니다.`, href: "/candidate/resume", label: "프로필 보완" });
  }

  const active = (applications || []).filter((item) => activeApplicationStatuses.has(item.status));
  if (active.length) {
    actions.push({ title: "진행 중 전형 확인", body: `${active.length}건의 지원이 검토·인터뷰·처우 협의 단계에 있습니다.`, href: "/candidate/applications", label: "지원 현황" });
  } else if (!unavailable.has("applications") && applications?.length === 0) {
    actions.push({ title: "첫 지원 후보 찾기", body: "지원 내역이 없습니다. 공고를 직접 살펴보거나 조건 일치 결과를 비교하세요.", href: "/candidate/recommendations", label: "조건 일치 보기" });
  }

  actions.push({ title: "조건 일치 공고 비교", body: "같은 산식의 요인별 기여도와 기업이 선언한 방향 근거를 나란히 확인하세요.", href: "/candidate/recommendations", label: "비교 시작" });
  return actions.slice(0, 3);
}

export function CandidateHomePage({ user }) {
  const requestEpoch = useRef(0);
  const [snapshot, setSnapshot] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    const epoch = ++requestEpoch.current;
    setLoading(true);
    const [resumeResult, applicationResult, consentResult] = await Promise.allSettled([
      api("/api/v1/candidates/me/resume"),
      api("/api/v1/candidates/me/applications"),
      api("/api/v1/candidates/me/consents")
    ]);
    if (epoch !== requestEpoch.current) return;

    const unavailable = new Set();
    const failures = [];
    let resume = null;
    if (resumeResult.status === "fulfilled") resume = resumeResult.value;
    else if (resumeResult.reason?.status !== 404) {
      unavailable.add("resume");
      failures.push("이력서");
    }

    let applications = [];
    if (applicationResult.status === "fulfilled") applications = applicationResult.value;
    else {
      unavailable.add("applications");
      failures.push("지원 현황");
    }

    let consents = [];
    if (consentResult.status === "fulfilled") consents = consentResult.value;
    else {
      unavailable.add("consents");
      failures.push("동의 기록");
    }

    setSnapshot({ resume, applications, consents, unavailable, failures });
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
    return () => { requestEpoch.current += 1; };
  }, [load]);

  const view = useMemo(() => {
    if (!snapshot) return null;
    const { resume, applications, consents, unavailable } = snapshot;
    const coreConsent = latestConsent(consents, "privacy_core");
    const profileCount = resume ? profileSignals.filter(([key]) => hasProfileValue(resume, key)).length : 0;
    const activeCount = applications.filter((item) => activeApplicationStatuses.has(item.status)).length;
    return {
      coreConsent,
      profileCount,
      profilePercent: Math.round((profileCount / profileSignals.length) * 100),
      activeCount,
      actions: buildNextActions({ resume, applications, coreConsent, unavailable })
    };
  }, [snapshot]);

  return (
    <section className="content wide candidate-workspace" aria-busy={loading}>
      <header className="candidate-command-hero">
        <div className="candidate-command-copy">
          <p className="workspace-kicker">Candidate command center</p>
          <h1>{user?.display_name || "지원자"}님의<br />다음 선택을 선명하게.</h1>
          <p>이력서 입력, 지원 흐름, 조건 일치 근거를 한 화면에 모았습니다. 점수는 선택을 돕는 비교 자료이며 합격 가능성이나 선발 결론이 아닙니다.</p>
          <div className="candidate-hero-actions">
            <Link className="button workspace-primary" to="/candidate/recommendations">조건 일치 공고 비교</Link>
            <Link className="button workspace-secondary" to="/candidate/resume">이력서 업데이트</Link>
          </div>
        </div>
        <aside className="candidate-model-card" aria-label="현재 점수 모델 요약">
          <div className="model-card-heading"><span>현재 플랫폼 기본 산식</span><strong>70 · 20 · 10</strong></div>
          <div className="model-bars" aria-hidden="true"><span style={{ "--bar": "70%" }} /><span style={{ "--bar": "20%" }} /><span style={{ "--bar": "10%" }} /></div>
          <dl><div><dt>요구 기술</dt><dd>70점</dd></div><div><dt>관련 경력</dt><dd>20점</dd></div><div><dt>희망 직무</dt><dd>10점</dd></div></dl>
          <p>결정론적 매처가 점수와 순서를 계산합니다. 생성형 설명은 별도 계층이며 결과를 바꾸지 않습니다.</p>
        </aside>
      </header>

      {loading && !snapshot ? <WorkspaceLoading /> : snapshot && view ? (
        <>
          <PartialDataNotice failures={snapshot.failures} onRetry={load} />
          <section className="candidate-vitals" aria-label="지원 활동 요약">
            <article><span>프로필 입력</span><strong>{snapshot.unavailable.has("resume") ? "—" : `${view.profilePercent}%`}</strong><small>추천 점수가 아닌 5개 구조화 입력의 진행률</small></article>
            <article><span>전체 지원</span><strong>{snapshot.unavailable.has("applications") ? "—" : snapshot.applications.length}</strong><small>현재 회원 DB에서 조회된 지원 관계</small></article>
            <article><span>진행 중 전형</span><strong>{snapshot.unavailable.has("applications") ? "—" : view.activeCount}</strong><small>검토·인터뷰·처우 협의 상태</small></article>
            <article><span>필수 동의 기록</span><strong className="vital-text">{snapshot.unavailable.has("consents") ? "확인 필요" : view.coreConsent?.action === "grant" ? "기록됨" : "현재 grant 아님"}</strong><small>{view.coreConsent?.policy_version ? `정책 ${view.coreConsent.policy_version}` : "최신 이벤트 기준"}</small></article>
          </section>

          <div className="candidate-command-grid">
            <section className="candidate-action-panel" aria-labelledby="next-actions-heading">
              <div className="workspace-section-heading"><div><p>Focus queue</p><h2 id="next-actions-heading">지금 이어갈 일</h2></div><span>최대 3개</span></div>
              <ol>{view.actions.map((action, index) => <ActionCard key={`${action.href}-${action.title}`} index={index + 1} {...action} />)}</ol>
            </section>

            <section className="candidate-profile-panel" aria-labelledby="profile-snapshot-heading">
              <div className="workspace-section-heading"><div><p>Profile signals</p><h2 id="profile-snapshot-heading">매칭에 쓰이는 내 정보</h2></div><Link to="/candidate/resume">편집</Link></div>
              {snapshot.unavailable.has("resume") ? <p className="workspace-empty-copy">이력서 정보를 불러오지 못했습니다.</p> : snapshot.resume ? (
                <>
                  <div className="profile-role"><span>희망 직무</span><strong>{snapshot.resume.desired_role || "미입력"}</strong><small>관련 경력 {snapshot.resume.years_experience ?? "—"}년</small></div>
                  <div className="workspace-skill-list" aria-label="보유 기술">{snapshot.resume.skills?.length ? snapshot.resume.skills.map((skill) => <span key={skill}>{skill}</span>) : <span>기술 미입력</span>}</div>
                  <p className="profile-progress-copy">구조화 입력 {view.profileCount}/{profileSignals.length}개 확인 · 기업 방향 분석은 자기소개와 기업 선언의 직접 표현을 별도로 대조합니다.</p>
                </>
              ) : <p className="workspace-empty-copy">저장된 구조화 이력서가 없습니다. 이력서를 작성해야 조건 일치 요청을 시작할 수 있습니다.</p>}
            </section>
          </div>

          <section className="candidate-journey" aria-labelledby="candidate-journey-heading">
            <div className="workspace-section-heading"><div><p>Application journey</p><h2 id="candidate-journey-heading">최근 지원 흐름</h2></div><Link to="/candidate/applications">전체 보기</Link></div>
            {snapshot.unavailable.has("applications") ? <p className="workspace-empty-copy">지원 현황을 불러오지 못했습니다.</p> : snapshot.applications.length ? (
              <ol>{snapshot.applications.slice(0, 4).map((item) => <li key={item.id}><time dateTime={item.applied_at}>{compactDate(item.applied_at)}</time><span className="journey-line" aria-hidden="true" /><div><strong><Link to={`/jobs/${item.job.id}`}>{item.job.title}</Link></strong><span>{item.job.company_name}</span></div><span className={`status-pill status-${item.status}`}>{applicationStatusLabels[item.status] || item.status}</span></li>)}</ol>
            ) : <div className="journey-empty"><p>아직 지원 기록이 없습니다.</p><Link className="button quiet small" to="/jobs">열린 공고 살펴보기</Link></div>}
          </section>
        </>
      ) : null}
      <p className="workspace-boundary" role="note">이 화면은 세 API의 현재 응답을 모아 보여 줍니다. 지원 시점 스냅샷, 채용 결과 예측, 데이터 정합성 또는 통제 충족 여부를 판정하지 않습니다.</p>
    </section>
  );
}

function factorPoints(item, factorId) {
  const factor = item.score_breakdown?.factors?.find((entry) => entry.factor_id === factorId);
  return factor ? `${Number(factor.display_points).toFixed(1)} / ${Number(factor.max_points).toFixed(0)}` : "확인 필요";
}

function alignmentSummary(item) {
  const alignment = item.explanation?.company_alignment;
  if (!alignment) return "분석 응답 없음";
  if (alignment.state === "COMPANY_PROFILE_UNAVAILABLE") return "기업 선언 미설정";
  if (alignment.state === "DIRECT_DECLARED_VALUE_EVIDENCE_FOUND") return `직접 표현 ${alignment.matched_declared_values?.length || 0}개`;
  if (alignment.state === "NO_DIRECT_DECLARED_VALUE_EVIDENCE") return "직접 겹친 표현 없음";
  return "상태 확인 필요";
}

export function CandidateJobComparison({ items, onRemove, onClear }) {
  if (!items.length) return null;
  const rows = [
    ["조건 일치 점수", (item) => `${Number(item.score).toFixed(1)} / 100`],
    ["요구 기술 기여", (item) => `${factorPoints(item, "skills")}점`],
    ["관련 경력 기여", (item) => `${factorPoints(item, "experience")}점`],
    ["희망 직무 기여", (item) => `${factorPoints(item, "role")}점`],
    ["확인된 일치 신호", (item) => item.matched_feature_labels?.join(" · ") || "확인된 항목 없음"],
    ["기업 방향 직접 근거", alignmentSummary]
  ];
  return (
    <section className="candidate-job-comparison" aria-labelledby="job-comparison-heading">
      <div className="comparison-heading">
        <div><p className="section-kicker">Session comparison</p><h2 id="job-comparison-heading">공고 근거 나란히 보기</h2><p>선택한 공고 {items.length}/3개를 같은 응답 안에서 비교합니다.</p></div>
        <button type="button" className="text-button" onClick={onClear}>비교 비우기</button>
      </div>
      {items.length === 1 && <p className="comparison-prompt" role="status">다른 공고를 하나 이상 더 담으면 요인별 차이를 나란히 볼 수 있습니다.</p>}
      <div className="comparison-table-wrap" tabIndex="0" role="region" aria-label="선택한 공고 비교표">
        <table className="comparison-table">
          <thead><tr><th scope="col">비교 항목</th>{items.map((item) => <th scope="col" key={item.job.id}><span>{item.job.title}</span><small>{item.job.company_name}</small><button type="button" onClick={() => onRemove(item.job.id)} aria-label={`${item.job.company_name} ${item.job.title} 비교에서 제거`}>비교에서 제거</button></th>)}</tr></thead>
          <tbody>{rows.map(([label, value]) => <tr key={label}><th scope="row">{label}</th>{items.map((item) => <td key={item.job.id}>{value(item)}</td>)}</tr>)}</tbody>
        </table>
      </div>
      <p className="comparison-boundary">비교 선택은 이 브라우저 화면에만 임시로 유지됩니다. 직접 표현이 없다는 표시는 의미상 부합하지 않는다는 판정이 아니며, 총점도 합격 가능성을 뜻하지 않습니다.</p>
    </section>
  );
}
