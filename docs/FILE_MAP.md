# 파일 역할과 정리 기준

기본 실행은 `streamlit_app.py` → `PaperDraftOrchestrator`의 adaptive 경로 → `PlannedPaper` → 자동 근거 추출 → 자료별 계획·작성·검토다.

| 위치 | 역할 |
|---|---|
| `research_extract_v3.py` | 페이지별 누락 보완, 원문 검토, 최종 요소별 수집 대장과 미해결 복구 |
| `research_extract_v2.py` | v3가 재사용하는 1차 근거 수집. 현재도 사용한다. |
| `research_extract.py` | 공통 유형·보고서 렌더링과 이전 v1 재생. 현재도 참조한다. |
| `research_sources_v3.py` | PDF의 실제 이미지·텍스트와 Parse 출처 대조, 누락 이미지 판독·원본 응답 보관 |
| `research_sources.py`, `document_parse.py` | 기본 Parse·빈 영역 재판독·API 캐시, JSON 원자 저장·잠금 재시도·실패 임시 파일 보존 |
| `research_values.py` | 문장·조건·설정의 수치 검사와 표기 정규화 |
| `research_coverage.py` | 실제 구조화 필드에 원문 식별자·시간 지표가 남았는지 추가 검사 |
| `requirement_extraction.py`, `docs/A_MODE_STABILITY.md` | A 모드 질문 기반 근거 수집·페이지별 체크포인트·원문 검토·질문 충족 판단과 재개 |
| `planned_paper.py`, `paper_plan.py` | 원문 입력, 작성 계획·근거 연결, 초안 실행과 저장 |
| `planning_wire.py` | 계획 응답의 장별 근거 목록 중복 출력 생략, 코드 합산용 복원과 기존 완료 계획 캐시 재사용 |
| `hierarchical_drafting.py` | 소절 작성·검토, 장별 1차 편집·검토, 전체 2차 편집·검토와 단계별 재개 |
| `writing_length.py` | 전체 본문 목표를 절 역할·소절 수에 배분하고 분할 작성 요청들이 같은 소절 예산을 나눠 쓰도록 구성 |
| `writing_policy.json`, `writing_policy.py` | 수기로 관리하는 공통 계획·작성·편집 지침, 분량 초과를 기존 수정 기회에 연결하고 규칙별 실행 캐시 분리 |
| `publication_tables.py`, `paper_display.py` | 표별 독립 해석 문단 연결·중복 배치 보류·내부 ID 제목 차단과 코드·수식·URL 의미를 보존하는 Markdown 표기 |
| `publication_table_views.py` | 원자료를 보존한 출판용 표 사본, 반복 병합 제목 정리·원시 트레이스 보류·해석용 주석 분류와 감사 기록 |
| `draft_prose.py` | 문단별 본문·근거 ID 필수 출력 스키마, 소절 범위 검사와 인용 표시 조립 |
| `paragraph_revision.py` | 지정 문단의 1:1 교체 스키마·수정 지적 범위·분량 검사, 증식 응답 보정과 원문 보존 |
| `prose_format_repair.py` | 한 객체에 합쳐진 여러 문단의 본문을 보존하고 기존 형식 보정 기회에서 문단별 근거 목록만 반환받아 연결 |
| `draft_diagnostics.py` | 검토 실패를 필수 항목·실제 문단·근거 내용·임시 승인·원문 위치로 추적하고 전체 진단 보고서 저장 |
| `table_placement.py` | 중복 배정 표의 배치 장 선택·검증·변경 사유 저장 |
| `review_response.py` | 소절 검토 JSON·ID 검사, 동일 응답 중복 제거와 잘못된 응답 형식 보정 |
| `content_review_completion.py` | 소절 내용 보완 2회 후 남은 지적을 경고로 보존하고 충족률·원래 검토 판정을 유지 |
| `editorial_review.py` | 근거 입력 없이 절·전체 편집의 중복·연결·용어·문체를 검토하고 하위 내용 검토 기록을 승계 |
| `editorial_recheck.py` | 편집 재검토의 본문·지적 묶음 구성, 이전 초안 인용문 중복 제거·원래 기록 보존과 배정 검증 |
| `editorial_revision.py` | 구간별 인용 연결, 기존 최초 편집 캐시 검증·재생, 신규 최초 편집·보완 호출 연결과 본문 변경 감지 |
| `editorial_patch.py` | 최초 편집·보완 시 전체 본문을 읽히고 고정 구간 칸의 유지·수정·삭제만 반환받아 위치·인용 적용 |
| `editorial_input.py` | 편집 요청 실제 바이트 상한 검사, 전체 문맥 유지와 보정 입력의 실패 응답 본문 중복 제거 |
| `drafting_budget.py`, `bounded_drafting.py`, `bounded_review.py` | 작성 요청 원문 중복 제거·입력 예산 검사·분할 작성·승인 근거 사용과 필수 내용 검토 |
| `paper_context.py`, `docs/WRITING_INPUT_CONTEXT.md` | 3번 작업: 명시적인 계획 배정으로 장·소절별 근거·지침 입력 생성과 배정 기록 |
| `evaluation/writing/run_chapter_pilot.py`, `docs/CHAPTER_PILOT_REVIEW.md`, `evaluation/writing/pilots/20261031-results/` | CUDA 근거 4개로 결과 장 1개를 생성·진단 검토한 실패 사례와 추가 검사 우선순위. 서비스 초안과 분리 |
| `docs/NPU_WRITING_RUBRIC.md`, `evaluation/writing/npu-rubric.v1.json` | NPU 논문 단독의 작성·평가 기준표와 기계 판독용 명세. 실행기 연결 전 설계안 |
| `docs/WRITING_REVIEW_RESPONSIBILITIES.md`, `evaluation/writing/npu-review-responsibilities.v1.json` | 2번 작업: 기존 33개 기준의 코드·에이전트 검사 책임과 판정 경계. 입력 문맥 구성·생성 흐름은 미변경 |
| `paper_draft_agent.py` | 공통 가이드 로더와 계획 기반 작성·두 근거 수집 모드의 앱 진입점 |
| `paper_structure*`, `structure_*`, `paper_outline.py` | 참고 논문의 구조·작성 가이드 추출과 표시 |
| `*evaluation.py`, `evaluation/`, `tests/` | 평가·회귀 검사. 고정 예측·정답·코드 스냅샷은 재현에 필요하다. |
| `input/` | 연구 원본 PDF |
| `golden sample/`, `paper_structure_analysis.json` | 참고 논문과 구성 가이드. 연구 사실의 출처로 사용하지 않는다. |
| `draft_history/` | 입력별 원본 Parse·모델 응답·초안·평가 재생 캐시. 진행 중 작업과 재생이 사용한다. |
| `workspace_cache.py`, `cache-snapshot.json`, `docs/CACHE_RESUME.md` | 전체 중간 결과의 Git 스냅샷·바이트 검증, 다른 PC에서 절대 경로 이관과 기존 캐시 식별자 유지 |
| 루트의 `paper_draft_full.*`, `paper_draft_sections.json`, `paper_draft_review.json` | 보존한 과거 비교 초안·검토 산출물. 현재 앱은 자동으로 불러오지 않는다. |
| `Results & Discussion.json` | 보존한 과거 비교 모드의 입력·산출물. 현재 작성 입력으로 읽지 않는다. |
| `archive/` | 기본 자동 추출이 읽지 않는 과거 수작업 기록과 초기 4·5장 초안 |

버전 번호가 붙은 추출 파일도 현재 경로에서 재사용하므로 이름만 보고 삭제하지 않는다. 생성된 `__pycache__`는 재생성 가능한 캐시다. `.env`는 로컬 설정이며 보관 폴더나 공유 산출물에 복사하지 않는다.

CUDA 고정 구성의 전용 `paper_content.py`, `paper_prompts.py`, `paper_quality.py`, `method_result.py`와 전용 테스트는 제거했다. `paper_draft_agent.py`의 고정 작성자·검토자·종합 편집자도 제거했다. `evaluation/` 아래 고정 코드 스냅샷은 과거 평가의 해시·비교 기록이므로 그대로 보존한다. `projects/cuda.json`은 현재 작성 경로의 원본 PDF 위치·프로젝트 정책이며 고정 목차 작성 구현이 아니다.

이동한 파일의 원래 경로·보관 경로·내용 해시는 `archive/manifest.json`에서 확인할 수 있다.
