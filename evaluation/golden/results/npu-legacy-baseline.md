# 골든 샘플 구조 추출 평가

- 원본: `AIComps2026_NPU_Benchmarking_1.1v.pdf` (PDF 14쪽)
- 예측 출처: `legacy_analysis` / `evaluation/golden/predictions/npu-legacy.json`
- 평가 항목: 원문 14개, 원시 예측 6개, 범위 내 예측 6개, 제목 대응 6개
- 채점 범위 제외: 0개 (원문에서 확인된 사전 제외 범주의 제목)

## 측정 범위와 한계

기존 legacy_analysis 저장본을 원문 대조 기준표와 비교한 오프라인 평가다. 이전 분석의 변환본이므로 현재 분석 모델이나 파서의 성능으로 해석하면 안 된다.
원문 대조 기준은 Codex가 페이지 이미지와 텍스트를 확인하여 작성했다. 사용자·전문가의 독립 검수 전이며 역할 분류에는 판단이 포함된다.
한 편의 구조 추출 결과이며 초안 반영률·논문 품질·다른 PDF로의 일반화 성능을 뜻하지 않는다.

## 결과

| 지표 | 결과 |
|---|---:|
| 제목 대응 정밀도 (번호 무관·사전 선언 번역 허용) | 6/6 (100.0%) |
| 제목 대응 재현율 | 6/14 (42.9%) |
| 제목 대응 F1 | 60.0% |
| 제목+번호 정밀도 | 4/6 (66.7%) |
| 제목+번호 재현율 | 4/14 (28.6%) |
| 제목+번호 F1 | 40.0% |
| 계층 정확도 (대응된 항목 한정·최상위 포함) | 5/6 (83.3%) |
| 하위 절 부모 정확도 (대응된 하위 절 한정) | 0/1 (0.0%) |
| 역할 분류 정확도 (대응된 항목 한정) | 6/6 (100.0%) |
| 번호가 맞는 하위 절 재현율 | 0/9 (0.0%) |
| 제목·번호·계층·역할을 모두 맞춘 항목 재현율 | 4/14 (28.6%) |
| 시작 페이지 일치율 (대응된 항목 한정) | 0/6 (0.0%) |

조건부 계층·역할 정확도는 찾아낸 제목만 대상으로 한다. 누락은 재현율과 함께 판단해야 하며 이 점수만으로 전체 구조가 정확하다고 해석하면 안 된다.
페이지 일치율은 시작 페이지가 source_pages에 포함되는지 측정한다. null 항목의 0점은 페이지 미제공이며 잘못된 페이지를 추측했다는 뜻은 아니다.

## 항목별 비교

| 원문 번호·제목 | PDF 쪽 | 예측 | 번호 | 부모 | 역할 |
|---|---:|---|---|---|---|
| 1 Introduction | 1 | 1 서론 (Introduction) | 일치 | 일치 | 일치 |
| 2 Related Work | 3 | 2 관련 연구 (Related Work) | 일치 | 일치 | 일치 |
| 3 Benchmark Design | 5 | 3 방법론 (Benchmark Design) | 일치 | 일치 | 일치 |
| 3.1 Benchmark Framework | 5 | 누락 | — | — | — |
| 3.2 Benchmark Configurations | 6 | 누락 | — | — | — |
| 3.3 Workloads and Datasets | 7 | 누락 | — | — | — |
| 3.4 Vendor-Specific Deployment Configuration | 8 | 누락 | — | — | — |
| 3.5 NPU Hardware and Software Environments | 9 | 누락 | — | — | — |
| 4 Evaluation Results and Findings | 9 | 4 실험 결과 (Evaluation Results and Findings) | 일치 | 일치 | 일치 |
| 4.1 RQ1: Do vendor-guided optimizations improve both latency and accuracy? | 9 | 누락 | — | — | — |
| 4.2 RQ2: Does NPU-only performance predict end-to-end performance? | 11 | 누락 | — | — | — |
| 4.3 RQ3: How much additional benefit comes from vendor-guided deployment? | 11 | 누락 | — | — | — |
| 4.4 Limitations | 12 | 5 한계점 (Limitations) | 불일치 | 불일치 | 일치 |
| 5 Conclusion and Future Work | 12 | 6 결론 (Conclusion and Future Work) | 불일치 | 일치 | 일치 |

## 대응하지 않은 예측


## 재현 방법

```powershell
.\.venv\Scripts\python.exe -X utf8 -B golden_evaluation.py --profiles evaluation/golden/predictions/npu-legacy.json --output evaluation/golden/results/recheck.json
```

현재 프로파일 평가: --profiles paper_structure_analysis.json 및 별도 --output 경로를 사용한다. 기존 초안·입력 프로파일은 수정하지 않는다.

## 다음 평가

1. 기준표를 원문과 함께 사용자 검수한다.
2. 새 분석 결과를 별도 파일에 저장하고 같은 기준표로 비교한다. 원본 파서 응답을 보존해야 파싱 누락과 LLM 분석 누락을 구분할 수 있다.
3. 구조 분석의 개선을 확인한 뒤, 작성 가이드의 근거성과 초안에서의 역할 반영을 별도 평가한다.
