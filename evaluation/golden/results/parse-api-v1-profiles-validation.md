# Direct Parse API + Python 목차 평가 v1

파싱은 Document Parse API, 목차 선택·페이지 연결·부모 복원은 Python 코드가 담당한다. Studio Agent를 호출하지 않는다.
기존 NPU 14개·RGBD 23개의 원문 기준표와 번역 별칭·제외 제목을 변경하지 않았다. 정답표는 추출 코드의 입력이 아니다.
지원 범위는 참고문헌 이전의 아라비아 숫자 본문 목차다. 무번호·로마 숫자 목차의 정확도는 이 결과로 주장하지 않는다.

| PDF | Studio Config 4 구조 F1 | 새 경로 F1 | 정밀도 | 재현율 | 오탐 / 누락 | 부모 | 시작 페이지 |
|---|---:|---:|---:|---:|---:|---:|---:|
| NPU | 100.0% | 100.0% | 14/14 (100.0%) | 14/14 (100.0%) | 0 / 0 | 14/14 (100.0%) | 14/14 (100.0%) |
| RGBD | 86.8% | 100.0% | 23/23 (100.0%) | 23/23 (100.0%) | 0 / 0 | 23/23 (100.0%) | 23/23 (100.0%) |

## 동일 Parse 결과 재생

기존 RGBD Studio의 step_1_parse 원본을 그대로 새 코드에 입력했다. 제목+번호 F1 100.0%, 정밀도 23/23 (100.0%), 재현율 23/23 (100.0%)다.
파싱 모델을 다시 호출하거나 Parse 결과를 수정하지 않고도 목차 선택 정책의 효과를 확인한 비교다. 새 API 실행과의 비교는 OCR 등 모든 숨은 설정이 통제된 모델 실험은 아니다.

## NPU 상세

| 원문 번호·제목 | 예측 | 번호 / 부모 / 페이지 |
|---|---|---|
| 1 Introduction | 1 Introduction | 일치 / 일치 / 일치 |
| 2 Related Work | 2 Related Work | 일치 / 일치 / 일치 |
| 3 Benchmark Design | 3 Benchmark Design | 일치 / 일치 / 일치 |
| 3.1 Benchmark Framework | 3.1 Benchmark Framework | 일치 / 일치 / 일치 |
| 3.2 Benchmark Configurations | 3.2 Benchmark Configurations | 일치 / 일치 / 일치 |
| 3.3 Workloads and Datasets | 3.3 Workloads and Datasets | 일치 / 일치 / 일치 |
| 3.4 Vendor-Specific Deployment Configuration | 3.4 Vendor-Specific Deployment Configuration | 일치 / 일치 / 일치 |
| 3.5 NPU Hardware and Software Environments | 3.5 NPU Hardware and Software Environments | 일치 / 일치 / 일치 |
| 4 Evaluation Results and Findings | 4 Evaluation Results and Findings | 일치 / 일치 / 일치 |
| 4.1 RQ1: Do vendor-guided optimizations improve both latency and accuracy? | 4.1 RQ1: Do vendor-guided optimizations improve both latency and accuracy? | 일치 / 일치 / 일치 |
| 4.2 RQ2: Does NPU-only performance predict end-to-end performance? | 4.2 RQ2: Does NPU-only performance predict end-to-end performance? | 일치 / 일치 / 일치 |
| 4.3 RQ3: How much additional benefit comes from vendor-guided deployment? | 4.3 RQ3: How much additional benefit comes from vendor-guided deployment? | 일치 / 일치 / 일치 |
| 4.4 Limitations | 4.4 Limitations | 일치 / 일치 / 일치 |
| 5 Conclusion and Future Work | 5 Conclusion and Future Work | 일치 / 일치 / 일치 |

역할 라벨 일치율: 12/14 (85.7%). 역할 기준은 초기 원문 판정이며 전문가 독립 검수 전이다.

## RGBD 상세

| 원문 번호·제목 | 예측 | 번호 / 부모 / 페이지 |
|---|---|---|
| 1 Introduction | 1 Introduction | 일치 / 일치 / 일치 |
| 2 Materials and methods | 2 Materials and methods | 일치 / 일치 / 일치 |
| 2.1 Experimental setup | 2.1 Experimental setup | 일치 / 일치 / 일치 |
| 2.1.1 Preparation of seedling samples | 2.1.1 Preparation of seedling samples | 일치 / 일치 / 일치 |
| 2.1.2 Embedded platform and RGBD imaging system | 2.1.2 Embedded platform and RGBD imaging system | 일치 / 일치 / 일치 |
| 2.1.3 RGBD seedling dataset | 2.1.3 RGBD seedling dataset | 일치 / 일치 / 일치 |
| 2.2 Network architecture | 2.2 Network architecture | 일치 / 일치 / 일치 |
| 2.2.1 Baseline model: RGB-CTA network | 2.2.1 Baseline model: RGB-CTA network | 일치 / 일치 / 일치 |
| 2.2.2 Tokenizer module for feature encoding | 2.2.2 Tokenizer module for feature encoding | 일치 / 일치 / 일치 |
| 2.2.3 Classifier module and attention-based pooling | 2.2.3 Classifier module and attention-based pooling | 일치 / 일치 / 일치 |
| 2.2.4 RGBD-CTA-D: Data-level fusion strategy | 2.2.4 RGBD-CTA-D: Data-level fusion strategy | 일치 / 일치 / 일치 |
| 2.2.5 RGBD-CTA-F: Feature-level fusion via cross-attention | 2.2.5 RGBD-CTA-F: Feature-level fusion via cross-attention | 일치 / 일치 / 일치 |
| 2.2.6 Training configuration | 2.2.6 Training configuration | 일치 / 일치 / 일치 |
| 3 Results and discussion | 3 Results and discussion | 일치 / 일치 / 일치 |
| 3.1 Performance analysis of fusion strategies | 3.1 Performance analysis of fusion strategies | 일치 / 일치 / 일치 |
| 3.2 Interpretability via Grad-CAM attention maps | 3.2 Interpretability via Grad-CAM attention maps | 일치 / 일치 / 일치 |
| 3.3 Intra-dataset benchmarking against established lightweight models | 3.3 Intra-dataset benchmarking against established lightweight models | 일치 / 일치 / 일치 |
| 3.4 Cross-study on seedling state classification | 3.4 Cross-study on seedling state classification | 일치 / 일치 / 일치 |
| 3.5 Ablation study: Effect of attention pooling module | 3.5 Ablation study: Effect of attention pooling module | 일치 / 일치 / 일치 |
| 3.6 Ablation study: Effectiveness of cross-attention fusion | 3.6 Ablation study: Effectiveness of cross-attention fusion | 일치 / 일치 / 일치 |
| 3.7 Ablation study: Impact of fusion direction in CA module | 3.7 Ablation study: Impact of fusion direction in CA module | 일치 / 일치 / 일치 |
| 4 Limitations and future work | 4 Limitations and future work | 일치 / 일치 / 일치 |
| 5 Conclusion | 5 Conclusion | 일치 / 일치 / 일치 |

역할 라벨 일치율: 19/23 (82.6%). 역할 기준은 초기 원문 판정이며 전문가 독립 검수 전이다.

## 출력과 검증 범위

- 원본 API 응답·설정·원본 및 응답 해시·선택/제외 후보는 ignored draft_history/parse-api-v1/에 보관한다.
- --outline-only는 Solar를 호출하지 않는다. 본문 목차의 role=other는 기술적 자리표시자로 역할 점수에 사용하지 않는다.
- 전체 분석에서는 코드가 정한 제목·번호·페이지를 유지하고, Solar가 원문 element_id에 역할 및 재사용 작성 가이드만 연결한다. JSON Schema와 로컬 ID·형식 검증을 적용한다.
- 원문 전용 영문 식별자는 재사용 지침에서 검사하고, 발견되면 지침 문장만 최대 한 번 수정해 재검사한다. 현재 앱 가이드의 일부 표현은 Codex가 추가 추상화했으며 프로파일의 guidance_review에 전후를 기록했다. 원본 API 응답은 수정하지 않았다.
- 제목·번호가 있는 일반 paragraph를 복원하고 문장·수식·캡션을 목차에서 제외한다. 서로 다른 제목의 동일 절 번호 충돌과 누락 부모는 임의 보완하지 않고 실패시킨다.
- 두 편에서 측정한 결과다. 무번호 절, OCR 오류, 합쳐진 문단, 복잡한 번호 체계, 번호가 붙은 목록은 추가 검증이 필요하다.
- 이 두 문서를 보며 줄바꿈·paragraph 절·반복 머리말 처리 규칙을 개선했다. 개발 샘플이며 독립 보류 평가셋의 점수가 아니다.
- 문체 가이드의 충실도·생성 초안 품질은 이 목차 점수와 별도로 평가해야 한다. 원문 기준표는 전문가 독립 검수 전이다.

## 재현

```powershell
python -X utf8 -B paper_structure.py --outline-only --run-dir draft_history/parse-api-v1 --output evaluation/golden/predictions/parse-api-v1-outlines.json
python -X utf8 -B evaluation/golden/evaluate_parse_pipeline.py --profiles evaluation/golden/predictions/parse-api-v1-outlines.json
```

동일 원본·설정의 캐시가 있으면 Parse API를 다시 호출하지 않는다. 새 파싱은 --force-parse 또는 별도 --run-dir를 사용한다.
