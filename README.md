# 연구 자료 기반 논문 초안 작성기

연구 자료와 참고 논문의 구조·문체 가이드로 논문별 작성 계획을 만들고,
계획에 따라 소절 작성·검토, 장별 편집·검토, 전체 편집·검토를 수행하는 Streamlit 서비스다.
기존 CUDA 고정 목차 비교 경로는 제거했으며, 근거 수집의 요구사항 기반·전체 수집 모드는 모두 지원한다.

다른 컴퓨터에서 설정하고 이어갈 작업은 [HANDOFF.md](HANDOFF.md)를 먼저 확인한다.
검증한 의존성은 `requirements.txt`, 비밀 값이 없는 설정 예시는 `.env.example`에 있다.
아키텍처와 실제 실행 흐름의 PNG/SVG는 `docs/diagrams/`에 있다.

## React 작업실 (추가 UI)

기존 Streamlit과 같은 Python 파이프라인·캐시를 사용하는 React UI를 `frontend/`에 추가했다.
PDF 선택·업로드, A/B 근거 수집, 요구사항 생성, 저장 근거 검색·원문 확인,
사용자 지시·임시 승인 후 재개, 사실·측정값 승인/제외/복원, 중복 검토,
작성 계획·초안 생성, 진행 기록, Markdown 미리보기, 경고·산출물 다운로드를 지원한다.
`web_api.py`와 `web_workspace.py`는 호출·진행 상황을 연결하며 작성 에이전트나 검토 흐름을 변경하지 않는다.

최초 설치와 빌드 (Node 22.12 이상 또는 20.19 이상):

```powershell
python -m pip install -r requirements-web.txt
npm --prefix frontend ci
npm --prefix frontend run build
python -m uvicorn web_api:app --host 127.0.0.1 --port 8000
```

브라우저에서 **http://127.0.0.1:8000**으로 접속한다. API 키는 기존 `.env`를 사용하며 브라우저로 전달하지 않는다.
개발 중에는 위 API 서버와 별도 터미널에서 `npm --prefix frontend run dev`를 실행해
**http://127.0.0.1:5173**에 접속한다. Vite가 `/api` 요청을 8000 포트로 연결한다.
UI 개발 서버만 재시작해도 실행 중인 Python 작업은 계속된다. Python 서버는 작업 중 `--reload` 없이 실행한다.

React에서 시작한 작업 상태는 `draft_history/web-ui/<작업 ID>/job.json`에 저장된다.
서비스 재시작 후 자동 재전송하지 않으며 실행 기록에서 같은 요청을 재개할 수 있다.
실제 단계별 캐시는 기존 `draft_history/parse-api-v1/`와 `draft_history/planned/`에 저장된다.
작업은 한 번에 하나씩 실행한다. **같은 프로젝트에서 Streamlit과 React의 생성 작업을 동시에 실행하지 않는다.**
작업실은 인증 없는 로컬 전용 UI이며 127.0.0.1로 실행한다. 기존 Streamlit 실행 방식도 그대로 사용할 수 있다.

API 경계 검증은 `python -m unittest discover -s tests -p test_web_api.py`로 실행한다.
이 검증은 외부 모델을 호출하지 않는다.

**절 단위 생성:** ‘작성 계획’ 화면의 각 절에서 **이 절만 생성·재개**를 누르면
해당 소절들의 작성·검토 → 1차 편집 → 절 편집 검토까지만 수행한다.
계획에 저장된 PDF·수집 모드와 일치하는 자료를 선택해야 하며, 계획 생성·다른 절·전체 2차 편집은 호출하지 않는다.
이 작업에는 현재 설정 창의 새 분량 대신 해당 계획에 이미 배정된 분량·소절 작성 지침·근거를 사용한다.
1·2차 편집자에는 현재 `writing_policy.json`의 `editing` 규칙과 각 소절의 현재 분량·저장된 목표·상한을 전달한다.
편집 규칙을 수정하고 같은 절을 생성·재개하면 계획·소절 입력을 다시 만들지 않고 해당 편집 단계에 새 규칙을 적용한다.
숫자 분량은 축약 지침이며 새로운 편집 차단 검사를 추가하지 않는다. 보완 횟수·경고 완료 정책도 유지한다.
실제 전달한 규칙과 분량은 각 편집 단계의 `generate-*-editing-input.json`에서 확인할 수 있다.
완료한 소절·절 체크포인트는 재사용하며 나중에 전체 초안 생성에서도 이어서 사용한다.
기존 전체 `draft.md`, `sections.json`, 전체 검토·경고·분량 보고서와 최신 초안 포인터는 덮어쓰지 않는다.
선택한 절의 결과·진행·경고·원문 연결은 `draft_history/planned/<project>/<run>/section-runs/<section_id>/`에 저장한다.
화면의 **문단 → 근거 → 원문**에서 초안 문단, 추출 사실, 원문 인용·페이지를 확인하고 JSON으로 내려받을 수 있다.
문장별 출처를 새로 추정하지 않고 기존 문단별 근거 연결을 표시한다.

**Overleaf용 LaTeX 내보내기:** 전체 초안 상단과 각 절의 결과 화면에서 **Overleaf ZIP**을 누른다.
완료된 저장 결과만 변환하며 추출·계획·작성·검토 에이전트를 호출하지 않는다.
ZIP 루트에 `main.tex`, 본문 조각 `content.tex`, `latexmkrc`, 사용 안내, 원본 Markdown,
문단별 근거 연결 `provenance.json`과 변환 기록 `export.json`을 포함한다.
Overleaf의 **New project → Existing project (.zip)** (또는 Upload project)에서 가져온 뒤
**Compiler: XeLaTeX / Main document: main.tex**로 컴파일한다.
UTF-8 한글, 기존 장·소절 번호, Markdown 표·목록·강조·링크·코드와 일반 LaTeX 수식을 변환한다.
표는 위치를 유지하는 `longtable`로 변환하며 긴 표는 페이지를 나눌 수 있다.
기존 프로젝트에 절만 넣으려면 `content.tex`를 가져오고 `main.tex`의 패키지 설정을 참고한다.
근거 ID를 새 참고문헌·DOI로 만들지 않으며 원문 연결은 JSON에 보존한다.
원본 PDF·API 키·전체 API 응답은 ZIP에 넣지 않는다. 그림 파일은 자동 수집하지 않고 변환 기록에 표시한다.
내보내기 기능은 로컬 다운로드까지 수행하며 Overleaf 업로드는 사용자가 진행한다.
공식 안내: [프로젝트 ZIP 업로드](https://docs.overleaf.com/managing-projects-and-files/uploading-a-project),
[한글과 XeLaTeX](https://www.overleaf.com/learn/latex/Korean).

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
   → 각 소절의 작성자 → 해당 소절의 근거·필수 내용 검토
   → 장별 1차 편집자 → 소절 간 연결·누락·근거 검토
   → 전체 2차 편집자 → 논문 전체의 일관성·근거·계획 검토
   → 각 단계에서 최대 두 번 수정·재검토, 통과한 단계만 다음으로 전달
   → 연구별 초안·계획·원본 응답·검토 이력·진단 지표 저장
```

계획의 장 수와 소절 수는 연구마다 달라진다. 목차 원문을 복제하지 않고 근거와 연구 목적에 맞춰 가이드를 적용한다.
필수 항목에서 명시한 실제 근거는 장의 입력에도 연결하고, 존재하지 않는 ID는 추가하지 않는다.
계획 생성·보정 응답의 장별 및 필수 항목별 `evidence_ids`는 동일 ID만 최초 순서대로 중복 제거한 뒤 검증한다.
제거 내역은 `plan.json`의 `evidence_id_normalizations`에 남기며 모델 원응답은 그대로 보존한다. 잘못된 값·없는 ID·표 중복 배치 검사는 유지한다.
여러 장에 배정된 같은 표는 별도 배치 보정 호출에서 표 내용과 후보 장의 목적을 비교해 장 하나를 선택한다.
기존 근거 ID는 유지하며 표 배치만 조정한다. 원래 배정·선택 장·사유는 `table-placement.json`과 `plan.json`의 `table_placement_adjustments`에 보존한다.
제목의 중복 절 번호는 코드에서 정리하며, 다른 내용을 추론해 채워 넣지 않는다. 관련 연구 정책은 프로젝트 설정으로 분리한다.
모델이 새 표·셀 값을 임의로 만들면 검사를 통과하지 못한다. PDF 표의 정확한 행·열을 작성용 표로 자동 변환하는 기능은 아직 없으며, 기존 수작업 표를 대신 삽입하지 않는다.

`projects/generic.json`은 일반 작성 정책이고 `projects/cuda.json`은 CUDA 원본 PDF 경로와 빈 관련 연구 정책만 지정한다.
CUDA 프로젝트도 원본 PDF에서 근거를 자동 추출한다. 기존 수작업 파일은 과거 비교 기록으로 보존하며 새 작성에는 읽지 않는다.

앱에서 연구 PDF를 업로드하면 연구 자료에 맞춰 작성 계획을 만든다. 프로젝트의 `input/` 폴더에 PDF를 넣으면 **input 폴더의 연구 자료**에서 바로 선택할 수도 있다.
**CUDA 원본 PDF 자동 분석**도 같은 자동 추출을 사용한다. **작성 계획만 만들기**로 먼저 계획을 볼 수 있다.
**연구 근거만 추출하기**는 골든 가이드·계획·본문 생성 없이 근거 목록을 만들고 유형·주장 강도별로 원문을 확인한다. JSON·Markdown 다운로드를 지원한다. 이 작업은 이전 초안을 갱신하지 않는다.
완료한 일반 초안은 `draft_history/planned/<project>/<입력 식별자>/`에 저장되고 앱 재시작 시 마지막 정상 초안을 불러온다.
기존 `paper_draft_full.md`와 CUDA 비교 산출물은 별도로 보존한다. 입력·모델·가이드·프롬프트가 같은 호출만 캐시로 재사용한다.
실패 시 후보/원본 응답을 보관하고 기존 정상 초안을 유지한다.
계획의 소절 수에 맞춰 작성 호출 수가 정해진다. 검토를 통과한 단계는 재사용하고, 전체 편집은 오류 유무와 관계없이 실행한다.
단계별 후보·검토·체크포인트와 호출 수는 [계층형 작성 흐름](docs/HIERARCHICAL_DRAFTING.md)을 참고한다.

```powershell
python -X utf8 -B planned_paper.py --research-pdf "연구자료.pdf" --extract-only
python -X utf8 -B planned_paper.py --research-pdf "연구자료.pdf" --plan-only
python -X utf8 -B planned_paper.py --research-pdf "연구자료.pdf"
python -X utf8 -B planned_paper.py --project cuda --plan-only
```

추출 결과는 해당 원본의 `draft_history/parse-api-v1/<원본 식별자>/research-evidence-v3/<출처 식별자>/evidence.json`과 `evidence.md`에 저장한다. `source-archive.json`, 페이지별 보완 기록·최종 수집 대장도 같은 실행 폴더에 둔다. 원래 Parse·이미지 재분석·모델 응답과 v1/v2 결과는 보존한다.

새 Python 호출은 `PaperDraftOrchestrator.run_pipeline(planning_mode="adaptive", project_id="generic", ...)`로 사용한다.
API의 생략 기본값도 `adaptive`다. 삭제한 고정 구성의 모드 값은 입력·API 처리 전에 거부한다. CUDA 원본 PDF도 현재 계획 기반 경로에서 분석한다.

필수 내용 충족률과 참고 구성 적용 판정은 LLM 보조 검토다. 실제 본문 인용·ID를 코드로 확인하지만 독립적인 품질 정답은 아니다.
연구별로 미리 정한 외부 평가 항목과 사람 검수 기준을 함께 사용해야 한다. 평가 항목의 정의는 `evaluation/planning/README.md`에 있다.
연구 근거 추출의 내용 평가 기준·항목별 판정·재계산 코드는 `evaluation/extraction/benchmark/`에 있다. [1차 평가 보고서](evaluation/extraction/benchmark/report.md)는 CUDA 원문과의 충실도·출처 완전성·값/단위/조건·표본 필수 사실 누락·과도한 제외를 분리한다. 평가용 참조 사실은 작성 입력에 전달하지 않는다.

[v2 비교 보고서](evaluation/extraction/v2/report.md): 같은42개 개발 참조 사실의 완전 보존이15/42(35.7%)→33/42(78.6%), 작성 입력까지 완전 보존은3/42→24/42다. 후보479개·작성용399개는 개수이며 전체 정확도 점수가 아니다. CUDA 한 자료에서의 Codex 단독 개발 평가로, 다른 연구 자료의 일반화 성능은 아직 확인하지 않았다. 테스트146개와 실제 캐시의 네트워크 금지 재생·앱 페이지/필터/이전 초안 보존을 확인했다. 기존7장 초안은 새 근거로 재생성하지 않았다.

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
연구 자료 추출과 골든 샘플 분석은 모두 현재의 Parse 기반 경로를 사용한다.
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

- `paper_draft_agent.py`: 공통 가이드 로더, 두 근거 수집 모드와 계획 기반 작성을 연결하는 진입점, CLI.
- `archive/manual-evidence/research_evidence.json`: 과거 수작업 검토 기록. 현재 초안의 연구 근거로 사용하지 않는다.
- `streamlit_app.py`: 입력 선택, 진행 상황, 초안 보기, Markdown/TXT 다운로드.
- 루트의 `paper_draft_full.*`, `paper_draft_sections.json`, `paper_draft_review*.json`: 보존한 과거 고정 구성의 산출물. 현재 앱은 자동으로 불러오거나 갱신하지 않는다.
- `archive/legacy-drafts/paper_draft_section4_5.md`: 기존 4·5장 초안. 새 생성에서 갱신하지 않는다.

현재 앱은 `draft_history/planned/latest.json`의 검증된 계획 기반 초안을 불러온다.
현재 작성·검토 정책에 따른 완료 조건을 만족한 뒤 마지막 초안 위치를 갱신한다.
연구 자료에 없는 정보는 `[확인 필요: ...]`로 표시하도록 지시한다.
검토는 LLM 판단과 본문·근거 ID·구성 검사를 조합한다. 모든 사실을 자동 증명하거나
독립 재실험하는 체계는 아니며, 저자가 측정 조건·수치 정확성·연구 주장을 최종 확인해야 한다.
초록과 참고문헌은 현재 생성 범위에 포함하지 않는다.

## API 호출 없는 회귀 검사

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

외부 호출을 대체하여 두 근거 수집 모드, 자료별 계획·소절 작성·편집·검토,
캐시 재개와 실패 시 기존 초안 보존을 검증한다.
