# 합성 시연 operator preflight

이 경로는 배포 도구가 아니라, 사람이 별도로 보관한 시연 입력의 파일 구조와 hash 연결을
한 번에 확인하는 읽기 전용 보조 도구다. AWS, Docker, Terraform, Git, 네트워크, clipboard를
호출하지 않는다.

1. `demo_readiness_observation.example.json`을 저장소 밖의 operator-private 절대경로로 복사한다.
2. 빈 값에 네 앱 image digest, query·fragment가 없는 HTTPS preview URL과 그 SHA-256,
   Windows image/build/endpoint/session record 절대경로와 SHA-256, 로컬 도구 절대경로를 넣는다.
3. 물리 Mac, MDM 배포, operator identity/remote-access가 실제로 준비됐다고 사람이 확인한
   경우에만 세 macOS 선언을 `true`로 둔다.
4. 다음 명령은 파일을 읽기만 한다.

```powershell
python scripts/check_demo_readiness.py --root . `
  --observation C:\operator-private\jcareer-demo-readiness.json
```

기본 예시나 입력 누락은 `NOT_READY`다. 모든 구조 입력이 연결돼도 결과는 최대
`READY_FOR_HUMAN_RUN`이며, 이는 승인, AWS 배포, endpoint/macOS 관찰, 도구 실행,
서비스 정상성, 보안·적합성 또는 위험 수용 판정이 아니다. URL 원문과 record 내용은 출력하지
않지만 입력 파일에는 자격증명, token, 계정 ID, 실제 개인정보를 넣지 않는다.
