# 작성 검토 실패: subsection-sec_conclusion-p2

## 검토 지적

- [원문·내용 검토; 처리 책임: writer] ri_conc_3의 description은 memcpy 병목 해소 필요성, Pinned Memory의 평균 속도 미세 불리·WCET·지터 안정성 관찰, 향후 학습·측정·분리 측정 계획, 3D 텐서 레이아웃 기반 cublasSgemmBatched 및 텐서 코어 활용 로드맵(30초~1분대 목표) 등 계획·제안 방향을 짧게 정리하도록 요구한다. 본문은 이 항목들을 대체로 반영하지만, E00262의 '30초~1분대 진입 목표'와 '전체 40,000개 대상' 중 '전체 40,000개' 규모가 본문에 명시되지 않아 description이 요구하는 로드맵 조건 일부가 누락되었다. 또한 E00296의 'Pinned Memory가 평균 속도에서 미세하게 불리할 수 있으나 최악 지연(WCET)과 지터에서 안정적'이라는 관찰은 E00296의 limits·conditions에 포함되지 않은 해석적 서술로, 승인된 근거의 범위를 벗어나 추가되었다.
  - 문단: sec_conclusion_p3; 근거: E00262, E00296
  - 실제 본문: 향후 방향으로는 memcpy 병목을 줄여야 CPU 대비 속도 우위를 확보할 수 있다는 판단 아래, global memory·SM 병목, Nsight Compute, shared memory, 타일링, cudaGraph 원리 학습과 FP32 변경 및 Nsight Compute 분석, backward_only 속도 원인 조사, pinned memory 성능 측정, 추론·bound·검증 분리 측정 등이 검토·제안 대상으로 남아 있다. 또한 CROWN 행렬식을 3D 텐서 레이아웃으로 변환해 cublasSgemmBatched를 호출하고 텐서 코어를 활용하는 방향은 antenna_lirpa의 2분을 넘어 30초~1분대 진입을 목표로 하는 차기 로드맵의 과제로 정리된다. 이러한 방향은 계획·제안 성격이며 실제 수행 결과로 대체하지 않는다. [근거:E00262,E00211,E00296]
