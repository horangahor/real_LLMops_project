# Studio 골든 샘플 구조 평가

원본: `AIComps2026_NPU_Benchmarking_1.1v.pdf`

Studio 구조 분석 단계의 Markdown에서 ‘섹션 계층 및 순서’ 구간에 명시된 번호·제목만 코드로 추출했다. 원문 기준표를 이용해 누락 제목을 채우거나 별도 LLM으로 재분석하지 않았다.
서술형 응답에 역할·페이지 필드가 없으므로 해당 지표는 N/A다. 계층은 응답에 실제 적힌 절 번호로 복원했으며 Studio가 계층 JSON을 직접 반환했다는 뜻이 아니다.

| 지표 | 결과 |
|---|---:|
| 명시적인 제목+번호 정밀도 | 10/10 (100.0%) |
| 명시적인 제목+번호 재현율 | 10/14 (71.4%) |
| 명시적인 제목+번호 F1 | 83.3% |
| 명시 번호로 복원한 계층 정확도 | 10/10 (100.0%) |
| 번호가 맞는 하위 절 재현율 | 5/9 (55.6%) |
| 구조화된 역할·페이지 라벨 정확도 | N/A (필드 미제공) |

## 상세

| 원문 번호·제목 | 명시적인 출력 |
|---|---|
| 1 Introduction | 1 Introduction |
| 2 Related Work | 2 Related Work |
| 3 Benchmark Design | 3 Benchmark Design |
| 3.1 Benchmark Framework | 3.1 Benchmark Framework |
| 3.2 Benchmark Configurations | 3.2 Benchmark Configurations |
| 3.3 Workloads and Datasets | 3.3 Workloads and Datasets |
| 3.4 Vendor-Specific Deployment Configuration | 3.4 Vendor-Specific Deployment Configuration |
| 3.5 NPU Hardware and Software Environments | 3.5 NPU Hardware and Software Environments |
| 4 Evaluation Results and Findings | 4 Evaluation Results and Findings |
| 4.1 RQ1: Do vendor-guided optimizations improve both latency and accuracy? | 번호·실제 제목 미제공 |
| 4.2 RQ2: Does NPU-only performance predict end-to-end performance? | 번호·실제 제목 미제공 |
| 4.3 RQ3: How much additional benefit comes from vendor-guided deployment? | 번호·실제 제목 미제공 |
| 4.4 Limitations | 번호·실제 제목 미제공 |
| 5 Conclusion and Future Work | 5 Conclusion and Future Work |

## 해석

번호·제목 목록에 없는 절도 서술형 본문에서 간접적으로 설명될 수 있다. 이 평가는 명시된 번호 목차의 완전성을 측정하며, 응답 전체의 의미적 이해를 측정하지 않는다.
관찰 목차 JSON과 일반 글쓰기 분석은 서로 다른 출력 계약이다. 이 결과는 현재 서비스의 schema_version 2 프로파일을 직접 대체할 수 없다.
한 문서·한 번의 Studio 실행이며 기준표는 Codex가 원문 대조로 작성한 초기 자료로 독립 검수 전이다. 이전 직접 API 실행과 워크플로우·출력 형식이 달라 같은 모델의 설정 변경 효과를 분리한 실험은 아니다.

## 재현

```powershell
.\.venv\Scripts\python.exe -X utf8 -B studio_outline_evaluation.py --structure evaluation/golden/predictions/npu-studio-structure.md --output evaluation/golden/results/npu-studio-recheck.json
```
