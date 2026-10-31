# 현재 v3 결과의 이식용 스냅샷

`evidence.json`은 2026-10-31 기존 로컬 캐시를 네트워크 없이 재생해 저장한 결과다. 원본과 내용이 동일한 복사본이며 코드가 사용하는 수작업 정답이 아니다.

- 예측 SHA256: `fe37748bd7639f298a1af5cb3aa291b64df578d0ac87b3868bca00524227ce3b`
- 연구 원본 SHA256: `22e2a29d284f0eacec8c935cb0319cedc00724a95bc053a4f3459d51bb0e594a`
- 84쪽, 후보 1,990개, 작성 입력 선택 1,619개, 미해결 원문 항목 40개.
- `ready_for_drafting=false`이며 작성용 선택 후보에도 수치 오류가 확인되었다. 작성 가능 여부와 과학적 정확성을 보증하는 데이터가 아니다.
- 기존 42개 참조에 대한 전수 판정·정식 v3 성능 점수는 아직 없다. 기존 `evaluation/extraction/v3/evaluate.py`가 요구하는 protocol/annotations 세트와 혼동하지 않는다.

검토한 사례는 [검토 메모](../review-20261031.md), 다른 PC에서 앱에 불러오는 방법과 다음 작업은 [HANDOFF](../../../../HANDOFF.md)를 참고한다.

스냅샷 내부의 절대 경로는 원래 PC의 출처 기록이다. PDF 본문은 저장소에 있지만 source-archive 및 원본 API 응답 전체는 Git에 없다. 결과 보기에는 이 JSON이면 충분하고, 완전한 API 캐시 재생에는 `draft_history/`를 별도로 복사해야 한다.
