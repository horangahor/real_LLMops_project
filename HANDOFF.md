# 다른 컴퓨터에서 이어가기 · 2026-10-31

## 최신 인수인계: v3 복구·속도 개선과 NPU 작성 기준표

아래 과거 기록보다 이 절을 우선한다. 사용자는 **NPU 논문 한 편을 골든 샘플로 삼아 초안을 작성**하기로 했다. 다음 작업의 중심은 연구일지 전체를 반복 감사하는 것이 아니라, 골든 기준과 코드/에이전트 검증을 연결하고 장·절 단위로 문맥을 줄이는 것이다.

### 이번에 완료한 작업

- v3 누락 감사의 잘못된 인덱스를 별도 요청으로 한 번 보정한다. 계속 실패하면 원래 응답을 보존하고 해당 페이지 후보를 격리·보류한다.
- 빈/불완전 JSON 응답은 완료 캐시로 인정하지 않는다. 수치 보정 묶음은 분할하고, 단일 후보도 실패하면 수치 검증 보류로 보존한다. 최종 검사·누락 복구의 실패가 전체 결과 저장을 막지 않게 했다. 복구 후보의 잘못된 출처 ID도 원형과 오류를 격리한다.
- Windows 긴 경로를 파일 저장·캐시 읽기에서 처리한다. PC의 LongPathsEnabled 레지스트리는 변경하지 않았다.
- 자동 누락 복구는 `RESEARCH_MAX_RECOVERY_ROUNDS=1`이 기본이다. 0~5를 허용하며 5는 이전 정밀 감사 수준이다. 1회 제한으로 미해결 항목이 늘 수 있으며 이를 통과 처리하지 않는다.
- 재검사는 미해결 원문 요소만 요청하고, 완료된 최종 페이지 결과는 입력·지침·설정 해시가 일치할 때 재사용한다. 옛 결과는 완료 대장 파일만 믿지 않고 정확한 요청 캐시를 네트워크 없이 재생해 연결한다.
- 초안 생성 경로에도 근거 추출 진행 콜백을 연결했다. 앱의 오류 문구를 작업 종류에 맞게 나누고 **저장된 연구 근거 불러오기**를 추가했다.
- 골든 JSON의 required_content를 코드로 식별하고 계획 required_items의 `guideline_ids`에 연결한다. 작성/검토 입력과 review.json까지 연결을 유지하며 잘못된 가이드 연결은 코드로 차단한다. 추가 모델 호출 단계는 없다.
- `docs/NPU_WRITING_RUBRIC.md`와 `evaluation/writing/npu-rubric.v1.json`: NPU 원문 14개 장·절에 대응하는 기준 25개 + 공통 검증 8개 = 33개. 출처·조건부 적용·통과 조건·검사 담당·최소 문맥·미달 처리를 기록했다.
- 전체 자동 코드 테스트 **201개 통과**. 논문 품질 평가 201개가 아니며 이번 실제 초안의 품질을 입증하지 않는다.

### 실제 v3 결과와 남은 품질 문제

- 최종 실행: `draft_history/parse-api-v1/GPU 프로그래밍의 핵심_ CUDA로 배우는 병렬 처리 기술-22e2a29d284f-bb82aeee/research-evidence-v3/df0f048d3ef4282d/`.
- 외부 API를 차단하고 기존 캐시만 재생해 84쪽의 결과 저장까지 마쳤다. 후보 1,990개, 작성 입력 선택 1,619개, 미해결 원문 항목 40개이며 `ready_for_drafting=false`다. 중복 OCR·표제가 있어 40개가 독립적인 누락 사실 40개를 뜻하지 않는다.
- 최종 근거의 이식용 스냅샷: `evaluation/extraction/v3/current/evidence.json`. SHA256은 `fe37748bd7639f298a1af5cb3aa291b64df578d0ac87b3868bca00524227ce3b`. 이 파일은 공식 42항목 전수 평가가 완료된 예측이 아니다.
- 검토 메모: `evaluation/extraction/v3/review-20261031.md`. 일부 값은 후보에만 있고 작성 입력에는 없다. 또한 P0083F0001에서 소수 쉼표 131.248s/1.613s를 131248s/1613s로 처리한 수치가 승인되어 있다. 검토 설명이 이를 지적해도 플래그가 승인인 문제가 남는다. P0084F0002에도 유사한 사례가 있다.
- 수작업 E01~E12, 표본 42개 참조의 전수 매칭은 아직 하지 않았다. “모든 내용 커버”, “v3 정확도 100%”라고 보고하지 않는다. 수작업 파일에 기록된 PDF 해시와 현재 연구 원본 PDF 해시도 다르다.
- 사용자 확인 없이 `ready_for_drafting` 게이트를 풀거나 수치를 추측해서 수정하지 않는다.

### 다른 PC에서 실행

Python 3.11 이상을 사용한다. 이번 PC의 테스트 환경은 Python 3.13.9다. `.venv`는 PC별로 새로 만들고 기존 압축 가상환경을 재사용하지 않는다.

```powershell
git pull --ff-only origin master
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# .env가 없을 때만 예제를 복사하고 UPSTAGE_API_KEY를 별도로 입력한다.
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -B -m unittest discover -s tests
.\.venv\Scripts\python.exe -B -m streamlit run streamlit_app.py
```

이 명령의 `.env` 복사는 파일이 이미 있으면 생략한다. 키를 Git에 넣지 않는다. 기본 Parse·Solar 경로에는 Studio Agent ID가 필요하지 않다. requirements의 `PyMuPDF==2.0`도 설치되어야 한다.

재추출 없이 현재 결과를 앱에서 확인하려면 프로젝트 폴더에서 다음을 실행한다.

```powershell
$evidenceDir = 'draft_history/parse-api-v1/GPU 프로그래밍의 핵심_ CUDA로 배우는 병렬 처리 기술-22e2a29d284f-bb82aeee/research-evidence-v3/df0f048d3ef4282d'
New-Item -ItemType Directory -Path $evidenceDir -Force | Out-Null
Copy-Item evaluation/extraction/v3/current/evidence.json -Destination (Join-Path $evidenceDir 'evidence.json')
```

앱에서 input의 CUDA PDF를 선택하고 **저장된 연구 근거 불러오기**를 누른다. 결과 보기에는 API 호출이 없다. 스냅샷 안의 run_dir/source_archive_path/source_index_path는 원래 PC의 실행 출처 기록이며 새 PC에서 존재하는 경로라는 뜻이 아니다. 스냅샷만으로 원본 API 캐시 재생이나 source-archive 열기를 할 수는 없다.

API 응답을 재사용해 이어서 추출하려면 ignored `draft_history/` 전체를 별도로 개인 복사해야 한다. 이 커밋에는 `.env`, `.venv`, API 원본 응답, 실행 캐시 전체를 포함하지 않는다. 캐시 없이 추출 버튼을 누르면 원문을 외부 Upstage 서비스에 보내 새 호출·비용이 발생할 수 있다. 같은 추출을 동시에 두 번 실행하지 않는다.

### 다음에 할 일

1. 우선 `docs/NPU_WRITING_RUBRIC.md`를 사용자와 검토한다. NPU 단독 선택 의사를 유지한다. 현재 앱 로더에는 두 프로파일이 남아 있으므로 다음 구현에서 원본 해시로 NPU만 선택해야 한다. RGBD 지침을 새 기준표에 섞지 않는다.
2. 기준표 JSON은 `authored_not_runtime_integrated` 상태다. 기존 guideline_ids 연결과 새 33개 평가 기준 ID의 어댑터, 판정 기록·중요도별 통과 조건을 연결해야 한다. 문서를 썼다고 이미 실행 중이라고 설명하지 않는다.
3. 수치 정규화·합계/비율의 일관성 검사 및 검토 설명/승인 플래그 충돌을 코드로 보완한다. 측정 범위가 같다는 확인 없이 단순 합계나 비율만으로 값을 바꾸지 않는다.
4. 현재 초안 작성은 장별이지만 계획은 전체 근거를 받고 검토/편집은 전체 초안·근거를 반복 전달한다. 장별 코드 검사 → 장별 의미 검토 → 문제 문단만 최대 2회 수정하는 흐름으로 개선한다. 최종 연결 검토에는 목차·장 요약·핵심 주장 목록을 우선 전달한다.
5. 근거가 확인된 한 장으로 실제 작성·평가를 먼저 확인한다. 현재 미해결 결과를 정상 검증 완료로 간주해 전체 초안을 생성하지 않는다. 새 모델 호출은 자동 코드 테스트와 구분해 사용자 의도에 맞게 실행한다.

## 이전 인수인계: v3의 원문 누락 보완과 파일 정리

현재 기본 추출기는 `research_extract_v3.py`다. 아래의 v2 완료 기록은 비교 기준으로 보존한 과거 결과다. v3의 42개 참조 점수는 최종 예측을 고정하고 원문 대조하기 전에는 확정하지 않는다.

CUDA 원본 84쪽의 통합 출처는 953개 요소다. PDF 내장 이미지 122개의 실제 영역을 Parse와 비교해 누락 영역 27개를 추가 판독했고, 원본·재판독 응답 52개를 보존한다. 원문 획득 경로와 AI 조언의 귀속을 구분하고, 질문·계획·해석·원문 자체의 미정 기록은 `context_only`로 남긴다. 최종 작성 필드와 원문을 다시 대조하며 미해결 항목이 있으면 본문 생성을 막는다. 이것은 모델 보조 누락 검사이며 전체 의미 정확도 100% 보증은 아니다.

실행 폴더: `draft_history/parse-api-v1/GPU 프로그래밍의 핵심_ CUDA로 배우는 병렬 처리 기술-22e2a29d284f-bb82aeee/research-evidence-v3/33690241b8ecd551/`. 페이지 수집과 별도 원문 검토의 완료 캐시가 있고, 최종 수집 대장 검사·누락 복구를 진행 중이다. 실패·중단 시 같은 CLI로 재개하면 요청 입력과 모델 설정이 일치하는 캐시만 사용한다. 동시에 같은 추출을 두 번 실행하지 않는다.

```powershell
python -X utf8 -B planned_paper.py --extract-only --research-pdf "input/GPU 프로그래밍의 핵심_ CUDA로 배우는 병렬 처리 기술.pdf"
```

검토·복구에는 medium 추론을 명시한다. 새 대장 첫 검사는 low로 시작하고 후속 검사는 medium이다. 공급자의 빈 최종 JSON은 정상 캐시로 저장하지 않으며 제한된 재시도·별도 설정 캐시·검토 묶음 분할을 사용한다. 수치·귀속·검토가 해결되지 않은 후보를 승인하지 않는다. 그림 뒤의 명시적인 실행 모드 캡션과 진술의 forward/backward가 다르면 별도로 격리한다. 현재 회귀 테스트 175개 통과, v1/v2의 네트워크 금지 재생 통과. 기존 7장 초안과 고정한 이전 예측은 보존했다. 최종 v3 예측이 생성되면 `evaluation/extraction/v3/`의 예측·판정·protocol·코드 스냅샷을 고정하고 validate/evaluate와 실제 패키지 UI 확인을 완료해야 한다. 실행 로그는 `draft_history/evidence-evaluation/v3-run-live.log`에 저장한다. 실행 중에는 같은 CLI를 중복 실행하지 않는다.

파일 정리는 삭제 대신 보관으로 진행했다. 수작업 `research_evidence.json`은 `archive/manual-evidence/`, 초기 `paper_draft_section4_5.md`는 `archive/legacy-drafts/`로 이동했다. 원래/보관 경로와 내용 해시는 `archive/manifest.json`, 현재 사용하는 파일 설명은 `docs/FILE_MAP.md`에 있다. 생성된 루트 Python 캐시 23개도 제거했다. 보관 파일 해시와 앱의 일반/기존 CUDA 모드 초기 화면·이전 초안 보존을 네트워크 없이 확인했고 `archive/validation.json`에 기록했다. v1/v2 모듈도 v3의 1차 추출·공통 렌더링에 쓰이므로 삭제하지 않는다. `.env`와 API 실행 캐시는 이동하지 않았다.

## 현재까지의 상태

프로젝트는 연구 자료와 참고 가이드로 논문별 작성 계획·초안을 생성하는 Streamlit 서비스다. 기존 CUDA 고정 1·3·4·5·6장 작성기는 비교 모드로 보존했다. 두 경로 모두 Python 코드로 제어하며 LangGraph 전환은 아직 하지 않았다.

초안의 내용 품질과 서비스 일반화를 개선하기 전에 정량 평가 기준을 마련하라는 멘토링을 받았다. 골든 샘플 구조는 우선 한 편을 기준으로 고정하는 방향이며, 현재는 후보 두 편 각각의 추출 품질을 확인하고 있다. 서비스가 읽는 `paper_structure_analysis.json`은 직접 Parse API와 Python으로 새로 분석한 schema_version 2 프로파일 두 개다. 기존 legacy 프로파일은 `draft_history/structure-*/`에 백업했고 이전 평가 결과도 유지했다.

## 가장 최근에 완료한 작업

**자동 연구 근거 추출 기본값을 v2로 개선하고 실실행·비교했다.** `research_extract_v2.py`가4쪽+인접문맥으로 개수 제한 없이 후보를 수집한다. `research_sources.py`는 원문 영역이 빈13쪽을 enhanced Parse로 다시 읽어 별도 ID/이미지 해시/원본 응답을 남긴다. `research_values.py`가 문장·조건·관찰·설정의 수치와 과학 표기/소수 쉼표/범위/버전을 검사한다. 단일 값을 range로 오분류한 경우 원래 유형·값을 보존하며 보정하고, 잘못된 부가 측정값은 주진술과 분리한다. 별도 Solar 검토 후 작성 게이트를 적용하며 수작업 근거·골든 가이드·평가 정답은 추출 입력에 넣지 않는다. 직접 Parse+Solar 경로이며 Studio를 쓰지 않는다.

실제84쪽 CUDA 입력: 후보479개, 작성용399개, 승인 측정537개, 격리30개, 수치 검사 보류46개, 출처 연결645곳이다. 같은42개 평가 참조의 완전 보존은15→33개(35.7%→78.6%), 부분12→6개, 누락15→3개, 작성 입력의 완전 보존은3→24개다. `evaluation/extraction/v2/`에 별도 예측·코드 스냅샷·해시 protocol·항목별 매칭·보고서가 있다. v1 예측과42개 참조는 그대로다. 단독 개발 감사이며 전체479개 정확도나 새 자료 보류 평가가 아니다.

남은 문제: FP32 정확성 재검증 주의, 일부 정확한 시간·표 수치 누락, AI 조언의 작성자 해석 오분류(F0267), OCR 띄어쓰기·불필요 날짜로 인한 정상 핵심 내용 보류, EPS 반복 행·유사 후보 과다 수집. 다음 개선은 출처 성격과 문맥 연결·표별 측정 대상/조건 보존·중복 정리이며, 다른 연구 원본에서 보류 평가가 필요하다. 기존7장 초안은 보존했고 새399개 근거로 본문 생성은 아직 하지 않았다.

`python -X utf8 -B evaluation/extraction/v2/validate.py`는 실제 앱 gateway의 캐시 재생에서 네트워크·수작업/평가 파일 읽기·골든 가이드 로드를 차단하며645개 인용/페이지와 게이트·기존 산출물 보존을 검사한다. `python -X utf8 -B evaluation/extraction/v2/evaluate.py`는 해시를 검증하고 비교 점수를 API 없이 재계산한다. 테스트146개, AppTest 실제479개 목록20페이지·필터·추출 버튼·이전 초안 보존을 통과했다. 개발 중 timeout·재시도가 있어 첫시도 성공률·처리비용 비교는 측정하지 않았다. `requirements.txt`에 이미지 렌더링용PyMuPDF==2.0을 추가했다.

## 이전 작업: v1 원문 대조 평가

**연구 근거 추출 v1의 원문 대조 평가를 완료했다.** `evaluation/extraction/benchmark/`의 protocol에 PDF·예측·추출 코드 해시와 seed20261030 표본21쪽을 고정했다. 원문49쪽을 시각적으로 확인하고 후보34개·승인43/격리20개 측정 항목을 전수 대조했다. 표본의 필수 사실42개는 평가 전용 reference에 두고 항목별 판정은 annotations에 분리했다. 추출기·예측·기존 초안은 바꾸지 않았다. 평가자는 Codex1개이고 예측을 이미 본 상태여서 전문가 독립·맹검·보류 평가가 아니다.

결과는 후보 진술 문서 충실도32/34(94.1%), 선택 출처 완전성25/34(73.5%), 승인 측정 값·단위·조건41/43(95.3%), 표본 필수 사실 완전 보존15/42(35.7%;partial12,missing15)다. 이 재현율은 선정 필수 사실만의 커버리지로 전체84쪽 재현율이 아니다. 후보·참조 단위가 달라 F1은 계산하지 않았다. 작성용11개에도F16횟수오류(66→56;실제p36은94→54)와F24의CV검증강도과장이남는다. 제외20항목중13개는실제PDF에있는수치·범위이며나머지는버전·모드·정성비교다. 현재supported/검사통과를사실정확성으로보고하면안된다.

`python -X utf8 -B evaluation/extraction/benchmark/evaluate.py`로 외부 API 없이 재계산한다. 누락/중복 판정으로 분모를 축소하거나 다른 원본·예측·코드를 섞으면 실패한다. 평가 코드 테스트 포함130개 통과. 다음 개선은 원자 주장별 모든 수치 검사·출처 연결, 형식과 사실 뒷받침의 분리, 조건/실패/비교 실험의 후보 누락 감소다. 기존 수작업 근거를 되살려 점수를 맞추지 않는다.

## 이전 작업: 연구 근거 추출 독립 단계

**연구 근거 추출을 별도 실행·검토 단계로 연결했다.** `research_extract.py`가 모든 자동 추출 후보의 유형·주장 강도·원문 뒷받침·조건·측정 지표/값/단위/조건/원문 ID를 구조화한다. 작성 요약에서 선택하지 않은 후보도 보존한다. 원문에 없는 수치 표기는 `rejected_measurements`에 남기고 해당 후보를 작성 입력에서 제외한다. 가설·확인 필요·부분 뒷받침 항목도 보고서에는 남지만 작성용 사실로 승인하지 않는다. 유형·의미 판정은 LLM 보조이며 독립적 사실 검증은 아니다.

앱의 **연구 근거만 추출하기**와 CLI `--extract-only`는 골든 가이드·계획·본문 생성 없이 실행한다. `research_evidence_view.py`가 유형·주장 강도 필터, 원문 인용·페이지·측정값, JSON/Markdown 다운로드를 제공한다. 추출만 실행하면 이전 초안을 유지한다고 화면에 표시한다. 일반 작성도 이 구조화·대조 단계를 거친 근거를 받는다.

실제 CUDA 자료에서 후보 34개·원문 연결 83곳·원문 수치 표기 확인 항목 43개·확인 필요 측정 항목 20개가 나왔다. 기존 요약 선택 17개 중 현재 검사 후 작성용 사실은 11개이며, 과거 17개로 만든 초안은 갱신하지 않았다. 원문·수작업 파일 접근·네트워크·골든 가이드 로드를 검사한 재생을 통과했다. 테스트 124개 통과, 앱 추출·필터·이전 초안 보존을 확인했다. `evaluation/extraction/README.md`, `cuda-evidence.md`, `cuda-evidence.json`, `validation.json`에 기록했다. 수치는 정확도나 누락률이 아닌 처리 결과 개수다.

## 이전 작업: 수작업 근거 연결 제거

**연구 근거의 수작업 입력·자동 교체를 제거했다.** 앱·CLI·기본 API는 원본 PDF에서 근거를 자동 추출한다. `research_evidence.json`은 과거 기록으로만 보존하며 현재 실행 경로에서 읽지 않는다. 원본이 없으면 멈추고 이전 근거로 대체하지 않는다. CUDA 프로젝트도 원본 PDF 경로만 지정한다. 기본 API는 adaptive로 바꿨고 고정 목차 비교는 명시적으로 선택해야 한다. 실제 CUDA 입력에서 수작업 파일 읽기와 외부 통신을 모두 차단한 재생을 통과했다. 근거 17개·7장 초안은 동일하며 테스트 115개 통과. `evaluation/planning/automatic-evidence-validation.json`에 기록했다.

`input/` 폴더의 PDF를 앱에서 바로 선택할 수 있다. 제공된 CUDA PDF는 84쪽이며 기존 `research_evidence.json`의 원본 해시와 달라 검토 근거를 자동 재사용하지 않는다. 일반 연구 입력으로 직접 Parse API와 Solar를 실행한다. 긴 PDF는 20쪽 구간별 후보 추출 후 최대 18개를 선택하고, 모델이 고른 원문 요소 ID에서 인용문·페이지를 코드가 직접 연결한다. 원문 연결은 의미적 사실 검증이 아니며 저자 검수가 필요하다.

이 입력의 새 초안은 7개 장·근거 17개·원문 연결 39곳으로 생성했다. 앱과 같은 경로의 네트워크 금지 재생도 통과했다. 근거 없는 향후 과제 2개는 `needs_check`로 낮추고 충족률에서 제외한다. 자동 검토에는 반복·긴 서술 등의 경고 18개가 남아 있으며 독립적 품질 검증 결과가 아니다. 상세 기록은 `evaluation/planning/input-cuda-validation.md`, 초안은 `evaluation/planning/examples/cuda-input-draft.md`다. 최신 회귀 테스트 112개 통과, 앱 입력 선택·계획 버튼 연결과 두 작성 모드를 확인했다. JSON 파싱 오류는 원본 응답을 보존하고 한 번만 재시도하며 두 번째도 실패하면 정상 캐시로 저장하지 않는다.

**연구별 작성 계획 경로를 추가하고 앱 기본값으로 연결했다.** CUDA 고정 경로는 비교·기존 호출 호환용으로 보존했다.

- `paper_plan.py`: facts 정규화, 역할별 골든 가이드 목록, 논문별 장·소절·목적·필수 내용·근거·가이드 적용 방식·의존 순서 검증.
- `planned_paper.py`: 일반 연구 PDF 입력, 원문 요소에 연결된 근거 추출, 계획·작성·검토·수정·입력별 캐시와 산출물.
- `projects/generic.json`과 `projects/cuda.json`: 일반 정책과 CUDA 원본 PDF/빈 관련 연구 정책을 분리했다. CUDA 수작업 근거는 기록으로만 남기고 실행 연결은 제거했다.
- 앱은 `연구 자료에 맞춰 계획`이 기본이다. PDF 업로드, 계획 미리보기·다운로드, 마지막 정상 초안 재로드를 지원한다. 기존 CUDA 비교 모드도 선택할 수 있다.
- 새 CLI: `python -X utf8 -B planned_paper.py --research-pdf "연구자료.pdf" --plan-only`. 계획 확인 후 `--plan-only`를 빼면 작성한다.
- 기본 Python API는 `adaptive`다. 고정 목차 비교는 `planning_mode="legacy_cuda"`를 명시하며 수작업 근거로 자동 교체하지 않는다.
- 제목·번호는 코드가 조립하고 모델은 본문 칸을 채운다. 빈 칸이나 형식 오류는 제한된 횟수로 해당 부분만 수정한다.
- 검토자는 원문 인용을 다시 쓰지 않고 실제 초안 문단 ID를 선택한다. 코드가 실제 인용문을 연결하고 모든 필수 내용·선택 가이드가 검토됐는지 확인한다.
- 계획에 없는 근거·표·장, 누락/순환 의존, 인용이 없는 충족 판정을 차단한다. 과학적 사실 판정과 가이드 반영 판정은 LLM 보조이며 독립 검증이 아니다.
- 실제 실행 기록은 ignored `draft_history/planned-validation/`, 평가 기준은 `evaluation/planning/README.md`다. 추가된 `input/` CUDA PDF는 기존 검토 원본과 해시가 다르다. 현재 CUDA 프로젝트는 원본 PDF를 자동 분석하고 과거 검토 프로파일을 읽지 않는다.
- 같은 generic 코드로 NPU 6개 장·RGBD 5개 장의 초안을 실제 생성·검토했다. 원문 근거 각 18개와 다른 논문의 가이드를 교차 연결했다. 현재 코드의 네트워크 금지 재생 검증도 통과했다.
- 회귀 테스트 106개 통과, 앱 기본/기존 CUDA 두 모드 초기 화면 오류 0개. 실행 비교 보고서는 `evaluation/planning/validation.md`, 계획·초안·검토 예시는 `evaluation/planning/examples/`에 있다.
- 필수 내용 27/27·30/30과 참고 적용 판정은 LLM 보조 수치다. 전문가 검수·첫 시도 성공률·독립 보류 평가의 성능 점수로 해석하지 않는다.

## 이전 완료: 직접 Parse API 구조 분석

**2026-10-30 사용자의 요청으로 참고 논문 분석을 Studio에서 직접 Document Parse API + Python 목차 처리로 전환했다.**

- 코드: `document_parse.py`(직접 호출·원본/설정/해시·캐시), `paper_outline.py`(원문 번호·페이지·요소 ID 기반 목차), `paper_structure.py`(CLI·선택적 Solar 작성 가이드·일괄 검증·백업/저장).
- 직접 API로 두 PDF를 실행했다. 파싱 모델은 `document-parse-260930`, mode=standard, ocr=auto다. NPU 14/14, RGBD 23/23의 제목·번호·부모·시작 페이지가 일치하고 오탐·누락은 0개다.
- 원문 기준표·별칭·제외 제목은 변경하지 않았고 추출 코드에 넣지 않았다. 이전 RGBD Studio의 동일 Parse 원본을 새 코드로 재생해도 목차 F1 100%다.
- NPU에서 발생한 줄바꿈 제목, paragraph로 분류된 무점 번호 절, 제목으로 분류된 반복 페이지 머리말을 보완했다. 두 PDF는 개발 샘플이며 독립 보류 평가셋이 아니다.
- 지원 범위는 참고문헌 이전 아라비아 숫자 본문 목차다. 무번호·로마 숫자·복잡한 번호 체계는 추가 지원·평가가 필요하다.
- 목차만 분석하는 --outline-only는 Solar를 호출하지 않는다. 전체 분석에서는 Solar가 역할·문체 지침을 작성하되 코드가 정한 목차·페이지는 바꾸지 못한다. JSON Schema·원문 ID·형식·전용 영문 식별자 검사를 사용한다.
- 전용 식별자가 남은 가이드는 재사용 문장만 최대 한 번 수정하고 다시 검사한다. 남은 일부 원문 전용 표현은 Codex가 추상화했고 프로파일의 guidance_review에 전후를 기록했다. 이 검사는 문체 품질·모든 의미적 전용성의 독립 검증이 아니다.
- 기존 앱 프로파일을 새 pdf_analysis 프로파일 두 개로 교체하고 앱 로더·외부 호출 없는 캐시 재사용을 확인했다. 기존 논문 초안을 재생성한 것은 아니다.
- 결과: `evaluation/golden/results/parse-api-v1-validation.md`. 원본 및 실행·가이드 기록은 ignored `draft_history/parse-api-v1/`에 있다.
- API 없는 회귀 테스트 88개 통과. 원본 요소 연결·캐시 무통신 재사용·새 프로파일의 앱 로더 호환을 확인했다.

## 다음 재개할 작업

1. 새 논문으로 기준 목차를 먼저 확정한 뒤 보류 평가를 수행한다. 현재 두 문서의 100%를 일반화 점수로 해석하지 않는다.
2. 역할 라벨과 재사용 문체 가이드를 별도 검수한다. 목차 정확도와 가이드 충실도·초안 품질은 다른 평가다.
3. 필요에 따라 무번호·로마 숫자 목차, 합쳐진 문단, 번호가 붙은 목록, OCR 오류를 지원한다.

## 현재 경로 재현

```powershell
# Parse API + Python 목차만: 기존 원본 캐시가 있으면 외부 호출 없음
python -X utf8 -B paper_structure.py --outline-only --run-dir draft_history/parse-api-v1 --output evaluation/golden/predictions/parse-api-v1-outlines.json
python -X utf8 -B evaluation/golden/evaluate_parse_pipeline.py --profiles evaluation/golden/predictions/parse-api-v1-outlines.json
# 전체 프로파일: 문체 가이드에만 Solar 직접 호출, 같은 입력·지침이면 캐시 재사용
python -X utf8 -B paper_structure.py --run-dir draft_history/parse-api-v1
```

기본 PDF 탐색은 프로젝트의 `golden sample/`와 상위 폴더 순서다. `--mode`, `--ocr`, `--parse-model`, `--force-parse`, `--run-dir`로 조건을 명시한다. Studio Agent ID/Config ID는 이 경로에 필요하지 않다. 연구 자료 추출 `method_result.py`는 별도 Studio 경로다.

## 이전 Studio Config 4 검증 (비교 기준 보존)

**2026-10-30 두 번째 골든 PDF `research_revies.pdf`를 같은 Studio Agent의 Config 4로 실행하고 평가했다.**

- 네 단계 모두 완료했고 폴링 시간은 약 421초였다. 원문 기준표는 실행 전 확정한 23개 그대로 사용했다.
- 구조 분석: 실제 목차 23/23의 제목·번호·부모·level·시작 페이지가 일치한다. 불필요한 항목 7개가 섞여 정밀도 76.7%, 재현율 100%, F1 86.8%다.
- 최종 검토: 실제 목차 23/23은 유지했고 불필요한 항목은 6개다. 독립 목차 배열의 진단 기준 F1은 88.5%다.
- 최종 JSON은 document_title 문자열 값이 닫힌 뒤 인용 표시가 들어가 2행 166열에서 실패한다. NPU와 달리 객체 내부 문법이 깨져 단순 접미부 분리로 읽을 수 없다.
- 원본 sections 배열 39개와 evidence 배열 51개만 각각 strict JSONDecoder.raw_decode로 읽어 진단했다. 원본을 보정하거나 전체 JSON이 유효한 것으로 처리하지 않았다.
- Parse는 실제 절 2개를 paragraph로 분류했지만 구조 분석이 복원했다. 반대로 문장·수식·표 제목을 heading1로 오분류한 항목이 후속 단계에도 남았다.
- 상세 보고서: `evaluation/golden/results/rgbd-studio-config4-validation.md`. 원본 응답과 평가 스크립트: ignored `draft_history/rgbd-config4/`.

## RGBD 실행 재현

- Agent: `agt_ZodDrwGVgFVrFBh6W8UiSY`
- Config ID: **4를 명시**한다. 버전을 생략했을 때 이전과 동일한 결과가 반환되어, 이후 검증에서는 사용자에게 받은 버전을 직접 지정했다.
- 이번 실행은 사용자가 Config 4로 다른 논문을 테스트해 달라고 요청하고 API 설정을 제공한 범위에서 수행했다.
- 원문 기준표: `evaluation/golden/rgbd-reference.json` / `.md`. 원문의 본문 번호 목차는 **23개**다. 3단계 절과 16페이지 중 실제 시작 페이지를 확인했다.
- 기준표는 Codex가 원문 텍스트·페이지 이미지와 대조해 작성했으며 사용자·전문가 독립 검수 전이다. 평가 기준표를 Studio 입력으로 보내거나 생성 결과에 누락 목차를 채워 넣지 않는다.

명령은 아래 새 컴퓨터 설정 후 프로젝트 폴더에서 실행한다. 이 명령은 PDF를 외부 Upstage 서비스로 전송하고 실제 Agent 작업을 생성한다.

```powershell
.\.venv\Scripts\python.exe -X utf8 -B evaluation/golden/run_studio_validation.py --reference evaluation/golden/rgbd-reference.json --pdf "golden sample/research_revies.pdf" --config-id 4 --run-dir draft_history/rgbd-config4
```

PDF를 다른 위치에 뒀다면 `--pdf` 경로를 바꾼다. 현재 실행 폴더에는 완료 상태가 있으므로 같은 명령은 기존 작업을 조회한다. 별도 새 실행이나 새 Config 검증은 새로운 `--run-dir`로 구분한다. 기본 원본 해시가 다르면 업로드 전에 중단한다. Studio 지침·서비스 입력 파일은 이 실행으로 수정하지 않는다.

## 새 컴퓨터 설정

이전 PC는 Python **3.13.9**, 이번 직접 API 전환의 회귀 검사는 **3.11.9**에서 실행했다. 저장소를 복제하거나 갱신한 후 프로젝트 폴더에서:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

이미 `.env`가 있다면 위 복사 명령으로 덮어쓰지 말고 기존 파일을 사용한다. `.env`에 API 키를 입력한다. 기존 컴퓨터의 `.env`를 개인적으로 복사해도 되며 GitHub에는 올리지 않는다. Studio 검증 명령은 기본 Config 4 또는 `--config-id`를 사용한다. 실제 예전 `.env`의 Config 값이 1이어도 이번 실행 명령의 4가 우선이다.

## 별도로 옮겨야 하는 파일

PDF 원본은 현재 Git 저장소에 포함되어 있지 않다. 기존 기본 경로는 **프로젝트 폴더의 상위 폴더**다. 현재 PC의 골든 PDF 두 개는 프로젝트 내부 `golden sample/`에 있으므로 실행 시 `--pdf`를 명시했다.

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
| RGBD의 기존 legacy 저장 분석 | 고정 기준표의 제목·번호 F1 28.6%. 미등록 번역·요약도 불일치로 집계 |
| RGBD 연구 논문 Config 4 | 네 단계 완료. 실제 목차 23/23 정확. 구조 F1 86.8%, 최종 목차 배열 진단 F1 88.5%. 최종 객체 내부 인용 토큰으로 JSON 문법 실패 |
| 직접 Parse API + Python v1 | NPU 14/14·RGBD 23/23, 제목+번호 F1 100%, 오탐·누락 0개. 부모·시작 페이지 모두 일치. 두 편은 개발 샘플 |

위 값은 각 문서·실행에 대한 결과다. 모든 논문에서의 정확도나 초안 작성 품질 점수로 일반화하지 않는다. 역할 라벨이 출력에 없으면 N/A로 기록한다.

목차 평가기 버전은 `golden-outline-v3`다. 처음부터 본문 번호 목차만 평가하고 초록·키워드·부속 항목은 제외했다. 제목의 줄바꿈·공백을 정규화하고, 누락·추가·번호·부모 관계를 별도로 본다. 비교 대상의 원문 해시와 기준표 해시를 기록한다.

## 저장된 Studio JSON 평가 방법

실행 폴더에 구조·스타일·최종 검토의 본문과 API 원본 응답이 남는다. 새 응답을 다른 LLM으로 보완하지 않고 아래 도구로 읽는다.

- `studio_json_evaluation.decode_document()`: JSON 또는 전송 계층에 감싼 JSON 문자열을 읽는다.
- RGBD의 최종 검토처럼 JSON 값 밖의 인용 표시로 객체 내부 문법이 깨진 응답은 이 함수로 읽을 수 없다. 이번에는 원본의 sections/evidence 배열을 각각 strict raw_decode로 읽었으며 진단 점수와 원본 문법 실패를 구분했다. 평가용 투영본이 정상 JSON이라고 원본도 정상인 것은 아니다.
- `diagnostic_citations=True`: 마지막에 등록된 형태의 인용 표시만 붙은 경우 첫 JSON 객체를 진단용으로 분리한다. 원본 전체 strict_valid=false와 객체 자체 정상 여부를 구분한다.
- `diagnostic_controls=True`: 이전 실패 원인의 진단 옵션이다. 느슨하게 읽었다고 원본 JSON이 정상인 것으로 판정하지 않는다.
- `studio_json_evaluation.explicit_outline()`: 실제 parent ID와 원본 page/evidence 링크만 사용한다. 정답표로 누락을 보완하지 않는다.
- `golden_evaluation.evaluate_outline()`: 준비된 기준표로 목차를 채점한다. Studio 출력에 역할 라벨이 없으므로 기술적 자리표시자 `other`를 진짜 역할로 채점하지 않는다. 역할과 역할 포함 완전 일치 지표는 N/A로 구분한다.

NPU Config 4의 원문 인용 37개는 지정 페이지에 정규화된 문자열 조각이 존재하는지도 확인했다. 이는 인용에서 도출한 해석 전체를 검증한 점수가 아니다.

## 아직 반영하지 않은 변경

- 무번호·로마 숫자 목차와 다른 논문으로의 일반화는 아직 검증하지 않았다. 문체 가이드의 의미적 일반화·역할·초안 반영 품질도 별도 평가가 필요하다.
- 연구 PDF 사실 추출 `method_result.py`는 여전히 Studio를 사용한다. 이번 전환 대상은 참고 논문 구조 분석이다.
- Studio의 인용 접미부 분리 기능은 과거 평가 도구에만 있다. 새 직접 경로는 원문 ID와 JSON Schema를 사용한다.
- `research_evidence.json`은 Codex가 CUDA PDF와 대조해 정리한 보조 자료다. 전문가가 독립 검증한 정답이 아니다. 작성·검토·종합과 장별 입력/결과표에 의존성이 있다.
- 사용자가 **이 수작업 근거 프로파일 없이 사용하는 구조로 개선한 뒤 실제 초안을 비교하는 과제는 나중에 하자**고 했다. 지금 바로 제거하지 않는다.
- 현재 5·1·6장 재작성은 중복을 검사해 조건부로 수행하는 것이 아니라 해당 CUDA 경로에서 항상 수행된다. 최초 작성과 같은 지침을 사용하고 Reviewer 지적을 직접 받지 않는다. 필요성은 비교 실험으로 확인하지 않았다.
- LangGraph, FastAPI, SSE, ChromaDB, Docker는 미구현이다.

## 그림

`docs/diagrams/`에 현재 구조의 PNG와 SVG를 보관했다. 2026-10-29 Python 실행 흐름 기준이며 아직 LangGraph 구조가 아니다.

## Git에서 제외한 것

환경 파일·API 키·가상환경·전체 문서 응답·과거 실패 후보는 이 기기 전환 커밋에 넣지 않았다. 기존에 추적되고 있던 pyc 캐시의 수정도 새로 커밋하지 않았다. 코드·평가 도구·평가 결과·새 PC 설정·그림과 이 메모가 작업 재개의 기준이다.
