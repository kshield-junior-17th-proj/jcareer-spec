import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const root = path.dirname(new URL(import.meta.url).pathname.replace(/^\/(?:([A-Za-z]):)/, '$1:'));
const sourcePath = path.join(root, 'JCAREER_ASIS_SYSTEM_SPEC.md');
const source = fs.readFileSync(sourcePath, 'utf8').replace(/^\uFEFF/, '').replace(/\r\n?/g, '\n');
const flowSourcePath = path.join(root, 'JCAREER_ASIS_FLOW.md');
const flowSource = fs.readFileSync(flowSourcePath, 'utf8').replace(/^\uFEFF/, '').replace(/\r\n?/g, '\n');

const escapeHtml = (value) => value
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;');

const plainText = (value) => value
  .replace(/`([^`]+)`/g, '$1')
  .replace(/\*\*([^*]+)\*\*/g, '$1')
  .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
  .trim();

const safeHref = (href) => /^(?:https?:\/\/|#|[A-Za-z0-9_.\/-]+(?:#[^\s]*)?)$/.test(href) ? href : '#';

function inline(value) {
  let html = escapeHtml(value);
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, label, href) => `<a href="${safeHref(href)}">${label}</a>`);
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/`([^`]+)`/g, (_, token) => {
    const statuses = {
      MODELLED: ['status modelled', '기준 설계 반영'],
      USER_CONFIRMED: ['status confirmed', '사용자 확인'],
      PLANNED_UNIMPLEMENTED: ['status planned', '계획만 있음'],
      LOCAL_SYNTHETIC_IMPLEMENTED: ['status local', '서비스 구현 범위'],
      STATIC_CHECKED: ['status local', '코드만 검사'],
      IMPLEMENTED_GUARDED_NOT_ACTIVE: ['status guarded', '코드 있으나 잠금'],
      BRANCH_PROTOTYPE_UNDEPLOYED: ['status branch', '별도 검증안·배포 전'],
      REPO_REPORTED_PREVIEW_DEPLOYED: ['status preview', '저장소상 미리보기 기록'],
      PEER_OBSERVED_PREVIEW_AVAILABLE: ['status preview', '제한적 미리보기 확인'],
      RAW_DRAFT_ONLY: ['status excluded', '초안에만 있음'],
      ASSUMED: ['status assumed', '확인 전 가정'],
      UNKNOWN: ['status unknown', '확인 못함'],
      OUT_OF_SCOPE: ['status excluded', '이번 범위 아님'],
      GATED: ['status gated', '승인 전 차단'],
      NOT_YET_MEASURED: ['status unknown', '아직 측정 안 함']
    };
    const status = statuses[token];
    return status
      ? `<span class="${status[0]}" data-status="${token}" title="내부 상태 코드: ${token}">${status[1]}</span>`
      : `<code>${token}</code>`;
  });
  return html;
}

function tableCells(line) {
  return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((cell) => cell.trim());
}

function isBoundary(line) {
  return /^\s*(?:#{1,3}\s|[-*]\s|\d+\.\s|>|```|\|)/.test(line);
}

function renderMarkdown(markdown, { includeLeadingQuote = false } = {}) {
  const lines = markdown.split(/\r?\n/);
  const html = [];
  const headings = [];
  let headingIndex = 0;
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i += 1; continue; }
    if (i === 0 && /^#\s/.test(line)) { i += 1; continue; }
    if (/^>/.test(line)) {
      const quote = [];
      while (i < lines.length && /^>/.test(lines[i])) quote.push(lines[i++].replace(/^>\s?/, ''));
      if (html.length || includeLeadingQuote) html.push(`<aside class="note">${inline(quote.join(' '))}</aside>`);
      continue;
    }
    const heading = line.match(/^(#{2,3})\s+(.+)$/);
    if (heading) {
      const level = heading[1].length;
      const title = plainText(heading[2]);
      const id = `section-${++headingIndex}`;
      headings.push({ level, title, id });
      html.push(`<h${level} id="${id}">${inline(heading[2])}<a class="anchor" href="#${id}" aria-label="${escapeHtml(title)} 바로가기">#</a></h${level}>`);
      i += 1;
      continue;
    }
    if (/^```/.test(line)) {
      const code = [];
      i += 1;
      while (i < lines.length && !/^```/.test(lines[i])) code.push(lines[i++]);
      i += 1;
      html.push(`<pre><code>${escapeHtml(code.join('\n'))}</code></pre>`);
      continue;
    }
    if (/^\|/.test(line) && i + 1 < lines.length && /^\|?\s*:?-{3,}/.test(lines[i + 1])) {
      const header = tableCells(line);
      i += 2;
      const rows = [];
      while (i < lines.length && /^\|/.test(lines[i])) rows.push(tableCells(lines[i++]));
      const head = `<thead><tr>${header.map((cell) => `<th scope="col">${inline(cell)}</th>`).join('')}</tr></thead>`;
      const body = `<tbody>${rows.map((row) => `<tr>${row.map((cell) => `<td>${inline(cell)}</td>`).join('')}</tr>`).join('')}</tbody>`;
      html.push(`<div class="table-scroll"><table>${head}${body}</table></div>`);
      continue;
    }
    if (/^[-*]\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^[-*]\s+/.test(lines[i])) {
        const item = [lines[i++].replace(/^[-*]\s+/, '')];
        while (i < lines.length && /^\s{2,}\S/.test(lines[i])) item.push(lines[i++].trim());
        items.push(item.join(' '));
      }
      html.push(`<ul>${items.map((item) => `<li>${inline(item)}</li>`).join('')}</ul>`);
      continue;
    }
    if (/^\d+\.\s+/.test(line)) {
      const items = [];
      const firstNumber = Number(line.match(/^(\d+)\./)[1]);
      while (i < lines.length && /^\d+\.\s+/.test(lines[i])) {
        const item = [lines[i++].replace(/^\d+\.\s+/, '')];
        while (i < lines.length && /^\s{2,}\S/.test(lines[i])) item.push(lines[i++].trim());
        items.push(item.join(' '));
      }
      const start = firstNumber === 1 ? '' : ` start="${firstNumber}"`;
      html.push(`<ol${start}>${items.map((item) => `<li>${inline(item)}</li>`).join('')}</ol>`);
      continue;
    }
    if (/^---+$/.test(line.trim())) { html.push('<hr>'); i += 1; continue; }

    const paragraph = [line.trim()];
    i += 1;
    while (i < lines.length && lines[i].trim() && !isBoundary(lines[i])) paragraph.push(lines[i++].trim());
    html.push(`<p>${inline(paragraph.join(' '))}</p>`);
  }

  const toc = headings.map(({ level, title, id }) =>
    `<li class="toc-${level}"><a href="#${id}">${escapeHtml(title)}</a></li>`
  ).join('');
  return { body: html.join('\n'), toc };
}

const { body, toc } = renderMarkdown(source);
const { body: flowBody } = renderMarkdown(flowSource, { includeLeadingQuote: true });
const flowSourceHash = crypto.createHash('sha256').update(flowSource, 'utf8').digest('hex');
const architectureFlows = {
  overview: {
    title: '전체 인프라',
    status: 'Terraform 설계',
    tone: 'modelled',
    summary: '사용자 진입부터 앱, 저장소, 기록·탐지까지 기준 Terraform이 표현한 전체 구성을 봅니다.',
    detailHref: 'index.html#section-14',
    detailLabel: '서비스·구성요소 명세 보기',
    stages: [
      { label: '서비스 접속' },
      { label: '인터넷 주소 안내' },
      { label: '웹 콘텐츠 전달' },
      { label: '웹 요청 검사' },
      { label: '앱 요청 분배' },
      { label: '앱·저장소·기록 설계' }
    ],
    boundary: '서울 리전 2-AZ, 6개 Terraform 모듈, 110개 계획 항목을 기준선으로 사용합니다. AWS 배포 상태와 실행 결과는 별도 검증 기록에서 관리합니다.'
  },
  candidate: {
    title: '구직자 공고 추천',
    status: '서비스 구현 범위',
    tone: 'local',
    summary: '합성 이력서와 열린 공고의 기술·경력·희망 직무를 같은 산식으로 비교해 공고 순서를 보여 주는 흐름입니다.',
    detailHref: 'index.html#section-31',
    detailLabel: '공고 추천 기능 명세 보기',
    stages: [
      { label: '이력서·공고 자료 확인', x: 1450, y: 300 },
      { label: '조건 비교·설명 생성', x: 1600, y: 300 },
      { label: '추천 결과 반환', x: 1750, y: 300 }
    ],
    boundary: '합성 데이터 기반 구현 범위입니다. 조건 일치도를 설명하며 합격 가능성을 예측하지 않습니다. AWS 데이터 저장소 연계와 배포 결과는 별도 검증 항목입니다.'
  },
  recruiter: {
    title: '기업용 인재 찾기',
    status: '공고 지원자 범위',
    tone: 'local',
    summary: '자기 회사의 한 공고에 지원한 활성 지원자만 대상으로 조건 일치 점수와 근거를 비교하는 흐름입니다.',
    detailHref: 'index.html#section-31',
    detailLabel: '기업용 인재 찾기 명세 보기',
    stages: [
      { label: '기업 소유·공고 범위 확인', x: 1450, y: 300 },
      { label: '해당 공고 지원자 비교', x: 1600, y: 300 },
      { label: '설명·최대 3명 임시 비교', x: 1750, y: 300 }
    ],
    boundary: '자사 공고에 지원한 활성 후보자를 대상으로 합니다. 기업 방향 대조는 점수와 순위를 바꾸지 않으며, 최대 3명의 비교 선택은 현재 화면에서만 유지합니다.'
  },
  explanation: {
    title: 'AI 설명 만들기',
    status: '설명 생성 검증',
    tone: 'guarded',
    summary: '조건 비교 엔진이 확정한 점수와 근거를 설명 문장으로 바꾸는 보조 흐름입니다. 점수와 순위를 고칠 권한은 없습니다.',
    detailHref: 'index.html#section-33',
    detailLabel: 'AI 점수·설명 규칙 보기',
    stages: [
      { label: '확정된 점수와 근거 받기', x: 1480, y: 290 },
      { label: '점수와 분리해 설명 만들기', x: 1600, y: 290 },
      { label: '형식 확인 후 상태와 함께 반환', x: 1720, y: 290 }
    ],
    boundary: '점수와 순위는 추천 엔진이 확정하며 설명 생성은 이를 바꾸지 않습니다. Amazon Bedrock 호출은 기본 잠금 상태로 두고 별도 승인·평가 절차를 적용합니다.'
  },
  mlops: {
    title: 'MLOps 학습·평가',
    status: '모델 검증 · 검토 대기',
    tone: 'guarded',
    summary: '기준 110개와 분리된 서버리스 경로에서 합성 특징 파일을 검사하고 후보 모델과 상태를 남긴 뒤 사람 검토를 기다립니다.',
    detailHref: '../../mlops/',
    detailLabel: 'MLOps 7단계 상세 보기',
    stages: [
      { label: '합성 자료 → 숫자 특징 5개', x: 1845, y: 135 },
      { label: 'S3 입력 → 수동 검사·학습', x: 2065, y: 135 },
      { label: '결과·상태 → 사람 검토 대기', x: 2285, y: 135 }
    ],
    boundary: 'MLOps 계획은 기본 잠금 0개, 보관함 준비 13개, 한 번 실행 준비 14개입니다. 기준 110개와 합산하지 않습니다. AWS 배포와 모델 품질은 이 문서에서 확인하지 않았습니다.'
  },
  operations: {
    title: '기록·탐지 경로',
    status: 'Terraform 설계',
    tone: 'modelled',
    summary: '파일 로그, 앱 로그, AWS 작업 기록과 위협 탐지 구성을 따로 살펴보는 보조 경로입니다.',
    detailHref: 'index.html#section-52',
    detailLabel: '보안·운영 명세 보기',
    stages: [
      { label: '위협 탐지 구성 확인', x: 585, y: 875 },
      { label: '파일·앱 로그 목적지 확인', x: 1460, y: 875 },
      { label: 'AWS 작업 기록 확인', x: 1990, y: 875 }
    ],
    boundary: 'Terraform 선언을 기준선으로 사용합니다. 로그 수집 완전성, 경보 처리와 장애 대응 효과는 운영 관찰 기록에서 따로 확인해야 합니다.'
  }
};

const svgStepMarkers = (flowKey, tone = '') => architectureFlows[flowKey].stages.map(({ x, y }, index) => `
            <g class="flow-step-marker ${tone}" data-flow-step="${index + 1}" transform="translate(${x} ${y})">
              <circle class="flow-marker ${tone}" r="24" />
              <text class="flow-marker-text" y="1">${index + 1}</text>
            </g>`).join('');

const flowStepItems = (flowKey) => architectureFlows[flowKey].stages.map(({ label }, index) =>
  `<li><span class="flow-step__number" aria-hidden="true">${index + 1}</span><span>${escapeHtml(label)}</span></li>`
).join('');

const commonHead = `
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#202b35">
  <meta name="description" content="J-Career 채용 서비스의 AWS 기준 설계, 기능, API, 데이터 흐름과 운영 통제를 정리한 시스템 명세">
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='8' fill='%23202b35'/%3E%3Cpath d='M19 14h9v24c0 9-5 13-14 12v-8c4 0 5-1 5-5V14zm14 0h17v8h-9v7h8v8h-8v13h-8V14z' fill='%23e87928'/%3E%3C/svg%3E">
  <meta property="og:type" content="website">
  <meta property="og:locale" content="ko_KR">
  <meta property="og:image" content="https://kshield-junior-17th-proj.github.io/jcareer-spec/terraform/asis/JCAREER_ASIS_FLOW.drawio.png">
  <meta property="og:image:alt" content="J-Career 채용 서비스와 AWS 구성의 전체 흐름도">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:image:alt" content="J-Career 채용 서비스와 AWS 구성의 전체 흐름도">
  <link rel="preconnect" href="https://api.fontshare.com">
  <link rel="preconnect" href="https://cdn.fontshare.com" crossorigin>
  <link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>
  <link rel="stylesheet" href="https://api.fontshare.com/v2/css?f[]=cabinet-grotesk@500,700,800&amp;display=swap">
`;

const commonCss = `
  :root {
    color-scheme: light;
    --ink: #182229;
    --ink-2: #3d4b53;
    --muted: #69747a;
    --paper: #efebe1;
    --surface: #fbf9f4;
    --surface-2: #f3efe6;
    --line: #d0c9bd;
    --line-strong: #978f82;
    --accent: #bd4d1e;
    --accent-soft: #f5dfd0;
    --green: #246a56;
    --amber: #8a5a00;
    --red: #a53a32;
    --blue: #315f83;
    --shadow: 0 26px 68px rgba(45, 49, 47, .13);
    --sans: "Cabinet Grotesk", "Pretendard Variable", Pretendard, "Noto Sans KR", "Segoe UI", AppleSDGothicNeo, sans-serif;
    --mono: "Cascadia Mono", "SFMono-Regular", Consolas, monospace;
  }
  * { box-sizing: border-box; }
  html { scroll-behavior: smooth; background: var(--paper); }
  body { margin: 0; color: var(--ink); background: var(--paper); font: 15.5px/1.72 var(--sans); letter-spacing: -.006em; }
  body::before { position: fixed; inset: 0; z-index: -1; content: ""; opacity: .18; background-image: linear-gradient(90deg, transparent 49.8%, #79736b 50%, transparent 50.2%), linear-gradient(0deg, transparent 49.8%, #79736b 50%, transparent 50.2%); background-size: 72px 72px; mask-image: linear-gradient(110deg, transparent, #000 44%, transparent 94%); }
  a, button { touch-action: manipulation; -webkit-tap-highlight-color: rgba(197, 83, 22, .18); }
  a { color: var(--blue); text-underline-offset: 3px; }
  :focus-visible { outline: 3px solid #e87928; outline-offset: 3px; }
  h2[id], h3[id] { scroll-margin-top: 24px; }
  .skip { position: fixed; top: 8px; left: 8px; z-index: 20; padding: 10px 14px; color: #fff; background: var(--ink); transform: translateY(-160%); }
  .skip:focus { transform: translateY(0); }
  .masthead { position: relative; overflow: hidden; color: var(--ink); background: radial-gradient(circle at 78% 24%, rgba(189,77,30,.12), transparent 22rem), var(--paper); border-bottom: 1px solid rgba(24,34,41,.24); }
  .masthead::after { position: absolute; inset: 0; pointer-events: none; content: ""; opacity: .1; background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 180 180' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.88' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='.28'/%3E%3C/svg%3E"); mix-blend-mode: multiply; }
  .masthead__inner { width: min(1480px, calc(100% - 48px)); margin: auto; }
  .utility { position: relative; z-index: 1; display: flex; align-items: center; justify-content: space-between; min-height: 58px; border-bottom: 1px solid rgba(24,34,41,.18); font: 700 10px/1 var(--mono); letter-spacing: .085em; text-transform: uppercase; }
  .utility a { color: var(--ink); text-decoration: none; }
  .utility__links { display: flex; flex-wrap: wrap; gap: 18px; }
  .doc-hero { display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(320px, .8fr); gap: clamp(30px, 5vw, 80px); padding: 52px 0 48px; }
  .kicker { margin: 0 0 12px; color: var(--accent); font: 700 11px/1.3 var(--mono); letter-spacing: .09em; text-transform: uppercase; }
  h1 { max-width: 800px; margin: 0; font-size: clamp(2.5rem, 5vw, 4.7rem); line-height: 1.01; letter-spacing: -.055em; text-wrap: balance; }
  .hero-copy { max-width: 760px; margin: 22px 0 0; color: var(--ink-2); font-size: 1.04rem; line-height: 1.7; text-wrap: pretty; }
  .hero-links { display: flex; flex-wrap: wrap; gap: 10px 22px; margin: 20px 0 0; }
  .hero-links a { color: var(--accent); font-size: .82rem; font-weight: 800; text-decoration-thickness: 1px; }
  .hero-links a:hover { color: var(--ink); }
  .doc-control { align-self: end; border-top: 1px solid rgba(24,34,41,.34); }
  .doc-control div { display: grid; grid-template-columns: 110px 1fr; gap: 14px; padding: 10px 0; border-bottom: 1px solid rgba(24,34,41,.16); }
  .doc-control dt { color: #748087; font: 700 10px/1.5 var(--mono); letter-spacing: .06em; }
  .doc-control dd { margin: 0; font-weight: 600; }
  .status-strip { color: var(--ink); background: #eadfca; border-bottom: 1px solid #c7bda9; }
  .status-strip__inner { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); width: min(1480px, calc(100% - 48px)); margin: auto; }
  .metric { padding: 18px 20px 17px; border-right: 1px solid #c7bda9; }
  .metric:first-child { border-left: 1px solid #c7bda9; }
  .metric strong { display: block; font: 700 clamp(1.55rem, 2.4vw, 2.2rem)/1 var(--mono); font-variant-numeric: tabular-nums; }
  .metric span { display: block; margin-top: 7px; color: #5d5a53; font-size: .76rem; font-weight: 700; }
  .shell { display: grid; grid-template-columns: 255px minmax(0, 1fr); gap: 42px; width: min(1480px, calc(100% - 48px)); margin: 40px auto 88px; align-items: start; }
  .toc { position: sticky; top: 20px; max-height: calc(100dvh - 40px); overflow: auto; scrollbar-width: thin; }
  .toc__title { margin: 0 0 10px; padding-bottom: 10px; border-bottom: 2px solid var(--ink); font: 700 12px/1.2 var(--mono); letter-spacing: .07em; text-transform: uppercase; }
  .toc ol { margin: 0; padding: 0; list-style: none; }
  .toc li { border-bottom: 1px solid rgba(77, 84, 87, .14); }
  .toc a { display: block; padding: 8px 6px; color: #46535c; font-size: .78rem; line-height: 1.35; text-decoration: none; transition: color .2s, background .2s, transform .2s; }
  .toc a:hover, .toc a[aria-current="true"] { color: var(--accent); background: rgba(255,255,255,.48); transform: translateX(3px); }
  .toc-3 a { padding-left: 19px; color: var(--muted); }
  .toc__actions { display: grid; gap: 8px; margin-top: 18px; }
  .button { display: inline-flex; align-items: center; justify-content: center; min-height: 44px; padding: 9px 12px; border: 1px solid var(--ink); color: var(--ink); background: transparent; font: 700 .76rem/1.2 var(--sans); text-decoration: none; cursor: pointer; transition: transform .18s, color .18s, background .18s; }
  .button:hover { color: #fff; background: var(--ink); transform: translateY(-2px); }
  .button:active { transform: translateY(0); }
  .button.button--accent { color: #fff; background: var(--accent); border-color: var(--accent); }
  .button.button--accent[aria-pressed="true"] { background: var(--ink); border-color: var(--ink); box-shadow: inset 0 -4px 0 var(--accent); }
  .document { min-width: 0; background: var(--surface); border: 1px solid var(--line); box-shadow: 12px 12px 0 rgba(118,108,92,.09), var(--shadow); }
  .executive { display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(270px, .65fr); gap: 28px; padding: clamp(28px, 5vw, 60px); background: linear-gradient(120deg, #fffdf8 0 72%, #f1e9dc 72%); border-bottom: 1px solid var(--line); }
  .section-label { margin: 0 0 12px; color: var(--accent); font: 700 11px/1.2 var(--mono); letter-spacing: .09em; text-transform: uppercase; }
  .executive h2 { margin: 0; font-size: clamp(1.65rem, 3vw, 2.6rem); line-height: 1.16; letter-spacing: -.035em; }
  .executive p { max-width: 65ch; margin: 18px 0 0; color: var(--ink-2); }
  .endpoint-bar { display: flex; height: 14px; margin-top: 25px; overflow: hidden; border: 1px solid #b8ad9b; }
  .endpoint-bar span:first-child { width: 55.56%; background: var(--ink); }
  .endpoint-bar span:last-child { width: 44.44%; background: var(--accent); }
  .endpoint-key { display: flex; flex-wrap: wrap; gap: 14px 24px; margin-top: 10px; color: var(--muted); font-size: .78rem; font-weight: 700; }
  .endpoint-key i { display: inline-block; width: 9px; height: 9px; margin-right: 6px; background: var(--ink); }
  .endpoint-key span:last-child i { background: var(--accent); }
  .decision-box { padding: 20px; background: rgba(255,253,248,.72); border-left: 3px solid var(--accent); }
  .decision-box strong { display: block; margin-bottom: 9px; font: 700 12px/1.4 var(--mono); }
  .decision-box p { margin: 0; font-size: .87rem; }
  .architecture { padding: 34px clamp(24px, 5vw, 60px) 44px; border-bottom: 1px solid var(--line); }
  .architecture__head { display: flex; align-items: end; justify-content: space-between; gap: 24px; margin-bottom: 18px; }
  .architecture h2 { margin: 0; font-size: 1.45rem; letter-spacing: -.025em; }
  .architecture__head p { max-width: 54ch; margin: 0; color: var(--muted); font-size: .84rem; }
  .diagram-link { display: block; overflow: hidden; border: 1px solid var(--line-strong); background: #f5f5f5; }
  .diagram-link img { display: block; width: 100%; height: auto; transition: transform .35s ease; }
  .diagram-link:hover img { transform: scale(1.012); }
  .diagram-caption { display: flex; justify-content: space-between; gap: 20px; margin-top: 10px; color: var(--muted); font-size: .76rem; }
  .mlops-bridge { display: grid; grid-template-columns: minmax(0, 1.08fr) minmax(330px, .92fr); gap: clamp(30px, 5vw, 72px); padding: clamp(38px, 6vw, 72px); color: #eef3f4; background: #25343d; border-bottom: 5px solid var(--accent); }
  .mlops-bridge .section-label { color: #f2a469; }
  .mlops-bridge h2 { max-width: 16ch; margin: 0; font-size: clamp(1.9rem, 3.4vw, 3.25rem); line-height: 1.08; letter-spacing: -.045em; text-wrap: balance; }
  .mlops-bridge__copy { max-width: 63ch; margin: 20px 0 0; color: #ccd6da; }
  .mlops-plan { display: grid; grid-template-columns: repeat(3, 1fr); margin-top: 28px; border: 1px solid rgba(255,255,255,.24); }
  .mlops-plan > div { min-width: 0; padding: 18px; border-right: 1px solid rgba(255,255,255,.18); }
  .mlops-plan > div:last-child { border-right: 0; }
  .mlops-plan strong { display: block; color: #fff; font: 750 clamp(1.7rem, 3vw, 2.5rem)/1 var(--mono); }
  .mlops-plan span, .mlops-plan small { display: block; }
  .mlops-plan span { margin-top: 8px; font-size: .82rem; font-weight: 800; }
  .mlops-plan small { margin-top: 3px; color: #aebdc3; font-size: .71rem; }
  .mlops-boundary { margin: 18px 0 0; padding-left: 14px; color: #b9c6cb; border-left: 3px solid #f2a469; font-size: .79rem; }
  .mlops-actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 24px; }
  .mlops-actions .button { color: #fff; border-color: rgba(255,255,255,.6); }
  .mlops-actions .button:hover { color: var(--ink); background: #fff; }
  .mlops-actions .button--accent { border-color: var(--accent); }
  .mlops-bridge__flow { align-self: center; padding: 24px; color: var(--ink); background: #f7f3ea; }
  .mlops-bridge__flow > p { margin: 0 0 16px; font: 800 11px/1.3 var(--mono); letter-spacing: .08em; text-transform: uppercase; }
  .mlops-steps { display: grid; gap: 0; margin: 0; padding: 0; list-style: none; counter-reset: mlops-step; }
  .mlops-steps li { display: grid; grid-template-columns: 34px minmax(0, 1fr); gap: 12px; align-items: center; min-height: 46px; padding: 7px 0; border-top: 1px solid #d5cfc2; counter-increment: mlops-step; }
  .mlops-steps li:first-child { border-top: 0; }
  .mlops-steps li::before { display: grid; width: 28px; height: 28px; place-items: center; content: counter(mlops-step); color: #fff; background: var(--accent); border-radius: 50%; font: 800 .73rem/1 var(--mono); }
  .mlops-steps strong { display: block; font-size: .86rem; line-height: 1.35; }
  .mlops-steps small { display: block; margin-top: 2px; color: var(--muted); font-size: .7rem; line-height: 1.35; }
  .content { padding: clamp(32px, 6vw, 74px); content-visibility: auto; contain-intrinsic-size: auto 48000px; }
  .content > h2 { margin: 4.5rem 0 1.4rem; padding: .55rem 0 .7rem; border-top: 4px solid var(--ink); border-bottom: 1px solid var(--line); font-size: clamp(1.55rem, 3vw, 2.2rem); line-height: 1.2; letter-spacing: -.035em; }
  .content > h2:first-child { margin-top: 0; }
  .content h3 { margin: 3rem 0 1rem; padding-left: 12px; border-left: 4px solid var(--accent); font-size: 1.25rem; line-height: 1.3; letter-spacing: -.02em; }
  .anchor { margin-left: 8px; color: transparent; font: 500 .8em/1 var(--mono); text-decoration: none; }
  h2:hover .anchor, h3:hover .anchor, .anchor:focus { color: #a9a294; }
  .content p { max-width: 74ch; margin: .85rem 0 1.05rem; color: var(--ink-2); text-wrap: pretty; }
  .content ul, .content ol { max-width: 76ch; padding-left: 1.4rem; }
  .content li { margin: .35rem 0; padding-left: .15rem; }
  .content li::marker { color: var(--accent); font-weight: 700; }
  code { padding: .14em .36em; color: #7c3512; background: #f4e8dc; border: 1px solid #e6d3c0; font: .86em/1.45 var(--mono); overflow-wrap: anywhere; }
  pre { overflow: auto; padding: 18px; color: #e8edf0; background: var(--ink); }
  pre code { padding: 0; color: inherit; background: none; border: 0; }
  .status { display: inline-block; padding: .16em .48em; border: 1px solid currentColor; font: 700 .76em/1.45 var(--sans); letter-spacing: -.01em; white-space: nowrap; }
  .modelled { color: var(--green); background: #edf7f2; }
  .confirmed { color: #29577b; background: #edf4f9; }
  .local { color: #315f83; background: #edf4f9; }
  .guarded { color: #73540f; background: #fff5d6; }
  .branch { color: #684085; background: #f7effb; }
  .preview { color: #29577b; background: #eaf5fb; }
  .planned, .assumed { color: var(--amber); background: #fff7e3; }
  .unknown, .excluded { color: #626972; background: #f1f2f3; }
  .gated { color: var(--red); background: #fff0ed; }
  .table-scroll { max-width: 100%; margin: 1.2rem 0 1.65rem; overflow-x: auto; border: 1px solid var(--line); }
  table { width: 100%; border-collapse: collapse; font-size: .84rem; line-height: 1.5; font-variant-numeric: tabular-nums; }
  thead { background: var(--ink); color: #fff; }
  th, td { min-width: 110px; padding: 10px 12px; border-right: 1px solid var(--line); border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
  th { font-weight: 700; }
  tbody tr:nth-child(even) { background: var(--surface-2); }
  tbody tr:hover { background: #f5eade; }
  td:last-child, th:last-child { border-right: 0; }
  .note { margin: 1.3rem 0; padding: 14px 18px; color: var(--ink-2); background: #f7f0e5; border-left: 4px solid var(--accent); }
  hr { margin: 3rem 0; border: 0; border-top: 1px solid var(--line); }
  .footer { display: flex; justify-content: space-between; gap: 24px; padding: 24px clamp(28px, 5vw, 60px); color: #59646b; background: #e8e2d7; border-top: 1px solid var(--line); font-size: .76rem; }
  .footer p { margin: 0; }
  .footer strong { color: var(--ink); }
  @media (max-width: 980px) {
    .doc-hero, .executive, .mlops-bridge { grid-template-columns: 1fr; }
    .status-strip__inner { grid-template-columns: repeat(3, 1fr); }
    .shell { grid-template-columns: 1fr; }
    .toc { position: static; max-height: none; }
    .toc ol { columns: 2; column-gap: 24px; }
    .toc li { break-inside: avoid; }
  }
  @media (max-width: 640px) {
    body { font-size: 15px; }
    .masthead__inner, .status-strip__inner, .shell { width: min(100% - 24px, 1480px); }
    .utility { align-items: flex-start; flex-direction: column; gap: 12px; padding: 14px 0; }
    .doc-hero { padding: 36px 0; }
    h1 { font-size: 2.45rem; }
    .status-strip__inner { grid-template-columns: repeat(2, 1fr); }
    .metric { padding: 14px 12px; }
    .shell { margin-top: 24px; }
    .toc ol { columns: 1; }
    .architecture__head, .diagram-caption, .footer { align-items: flex-start; flex-direction: column; }
    .mlops-bridge { padding: 32px 18px; }
    .mlops-plan { grid-template-columns: 1fr; }
    .mlops-plan > div { display: grid; grid-template-columns: 52px minmax(0, 1fr); gap: 3px 12px; padding: 14px; border-right: 0; border-bottom: 1px solid rgba(255,255,255,.18); }
    .mlops-plan > div:last-child { border-bottom: 0; }
    .mlops-plan strong { grid-row: 1 / 3; align-self: center; }
    .mlops-plan span, .mlops-plan small { grid-column: 2; margin-top: 0; }
    .mlops-plan small, .mlops-steps small { font-size: .76rem; }
    .content { padding: 28px 18px 48px; }
    .content > h2 { margin-top: 3.5rem; }
    .executive { background: var(--surface); }
  }
  @media (prefers-reduced-motion: reduce) { html { scroll-behavior: auto; } *, *::before, *::after { animation: none !important; transition-duration: .01ms !important; } }
  @media print {
    @page { size: A4; margin: 14mm 13mm 15mm; }
    body { background: #fff; color: #111; font-size: 9.2pt; line-height: 1.55; }
    body::before, .skip, .utility, .status-strip, .toc, .architecture__head .button, .hero-links, .mlops-actions, .anchor { display: none !important; }
    .masthead { color: #111; background: #fff; border-bottom: 2pt solid #111; }
    .masthead__inner, .shell { width: 100%; }
    .doc-hero { grid-template-columns: 1fr .7fr; padding: 10mm 0 9mm; }
    .kicker, .hero-copy, .doc-control dt { color: #333; }
    h1 { font-size: 28pt; }
    .doc-control { border-color: #777; }
    .doc-control div { border-color: #bbb; }
    .shell { display: block; margin: 0; }
    .document { border: 0; box-shadow: none; }
    .executive, .architecture, .mlops-bridge, .content { padding-left: 0; padding-right: 0; }
    .content { content-visibility: visible; contain-intrinsic-size: none; }
    .executive { background: #fff; }
    .architecture { break-before: page; }
    .mlops-bridge { grid-template-columns: 1fr .82fr; gap: 9mm; break-before: page; break-inside: avoid; color: #111; background: #fff; border-bottom: 2pt solid #111; }
    .mlops-bridge .section-label, .mlops-bridge__copy, .mlops-boundary { color: #333; }
    .mlops-plan { border-color: #777; }
    .mlops-plan > div { border-color: #bbb; }
    .mlops-plan strong { color: #111; }
    .mlops-plan small { color: #444; }
    .mlops-bridge__flow { padding: 5mm; background: #f2f2f2; }
    .diagram-link { border: 1pt solid #555; }
    .content > h2 { break-before: page; margin-top: 0; border-top-width: 2pt; }
    .content > h2:first-child { break-before: auto; }
    h3, table, figure { break-inside: avoid; }
    thead { display: table-header-group; color: #fff !important; background: #333 !important; print-color-adjust: exact; }
    tr { break-inside: avoid; }
    .table-scroll { overflow: visible; }
    table { font-size: 7.5pt; }
    th, td { min-width: 0; padding: 4pt 5pt; }
    .footer { padding-left: 0; padding-right: 0; background: #fff; }
    a { color: inherit; text-decoration: none; }
  }
`;

const indexHtml = `<!doctype html>
<html lang="ko">
<head>
${commonHead}
  <meta property="og:title" content="J-Career 서비스·인프라 시스템 명세">
  <meta property="og:description" content="채용 서비스의 구성요소, 기능, API, 데이터 흐름과 AWS 기준 설계를 확인합니다.">
  <meta property="og:url" content="https://kshield-junior-17th-proj.github.io/jcareer-spec/terraform/asis/">
  <link rel="canonical" href="https://kshield-junior-17th-proj.github.io/jcareer-spec/terraform/asis/">
  <title>J-Career 서비스·인프라 시스템 명세</title>
  <style>${commonCss}</style>
</head>
<body>
  <a class="skip" href="#specification">본문으로 건너뛰기</a>
  <header class="masthead">
    <div class="masthead__inner">
      <div class="utility">
        <a href="index.html">J-Career / 서비스·인프라 명세</a>
        <nav class="utility__links" aria-label="산출물">
          <a href="../../mlops/">MLOps</a>
          <a href="architecture.html">인프라 도면</a>
          <a href="JCAREER_ASIS_SYSTEM_SPEC.pdf">PDF</a>
          <a href="JCAREER_ASIS_FLOW.drawio">DRAW.IO 원본</a>
          <a href="validation-report.json">검증 JSON</a>
        </nav>
      </div>
      <div class="doc-hero">
        <div>
          <p class="kicker">JC-ASIS-SPEC-001 · 2026.08 기준 설계</p>
          <h1>J-Career 서비스·인프라<br>시스템 명세</h1>
          <p class="hero-copy">채용 서비스의 기능과 데이터, AWS 인프라와 운영 통제, MLOps 모델 검증을 한 문서로 정리했습니다. 업무망 PC 180대와 서울 리전 2-AZ, 6개 Terraform 모듈, 110개 계획 항목을 기준으로 읽을 수 있습니다.</p>
          <p class="hero-links"><a href="#mlops-overview">MLOps 7단계 바로 보기 ↓</a><a href="../../mlops/">MLOps 전용 페이지 ↗</a></p>
        </div>
        <dl class="doc-control">
          <div><dt>문서 번호</dt><dd>JC-ASIS-SPEC-001</dd></div>
          <div><dt>기준일</dt><dd>2026-08-30</dd></div>
          <div><dt>문서 상태</dt><dd>기준 설계 · 기술 검토 진행</dd></div>
          <div><dt>배포 단계</dt><dd>AS-IS 미적용 · 검증 Lab 별도</dd></div>
          <div><dt>MLOps</dt><dd>별도 7단계 · 계획 0 / 13 / 14</dd></div>
          <div><dt>별도 검토</dt><dd>TRACE, JC-RECEIPT 등 제안 단계 서비스</dd></div>
        </dl>
      </div>
    </div>
  </header>

  <section class="status-strip" aria-label="핵심 수치">
    <div class="status-strip__inner">
      <div class="metric"><strong>180</strong><span>업무망 PC · 사용자 확정</span></div>
      <div class="metric"><strong>100</strong><span>Windows PC</span></div>
      <div class="metric"><strong>80</strong><span>macOS PC</span></div>
      <div class="metric"><strong>6</strong><span>Terraform을 나눈 구성 부분</span></div>
      <div class="metric"><strong>110</strong><span>Terraform 계획 항목 · 6개 모듈</span></div>
      <div class="metric"><strong>7</strong><span>MLOps 모델 검증 단계 · 별도 구성</span></div>
    </div>
  </section>

  <div class="shell">
    <aside class="toc" aria-label="문서 목차">
      <p class="toc__title">문서 목차</p>
      <ol>${toc}</ol>
      <div class="toc__actions">
        <a class="button button--accent" href="JCAREER_ASIS_SYSTEM_SPEC.pdf">PDF 내려받기</a>
        <a class="button" href="../../mlops/">MLOps 7단계</a>
        <a class="button" href="architecture.html">도면 크게 보기</a>
        <a class="button" href="JCAREER_ASIS_FLOW.drawio">편집 원본 받기</a>
        <a class="button" href="validation-report.json">검증 결과</a>
      </div>
    </aside>

    <main id="specification" class="document">
      <section class="executive" aria-labelledby="executive-title">
        <div>
          <p class="section-label">아키텍처 기준</p>
          <h2 id="executive-title">한눈에 보는 J-Career 인프라</h2>
          <p>업무망 PC는 180대이며 Windows 100대, macOS 80대로 구성됩니다. AWS는 서울 리전의 두 가용 영역과 6개 Terraform 모듈, 110개 계획 항목을 기준으로 설계했습니다. 배포 여부와 실행 결과는 별도의 검증 기록에서 관리합니다.</p>
          <div class="endpoint-bar" role="img" aria-label="업무망 PC 180대 중 Windows 100대, macOS 80대"><span></span><span></span></div>
          <div class="endpoint-key"><span><i></i>Windows 100 · 55.6%</span><span><i></i>macOS 80 · 44.4%</span></div>
        </div>
        <aside class="decision-box">
          <strong>문서 적용 기준</strong>
          <p>이 명세는 시스템 구조와 검증 범위를 설명합니다. 적합성, 인증 가능성, 보안 통제 충족 여부는 별도의 평가와 승인 절차가 필요합니다. ISO 엑셀은 검증 전 템플릿으로 관리하며 외부 증거나 번역문을 공식 문구로 전용하지 않습니다.</p>
        </aside>
      </section>

      <section class="architecture" aria-labelledby="architecture-title">
        <div class="architecture__head">
          <div><p class="section-label">상호작용 전체 흐름도</p><h2 id="architecture-title">전체 구성에서 서비스별 경로까지</h2><p>전체 보기와 서비스 경로 5개를 제공합니다. 서비스를 누르면 관련 구간, 번호와 확인 수준이 함께 바뀝니다.</p></div>
          <a class="button" href="architecture.html">서비스 경로 탐색</a>
        </div>
        <a class="diagram-link" href="architecture.html" aria-label="서비스별로 탐색할 수 있는 AWS 인프라 흐름도 열기">
          <img src="JCAREER_ASIS_FLOW.drawio.png" width="2400" height="1400" loading="lazy" decoding="async" alt="업무망 Windows 100대와 macOS 80대, 사용자 요청 6단계, 가용 영역 두 곳, 데이터 저장소, 기록·탐지와 승인 전 MLOps 확장 경계를 표시한 J-Career 기존 설계 흐름도">
        </a>
        <div class="diagram-caption"><span>실선: 구성 확인 · 점선: 실제 연결 미구현</span><span>서비스별 강조 경로는 도면 페이지에서 확인 · 비밀정보 미표시</span></div>
      </section>

      <section id="mlops-overview" class="mlops-bridge" aria-labelledby="mlops-overview-title">
        <div>
          <p class="section-label">MLOps 모델 검증</p>
          <h2 id="mlops-overview-title">후보 모델은 사람 검토 전까지 추천에 쓰지 않습니다.</h2>
          <p class="mlops-bridge__copy">합성 회원·기업 자료에서 다섯 가지 비교 수치만 뽑아 입력 파일을 만듭니다. 담당자가 작업을 한 번 시작하면 후보 모델과 비교 결과가 남습니다. 자동 일정과 자동 배포는 두지 않았습니다.</p>
          <div class="mlops-plan" aria-label="MLOps Terraform 단계별 계획 수">
            <div data-mlops-plan="0"><strong>0</strong><span>기본 잠금</span><small>생성 계획 없음</small></div>
            <div data-mlops-plan="13"><strong>13</strong><span>보관함 준비</span><small>파일·상태·로그·권한</small></div>
            <div data-mlops-plan="14"><strong>14</strong><span>한 번 실행 준비</span><small>13개 + 작업 실행기</small></div>
          </div>
          <p class="mlops-boundary">MLOps는 기준 110개와 분리한 별도 계획이며 수치를 합산하지 않습니다. AWS 배포와 모델 품질은 이 문서에서 확인하지 않았습니다.</p>
          <div class="mlops-actions"><a class="button button--accent" href="../../mlops/">7단계 자세히 보기</a><a class="button" href="../../mlops/JCAREER_MLOPS_SYSTEM_SPEC.pdf">MLOps PDF</a></div>
        </div>
        <div class="mlops-bridge__flow">
          <p>자료가 움직이는 순서</p>
          <ol class="mlops-steps">
            <li data-mlops-stage="1"><div><strong>합성 자료 읽기</strong><small>회원·기업 시험 자료만 사용</small></div></li>
            <li data-mlops-stage="2"><div><strong>비교 수치 만들기</strong><small>원문 대신 숫자 특징 5개</small></div></li>
            <li data-mlops-stage="3"><div><strong>입력 파일 보관</strong><small>CSV 1개와 검증 JSON 2개</small></div></li>
            <li data-mlops-stage="4"><div><strong>담당자가 한 번 시작</strong><small>확인값과 실행 번호 입력</small></div></li>
            <li data-mlops-stage="5"><div><strong>파일 검사·후보 학습</strong><small>허용 항목과 파일 지문 확인</small></div></li>
            <li data-mlops-stage="6"><div><strong>결과와 상태 기록</strong><small>결과 파일 6개와 처리 상태</small></div></li>
            <li data-mlops-stage="7"><div><strong>사람 검토 대기</strong><small>추천 서비스에는 자동 반영하지 않음</small></div></li>
          </ol>
        </div>
      </section>

      <article class="content">${body}</article>
      <footer class="footer"><p><strong>JC-ASIS-SPEC-001</strong> · 기준일 2026-08-30</p><p>J-Career 서비스·인프라 기준 설계 · 배포 검증 별도 관리</p></footer>
    </main>
  </div>
  <script>
    const links = [...document.querySelectorAll('.toc ol a[href^="#"]')];
    const sections = links.map((link) => document.querySelector(link.hash)).filter(Boolean);
    const observer = new IntersectionObserver((entries) => {
      const current = entries.filter((entry) => entry.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
      if (!current) return;
      links.forEach((link) => link.removeAttribute('aria-current'));
      const active = links.find((link) => link.hash === '#' + current.target.id);
      if (active) active.setAttribute('aria-current', 'true');
    }, { rootMargin: '-15% 0px -75% 0px' });
    sections.forEach((section) => observer.observe(section));
  </script>
</body>
</html>`;

const architectureHtml = `<!doctype html>
<html lang="ko">
<head>
${commonHead}
  <meta property="og:title" content="J-Career AWS 인프라 흐름도">
  <meta property="og:description" content="서비스 버튼을 누르면 채용 기능과 MLOps, 보안·운영 경로를 단계별로 볼 수 있습니다.">
  <meta property="og:url" content="https://kshield-junior-17th-proj.github.io/jcareer-spec/terraform/asis/architecture.html">
  <link rel="canonical" href="https://kshield-junior-17th-proj.github.io/jcareer-spec/terraform/asis/architecture.html">
  <meta name="flow-source-sha256" content="${flowSourceHash}">
  <title>J-Career AWS 인프라 흐름도</title>
  <style>
${commonCss}
    .plate { width: min(1520px, calc(100% - 48px)); margin: 38px auto 80px; }
    .plate__nav { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin-bottom: 18px; }
    .plate__nav a { color: var(--ink); font-weight: 700; }
    .motion-toggle-doc { min-height: 40px; display: inline-flex; align-items: center; gap: 7px; padding: 8px 10px; border: 1px solid rgba(24,34,41,.28); color: var(--ink); background: transparent; cursor: pointer; font-family: var(--sans); font-size: 11px; font-weight: 700; line-height: 1.2; letter-spacing: 0; transition: color .18s, background .18s, border-color .18s, transform .18s; }
    .motion-toggle-doc::before { width: 17px; height: 7px; border-radius: 999px; background: var(--accent); box-shadow: 7px 0 0 -2px rgba(189,77,30,.24); content: ""; animation: motionSignal 1.6s ease-in-out infinite; }
    .motion-toggle-doc:hover { color: var(--ink); background: #fff; border-color: var(--ink); }
    .motion-toggle-doc:active { transform: translateY(1px); }
    .motion-toggle-doc[aria-pressed="true"]::before { background: #9ba8af; box-shadow: none; animation: none; }
    .architecture-workspace { display: grid; grid-template-columns: minmax(370px, .62fr) minmax(0, 1.38fr); gap: 18px; align-items: start; }
    .flow-explorer { margin: 0; padding: 30px; background: var(--ink); color: white; border-top: 5px solid var(--accent); box-shadow: var(--shadow); }
    .flow-explorer__head { display: grid; grid-template-columns: 1fr; gap: 12px; align-items: end; }
    .flow-explorer__head h2 { max-width: 760px; margin: 0; font-size: clamp(1.7rem, 3.5vw, 2.75rem); line-height: 1.12; letter-spacing: -.04em; text-wrap: balance; }
    .flow-explorer__head > p { margin: 0; color: #cfd8de; font-size: .9rem; line-height: 1.65; }
    .flow-selector { margin-top: 22px; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
    .flow-button { min-height: 72px; padding: 12px 14px; display: flex; flex-direction: column; justify-content: center; align-items: flex-start; gap: 4px; border: 1px solid #69757e; color: #f7f9fa; background: transparent; font-family: inherit; text-align: left; cursor: pointer; transition: border-color .18s, background .18s, transform .18s; }
    .flow-button:hover { border-color: #f2a469; background: rgba(255,255,255,.06); transform: translateY(-2px); }
    .flow-button[aria-pressed="true"] { border-color: #f2a469; background: #fff; color: var(--ink); box-shadow: inset 0 -4px 0 var(--accent); }
    .flow-button strong { font-size: .88rem; line-height: 1.25; }
    .flow-button small { color: #aebbc4; font-size: .68rem; line-height: 1.25; }
    .flow-button[aria-pressed="true"] small { color: #65717a; }
    .flow-detail { margin-top: 12px; padding: 22px; display: grid; grid-template-columns: 1fr; gap: 20px; background: #fff; color: var(--ink); border-left: 4px solid var(--accent); view-transition-name: flow-detail; }
    .flow-detail__status { margin-bottom: 10px; }
    .flow-detail h3 { margin: 0; font-size: 1.35rem; letter-spacing: -.025em; }
    .flow-detail__summary { margin: 9px 0 0; color: var(--ink-2); font-size: .84rem; line-height: 1.65; text-wrap: pretty; }
    .flow-detail__route { min-width: 0; }
    .flow-detail__route > strong, .flow-detail__boundary strong { display: block; margin-bottom: 9px; font: 700 11px/1.3 var(--mono); letter-spacing: .06em; text-transform: uppercase; }
    .flow-steps { margin: 0; padding: 0; display: grid; gap: 6px; list-style: none; }
    .flow-steps li { min-height: 42px; display: grid; grid-template-columns: 30px minmax(0, 1fr); align-items: center; gap: 10px; padding: 7px 11px; color: #364650; background: #f2f0e9; border: 1px solid #d8d2c6; font-size: .78rem; font-weight: 700; }
    .flow-step__number { width: 28px; height: 28px; display: inline-grid; place-items: center; color: white; background: var(--accent); border-radius: 50%; font: 800 12px/1 var(--mono); font-variant-numeric: tabular-nums; }
    .flow-detail__boundary { padding-top: 14px; border-top: 1px solid var(--line); }
    .flow-detail__boundary p { margin: 0; color: #59666e; font-size: .78rem; line-height: 1.6; }
    .flow-detail__link { display: inline-flex; align-items: center; margin-top: 13px; padding-bottom: 2px; color: var(--ink); border-bottom: 2px solid var(--accent); font-size: .78rem; font-weight: 800; text-decoration: none; transition: color .18s, border-color .18s; }
    .flow-detail__link::after { content: ' →'; margin-left: 4px; }
    .flow-detail__link:hover { color: var(--accent); border-color: var(--accent); }
    .flow-explorer__exclusion { margin: 13px 0 0; color: #aebbc4; font-size: .72rem; }
    .plate__frame { position: relative; margin: 0 12px 12px 0; padding: 18px; overflow: auto; background: var(--surface); border: 1px solid var(--line); box-shadow: 12px 12px 0 #d4cdc0, 0 34px 72px rgba(45,49,47,.14); }
    .diagram-stage { position: relative; width: 100%; min-width: 720px; }
    .diagram-stage > a, .diagram-stage img { display: block; width: 100%; }
    .diagram-stage img { height: auto; border: 1px solid var(--line); filter: saturate(.82) contrast(1.02); transition: filter .35s ease; }
    .plate__frame:hover .diagram-stage img { filter: saturate(1) contrast(1.04); }
    .flow-overlay { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
    .flow-layer { opacity: 0; transition: opacity .25s ease; }
    .flow-layer.is-active { opacity: 1; }
    .flow-line { fill: none; stroke: #e87928; stroke-width: 16; stroke-linecap: round; stroke-linejoin: round; opacity: .82; filter: drop-shadow(0 2px 2px rgba(32,43,53,.28)); stroke-dasharray: 34 18; animation: flowMarch 1.05s linear infinite; }
    .flow-line.local { stroke: #0d7f9b; stroke-dasharray: 18 16; }
    .flow-line.missing { stroke: #bd22bf; stroke-dasharray: 7 18; }
    .flow-line.record { stroke: #8a5a00; stroke-dasharray: 34 18; }
    .flow-node { fill: rgba(255,255,255,.22); stroke: #e87928; stroke-width: 10; }
    .flow-node.local { stroke: #0d7f9b; }
    .flow-node.missing { stroke: #bd22bf; stroke-dasharray: 12 9; }
    .flow-node.record { stroke: #8a5a00; stroke-dasharray: 12 9; }
    .flow-marker { fill: var(--ink); stroke: #fff; stroke-width: 4; }
    .flow-marker.local { fill: #0d7f9b; }
    .flow-marker.missing { fill: #8c2e8f; }
    .flow-marker.record { fill: #765313; }
    .flow-marker-text { fill: #fff; font: 800 22px/1 var(--sans); text-anchor: middle; dominant-baseline: central; }
    .flow-step-marker { filter: drop-shadow(0 2px 3px rgba(32,43,53,.34)); transform-box: fill-box; transform-origin: center; }
    .flow-callout { fill: #fff; stroke: #0d7f9b; stroke-width: 4; }
    .flow-callout.missing { stroke: #bd22bf; stroke-dasharray: 12 9; }
    .flow-callout-text { fill: var(--ink); font: 800 24px/1.2 var(--sans); text-anchor: middle; }
    .plate__frame.is-zoomed .diagram-stage { width: 2400px; }
    .diagram-legend { margin-top: 12px; display: flex; flex-wrap: wrap; gap: 10px 22px; color: var(--muted); font-size: .74rem; }
    .diagram-legend span { display: inline-flex; align-items: center; gap: 7px; }
    .legend-line { width: 32px; border-top: 4px solid #e87928; }
    .legend-line.local { border-color: #0d7f9b; border-top-style: dashed; }
    .legend-line.missing { border-color: #c61bc9; border-top-style: dashed; }
    .legend-line.record { border-color: #8a5a00; }
    .plate__section { padding: 28px; background: var(--surface); border-top: 4px solid var(--ink); }
    .plate__section h2 { margin: 0 0 16px; font-size: 1.35rem; }
    .plate__section p { color: var(--ink-2); }
    .plate__source { margin-top: 28px; }
    .plate__source > h2 { margin-top: 44px; padding-top: 20px; border-top: 1px solid var(--line); }
    .plate__source > h2:first-of-type { margin-top: 0; }
    .plate__source h3 { margin-top: 28px; }
    .plate__source table { font-size: .84rem; }
    .scroll-progress { position: fixed; inset: 0 0 auto; z-index: 60; height: 3px; pointer-events: none; }
    .scroll-progress span { display: block; width: 100%; height: 100%; background: #e87928; transform: scaleX(0); transform-origin: left center; }
    @keyframes flowMarch { to { stroke-dashoffset: -52; } }
    @keyframes motionSignal { 50% { transform: translateX(5px); opacity: .58; } }
    ::view-transition-old(flow-detail) { animation: .18s ease both flowOld; }
    ::view-transition-new(flow-detail) { animation: .34s cubic-bezier(.2,.75,.2,1) both flowNew; }
    @keyframes flowOld { to { opacity: 0; transform: translateY(-8px); } }
    @keyframes flowNew { from { opacity: 0; transform: translateY(10px); } }
    html[data-motion="reduced"] .flow-line, html[data-motion="reduced"] .motion-toggle-doc::before, html.document-hidden .flow-line { animation: none; }
    html[data-motion="reduced"] .scroll-progress { display: none; }
    html[data-motion="reduced"] *, html[data-motion="reduced"] *::before, html[data-motion="reduced"] *::after { animation: none !important; transition-duration: .01ms !important; }
    @media (max-width: 1200px) { .architecture-workspace { grid-template-columns: 1fr; } .flow-explorer__head { grid-template-columns: minmax(0, 1fr) minmax(260px, .46fr); gap: 36px; } .flow-selector { grid-template-columns: repeat(3, minmax(0, 1fr)); } .flow-detail { grid-template-columns: minmax(250px, .65fr) minmax(0, 1.35fr); gap: 30px; } .flow-detail__boundary { grid-column: 1 / -1; } }
    @media (max-width: 1060px) { .flow-selector { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
    @media (max-width: 880px) { .plate__nav, .flow-explorer__head { align-items: flex-start; grid-template-columns: 1fr; } .plate__nav { flex-direction: column; } .flow-detail { grid-template-columns: 1fr; } }
    @media (max-width: 640px) { .plate { width: calc(100% - 24px); margin-top: 20px; } .plate__frame { padding: 6px; } .flow-explorer { padding: 24px 18px; } .flow-selector { grid-template-columns: 1fr 1fr; } .flow-button { min-height: 64px; } .flow-detail { padding: 19px; gap: 20px; } .flow-detail__boundary { grid-column: auto; } .diagram-stage { min-width: 900px; } }
    @media (max-width: 410px) { .flow-selector { grid-template-columns: 1fr; } }
    @media print { .flow-selector, .flow-overlay, .plate__nav button { display: none !important; } .flow-explorer { color: #111; background: #fff; border: 1pt solid #555; box-shadow: none; } .flow-explorer__head > p, .flow-explorer__exclusion { color: #333; } .flow-detail { border: 1pt solid #777; } .diagram-stage { min-width: 0; } }
  </style>
</head>
<body>
  <a class="skip" href="#diagram">도면으로 건너뛰기</a>
  <header class="masthead">
    <div class="masthead__inner">
      <div class="utility"><a href="index.html">← 기술 명세</a><nav class="utility__links" aria-label="산출물"><a href="../../mlops/">MLOps 7단계</a><a href="JCAREER_ASIS_FLOW.drawio">DRAW.IO</a><a href="JCAREER_ASIS_FLOW.drawio.png">PNG</a><a href="JCAREER_ASIS_SYSTEM_SPEC.pdf">PDF</a><a href="validation-report.json">검증 JSON</a><button class="motion-toggle-doc" type="button" data-motion-toggle aria-pressed="false" hidden><span data-motion-label>움직임 줄이기</span></button></nav></div>
      <div class="doc-hero">
        <div><p class="kicker">JC-ASIS-ARCH-001 · 서비스별 경로 탐색</p><h1>J-Career AWS<br>인프라 흐름도</h1><p class="hero-copy">업무망 PC에서 채용 서비스와 데이터 저장소, 보안·관측 구성으로 이어지는 흐름을 한 장에 담았습니다. 서비스 버튼을 누르면 관련 경로와 1·2·3 단계 설명이 함께 바뀝니다.</p></div>
        <dl class="doc-control"><div><dt>도면 성격</dt><dd>서비스·인프라 기준 설계</dd></div><div><dt>업무망</dt><dd>180대 · Windows 100 / macOS 80</dd></div><div><dt>AWS 설계</dt><dd>2-AZ · 6개 모듈 · 계획 110개</dd></div><div><dt>MLOps</dt><dd>별도 7단계 · 계획 0 / 13 / 14</dd></div><div><dt>검증 단계</dt><dd>AWS 배포 결과 별도 관리</dd></div></dl>
      </div>
    </div>
  </header>
  <main class="plate" id="diagram">
    <div class="plate__nav"><p>업무망 수량은 <span class="status confirmed" title="내부 상태 코드: USER_CONFIRMED">사용자 확인</span> 값이며, AWS 구성은 <span class="status modelled" title="내부 상태 코드: MODELLED">기준 설계 반영</span> 항목입니다. 배포 결과는 검증 기록에서 별도로 관리합니다.</p><div><button class="button button--accent" id="diagram-zoom" type="button" aria-pressed="false">원본 크기로 보기</button> <a class="button" href="JCAREER_ASIS_FLOW.drawio">편집 원본</a> <a class="button" href="JCAREER_ASIS_FLOW.drawio.png">PNG 원본</a></div></div>
    <div class="architecture-workspace">
    <section class="flow-explorer" aria-labelledby="flow-explorer-title">
      <div class="flow-explorer__head">
        <div><p class="kicker">전체 보기 1개 · 서비스·보조 경로 5개</p><h2 id="flow-explorer-title">전체는 ①~⑥, 선택 경로는 1·2·3으로 읽습니다.</h2></div>
        <p>전체 인프라는 바탕 도면의 ①~⑥을 따라갑니다. 나머지 다섯 선택 화면은 1·2·3 표시와 왼쪽 단계 목록이 같은 순서입니다.</p>
      </div>
      <div class="flow-selector" role="group" aria-label="표시할 서비스·보조 경로">
        <button class="flow-button" type="button" data-flow-button="overview" aria-pressed="true" aria-controls="flow-detail"><strong>전체 인프라</strong><small>기준 설계</small></button>
        <button class="flow-button" type="button" data-flow-button="candidate" aria-pressed="false" aria-controls="flow-detail"><strong>구직자 공고 추천</strong><small>AI · 구현 범위</small></button>
        <button class="flow-button" type="button" data-flow-button="recruiter" aria-pressed="false" aria-controls="flow-detail"><strong>기업용 인재 찾기</strong><small>AI · 공고 지원자 안에서</small></button>
        <button class="flow-button" type="button" data-flow-button="explanation" aria-pressed="false" aria-controls="flow-detail"><strong>AI 설명 만들기</strong><small>점수와 분리</small></button>
        <button class="flow-button" type="button" data-flow-button="mlops" aria-pressed="false" aria-controls="flow-detail"><strong>MLOps 학습·평가</strong><small>모델 검증 · 검토 대기</small></button>
        <button class="flow-button" type="button" data-flow-button="operations" aria-pressed="false" aria-controls="flow-detail"><strong>기록·탐지</strong><small>운영 보조 경로</small></button>
      </div>
      <article class="flow-detail" id="flow-detail" aria-live="polite" aria-atomic="false">
        <div>
          <span class="flow-detail__status status modelled" id="flow-status">Terraform 설계</span>
          <h3 id="flow-title">전체 인프라</h3>
          <p class="flow-detail__summary" id="flow-summary">사용자 진입부터 앱, 저장소, 기록·탐지까지 기준 Terraform이 표현한 전체 구성을 봅니다.</p>
        </div>
        <div class="flow-detail__route"><strong>순서대로 읽는 단계</strong><ol class="flow-steps" id="flow-steps" aria-label="전체 인프라 단계별 경로">${flowStepItems('overview')}</ol></div>
        <div class="flow-detail__boundary"><strong>설계 범위</strong><p id="flow-boundary">서울 리전 2-AZ, 6개 Terraform 모듈, 110개 계획 항목을 기준선으로 사용합니다. AWS 배포 상태와 실행 결과는 별도 검증 기록에서 관리합니다.</p><a class="flow-detail__link" id="flow-detail-link" href="index.html#section-14">서비스·구성요소 명세 보기</a></div>
      </article>
      <p class="flow-explorer__exclusion">MLOps는 합성 데이터 기반 모델 검증과 사람 검토 단계를 보여 줍니다. 기준 110개와 분리한 별도 계획이며 합산하지 않습니다. 제안 단계 신규 서비스는 현재 선택 경로에서 제외했습니다.</p>
    </section>
    <figure class="plate__frame" id="diagram-frame" aria-describedby="flow-boundary">
      <div class="diagram-stage" data-scale-reveal>
        <a href="JCAREER_ASIS_FLOW.drawio.png" aria-label="AWS 인프라 흐름도 PNG 원본 열기"><img src="JCAREER_ASIS_FLOW.drawio.png" width="2400" height="1400" fetchpriority="high" decoding="async" alt="업무망 PC 180대, 사용자 요청 6단계, 가용 영역 두 곳, 데이터 저장소, 기록·탐지와 승인 전 MLOps 확장 경계를 표시한 J-Career 기존 설계 흐름도"></a>
        <svg class="flow-overlay" viewBox="0 0 2400 1400" preserveAspectRatio="xMidYMid meet" aria-hidden="true" focusable="false">
          <g class="flow-layer is-active" data-flow-layer="overview">
            <path class="flow-line" d="M165 455H382 M490 455H628 M734 455H870 M980 455H1120V510H1216 M1348 510H1535" />
            <path class="flow-line missing" d="M1664 510H1822" />
            <path class="flow-line record" d="M1280 582V922 M1600 582V922" />
            <circle class="flow-node" cx="435" cy="435" r="68" /><circle class="flow-node" cx="680" cy="435" r="68" /><circle class="flow-node" cx="925" cy="455" r="70" /><circle class="flow-node" cx="1280" cy="510" r="68" /><circle class="flow-node" cx="1600" cy="510" r="70" />
          </g>
          <g class="flow-layer" data-flow-layer="candidate">
            <path class="flow-line" d="M165 455H382 M490 455H628 M734 455H870 M980 455H1120V510H1216 M1348 510H1535" />
            <circle class="flow-node local" cx="1600" cy="510" r="76" />
            <rect class="flow-callout" x="1370" y="330" width="460" height="62" rx="12" /><text class="flow-callout-text" x="1600" y="370">서비스 구현 범위 · 데이터 연계 검토</text>
${svgStepMarkers('candidate', 'local')}
          </g>
          <g class="flow-layer" data-flow-layer="recruiter">
            <path class="flow-line" d="M165 455H382 M490 455H628 M734 455H870 M980 455H1120V510H1216 M1348 510H1535" />
            <circle class="flow-node local" cx="1600" cy="510" r="76" />
            <rect class="flow-callout" x="1370" y="330" width="460" height="62" rx="12" /><text class="flow-callout-text" x="1600" y="370">서비스 구현 범위 · 데이터 연계 검토</text>
${svgStepMarkers('recruiter', 'local')}
          </g>
          <g class="flow-layer" data-flow-layer="explanation">
            <path class="flow-line" d="M165 455H382 M490 455H628 M734 455H870 M980 455H1120V510H1216 M1348 510H1535" />
            <circle class="flow-node local" cx="1600" cy="510" r="76" />
            <rect class="flow-callout" x="1405" y="330" width="390" height="62" rx="12" /><text class="flow-callout-text" x="1600" y="370">점수 고정 → 설명만 생성</text>
${svgStepMarkers('explanation', 'local')}
          </g>
          <g class="flow-layer" data-flow-layer="mlops">
            <rect class="flow-callout missing" x="1752" y="42" width="624" height="118" rx="14" />
${svgStepMarkers('mlops', 'missing')}
          </g>
          <g class="flow-layer" data-flow-layer="operations">
            <path class="flow-line record" d="M1280 582V922 M1600 582V922" />
            <circle class="flow-node record" cx="585" cy="990" r="74" /><circle class="flow-node record" cx="1300" cy="990" r="74" /><circle class="flow-node record" cx="1620" cy="990" r="74" /><circle class="flow-node record" cx="1990" cy="990" r="74" />
${svgStepMarkers('operations', 'record')}
          </g>
        </svg>
      </div>
      <figcaption class="diagram-legend"><span><i class="legend-line"></i>Terraform 기준 진입 경로</span><span><i class="legend-line local"></i>서비스 구현 경로</span><span><i class="legend-line missing"></i>추가 연결 검토</span><span><i class="legend-line record"></i>기록·탐지 구성</span><span>바탕 ①~⑥은 전체 흐름, 큰 원 1·2·3은 선택 경로입니다.</span><span>색상과 단계 설명을 함께 확인할 수 있습니다.</span></figcaption>
    </figure>
    </div>
    <section class="plate__section plate__source" data-flow-source-sha256="${flowSourceHash}">${flowBody}</section>
  </main>
  <script src="https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js" integrity="sha384-XmJ9SoHtVOHoQUcKvFAzVXwdkKo1Ie3bhmSoIAkcdsHGaIrVJIkmozyq0FJeb/Ly" crossorigin="anonymous"></script>
  <script src="https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/ScrollTrigger.min.js" integrity="sha384-wl5TeDVvOWt30Pbf8aSo2ZrzsOjddu3avOBvHe+p+OhJt9gP6w9YXmDkN5DK2/dF" crossorigin="anonymous"></script>
  <script src="../../assets/motion.js"></script>
  <script>
    const zoomButton = document.querySelector('#diagram-zoom');
    const diagramFrame = document.querySelector('#diagram-frame');
    zoomButton?.addEventListener('click', () => {
      const expanded = diagramFrame.classList.toggle('is-zoomed');
      zoomButton.setAttribute('aria-pressed', String(expanded));
      zoomButton.textContent = '원본 크기로 보기';
    });
    const flowDefinitions = ${JSON.stringify(architectureFlows)};
    const flowButtons = [...document.querySelectorAll('[data-flow-button]')];
    const flowLayers = [...document.querySelectorAll('[data-flow-layer]')];
    const flowStatus = document.querySelector('#flow-status');
    const flowTitle = document.querySelector('#flow-title');
    const flowSummary = document.querySelector('#flow-summary');
    const flowSteps = document.querySelector('#flow-steps');
    const flowBoundary = document.querySelector('#flow-boundary');
    const flowDetailLink = document.querySelector('#flow-detail-link');
    const showFlow = (requestedKey, updateAddress = true) => {
      const key = Object.hasOwn(flowDefinitions, requestedKey) ? requestedKey : 'overview';
      const definition = flowDefinitions[key];
      const updateFlow = () => {
        flowButtons.forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.flowButton === key)));
        flowLayers.forEach((layer) => layer.classList.toggle('is-active', layer.dataset.flowLayer === key));
        flowStatus.textContent = definition.status;
        flowStatus.className = 'flow-detail__status status ' + definition.tone;
        flowTitle.textContent = definition.title;
        flowSummary.textContent = definition.summary;
        flowSteps.setAttribute('aria-label', definition.title + ' 단계별 경로');
        flowSteps.replaceChildren(...definition.stages.map((stage, index) => {
          const item = document.createElement('li');
          const number = document.createElement('span');
          number.className = 'flow-step__number';
          number.setAttribute('aria-hidden', 'true');
          number.textContent = String(index + 1);
          const label = document.createElement('span');
          label.textContent = stage.label;
          item.append(number, label);
          return item;
        }));
        flowBoundary.textContent = definition.boundary;
        flowDetailLink.href = definition.detailHref;
        flowDetailLink.textContent = definition.detailLabel;
      };
      if (updateAddress && window.JCareerMotion) window.JCareerMotion.transition(updateFlow);
      else updateFlow();
      if (updateAddress || requestedKey !== key) {
        const address = new URL(window.location.href);
        if (key === 'overview') address.searchParams.delete('flow');
        else address.searchParams.set('flow', key);
        history.replaceState({ flow: key }, '', address);
      }
    };
    flowButtons.forEach((button) => button.addEventListener('click', () => showFlow(button.dataset.flowButton)));
    window.addEventListener('popstate', () => showFlow(new URLSearchParams(window.location.search).get('flow') || 'overview', false));
    showFlow(new URLSearchParams(window.location.search).get('flow') || 'overview', false);
  </script>
</body>
</html>`;

const generatedOutputs = [
  ['index.html', indexHtml],
  ['architecture.html', architectureHtml]
];

if (process.argv.includes('--check')) {
  let synchronized = true;
  for (const [name, expected] of generatedOutputs) {
    const outputPath = path.join(root, name);
    const actual = fs.existsSync(outputPath) ? fs.readFileSync(outputPath, 'utf8') : '';
    const matches = actual === expected;
    synchronized &&= matches;
    console.log(`${matches ? 'in-sync' : 'stale'} ${name} (${Buffer.byteLength(expected)} bytes expected)`);
  }
  if (!synchronized) process.exitCode = 1;
} else {
  for (const [name, content] of generatedOutputs) {
    fs.writeFileSync(path.join(root, name), content, 'utf8');
    console.log(`generated ${name} (${Buffer.byteLength(content)} bytes)`);
  }
}
