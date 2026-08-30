# OpenDART 온디맨드 갱신 작업자

이 디렉터리는 기업 공개정보 갱신 요청을 SQS FIFO에서 받아 실행하는 Lambda 소스다.
상시 컨테이너를 추가하지 않고, 기업 담당자가 갱신을 요청했을 때만 실행하는 배포 후보다.

- 공고·추천 조회는 OpenDART를 호출하지 않고 기업 DB의 마지막 정상 저장본만 읽는다.
- API 큐 메시지에는 회사 UUID, DART 고유번호, 요청 UUID·시각만 들어간다.
- API 키는 메시지·DB·환경변수에 넣지 않고 실행 시 SSM SecureString에서 읽는다.
- 회사명 불일치, 오래된 요청, 응답 형식 오류에서는 정상 저장본을 덮어쓰지 않는다.
- `AVAILABLE_LIVE`는 내부 상태 코드일 뿐 실제 배포·운영을 뜻하지 않는다.
- 현재 AWS 배포와 실 OpenDART 호출 증거는 없다.

Lambda artifact는 이 디렉터리와 `src/runtime/api/app/opendart.py`를 함께 패키징해야 한다.
사람이 artifact·키 parameter·network egress·DB 변경 권한을 승인하기 전에는 배포하지 않는다.
