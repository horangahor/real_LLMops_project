# CROWN 검증 CUDA 가속 최적화 과정 및 성능 분석 — 자동 추출 연구 근거

기계 추출·원문 대조 결과이며 독립적인 사실 검증이 아닙니다.

후보 34개 / 작성용 11개

## F01 · 구현·방법 · 구현 기록

CUDA 컴파일 환경은 NVIDIA CUDA 컴파일러 드라이버(nvcc) release 13.3, V13.3.73이며, CUDA 동작이 필요한 코드만 바꿔도 nvcc로 컴파일이 가능하다는 점을 전제로 CUDA 포팅을 진행했다.

원문 대조: 일부만 뒷받침 — nvcc 버전 출력 텍스트와 CUDA 동작이 필요한 코드만 바꿔도 nvcc 컴파일이 가능하다는 전제가 원문에 함께 제시되어 있어, CUDA 포팅의 환경·전제가 진술과 일치한다. [코드 검사: 측정값 1개를 원문에서 확인하지 못해 작성용 근거에서 제외]

해석 한계: CUDA 툴킷/드라이버의 정확한 설치 환경, GPU 모델, 측정 머신 사양은 명시되지 않았다. 버전 표기는 nvcc 출력 텍스트 기준이다.

- 조건: CUDA 컴파일러 드라이버(nvcc) release 13.3, V13.3.73
- 조건: CUDA 동작이 필요한 코드만 수정해도 nvcc로 컴파일 가능하다는 전제
- 측정: nvcc version = 13.3  (nvcc --version 출력 기준) / p1:e1
- 확인 필요 수치 (작성 제외): nvcc build version = V13.3.73  — 수치 표기를 연결 원문에서 확인하지 못했습니다.

출처: 1쪽 · p1:e1

> C :\Program Files\Microsoft Visual Studio\18\Community>nvcc --version
> nvcc: NVIDIA (R) Cuda compiler driver
> Copyright (c) 2005-2026 NVIDIA Corporation
> Built on Tue_Jun__9_14:30:19_Pacific_Daylight_Time_2026
> Cuda compilation tools, release 13.3, V13.3.73
> Build cuda_13.3.r13.3/compiler.38244171_0

출처: 1쪽 · p1:e4

> 기본적으로 c++ 언어에서 GPU의 동작을 가능하게 한 것이 CUDA
> 그러다 보니 기본적으로 c 언어와 동일하고 CUDA 동작이 필요한 코드만 따로 바꾸어도
> nvcc(NVIDIA C Compiler) 에서 컴파일이 가능

## F02 · 구현·방법 · 구현 기록

원본 C++ 파일(lirpa_forward_backward_fc_array.cpp)의 기본 틀을 유지한 채 병렬 연산이 필요한 부분만 커널 함수로 바꾸는 방식으로 CUDA 포팅을 시도했고, 초기 포팅 후 컴파일·실행 검증에서 기존과 동일하게 동작함을 확인했다.

원문 대조: 일부만 뒷받침 — 원본 C++ 파일의 기본 틀을 유지하고 병렬 연산 부분만 커널 함수로 바꾸는 방식의 포팅 시도와, 포팅 직후 컴파일·실행 검증에서 동일하게 동작했다는 진술이 원문에 있다. [코드 검사: 측정값 1개를 원문에서 확인하지 못해 작성용 근거에서 제외]

해석 한계: 동일 동작 확인은 포팅 직후의 검증 결과이며, 이후 최적화 버전들에서의 수치 일치 여부는 각 측정 출력의 bound 값이 같은지로만 확인된다.

- 조건: 원본 파일: lirpa_forward_backward_fc_array.cpp
- 조건: 병렬 연산이 필요한 부분만 kernel 함수로 교체
- 조건: 포팅 직후 컴파일·실행 검증
- 확인 필요 수치 (작성 제외): 포팅 직후 동작 검증 결과 = 동일하게 동작함  — 수치 표기를 연결 원문에서 확인하지 못했습니다.

출처: 1쪽 · p1:e5

> 그 럼 lirpa_forward_backward_fc_array.cpp 에서 기본 틀을 가져와서 병렬 연산이 필요한
> 부분만
> kernel 함수로 바꾸면 되지 않을까? (이 때 kernel 함수란 device, 즉 GPU에서 동작하는
> 코드를 의미)

출처: 1쪽 · p1:e16

> m at_add 부터 배열을 통한 연산을 하고 있음 ⇐ 포팅을 해봤다..

출처: 2쪽 · p2:e18

> 최 종 포팅, 컴파일, 실행 검증 완료(동일하게 동작함)

## F03 · 구현·방법 · 해석

신경망은 Fully Connected 구조이며 입력 256개(16×16), 은닉층 2개(N^(1)=491, N^(2)=491), 출력 16개로 구성된다. 1차 목표는 테스트 데이터 1개와 eps=10^-6으로 CROWN 알고리즘을 돌려 16개 출력을 뽑는 것이다.

원문 대조: 일부만 뒷받침 — 신경망 구조(FC, 입력 256, 은닉 491/491, 출력 16)와 1차 목표(테스트 데이터 1개, eps=10^-6로 CROWN 돌려 16개 출력)는 교수 안내 메시지에서 제시된 가정값으로 원문에 있으나, 실제 모델 파일 로드 후 확인된 값인지는 별도 명시가 없어 가정/안내 수준으로만 지지된다. [코드 검사: 측정값 1개를 원문에서 확인하지 못해 작성용 근거에서 제외]

해석 한계: 층별 뉴런 수와 입력/출력 차원은 교수 안내 메시지에서 제시된 가정값이며, 실제 모델 파일 로드 후 확인된 값인지는 별도 명시가 없다.

- 조건: 신경망 구조: Fully Connected
- 조건: 입력: N^(0)=256 (16×16)
- 조건: 은닉층: N^(1)=491, N^(2)=491
- 조건: 출력: N^(3)=16
- 조건: 1차 목표: 테스트 데이터 1개, eps=10^-6로 CROWN 수행 후 16개 출력 추출
- 측정: 입력 차원 = 256  (교수 안내 기준 (16×16)) / p2:e28
- 측정: 은닉층 1 뉴런 수 = 491  (교수 안내 기준) / p2:e28
- 측정: 은닉층 2 뉴런 수 = 491  (교수 안내 기준) / p2:e28
- 측정: 출력 차원 = 16  (교수 안내 기준) / p2:e28
- 확인 필요 수치 (작성 제외): CROWN eps = 1e-06  — 수치 표기를 연결 원문에서 확인하지 못했습니다.

출처: 2쪽 · p2:e28

> ![image](/image/placeholder)
> 최광훈 안테나 선택 신경망은 Fully Connected 구조이고요. 1 Fully Layer Fully Layer Fully Layer Fully 2 Layers and the Output Layer Number of neurons of FCN. We assumed Ny - 8, Ng - TI Thus the length of input vector is NR × Ng ■ 256. layer index / O(input) 1 2 3(output) number of neurons N(0) = 256 N(1) = 491 N(2) ■ 491 N(3) = 16 오후 5:08 최광훈 입력 N^(0)=256개 (16x16), 출력 N^(3)=16개 히든 계층은 2개인데, N^(1)=491, N^(2)=491이에요. 일단 한번 살펴보고 궁금한게 있으면 언제든지 바로 바로 질문하세요~ 오후 5:09 최광훈 즉, crown 알고리즘의 입력으로 테스트 데이터 1개와 eps=10^-6으로 crown 알고리즘을 돌려서 16개 출력을 뽑는 것을 1차 목표로! 혹시 궁금한 사항이 있으면, 나한테 물어봐도 되고 또는 김송헌 학생한테 물어봐도 됩니다~ 오후 5:14

출처: 2쪽 · p2:e29

> 아 마 my_lirpa.cu에 실제 신경망을 로드(기존에는 가상 신경망을 사용했음) 해서.. 16개
> 출력을 뽑는 것을 1차 목표로 하라는 말씀 같음

## F04 · 측정 결과 · 관측 기록

CROWN 검증의 단일 실행 경과 시간은 CPU only 버전이 101.237800ms, GPU only 버전(my_lirpa.cu, 모든 병렬 함수를 커널로 교체)이 353.057200ms로, 초기 GPU 버전이 CPU보다 느렸다.

원문 대조: 원문 뒷받침 — CPU only와 GPU only 초기 버전의 단일 실행 경과 시간이 각 실행 출력의 Elapsed time으로 제시되어 있어 진술과 일치한다. 다만 CPU only 96ms라는 별도 정리값(p8:e73)은 동일 구간인지 확인이 필요하다는 한계가 있다.

해석 한계: 수치는 각 실행 출력에 표시된 Elapsed time 기준이며, 측정 반복 횟수·웜업 여부·머신 상태는 버전마다 다를 수 있다. CPU only 96ms라는 별도 정리값(p8:e73)과는 동일 구간인지 확인이 필요하다.
자동 원문 대조: CPU only와 GPU only 초기 버전의 단일 실행 경과 시간이 각 실행 출력의 Elapsed time으로 제시되어 있어 진술과 일치한다. 다만 CPU only 96ms라는 별도 정리값(p8:e73)은 동일 구간인지 확인이 필요하다는 한계가 있다.

- 조건: CROWN 검증 단일 실행
- 조건: eps = 1e-06
- 조건: CPU only 버전 vs GPU only 버전(my_lirpa.cu, 모든 병렬 함수를 커널로 교체)
- 측정: Elapsed time = 101.237800 ms (CPU only (no GPU) 단일 실행) / p3:e35
- 측정: Elapsed time = 353.057200 ms (GPU only (my_lirpa.cu, 모든 병렬 함수 커널 교체) 단일 실행) / p4:e37

출처: 3쪽 · p3:e35

> ![image](/image/placeholder)
> Starting CROWN Verification (eps = 1e-06) ** MODE: CPU ONLY (no GPU) ** calc success Elapsed time: 101.237800 ms Output Dimension: 16 [Index] | Lower Bound | Upper Bound | Normal Pred (y) [ 0] [ 1] 2] 3] 4] 5] 6] 7] 8] 9] 10] [ 11] [ 12] [ 13] [ 14] [ 15] 0.081772 0.273538 0.102147 0.114244 2.670552 1.846574 -1.714750 -1.880139 0.706986 -2.612086 0.003713 1.310476 2,049539 -1.025923 1.082576 -3,404772 0.082159 0.273823 0.102482 0.114541 2.670843 1.846872 -1,714490 -1.879695 0.707275 -2.611722 0.003976 1.310817 2,049839 -1.025597 1.082852 -3,404355 0.081966 0.273680 0.102314 0.114393 2.670697 1.846723 -1.714620 -1.879916 0.707131 -2.611904 0.003845 1,310646 2,049689 -1.025760 1,082714 -3,404563

출처: 4쪽 · p4:e37

> ![image](/image/placeholder)
> Starting CROWN Verification (eps = 1e-06) clear |irpa_forward! calc success Elapsed time: 353.057200 ms Output Dimension: 16 [Index] | Lower Bound | Upper Bound | Normal Pred (y) [ 0] 1] 2] 3] 4] 5] 6] 7] 8] 9] 10] 11] 12] 13] 14] 15] 0.081772 0.273538 0.102147 0.114244 2.670552 1.846574 -1.714750 -1.880139 0.706986 -2.612086 0.003713 1.310476 2,049539 -1.025923 1.082576 -3,404772 0.082159 0.273823 0.102482 0.114541 2,670843 1.846872 -1,714490 -1.879695 0.707275 -2.611722 0.003976 1.310817 2,049839 -1.025597 1.082852 -3,404355 0.081966 0.273680 0.102314 0.114393 2.670697 1.846723 -1.714620 -1.879916 0.707131 -2.611904 0.003845 1.310646 2,049689 -1.025760 1,082714 -3,404563

출처: 8쪽 · p8:e73

> v 0 : 단독 CPU 처리 , 96ms

## F05 · 측정 결과 · 관측 기록

cuBLAS로 행렬곱을 대체하고 메모리 풀을 도입하며 벡터 연산을 CPU로 되돌린 최적화 버전(GPU OPTIMIZED, crown_test_op_only_GPU.cu)은 229.691800ms로 약 100ms 줄었지만 여전히 CPU보다 느렸다.

원문 대조: 일부만 뒷받침 — GPU OPTIMIZED 버전(cuBLAS matmul 대체, 메모리 풀 사용, 벡터 연산 CPU화)의 단일 실행 경과 시간이 229.691800ms로 원문에 제시되어 있으며, 작성자가 약 100ms 줄었지만 여전히 CPU보다 느리다고 진술한 점과 부합한다. 개별 최적화 항목의 기여도는 분리 측정되지 않았다. [코드 검사: 측정값 1개를 원문에서 확인하지 못해 작성용 근거에서 제외]

해석 한계: 적용된 최적화 항목(1. cuBLAS matmul 대체, 2. 메모리 풀 사용, 3. 벡터 연산 CPU화)은 작성자가 명시한 내용이며, 각 항목의 개별 기여도는 분리 측정되지 않았다.

- 조건: GPU OPTIMIZED 버전(crown_test_op_only_GPU.cu)
- 조건: 최적화 항목: 1) cuBLAS matmul 대체, 2) 메모리 풀 사용, 3) 벡터 연산 CPU화
- 조건: 단일 실행 기준
- 확인 필요 수치 (작성 제외): Elapsed time = 229.691800 ms — 수치 표기를 연결 원문에서 확인하지 못했습니다.

출처: 5쪽 · p5:e43

> ![image](/image/placeholder)
> Starting CROWN Verification (eps = 1e-06) ** MODE: GPU OPTIMIZED (cuBLAS + Pool) ** calc success Elapsed time: 229,691800 ms Output Dimension: 16 [Index] | Lower Bound | Upper Bound | Normal Pred (y) [ 0] 1] 2] 3] 4] 5] 6] 7] 8] 9] 10] 11] 12] [ 13] [ 14] [ 15] 0.081772 0.082159 0.273538 0.273823 0.102147 0.102482 0.114244 0.114541 2.670552 2,670843 1.846574 1.846872 -1.714750 -1,714490 -1.880139 -1.879695 0.706986 0.707275 -2.612086 -2.611722 0.003713 0.003976 1.310476 1.310817 2,049539 2,049839 -1.025923 -1.025597 1,082576 1,082852 -3,404772 | -3,404355 C: :₩UsersMuser\Desktop#cuda#crown: 0.081966 0.273680 0.102314 0.114393 2.670697 1.846723 -1.714620 -1.879916 0.707131 -2.611904 0.003845 1,310646 2,049689 -1.025760 1,082714 -3,404563

출처: 5쪽 · p5:e45

> 1. cuBLAS로 matmul 대체
> 2. 메모리 풀 사용 (미리 큰 공간을 할당해서 빌려주는 형식으로 함, 대신 함수 호출마다
> 메모리 할당, 해제를 없앰)
> 3. 벡터 연산을 CPU로 바꿈

출처: 5쪽 · p5:e46

> 2 29.691ms로 100ms정도 줄었지만 여전히 CPU보다 느림

## F06 · 측정 결과 · 관측 기록

하이브리드 버전(HYBRID, matmul만 GPU/cuBLAS, 나머지 CPU)은 201.670100ms, 하이브리드 V2(cuBLAS 예열, 가중치 GPU 사전 업로드, 필요한 부분만 복사)는 85.785300ms로 CPU보다 빨라졌다.

원문 대조: 일부만 뒷받침 — HYBRID(matmul만 GPU/cuBLAS, 나머지 CPU)와 HYBRID V2(cuBLAS 예열, 가중치 GPU 사전 업로드, 필요한 부분만 복사)의 단일 실행 경과 시간이 각각 원문에 제시되어 진술과 일치한다. 다만 V2의 CPU 대비 우위는 반복 측정 조건에 따라 달라질 수 있다는 한계가 있다. [코드 검사: 측정값 1개를 원문에서 확인하지 못해 작성용 근거에서 제외]

해석 한계: V2의 85ms 개선은 단일 실행 기준이며, 이후 500회 반복 측정에서는 hybrid V2가 CPU보다 느려진 구간도 있어 반복 측정·캐시·웜업 조건에 따라 결과가 달라진다.

- 조건: HYBRID: matmul=GPU, rest=CPU
- 조건: HYBRID V2: cuBLAS 예열, 가중치 GPU 사전 업로드, 필요한 부분만 복사
- 조건: 단일 실행 기준
- 측정: Elapsed time = 201.670100 ms (HYBRID (matmul=GPU, rest=CPU) 단일 실행) / p6:e48
- 확인 필요 수치 (작성 제외): Elapsed time = 85.785300 ms — 수치 표기를 연결 원문에서 확인하지 못했습니다.

출처: 6쪽 · p6:e48

> ![image](/image/placeholder)
> Starting CROWN Verification (eps = 1e-06) ** MODE: HYBRID (matmul=GPU, rest=CPU) ** calc success Elapsed time: 201.670100 ms Output Dimension: 16 [Index] | Lower Bound | Upper Bound | Normal Pred (y) [ 0] 1] 2] 3] 4] 5] 6] 7] 8] 9] 10] 11] 12] 13] 14] [ 15] 0.081772 | 0.273538 0.102147 0.114244 2.670552 1.846574 -1.714750 -1.880139 0.706986 -2.612086 0.003713 1,310476 2,049539 -1.025923 1.082576 -3,404772 0.082159 | 0.273823 0.102482 0.114541 2,670843 1.846872 -1,714490 -1.879695 0.707275 -2.611722 0.003976 1.310817 2,049839 -1.025597 1.082852 -3,404355 0.081966 0.273680 0.102314 0.114393 2.670697 1.846723 -1.714620 -1.879916 0.707131 -2.611904 0.003845 1.310646 2.049689 -1.025760 1.082714 -3,404563

출처: 6쪽 · p6:e49

> 2 01.670ms , 조금 줄었다. , 여전히 cpu보다 느림

출처: 7쪽 · p7:e54

> ![image](/image/placeholder)
> Starting CROWN Verification (eps = 1e-06) ** MODE: HYBRID V2 ** calc success Elapsed time: 85,785300 ms Output Dimension: 16 [Index] | Lower Bound | Upper Bound | Normal Pred (y) [ 0] [ 1] 2] 3] 4] 5] 6] 7] 8] 9] 10] 11] 12] [ 13] [ 14] [ 15] 0.081772 0.273538 0.102147 0.114244 2.670552 1,846574 -1.714750 -1.880139 0.706986 -2,612086 0.003713 1.310476 2,049539 -1.025923 1.082576 -3,404772 0.082159 0.273823 0.102482 0.114541 2,670843 1,846872 -1,714490 -1.879695 0.707275 -2.611722 0.003976 1,310817 2,049839 -1.025597 1.082852 -3,404355 0.081966 0.273680 0.102314 0.114393 2.670697 1.846723 -1.714620 -1.879916 0.707131 -2.611904 0.003845 1,310646 2,049689 -1.025760 1.082714 -3,404563

## F07 · 측정 결과 · 해석

가중치 GPU 사전 업로드(preload)로 보였던 50ms 가량의 단축은 실제 가중치 활용 효과보다 cudaMalloc/cudaMemcpy 호출이 타이머 이전에 발생하면서 CUDA 컨텍스트 초기화, 클럭 부스팅, JIT 컴파일 등 웜업 비용이 측정 구간 밖으로 빠진 영향으로 해석되었다.

원문 대조: 일부만 뒷받침 — preload로 보였던 50ms 단축이 실제 가중치 활용보다 CUDA 컨텍스트 초기화·클럭 부스팅·JIT 컴파일 등 웜업 비용이 타이머 밖으로 빠진 영향이라는 해석은 원문에 작성자의 추론으로 제시되어 있다. 가중치 활용 자체의 효과가 크지 않았다는 보고(500회 누적 5~10ms 우세)도 함께 원문에 있다. [코드 검사: 측정값 2개를 원문에서 확인하지 못해 작성용 근거에서 제외]

해석 한계: 웜업 원인 분석은 작성자의 추론이며, preload 버전과 mempool 버전의 측정 구간 차이에서 도출된 해석이다. 가중치 활용 자체의 효과는 500회 누적에서 5~10ms 우세 수준으로 크지 않았다고 보고되었다.

- 조건: preload 버전과 mempool 버전의 측정 구간 차이
- 조건: pre_upload_weights_to_gpu가 t_start 앞에서 cudaMalloc/cudaMemcpy 호출
- 조건: 500회 누적에서 가중치 활용 효과는 5~10ms 우세 수준
- 확인 필요 수치 (작성 제외): preload 관련 단축 폭(관찰) = 50ms  — 수치 표기를 연결 원문에서 확인하지 못했습니다.
- 확인 필요 수치 (작성 제외): 500회 누적 가중치 활용 우세 = 5~10ms  — 수치 표기를 연결 원문에서 확인하지 못했습니다.

출처: 13쪽 · p13:e106

> 아 .. preload를 하면서 GPU가 웜업 되는 것이 원인이었다..

출처: 13쪽 · p13:e108

> ![image](/image/placeholder)
> 50ms가 줄어든 진짜 이유: CUDA 컨텍스 트 초기화 웜업 효과 pre_upload_weights_to_gpu 가 t_start 앞에서 cudaMalloc 과 cudaMemcpy 를 호출 하면, 이 시점에 CUDA 드라이버가 처음 깨어 나면서: 1. GPU 컨텍스트 초기화 (CUDA 드라이버 로드) 2. GPU 클럭 부스팅 (저전력 → 최대 성능 주 파수로 전환) 3. JIT 컴파일 (커널 코드 첫 번째 컴파일) 이 세 가지 초기화 비용이 전부 타이머 구간 밖으로 빠져나가게 됩니다. 반면 mempool 버전에서는 ensure_pool() → 첫 번째 cudaMalloc 이 t_start 안에 들어있어서, 저 초기화 비용 이 전부 측정에 포함됩니다. mempool 버전: [초기화 50ms] + [실 제 연산] = 측정됨 preload 버전: [초기화 50ms] + [실제 연산] = 초기화는 타이머 밖! 즉, d_W 를 활용해서 빨라진 게 아니라, pre_upload_weights_to_gpu 가 의도치 않 게 GPU 웜업 역할을 하면서 초기화 비용을 타이머 밖으로 밀어낸 것입니다. first_try 에서 warmup_cublas() 를 명시적으로 두었 던 것도 이 이유 때문이었습니다.

출처: 14쪽 · p14:e116

> 5 00 회 정도 하니까 5~10ms 정도 우세함..

## F08 · 측정 결과 · 관측 기록

메모리 풀 + 웜업 조합만으로 거의 200ms가 단축되었고, make_zero_matrix/make_zero_vector를 CPU로 되돌리고 결과 벡터·행렬의 불필요한 memcpy를 제거하면서 추가 단축이 이루어져 최종 측정값은 115.469900ms까지 내려갔다.

원문 대조: 일부만 뒷받침 — 메모리 풀 + 웜업 조합으로 거의 200ms 단축, make_zero_matrix/make_zero_vector CPU 회귀와 불필요한 memcpy 제거로 추가 단축되어 최종 115.469900ms까지 내려갔다는 진술은 원문의 측정값과 서술에 의해 지지된다. 다만 115.469900ms는 해당 최적화 조합의 단일 실행값이며, CPU only 500회 평균 78.296988ms 구간도 보고되어 반복 측정 조건에 따라 우위 여부가 달라질 수 있다. [코드 검사: 측정값 2개를 원문에서 확인하지 못해 작성용 근거에서 제외]

해석 한계: 115.469900ms는 mempool + warmup + CPU 회귀 + memcpy 제거가 적용된 버전의 단일 실행 측정값이며, CPU only와의 최종 우위 여부는 반복 측정 조건에 따라 달라질 수 있다. CPU only 500회 평균은 78.296988ms로 보고된 구간도 있다.

- 조건: 적용 요소: 메모리 풀 + warmup + CPU 회귀(make_zero_matrix/make_zero_vector) + 불필요한 memcpy 제거
- 조건: 단일 실행 기준
- 조건: CPU only 500회 평균 78.296988ms 보고 구간 존재
- 확인 필요 수치 (작성 제외): Elapsed time = 128.894800 ms — 수치 표기를 연결 원문에서 확인하지 못했습니다.
- 확인 필요 수치 (작성 제외): Elapsed time = 115.469900 ms — 수치 표기를 연결 원문에서 확인하지 못했습니다.

출처: 19쪽 · p19:e137

> my_lirpa_optimizing.cu
> 그럼 여기까지 확실한건 메모리 풀 + warm up 조합은 일단 매우 좋다는 것 (두 개만으로
> 거의 200ms 단축함) // my_lirpa_mempool_warmup.cu

출처: 19쪽 · p19:e141

> ![image](/image/placeholder)
> Starting CROWN Verification (eps = 1e-06) mempool + warmup calc success Elapsed time: 128,894800 ms Output Dimension: 16 [Index] | Lower Bound | Upper Bound | Normal Pred (y) 0] 1] 3] 4] 5] 6] 7] 8] 9] 10] 11] 12] 13] 14] 15] 0.081772 0.273538 0.102147 0.114244 2.670552 1.846574 -1.714750 -1.880139 0.706986 -2.612086 0.003713 1,310476 2,049539 -1.025923 1,082576 -3,404772 0.082159 0.273823 0.102482 0.114541 2.670843 1.846872 -1,714490 -1.879695 0.707275 -2.611722 0.003976 1.310817 2,049839 -1.025597 1,082852 -3,404355 계속하려면 아무 키나 누르십시오 · 0.081966 0.273680 0.102314 0.114393 2.670697 1.846723 -1.714620 -1.879916 0.707131 -2.611904 0.003845 1.310646 2,049689 -1.025760 1,082714 -3,404563 ·

출처: 19쪽 · p19:e142

> 2 2 ~ 25ms 정도 줄었다!! 이것만으로도 …

## F09 · 측정 결과 · 관측 기록

forward 함수의 DTOH memcpy를 극단적으로 제거한 후 CROWN 검증(eps=1e-6, 출력 차원 16) 실행 시간이 약 103ms에서 약 64ms로 감소했다.

원문 대조: 원문 뒷받침 — p21:e148에서 CROWN 검증 실행 시간이 103,741500 ms로 기록되고, p21:e149에서 '103ms 정도'로 언급되며, p22:e150에서 forward 함수의 DTOH memcpy를 극단적으로 제거했다는 조치가 함께 서술되어 있어 진술의 전후 관계와 수치가 원문 내에서 연결된다. 다만 측정 환경·반복 조건은 명시되지 않아 변동 가능성은 남는다.

해석 한계: 측정 환경·반복 조건에 따라 변동 가능. 단일 시점 측정값.
자동 원문 대조: p21:e148에서 CROWN 검증 실행 시간이 103,741500 ms로 기록되고, p21:e149에서 '103ms 정도'로 언급되며, p22:e150에서 forward 함수의 DTOH memcpy를 극단적으로 제거했다는 조치가 함께 서술되어 있어 진술의 전후 관계와 수치가 원문 내에서 연결된다. 다만 측정 환경·반복 조건은 명시되지 않아 변동 가능성은 남는다.

- 조건: CROWN 검증 (eps = 1e-06)
- 조건: 출력 차원 16
- 측정: Elapsed time = 103,741500 ms ms (CROWN Verification (eps = 1e-06), Output Dimension: 16) / p21:e148
- 측정: Elapsed time (요약) = 103ms ms (CROWN Verification (eps = 1e-06), Output Dimension: 16) / p21:e149

출처: 21쪽 · p21:e148

> ![image](/image/placeholder)
> Starting CROWN Verification (eps = 1e-06) mempool + warmup calc success Elapsed time: 103,741500 ms Output Dimension: 16 [Index] | Lower Bound | Upper Bound | Normal Pred (y) 3] 5] 6] 7] 8] 9] 10] 11] 12] 13] 14] 15] 0.081772 0.273538 0.102147 0.114244 2.670552 1.846574 -1.714750 -1.880139 0.706986 -2.612086 0.003713 1,310476 2,049539 -1.025923 1,082576 -3,404772 0.082159 0.273823 0.102482 0.114541 2,670843 1.846872 -1,714490 -1.879695 0.707275 -2.611722 0.003976 1,310817 2,049839 -1.025597 1,082852 -3,404355 0.081966 0.273680 0.102314 0.114393 2.670697 1.846723 -1.714620 -1.879916 0.707131 -2.611904 0.003845 1,310646 2,049689 -1.025760 1,082714 -3,404563

출처: 21쪽 · p21:e149

> (결과 103ms 정도로 이제 거의 cpu와 비슷해졌다)

출처: 22쪽 · p22:e150

> 이제 forward 함수에서 DTOH하는 memcpy를 극단적으로 없앴다.

## F10 · 측정 결과 · 관측 기록

CUDA 동기화(cudaDeviceSynchronize)를 필요한 부분만 남기고 제거한 결과 실행 시간이 약 1ms 감소했다(26.5291ms → 25.4572ms).

원문 대조: 원문 뒷받침 — p26:e180에서 cudaDeviceSynchronize 제거 조치가, p26:e181에서 실행 시간 25,457200 ms 기록이, p26:e182에서 '1 ms 정도 줄었다'는 진술이 함께 제시되어 있어 감소폭과 수치가 원문 내에서 연결된다. 감소 전 값 26.5291ms는 진술에만 등장하고 해당 측정 시점의 동일 형식 기록은 원문에 보이지 않는다.

해석 한계: 측정 시점 기준. 감소폭은 1ms 수준.

- 조건: CROWN 검증 (eps = 1e-06)
- 조건: 출력 차원 16
- 측정: Elapsed time = 25,457200 ms ms (CROWN Verification (eps = 1e-06), Output Dimension: 16) / p26:e181
- 측정: Elapsed time 감소폭 = 1 ms ms (cudaDeviceSynchronize 제거 전후 비교) / p26:e182

출처: 26쪽 · p26:e180

> 동기화 (cudaDeviceSynchronize) 제거
> 필요한 부분을 제외하고 동기화 코드 제거함

출처: 26쪽 · p26:e181

> ![image](/image/placeholder)
> Starting CROWN Verification (eps = 1e-06) mempool + warmup calc success Elapsed time: 25,457200 ms Output Dimension: 16 [Index] | Lower Bound | Upper Bound | Normal Pred (y) 0] 1] 3] 5] 6] 7] 8] 9] 10] 11] 12] 13] 14] 15] 0.081772 0.273538 0.102147 0.114244 2.670552 1,846574 -1.714750 -1,880139 0.706986 -2.612086 0.003713 1,310476 2,049539 -1.025923 1.082576 -3,404772 0.082159 0.273823 0.102482 0.114541 2,670843 1.846872 -1,714490 -1.879695 0.707275 -2.611722 0.003976 1.310817 2,049839 -1.025597 1.082852 -3,404355 0.081966 0.273680 0.102314 0.114393 2.670697 1.846723 -1.714620 -1.879916 0.707131 -2.611904 0.003845 1.310646 2,049689 -1.025760 1,082714 -3,404563

출처: 26쪽 · p26:e182

> 1 ms 정도 줄었다

## F11 · 측정 결과 · 관측 기록

cuBlas 도입 후 실행 시간이 약 40ms로 다시 늘어났고, cuSparse로 spMV만 적용한 경우에도 약 27ms로 더 느려졌으며, spMM까지 도입하면 약 38.58ms로 회귀했다.

원문 대조: 원문 뒷받침 — p26:e184에서 cuBlas 도입 후 결과가 좋지 않았다는 진술이, p27:e188에서 실행 시간 40,050500 ms 기록이, p27:e189에서 '40ms 정도로 다시 시간이 늘어남'이라는 진술이 함께 제시되어 있어 cuBlas 관련 증가 주장은 원문 내에서 연결된다. cuSparse spMV 약 27ms, spMM 약 38.58ms라는 세부 수치는 진술에만 등장하고 해당 측정 기록의 동일 형식 원문은 이 후보 연결 범위 내에서 확인되지 않는다.

해석 한계: 현재 모델 크기와 호출 패턴에서 측정된 결과이며, 라이브러리 함수 선택에 따라 결과가 달라질 수 있음.

- 조건: CROWN 검증 (eps = 1e-06)
- 조건: 출력 차원 16
- 측정: Elapsed time = 40,050500 ms ms (CROWN Verification (eps = 1e-06), Output Dimension: 16) / p27:e188

출처: 26쪽 · p26:e184

> cuBlas 도입함.. 근데 오히려 결과가 안좋음

출처: 27쪽 · p27:e188

> ![image](/image/placeholder)
> Starting CROWN Verification (eps = 1e-06) mempool + warmup calc success Elapsed time: 40,050500 ms Output Dimension: 16 [Index] | Lower Bound | Upper Bound | Normal Pred (y) 1] 2] 3] 4] 5] 6] 7] 8] 9] 10] 11] 12] 13] 14] 15] 0.903952 0.990928 -0.591686 0.324877 2,829982 2,199842 -2,379492 -1,422470 0.788409 -2.194350 1.078205 3.603885 3,004923 -1.185600 1,494055 -3,060963 0.904427 0.991328 -0.591280 0.325260 2,830317 2,200121 -2.379074 -1.421962 0.788821 -2.193915 1.078522 3,604276 3,005297 -1.185184 1,494391 -3.060550 0.081966 0.273680 0.102314 0.114393 2.670697 1.846723 -1.714620 -1.879916 0.707131 -2.611904 0.003845 1.310646 2,049689 -1.025760 1,082714 -3,404563

출처: 27쪽 · p27:e189

> 4 0ms 정도로 다시 시간이 늘어남

## F12 · 한계 · 해석

cuBlas/cuSparse 실험 결과 현재 모델 크기와 호출 패턴에서는 느려져 현 기준 코드에는 포함하지 않았으며, 추후 재도입 시도가 필요하다고 정리했다.

원문 대조: 원문 뒷받침 — p30:e206에서 cuBLAS/cuSPARSE가 현재 모델 크기와 호출 패턴에서 느려져 현 기준 코드에 포함하지 않았고 추후 재도입 시도가 필요하다는 정리가, p31:e209에서 신경망 크기가 매우 작고 오버헤드가 생겼다는 해석이, p31:e210에서 기본 형태 함수만 사용했으며 변형 함수들과 Nsight compute 분석이 필요하다는 여지가 함께 제시되어 있어 진술의 취지가 원문 내에서 연결된다.

해석 한계: 소규모 신경망에서의 실험 기준. 함수 변형 및 Nsight Compute 분석과 함께 재검토 예정.

- 조건: 소규모 신경망
- 조건: cuBLAS/cuSPARSE 기본 형태 행렬곱 함수 사용

출처: 30쪽 · p30:e206

> c uBLAS와 cuSPARSE는 실험했지만 현재 모델 크기와 호출 패턴에서는 느려졌으므로, 현
> 기준 코드에는 포함하지 않은 상태, 후에 다시 도입해보는 시도가 필요함

출처: 31쪽 · p31:e209

> 1. 신경망의 크기가 매우 작다.
> 2. cuBlas, cuSparse 의 동작 방식에서 오버헤드가 생겼다. (이 또한 신경망이 작기
> 때문에)

출처: 31쪽 · p31:e210

> 아 직 실험해볼 여지는 많다. 현재까지는 cuBlas, cuSparse에 있는 기본적인 형태의 행렬곱
> 연산 함수를 사용했는데, 행렬곱에도 변형 함수들이 매우 많다. ⇐ sm 내의 분석과 함께
> 사용해야 하는 함수들이라 Nsight compute 분석때 같이 진행하면 될 듯?

## F13 · 구현·방법 · 구현 기록

backward_bound_gpu의 affine 중복 계산 삭제, new_(upper,lower)_p 복사 대신 std::swap 포인터 스와핑, backward 행렬곱 커널 2개를 하나로 합친 backward_matmul_pair_gpu 도입, build_coeff_pair_fused_gpu 및 backward_bias_pair_fused_gpu 커널 퓨전을 적용했다.

원문 대조: 원문 뒷받침 — p32:e222에 backward_bound_gpu의 affine 중복 계산 삭제, new_(upper,lower)_p 복사 대신 std::swap 포인터 스와핑, backward_matmul_pair_gpu 커널 통합, build_coeff_pair_fused_gpu 및 backward_bias_pair_pair_fused_gpu 커널 퓨전 적용이 나열되어 있어 진술된 적용 범위가 원문 내에서 확인된다. backward_matmul_pair_gpu 관련 '22ms 보이는 비율이 늘었다', '최저점(28ms)도 잘 안 보이게 됐다'는 체감 서술도 동일 원문에 포함된다.

해석 한계: 적용 범위는 backward_bound_gpu 및 관련 커널 함수 중심.
자동 원문 대조: p32:e222에 backward_bound_gpu의 affine 중복 계산 삭제, new_(upper,lower)_p 복사 대신 std::swap 포인터 스와핑, backward_matmul_pair_gpu 커널 통합, build_coeff_pair_fused_gpu 및 backward_bias_pair_pair_fused_gpu 커널 퓨전 적용이 나열되어 있어 진술된 적용 범위가 원문 내에서 확인된다. backward_matmul_pair_gpu 관련 '22ms 보이는 비율이 늘었다', '최저점(28ms)도 잘 안 보이게 됐다'는 체감 서술도 동일 원문에 포함된다.

- 조건: backward_bound_gpu 및 관련 커널 함수 중심

출처: 32쪽 · p32:e222

> 1. backward_bound_gpu에서 사용하는 affine 중복 계산 삭제 (커널 2개 함수 줄어듦)
> 2. backward_bound_gpu에서 사용하는 new_(upper, lower)_p를 복사하지 않고 swap
> 함수를 이용해서 포인터 스와핑 (std::swap 이용)
> 3. backward 에서 사용하는 행렬곱 커널 2개를 하나로 합친 커널 함수 만듦 ,
> backward_matmul_pair_gpu ⇒ 22ms 보이는 비율이 늘었다.. 최저점(28ms)도 잘
> 안보이게 됐고 체감상, 효과가 있는듯
> 4. build_coeff_pair_fused_gpu 커널 퓨전
> 5. backward_bias_pair_fused_gpu 커널 퓨전

## F14 · 측정 결과 · 관측 기록

커널 퓨전과 set_shape 함수를 다른 커널에 직접 내장한 결과 CROWN 검증 실행 시간이 최저 약 21.3753ms까지 감소했다.

원문 대조: 원문 뒷받침 — p34:e226에서 커널 퓨전 + set_shape 함수를 다른 커널에 직접 내장한 조치가, p34:e227에서 실행 시간 21.375300 ms 기록이, p34:e228에서 '최저 21ms까지 가능하다'는 진술이 함께 제시되어 있어 최저치 감소 주장은 원문 내에서 연결된다. 23~26ms 변동 가능성은 진술에만 등장하고 해당 변동 구간의 동일 형식 측정 기록은 이 후보 연결 범위 내에서 확인되지 않는다.

해석 한계: 측정 환경에 따라 23~26ms 수준으로 변동하는 경우가 있다고 함께 기록됨.
자동 원문 대조: p34:e226에서 커널 퓨전 + set_shape 함수를 다른 커널에 직접 내장한 조치가, p34:e227에서 실행 시간 21.375300 ms 기록이, p34:e228에서 '최저 21ms까지 가능하다'는 진술이 함께 제시되어 있어 최저치 감소 주장은 원문 내에서 연결된다. 23~26ms 변동 가능성은 진술에만 등장하고 해당 변동 구간의 동일 형식 측정 기록은 이 후보 연결 범위 내에서 확인되지 않는다.

- 조건: CROWN 검증 (eps = 1e-06)
- 조건: 출력 차원 16
- 측정: Elapsed time = 21.375300 ms ms (CROWN Verification (eps = 1e-06), Output Dimension: 16) / p34:e227

출처: 34쪽 · p34:e226

> 커널 퓨전 + set_shape 함수를 다른 커널함수들에 직접 내장한 결과

출처: 34쪽 · p34:e227

> ![image](/image/placeholder)
> Starting CROWN Verification (eps = 1e-06) mempool + warmup calc success Elapsed time: 21.375300 ms Output Dimension: 16 [Index] | Lower Bound | Upper Bound | Normal Pred (y) 0] 1] 2] 3] 4] 5] 6] 7] 8] 9] 10] 11] 12] 13] 14] [ 15] 0.081772 0.273538 0.102147 0.114244 2.670552 1.846574 -1.714750 -1.880139 0.706986 -2.612086 0.003713 1,310476 2,049539 -1.025923 1.082576 -3,404772 0.082159 | 0.081966 0.273823 0.273680 0.102482 0.102314 0.114541 0.114393 2,670843 2.670697 1,846872 1.846723 -1,714490 -1.714620 -1.879695 -1.879916 0.707275 0.707131 -2.611722 -2.611904 0.003976 0.003845 1.310817 1.310646 2,049839 2.049689 -1.025597 -1.025760 1.082852 | 1,082714 -3,404355 | -3,404563

출처: 34쪽 · p34:e228

> 최 저 21ms 까지 가능하다!!

## F15 · 측정 결과 · 관측 기록

forward-backward 간 전달되는 alpha, beta 값을 메모리 풀에 올려 전달 과정을 삭제하고, bias도 메모리 풀에서 관리하도록 한 뒤 memcpy 호출이 109→94번으로 감소했으며, 21~23ms 구간에서 비교적 안정적으로 동작했다.

원문 대조: 원문 뒷받침 — p35:e230에서 forward-backward 간 alpha, beta 값을 메모리 풀에 올려 전달 과정을 삭제한 조치가, p36:e238에서 bias도 메모리 풀에서 관리하도록 한 뒤 21~23ms 내에서 특히 21ms에서 안정적으로 동작했다는 진술이, p36:e239에서 Nsight 구간 내 memcpy가 109⇒94번으로 감소했다는 기록이 함께 제시되어 있어 memcpy 감소와 안정 구간 주장은 원문 내에서 연결된다. '성능의 최고점이 오른지는 모르겠는데'라는 불확실성 서술도 동일 원문에 포함된다.

해석 한계: memcpy 감소 횟수와 안정 구간은 Nsight 구간 및 측정 시점 기준.

- 조건: CROWN 검증 (eps = 1e-06)
- 조건: 출력 차원 16
- 조건: Nsight 구간 기준
- 측정: memcpy 호출 횟수 = 109 회 (Nsight 구간 내, 감소 전) / p36:e239
- 측정: memcpy 호출 횟수 = 94 회 (Nsight 구간 내, 감소 후) / p36:e239

출처: 35쪽 · p35:e230

> forward - backward 간에 전달되는 alpha, beta 값을 메모리 풀에 올려서 전달 과정 삭제함

출처: 36쪽 · p36:e238

> b ias 도 메모리 풀에서 관리 하도록 함
> 성능의 최고점이 오른지는 모르겠는데 ,
> 21 ~ 23ms 내에서 (특히 21 ms) 꽤 안정적으로 동작함

출처: 36쪽 · p36:e239

> N VTX 구간 내에서 memcpy 가 109 ⇒ 94 번 호출, 15번 감소

## F16 · 측정 결과 · 관측 기록

backward 호출 시 forward 중간 결과를 CPU로 복사할지 여부를 플래그로 제어(false 시 memcpy 현저히 감소)하여 실행 시간이 약 17.2236ms로 줄었고, memcpy 호출 횟수도 66→56회로 감소했다.

원문 대조: 원문 뒷받침 — p36:e241에서 backward 호출 시 forward 중간 결과를 CPU에 복사할지 여부의 플래그 도입 조치가, p36:e242에서 false 시 memcpy가 현저히 줄어든다는 진술이, p36:e243에서 실행 시간 17.223600 ms 기록이 함께 제시되어 있어 플래그 적용 후 실행 시간 감소 주장은 원문 내에서 연결된다. memcpy 66⇒56회 감소 및 감소 전 실행 시간 약 17.2236ms 대비 이전 값은 진술에만 등장하고 해당 측정 기록의 동일 형식 원문은 이 후보 연결 범위 내에서 확인되지 않는다.

해석 한계: 플래그 적용 여부에 따른 비교. memcpy 횟수는 Nsight 기준.
자동 원문 대조: p36:e241에서 backward 호출 시 forward 중간 결과를 CPU에 복사할지 여부의 플래그 도입 조치가, p36:e242에서 false 시 memcpy가 현저히 줄어든다는 진술이, p36:e243에서 실행 시간 17.223600 ms 기록이 함께 제시되어 있어 플래그 적용 후 실행 시간 감소 주장은 원문 내에서 연결된다. memcpy 66⇒56회 감소 및 감소 전 실행 시간 약 17.2236ms 대비 이전 값은 진술에만 등장하고 해당 측정 기록의 동일 형식 원문은 이 후보 연결 범위 내에서 확인되지 않는다.

- 조건: CROWN 검증 (eps = 1e-06)
- 조건: 출력 차원 16
- 조건: forward 중간 결과 CPU 복사 여부 플래그 제어
- 측정: Elapsed time = 17.223600 ms ms (CROWN Verification (eps = 1e-06), Output Dimension: 16) / p36:e243

출처: 36쪽 · p36:e241

> backward 호출시 forward를 호출하는데, forward의 중간 결과를 CPU (메모리)에
> 복사(memcpy)하는 여부의 플래그를 도입

출처: 36쪽 · p36:e242

> ( false로 할 경우 memcpy 가 현저히 줄어듦)

출처: 36쪽 · p36:e243

> ![image](/image/placeholder)
> Starting CROWN Verification (eps = 1e-06) mempool + warmup calc success Elapsed time: 17.223600 ms Output Dimension: 16 [Index] | Lower Bound | Upper Bound | Normal Pred (y) 0] 1] 2] 3] 4] 5] 6] 7] 8] 9] 10] 11] 12] 13] [ 14] 15] 0.081772 0.273538 0.102147 0.114244 2.670552 1.846574 -1.714750 -1.880139 0.706986 -2.612086 0.003713 1,310476 2,049539 -1.025923 1,082576 -3,404772 0.082159 0.273823 0.102482 0.114541 2,670843 1.846872 -1,714490 -1.879695 0.707275 -2.611722 0.003976 1,310817 2,049839 -1.025597 1.082852 -3,404355 0.081966 0.273680 0.102314 0.114393 2.670697 1.846723 -1.714620 -1.879916 0.707131 -2.611904 0.003845 1,310646 2,049689 -1.025760 1,082714 -3,404563

## F17 · 구현·방법 · 구현 기록

기존 backward_bound_gpu는 GPU 계산 결과를 CPU로 옮긴 뒤 affine_min/max를 CPU에서 수행하고, affine_min/max도 GPU에서 다시 실행되어 GPU→CPU→GPU→CPU 불필요한 복사가 발생했다. 이를 affine_min/max까지 backward_bound_gpu에서 실행되도록 개선해 GPU→CPU 복사를 최소화했다.

원문 대조: 원문 뒷받침 — 원문 p41:e276에서 기존 backward_bound_gpu가 GPU→CPU→GPU→CPU 불필요한 복사를 발생시켰다고 기술하고, p41:e277에서 affine_min/max까지 backward_bound_gpu에서 실행되도록 개선해 GPU→CPU 복사를 최소화했다고 서술함. 개선 전후 복사 횟수/대역폭 수치는 원문에 없음.

해석 한계: 특정 테스트 환경(eps=1e-06, Output Dimension 16)에서의 실행 예시 기준이며, 개선 전후 복사 횟수/대역폭 수치는 명시되지 않음.
자동 원문 대조: 원문 p41:e276에서 기존 backward_bound_gpu가 GPU→CPU→GPU→CPU 불필요한 복사를 발생시켰다고 기술하고, p41:e277에서 affine_min/max까지 backward_bound_gpu에서 실행되도록 개선해 GPU→CPU 복사를 최소화했다고 서술함. 개선 전후 복사 횟수/대역폭 수치는 원문에 없음.

- 조건: 특정 테스트 환경(eps=1e-06, Output Dimension 16)에서의 실행 예시 기준

출처: 41쪽 · p41:e276

> backward_bound_gpu에서 기존에는 GPU (backward_bound_gpu 계산결과) -> CPU
> 이후
> CPU에서 affine_min/max를 통해 계산을 수행한 후 최종결과를 얻는 방식이었다
> (이 때 affine_min/max 도 GPU에서 계산이 돌아가기 때문에
> GPU -> CPU -> GPU -> CPU 불필요한 복사가 발생됨
> )

출처: 41쪽 · p41:e277

> 이 부분에서 affine_min/max까지 backward_bound_gpu에서 실행되도록 개선하여
> GPU -> CPU 이렇게 메모리 복사를 최소화함

## F18 · 측정 결과 · 해석

affine_min_gpu/affine_max_gpu 커널 퓨전 가능성이 제기되었고, 미리 작성해둔 퓨전 함수를 사용해 적용한 뒤 elapsed time이 약 0.2ms 정도 낮아진 것으로 관찰됐다.

원문 대조: 일부만 뒷받침 — 원문 p41:e281에서 affine_min_gpu/affine_max_gpu 커널 퓨전 가능성이 제기되고 미리 작성한 퓨전 함수 적용 코드가 제시됨. p41:e278과 p41:e279에서 elapsed time이 15.828400ms에서 15.751000ms 수준으로 낮아진 예시가 관찰됨. 그러나 '약 0.2ms 감소'는 원문 수치를 근거로 한 해석이며, 절대적 성능 향상 규모나 통계적 유의성은 원문에 제시되지 않음. [코드 검사: 측정값 1개를 원문에서 확인하지 못해 작성용 근거에서 제외]

해석 한계: 측정값은 15.828400ms → 15.751000ms 수준의 예시이며, 절대적 성능 향상 규모나 통계적 유의성은 제시되지 않음.

- 조건: 특정 테스트 환경(eps=1e-06, Output Dimension 16)에서의 실행 예시 기준
- 측정: elapsed time = 15.828400ms ms (퓨전 적용 전 예시 측정값) / p41:e278
- 확인 필요 수치 (작성 제외): elapsed time = 15.751000ms ms — 수치 표기를 연결 원문에서 확인하지 못했습니다.

출처: 41쪽 · p41:e278

> ![image](/image/placeholder)
> Starting CROWN Verification (eps = 1e-06) mempool + warmup calc success Elapsed time: 15.828400 ms Output Dimension: 16 [Index] | Lower Bound | Upper Bound | inference (y) 0] 1] 2] 3] 4] 5] 6] 7] 8] 9] 10] 11] 12] [ 13] [ 14] [ 15] 0.081772 0.273538 0.102147 0.114244 2.670552 1.846574 -1.714750 -1.880139 0.706986 -2.612086 0.003713 1.310476 2,049539 -1.025923 1.082576 -3,404772 0.082159 0.273823 0.102482 0.114541 2,670843 1.846872 -1,714490 -1.879695 0.707275 -2.611722 0.003976 1.310817 2,049839 -1.025597 1.082852 -3,404355 0.081966 0.273680 0.102314 0.114393 2.670697 1.846723 -1.714620 -1.879916 0.707131 -2.611904 0.003845 1.310646 2,049689 -1.025760 1,082714 -3,404563

출처: 41쪽 · p41:e279

> 결 과는 15ms 후반까지 나옴

출처: 41쪽 · p41:e281

> ![image](/image/placeholder)
> // 3. GPU 안에서 최종 정답 계산 // 커널 퓨전 가능할듯 affine_min_gpu<<<blocksPerGrid,f 256>>>(lower_M, lower_p, d_xl, d_xu, d_final_lower); affine_max_gpu<<<blocksPerGrid,f 256>>>(upper_M, upper_p, d_xl, d_xu, d_final_upper); ;

## F19 · 구현·방법 · 구현 기록

Forward 단계의 입력 버퍼(x0 ± eps)를 Backward에서 재사용해 H2D 복사를 제거하고, 단위행렬/영벡터 같은 default 초기 상태를 GPU 커널에서 직접 생성해 PCIe 통신 오버헤드를 최소화했다.

원문 대조: 일부만 뒷받침 — 원문 p43:e287에서 Forward 단계의 입력 버퍼(x0 ± eps)를 Backward에서 재사용해 H2D 복사를 제거했다고 기술하고, p43:e288에서 default 초기 상태(단위행렬/영벡터)를 GPU 커널에서 직접 생성해 PCIe 통신 오버헤드를 최소화했다고 서술함. p43:e289에서 전체 elapsed time이 13.939000ms 수준으로 낮아진 예시가 제시되나, 해당 최적화의 개별 기여도는 분리 제시되지 않음. [코드 검사: 측정값 1개를 원문에서 확인하지 못해 작성용 근거에서 제외]

해석 한계: 해당 최적화의 개별 기여도는 분리 제시되지 않았고, 전체 elapsed time이 13.939ms 수준으로 낮아진 예시만 제시됨.

- 조건: 특정 테스트 환경(eps=1e-06, Output Dimension 16)에서의 실행 예시 기준
- 확인 필요 수치 (작성 제외): elapsed time = 13.939000ms ms — 수치 표기를 연결 원문에서 확인하지 못했습니다.

출처: 43쪽 · p43:e287

> - Forward 단계의 입력 버퍼(x0 ± eps)를 Backward에서 재사용하여 H2D 복사 제거

출처: 43쪽 · p43:e288

> - default 초기 상태(단위행렬/영벡터)를 GPU 커널에서 직접 생성하여 PCIe 통신 오버헤드
> 최소화

출처: 43쪽 · p43:e289

> ![image](/image/placeholder)
> Starting CROWN Verification (eps = 1e-06) mempool + warmup calc success lapsed time: 13,939000 ms Output Dimension: 16 Index] | Lower Bound | Upper Bound | inference (y) 0] 1] 2] 3] 4] 5] 6] 7] 8] 9] 10] 11] 12] 13] 14] 15] | 0.081772 0.273538 0.102147 0.114244 2.670552 1,846574 -1.714750 -1.880139 0.706986 -2.612086 0.003713 1,310476 2,049539 -1.025923 1.082576 -3,404772 0.082159 0.273823 0.102482 0.114541 2,670843 1,846872 -1,714490 -1.879695 0.707275 -2.611722 0.003976 1.310817 2,049839 -1.025597 1,082852 -3,404355 0.081966 0.273680 0.102314 0.114393 2.670697 1.846723 -1.714620 -1.879916 0.707131 -2.611904 0.003845 1,310646 2,049689 -1.025760 1,082714 -3,404563

## F20 · 측정 결과 · 해석

40000회 루프 테스트에서 backward보다 forward가 더 느린 현상이 발생했고, 원인은 forward_bound_impl의 플래그에 따라 중간 레이어 결과가 복사되는지 여부였다. 단일 실행에서는 D2H 오버헤드가 연산 오버헤드를 넘지 않았으나, 40000회×eps 반복에서는 D2H 복사 오버헤드가 forward 계산 이득을 넘어섰다.

원문 대조: 일부만 뒷받침 — 원문 p45:e313에서 40000회 루프 테스트에서 backward보다 forward가 더 느린 현상을 확인했고, p45:e314에서 forward_bound_impl의 플래그에 따라 중간 레이어 결과가 복사되는지 여부가 원인이라고 서술함. p46:e316에서 40000회×eps 반복에서 D2H 복사 오버헤드가 forward 계산 이득을 넘어섰다고 해석함. 그러나 플래그 동작과 복사 오버헤드 해석은 작성자의 분석이며, 정량적 분해(복사량/연산시간 분리)는 원문에 제시되지 않음.

해석 한계: 플래그 동작과 복사 오버헤드 해석은 작성자의 분석이며, 정량적 분해(예: 복사량/연산시간 분리)는 제시되지 않음.

- 조건: 40000회 루프 테스트 환경
- 조건: eps 반복 테스트

출처: 45쪽 · p45:e313

> 40000번의 루프에서는 backward보다 forward가 느린것을 확인함, 왜일까?
> ⇒ 원인은 중간 레이어 결과를 저장하느냐/ 마느냐의 플래그에 있었다.

출처: 45쪽 · p45:e314

> f orward_bound_impl의 플래그를 true로 두면 중간 결과가 복사됨,

출처: 46쪽 · p46:e316

> 40000번 * 각 eps 테스트를 반복하면서 D2H 복사 오버헤드가 backward ⇒ forward 계산의
> 이득을 뛰어넘어버린 것임..

## F21 · 구현·방법 · 구현 기록

Forward는 중간 결과(layer_bound 복사용), final_affine 복사용, 최종 결과 복사용으로 플래그를 3개로 나누고, backward도 layer_bound와 affine_bound 복사 제어 플래그를 각각 2개로 분리했다. 이후 forward 최종 계산(result→lower/upper bounds)의 D2H 복사 비효율을 개선해 backward가 forward보다 느렸던 문제를 해결했다.

원문 대조: 원문 뒷받침 — 원문 p46:e318에서 forward의 플래그를 3개(중간 결과(layer_bound 복사용), final_affine 복사용, 최종 결과 복사용)로 늘리고, backward의 플래그도 layer_bound와 affine_bound 복사 제어 플래그를 각각 2개로 분리했다고 기술함. p46:e319에서 forward 최종 계산(result→lower/upper bounds)의 D2H 복사 비효율성을 개선하기 위해 최적화를 진행했다고 서술하고, p46:e320에서 backward가 forward보다 빠른 문제를 해결했다고 기술함. 개선 후 개별 단계 시간 분해는 별도로 제시되지 않음.

해석 한계: 플래그 분리와 복사는 구현 변경으로 기술되었으며, 개선 후 개별 단계 시간 분해는 별도로 제시되지 않음.
자동 원문 대조: 원문 p46:e318에서 forward의 플래그를 3개(중간 결과(layer_bound 복사용), final_affine 복사용, 최종 결과 복사용)로 늘리고, backward의 플래그도 layer_bound와 affine_bound 복사 제어 플래그를 각각 2개로 분리했다고 기술함. p46:e319에서 forward 최종 계산(result→lower/upper bounds)의 D2H 복사 비효율성을 개선하기 위해 최적화를 진행했다고 서술하고, p46:e320에서 backward가 forward보다 빠른 문제를 해결했다고 기술함. 개선 후 개별 단계 시간 분해는 별도로 제시되지 않음.

- 조건: 플래그 분리와 복사 제어 구현 변경

출처: 46쪽 · p46:e318

> ⇒ forward의 플래그를 3개로 늘림 (중간 결과(layer_bound 복사용), final_affine 복사용,
> 최종 결과 복사용)
> ⇒ 그리고 backward의 플래그도 기존의 layer_bound와 backward result의
> affine_bound를 같이 복사할지 제어하는 플래그를 각각 2개로 분리했다.

출처: 46쪽 · p46:e319

> 또 한 forward 최종 계산(result -> lower/upper bounds)을 D2H 복사 하는데에서 비효율적인
> 부분이 있어서 정확한 테스트를 위해 최적화를 진행함

출처: 46쪽 · p46:e320

> 그 래서 일단 backward가 forward보다 빠른 문제는 해결 (forward 최적화 해서)

## F22 · 측정 결과 · 해석

92만 번 규모의 다중 데이터 테스트에서 forward 전체 실행 시간은 약 64s, backward는 약 98s로 backward가 더 느렸고, cudaMemcpy 호출 횟수는 forward/backward가 동일했다. 단일 테스트에서 forward/backward가 약 3배 차이 나는 것과 달리 다중 데이터에서는 차이가 줄어드는 현상이 관찰됐으나 원인은 해결되지 않았다.

원문 대조: 일부만 뒷받침 — 원문 p46:e322에서 단일 테스트 결과로 비교하면 다중 데이터셋 테스트에서 3배 차이가 나야 하는데 그렇지 않다고 의문을 제기하고 Nsight system 분석을 이용하기로 했다고 서술함. p47:e334와 p47:e335에서 40000개 데이터에 대한 forward/backward 테스트 결과가 제시됨. 그러나 'forward 약 64s, backward 약 98s', 'cudaMemcpy 호출 횟수 동일', '단일 테스트에서 약 3배 차이' 등의 구체적 수치와 해석은 원문에 명시되지 않았으며 작성자의 관찰/추정 기반임.

해석 한계: 호출 횟수 해석과 시간 수치는 작성자의 관찰/추정 기반이며, 3배 차이의 근거인 단일 테스트 조건과의 직접 비교 수치는 불명확함.

- 조건: 92만 번 규모 다중 데이터 테스트
- 조건: 40000개 데이터 테스트

출처: 46쪽 · p46:e322

> 근데 각각 forward, backward 결과를 보니 단일 테스트 결과로 비교하면 단순하게 다중
> 데이터셋을 가지고 테스트 했을 때 3배 차이가 나야하는데 왜 그렇게 안나오지?
> ⇒ Nsight system 분석을 이용하기로 했다

출처: 47쪽 · p47:e334

> f orward - (일단 40000개 의 데이터에 대해서만 테스트 했을 때)

출처: 47쪽 · p47:e335

> b ackward - (일단 40000개의 데이터에 대해서만 테스트 했을 때)

## F23 · 구현·방법 · 구현 기록

CROWN 결과를 담는 구조체를 switch 바깥에 선언해 반복문 내부에서 값을 채우면 값에 의한 복사가 발생하고, 92만 번 복사 시 큰 비용이 될 수 있다는 지적에 따라 구조체를 case 내부 중괄호 범위에서 선언·초기화하도록 변경해 컴파일 오류와 성능 문제를 해결했고, 실행 시간이 2100s대 문제에서 개선됐다.

원문 대조: 원문 뒷받침 — 원문 p49:e349에서 switch 바깥에 CROWN 결과 구조체를 선언해 반복문 내부에서 값을 채우면 값에 의한 복사가 발생한다고 지적하고, p50:e351에서 case 내부 중괄호 범위에서 ForwardBoundResult/BackwardBoundResult를 선언·초기화하는 코드 변경이 제시됨. p50:e357에서 2100s대 문제가 해결됐다고 서술함. 그러나 값에 의한 복사와 성능 영향의 정량적 분해는 제시되지 않았고, 개선 후 시간도 1342.47s, 1460.60s, 1564.18s 등 실행 조건에 따라 편차가 크게 나타남.

해석 한계: 값에 의한 복사와 성능 영향의 정량적 분해는 제시되지 않았고, 개선 후 시간도 1342.47s, 1460.60s, 1564.18s 등 실행 조건에 따라 편차가 크게 나타남.

- 조건: switch 문 내 구조체 선언 위치 변경
- 조건: 92만 번 규모 반복 테스트
- 측정: 실행 시간 = 2100s s (개선 전 문제 발생 예시) / p50:e357

출처: 49쪽 · p49:e349

> 먼 저 switch의 스코프 바깥에 CROWN 결과를 담을 구조체를 선언해놓고
> 반복문 내부에서 CROWN 을 돌려서 결과를 담고 있는데, 이 부분이 옛날에 배웠듯, 값에
> 의한 복사란 말이다

출처: 50쪽 · p50:e351

> ![image](/image/placeholder)
> 9 0 V V 8 9 e Vector ye = network_forward (*net, dataset[i]); // CROWN backward bound or forward bound 계산 switch(method){ case 0: { ForwardBoundResult fwd = lirpa_forward_bound_impl(*net, dataset[i], eps_f, false, false, true) // Top-k 인증 판정 if (certify_topk(y0, fwd.final_lower, fwd.final_upper, k)) +t_count; else ++f_count; break; } case 1: BackwardBoundResult bwd = lirpa_backward_bound(*net, dataset[i], eps_f, false, false); // Top-k 인증 판정 if (certify_topk(y0, bwd.final_lower, bwd.final_upper, k)) ++t_count; else ++f_count; break; } default: break;

출처: 50쪽 · p50:e357

> 음 .. 준수한 결과다. ⇒ 이러면 2100s 초 나오는 문제도 원인 해결 완료

## F24 · 구현·방법 · 구현 기록

추론, bound 계산, 검증 시간을 각각 분리 측정하기 위해 각 단계 끝마다 타임스탬프를 기록해 누적했고, forward/backward 각각 20회 측정을 진행했다. warmup을 적용했으나 평균 시간이 더 늘어나거나 스파이크가 발생하는 현상이 있었고, CV를 통해 간헐적 스파이크/분산을 확인했으나 원인은 규명되지 않았다.

원문 대조: 원문 뒷받침 — 원문 p54:e392에서 추론(t0~t1), bound 계산(t1~t2), 검증(t2~t3) 각 단계 끝마다 타임스탬프를 기록해 누적하는 측정 코드가 제시됨. p54:e395에서 forward/backward 각각 20회 측정을 완료했다고 서술하고, p57:e426에서 warmup 적용 후 평균 시간이 더 늘어나는 현상이 관찰됐다고 기술함. 그러나 warmup 후 평균 증가·스파이크 원인은 미해결 상태이며, 클록 고정/GPU 사용량 측정 등은 향후 확인 항목으로 제시됨.

해석 한계: warmup 후 평균 증가·스파이크 원인은 미해결 상태이며, 클록 고정/GPU 사용량 측정 등은 향후 확인 항목으로 제시됨.
자동 원문 대조: 원문 p54:e392에서 추론(t0~t1), bound 계산(t1~t2), 검증(t2~t3) 각 단계 끝마다 타임스탬프를 기록해 누적하는 측정 코드가 제시됨. p54:e395에서 forward/backward 각각 20회 측정을 완료했다고 서술하고, p57:e426에서 warmup 적용 후 평균 시간이 더 늘어나는 현상이 관찰됐다고 기술함. 그러나 warmup 후 평균 증가·스파이크 원인은 미해결 상태이며, 클록 고정/GPU 사용량 측정 등은 향후 확인 항목으로 제시됨.

- 조건: forward/backward 각각 20회 측정
- 조건: warmup 적용

출처: 54쪽 · p54:e392

> ![image](/image/placeholder)
> for (int i = 0; i < N; ++i) { // - [1] 추론 // 신경망 정방향 통과 auto t0 = std::chrono::high_resolution_clock::now(); Vector ye = network_forward(*net, dataset[i]); auto t1 = std::chrono::high_resolution_clock::now(); // 추론 끝 시간 time_infer_total += std::chrono::duration<double>(t1 - t0).count(); // 추론 시간 누적 // - [2] Bound 계산 + [3] 검증 // CROWN backward bound or forward bound 계산 // (각 case 안에서 직접 초기화 → NRVO 적용, 4MB+ 구조체 복사 0회) switch(method){ case 0: { ForwardBoundResult fwd = lirpa_forward_bound_imp1(*net, dataset[i], eps_f, false, false, true); auto t2 = std::chrono::high_resolution_clock::now(); // bound 계산 끝 시간 time_bound_total += std::chrono::duration<double>(t2 - t1).count(); // bound 시간 누적 // Top-k 인증 판정 if (certify_topk(y0, fwd.final_lower, fwd.final_upper, k)) ++t_count; else ++f_count; auto t3 = std::chrono::high_resolution_clock::now(); // 검증 끝 시간 time_certify_total += std::chrono::duration<double>(t3 - t2).count(); // 검증 시간 누적 break; } case 1: { BackwardBoundResult bwd - lirpa_backward_bound(*net, dataset[i], eps_f, false, false); auto t2 = std::chrono::high_resolution_clock::now();/ bound 계산 끝 시간 time_bound_total += std::chrono::duration<double>(t2 - t1).count();// bound 시간 누적 // Top-k 인증 판정 if (certify_topk(y0, bwd.final_lower, bwd.final_upper, k)) +t_count; else ++f_count; auto t3 = std::chrono::high_resolution_clock::now(); // 검증 끝 시간 time_certify_total += - t2).count(); // 검증 시간 누적 break; } default: break; }

출처: 54쪽 · p54:e395

> 그 리고 저렇게 해서 각 forward, backward 20번씩 측정 완료
> (튀는 값 있긴 있는데, 그건 각 20번 실행 시간 평균이랑 분산 구해서 슬라이드에 넣을 예정)

출처: 57쪽 · p57:e426

> 근 데 웬 일? warmup 하니까 걸리는 시간 및 각 평균 시간이 더 늘어남 …

## F25 · 측정 결과 · 관측 기록

Real-Time Single-Sample(B=1) Latency Analysis에서 평균 지연 1145.24 us, P99 1311.90 us, 최대 7830.90 us, 처리량 873.18 samples/sec가 측정되었으며, 전체 elapsed 1055.28s 중 bound가 87.3%, infer가 12.5%, certify가 0.2%를 차지했다.

원문 대조: 원문 뒷받침 — 원문(p61:e468)에 평균 지연 1145.24 us, P99 1311.90 us, 최대 7830.90 us, 처리량 873.18 samples/sec 및 전체 elapsed 1055.28s 중 bound 87.3%, infer 12.5%, certify 0.2%가 명시되어 있음. 평가 샘플 10만개는 표본 측정 목적이며, 최대 지연은 이상치 가능성 있음.

해석 한계: 평가 샘플은 10만개로 표본 측정 목적이며, cudaEvent 측정 제어 인자에 따라 드라이버 오버헤드가 달라질 수 있다. 최대 지연은 이상치(outlier) 가능성이 있다.
자동 원문 대조: 원문(p61:e468)에 평균 지연 1145.24 us, P99 1311.90 us, 최대 7830.90 us, 처리량 873.18 samples/sec 및 전체 elapsed 1055.28s 중 bound 87.3%, infer 12.5%, certify 0.2%가 명시되어 있음. 평가 샘플 10만개는 표본 측정 목적이며, 최대 지연은 이상치 가능성 있음.

- 조건: 평가 샘플: 100000
- 조건: 측정 방식: Real-Time Single-Sample (B=1) Latency Analysis
- 조건: 측정 구간: all eps × all data
- 조건: elapsed: 1055.28s
- 측정: Mean Latency = 1145.24 us us (B=1, all eps × all data, 100000 samples evaluated, cudaEvent 측정 제어 인자 measure_gpu=1(기본값, 마지막 샘플만 1회 측정)) / p61:e468
- 측정: P99 Tail Latency = 1311.90 us us (B=1, all eps × all data, 100000 samples evaluated) / p61:e468
- 측정: Max Latency = 7830.90 us us (B=1, all eps × all data, 100000 samples evaluated, 이상치 가능성 있음) / p61:e468
- 측정: Throughput = 873.18 samples/sec samples/sec (B=1, all eps × all data, 100000 samples evaluated) / p61:e468
- 측정: total elapsed = 1055.28s s (all eps × all data) / p61:e468
- 측정: bound phase = 87.3% % (all eps × all data, total elapsed 1055.28s 중 bound 920.844s) / p61:e468
- 측정: infer phase = 12.5% % (all eps × all data, total elapsed 1055.28s 중 infer 131.799s) / p61:e468
- 측정: certify phase = 0.2% % (all eps × all data, total elapsed 1055.28s 중 certify 1.597s) / p61:e468

출처: 61쪽 · p61:e468

> ![image](/image/placeholder)
> total elapsed: 1055.28s Phase Timing Breakdown (all eps × all data) infer : 131.799s (12.5%) bound : 920.844s (87.3%) certify : 1,597s (0.2%) --- Real-Time Single-Sample (B=1) Latency Analysis === Evaluated Samples : 100000 Min Latency : 1092.30 us Mean Latency : 1145.24 us (1.15 ms) Median (P50) : 1136.80 us P95 Tail Latency : 1179,00 us P99 Tail Latency : 1311.90 us Max Latency : 7830.90 us Jitter (StdDev) : 60.33 us Throughput : 873.18 samples/sec Pure GPU Execution: 953.70 us (last sample) results saved to results_cuda.csv iming log appended to timing_log_crown.csv

출처: 61쪽 · p61:e469

> (평가 샘플이 10만개밖에 안되는 이유는 표본 측정으로 하려고..)

출처: 61쪽 · p61:e471

> ![image](/image/placeholder)
> 204 205 206 207 208 + + + + + int measure_gpu = (argc > 8 && strlen(argv[8]) > 0) ? std::atoi(argv[8]) : 1; // measure_gpu: cudaEvent 하드웨어 타이머 측정 제어 시스템 인자 // 0 = 비활성화 (Off, 드라이버 오버헤드 0, 최고 속도) // 1 = 마지막 샘플만 1회 측정 (Last sample only, 전체 루프 오버헤드 0초 + 맨 마지막 Pure GPU 시간 리포트, 기본값) // 2 를 매 샘플마다 측정 (All samples, 92만 번 전체 정밀 측정, 호출당 20~50us 드라이버 오버헤드 발생 주의)

## F26 · 구현·방법 · 구현 기록

cudaEvent 측정 제어 인자 measure_gpu는 0(비활성화, 드라이버 오버헤드 0), 1(기본값, 마지막 샘플만 1회 측정), 2(매 샘플 측정, 호출당 20~50us 드라이버 오버헤드 발생 가능)로 구성된다.

원문 대조: 일부만 뒷받침 — 원문(p61:e471)에 measure_gpu 인자 정의(0=비활성화, 1=마지막 샘플만 1회 측정 기본값, 2=매 샘플 측정)와 각 모드의 드라이버 오버헤드 관련 주의 사항이 명시되어 있음. 실제 오버헤드 수치는 주의 사항으로 제시된 값임. [코드 검사: 측정값 2개를 원문에서 확인하지 못해 작성용 근거에서 제외]

해석 한계: 이는 시스템 인자 기반 제어 방식 설명이며, 실제 오버헤드 수치는 주의 사항으로 제시된 값이다.

- 조건: 제어 방식: 시스템 인자(argc>8, argv[8]) 기반
- 조건: 기본값: 1 (마지막 샘플만 1회 측정)
- 측정: measure_gpu=0 = 비활성화 (Off, 드라이버 오버헤드 0, 최고 속도) mode (cudaEvent 하드웨어 타이머 측정 제어 시스템 인자) / p61:e471
- 확인 필요 수치 (작성 제외): measure_gpu=1 = 마지막 샘플만 1회 측정 (Last sample only, 전체 루프 오버헤드 0초 + 맨 마지막 Pure GPU 시간 리포트, 기본값) mode — 수치 표기를 연결 원문에서 확인하지 못했습니다.
- 확인 필요 수치 (작성 제외): measure_gpu=2 = 매 샘플마다 측정 (All samples, 92만 번 전체 정밀 측정, 호출당 20~50us 드라이버 오버헤드 발생 주의) mode — 수치 표기를 연결 원문에서 확인하지 못했습니다.

출처: 61쪽 · p61:e471

> ![image](/image/placeholder)
> 204 205 206 207 208 + + + + + int measure_gpu = (argc > 8 && strlen(argv[8]) > 0) ? std::atoi(argv[8]) : 1; // measure_gpu: cudaEvent 하드웨어 타이머 측정 제어 시스템 인자 // 0 = 비활성화 (Off, 드라이버 오버헤드 0, 최고 속도) // 1 = 마지막 샘플만 1회 측정 (Last sample only, 전체 루프 오버헤드 0초 + 맨 마지막 Pure GPU 시간 리포트, 기본값) // 2 를 매 샘플마다 측정 (All samples, 92만 번 전체 정밀 측정, 호출당 20~50us 드라이버 오버헤드 발생 주의)

## F27 · 측정 결과 · 해석

여러 번 측정 결과 pinned memory를 미적용한 버전의 복사 속도가 약 3배 빠르다. 작은 전송에서는 CUDA 내부 staging 경로가 pinned direct-DMA 경로보다 유리할 가능성이 있으나, 내부 구현을 직접 확인할 수 없어 확정은 할 수 없다.

원문 대조: 일부만 뒷받침 — 원문(p81:e624)에 여러 번 측정 결과 pinned 미적용 버전이 복사 속도 약 3배 빠르다는 관찰과, 작은 전송에서 CUDA 내부 staging 경로가 pinned direct-DMA 경로보다 유리할 가능성이 서술되어 있음. 그러나 내부 구현 미확인으로 인과 확정은 불가하다고 명시되어 있어, '약 3배 빠르다'는 관찰은 supported이나 '유리할 가능성'은 interpretation으로 처리함.

해석 한계: 작은 전송(현재 입력 기준 1Kib)에서의 결과이며, CUDA 내부 구현 미확인으로 인과 확정 불가

- 조건: 전송 크기: 작은 전송(현재 입력 기준 1Kib)
- 조건: 비교 대상: pinned memory 적용 버전 vs 미적용 버전
- 조건: 측정 방식: 여러 번 측정
- 측정: 복사 속도 비교 = pinned 미적용 버전이 약 3배 빠름 relative (작은 전송(현재 입력 기준 1Kib), 여러 번 측정 결과) / p81:e624

출처: 81쪽 · p81:e624

> 1. 여러 번 측정 결과, pinned memory를 미적용한 버전의 복사 속도가 약 3배 빠르다 ⇐
> 작은 전송에서는 CUDA 내부 staging 경로가 pinned direct-DMA 경로보다 유리할
> 가능성이 있다. (다만 내부 구현을 직접 확인할 수 없으므로 확정은 할 수 없다)

## F28 · 측정 결과 · 해석

추론이 끝나기까지의 동기화(synchronize) 시간은 pinned memory를 미적용한 버전이 가장 빠르다. 이는 1번의 H2D 복사 시간이 영향을 미칠 수 있으며, 추론 과정은 cuda stream synchronize: H2D - 추론 graph 실행 - D2H 순서로 이루어진다.

원문 대조: 일부만 뒷받침 — 원문(p81:e625)에 추론 완료까지 동기화(synchronize) 시간이 pinned 미적용 버전이 가장 빠르다는 관찰과, 이것이 1번(H2D 복사 시간)의 영향일 가능성이 제시되어 있음. 인과가 확정적으로 서술되지 않았으므로 관찰 사실은 supported이나 '영향을 미칠 수 있다'는 부분은 interpretation으로 처리함. [코드 검사: 측정값 1개를 원문에서 확인하지 못해 작성용 근거에서 제외]

해석 한계: 동기화 시간 우위가 H2D 복사 시간 영향일 가능성은 제시되었으나 확정적 인과로 서술되지 않음

- 조건: 추론 과정: cuda stream synchronize: H2D - 추론 graph 실행 - D2H
- 조건: 비교 대상: pinned memory 적용 버전 vs 미적용 버전
- 확인 필요 수치 (작성 제외): 추론 완료까지 동기화(synchronize) 시간 = pinned 미적용 버전이 가장 빠름 relative — 수치 표기를 연결 원문에서 확인하지 못했습니다.

출처: 81쪽 · p81:e625

> 2. 추론이 끝나기까지의 동기화(synchronize) 시간이 pinned memory를 미적용한
> 버전이 가장 빠르다. ⇐ 1번의 H2D 복사 시간이 영향을 미칠 수 있다
> (추론 과정에서의 cuda stream synchronize : H2D - 추론 graph 실행 - D2H)

## F29 · 측정 결과 · 해석

cudaMemcpyAsync 호출 시간에서 pinned memory 적용 버전이 미적용 버전보다 빠르거나 느렸다. 이는 2copy 과정에서 1copy로 바꾼 것이 크게 효과를 보지 못했기 때문으로 해석된다.

원문 대조: 일부만 뒷받침 — 원문(p81:e626, p81:e628)에 여러 번 측정 결과 cudaMemcpyAsync 호출 시간에서 pinned 적용 버전이 빠르거나 느렸다는 관찰과, 2copy에서 1copy로 바꾼 것이 크게 효과를 보지 못했다는 해석이 있음. 마지막 측정에서는 nopinned가 더 빠르게 나와 확신할 수 없다고 명시되어 있어, 결과 갈림과 해석 모두 partial로 처리함. [코드 검사: 측정값 2개를 원문에서 확인하지 못해 작성용 근거에서 제외]

해석 한계: 여러 번 측정 결과이며 측정마다 결과가 갈렸고, 마지막 측정에서는 nopinned가 더 빠르게 나와 확신할 수 없다고 명시됨

- 조건: 측정 대상: cudaMemcpyAsync 호출 시간
- 조건: 비교 대상: pinned memory 적용 버전 vs 미적용 버전
- 조건: 변경 내용: 2copy 과정에서 1copy로 변경
- 조건: 측정 방식: 여러 번 측정, 마지막 측정 결과 포함
- 확인 필요 수치 (작성 제외): cudaMemcpyAsync 호출 시간 비교 = pinned 적용 버전이 빠르거나 느렸음 (결과 갈림) relative — 수치 표기를 연결 원문에서 확인하지 못했습니다.
- 확인 필요 수치 (작성 제외): 마지막 측정 결과 = nopinned가 더 빠르게 나와 확신할 수 없음 relative — 수치 표기를 연결 원문에서 확인하지 못했습니다.

출처: 81쪽 · p81:e626

> 3. 여러 번 측정 결과, cudaMemcpyAsync를 호출하는 시간에서 pinned memory를
> 적용한 버전이 pinned memory 미적용 버전보다 빠르거나 느렸다 ⇐ 2copy 과정에서
> 1copy로 바꾼 것이 크게 효과를 보지 못했다

출처: 81쪽 · p81:e628

> 3 번은 추가로 말하면
> 여러 번 측정결과, pinned를 적용한 버전의 cudaMemcpyAsync가 더 빨라서 그래도
> 2copy에서 1copy로 가면서 고정 setup 비용이 줄긴 했구나 했는데 마지막 측정결과에서
> nopinned가 더 빠르게 나오면서 확신할 수 없게 됨..

## F30 · 측정 결과 · 추정·가설

작은 데이터 크기(현재 입력 기준 1Kib)를 staging buffer로 옮기는 고정 비용이 크지 않을 수 있다.

원문 대조: 일부만 뒷받침 — 원문(p81:e627)에 작은 데이터 크기(현재 입력 기준 1Kib)를 staging buffer로 옮기는 고정 비용이 크지 않을 수 있다는 가능성 서술이 있음. 확정 성과가 아닌 가능성 서술이므로 hypothesis로 분류하고, 현재 입력 기준 1Kib 조건에서만 언급된 점을 명시함.

해석 한계: 현재 입력 기준 1Kib에서의 추정이며 확정 성과가 아닌 가능성 서술

- 조건: 데이터 크기: 작은 데이터 크기(현재 입력 기준 1Kib)
- 조건: 대상: staging buffer로 옮기는 고정 비용

출처: 81쪽 · p81:e627

> ⇒ 작은 데이터 크기(현재 입력 기준 1Kib)를 staging buffer로 옮기는 고정 비용이 크지
> 않을 수 있다

## F31 · 구현·방법 · 구현 기록

CROWN 3가지 방법에서 사용하는 커널을 퓨전하고 backward_only에서 메모리 복사 커널을 제거했다.

원문 대조: 원문 뒷받침 — 원문(p82:e632)에 CROWN 3가지 방법에서 사용하는 커널의 퓨전 및 backward_only에서 메모리 복사 커널을 제거했다는 설명이 명시되어 있음. 구체적 커널 감소 횟수는 별도 요소에서 확인 필요.

해석 한계: CROWN 3가지 방법 및 backward_only 대상이며, 구체적 커널 감소 횟수는 별도 요소에서 확인
자동 원문 대조: 원문(p82:e632)에 CROWN 3가지 방법에서 사용하는 커널의 퓨전 및 backward_only에서 메모리 복사 커널을 제거했다는 설명이 명시되어 있음. 구체적 커널 감소 횟수는 별도 요소에서 확인 필요.

- 조건: 대상: CROWN 3가지 방법
- 조건: 추가 대상: backward_only
- 조건: 변경 내용: 커널 퓨전, 메모리 복사 커널 제거

출처: 82쪽 · p82:e632

> 추 가로 CROWN 3가지 방법에서 사용하는 커널의 퓨전 및 backward_only에서 메모리 복사
> 커널을 제거했다

## F32 · 측정 결과 · 관측 기록

전체 elapsed 시간은 787s에서 630s로 약 157초 줄었다.

원문 대조: 일부만 뒷받침 — 원문(p83:e638, p83:e639)에 total elapsed 630.94s와 '7 87s ⇒ 630s로 157초 정도 줄었다'는 서술이 있음. 787s는 원문 표기 '7 87s'를 정리한 값이며, 감소량 157초는 원문에 명시된 값임. [코드 검사: 측정값 4개를 원문에서 확인하지 못해 작성용 근거에서 제외]

해석 한계: ‘all eps × all data’ 기준 total elapsed이며, 787s는 원문 표기 ‘7 87s’를 정리한 값

- 조건: 기준: all eps × all data
- 조건: 비교 전 total elapsed: 787s (원문 표기 '7 87s')
- 조건: 비교 후 total elapsed: 630.94s
- 조건: 감소량: 약 157초
- 측정: total elapsed (비교 후) = 630.94s s (all eps × all data) / p83:e638
- 측정: total elapsed 감소량 = 157초 정도 s (787s → 630s, all eps × all data) / p83:e639
- 측정: P99 Tail Latency (비교 후) = 822.90 us us (B=1, all eps × all data, 100000 samples evaluated) / p83:e638
- 측정: Max Latency (비교 후) = 13511.00 us us (B=1, all eps × all data, 100000 samples evaluated) / p83:e638
- 측정: Throughput (비교 후) = 1450.02 samples/sec samples/sec (B=1, all eps × all data, 100000 samples evaluated) / p83:e638
- 확인 필요 수치 (작성 제외): infer phase (비교 후) = 131.248s (20.8%) s / % — 수치 표기를 연결 원문에서 확인하지 못했습니다.
- 확인 필요 수치 (작성 제외): bound phase (비교 후) = 497.107s (78.8%) s / % — 수치 표기를 연결 원문에서 확인하지 못했습니다.
- 확인 필요 수치 (작성 제외): certify phase (비교 후) = 1.613s (0.3%) s / % — 수치 표기를 연결 원문에서 확인하지 못했습니다.
- 확인 필요 수치 (작성 제외): Mean Latency (비교 후) = 689.64 us (0.69 ms) us — 수치 표기를 연결 원문에서 확인하지 못했습니다.

출처: 83쪽 · p83:e638

> ![image](/image/placeholder)
> total elapsed: 630.94s Phase Timing Breakdown (all eps X all data) infer : 131,248s (20.8%) bound : 497.107s (78.8%) certify : 1,613s (0.3%) Real-Time Single-Sample (B=1) Latency Analysis === Evaluated Samples : 100000 Min Latency : 658.10 us Mean Latency : 689.64 us (0.69 ms) Median (P50) : 682.00 us P95 Tail Latency : 712.20 us P99 Tail Latency : 822.90 us Max Latency : 13511.00 us Jitter (StdDev) : 76.80 us Throughput : 1450.02 samples/sec Pure GPU Execution: 522.05 us (last sample)

출처: 83쪽 · p83:e639

> 7 87s ⇒ 630s로 157초 정도 줄었다

## F33 · 측정 결과 · 관측 기록

forward의 전체 elapsed는 1029s에서 668s로 줄었고, forward+backward는 1138s에서 758s로 줄었다.

원문 대조: 원문 뒷받침 — p83:e642에서 '1029s ⇒ 668s'가 명시되어 있고, p83:e641의 total elapsed 668.37s 및 p84:e644의 total elapsed 758.37s가 각각 forward와 forward+backward의 'all eps × all data' 기준 측정값으로 제시됨. 1138s는 원문에 직접 표기되지 않으나 668s→758s 흐름과 문맥상 forward+backward 총 elapsed로 해석됨.

해석 한계: 각각 ‘all eps × all data’ total elapsed 기준이며, 방법별 phase breakdown과 single-sample latency는 별도 요소로 제시됨

- 조건: all eps × all data total elapsed 기준
- 조건: forward와 forward+backward의 phase breakdown 및 single-sample latency는 별도 요소로 제시됨
- 측정: total elapsed (forward) = 668.37s s (all eps × all data) / p83:e641
- 측정: total elapsed (forward, 비교 전) = 1029s s (all eps × all data) / p83:e642
- 측정: total elapsed (forward+backward) = 758.37s s (all eps × all data) / p84:e644

출처: 83쪽 · p83:e641

> ![image](/image/placeholder)
> total elapsed: 668.37s Phase Timing Breakdown (all eps X all data) infer : 130.712s (19.6%) bound : 535,361s (80.1%) certify : 1,437s (0.2%) === Real-Time Single-Sample (B=1) Latency Analysis === Evaluated Samples : 100000 Min Latency : 677.20 us Mean Latency : 723.97 us (0.72 ms) Median (P50) : 719.80 us P95 Tail Latency : 752.50 us P99 Tail Latency : 780.90 us Max Latency : 5496.50 us Jitter (StdDev) : 28.04 us Throughput : 1381.28 samples/sec Pure GPU Execution: 570.08 us (last sample)

출처: 83쪽 · p83:e642

> 1029s ⇒ 668s

출처: 84쪽 · p84:e644

> ![image](/image/placeholder)
> eps= eps= eps= eps= 9.0e-03: T= 1.0e-02: T= 1.0e-01: T= 1.0e+00: T= 1 F=39999 ratio=0.000 0 F=40000 ratio=0.000 0 F=40000 ratio=0.000 0 F=40000 ratio=0.000 total elapsed: 758.37s Phase Timing Breakdown (all eps × all data) infer : 131,863s (17.4%) bound : 623,538s (82.2%) certify : 1,666s (0.2%) --- Real-Time Single-Sample (B=1) Latency Analysis === Evaluated Samples : 100000 Min Latency : 774.30 us Mean Latency : 820.80 us (0.82 ms) Median (P50) : 816.80 us P95 Tail Latency : 849.00 us P99 Tail Latency : 875.20 us Max Latency : 3314.70 us Jitter (StdDev) : 23.60 us Throughput : 1218.32 samples/sec Pure GPU Execution: 663.10 us (last sample)

## F34 · 측정 결과 · 해석

커널 횟수 감소 폭과 시간 감소 폭이 방법별로 비례하지 않으며, forward에서 무거운 커널 연산 호출 횟수가 9회 줄어 가장 많이 줄었으나 backward_only는 45→33회(26.7%)로 가장 적게 줄었고, 단순 가중치·bias 복사 커널 6개, 부호 분리 커널 6개 감소 등 커널별 비용이 다르다.

원문 대조: 원문 뒷받침 — p84:e647에서 forward 무거운 커널 9회 감소, backward forward 부분 12개(9+3, cache 저장 커널 3개 추가 감소), 실제 backward 3개 감소, backward_only 45→33회(26.7%)로 가장 적게 감소, 단순 가중치·bias 복사 커널 6개 및 부호 분리 커널 6개 감소 등 커널별 횟수 차이가 기술되어 있음. 다만 시간 감소와의 정량적 인과 관계는 제한적이라는 한계가 함께 제시됨.

해석 한계: 커널 횟수 감소는 forward/backward/backward_only의 구성 차이(캐시 저장 커널 포함 등)와 커널별 비용 차이로 설명되나, 시간 감소와의 정량적 인과 확인은 제한적
자동 원문 대조: p84:e647에서 forward 무거운 커널 9회 감소, backward forward 부분 12개(9+3, cache 저장 커널 3개 추가 감소), 실제 backward 3개 감소, backward_only 45→33회(26.7%)로 가장 적게 감소, 단순 가중치·bias 복사 커널 6개 및 부호 분리 커널 6개 감소 등 커널별 횟수 차이가 기술되어 있음. 다만 시간 감소와의 정량적 인과 관계는 제한적이라는 한계가 함께 제시됨.
원문 작성자의 해석으로만 서술하며 독립적으로 입증한 인과·성과로 쓰지 않는다.

- 조건: forward/backward/backward_only 구성 차이(캐시 저장 커널 포함 등)
- 조건: 커널별 비용 차이로 인해 횟수 감소 폭과 시간 감소 폭이 방법별로 비례하지 않음
- 측정: 무거운 커널 연산 호출 횟수 감소 (forward) = 9 회 (forward) / p84:e647
- 측정: backward forward 부분 커널 감소 = 12 개 (backward (9+3, cache 저장 커널 3개 추가 감소)) / p84:e647
- 측정: 실제 backward 커널 감소 = 3 개 (backward) / p84:e647
- 측정: backward_only 커널 감소 비율 = 26.7 % (45 ⇒ 33회) / p84:e647
- 측정: 단순 가중치·bias 복사 커널 감소 = 6 개 (커널 종류별 감소) / p84:e647
- 측정: 부호 분리 커널 감소 = 6 개 (커널 종류별 감소) / p84:e647

출처: 84쪽 · p84:e647

> f orward에서는 무거운 커널 연산의 호출 횟수가 9개 줄어듦
> backward에서는 forward 부분 12개(9+3(얘는 backward에서 사용하는 cache까지 저장하는
> 커널을 사용했으니 3개 추가로 줄어듦)) , 실제 backward 부분에서는 3개밖에 안줄어듦
> backward_only 에서는 비율로 따지면 45 ⇒ 33회 즉 커널이 26.7%로 가장 적게 줄어듦 +
> 단순 가중치, bias 복사 커널 6개 , 부호 분리 커널 6개 줄어든 거라 커널 비용도 다름
