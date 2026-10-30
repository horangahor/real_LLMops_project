# RGBD Studio Config 4 구조 추출 평가

## 실행 조건

- PDF: `research_revies.pdf`, 16페이지. 기존 원문 기준표 23개를 변경하지 않고 사용했다.
- 같은 구조 Agent의 Config 4를 명시했고, 원본 PDF만 전송했다. 평가 기준표는 입력하지 않았다.
- 원본 SHA-256과 기준표를 확인했고, 원본 API 응답은 ignored 실행 폴더에 보관했다.
- 기존 앱 입력 프로파일과 Studio 지침은 변경하지 않았다.

## 목차 비교

| 지표 | 기존 legacy 저장 분석 | Config 4 구조 분석 | Config 4 최종 검토 |
|---|---:|---:|---:|
| 범위 내 예측 수 | 12 | 30 | 29 |
| 제목+번호 정밀도 | 5/12 (41.7%) | 23/30 (76.7%) | 23/29 (79.3%) |
| 제목+번호 재현율 | 5/23 (21.7%) | 23/23 (100.0%) | 23/23 (100.0%) |
| 제목+번호 F1 | 28.6% | 86.8% | 88.5% |
| 부모 관계 정확도 (대응 항목) | 5/5 (100.0%) | 23/23 (100.0%) | 23/23 (100.0%) |
| 하위 절 재현율 | 0/18 (0.0%) | 18/18 (100.0%) | 18/18 (100.0%) |
| 시작 페이지 포함률 (대응 항목) | 0/5 (0.0%) | 23/23 (100.0%) | 23/23 (100.0%) |

## JSON 및 원본 필드

| 단계 | 응답 전체 strict JSON | 객체 자체 strict JSON | 인용 접미부 수 |
|---|---|---|---:|
| structure | True | True | 0 |
| style | True | True | 0 |
| review | False | False | 1 |

최종 검토는 2행 166열의 document_title 값 바로 뒤에서 `Expecting ',' delimiter`로 실패했다. 인용 표시가 닫힌 문자열 뒤와 쉼표 사이에 들어갔으므로 NPU 실행의 단순 접미부 문제와 다르다.
최종 응답을 수정하거나 인용 표시를 제거하지 않았다. 원문 sections 배열 39개와 evidence 배열 51개를 각각 strict JSONDecoder.raw_decode로 읽어 진단용 투영을 만들었다. 최종 검토의 아래 목차 점수는 이 독립 배열에 한정하며 전체 JSON이 유효하거나 서비스가 바로 읽을 수 있다는 뜻이 아니다.
최종 structure_coverage는 output_section_count=38을 자체 보고했으나 실제 sections 배열 길이는 39다. 자체 보고 개수를 평가 점수로 사용하지 않았다.

## Document Parse 단계에서 확인한 원인

- 실제 모델: `document-parse-260930`. 16페이지 처리.
- 실제 제목의 시작 페이지 내 텍스트 존재: 23/23 (100.0%).
- 같은 제목을 heading 범주로 분류한 비율: 21/23 (91.3%).
- 2장 Materials and methods와 2.1.1 Preparation of seedling samples는 paragraph로 분류됐지만 후속 구조 분석이 복원했다.
- 반대로 본문 문장, computed as:, 수식, 표 6·8 제목, 결론 앞의 문장 조각이 heading1로 분류됐고 후속 단계가 목차 후보에 그대로 남겼다.
- Data will be made available on request.도 목차에 포함됐다. 데이터 제공 안내는 사전 범위 밖이지만 이 문장은 고정된 excluded_titles의 Data availability와 문자열이 달라 기존 평가기에서 오탐으로 남는다. 결과를 보고 기준표를 변경하지 않았다.
- 이 점검은 지정한 제목의 텍스트·범주 확인이다. 전체 OCR, 읽기 순서, 수식·표 인식 정확도 점수가 아니다.

### structure

- 원본 level 필드: 23/23 (100.0%)
- 원본 번호 필드: 23/23 (100.0%)
- 근거 ID 연결: 0/0 (N/A)
- 인용문 조각의 지정 페이지 존재: 37/40 (92.5%)
- 누락: 0개. 오탐: 7개. 범위 제외: 10개.
- 오탐: The subsequent integration of these re-encoded depth images with RGB data resulted in a significant improvement in weed detection accuracy. (unknown_title)
- 오탐: computed as: (unknown_title)
- 오탐: 𝑧 = MaxPool(ReLU(Conv2d(𝑥))) (unknown_title)
- 오탐: Ablation results of removing the attention-pooling module. (unknown_title)
- 오탐: Impact of fusion direction in the CA module on classification performance. (unknown_title)
- 오탐: environmental settings to improve the robustness and generalizability of the model in real-world scenarios. (unknown_title)
- 오탐: Data will be made available on request. (unknown_title)

### review

- 원본 level 필드: 23/23 (100.0%)
- 원본 번호 필드: 23/23 (100.0%)
- 근거 ID 연결: 39/39 (100.0%)
- 인용문 조각의 지정 페이지 존재: 51/51 (100.0%)
- 누락: 0개. 오탐: 6개. 범위 제외: 10개.
- 오탐: computed as: (unknown_title)
- 오탐: 𝑧 = MaxPool(ReLU(Conv2d(𝑥))) (unknown_title)
- 오탐: Ablation results of removing the attention-pooling module. (unknown_title)
- 오탐: Impact of fusion direction in the CA module on classification performance. (unknown_title)
- 오탐: environmental settings to improve the robustness and generalizability of the model in real-world scenarios. (unknown_title)
- 오탐: Data will be made available on request. (unknown_title)

## 항목별 대조

| 원문 번호·제목 | 원문 시작 페이지 | 구조 분석 | 최종 검토 |
|---|---:|---|---|
| 1 Introduction | 1 | 일치 | 일치 |
| 2 Materials and methods | 2 | 일치 | 일치 |
| 2.1 Experimental setup | 2 | 일치 | 일치 |
| 2.1.1 Preparation of seedling samples | 2 | 일치 | 일치 |
| 2.1.2 Embedded platform and RGBD imaging system | 3 | 일치 | 일치 |
| 2.1.3 RGBD seedling dataset | 3 | 일치 | 일치 |
| 2.2 Network architecture | 4 | 일치 | 일치 |
| 2.2.1 Baseline model: RGB-CTA network | 4 | 일치 | 일치 |
| 2.2.2 Tokenizer module for feature encoding | 4 | 일치 | 일치 |
| 2.2.3 Classifier module and attention-based pooling | 6 | 일치 | 일치 |
| 2.2.4 RGBD-CTA-D: Data-level fusion strategy | 7 | 일치 | 일치 |
| 2.2.5 RGBD-CTA-F: Feature-level fusion via cross-attention | 7 | 일치 | 일치 |
| 2.2.6 Training configuration | 8 | 일치 | 일치 |
| 3 Results and discussion | 9 | 일치 | 일치 |
| 3.1 Performance analysis of fusion strategies | 9 | 일치 | 일치 |
| 3.2 Interpretability via Grad-CAM attention maps | 10 | 일치 | 일치 |
| 3.3 Intra-dataset benchmarking against established lightweight models | 10 | 일치 | 일치 |
| 3.4 Cross-study on seedling state classification | 12 | 일치 | 일치 |
| 3.5 Ablation study: Effect of attention pooling module | 12 | 일치 | 일치 |
| 3.6 Ablation study: Effectiveness of cross-attention fusion | 13 | 일치 | 일치 |
| 3.7 Ablation study: Impact of fusion direction in CA module | 14 | 일치 | 일치 |
| 4 Limitations and future work | 14 | 일치 | 일치 |
| 5 Conclusion | 15 | 일치 | 일치 |

## 해석 한계

- 단일 RGBD 논문의 실행 결과다. NPU와 함께 두 편에서 관찰한 결과이며 전체 논문의 일반화 점수가 아니다.
- legacy는 예전 저장본이며 동일 모델·동일 출력 계약의 통제된 전후 실험이 아니다. 엄격한 제목 매칭은 미등록 번역·요약도 불일치로 본다.
- 기준표는 원문 대조로 작성했으나 전문가 독립 검수 전이다. 역할 라벨은 제공되지 않아 N/A이며 추론하지 않았다.
- 인용문 검사는 문자열 조각의 페이지 존재 검사다. 해석의 타당성이나 문체 가이드의 충실도를 증명하지 않는다.
- 페이지 지표는 시작 페이지가 source_pages에 포함되는지 검사하며, 추가 페이지의 정확성을 뜻하지 않는다.
- 자체 보고 coverage나 confidence를 정답 점수로 사용하지 않았다. 진단 파싱은 원본의 strict_valid 상태를 바꾸지 않는다.

## 다음 Studio 지침 개선 후보

1. Parse의 heading1은 후보로 취급한다. 본문 문장·수식·수식 도입문·표/그림 캡션·문장 조각은 원문 위치와 문맥을 대조해 본문 목차에서 제외하고, 논문 메타데이터·부속 항목은 별도 배열로 분리한다.
2. paragraph로 분류됐어도 실제 번호와 절 제목이 있으면 본문 목차 후보로 복원한다. 이번 2장과 2.1.1의 복원은 유지한다. 무번호라는 이유만으로 실제 절을 일괄 삭제하지 않는다.
3. 최종 응답은 JSON 객체 하나로 제한하고 출처는 evidence_id 배열과 JSON 문자열 안에만 둔다. 값 밖의 인용 토큰을 금지한다. 실제 배열 개수로 coverage를 계산하고 형식 검증 실패는 성공과 구분한다.
4. 이 두 PDF를 고정 회귀 샘플로 재실행해 재현율뿐 아니라 오탐 수와 strict JSON 성공 여부도 함께 비교한다.

## 재현

원본 실행과 평가 스크립트는 `draft_history/rgbd-config4/`에 보관했다.
구조·최종 검토의 목차 투영은 `evaluation/golden/predictions/rgbd-studio-config4-*-projection.json`에 있다.
동일 기준표와 `studio_json_evaluation.explicit_outline()` 및 `golden_evaluation.evaluate_outline()`로 재채점할 수 있다.
