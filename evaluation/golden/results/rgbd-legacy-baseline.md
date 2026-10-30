# 골든 샘플 구조 추출 평가

- 원본: `research_revies.pdf` (PDF 16쪽)
- 예측 출처: `legacy_analysis` / `paper_structure_analysis.json`
- 평가 항목: 원문 23개, 원시 예측 12개, 범위 내 예측 12개, 제목 대응 5개
- 채점 범위 제외: 0개 (원문에서 확인된 사전 제외 범주의 제목)

## 측정 범위와 한계

기존 legacy_analysis 저장본을 원문 대조 기준표와 비교한 오프라인 평가다. 이전 분석의 변환본이므로 현재 분석 모델이나 파서의 성능으로 해석하면 안 된다.
원문 대조 기준은 Codex가 페이지 이미지와 텍스트를 확인하여 작성했다. 사용자·전문가의 독립 검수 전이며 역할 분류에는 판단이 포함된다.
한 편의 구조 추출 결과이며 초안 반영률·논문 품질·다른 PDF로의 일반화 성능을 뜻하지 않는다.

## 결과

| 지표 | 결과 |
|---|---:|
| 제목 대응 정밀도 (번호 무관·사전 선언 번역 허용) | 5/12 (41.7%) |
| 제목 대응 재현율 | 5/23 (21.7%) |
| 제목 대응 F1 | 28.6% |
| 제목+번호 정밀도 | 5/12 (41.7%) |
| 제목+번호 재현율 | 5/23 (21.7%) |
| 제목+번호 F1 | 28.6% |
| 계층 정확도 (대응된 항목 한정·최상위 포함) | 5/5 (100.0%) |
| 하위 절 부모 정확도 (대응된 하위 절 한정) | 0/0 (N/A) |
| 역할 분류 정확도 (대응된 항목 한정) | 5/5 (100.0%) |
| 번호가 맞는 하위 절 재현율 | 0/18 (0.0%) |
| 제목·번호·계층·역할을 모두 맞춘 항목 재현율 | 5/23 (21.7%) |
| 시작 페이지 일치율 (대응된 항목 한정) | 0/5 (0.0%) |

조건부 계층·역할 정확도는 찾아낸 제목만 대상으로 한다. 누락은 재현율과 함께 판단해야 하며 이 점수만으로 전체 구조가 정확하다고 해석하면 안 된다.
페이지 일치율은 시작 페이지가 source_pages에 포함되는지 측정한다. null 항목의 0점은 페이지 미제공이며 잘못된 페이지를 추측했다는 뜻은 아니다.

## 항목별 비교

| 원문 번호·제목 | PDF 쪽 | 예측 | 번호 | 부모 | 역할 |
|---|---:|---|---|---|---|
| 1 Introduction | 1 | 1 서론 | 일치 | 일치 | 일치 |
| 2 Materials and methods | 2 | 2 재료 및 방법 | 일치 | 일치 | 일치 |
| 2.1 Experimental setup | 2 | 누락 | — | — | — |
| 2.1.1 Preparation of seedling samples | 2 | 누락 | — | — | — |
| 2.1.2 Embedded platform and RGBD imaging system | 3 | 누락 | — | — | — |
| 2.1.3 RGBD seedling dataset | 3 | 누락 | — | — | — |
| 2.2 Network architecture | 4 | 누락 | — | — | — |
| 2.2.1 Baseline model: RGB-CTA network | 4 | 누락 | — | — | — |
| 2.2.2 Tokenizer module for feature encoding | 4 | 누락 | — | — | — |
| 2.2.3 Classifier module and attention-based pooling | 6 | 누락 | — | — | — |
| 2.2.4 RGBD-CTA-D: Data-level fusion strategy | 7 | 누락 | — | — | — |
| 2.2.5 RGBD-CTA-F: Feature-level fusion via cross-attention | 7 | 누락 | — | — | — |
| 2.2.6 Training configuration | 8 | 누락 | — | — | — |
| 3 Results and discussion | 9 | 3 결과 및 토론 | 일치 | 일치 | 일치 |
| 3.1 Performance analysis of fusion strategies | 9 | 누락 | — | — | — |
| 3.2 Interpretability via Grad-CAM attention maps | 10 | 누락 | — | — | — |
| 3.3 Intra-dataset benchmarking against established lightweight models | 10 | 누락 | — | — | — |
| 3.4 Cross-study on seedling state classification | 12 | 누락 | — | — | — |
| 3.5 Ablation study: Effect of attention pooling module | 12 | 누락 | — | — | — |
| 3.6 Ablation study: Effectiveness of cross-attention fusion | 13 | 누락 | — | — | — |
| 3.7 Ablation study: Impact of fusion direction in CA module | 14 | 누락 | — | — | — |
| 4 Limitations and future work | 14 | 4 한계 및 향후 연구 | 일치 | 일치 | 일치 |
| 5 Conclusion | 15 | 5 결론 | 일치 | 일치 | 일치 |

## 대응하지 않은 예측

- 오탐: 2.1 실험 설정 (샘플 준비, 임베디드 플랫폼, 데이터셋) (unknown_title)
- 오탐: 2.2 네트워크 아키텍처 (토큰화기, 분류기, 융합 모듈) (unknown_title)
- 오탐: 3.1 융합 전략 비교 (unknown_title)
- 오탐: 3.2 Grad-CAM 해석 가능성 (unknown_title)
- 오탐: 3.3 경량 모델 벤치마킹 (unknown_title)
- 오탐: 3.4 교차 연구 비교 (unknown_title)
- 오탐: 3.5 제거 실험 (Attention Pooling, CA 모듈) (unknown_title)

## 재현 방법

```powershell
python -X utf8 -B golden_evaluation.py --reference evaluation/golden/rgbd-reference.json --profiles paper_structure_analysis.json --source "golden sample/research_revies.pdf" --output evaluation/golden/results/rgbd-recheck.json
```

현재 프로파일 평가: --profiles paper_structure_analysis.json 및 별도 --output 경로를 사용한다. 기존 초안·입력 프로파일은 수정하지 않는다.

## 다음 평가

1. 기준표를 원문과 함께 사용자 검수한다.
2. 새 분석 결과를 별도 파일에 저장하고 같은 기준표로 비교한다. 원본 파서 응답을 보존해야 파싱 누락과 LLM 분석 누락을 구분할 수 있다.
3. 구조 분석의 개선을 확인한 뒤, 작성 가이드의 근거성과 초안에서의 역할 반영을 별도 평가한다.
