# 다른 컴퓨터에서 이어가기 · 2026-10-30

## 현재까지의 상태

프로젝트는 CUDA 연구 자료로 1·3·4·5·6장 초안을 작성하고 2장 관련 연구는 비워두는 Streamlit 서비스다. 작성·검토·종합 흐름은 일반 Python 코드로 제어한다. LangGraph 전환은 아직 하지 않았다.

초안의 내용 품질과 서비스 일반화를 개선하기 전에 정량 평가 기준을 마련하라는 멘토링을 받았다. 골든 샘플 구조는 우선 한 편을 기준으로 고정하는 방향이며, 현재는 후보 두 편 각각의 추출 품질을 확인하고 있다. 서비스가 읽는 기존 `paper_structure_analysis.json`은 아직 두 개의 legacy 프로파일이며 최신 Studio 결과로 교체하지 않았다.

## 가장 먼저 재개할 작업

**두 번째 골든 PDF `research_revies.pdf`를 같은 Studio Agent의 Config 4로 실행하고 평가한다. 아직 실제 실행하지 않았다.**

- Agent: `agt_ZodDrwGVgFVrFBh6W8UiSY`
- Config ID: **4를 명시**한다. 버전을 생략했을 때 이전과 동일한 결과가 반환되어, 이후 검증에서는 사용자에게 받은 버전을 직접 지정했다.
- 사용자가 이 대화에서 두 번째 PDF 원본과 추출 본문을 Upstage로 전송해 실행·평가하는 데 명시적으로 동의했다. 직후 기기 전환을 위한 커밋·푸시를 요청하여 실행은 보류했다. 새 컴퓨터에서는 이 동의와 현재 요청의 범위를 대화 기록과 함께 확인한다.
- 원문 기준표: `evaluation/golden/rgbd-reference.json` / `.md`. 원문의 본문 번호 목차는 **23개**다. 3단계 절과 16페이지 중 실제 시작 페이지를 확인했다.
- 기준표는 Codex가 원문 텍스트·페이지 이미지와 대조해 작성했으며 사용자·전문가 독립 검수 전이다. 평가 기준표를 Studio 입력으로 보내거나 생성 결과에 누락 목차를 채워 넣지 않는다.

명령은 아래 새 컴퓨터 설정 후 프로젝트 폴더에서 실행한다. 이 명령은 PDF를 외부 Upstage 서비스로 전송하고 실제 Agent 작업을 생성한다.

```powershell
.\.venv\Scripts\python.exe -X utf8 -B evaluation/golden/run_studio_validation.py --reference evaluation/golden/rgbd-reference.json --config-id 4 --run-dir draft_history/rgbd-config4
```

PDF를 다른 위치에 뒀다면 `--pdf "절대경로\research_revies.pdf"`를 추가한다. 기존 실행 폴더에 상태가 있으면 같은 작업을 이어서 조회하므로, 별도 새 실행은 새로운 `--run-dir`로 구분한다. 기본 원본 해시가 다르면 업로드 전에 중단한다. Studio 지침·서비스 입력 파일·환경 파일을 이 실행으로 수정하지 않는다.

## 새 컴퓨터 설정

검증한 Python 버전은 **3.13.9**다. 저장소를 복제하거나 갱신한 후 프로젝트 폴더에서:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

이미 `.env`가 있다면 위 복사 명령으로 덮어쓰지 말고 기존 파일을 사용한다. `.env`에 API 키를 입력한다. 기존 컴퓨터의 `.env`를 개인적으로 복사해도 되며 GitHub에는 올리지 않는다. Studio 검증 명령은 기본 Config 4 또는 `--config-id`를 사용한다. 실제 예전 `.env`의 Config 값이 1이어도 이번 실행 명령의 4가 우선이다.

## 별도로 옮겨야 하는 파일

PDF 원본은 현재 Git 저장소에 포함되어 있지 않다. 기본 경로는 **프로젝트 폴더의 상위 폴더**다.

```text
작업폴더/
├─ real_LLMops_project/                 # 복제한 저장소
├─ research_revies.pdf
├─ AIComps2026_NPU_Benchmarking_1.1v.pdf
└─ GPU 프로그래밍의 핵심_ CUDA로 배우는 병렬 처리 기술.pdf
```

- 두 번째 골든 평가에는 `research_revies.pdf`가 필요하다.
- NPU 재평가에는 NPU PDF가 필요하다.
- 현재 CUDA 근거 프로파일로 새 초안을 생성할 때는 CUDA 원본 PDF도 필요하다. 기존 PDF의 해시를 검사한다.
- `.env`, `.venv`, `.venv.zip`, `draft_history/` 전체 응답·실행 로그는 Git에 없다. 과거 원본 응답을 그대로 확인하려면 `draft_history/`도 별도로 개인 복사한다. 새 평가 실행에는 과거 작업 ID가 필요하지 않다.

앱과 로컬 테스트:

```powershell
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py
.\.venv\Scripts\python.exe -X utf8 -B -m unittest discover -s tests
```

## 완료한 평가

`evaluation/golden/README.md`와 각 결과 문서를 참조한다.

| 대상 | 상태 |
|---|---|
| NPU의 기존 legacy 저장 분석 | 목차 제목·번호 F1 40% |
| NPU의 직접 Document Parse/Solar 재실행 | F1 87.5%, 원문에 없는 소제목 4개 추가 |
| NPU의 이전 Studio 서술형 응답 | 명시적 목차 F1 83.3%, 4.1~4.4 번호·제목 미제공 |
| NPU Studio Config 2 | 목차 14/14 정확. 최종 JSON 내부 줄바꿈 문법 오류 |
| NPU Studio Config 3 | 마지막 paper_evidence_review에서 model_request_error 재현 |
| NPU Studio Config 4 | 네 단계 완료. 목차 제목·번호·부모·계층·페이지 모두 14/14. 최종 객체는 정상이나 뒤의 인용 표시 37개 때문에 응답 전체 json.loads는 Extra data |
| RGBD 연구 논문 Config 4 | 원문 기준표 23개 준비 완료. 실행·결과 평가는 아직 전 |

위 값은 각 문서·실행에 대한 결과다. 모든 논문에서의 정확도나 초안 작성 품질 점수로 일반화하지 않는다. 역할 라벨이 출력에 없으면 N/A로 기록한다.

목차 평가기 버전은 `golden-outline-v3`다. 처음부터 본문 번호 목차만 평가하고 초록·키워드·부속 항목은 제외했다. 제목의 줄바꿈·공백을 정규화하고, 누락·추가·번호·부모 관계를 별도로 본다. 비교 대상의 원문 해시와 기준표 해시를 기록한다.

## 저장된 Studio JSON 평가 방법

실행 폴더에 구조·스타일·최종 검토의 본문과 API 원본 응답이 남는다. 새 응답을 다른 LLM으로 보완하지 않고 아래 도구로 읽는다.

- `studio_json_evaluation.decode_document()`: JSON 또는 전송 계층에 감싼 JSON 문자열을 읽는다.
- `diagnostic_citations=True`: 마지막에 등록된 형태의 인용 표시만 붙은 경우 첫 JSON 객체를 진단용으로 분리한다. 원본 전체 strict_valid=false와 객체 자체 정상 여부를 구분한다.
- `diagnostic_controls=True`: 이전 실패 원인의 진단 옵션이다. 느슨하게 읽었다고 원본 JSON이 정상인 것으로 판정하지 않는다.
- `studio_json_evaluation.explicit_outline()`: 실제 parent ID와 원본 page/evidence 링크만 사용한다. 정답표로 누락을 보완하지 않는다.
- `golden_evaluation.evaluate_outline()`: 준비된 기준표로 목차를 채점한다. Studio 출력에 역할 라벨이 없으므로 기술적 자리표시자 `other`를 진짜 역할로 채점하지 않는다. 역할과 역할 포함 완전 일치 지표는 N/A로 구분한다.

NPU Config 4의 원문 인용 37개는 지정 페이지에 정규화된 문자열 조각이 존재하는지도 확인했다. 이는 인용에서 도출한 해석 전체를 검증한 점수가 아니다.

## 아직 반영하지 않은 변경

- 일반 골든 분석 경로 `paper_structure.py`는 여전히 Document Parse와 Solar를 직접 호출한다. Studio 수정 사항이 일반 앱에 자동 연결되지는 않는다. 이번 Studio 평가는 별도 Files/Jobs API 실행이다.
- Studio의 최신 결과를 현재 서비스의 schema_version 2 작성 가이드로 연결하는 작업은 미완료다.
- 인용 접미부 분리 기능은 평가 도구에만 있으며 일반 생성 파이프라인에는 아직 연결하지 않았다.
- `research_evidence.json`은 Codex가 CUDA PDF와 대조해 정리한 보조 자료다. 전문가가 독립 검증한 정답이 아니다. 작성·검토·종합과 장별 입력/결과표에 의존성이 있다.
- 사용자가 **이 수작업 근거 프로파일 없이 사용하는 구조로 개선한 뒤 실제 초안을 비교하는 과제는 나중에 하자**고 했다. 지금 바로 제거하지 않는다.
- 현재 5·1·6장 재작성은 중복을 검사해 조건부로 수행하는 것이 아니라 해당 CUDA 경로에서 항상 수행된다. 최초 작성과 같은 지침을 사용하고 Reviewer 지적을 직접 받지 않는다. 필요성은 비교 실험으로 확인하지 않았다.
- LangGraph, FastAPI, SSE, ChromaDB, Docker는 미구현이다.

## 그림

`docs/diagrams/`에 현재 구조의 PNG와 SVG를 보관했다. 2026-10-29 Python 실행 흐름 기준이며 아직 LangGraph 구조가 아니다.

## Git에서 제외한 것

환경 파일·API 키·가상환경·전체 문서 응답·과거 실패 후보는 이 기기 전환 커밋에 넣지 않았다. 기존에 추적되고 있던 pyc 캐시의 수정도 새로 커밋하지 않았다. 코드·평가 도구·평가 결과·새 PC 설정·그림과 이 메모가 작업 재개의 기준이다.
