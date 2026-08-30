# J-Career AI 매칭·점수 설명 흐름

이 문서는 합성 AS-IS 런타임의 구현 계약과 시연 가능한 관찰 항목을 정리한다. 실제 J사
운영 상태, 법적 판단, ISMS 또는 ISO/IEC 42001 판정 결과가 아니다.

## 2026-08-28 조직 관찰값과 흐름 책임

신규 화이트보드에는 명칭 미해결 80명 부서 아래 **AI서비스 20명**과 정보보안팀 30명이
나란히 있고, AI서비스가 개발·서비스운영·DevOps 기능을 자체 보유하는 것으로 판독됐다.
기존 `context/raw/SCENARIO_FACTS-가상고객사J사.md#3`의 AI개발 7~8명·CEO 직속 IS팀 5명·
경영지원 보안 4명 구조를 대체할지는 사람 결정 대기다.

이 관찰값은 매칭 흐름의 **운영 책임과 검토 독립성**에는 영향을 주지만 데이터 흐름 자체에
새 서비스나 호출을 추가하지 않는다. `api`·`agent`·`llm-gateway`는 조직 상자가 아니라 기술
배포 단위다. 조직 기준선이 승인되기 전에는 각 단계의 승인자·검토자·접근자 수를 20명 또는
30명으로 치환하지 않는다. 80명 노드명과 정보보안팀 첫 기능 명칭도 미해결로 둔다.

영향 범위는
[`WHITEBOARD_IMPACT_ASSESSMENT_2026-08-28.md`](../../context/findings/WHITEBOARD_IMPACT_ASSESSMENT_2026-08-28.md),
필드 경계는 [`DB_FIELD_CATALOG.md`](DB_FIELD_CATALOG.md)에 기록한다.

같은 날 Notion의 [`8/28 멘토 회의`](https://app.notion.com/p/3ca0be5710e8805badf9c7fa7c8f762b?pvs=204)
`0828 회의록 정리본`에는 **DevOps를 별도 팀으로 두지 않고 AI서비스의 DevOps 업무를 인프라팀
책임으로 옮긴 뒤 그 아래 SI팀·데이터팀을 두는 안**, 정보보안팀을
**Blue·Red·Compliance**로 구분하는 안이 추가됐다.
이 값은 `MENTOR_PROPOSED_HUMAN_DECISION_PENDING`이며 앞 절의 화이트보드 관찰값을 지우거나 승인된
조직 기준선으로 승격하지 않는다. 인원·보고선·RACI도 임의로 채우지 않는다.

이번 구현의 중심은 조직도가 아니라 **AI 서비스 사실 경계**다. 조직안은 바뀔 수 있는 참고
컨텍스트로만 두며, 아래 점수·설명·DB 전송·학습 경계는 조직 이름과 보고선이 바뀌어도 유지한다.

또한 AI서비스가 `agent`를 학습시키는 흐름은 현재 구현에 없다. `agent`는 아래의
`deterministic-70-20-10-v1`을 계산하고, `src/mlops/**`의 학습 코드는 실제 회원·기업 데이터를
읽지 않는 별도 합성 생명주기 시연이다. 이용자 데이터 학습은 현재 기본 비활성이고 전용 동의
유형도 없으며, 향후 시나리오 채택 여부와 안내·동의·철회·lineage는 사람 결정이 필요하다.
통합 경계는 [`mentor_feedback_2026_08_28.json`](contracts/mentor_feedback_2026_08_28.json)에 둔다.

사용자 제공 참고 화면은 저장소 근거로 승격하지 않는다. 아래 흐름과 필드는
`src/runtime/ASIS_RUNTIME_SPEC.md#2. 서비스 책임`과
`src/runtime/DB_FIELD_CATALOG.md#4. 현재 matcher와 LLM 설명 payload`의 source 관찰값으로 구분한다.

## 8단계 흐름과 현재 구현

| 순서 | 참고 화면의 단계 | 현재 합성 런타임 | 관찰 지점 |
|---:|---|---|---|
| 1 | 이력서 및 채용정보 입력 | 이력서·공고 API와 웹 폼 | 구조화 필드와 자유서술 필드 구분 |
| 2 | 개인정보 수집·이용 동의 | 핵심 동의 이벤트 기록·철회 | 동의 전 추천 경로 차단 여부 |
| 3 | AI 입력 데이터 삽입 | API가 matcher 입력과 설명 입력을 별도 구성 | 점수 미사용 필드가 설명 입력에 포함되는지 |
| 4 | 설명 요청 구성 및 gateway 호출 | API가 `llm-gateway`용 입력을 준비해 호출 | 준비 필드·prompt hash·provider 구성. 외부 provider 수신 확인은 아님 |
| 5 | 회사 DB 연동 | 회원 DB의 이력서와 기업 DB의 기업·공고를 API가 조합하고 Redis에 추천 캐시 | 논리 참조·교차 DB 비원자성·캐시와 raw prompt 저장면 |
| 6 | AI 분석·매칭 | `agent`가 결정론적 산식으로 계산 | 산식 버전·요인별 원시 기여도 |
| 7 | AI 매칭 결과 생성 | 점수·정렬·선정 근거와 별도 설명 코멘트 | 설명 과장·점수 불변성 |
| 8 | 사용자에게 결과 제공 | 후보자·채용담당자 추천 화면 | 역할별 표시 내용과 데이터 경계 |

## 현재 점수 계약

`deterministic-70-20-10-v1`은 플랫폼 공통 기본값이다. 기업이 공고별로 승인한 가중치가
아니므로 화면에서도 기업 선호라고 표현하지 않는다.

```text
총점 = 요구 기술 일치 최대 70 + 경력 조건 최대 20 + 희망 직무 연관 최대 10
```

- 기술: 정규화한 고유 요구 기술 수 대비 일치 수의 비율
- 경력: `min(후보 경력 / 최소 경력, 1)`; 최소 경력이 0이면 최대 20점
- 직무: 공고 제목 토큰과 희망 직무의 정규화 부분 일치
- 총점: 반올림 전 기여도를 합산한 뒤 소수 첫째 자리로 표시
- 항목 표시값: 각 기여도를 별도로 소수 첫째 자리로 표시하므로 표시값 합과 총점이 0.1
  다를 수 있다.

이름·전화번호·이메일·생년월일·거주지역·학교/학력·자격증·프로젝트·자기소개는 이 점수 계산에
사용하지 않는다. 다만 현재 AS-IS API는 cache miss의 설명 요청에 이 9개 필드를 준비하고,
현재 field-name counter는 그중 6개만 표시한다. `subject_ref`, score breakdown, matched label에도
지원자 파생 정보가 포함될 수 있으므로 9/6은 전체 provider payload나 승인된 LLM02 모수가 아니다.
빈 추천 집합에는 준비하지 않으며, cache hit에서는 원본 요청의 필드 집합을 현재 cache 응답만으로
검증하지 못하므로 필드명을 재진술하지 않는다. 응답의 `explanation_attempt`는 이 상태와 gateway
확인 상태를 분리하며, 외부 공급자의 실제 수신을 단정하지 않는다.

신규 화이트보드의 회원DB 논리 목록에는 병역·학점·프로젝트와 화이트보드상 민감정보인
장애·신체·보훈이 포함된다. 프로젝트는 현재 이력서와 정성 근거·설명 문맥에만 구현됐고
점수에는 사용되지 않는다. 나머지 필드는 현재 데이터 모델과 점수 산식에 구현되어 있지 않다.
판독 목록에 있다는 사실은 수집·점수 사용·LLM 전송 승인이 아니다. 논리 필드 14개와 현재
물리·전송 필드의 대응은 [`DB_FIELD_CATALOG.md`](DB_FIELD_CATALOG.md)를 따른다.

## 회원·기업 데이터 경계

추가 참고 화면 `기업db_회원db.jpg`를 기준으로 현재 런타임은 다음처럼 소유권을 나눈다.

- 회원 DB: 모든 플랫폼 identity, 동의, 이력서·자소서, 지원관계, 감사 이벤트
- 기업 DB: 기업, 회사 방향·선언 가치, 채용공고
- `User.company_id`와 `Application.job_id`: DB foreign key가 아닌 opaque 논리 참조
- 조합 주체: API만 회원·기업·합성결과 DB를 읽고 DTO를 만든다. matcher와 LLM gateway는 DB DSN을 받지 않는다.

로컬에서는 두 database와 서로 다른 role의 반대편 `CONNECT`를 차단한다. Terraform AS-IS는
기존 RDS Primary/Standby와 read replica를 유지한 채 두 논리 DB 이름과 API DSN 계약만
표현한다. 기업 DB·role bootstrap은 Terraform이 실행하지 않으며, 같은 RDS를 쓰므로 장애·
백업·보안그룹은 분리되지 않는다.

기업도 플랫폼 고객이다. `/api/v1/recruiter/overview`는 로그인한 기업의 공고 ID만 대상으로
회원 DB의 지원관계를 집계하고, 기업 DB의 회사 프로필·최근 공고와 함께 반환한다. 이 화면은
운영 건수와 데이터 소유 경계를 보여 줄 뿐 추천 적합성, 선발 우선순위, 통제 충족 여부를
판정하지 않는다. 기업 담당자 identity는 현재 회원 DB에 있고 기업 조직은 기업 DB에 있어,
이 연결을 별도 기업 membership 모델로 옮길지는 사람의 제품·보안 결정으로 남긴다.

신규 화이트보드 기업DB의 사업자번호·담당자 이메일/전화번호·우대사항·자격요건은 논리 필드로
관찰됐지만 현재 물리 스키마와 일치하지 않는다. 특히 `Company.opendart_corp_code`는 OpenDART
고유번호이지 사업자번호가 아니며, 담당자 이메일은 회원 DB의 `User.email`에 있다. 데이터 사전,
수집 목적과 저장 위치를 승인하기 전에는 스키마를 자동 확장하지 않는다. 장애·신체·보훈·병역도
별도 동의·접근·사용 기준 없이 수집하거나 추천 입력으로 보내지 않는다.

## 설명 생성기의 권한 경계

1. `agent`가 점수·정렬·요인별 기여도를 확정한다.
2. `llm-gateway`는 해당 결과를 문장으로 바꾸며 점수나 순위를 반환하지 않는다.
3. API→gateway 연결·HTTP·JSON·응답 계약 또는 gateway/외부 공급자 경로가 unavailable/invalid이면
   점수·정렬·breakdown은 유지되지만 설명과 `company_alignment`는 함께 비고 legacy 상태
   `UNAVAILABLE_PROVIDER`로 축약된다. 이 상태는 외부 공급자 장애 발생 증거가 아니다.
4. AS-IS에는 생성 문장의 의미 검증이 없으며 응답에
   `output_validation_state=NOT_IMPLEMENTED_ASIS`를 남긴다.
5. Bedrock adapter는 최상위 `items`와 항목별 `subject_ref`·`text`만 허용하고, 요청한
   subject 집합의 누락·추가·중복, 자료형 오류, 빈 문장과 길이 상한 초과를 거부한다. 이는
   응답 형식 경계일 뿐 생성 문장의 사실성이나 의미를 검증하지 않는다.
6. cache hit는 원본 요청의 설명을 반환하지만 item 내부 계약을 다시 검증하지 않으므로
   `CACHE_ENTRY_ACCEPTED_ORIGIN_NOT_VERIFIED`로 표시한다. 이는 과거 gateway 수신·검증 증거가
   아니다.

## 자소서와 기업 방향 비교

- 기업 담당자는 회사 단위 `direction_statement`와 `declared_values`를 직접 입력한다.
- 저장할 때 `company-profile-*` 버전을 새로 발급하고 감사 이벤트에는 버전과 가치 개수만
  기록한다.
- Gateway는 자소서의 직접 일치 표현과 기업 선언 가치를 비교해
  `company_alignment`를 반환한다.
- 이 결과의 `score_effect`는 현재 `NONE`이다. 기존 100점 점수나 정렬을 바꾸지 않는다.
- 기업 추천 API는 Gateway 문장과 별도로 자기소개·프로젝트와 공고 요구 기술·기업 선언의
  직접 문구 위치만 `recruiter_review_support`로 만든다. `score_effect=NONE`,
  `ranking_effect=NONE`, 자동선발·합격확률·기업 적합 판정 `false`와 사람 검토가 고정된다.
  이 경계가 다르면 기업 UI는 해당 근거를 표시하지 않는다.
- Bedrock 모드에서는 동일한 자소서·기업 선언문을 설명 입력으로 사용하지만 현재 AS-IS에는
  의미 검증기가 없으므로 새로운 근거를 만들거나 기업 방향을 과장할 가능성을 별도 관찰한다.

## 시연 가능한 AS-IS 관찰 시나리오

| ID | 조작 | 관찰할 값 |
|---|---|---|
| SCORE-01 | 정상 추천 조회 | 총점과 세 요인의 원시 기여도·표시값·산식 버전 |
| SCORE-02 | 빈 희망직무로 matcher 직접 호출 | 직무 점수 0; 근거 없는 10점이 생성되지 않음 |
| EXPLAIN-01 | 정상 설명 요청 | 명시 candidate context 9개/현재 field-name counter 6개를 기록. score breakdown·matched label·subject ref는 이 계수 밖이므로 전체 LLM02 모수로 판정하지 않음 |
| EXPLAIN-02 | `overclaim` 장애 주입 | “우선 채용” 문장이 차단되지 않지만 점수·정렬은 변하지 않음 |
| EXPLAIN-03 | timeout·429·503·malformed 주입 | 설명과 `company_alignment`를 사용할 수 없고 score breakdown은 기준 응답과 동일 |
| EXPLAIN-04 | prompt record 확인 | candidate context와 score breakdown이 raw prompt 기록에 함께 남음 |
| ALIGN-01 | 기업 선언 가치와 자소서 직접 표현 비교 | 일치 가치·기업 프로필 버전·`score_effect=NONE` 표시 |
| ALIGN-02 | 기업 방향 또는 자소서에 합성 지시문 삽입 | 설명 생성기가 비근거 결론을 만드는지 관찰; 자동 판정하지 않음 |
| DATA-01 | `tests/database_boundary.py` 실행 | 회원 DB 5개·기업 DB 2개·합성결과 DB 2개 테이블 분리와 세 role의 자기 DB 외 여섯 연결 조합 거부; 최신 보강본은 미실행 |
| DATA-02 | 기업회원 가입 | identity는 회원 DB, 기업 조직은 기업 DB에 생성되는 split write |
| DATA-03 | 미구현·미실행 후보: 승인된 별도 합성 환경에서 한 DB commit 실패 주입 | 현재 소스에는 주입 경로와 실행 증거가 없음. 기업회원 가입·기업 변경 감사의 부분 완료와 재시도 계약은 사람이 정한 뒤 관찰 |
| BEDROCK-01 | 기본 구성 확인 | model/profile ID는 있으나 `ALLOW_BEDROCK_LIVE=false`; 실호출 실행 증거 없음 |
| BEDROCK-02 | 순수 parser에 형식 오류 응답 주입 | 누락·추가·중복 subject와 잘못된 자료형을 거부; 순수 parser 시험이며 실호출 실행 증거 아님 |

`EXPLAIN-01`의 9개/6개 값은 현재 코드로 재현하는 관찰값이다. 개인정보의 법적 분류나
통제 판정은 이 런타임이 하지 않는다.

## Bedrock 구성 상태

기존 `llm-gateway` 안에 Bedrock Converse adapter가 포함되어 있으며 별도 AI 제품 서비스는
추가하지 않았다. 단기 lab에는 AWS 권한을 일반 gateway와 분리하기 위한 조건부 capability
broker helper container source가 있지만, 두 provider broker가 같은 EC2 role을 쓰는 process
경계일 뿐이다. Compose와 Terraform AS-IS의 기본 provider는 외부 공급자 경계를 재현하는
합성 adapter이고, live 플래그는 `false`다.

현재 Terraform AS-IS에는 Bedrock 호출 IAM 권한이 없고 `/llm` 공개 경로와 공유 task role이
남아 있다. 별도 lab source의 조건부 IAM·broker도 승인된 plan/apply와 원격 경계 관찰 전에는
실행 증거가 아니다. 따라서 변수 두 개를 바꾸는 것만으로 live 준비가 끝난 것이 아니다. 기본
잠금은 무인증 과금 호출을 만들지 않기 위한 실행 가드이며, AS-IS 관찰 요소를 해소했다는 뜻도
아니다.
응답 parser의 형식 검사는 provider payload를 내부 설명 계약으로 승격하기 전의 경계이며,
`output_validation_state=NOT_IMPLEMENTED_ASIS`로 표시되는 의미 검증 부재를 대체하지 않는다.

## 기능 커버리지와 남은 결정

현재 구현에는 구조화 이력서·공고 입력, 동의, 결정론적 순위·점수, 요인별 산식, 기업 선언
방향과 자소서 근거 비교, 기업 담당자용 직접 문구 검토, 후보자·채용담당자 표시, provider 장애 시
점수 보존이 포함된다.

다음은 아직 구현 사실로 주장하지 않는다.

- 2026-08-28 조직도를 기존 시나리오 기준선으로 교체하고 AI서비스·정보보안팀 사이의
  개발·운영·검토 책임을 확정하는 일
- 회원DB 14개·기업DB 9개 화이트보드 논리 필드의 canonical mapping과 LLM02 계수 단위 승인
- PDF/DOCX 이력서 업로드와 OCR·구조화 추출
- 기업별·공고별 가중치 승인·이력·롤백과 이를 점수에 반영하는 기능
- 자소서 의미 유사도의 평가 데이터 기반 검증과 점수 반영 승인
- 웹 런타임의 실제 Bedrock 활성화, 전용 IAM 역할, 내부 호출 인증, 호출량 제한
- 생성 문장 근거 검증기와 금칙 결론 차단
- 추천 실행 단위 감사 이벤트와 장기 보존 저장 모델
- 장애·신체·보훈·병역·학점·프로젝트 등 화이트보드 논리 항목의 수집·사용 결정
- 컨설팅 대시보드의 승인된 비식별 snapshot ingestion

이 목록은 구현 누락 여부를 숨기지 않기 위한 범위 표시이며, 채택 우선순위와 적정성은
사람이 정한다.

## 재현

```powershell
python tests/score_contract.py
python tests/smoke.py
python tests/database_boundary.py
python tests/security_smoke.py
python tests/resilience_smoke.py
```

각 스크립트의 `PASS`는 코드에 작성된 assertion이 통과했다는 뜻이다. 관리체계나 법적
요구사항에 대한 판정은 사람이 수행한다.
