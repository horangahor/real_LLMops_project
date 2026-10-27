# CUDA 연구 논문 초안 작성기

CUDA 연구 자료와 참고 논문의 구조·문체 분석을 바탕으로 **1·3·4·5·6장**을 작성하고,
종합 편집을 거쳐 전체 논문 초안을 저장하는 Streamlit 서비스다.
**2장 관련 연구는 제목만 표시하고 본문은 비워둔다.**

## 논문 구성

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
생성은 장별 5회 → 검토 → 종합 편집 → 재검토로 기본 8회의 Solar API 호출을 사용한다.
주요 오류가 남으면 종합 편집과 검토를 한 번 더 수행한다(최대 10회).

## Orchestrator–worker 흐름

```text
연구 PDF → method_result.py (Studio Agent) → 연구 사실 JSON
참고 논문 → paper_structure.py (Document Parse + Solar) → 구조·문체 프로파일
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

기본 실행은 저장된 `Results & Discussion.json`과 `paper_structure_analysis.json`을
읽는다. 참고 스타일을 새로 분석하려면 `paper_structure.py`를 별도로 실행한다.
CUDA 연구 PDF를 업로드하면 기존 연구 JSON의 존재 여부와 관계없이 Studio Agent로
다시 추출한다. 현재 추출기는 결과를 `Results & Discussion.json`에 저장한다.
연구 데이터와 별개로 참고 논문은 문체와 구조만 제공한다.

## 원문 근거 및 품질 검토

`research_evidence.json`은 현재 CUDA 연구 PDF의 본문과 일부 로그·표를 대조한
초안 작성용 근거 12개를 담는다. 각 근거에는 페이지, 관측 내용, 해석 한계가 있다.
추출 JSON과 원본 PDF의 SHA-256이 모두 일치할 때만 이 프로파일을 사용한다.
결론에는 핵심 주장, 문단별 역할, 선택할 대표 근거를 `section_briefs`로 지정한다.
결론이 모든 중간 실험 수치를 되풀이하지 않도록 대표 성과만 선택하게 하고,
문단 구성·분량·수치 나열도 검사한다. 이 프로파일은 현재 연구 자료에 맞춰 검토한 설정이다.
결론은 1,000~2,500자를 권장하고 최대 3,000자까지 허용한다. 서로 다른 성능 수치는
10개 이내를 권장하며, 개수 초과는 경고로만 기록하고 저장을 막지 않는다.
분량·수치 기준은 작성·검토·종합 프롬프트와 코드 검사에서 같은 기준을 사용한다.
메시지는 실제 개수·글자 수를 표시하며, 내용의 반복 여부를 판정한 것은 아니다.
근거 없는 수치와 잘못된 비교는 수치 개수와 관계없이 오류로 검사한다.
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

- `paper_draft_agent.py`: 장별 worker, 종합 worker, orchestrator, CLI.
- `paper_prompts.py`: 장별 역할과 근거 사용 지침.
- `paper_quality.py`: 검토 근거 선택, 원문/추출물 일치 검사, 알려진 오류 검사.
- `research_evidence.json`: 원문 페이지에 연결된 검토 근거와 해석 한계.
- `streamlit_app.py`: 입력 선택, 진행 상황, 초안 보기, Markdown/TXT 다운로드.
- `paper_draft_full.md`, `paper_draft_full.txt`: 새로 생성하는 전체 초안.
- `paper_draft_sections.json`: 종합 전 장별 초안과 종합 후 장별 본문.
- `paper_draft_review.json`: 검토 지적, 수정 후 검토 결과, 사용한 근거 출처.
- `paper_draft_candidate.md`, `paper_draft_review_failed.json`: 검토 미통과 시 후보와 지적.
- `paper_draft_section4_5.md`: 기존 4·5장 초안. 새 생성에서 갱신하지 않는다.

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
