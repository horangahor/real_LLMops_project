# 수정한 Studio 워크플로우의 골든 PDF 검증

## 결론

등록된 구조 분석 Studio Agent를 실제로 실행했다. Parse → `Instruct - paper_structure_profile` → `Instruct - paper_style_checklist`의 세 단계가 모두 완료되었다. 파서 원본에는 실제 목차 제목 텍스트 14개가 모두 존재한다.

구조 분석은 상위 장 5개와 방법 파트 하위 절 3.1~3.5의 번호·제목을 정확히 나열한다. 결과 파트는 RQ1~RQ3와 Limitations를 설명하지만 4.1~4.4의 실제 번호·제목을 나열하지 않는다. 따라서 내용을 전혀 읽지 못한 것은 아니지만, 완전한 상세 목차를 출력하는 기준으로는 네 항목이 빠져 있다.

## 어떤 설정을 실행했는가

- 문서: `AIComps2026_NPU_Benchmarking_1.1v.pdf`, 14페이지. 이전 평가와 같은 원본 SHA-256을 확인했다.
- Agent: 로컬 `STRUCTURE_AGENT_ID`로 등록된 Agent. 응답의 Agent가 설정과 일치함을 확인했다.
- 설정 선택: `config_id`를 생략했다. 공식 Create Job API에 따르면 생략 시 최신 설정 버전을 사용한다. 문서: https://console.upstage.ai/api/agents/jobs/create-job
- 로컬 `STRUCTURE_CONFIG_ID=1`은 이 검증에 사용하지 않았다. 환경 파일은 변경하지 않았다.
- 응답에는 실제 설정 버전 번호가 없어 버전 숫자나 Studio 편집 화면의 미저장 Draft 반영 여부를 독립 확인하지 못했다. 정확한 특정 버전 비교가 필요하면 Studio의 Use via API에서 저장된 Config ID를 확인해야 한다.
- 별도의 본문 분석 프롬프트를 추가로 전송하지 않았다. 사용자 파일만 Studio Agent에 전달했다.
- 폴링 약 96초 후 완료되었다. 전체 단계 결과와 사용량은 `npu-studio-run-metadata.json` 및 로컬 원본 응답에 기록했다.
- 평가 실행만 Studio 경로를 사용했다. 일반 서비스의 직접 API 분석 함수나 현재 입력 프로파일을 이 결과로 교체하지 않았다.

## 점수

| 항목 | 결과 |
|---|---:|
| 원문 번호 목차 | 14개 |
| Studio가 명시한 번호·제목 | 10개 |
| 정확한 번호·제목 | 10개 |
| 명시 목차 정밀도 | 100.0% (10/10) |
| 명시 목차 재현율 | 71.4% (10/14) |
| 명시 목차 F1 | 83.3% |
| 원문 상위 장 번호·제목 반영 | 100.0% (5/5) |
| 원문 하위 절 번호·제목 반영 | 55.6% (5/9) |
| 명시 번호로 복원한 계층 정확도 | 100.0% (10/10) |
| 구조화된 역할·페이지 라벨 정확도 | N/A: 해당 필드 없음 |

추출된 번호가 맞는다고 Studio가 계층 JSON을 직접 반환한 것은 아니다. 평가 코드가 응답에 실제 적힌 번호에서 부모 관계를 복원했다.

## 상세 목차로 제공하지 않은 항목

1. 4.1 RQ1: Do vendor-guided optimizations improve both latency and accuracy?
2. 4.2 RQ2: Does NPU-only performance predict end-to-end performance?
3. 4.3 RQ3: How much additional benefit comes from vendor-guided deployment?
4. 4.4 Limitations

Studio 응답에는 “결과 파트인 Section 4는 RQ1, RQ2, RQ3 중심으로 하위 절을 구성하고 마지막에 Limitations를 둡니다”라는 요약이 있다. 의미적으로 관련 구조를 인식한 흔적은 있지만, 번호와 정확한 제목의 상세 목록으로는 부족하다.

## 출력 형식

구조 분석과 작성 체크리스트는 각각 JSON 문자열로 감싼 Markdown이다. `observed_outline`, `children`, `role`, `source_pages`가 있는 객체는 반환하지 않았다. 따라서 JSON으로 디코딩된다는 사실만으로 서비스 프로파일 스키마에 맞는 결과라고 볼 수 없다.

- 원본 구조 분석: `../predictions/npu-studio-structure.md`
- 원본 작성 체크리스트: `../predictions/npu-studio-style.md`
- 평가용 번호 목차 트리: `npu-studio-derived-outline.json`
- 항목별 점수: `npu-studio.json` / `npu-studio.md`

다른 LLM을 이용해 Studio 응답을 보완하거나, 원문 기준표에서 빠진 목차를 채우지 않았다. 평가용 트리의 역할 `other`는 코드의 자리표시자일 뿐이며, 역할 평가에는 사용하지 않았다.

## 해석 한계와 다음 변경 위치

한 문서·한 번의 실행이고, 기준표는 Codex가 원문을 대조해 작성한 초기 자료로 독립 검수 전이다. 이전 87.5%는 직접 Document Parse/Solar 경로의 구조 객체 점수이며 이번 83.3%와 출력 계약·워크플로우가 다르다. 이를 같은 조건에서 Studio 변경 전후 성능이 떨어진 결과로 해석하면 안 된다.

현재 문제는 파서가 문서 내용을 통째로 읽지 못한 것이 아니라, 구조 분석 단계에서 상세 목차를 요약하는 출력 방식이다. Studio의 `paper_structure_profile` Instruct 지침에 모든 실제 장·절 번호와 원문 제목을 계층 객체로 반환하도록 지정하는 것이 다음 개선 후보이며, 이번 검증에서는 그 지침을 수정하지 않았다.
