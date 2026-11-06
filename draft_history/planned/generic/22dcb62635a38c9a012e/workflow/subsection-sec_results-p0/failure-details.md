# 작성 검토 실패: subsection-sec_results-p0

## 검토 지적

- [원문·내용 검토; 처리 책임: writer] sec_results_p2는 초기 포팅 단계의 CPU ONLY/GPU/GPU OPTIMIZED/HYBRID/HYBRID V2 비교와 단일 실행 한계를 서술해야 하나, 인용된 근거(E00277~E00361)는 cudaHostRegister/No Pinning 비교, 클록 고정, Persistence mode, 그래프 적용 전후 감소 등 후속 메모리 전송·그래프 최적화 맥락의 근거로, 초기 포팅 단계의 실행 시간 결과 및 비교 관찰과 직접 연결되지 않는다.
  - 문단: sec_results_p2; 근거: E00277, E00278, E00279, E00280, E00281, E00282, E00283, E00284, E00286, E00292, E00293, E00294, E00295, E00296, E00297, E00298, E00299, E00300, E00301, E00320, E00346, E00358, E00361
  - 실제 본문: 초기 포팅 단계에서는 CPU 전용 구현(CPU ONLY)과 GPU 버전, 그리고 이후 GPU OPTIMIZED, HYBRID, HYBRID V2를 순차적으로 비교하였다. 단일 실행 기준으로 CPU ONLY는 101.237800ms, GPU 버전은 353.057200ms, GPU OPTIMIZED는 229.691800ms, HYBRID는 201.670100ms, HYBRID V2는 85.785300ms로 기록되었다. 이 시점에서는 GPU OPTIMIZED와 HYBRID조차 CPU ONLY보다 느렸으며, GPU 가속이 곧바로 전체 실행 시간 단축으로 이어지지는 않았다. 해당 수치는 단일 실행 결과이며 반복 측정 통계는 제시되지 않았다. [근거:E00277,E00278,E00279,E00280,E00281,E00282,E00283,E00284,E00286,E00292,E00293,E00294,E00295,E00296,E00297,E00298,E00299,E00300,E00301,E00320,E00346,E00358,E00361]
- [원문·내용 검토; 처리 책임: writer] sec_results_p3은 단일 샘플 기준 Inference time과 Bound time 분해를 통해 초기 비교 맥락을 설명해야 하나, 인용된 근거(Hefd7e87bb735_58, Hefd7e87bb735_62)는 측정 조건이 원문에 직접 명시되어 있지 않다는 관찰과 warmup·평균 측정·cudaGraph 적용 여부 등 측정 방식 기록만 포함하며, 실제 Inference time/Bound time 분해 수치나 초기 CPU/GPU 비교 맥락을 직접 뒷받침하지 않는다.
  - 문단: sec_results_p3; 근거: Hefd7e87bb735_58, Hefd7e87bb735_62
  - 실제 본문: 초기 비교에서 CPU ONLY와 GPU 버전의 차이는 단일 샘플 기준 Inference time과 Bound time 분해로 확인할 수 있다. 이 분해는 전체 실행 시간 중 추론과 경계 계산이 어느 정도 비중을 차지하는지 보여주며, 이후 CUDA 최적화 단계별 시간 구성을 해석하는 기준이 된다. [근거:Hefd7e87bb735_58,Hefd7e87bb735_62]
- [원문·내용 검토; 처리 책임: writer] sec_results_p4는 forward/backward의 sparse.py 대비 CUDA 가속 배율과 추론+bound+검증 단축률을 서술해야 하나, 인용된 근거(Hefd7e87bb735_58, Hefd7e87bb735_62, Hcdbfb7147ce4_7, Hcdbfb7147ce4_9) 중 Hefd7e87bb735_58/Hefd7e87bb735_62는 측정 조건 미명시 관찰이고 Hcdbfb7147ce4_7/Hcdbfb7147ce4_9는 구성 요소 단위 성능 순위·순위 간 차이 비교 미확인 관찰로, 표에 제시된 5.32x/4.86x/5.30x/4.89x 및 81.2%/79.4%/81.1%/79.6% 단축률 수치를 직접 뒷받침하지 않는다.
  - 문단: sec_results_p4; 근거: Hefd7e87bb735_58, Hefd7e87bb735_62, Hcdbfb7147ce4_7, Hcdbfb7147ce4_9
  - 실제 본문: forward와 backward 방식 모두 sparse.py 대비 CUDA 가속 배율과 추론+bound+검증 단축률이 보고되었다. forward는 bound 계산에서 5.32배(81.2% 단축), 추론+bound+검증에서 4.86배(79.4% 단축)로 나타났고, backward는 bound 계산에서 5.30배(81.1% 단축), 추론+bound+검증에서 4.89배(79.6% 단축)로 나타났다. 이 비교는 초기 CUDA 포팅이 기준 구현 대비 경계 계산과 전체 파이프라인 시간을 어느 정도 줄였는지 보여준다. [근거:Hefd7e87bb735_58,Hefd7e87bb735_62,Hcdbfb7147ce4_7,Hcdbfb7147ce4_9]
- [원문·내용 검토; 처리 책임: writer] sec_results_p5는 40000회 반복 기준 forward/backward의 total_s/infer_s/bound_s/certify_s 및 평균 지연시간 분해를 서술해야 하나, 인용된 근거(Hefd7e87bb735_58, Hefd7e87bb735_62)는 측정 조건 미명시 관찰과 warmup·평균 측정·cudaGraph 적용 여부 기록만 포함하며, 실제 481.7157/1.3569/479.6443/0.6957 및 438.3345/1.599/435.8792/0.6724, avg_infer_ms 0.0015/0.0017, avg_bound_ms 0.5214/0.4738 수치를 직접 뒷받침하지 않는다.
  - 문단: sec_results_p5; 근거: Hefd7e87bb735_58, Hefd7e87bb735_62
  - 실제 본문: 40000회 반복 기준 단계별 시간 분해를 보면, backward는 total_s 481.7157, infer_s 1.3569, bound_s 479.6443, certify_s 0.6957로 bound 단계가 대부분을 차지했고, forward는 total_s 438.3345, infer_s 1.599, bound_s 435.8792, certify_s 0.6724로 유사한 구성을 보였다. 평균 지연시간 역시 backward avg_infer_ms 0.0015, avg_bound_ms 0.5214, forward avg_infer_ms 0.0017, avg_bound_ms 0.4738로 경계 계산 중심의 시간 구성이 반복 기준으로도 확인되었다. [근거:Hefd7e87bb735_58,Hefd7e87bb735_62]
- [composition; 처리 책임: writer] ### 4.1 초기 포팅과 CPU/GPU 버전 비교: 본문 1463자 / 목표 800자 / 허용 상한 1000자로 허용 범위를 초과했습니다. 핵심 설명·조건·반례·한계를 남기고 반복·로그·수치 열거를 줄여 목표 분량에 맞추세요. 소절 삭제나 긴 한 문단으로 합치는 방식은 쓰지 마세요.
  - 문단: none; 근거: 미지정
- [composition; 처리 책임: writer] sec_results/p0: 표 source_table_0023에 근거 인용으로 연결된 문단이 3개입니다. 표 하나마다 핵심 관찰·비교 조건·해석 한계를 독립 문단 1~2개로 구성하세요. 근거를 일괄 부착하거나 조건·반례를 삭제하지 마세요.
  - 문단: none; 근거: 미지정
- [composition; 처리 책임: writer] sec_results/p0: 표 source_table_0024에 근거 인용으로 연결된 문단이 3개입니다. 표 하나마다 핵심 관찰·비교 조건·해석 한계를 독립 문단 1~2개로 구성하세요. 근거를 일괄 부착하거나 조건·반례를 삭제하지 마세요.
  - 문단: none; 근거: 미지정
- [composition; 처리 책임: writer] sec_results/p0: 표 source_table_0025에 근거 인용으로 연결된 문단이 3개입니다. 표 하나마다 핵심 관찰·비교 조건·해석 한계를 독립 문단 1~2개로 구성하세요. 근거를 일괄 부착하거나 조건·반례를 삭제하지 마세요.
  - 문단: none; 근거: 미지정
