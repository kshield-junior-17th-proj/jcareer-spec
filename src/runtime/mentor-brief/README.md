# 0828 CEO mentor brief

이 정적 화면은 `../contracts/mentor_feedback_2026_08_28.json`만 읽어 2026-08-28 멘토
회의 피드백을 보여 준다. 첫 화면은 조직도가 아니라 결정론 점수·Bedrock 설명·회원DB/기업DB
전송·학습 기본 금지·합성 MLOps라는 AI 서비스 사실 경계다. 조직은 뒤쪽의 변경 가능한 참고안으로
두며, 적합성·위험 등급·보완대책 승인·잔여위험을 계산하지 않는다.

정보보호시스템의 전체 대장과 명시적 부재는
[`../INFORMATION_PROTECTION_SYSTEM_INVENTORY.md`](../INFORMATION_PROTECTION_SYSTEM_INVENTORY.md)에
분리해 두었다.

저장소 루트에서 로컬 파일 서버를 열면 된다.

```powershell
python -m http.server 4179 --directory src/runtime
```

브라우저에서 `http://127.0.0.1:4179/mentor-brief/`를 연다. 페이지는 Notion이나 외부 API를
직접 호출하지 않는다. 화면의 원문 링크만 사용자가 선택했을 때 새 탭으로 열린다.

계약과 정적 화면 회귀는 다음처럼 실행한다.

```powershell
python -m unittest src/runtime/tests/mentor_feedback_contract.py
node --check src/runtime/mentor-brief/app.js
```

회의 원문: [8/28 멘토 회의](https://app.notion.com/p/3ca0be5710e8805badf9c7fa7c8f762b?pvs=204)
