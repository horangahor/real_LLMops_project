# Studio Config 2 재평가

## 판정

이번 NPU 파일에서는 목차 추출이 개선되었다. 본문 장·절 14개 모두 실제 제목, 번호, 부모 관계, 계층 수준, 시작 페이지가 원문 기준과 일치했다. 그러나 마지막 `paper_evidence_review` 응답에 JSON 문법 오류가 있어, 전체 파이프라인의 최종 응답을 자동으로 읽는 기준은 통과하지 못했다.

## 실행 확인

- 사용자가 제공한 Agent에 `config_id: "2"`를 명시하여 새 작업을 생성했다. 환경 파일은 변경하지 않았다.
- 앞서 config_id를 생략한 새 작업은 세 단계 텍스트가 이전과 동일하여 수정본 반영을 확인할 수 없었다. 그 결과를 수정 효과로 채택하지 않고 사용자에게 정확한 버전을 확인했다.
- Config 2에서는 Parse → 구조 분석 → 작성 체크리스트 → `paper_evidence_review`의 네 단계가 모두 완료됐다.
- 구조·스타일 단계의 내용도 이전 실행과 달라졌다. 이 결과는 이전 작업의 텍스트를 다시 채점한 것이 아니다.
- NPU 원본 PDF의 SHA-256과 본문 목차 14개를 이전 평가와 동일하게 유지했다. API에 이미 업로드한 동일 파일 ID를 사용했다.
- 마지막 작업의 처리 완료까지 폴링 약 120초가 걸렸다. 실행·응답 상태는 `npu-studio-config2-run-metadata.json`에 기록했다.

## 목차 평가

처음부터 범위 밖인 초록·키워드·참고문헌·관련연구의 굵은 문단 소제목 3개를 제외했다. 출력 20개 중 이 6개를 별도 기록하고 본문 번호 목차 14개를 채점했다. 임의로 누락을 채우거나 원문에 없는 항목을 지운 것은 아니다.

| 항목 | 이전 Studio 서술형 응답 | Config 2 구조 분석 |
|---|---:|---:|
| 원문 본문 장·절 | 14 | 14 |
| 실제 제목·번호 대응 | 10/14 | 14/14 |
| 목차 정밀도 | 100.0% | 100.0% |
| 목차 재현율 | 71.4% | 100.0% |
| 목차 F1 | 83.3% | 100.0% |
| 상위 장 반영 | 5/5 | 5/5 |
| 하위 절 반영 | 5/9 | 9/9 |
| 부모 관계 | 번호로 복원한 10개 일치 | 원본 parent ID로 14/14 일치 |
| 원본 level 값 | 필드 없음 | 14/14 일치 |
| 원본 번호 필드 | 서술형 번호에서 읽음 | 14/14 일치 |
| 원문 시작 페이지 | 필드 없음 | 14/14 일치 |
| 역할 라벨 정확도 | N/A | N/A: 별도의 역할 라벨 미제공 |

이전에는 누락됐던 4.1~4.4의 실제 제목과 번호가 모두 포함됐다. 최종 검토 내용도 진단 파싱으로 읽어 같은 본문 목차 14개가 유지됨을 확인했다. 다만 이 점수는 목차 내용에 대한 점수이며 최종 JSON 문법 통과를 뜻하지 않는다.

## JSON 형식 검사

| 단계 | JSON 본문 문법 | 구조 |
|---|---|---|
| paper_structure_profile | 통과 | document_title, headings, style_evidence, uncertainties |
| paper_style_checklist | 통과 | document_title, sections, writing_style, reference_checklist, uncertainties |
| paper_evidence_review | 실패 | sections, writing_style, reference_checklist, evidence, review, uncertainties, structure_coverage 등의 내용을 담지만 문법 오류 존재 |

최종 검토 본문을 `json.loads()`로 읽으면 `Invalid control character`가 발생한다. 로컬에 보존한 원본 본문 기준 504행 163열이며, `evidence.s23.quote` 문자열 안에 이스케이프되지 않은 실제 줄바꿈이 들어 있다. 문자열 내부 줄바꿈은 JSON에서 `\n`으로 표현되어야 한다.

내용 진단에는 `json.loads(..., strict=False)`를 사용했지만 원본 응답은 수정하지 않았고 문법 실패를 유지했다. Git에 저장한 review projection은 목차 관련 필드만 로컬에서 다시 직렬화한 평가 자료이며 원본 응답이 아니다.

## 근거 연결 확인

- 최종 목차 20개가 참조한 근거 ID는 모두 evidence 배열에 존재한다: 20/20.
- evidence 35개의 인용문은 지정된 원문 페이지 텍스트와 정규화 대조했다. 생략부호로 나뉜 조각을 각각 확인하여 35/35에서 해당 페이지에 존재했다.
- 이 검사는 문자·출처 위치의 대조다. 인용에서 도출한 모든 문체 해석이나 과학적 판단이 정확하다는 평가가 아니다.
- 모델이 자체 출력한 `structure_coverage.status`나 `source_heading_count`를 정답 또는 점수로 사용하지 않았다.

## 평가기와 자료

줄바꿈된 실제 절 제목을 처리하기 전에 번호를 분리하던 평가기의 공백 정규화 순서를 수정했다. 기존의 ‘공백 차이는 허용’ 기준을 적용한 것이며, 기존 세 결과도 평가기 v3·동일 기준표로 재채점했다. 기존 점수 40%, 87.5%, 83.3%는 변하지 않았다.

원본의 큰 텍스트 인용과 API 응답 전체는 로컬 `draft_history/20261030-studio-npu-validation-03-config2/`에만 보관했다. Git에는 재평가에 필요한 목차 관련 필드의 투영본과 점수·진단 상태만 저장했다.

- 구조 분석 목차 투영: `../predictions/npu-studio-config2-structure-projection.json`
- 최종 검토 목차 투영: `../predictions/npu-studio-config2-review-projection.json`
- 구조 점수: `npu-studio-config2-structure.json`
- 최종 검토의 진단 점수: `npu-studio-config2-review.json`

한 문서·한 번의 Config 2 실행 결과이며, 기준표는 Codex가 원문 대조로 작성한 초기 자료로 독립 검수 전이다. 서비스가 요구하는 기존 schema_version 2 작성 가이드와는 스키마가 다르므로 이번 결과로 서비스 입력을 교체하지 않았다.

## 남은 문제

가장 먼저 최종 paper_evidence_review 단계가 항상 유효한 JSON을 내보내도록 수정하고 재검사할 필요가 있다. 그다음 이 구조·작성 가이드를 초안에 반영하는 연결과 반영률을 평가할 수 있다. 이번 검증에서는 Studio 지침이나 서비스 입력을 수정하지 않았다.
