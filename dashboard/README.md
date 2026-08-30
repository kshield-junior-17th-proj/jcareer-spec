# J-Career Evidence Desk

컨설턴트가 사람 승인 메타를 포함한 비식별 snapshot을 읽는 정적 화면 scaffold다. 클라이언트 AWS,
J-Career 런타임 API, 저장소 파일을 직접 조회하지 않는다. JSON 파일은 브라우저 메모리에서만
검사·표시하며 업로드하거나 `localStorage`에 보관하지 않는다.

현재 승인된 assessment JSON과 `measurement/out`이 없으므로 기본 화면은 의도적으로
`snapshot 없음` 상태다. 합성 숫자나 예시 판정을 실제 결과처럼 미리 채우지 않는다.

## 실행 경계

- 입력: `jcareer-consulting-snapshot/v1` JSON 한 개
- 허용 audience: `INTERNAL_REVIEW`만. 외부용 최소 필드 계약은 아직 승인되지 않아 fail-closed
- 필수: 단일 가명 tenant, `REDACTED`, 직접 식별자 없음 표시, 내부 검토 승인 메타. 각 source
  artifact와 observation의 비표시 `tenant_ref`가 snapshot tenant와 정확히 같아야 함
- 추적성: 모든 source/evidence/판단 ref가 URL·절대경로·상위경로가 아닌 상대 논리 경로이며,
  source artifact 또는 그 `#fragment`로 연결되어야 함
- 시점: artifact 수집과 사람 판단 ≤ snapshot 생성 ≤ 승인 순서를 구조적으로 검사
- 범위: 지원자·기업 관찰은 `scope.customer_sides`의 부분집합이어야 함. 양측에 걸친 관찰은
  객체와 `observation_id`를 복제하지 않고 선택적 `customer_sides`에 두 측을 선언한다. 기존
  `customer_side`는 하위호환용 주 투영이며 배열에 포함되어야 한다. `platform`은 고객 측 배열과
  섞지 않고 운영 관찰 lane으로 별도 허용한다.
- 집계: 상단은 `observations.length`를 고유 관찰 건수로 표시한다. 공동 관찰은 두 lane에 같은
  객체를 표시할 수 있으므로 lane별 수는 `표시` 수이며 합계를 전체 관찰 건수로 사용하지 않는다.
- 표시: 수집 상태, 측정 사실, source/evidence ref, 사람이 입력한 판단문
- 미실행: 통제 충족 여부 계산, 적합성 판단, 잔여위험 산정, AS-IS/TO-BE 자동 비교
- 네트워크: CSP `connect-src 'none'`; JavaScript에 fetch/XHR/WebSocket/EventSource 없음
- 데이터 지속성: 없음. 새 snapshot을 읽으면 이전 객체와 DOM을 폐기한다.
- 로컬 경로 최소화: 선택한 파일명은 화면에 다시 표시하지 않는다.
- 비식별 방어: 금지 필드명과 계정 모양, 자격증명, 연락처, IP, UUID, ARN, 서비스 endpoint,
  DB/cache URL, 절대 로컬 경로 모양, 보이지 않는 문자와 양방향 표시 제어문자를 추가 거부한다.
  패턴 검사는 사람의 비식별 검토를 대체하지 않는다.

`customer_sides`는 현재 reader가 선택적으로 받는 additive v1 필드다. 이 필드를 모르는 strict 구
reader는 `additionalProperties=false` 때문에 새 snapshot을 거부한다. 조직 간 교환 전에 v1 additive
변경을 허용할지, v1.1/v2로 올리고 다중 버전 reader를 둘지는 사람이 정한다.

`approval`은 snapshot의 배포 audience를 사람이 승인했다는 메타데이터다. 평가 대상 통제가
충족됐다는 뜻이 아니다. `human_decision`이 있으면 `owner=HUMAN`, 판정 출처와 결정자 가명
참조가 모두 있는 경우에만 중립적인 문구로 그대로 표시한다. 이 필드들은 입력 파일의
자기진술이며, 신뢰된 발급자의 서명이나 승인자 identity 검증은 아직 없다.

## 로컬 확인

별도 패키지 설치 없이 Node.js 정적 검사를 실행할 수 있다.

```powershell
cd dashboard
npm test
npm run verify
```

## 승인 snapshot 패키징

`tools/package-snapshot.mjs`는 사람이 이미 작성·비식별 검토·승인한 snapshot과 그 snapshot이
선언한 source artifact 파일을 함께 받아 모든 SHA-256 결속을 확인한 뒤, Evidence Desk가 읽을
동일 JSON을 새 파일로 만든다. 기존 파일은 덮어쓰지 않으며 snapshot 내용이나 사람 판단문을
생성·수정하지 않는다.

```powershell
node tools/package-snapshot.mjs --snapshot approved-snapshot.json --artifacts-dir reviewed-artifacts --output packaged-snapshot.json
```

source artifact 누락·digest 불일치·경로 이탈·snapshot 계약 오류가 하나라도 있으면 출력 파일을
만들지 않는다. 이는 파일 결속 검사이며 승인자 신원, 서명 신뢰성, 원자료 전체의 비식별 상태를
증명하지 않는다. 실제 승인 입력이 없으므로 저장소에는 packaged snapshot을 미리 넣지 않는다.

브라우저 확인이 필요할 때만 사용자가 명시적으로 정적 서버를 실행한다.

```powershell
python -m http.server 4173 --directory .
```

2026-08-30 정적 확인에서 validator·view-model·artifact 결속 test 28개와 무통신·무브라우저저장·무판정 경계 검사가
통과했고, loopback 빈 화면은 외부 요청과 console 오류 없이 렌더링됐다. 기업 수명주기·상태
게이트·교차 저장소·provider 경계를 포함한 fixture는 계약 검사용이며 관찰 결과가 아니다. 승인된 입력 파일이
없으므로 실제 snapshot loaded 상태는 관찰 결과로 주장하지 않는다.

## 외부 preview

현재 scaffold 자체에는 사용자 인증, 서버 측 tenant isolation, 영구 audit log, 승인 workflow가
없다. 따라서 인터넷 공개나 운영 사용 대상이 아니다. 현재 v1 JSON에는 reviewer·tenant 내부
참조, source/evidence 경로와 artifact 식별자·digest가 들어가므로 DOM에서 숨기는 것만으로
외부 데이터 최소화가 되지 않는다. validator는 `EXTERNAL_PREVIEW`를 거부한다. 외부 팀에는
사람이 별도로 승인한 redacted snapshot을 사용한다는 원칙을 유지하되, 내부 참조를 payload에서
제거한 별도 외부 projection/schema가 승인되기 전에는 이 scaffold로 제공하지 않는다.

artifact·observation의 `tenant_ref` equality는 한 파일 안에서 다른 tenant 자료가 섞이는 것을
거부하는 내용 결속일 뿐이다. 발급자 서명, 서버 저장소 partition, 객체 수준 인가를 검증하지 않으므로
production tenant isolation으로 해석하지 않는다.

상단의 `Direct client AWS query: none`은 현재 브라우저 코드가 클라이언트 AWS/API를 직접
조회하지 않는다는 코드 경계다. 호스팅 소유권까지 증명하는 문구가 아니다. 운영 호스팅은
consultant-owned origin과 승인된 단방향 snapshot ingestion 구조를 사람이 별도로 확정해야 한다.

운영 전에는 다음을 별도 구현·검증해야 한다.

1. per-user authentication과 권한별 audience 제한
2. 서버 측 tenant isolation 및 객체 수준 인가
3. 승인된 ingestion과 immutable audit log
4. snapshot 서명·만료·회수 및 재승인 흐름
5. 비식별 검토와 외부 공개 승인 주체

이 목록은 구현 상태를 숨기지 않기 위한 경계이며, 적합성 또는 위험 수준 판정이 아니다.
