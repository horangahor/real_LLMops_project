# 연구 자료 기반 논문 초안 작성기

연구 자료와 참고 논문의 구조·문체 가이드로 논문별 작성 계획을 만들고,
계획에 따라 장별 작성·검토·수정을 수행하는 Streamlit 서비스다.
기존 CUDA 고정 목차 작성기는 비교 모드로 보존한다.

다른 컴퓨터에서 설정하고 이어갈 작업은 [HANDOFF.md](HANDOFF.md)를 먼저 확인한다.
검증한 의존성은 `requirements.txt`, 비밀 값이 없는 설정 예시는 `.env.example`에 있다.
아키텍처와 실제 실행 흐름의 PNG/SVG는 `docs/diagrams/`에 있다.

## 연구별 작성 계획 (앱 기본값)

`paper_plan.py`는 연구 근거·작성 계획의 연결을 검증하고, `planned_paper.py`는 계획·작성·검토를 실행한다.
연구 PDF는 Document Parse API 원본에서 근거를 추출한다. 모델은 근거가 되는 원문 요소 ID를 선택하고, 인용문과 페이지는 코드가 해당 요소에서 직접 연결한다.
기본 추출기 `research_extract_v3.py`는4쪽+인접문맥의 1차 수집 캐시를 재사용하고, 모든 페이지·원문 요소에 대해 누락을 다시 검사·복구한다. 이전의 구간당8개·요약18개 제한은 없다. 원문 영역이 비었거나 숫자 OCR 띄어쓰기가 의심되면 이미지로 다시 읽어 원래 Parse와 별도 출처로 저장한다.
문제·조건·방법·결과·실패·한계를 구분하고, 관측·구현·해석·가설·계획·확인 필요와 연구노트/실행 로그/코드/인용 안내/AI 조언을 분리한다. 측정값(지표·값·단위·조건·원문 ID), 버전·설정, 관찰·비교, 해석 한계를 보존한다.
`research_values.py`는 진술·조건·관찰·설정 안의 수치까지 대조하고 과학 표기·소수 쉼표·범위·버전을 구분한다. 단일 측정값을 범위로 잘못 분류한 경우 보정 전 유형·원래 값을 남긴다. 잘못된 부가 측정값은 별도 격리하며 올바른 주진술 전체를 자동 제외하지 않는다.
별도 Solar 원문 검토를 거쳐 수치 검사 통과·원문 뒷받침 후보만 작성으로 넘긴다. 원문 뒷받침 부족·귀속 불확실 후보는 격리한다. 자료 성격·의미 판정은 LLM 보조이므로 독립적 사실 검증이나 완전한 누락 방지는 아니다. OCR 표기 차이로 정상 내용이 보류되거나 반복 행이 과다 수집되는 사례도 남아 있다.

v3는 질문·계획·해석·인용된 AI 조언도 귀속과 한계를 보존한 `context_only` 근거로 남긴다. 이 항목은 연구 문제·미수행 계획·보고된 조언의 문맥에만 쓰며 실험 성과로 쓰지 않는다. 귀속을 바꾸거나 원문 뒷받침이 부족한 후보는 격리한다. 최종 작성 입력의 필드와 원문을 요소별로 다시 비교하고 미해결 항목을 추가 복구한다. 원시 예측 행렬 등도 원문 전체를 `source-archive.json`에 보존한다. `element_ledger`는 각 요소의 실제 연결 근거·원시 데이터·비연구 표식·미해결 상태를 기록한다. 미해결 원문 항목이 남으면 본문 생성을 중단한다. 모델의 대장 검토는 독립적인 의미적 완전성 보증이 아니다.
연구 근거 JSON은 자동 추출의 중간 산출물이다. 앱·CLI·기본 API는 원본 PDF를 받아 생성하며 작성용 facts JSON의 직접 입력은 받지 않는다.
사람이 정리한 `research_evidence.json`과 장별 `section_briefs`·수작업 결과표는 현재 실행 경로에 연결하지 않는다. 원본이 없으면 이전 근거로 대체하지 않고 멈춘다.

```text
연구 PDF → 자동 연구 근거 + 프로젝트 정책 + 골든 역할별 가이드·역할 계층
   → 논문별 계획 (장·소절·목적·필수 내용·근거·참고 지침 적용 방법·의존 순서)
   → 원문 ID/참고 ID/표/의존 관계 검증
   → 각 장의 작성자 (정해진 본문 칸만 생성, 제목·번호는 코드 조립)
   → 계획 항목 전수 검토 + 원문 ID/본문 인용 검증 + 참고 구성 적용 검토
   → 오류가 있으면 종합 편집·재검토 (최대 두 번 수정)
   → 연구별 초안·계획·원본 응답·검토 이력·진단 지표 저장
```

계획의 장 수와 소절 수는 연구마다 달라진다. 목차 원문을 복제하지 않고 근거와 연구 목적에 맞춰 가이드를 적용한다.
필수 항목에서 명시한 실제 근거는 장의 입력에도 연결하고, 존재하지 않는 ID는 추가하지 않는다.
제목의 중복 절 번호는 코드에서 정리하며, 다른 내용을 추론해 채워 넣지 않는다. 관련 연구 정책은 프로젝트 설정으로 분리한다.
모델이 새 표·셀 값을 임의로 만들면 검사를 통과하지 못한다. PDF 표의 정확한 행·열을 작성용 표로 자동 변환하는 기능은 아직 없으며, 기존 수작업 표를 대신 삽입하지 않는다.

`projects/generic.json`은 일반 작성 정책이고 `projects/cuda.json`은 CUDA 원본 PDF 경로와 빈 관련 연구 정책만 지정한다.
CUDA 프로젝트도 원본 PDF에서 근거를 자동 추출한다. 기존 수작업 파일은 과거 비교 기록으로 보존하며 새 작성에는 읽지 않는다.

앱에서 **연구 자료에 맞춰 계획**을 선택하고 연구 PDF를 업로드한다. 프로젝트의 `input/` 폴더에 PDF를 넣으면 **input 폴더의 연구 자료**에서 바로 선택할 수도 있다.
**CUDA 원본 PDF 자동 분석**도 같은 자동 추출을 사용한다. **작성 계획만 만들기**로 먼저 계획을 볼 수 있다.
**연구 근거만 추출하기**는 골든 가이드·계획·본문 생성 없이 근거 목록을 만들고 유형·주장 강도별로 원문을 확인한다. JSON·Markdown 다운로드를 지원한다. 이 작업은 이전 초안을 갱신하지 않는다.
완료한 일반 초안은 `draft_history/planned/<project>/<입력 식별자>/`에 저장되고 앱 재시작 시 마지막 정상 초안을 불러온다.
기존 `paper_draft_full.md`와 CUDA 비교 산출물은 별도로 보존한다. 입력·모델·가이드·프롬프트가 같은 호출만 캐시로 재사용한다.
실패 시 후보/원본 응답을 보관하고 기존 정상 초안을 유지한다.

```powershell
python -X utf8 -B planned_paper.py --research-pdf "연구자료.pdf" --extract-only
python -X utf8 -B planned_paper.py --research-pdf "연구자료.pdf" --plan-only
python -X utf8 -B planned_paper.py --research-pdf "연구자료.pdf"
python -X utf8 -B planned_paper.py --project cuda --plan-only
```

추출 결과는 해당 원본의 `draft_history/parse-api-v1/<원본 식별자>/research-evidence-v3/<출처 식별자>/evidence.json`과 `evidence.md`에 저장한다. `source-archive.json`, 페이지별 보완 기록·최종 수집 대장도 같은 실행 폴더에 둔다. 원래 Parse·이미지 재분석·모델 응답과 v1/v2 결과는 보존한다.

새 Python 호출은 `PaperDraftOrchestrator.run_pipeline(planning_mode="adaptive", project_id="generic", ...)`로 사용한다.
API의 생략 기본값도 `adaptive`다. 고정 목차를 비교하려면 `planning_mode="legacy_cuda"`를 명시한다. 비교 경로도 추출물을 수작업 근거로 자동 교체하지 않는다.

필수 내용 충족률과 참고 구성 적용 판정은 LLM 보조 검토다. 실제 본문 인용·ID를 코드로 확인하지만 독립적인 품질 정답은 아니다.
연구별로 미리 정한 외부 평가 항목과 사람 검수 기준을 함께 사용해야 한다. 평가 항목의 정의는 `evaluation/planning/README.md`에 있다.
연구 근거 추출의 내용 평가 기준·항목별 판정·재계산 코드는 `evaluation/extraction/benchmark/`에 있다. [1차 평가 보고서](evaluation/extraction/benchmark/report.md)는 CUDA 원문과의 충실도·출처 완전성·값/단위/조건·표본 필수 사실 누락·과도한 제외를 분리한다. 평가용 참조 사실은 작성 입력에 전달하지 않는다.

[v2 비교 보고서](evaluation/extraction/v2/report.md): 같은42개 개발 참조 사실의 완전 보존이15/42(35.7%)→33/42(78.6%), 작성 입력까지 완전 보존은3/42→24/42다. 후보479개·작성용399개는 개수이며 전체 정확도 점수가 아니다. CUDA 한 자료에서의 Codex 단독 개발 평가로, 다른 연구 자료의 일반화 성능은 아직 확인하지 않았다. 테스트146개와 실제 캐시의 네트워크 금지 재생·앱 페이지/필터/이전 초안 보존을 확인했다. 기존7장 초안은 새 근거로 재생성하지 않았다.

## 기존 CUDA 비교 모드의 논문 구성

서론과 결론은 소절 없이 연결된 문단으로 작성한다. 본문은 장마다 세 소절만 사용한다.

| 장 | 소절 구성 |
| --- | --- |
| 1장 서론 | 소절 없음: 배경 → 문제 → 목표·기여 |
| 3장 배경·문제 정의 | 3.1 배경 개념 / 3.2 기존 계산 흐름 / 3.3 문제 정의 |
| 4장 방법론 | 4.1 전체 구조 / 4.2 메모리·데이터 이동 / 4.3 커널·실행 최적화 |
| 5장 실험·고찰 | 5.1 실험 설계 / 5.2 결과 및 분석 / 5.3 한계와 미해결 문제 |
| 6장 결론 | 소절 없음: 핵심 발견 → 성과 → 한계·후속 과제 |

프로파일링과 대규모 입력 실험은 5.2 안에서 문단·표로 구분하며,
별도 5.6 결과 요약은 만들지 않는다. 조건이 다른 실험을 한 표에 합치지는 않는다.
`SECTION_SUBSECTIONS`를 작성·검토·종합 편집이 공유하고 코드 검사로도 확인한다.

## 실행

이 폴더에서 PowerShell로 실행한다. 기존 가상환경의 Streamlit, requests,
python-dotenv가 필요하다. `.env`의 기존 Upstage 설정을 사용한다.
작성·검토 모델 기본값은 `solar-pro4`이며 `.env`의 `SOLAR_MODEL`로 바꿀 수 있다.
검토 호출에는 지원 모델에 한해 `reasoning_effort=low`를 사용한다.
[Upstage 공식 Chat API](https://console.upstage.ai/api/chat)의 모델·파라미터 규격을 따른다.

```powershell
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

브라우저에서 http://localhost:8501 에 접속한다.
CLI는 `.\.venv\Scripts\python.exe paper_draft_agent.py`로 실행한다.
아래 호출 횟수는 **기존 CUDA 고정 구성 모드** 기준이다. 연구별 계획 경로는 근거 추출·계획·장 수·수정 횟수에 따라 달라진다.
완료한 호출은 캐시로 재사용한다. 기존 모드는 장별 5회 → 검토 → 종합 편집 → 재검토로 기본 8회의 Solar API 호출을 사용한다.
주요 오류가 남으면 종합 편집과 검토를 한 번 더 수행한다(최대 10회).
현재 CUDA 검토 프로파일에는 서론·결과·결론 전용 근거가 있으며, 종합 편집 후 세 장을 선택
근거로 다시 작성한다. 이 경우 기본 11회, 추가 수정까지 최대 16회 호출한다.

## 이전 수작업 근거·결과표 실험 기록 (현재 실행에서 제외)

아래는 과거 CUDA 실험의 구현 설명이다. 수작업 프로파일을 로드하는 연결은 제거했고, 기존 파일·보조 함수만 비교 기록으로 보존한다.

`paper_content.py`는 검토 프로파일의 `section_briefs.selected_facts`를 통해 장별 작성
자료를 분리한다. 서론은 목표·문제·기여 중심, 결론은 선택한 대표 관측과 의미 중심으로
작성하며, 다른 장의 전체 실험 이력 대신 목적·소절 구성을 문맥으로 받는다.
결과 장의 해석 작성자에게도 표의 역할·조건과 정성적 관측을 주고 셀 값은 주지 않는다.
종합 편집 뒤에도 결과·서론·결론을 이 자료로 독립 정리하여 수치 나열이 다시 유입되는 것을 줄인다.

`research_evidence.json`의 `result_tables`는 기존 검토 근거에 연결한 표 데이터다.
초기 실행, 후기 단일 실행, 평균 bound 계산, 추론·bound·검증, 배칭, 입력 복사 실험을
별도 표로 렌더링한다. 모델은 해석 문장을 작성하고 표의 셀은 코드가 조립한다.
새 실험이나 가속비를 계산해 추가하지 않는다. 종합 편집에서 표가 빠지거나 바뀌어도
5.2에 검토된 표를 다시 배치한다. 다른 연구의 미검토 추출물에는 이 CUDA 표를 적용하지 않는다.
초안과 검토 기록에는 작성 정책 버전과 글자 수·단위가 붙은 수치 개수·표 행 수를 기록한다.
이 값은 전후 비교용이며 글이 짧다는 이유로 품질이 높다고 판정하지 않는다.

## 기존 CUDA 고정 구성의 Orchestrator–worker 흐름

```text
연구 PDF → method_result.py (Studio Agent) → 연구 사실 JSON
참고 논문 → Document Parse API → Python 목차 복원·검증 → Solar 작성 가이드
                  (원본 요소·페이지·좌표 보존)              ↓
                                                구조·문체 프로파일
                                     ↓
                        PaperDraftOrchestrator
                                     ↓
       SectionWriter: 3장 → 4장 → 5장 → 1장 → 6장
              각 worker는 앞서 작성한 장을 문맥으로 받음
                                     ↓
       PaperReviewer: 원문 검토 근거와 장별 주장을 대조
                                     ↓
       PaperSynthesizer: 검토 지적을 반영하여 종합 편집
                                     ↓
       PaperReviewer + 알려진 오류 재발 검사: 수정 결과 재검토
                                     ↓
       1장 → 빈 2장 → 3장 → 4장 → 5장 → 6장으로 조립·저장
```

현재는 Python에서 명시적으로 순서를 제어한다. LangGraph, FastAPI, ChromaDB,
SSE, Docker는 아직 이 구현에 포함하지 않는다.

기존 CUDA 비교 모드의 기본 실행은 저장된 `Results & Discussion.json`과 `paper_structure_analysis.json`을
읽는다. 참고 스타일을 새로 분석하려면 `paper_structure.py`를 별도로 실행한다.
CUDA 연구 PDF를 업로드하면 기존 연구 JSON의 존재 여부와 관계없이 Studio Agent로
다시 추출한다. 현재 추출기는 결과를 `Results & Discussion.json`에 저장한다.
연구 데이터와 별개로 참고 논문은 문체와 구조만 제공한다.

## 골든 샘플 분석

골든 참고 논문의 분석은 Studio 없이 `paper_structure.py`에서 실행한다.
`document_parse.py`가 Document Parse API를 직접 호출하고 원본 JSON·요소·페이지·좌표·설정·해시를 보존한다.
`paper_outline.py`가 실제 절 번호를 기준으로 제목·시작 페이지·부모를 복원한다. 줄바꿈된 제목,
paragraph로 오분류된 절, 제목으로 오분류된 반복 페이지 머리말을 처리하며, 문장·수식·캡션을 목차로 승격하지 않는다.
존재하지 않는 부모나 충돌하는 번호는 임의로 보완하지 않고 오류로 처리한다.
현재 지원 범위는 참고문헌 이전의 **아라비아 숫자 본문 목차**다. 무번호·로마 숫자 목차는 별도 지원이 필요하다.

목차는 코드가 결정하고 Solar는 원문 요소 ID에 역할과 재사용할 문체·작성 가이드만 연결한다.
`json_schema`와 로컬 ID·형식 검증을 사용한다. 원문 전용 영문 식별자가 재사용 지침에 남으면 실패시킨다.
이 식별자 검사는 내용 전체의 안전한 일반화나 문체 품질을 증명하지 않는다.
현재 저장된 가이드의 일부 원문 전용 표현은 Codex가 추가 추상화했고 `guidance_review`에 전후를 기록했다.
전체 목록의 분석이 성공한 뒤 앱의 `paper_structure_analysis.json`을 교체하며 이전 파일은 `draft_history/`에 백업한다.
동일 원본·파싱 설정의 원본 캐시를 재사용하고, 가이드는 입력·목차·프롬프트·모델이 일치할 때만 재사용한다.

직접 API로 실행한 NPU 14개·RGBD 23개 목차의 제목+번호 F1은 두 편 모두 100%이며,
부모·시작 페이지도 일치했다. 두 샘플을 보며 규칙을 개선했으므로 독립 검증이나 다른 논문 전체의 정확도가 아니다.
상세 비교는 `evaluation/golden/results/parse-api-v1-validation.md`에 있다.
이전 Studio Config 2·3·4와 RGBD Config 4 결과는 비교 기준으로 `evaluation/golden/`에 그대로 보관한다.
이번 전환은 참고 논문 분석 경로이며, CUDA 연구 자료를 추출하는 `method_result.py`의 Studio 경로는 별도다.
새 프로파일은 `schema_version: 2`로 저장하며, 다음 항목을 구분한다.

- `observed_outline`: 실제 관찰된 목차와 하위 절. 확인되지 않은 페이지는 `null`.
- `style_rules`, `section_guidelines`: 재사용할 문체와 역할별 필수 내용·문단 흐름·표/그림 지침.
- `not_to_transfer`: 원 논문에서 우리 연구로 옮기면 안 되는 내용.
- `provenance`, `analysis_notes`: PDF 분석인지 기존 분석 변환인지와 확인 한계.

장별 작성자는 자신의 역할에 맞는 지침만 받는다. 원 논문의 목차·수치·적용 금지 예시를
프롬프트 전체에 붙여 넣지 않는다. 종합 편집에는 현재 작성 범위의 지침을 함께 전달한다.
이전 Markdown 형식도 읽을 수 있지만, 새 형식으로 변환하면 역할별 전달이 적용된다.

```powershell
# 저장된 분석을 로컬에서 구조화: 외부 API 호출 없음
.\.venv\Scripts\python.exe paper_structure.py --migrate-legacy
# PDF에서 분석: Parse API + Python 목차 + Solar 작성 가이드
.\.venv\Scripts\python.exe paper_structure.py "참고논문.pdf"
# 목차만 분석: Parse API + Python, Solar 호출 없음 (별도 출력 필수)
.\.venv\Scripts\python.exe -X utf8 -B paper_structure.py --outline-only --run-dir draft_history/parse-api-v1 --output evaluation/golden/predictions/parse-api-v1-outlines.json
# 저장된 목차를 기존 두 원문 기준표로 평가: 외부 호출 없음
.\.venv\Scripts\python.exe -X utf8 -B evaluation/golden/evaluate_parse_pipeline.py --profiles evaluation/golden/predictions/parse-api-v1-outlines.json
```

전체 목록의 분석과 형식 검증이 성공한 뒤 기존 결과를 교체한다.
기존 파일은 `draft_history/`에 보관한다. 기존 분석 변환은 PDF 원문을 재검증한 결과가 아니다.
기본 PDF 탐색은 프로젝트의 `golden sample/`와 상위 폴더 순서다. `--mode standard|enhanced|auto`,
`--ocr auto|force`, `--parse-model`, `--run-dir`, `--force-parse`로 파싱 조건과 캐시를 제어한다.
기본 파싱 모델은 재현을 위해 `document-parse-260930`, 모드는 `standard`, OCR은 `auto`로 고정한다.
로컬 변환은 기존 Markdown에서 명시된 목차를 분리하고, 관찰된 절의 역할에 맞춘 공통
작성 가이드를 연결한다. 기존 자유 형식 분석의 모든 세부 문장을 의미 분석해 옮기는 방식은 아니다.
Streamlit의 **골든 샘플 구조·작성 가이드**에서 논문별 탭으로 목차·작성 가이드·문체·JSON을
확인할 수 있다. JSON과 읽기용 Markdown을 각각 다운로드할 수 있으며,
프로파일 형식에 문제가 있으면 오류를 표시하고 초안 생성을 시작하지 않는다.

## 과거 수작업 근거 기록과 품질 검토

`research_evidence.json`은 현재 CUDA 연구 PDF의 본문과 일부 로그·표를 대조한
초안 작성용 근거 12개를 담는다. 각 근거에는 페이지, 관측 내용, 해석 한계가 있다.
이 자료는 Codex가 원문 대조로 정리했으며 저자·전문가의 독립 검증을 받은 정답이라는 뜻은 아니다.
과거에는 추출 JSON과 원본 PDF의 SHA-256이 모두 일치할 때 이 프로파일을 사용했다. 현재 작성 경로에서는 프로파일을 로드하지 않는다.
결론에는 핵심 주장, 문단별 역할, 선택할 대표 근거를 `section_briefs`로 지정한다.
결론이 모든 중간 실험 수치를 되풀이하지 않도록 대표 성과만 선택하게 하고,
문단 구성·분량·수치 나열도 검사한다. 이 프로파일은 현재 연구 자료에 맞춰 검토한 설정이다.
결론은 1,000~2,500자를 권장하고 최대 3,000자까지 허용한다. 서로 다른 성능 수치는
10개 이내를 권장하며, 개수 초과는 경고로만 기록하고 저장을 막지 않는다.
분량·수치 기준은 작성·검토·종합 프롬프트와 코드 검사에서 같은 기준을 사용한다.
메시지는 실제 개수·글자 수를 표시하며, 내용의 반복 여부를 판정한 것은 아니다.
근거 없는 수치와 잘못된 비교는 수치 개수와 관계없이 오류로 검사한다.
`PAPER_EDITORIAL_RULES`는 장별 설명 역할, 작성 방침의 본문 노출 방지, 중복 축소,
관측과 인과 주장 강도 조절을 작성자·검토자·종합 편집자에게 공통으로 전달한다.
일부 작성 방침 문구는 코드에서도 경고하며, 연구의 실제 한계와 확인 필요 표시는 유지한다.
검토되지 않은 원래 추출값은 작성 프롬프트에서 제외하여 잘못 연결된 수치의 재사용을 막는다.
PDF나 추출 결과가 바뀌면 기존 검토 결과를 새 자료에 그대로 적용하지 않는다.
새 추출물은 원문 대조 전 상태로 표시되며, 해당 자료용 근거 검토가 추가로 필요하다.

검토자는 단일 샘플 지연·bound 구간 가속비·배칭 처리량, 예열과 측정 경계,
정밀도 전환 실험과 다른 실험의 수치 혼동을 확인한다. 이미 발견한 오류와
결론의 소절·목록 반복은 별도 코드 검사로도 확인한다.
주요 오류가 남으면 기존 저장 초안을 유지하고 후보와 검토 지적을 별도로 저장한다.
도중에 중단되면 `.paper_draft_working.json`에 저장한 장별 초안을 이어서 사용한다.
연구 근거·참고 스타일·모델·작성 지침이 모두 일치할 때만 재사용하며,
전체 결과를 성공적으로 저장하면 중간 저장 파일을 제거한다.

## 코드와 산출물

- `paper_plan.py`: 연구 근거 정규화, 가이드 선택 목록, 자료별 작성 계획·프로젝트 정책 검증.
- `planned_paper.py`: 원본 PDF → 자동 근거 추출 → 계획 → 본문 칸 작성 → 계획·근거·참고 구성 검토와 수정, CLI.
- `projects/generic.json`, `projects/cuda.json`: 공통 정책과 CUDA 자료·검토 근거·빈 관련 연구 정책.
- `draft_history/planned/`: 입력별 계획·초안·원본 응답·검토·진단 지표. 완료한 앱 초안의 마지막 위치도 기록한다.
- `evaluation/planning/`: 일반 작성 경로의 평가 정의 및 실행 검증 결과.

아래는 기존 CUDA 비교 모드의 코드와 산출물이다.

- `paper_draft_agent.py`: 장별 worker, 종합 worker, orchestrator, CLI.
- `paper_prompts.py`: 장별 역할과 근거 사용 지침.
- `paper_quality.py`: 알려진 오류 검사와 과거 검토 근거 재현용 보조 함수. 수작업 프로파일 로더는 현재 실행에서 호출하지 않는다.
- `archive/manual-evidence/research_evidence.json`: 과거 수작업 검토 기록. 현재 초안의 연구 근거로 사용하지 않는다.
- `streamlit_app.py`: 입력 선택, 진행 상황, 초안 보기, Markdown/TXT 다운로드.
- `paper_draft_full.md`, `paper_draft_full.txt`: 새로 생성하는 전체 초안.
- `paper_draft_sections.json`: 종합 전 장별 초안과 종합 후 장별 본문.
- `paper_draft_review.json`: 검토 지적, 수정 후 검토 결과, 사용한 근거 출처.
- `paper_draft_candidate.md`, `paper_draft_review_failed.json`: 검토 미통과 시 후보와 지적.
- `archive/legacy-drafts/paper_draft_section4_5.md`: 기존 4·5장 초안. 새 생성에서 갱신하지 않는다.

전체 초안을 아직 생성하지 않았다면 화면에는 기존 4·5장 초안을 표시한다.
모든 장과 종합 응답의 형식 검증이 성공한 뒤 산출물을 갱신한다.
연구 자료에 없는 정보는 `[확인 필요: ...]`로 표시하도록 지시한다.
검토는 LLM 판단과 알려진 오류의 재발 검사를 조합한다. 모든 사실을 자동 증명하거나
독립 재실험하는 체계는 아니며, 저자가 측정 조건·수치 정확성·연구 주장을 최종 확인해야 한다.
초록과 참고문헌은 현재 생성 범위에 포함하지 않는다.

## API 호출 없는 회귀 검사

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

외부 호출을 대체하여 장별 의존 관계, 종합 입력, 빈 관련 연구, PDF 재추출,
실패 시 기존 초안 보존을 검증한다.
