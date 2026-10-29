# Studio Config 4 테스트

## 판정

같은 Agent의 Config 4를 명시해 NPU 골든 PDF로 새 작업을 실행했다. Parse, 구조 분석, 체크리스트, 근거 검토 네 단계 모두 정상 완료되었다. Config 3의 model_request_error는 이번 실행에서 발생하지 않았다.

구조 분석과 최종 검토의 JSON 객체는 본문 목차 14개를 모두 정확하게 담았다. 단, 최종 응답은 JSON 객체 뒤에 인용 표시가 붙어 있어 응답 전체를 JSON으로 읽으려면 출처 표시와 객체를 분리하는 처리가 필요하다.

## 같은 기준으로 측정한 목차 결과

| 항목 | Config 4 |
|---|---:|
| 실제 본문 장·절 제목·번호 | 14/14 일치 |
| 목차 정밀도 | 100.0% |
| 목차 재현율 | 100.0% |
| 목차 F1 | 100.0% |
| 원본 parent ID의 부모 관계 | 14/14 일치 |
| 원본 level 값 | 14/14 일치 |
| 원본 번호 필드 | 14/14 일치 |
| 원문 시작 페이지 | 14/14 일치 |
| 목차의 근거 ID 연결 | 20/20 유효 |
| 인용문 조각의 지정 페이지 존재 | 37/37 확인 |

처음부터 범위 밖인 초록·키워드·참고문헌·관련연구의 굵은 문단 소제목 3개는 별도 집계했다. 역할 라벨은 제공되지 않아 추론하지 않고 평가에서 제외했다. 인용문 확인은 정규화한 문자열 조각의 페이지 존재 검사이며 모든 해석·문체 판단의 타당성 점수가 아니다.

## JSON 문법과 출력 형식

| 단계 | JSON 객체 자체 | 응답 전체의 순수 JSON 여부 |
|---|---|---|
| paper_structure_profile | 정상 | 정상 |
| paper_style_checklist | 정상 | 정상 |
| paper_evidence_review | 정상 | 인용 표시 접미부 때문에 실패 |

최종 검토 응답은 유효한 JSON 객체가 끝난 직후 `【†1】【†2】…【†37】`이 붙는다. 원문 응답 전체의 `json.loads()`는 `Extra data`를 반환한다. 로컬 본문 기준 위치는 652행 2열이다.

엄격한 JSONDecoder로 첫 객체를 읽는 것은 성공했고, 그 객체의 내용은 수정하지 않았다. 남은 176글자는 인용 표시 37개뿐임을 정규식으로 확인했다. 객체 부분만 분리하면 일반 `json.loads()`로 읽을 수 있다. Config 2처럼 객체 내부의 실제 줄바꿈을 허용하는 느슨한 파싱은 이번 결과에 필요하지 않았다.

평가 도구에는 명시적 진단 옵션만 추가했다. 원본의 strict_valid=false, json_object_strict_valid=true, trailing_citation_count=37을 각각 기록한다. 객체 내부 문자열의 인용 표시는 그대로 보존하고, 인용 표시 외의 임의 접미부나 추가 JSON 객체는 받아들이지 않는다. 서비스 입력·일반 분석 함수는 변경하지 않았다.

## 이전 설정과 관찰 차이

- Config 2: 모든 단계는 완료됐으나 최종 JSON 객체 내부의 줄바꿈이 문법에 맞지 않았다.
- Config 3: 마지막 검토가 model_request_error로 종료됐다.
- Config 4: 네 단계 모두 완료됐고 JSON 객체 자체도 정상이다. 다만 응답 마지막의 출처 표시를 객체와 분리해야 한다.

한 문서에 대한 각 실행의 관찰 결과이며 모델 설정 변경의 일반적 효과를 통계적으로 검증한 것은 아니다. 기준표는 Codex가 원문을 대조해 작성한 초기 자료로 독립 검수 전이다.

## 실행과 보관

Config 4의 새 작업은 약 73초의 폴링 후 완료됐다. 이전에 업로드한 동일 PDF의 파일 ID를 사용했고, 원본·평가 기준표의 해시도 확인했다. 실제 전체 응답은 로컬 ignored `draft_history/20261030-studio-npu-validation-06-config4/`에 보존했다.

- 구조 분석 목차 투영: `../predictions/npu-studio-config4-structure-projection.json`
- 최종 검토 목차 투영: `../predictions/npu-studio-config4-review-projection.json`
- 구조 점수: `npu-studio-config4-structure.json`
- 최종 검토 진단 점수: `npu-studio-config4-review.json`
- 실행·근거 대조 기록: `npu-studio-config4-run-metadata.json`

Git의 투영본은 목차 관련 필드만 로컬에서 직렬화한 평가 자료이며 원본 응답이 아니다. 원문의 큰 인용은 로컬 원본에만 남겼다. 서비스의 기존 입력 프로파일은 교체하지 않았다.
