# 파일 역할과 정리 기준

기본 실행은 `streamlit_app.py` → `PaperDraftOrchestrator`의 adaptive 경로 → `PlannedPaper` → 자동 근거 추출 → 자료별 계획·작성·검토다.

| 위치 | 역할 |
|---|---|
| `research_extract_v3.py` | 페이지별 누락 보완, 원문 검토, 최종 요소별 수집 대장과 미해결 복구 |
| `research_extract_v2.py` | v3가 재사용하는 1차 근거 수집. 현재도 사용한다. |
| `research_extract.py` | 공통 유형·보고서 렌더링과 이전 v1 재생. 현재도 참조한다. |
| `research_sources_v3.py` | PDF의 실제 이미지·텍스트와 Parse 출처 대조, 누락 이미지 판독·원본 응답 보관 |
| `research_sources.py`, `document_parse.py` | 기본 Parse·빈 영역 재판독·해시가 연결된 API 캐시 |
| `research_values.py` | 문장·조건·설정의 수치 검사와 표기 정규화 |
| `research_coverage.py` | 실제 구조화 필드에 원문 식별자·시간 지표가 남았는지 추가 검사 |
| `planned_paper.py`, `paper_plan.py` | 원문 입력, 작성 계획·근거 연결, 본문 작성과 검토 |
| `docs/NPU_WRITING_RUBRIC.md`, `evaluation/writing/npu-rubric.v1.json` | NPU 논문 단독의 작성·평가 기준표와 기계 판독용 명세. 실행기 연결 전 설계안 |
| `paper_draft_agent.py`, `paper_content.py`, `paper_prompts.py`, `paper_quality.py` | 앱 진입점과 기존 비교 모드·작성 품질 검사 |
| `paper_structure*`, `structure_*`, `paper_outline.py` | 참고 논문의 구조·작성 가이드 추출과 표시 |
| `*evaluation.py`, `evaluation/`, `tests/` | 평가·회귀 검사. 고정 예측·정답·코드 스냅샷은 재현에 필요하다. |
| `input/` | 연구 원본 PDF |
| `golden sample/`, `paper_structure_analysis.json` | 참고 논문과 구성 가이드. 연구 사실의 출처로 사용하지 않는다. |
| `draft_history/` | 입력별 원본 Parse·모델 응답·초안·평가 재생 캐시. 진행 중 작업과 재생이 사용한다. |
| 루트의 `paper_draft_full.*`, `paper_draft_sections.json`, `paper_draft_review.json` | 기존 비교 모드가 읽거나 저장하는 초안·검토 산출물 |
| `Results & Discussion.json` | 명시적으로 선택하는 기존 비교 모드의 입력·산출물 |
| `archive/` | 기본 자동 추출이 읽지 않는 과거 수작업 기록과 초기 4·5장 초안 |

버전 번호가 붙은 추출 파일도 현재 경로에서 재사용하므로 이름만 보고 삭제하지 않는다. 생성된 `__pycache__`는 재생성 가능한 캐시다. `.env`는 로컬 설정이며 보관 폴더나 공유 산출물에 복사하지 않는다.

이동한 파일의 원래 경로·보관 경로·내용 해시는 `archive/manifest.json`에서 확인할 수 있다.
