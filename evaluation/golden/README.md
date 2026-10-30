# 골든 샘플 구조 추출 평가 v3

## 현재 사용 경로: 직접 Parse API + Python

참고 논문의 구조 분석은 Studio 대신 `paper_structure.py` → `document_parse.py` → `paper_outline.py` 경로로 전환했다.
`--outline-only`는 Parse API와 Python만 사용한다. 전체 프로파일은 코드가 정한 목차에 Solar의 역할·재사용 가이드를 연결한다.
목차 숫자·제목·페이지·부모를 Solar가 다시 생성하거나 수정하지 않는다. JSON Schema·원문 ID·형식 검증을 적용한다.

기존 원문 기준표를 변경하지 않고 직접 API 원본을 평가한 결과는 NPU 14/14, RGBD 23/23으로 제목+번호 F1과 부모·시작 페이지 일치율이 100%다.
기존 RGBD Studio의 동일 Parse 원본을 새 코드로 재생해도 F1 100%다. Studio 구조 분석의 F1 86.8%와 구분해 기록했다.
NPU에서 처음 발생한 줄바꿈·paragraph 절 누락·반복 머리말 오류를 수정했으므로 두 편은 개발 샘플이며 별도 보류 평가셋이 아니다.
지원 범위는 참고문헌 이전의 아라비아 숫자 본문 목차다. 무번호·로마 숫자 절과 다른 문서의 일반화는 추가 평가가 필요하다.

```powershell
python -X utf8 -B paper_structure.py --outline-only --run-dir draft_history/parse-api-v1 --output evaluation/golden/predictions/parse-api-v1-outlines.json
python -X utf8 -B evaluation/golden/evaluate_parse_pipeline.py --profiles evaluation/golden/predictions/parse-api-v1-outlines.json
```

원본 응답·설정·캐시 해시·선택/제외 후보는 ignored `draft_history/parse-api-v1/`에 보관한다.
결과는 `results/parse-api-v1-validation.md`, `results/npu-parse-api-v1.json`, `results/rgbd-parse-api-v1.json`이다.
이하 Studio·legacy 평가는 과거 비교 기준이다. 서비스의 새 프로파일과 당시 입력을 혼동하지 않는다.

## 목적과 평가 대상

골든 PDF에서 관찰한 목차가 저장된 구조 분석에 얼마나 정확하게 반영되었는지 측정한다.
평가 대상 한 편은 `AIComps2026_NPU_Benchmarking_1.1v.pdf`로 고정했다. CUDA 초안과 마찬가지로 가속기 최적화·성능 평가를 다루어 첫 비교 대상으로 선정했다. 이것은 평가 대상 선정이며 초안 서비스가 로드하는 기존 두 프로파일을 교체하는 변경은 아니다.

기준선은 `paper_structure_analysis.json`의 해당 논문 프로파일을 복사한 `predictions/npu-legacy.json`이다. 출처가 `legacy_analysis`이므로 이전 분석을 로컬 변환한 결과다. 기준선 측정에서는 Document Parse/Solar를 새로 실행하지 않았다.

이후 사용자가 NPU PDF와 추출 본문의 Upstage 외부 전송을 명시적으로 허용하여 실제 API도 한 번 실행했다. `predictions/npu-live.json`이 변경하지 않은 `paper_structure.analyze_paper()`의 새 결과이며, `results/npu-live.json`과 `results/npu-live-validation.md`에 평가와 비교를 기록했다. 전체 파서/LLM 응답과 실행 스크립트는 로컬의 ignored `draft_history/20261029-npu-live-validation/`에 보관하고 Git에는 넣지 않았다. 기존 서비스 입력 프로파일은 교체하지 않았다.

사용자가 Studio 워크플로우를 수정한 뒤 별도의 Studio Agent 실행도 수행했다. `STRUCTURE_AGENT_ID`의 Agent를 Files/Jobs API로 직접 호출하고 `config_id`를 생략해 서버의 최신 저장 설정을 사용했다. 로컬에 고정된 설정 버전 1은 이 검증에 사용하지 않았다. 결과는 `results/npu-studio-validation.md`에 있다. 이 경로는 앞의 직접 Document Parse/Solar 호출 경로와 구분한다.

## 원문 기준표

`npu-reference.json`에 번호가 있는 본문 장·절 14개(상위 5개, 하위 9개)를 기록했다.

- 제외: 초록, 키워드, 참고문헌 목록, 표·그림 제목, 페이지 머리말, 문단 내 굵은 소제목.
- 열: 원문 절 번호, 원문 제목, 미리 선언한 번역 별칭, 상위 절, 역할, 시작 PDF 페이지.
- 페이지는 PDF의 1부터 시작하는 물리적 페이지다. 본문의 페이지 번호도 이번 문서에서는 같다.
- Codex가 로컬 PDF 전체 텍스트와 관련 11페이지의 렌더링 이미지를 대조해 작성했다. 사용자나 전문가가 독립적으로 검수한 정답은 아니며, 특히 역할 라벨은 명시한 기준에 따른 초기 판정이다.
- 원문 SHA-256을 고정한다. PDF가 바뀌면 채점을 중단하고 기준표를 재검토해야 한다.
- 이 자료는 평가에만 사용한다. 초안 생성 입력이나 `research_evidence.json`으로 연결하지 않는다.

## 지표 정의

각 예측 제목과 기준표 항목은 1:1로 대응한다. NFKC, 대소문자, 공백, 문장부호를 정규화한다. 원문 제목과 사전에 기록한 번역 별칭을 사용하며, 예측의 괄호 안 원문 제목도 인정한다. 절 번호만으로 대응하거나 실행 결과를 본 뒤 의미 유사도 기준을 변경하지 않는다. 같은 절의 중복 예측은 첫 항목만 대응시키고 나머지는 오탐으로 기록한다. 여러 제목에 동시에 대응하는 모호한 항목도 오탐이다.

v2는 v1에서 선언만 하고 실제 채점에 반영하지 않았던 제외 범위를 구현한다. 원문에서 확인된 참고문헌 제목과 관련 연구의 굵은 문단 소제목 3개는 `excluded_titles`로 기록하고, 번호 없는 해당 예측만 별도로 집계한다. 원문에 없는 가상의 요약 소제목은 오탐으로 유지한다. 원시 예측 수, 채점 대상 수, 제외 수를 모두 보고한다. 이전 기준선과 새 실행 결과 모두 같은 v2로 다시 채점한다.

v3는 제목이 줄바꿈된 경우에도 절 번호를 분리하기 전에 공백을 정규화하도록 수정했다. 제목 공백 정규화라는 기존 판정 기준을 적용하기 위한 평가기 수정이며, 원문 14개와 일치 기준은 같다. 기준표 v3에는 처음부터 제외 범위였던 초록·키워드의 실제 표기도 열거했다. 기존 비교 결과도 같은 기준표·평가기로 다시 채점했으며 수치는 변하지 않았다.

1. **제목 대응 정밀도/재현율/F1:** 절의 정체성을 찾아냈는지 본다. 번호는 별도다. 정밀도는 TP/예측 수, 재현율은 TP/기준 항목 수, F1은 2TP/(예측 수+기준 항목 수)다.
2. **제목+번호 정밀도/재현율/F1:** 대응된 제목의 절 번호까지 같아야 TP다. 번호가 틀린 항목은 이 지표에서 오탐과 누락으로 각각 집계된다.
3. **계층 정확도:** 제목이 대응된 항목 중 실제 부모 절의 정체성이 같은 비율이다. 최상위 항목은 최상위로 남아야 맞다. 루트가 많아 점수가 높아지는 현상을 드러내기 위해 대응된 하위 절만의 부모 정확도도 별도 보고한다.
4. **역할 분류 정확도:** 제목이 대응된 항목 중 역할이 같은 비율이다. 찾지 못한 항목은 분모에 없으므로 반드시 목차 재현율과 함께 읽는다.
5. **번호가 맞는 하위 절 재현율:** 원문의 하위 절 9개 중 제목과 번호를 모두 맞춘 비율이다.
6. **완전 일치 항목 재현율:** 제목 정체성·번호·부모·역할을 모두 맞춘 항목/전체 원문 항목이다. 합성 가중 점수 대신 정확한 항목 수를 보여준다.
7. **시작 페이지 일치율:** 대응된 항목 중 `source_pages`에 원문 시작 페이지가 들어 있는 비율이다. null은 미제공으로 0점이며, 틀린 페이지를 추측한 것과 구분해 해석한다.

빈 분모는 100%가 아니라 N/A(null)로 보고한다. 전체 항목 수와 분자를 함께 저장하여 조건부 고득점을 누락 없는 성능으로 오해하지 않게 한다.

## 실행

프로젝트 폴더에서 다음 명령을 실행한다. Python 표준 라이브러리만 사용한다.

```powershell
.\.venv\Scripts\python.exe -X utf8 -B golden_evaluation.py --profiles evaluation/golden/predictions/npu-legacy.json --output evaluation/golden/results/npu-legacy-baseline.json
```

현재 서비스의 저장 분석을 평가하려면 별도 출력 경로를 사용한다.

```powershell
.\.venv\Scripts\python.exe -X utf8 -B golden_evaluation.py --profiles paper_structure_analysis.json --output evaluation/golden/results/npu-current.json
```

새 분석을 비교할 때도 `--profiles`와 `--output`만 바꾸고 같은 기준표를 사용한다. 기준표를 바꾸면 SHA-256이 달라지므로 평가 버전 차이를 기록해야 한다. 출력 JSON에는 원본 PDF, 기준표, 예측 파일의 해시와 항목별 판정을 저장한다. 같은 이름의 Markdown 보고서도 생성한다.

## 실제 API 검증과 남은 평가

- 실제 검증에서는 원본 파서 응답을 로컬에 보존하여 목차 제목 14개의 본문 텍스트·페이지 존재와 heading 분류 여부를 확인했다. 이는 전체 글자의 OCR·읽기 순서·표 인식 정확도 평가가 아니다. 일반 서비스의 분석 함수 자체는 여전히 원본 파서 응답을 보존하지 않으며 검증 실행 스크립트가 이번 응답을 보존했다.
- 작성 가이드가 원문의 문단 전개와 얼마나 부합하는지. 현재 legacy 가이드에는 공통 템플릿이 포함되어 있어 목차 점수로 가이드 충실도를 대신할 수 없다.
- 골든 가이드가 실제 초안의 장별 전개·문체에 반영되는 정도. 현재 작성기는 고정 목차를 사용하므로 원문 목차의 단순 복제율을 반영률로 쓰면 안 된다.
- 초안의 과학적 정확성·새로움·자연스러움 및 다른 논문으로의 일반화.

기준선 측정 후에는 기준표 사용자 검수, 새 분석 결과와의 비교, 원문 관찰에 연결된 작성 가이드 평가, 초안 반영 평가 순으로 진행한다. 자동 평가 도구를 만들었다는 것만으로 평가 기준 자체가 독립 검증되었다고 보지 않는다.

## Studio 서술형 출력의 재평가

현재 Studio 구조 분석 단계는 구조화된 목차 객체 대신 Markdown 문자열을 반환한다. 마지막 단계는 작성 체크리스트이므로 `include=["all"]`로 구조 분석 단계를 별도로 확보했다. 원본 응답 전체는 로컬의 ignored `draft_history/20261030-studio-npu-validation/`에 보존했다.

`studio_outline_evaluation.py`는 구조 분석의 ‘섹션 계층 및 순서’ 구간에서 굵게 표시된 명시적 번호·제목만 화살표와 쉼표로 분리한다. 원문 기준표에서 빠진 항목을 채우거나 LLM을 다시 호출하지 않는다. 부모 관계는 출력된 번호에서만 복원한다. 역할·페이지는 제공되지 않아 추론하지 않고 N/A로 기록한다. 평가용 중간 트리의 `other` 역할은 기술적 자리표시자이며 Studio가 분류한 역할이 아니다. 이 트리는 서비스용 schema_version 2 프로파일이 아니다.

```powershell
.\.venv\Scripts\python.exe -X utf8 -B studio_outline_evaluation.py --structure evaluation/golden/predictions/npu-studio-structure.md --output evaluation/golden/results/npu-studio.json
```

이 점수는 Studio 응답에 명시된 상세 목차의 정확성과 완전성이다. 전체 서술의 의미적 분석 품질, 이전 Studio 설정 대비 개선 효과, 직접 API와 같은 조건의 모델 성능 비교는 아니다.

## 명시적으로 지정한 Studio Config 2

사용자가 제공한 같은 Agent의 Config ID 2를 직접 요청해 검증했다. `paper_evidence_review` 단계가 추가되었고 구조·스타일·검토 내용이 이전 응답과 달라졌다. 결과는 `results/npu-studio-config2-validation.md`에 있다.

`studio_json_evaluation.py`는 새 응답의 `headings` 또는 `sections`를 평가용 트리로 변환한다. 부모는 실제 parent ID에서만 읽고, 페이지는 원본 page 또는 실제 evidence ID로 연결된 evidence 배열에서 읽는다. 원문 기준표로 누락을 보완하지 않는다. 역할은 제공되지 않아 추론하지 않는다. 원본 응답의 중복 ID·없는 부모·순환은 실패 처리한다.

구조 분석 JSON과 스타일 JSON은 엄격한 JSON 문법 검사를 통과했지만, 마지막 검토 응답은 문자열 안의 실제 줄바꿈 때문에 실패했다. `diagnostic_controls=True`는 내용 확인을 위한 제한적 진단 파싱이며 원본을 수정하거나 문법이 유효하다고 인정하지 않는다. 원본 오류 위치와 문법 실패 상태를 보고서에 그대로 남긴다.

Git에는 목차 관련 필드만 남긴 `*-projection.json`을 보관한다. 마지막 검토의 전체 원본과 인용문은 ignored 실행 폴더에만 유지한다. 특히 검토 투영본은 로컬에서 직렬화한 평가 자료이므로, 그 파일이 JSON으로 열린다고 해서 원본 검토 응답도 유효했던 것은 아니다.

## Studio Config 3 실패 검증

사용자가 Config ID 3으로 재평가를 요청했다. 서로 다른 새 작업 두 번(최초 실행과 제한적 재시도) 모두 마지막 `paper_evidence_review`에서 `model_request_error`로 종료됐다. 완료된 구조 분석은 같은 목차 기준 F1 100%이지만, 전체 워크플로우와 최종 JSON은 평가 불가로 구분했다. 실패 응답의 빈 객체를 정상 검토 결과로 채점하지 않았다. 상세 내용은 `results/npu-studio-config3-validation.md`와 `results/npu-studio-config3.json`에 있다.

## Studio Config 4

사용자가 Config 4로 정정한 뒤 별도 새 작업을 실행했다. 네 단계가 모두 완료됐고, 구조 분석과 최종 검토 JSON 객체의 목차 F1은 같은 원문 기준으로 100%다. Config 2의 JSON 내부 제어문자 오류는 이번 최종 객체에서 관찰되지 않았다.

다만 JSON 객체 뒤에 출처 표시 `【†1】`~`【†37】`이 붙어 응답 전체의 엄격한 JSON 파싱은 `Extra data`로 실패한다. `decode_document(..., diagnostic_citations=True)`는 진단용으로 명시한 경우에만 엄격한 JSONDecoder로 첫 객체를 읽고, 남은 부분이 출처 표시 패턴만으로 구성되는지 확인한다. 일반 설명·두 번째 객체·기타 문자열은 버리지 않으며, 객체 내부 오류도 이 기능으로 고치지 않는다. 원본 전체의 strict_valid는 false로 유지하고 객체 자체의 json_object_strict_valid=true를 별도 기록한다.

애플리케이션 입력이나 Studio 지침에는 이 처리를 적용하지 않았고 평가 도구에만 옵션을 추가했다. 상세 비교는 `results/npu-studio-config4-validation.md`에 있다.

## 두 번째 논문: RGBD Config 4

2026-10-30 `research_revies.pdf`(16쪽)를 같은 Agent의 Config 4로 실행했다. 실행 전 작성한 `rgbd-reference.json`의 번호 목차 23개와 제외 제목 목록은 변경하지 않았다. 원본 PDF만 전송했고 기준표는 입력하지 않았다. 네 단계가 약 421초의 폴링 후 완료됐다.

| 대상 | 제목+번호 정밀도 | 재현율 | F1 | 불필요한 항목 |
|---|---:|---:|---:|---:|
| 기존 legacy 저장 분석 | 41.7% | 21.7% | 28.6% | 7 |
| Config 4 구조 분석 | 76.7% | 100% | 86.8% | 7 |
| Config 4 최종 검토의 독립 목차 배열 (진단) | 79.3% | 100% | 88.5% | 6 |

Config 4의 실제 본문 목차는 구조·최종 검토 모두 23/23이고 번호·부모·level·시작 페이지가 일치한다. Parse 모델은 실제 절 2개를 paragraph로 분류했지만 구조 분석이 복원했다. 반대로 문장·수식·표 제목·문장 조각 등을 heading1로 분류한 결과가 후속 목차에 남아 정밀도를 낮췄다. 고정 평가기는 제외 제목과 문자열이 다른 데이터 제공 안내 문장도 불필요한 항목에 포함한다. 결과를 보고 별칭을 추가하지 않았다.

최종 검토에는 JSON 객체 뒤의 인용 표시뿐 아니라 document_title 문자열이 닫힌 뒤에도 인용 토큰이 삽입됐다. 2행 166열에서 문법 오류가 나므로 NPU에서 사용한 첫 객체/접미부 분리 옵션으로 처리할 수 없다. 원본 sections 배열 39개와 evidence 배열 51개만 독립적으로 strict JSONDecoder.raw_decode로 읽어 진단했다. 응답을 보정하지 않았고 전체 JSON의 strict_valid 및 json_object_strict_valid는 false다. 최종 검토 점수는 해당 배열에 한정한다.

세부 비교·오탐 목록·원인·개선 후보는 `results/rgbd-studio-config4-validation.md`에 있다. 목차 투영과 결과 JSON은 `predictions/rgbd-studio-config4-*-projection.json`, `results/rgbd-studio-config4-*.json`이다. 전체 API 응답과 오프라인 평가 스크립트는 ignored `draft_history/rgbd-config4/`에 보관했다. 앱의 기존 분석 프로파일과 Studio 지침은 변경하지 않았다.
