# Studio Config 3 테스트

## 판정

같은 구조 분석 Agent에 Config ID 3을 명시하여 NPU 골든 PDF로 테스트했다. 새 작업 한 번과 동일 설정의 제한적 재시도 한 번 모두 마지막 `paper_evidence_review`에서 실패했다. 따라서 전체 워크플로우는 통과하지 못했고, 이전 Config 2의 최종 JSON 문법 오류가 해결됐는지도 확인할 수 없다.

## 실행 결과

| 단계 | 첫 실행 | 재시도 |
|---|---|---|
| Parse | 완료 | 완료 |
| paper_structure_profile | 완료 | 완료 |
| paper_style_checklist | 완료 | 완료 |
| paper_evidence_review | 실패 | 실패 |

기존 작업 결과를 다시 조회한 것이 아니라 서로 다른 Job ID로 두 번 실행했다. 원본 PDF와 평가 기준표의 해시는 동일하다. 환경 파일이나 Studio 모델·지침은 수정하지 않았다.

두 실행 모두 Upstage가 반환한 오류는 다음과 같다.

```json
{
  "code": "model_request_error",
  "step": "instruct",
  "message": "The selected model could not process this request. Check the model and workflow settings, or contact support."
}
```

실패한 마지막 단계는 빈 `{}`를 반환했다. 이를 문법이 올바른 정상 검토 결과로 처리하지 않았으며 최종 검토 점수는 N/A로 기록했다.

## 앞 단계의 부분 평가

완료된 구조 분석 단계의 JSON 본문은 두 번 모두 정상적으로 읽혔다. 같은 원문 목차 14개로 평가했다.

| 항목 | 결과 |
|---|---:|
| 제목·번호 정밀도 | 100.0% |
| 제목·번호 재현율 | 100.0% (14/14) |
| 제목·번호 F1 | 100.0% |
| 부모 관계 | 14/14 일치 |
| 시작 페이지 | 14/14 일치 |
| 최종 검토 JSON·근거 평가 | N/A: API 단계 실패로 결과 없음 |

이 점수는 완료된 중간 구조 분석에 한정된다. 전체 워크플로우나 마지막 검토 기능의 정확도가 100%라는 뜻이 아니다. 역할 라벨은 제공되지 않아 평가하지 않았다.

## Config 2와 차이

- Config 2: 마지막 검토 응답까지 생성됐지만 그 응답의 JSON 문자열에 문법 오류가 있었다.
- Config 3: 마지막 검토 요청 자체가 `model_request_error`로 종료되어 유효한 최종 응답을 얻지 못했다.

API 응답에는 선택된 실제 모델명이나 어떤 설정이 원인인지에 대한 구체적인 설명이 없어 원인을 확정할 수 없다. Studio의 마지막 Instruct 노드에서 선택 모델과 워크플로우 설정을 확인할 필요가 있다.

## 자료

- 두 실행의 상태·오류·중간 목차 점수: `npu-studio-config3.json`
- 완료된 구조 분석의 목차 필드 투영본: `../predictions/npu-studio-config3-structure-projection.json`
- 원본 API 응답은 로컬 ignored `draft_history/20261030-studio-npu-validation-04-config3/`와 `draft_history/20261030-studio-npu-validation-04-config3-retry1/`에 보존했다.

한 문서와 동일 설정의 두 실행 결과다. 기준표는 Codex가 원문을 대조해 작성한 초기 자료로 독립 검수 전이며, 서비스 입력 파일은 교체하지 않았다.
