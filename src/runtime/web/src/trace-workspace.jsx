import React, { useCallback, useEffect, useMemo, useState } from "react";

import { api, jsonBody } from "./api.js";

const modeLabels = {
  disabled: "비활성",
  shadow: "관찰 모드",
  enforced: "강제 기록 모드"
};

const stateLabels = {
  PENDING_REVIEW: "사람 검토 대기",
  NEEDS_CANDIDATE_INFO: "후보자 정보 요청",
  ESCALATED: "전문 검토로 이관",
  CLOSED_UPHELD: "원 기록 유지",
  CLOSED_CHANGED: "정정 반영"
};

const dispositionOptions = [
  ["UPHOLD", "EVIDENCE_CONFIRMED", "원 기록 유지"],
  ["CHANGE", "CORRECTION_SUPPORTED", "정정 반영"],
  ["REQUEST_INFO", "MORE_EVIDENCE_NEEDED", "추가 정보 요청"],
  ["ESCALATE", "SPECIALIST_REVIEW_REQUIRED", "전문 검토 이관"]
];

function requestKey(prefix) {
  const random = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${random}`;
}

function formatDate(value) {
  const parsed = new Date(value);
  if (!value || Number.isNaN(parsed.getTime())) return "시각 확인 필요";
  return new Intl.DateTimeFormat("ko-KR", { dateStyle: "medium", timeStyle: "short" }).format(parsed);
}

function shortHash(value) {
  return value ? `${value.slice(0, 12)}…${value.slice(-8)}` : "없음";
}

function factorRows(breakdown) {
  return (breakdown?.factors || []).map((factor) => ({
    id: factor.factor_id,
    label: { skills: "기술", experience: "경력", role: "직무" }[factor.factor_id] || factor.factor_id,
    points: Number(factor.display_points),
    maximum: Number(factor.max_points)
  }));
}

function ScoreTable({ breakdown, caption }) {
  const rows = factorRows(breakdown);
  return (
    <div className="trace-table-wrap" tabIndex="0" role="region" aria-label={caption}>
      <table className="trace-score-table">
        <caption>{caption}</caption>
        <thead><tr><th scope="col">요소</th><th scope="col">관찰 점수</th><th scope="col">최대점</th></tr></thead>
        <tbody>
          {rows.map((row) => <tr key={row.id}><th scope="row">{row.label}</th><td>{row.points.toFixed(1)}</td><td>{row.maximum.toFixed(0)}</td></tr>)}
          <tr className="trace-total"><th scope="row">합계</th><td>{Number(breakdown?.total_points || 0).toFixed(1)}</td><td>{Number(breakdown?.max_points || 100).toFixed(0)}</td></tr>
        </tbody>
      </table>
    </div>
  );
}

function RecourseTwin({ replay }) {
  if (!replay) return null;
  const original = new Map(factorRows(replay.original?.score_breakdown).map((item) => [item.id, item]));
  const corrected = new Map(factorRows(replay.corrected?.score_breakdown).map((item) => [item.id, item]));
  const ids = ["skills", "experience", "role"];
  return (
    <section className="recourse-twin" aria-labelledby={`twin-${String(replay.observed_at).replace(/\W/g, "")}`}>
      <div className="trace-subheading">
        <div><p>Recourse Twin</p><h5 id={`twin-${String(replay.observed_at).replace(/\W/g, "")}`}>원 기록과 정정 관찰 비교</h5></div>
        <strong className={Number(replay.delta_points) === 0 ? "trace-delta neutral" : "trace-delta"}>{Number(replay.delta_points) > 0 ? "+" : ""}{Number(replay.delta_points).toFixed(1)}점</strong>
      </div>
      <div className="trace-table-wrap" tabIndex="0" role="region" aria-label="원 기록과 정정 관찰 점수 비교">
        <table className="trace-twin-table">
          <caption>동일한 70·20·10 산식으로 다시 본 관찰값이며 채용 또는 이의 결정이 아닙니다.</caption>
          <thead><tr><th scope="col">요소</th><th scope="col">원 기록</th><th scope="col">정정 관찰</th></tr></thead>
          <tbody>
            {ids.map((id) => <tr key={id}><th scope="row">{{ skills: "기술", experience: "경력", role: "직무" }[id]}</th><td>{Number(original.get(id)?.points || 0).toFixed(1)}</td><td>{Number(corrected.get(id)?.points || 0).toFixed(1)}</td></tr>)}
            <tr className="trace-total"><th scope="row">합계</th><td>{Number(replay.original?.score_breakdown?.total_points || 0).toFixed(1)}</td><td>{Number(replay.corrected?.score_breakdown?.total_points || 0).toFixed(1)}</td></tr>
          </tbody>
        </table>
      </div>
      <p className="trace-boundary" role="note">이 비교는 점수·순위에 반영되지 않습니다. 자동 채용 결정이나 자동 이의판정도 수행하지 않습니다.</p>
    </section>
  );
}

function ReviewControl({ item, busy, onReview }) {
  const [disposition, setDisposition] = useState("UPHOLD");
  const selected = dispositionOptions.find(([value]) => value === disposition);
  const closed = item.state?.startsWith("CLOSED_");
  return (
    <form className="trace-review-form" onSubmit={(event) => { event.preventDefault(); onReview(item, selected); }} aria-busy={busy}>
      <label htmlFor={`review-${item.case_id}`}><span>사람 검토 처분</span><select id={`review-${item.case_id}`} value={disposition} onChange={(event) => setDisposition(event.target.value)} disabled={busy || closed}>{dispositionOptions.map(([value, , label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <button type="submit" className="button small" disabled={busy || closed}>{busy ? "기록 중…" : closed ? "검토 종료" : "검토 기록"}</button>
      <p>관리자 검토자의 명시적 기록만 상태를 바꿉니다.</p>
    </form>
  );
}

function RecourseCaseCard({ item, role, busy, onReview }) {
  const latestReview = item.human_reviews?.at(-1);
  return (
    <article className="recourse-case" aria-labelledby={`case-${item.case_id}`}>
      <header>
        <div><p>Case {item.case_id.slice(0, 8)}</p><h4 id={`case-${item.case_id}`}>{stateLabels[item.state] || item.state}</h4></div>
        <span className={`trace-state trace-state-${String(item.state).toLowerCase()}`}>{stateLabels[item.state] || item.state}</span>
      </header>
      <dl className="trace-meta-grid">
        <div><dt>사유 코드</dt><dd>{item.reason_code}</dd></div>
        <div><dt>상태 버전</dt><dd>{item.version}</dd></div>
        <div><dt>접수 시각</dt><dd><time dateTime={item.created_at}>{formatDate(item.created_at)}</time></dd></div>
        <div><dt>사람 검토</dt><dd role="status" aria-live="polite">{latestReview ? `${latestReview.disposition} · ${formatDate(latestReview.reviewed_at)}` : "아직 기록 없음"}</dd></div>
      </dl>
      <RecourseTwin replay={item.replay_observation} />
      {role === "admin" && <ReviewControl item={item} busy={busy} onReview={onReview} />}
    </article>
  );
}

function CorrectionForm({ receipt, busy, onSubmit }) {
  const [reasonCode, setReasonCode] = useState("FEATURE_INCORRECT");
  const [desiredRole, setDesiredRole] = useState("");
  const [skills, setSkills] = useState("");
  const [years, setYears] = useState("0");
  const submit = (event) => {
    event.preventDefault();
    onSubmit(receipt, {
      reason_code: reasonCode,
      corrected_features: {
        desired_role: desiredRole.trim(),
        skills: skills.split(",").map((item) => item.trim()).filter(Boolean),
        years_experience: Number(years)
      }
    });
  };
  return (
    <form className="trace-correction-form" onSubmit={submit} aria-busy={busy}>
      <fieldset disabled={busy}>
        <legend>정정·재검토 요청</legend>
        <p>연락처·주소·자기소개 원문은 입력하지 마세요. 구조화된 기술·경력·희망 직무만 일회성 재계산에 사용되며 receipt에는 값 자체를 저장하지 않습니다.</p>
        <div className="trace-form-grid">
          <label><span>사유</span><select value={reasonCode} onChange={(event) => setReasonCode(event.target.value)}><option value="FEATURE_INCORRECT">기록된 특징이 다름</option><option value="FEATURE_MISSING">특징이 누락됨</option><option value="EVIDENCE_VERSION">근거 버전이 다름</option><option value="OTHER_STRUCTURED">기타 구조화 정정</option></select></label>
          <label><span>희망 직무</span><input value={desiredRole} onChange={(event) => setDesiredRole(event.target.value)} maxLength="120" autoComplete="off" /></label>
          <label><span>기술 (쉼표 구분)</span><input value={skills} onChange={(event) => setSkills(event.target.value)} maxLength="600" autoComplete="off" /></label>
          <label><span>관련 경력 연수</span><input type="number" value={years} onChange={(event) => setYears(event.target.value)} min="0" max="60" step="1" /></label>
        </div>
        <button type="submit" className="button small">{busy ? "요청 중…" : "사람 검토 요청"}</button>
      </fieldset>
    </form>
  );
}

function ReceiptCard({ item, role, busyCaseId, onRecourse, onReview }) {
  const cases = item.recourse_cases || [];
  return (
    <article className="decision-receipt" aria-labelledby={`receipt-${item.receipt_id}`}>
      <header className="receipt-heading">
        <div><p>Decision Receipt</p><h2 id={`receipt-${item.receipt_id}`}>공고 근거 기록 {item.job_ref.slice(0, 8)}</h2></div>
        <span className="integrity-badge"><span aria-hidden="true">✓</span> 무결성 {item.integrity_state === "VERIFIED" ? "확인" : "확인 필요"}</span>
      </header>
      <dl className="trace-meta-grid">
        <div><dt>관찰 출처</dt><dd>{item.source_status} · {item.cache_state}</dd></div>
        <div><dt>매처 산식</dt><dd>{item.score_breakdown?.formula_version}</dd></div>
        <div><dt>기록 시각</dt><dd><time dateTime={item.timestamps?.receipt_recorded_at}>{formatDate(item.timestamps?.receipt_recorded_at)}</time></dd></div>
        <div><dt>SHA-256</dt><dd><code title={item.integrity_sha256}>{shortHash(item.integrity_sha256)}</code></dd></div>
      </dl>
      <div className="trace-feature-groups">
        <section aria-labelledby={`used-${item.receipt_id}`}><h3 id={`used-${item.receipt_id}`}>사용 특징 ID</h3><ul>{item.used_feature_ids?.map((feature) => <li key={feature}><code>{feature}</code></li>)}</ul></section>
        <section aria-labelledby={`excluded-${item.receipt_id}`}><h3 id={`excluded-${item.receipt_id}`}>제외 특징 ID</h3><ul>{item.excluded_feature_ids?.map((feature) => <li key={feature}><code>{feature}</code></li>)}</ul></section>
      </div>
      <ScoreTable breakdown={item.score_breakdown} caption="기록된 70·20·10 점수 분해" />
      <details className="trace-provenance"><summary>버전·근거 결속 보기</summary><dl>{Object.entries(item.fingerprints || {}).map(([name, hash]) => <div key={name}><dt>{name}</dt><dd><code>{shortHash(hash)}</code></dd></div>)}</dl><ul>{item.evidence_refs?.map((ref) => <li key={ref}><code>{ref}</code></li>)}</ul></details>
      <p className="trace-boundary" role="note">이 기록은 결정 당시 근거·버전·사람 검토를 잇는 증적입니다. 합격 판단, ISO 충족 판단 또는 잔여 위험 판단이 아닙니다.</p>
      {role === "candidate" && <CorrectionForm receipt={item} busy={busyCaseId === item.receipt_id} onSubmit={onRecourse} />}
      {cases.length > 0 && <section className="receipt-cases" aria-labelledby={`cases-${item.receipt_id}`}><h3 id={`cases-${item.receipt_id}`}>연결된 재검토 요청</h3><div>{cases.map((entry) => <RecourseCaseCard key={entry.case_id} item={entry} role={role} busy={busyCaseId === entry.case_id} onReview={onReview} />)}</div></section>}
    </article>
  );
}

export function TraceWorkspace({ role }) {
  const [status, setStatus] = useState(null);
  const [receipts, setReceipts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState("");
  const [busyCaseId, setBusyCaseId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [statusResult, receiptResult] = await Promise.all([
        api("/api/v1/trace/status"),
        api("/api/v1/trace/receipts")
      ]);
      setStatus(statusResult);
      setReceipts(receiptResult.items || []);
    } catch (caught) {
      setError(caught);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);
  const caseCount = useMemo(() => receipts.reduce((sum, receipt) => sum + (receipt.recourse_cases?.length || 0), 0), [receipts]);

  const submitRecourse = async (receipt, values) => {
    setBusyCaseId(receipt.receipt_id);
    setError(null);
    setNotice("");
    try {
      await api(`/api/v1/trace/receipts/${receipt.receipt_id}/recourse`, {
        method: "POST",
        headers: { "Idempotency-Key": requestKey("recourse") },
        body: jsonBody({ ...values, base_integrity_sha256: receipt.integrity_sha256 })
      });
      setNotice("정정 관찰과 사람 검토 요청을 기록했습니다.");
      await load();
    } catch (caught) {
      setError(caught);
    } finally {
      setBusyCaseId(null);
    }
  };

  const submitReview = async (item, selected) => {
    setBusyCaseId(item.case_id);
    setError(null);
    setNotice("");
    try {
      await api(`/api/v1/trace/cases/${item.case_id}/reviews`, {
        method: "POST",
        headers: { "Idempotency-Key": requestKey("review") },
        body: jsonBody({ disposition: selected[0], basis_code: selected[1], expected_version: item.version })
      });
      setNotice("사람 검토 처분을 기록했습니다.");
      await load();
    } catch (caught) {
      setError(caught);
    } finally {
      setBusyCaseId(null);
    }
  };

  return (
    <section className="content wide trace-workspace" aria-busy={loading}>
      <header className="trace-hero">
        <div><p className="workspace-kicker">TRACE / JC-RECEIPT</p><h1>결정 근거와<br />재검토를 잇는 기록</h1><p>최소 개인정보로 점수 근거·버전·사람 검토 상태를 연결합니다. 이 화면은 합격을 정하거나 이의를 자동 판정하지 않습니다.</p></div>
        <dl><div><dt>TRACE 모드</dt><dd>{modeLabels[status?.mode] || "확인 중"}</dd></div><div><dt>조회 receipt</dt><dd>{receipts.length}</dd></div><div><dt>재검토 case</dt><dd>{caseCount}</dd></div><div><dt>MLOps 저장소 공유</dt><dd>{status?.mlops_receipt_store_shared === false ? "아니요" : "확인 필요"}</dd></div></dl>
      </header>
      <p className="trace-rights-boundary" role="note"><strong>권한 경계</strong> 후보자는 자기 receipt와 case, 채용 담당자는 자기 공고 범위만 봅니다. 사람 검토 처분은 관리자 검토자만 기록합니다.</p>
      {notice && <p className="notice success" role="status" aria-live="polite">{notice}</p>}
      {error && <div className="notice error" role="alert"><span>{error.message || String(error)}</span><button type="button" className="text-button" onClick={load}>다시 불러오기</button></div>}
      {loading && receipts.length === 0 ? <div className="loading" role="status" aria-live="polite"><span className="spinner" aria-hidden="true" />Decision Receipt를 불러오는 중</div> : receipts.length > 0 ? (
        <ol className="receipt-list" aria-label="Decision Receipt 목록">{receipts.map((item) => <li key={item.receipt_id}><ReceiptCard item={item} role={role} busyCaseId={busyCaseId} onRecourse={submitRecourse} onReview={submitReview} /></li>)}</ol>
      ) : !loading ? <div className="trace-empty"><h2>기록된 Decision Receipt가 없습니다</h2><p>{status?.mode === "disabled" ? "TRACE_MODE가 기본값 disabled입니다. 기존 추천 응답은 바뀌지 않으며 새 receipt를 만들지 않습니다." : "추천 결과가 성공적으로 관찰된 뒤 이곳에서 확인할 수 있습니다."}</p></div> : null}
    </section>
  );
}
