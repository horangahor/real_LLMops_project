# CUDA 기반 CROWN 신경망 검증의 실시간 가속과 최적화 과정

## 제1장 서론

### 1.1 연구 배경과 문제 제기

신경망 검증은 배포 환경에서 모델의 안전성을 보장해야 하는 실용적 요구를 갖지만, 기존 CROWN 검증은 CPU 환경에서 수행 시간이 매우 느리고 신경망 검증팀도 오프라인 환경에서만 제한적으로 빠른 상황에 머물러 있었다. 이러한 배경에서 본 연구는 실시간 환경에서 대규모 연산을 충족할 수 있는지 확인하는 것을 목표로 하며, CROWN 검증을 CUDA로 구현하고 최적화하는 방향을 취한다. 실시간성을 확보하려면 마이크로초에서 수 밀리초(ms) 수준으로 지연을 제한해야 한다는 조건이 함께 제시된다.

CUDA 기반 구현의 동기는 CUDA 프로그래밍 역량을 활용할 수 있다는 점과, 안테나 신경망 검증 알고리즘을 하드웨어에 구현하여 실시간 검증에 관심을 둘 수 있으며 하드웨어 구현과 실시간 검증의 여지가 있다는 논문의 뒷받침 논문으로 작성 가능하다는 점에서 정리된다. 다만 이 내용은 CUDA 구현 이유와 목적에 대한 기록이며, 실제 실시간 검증 구현 결과나 논문 작성 결과를 포함하지는 않는다.

### 1.2 기존 접근과 본 연구의 초점

기존 CROWN 신경망 검증은 주로 CPU 환경에서 수행되어, 대규모 연산이 요구되는 상황에서 처리 시간이 매우 느리다는 한계가 있었다. 신경망 검증팀 역시 오프라인 환경에서만 제한적으로 빠른 성능을 확보할 수 있어, 실시간 환경에서의 운용 가능성은 충분히 검토되지 못했다. 본 연구는 이러한 배경에서, 실시간 환경에서 대규모 연산을 충족할 수 있는지 여부를 CUDA 기반 구현과 최적화를 통해 확인하려는 데 초점을 둔다.

### 1.3 연구 목표와 기여 요약

본 연구는 신경망 검증 도구인 CROWN을 CPU 환경에서만 실행하던 기존 방식에서 벗어나, 실시간 환경의 대규모 연산을 CUDA 기반으로 구현하고 최적화하여 실제 네트워크 환경에 대응할 수 있는지 확인하는 데 목적이 있다. 기존 CROWN 검증은 CPU에서 시간이 매우 느리고, 신경망 검증팀도 오프라인 환경에서만 제한적으로 빠른 상황이었기 때문에, 실시간 대규모 연산을 감당하기 어려웠다. 이에 따라 본 연구는 CUDA를 활용한 구현과 최적화 과정을 통해 이러한 제약을 완화할 수 있는지 살펴보는 것을 핵심 목표로 삼는다. 다만 이 목표와 배경은 원문에 직접 기록된 내용이 아니라, 사용자가 이 질문에 한해 임시 승인한 설명에 기반하므로, 세부 기준·수치·실험·입증된 원인으로 확장하지 않고 연구 동기와 초점의 범위에서만 짧게 반영한다.

## 제2장 평가 대상과 실험 구성

### 2.1 평가 대상과 입력 조건

평가 대상은 CROWN 검증을 구현한 C++ 프로그램이다. 신경망 구조는 입력 256, 은닉 491, 491, 출력 16의 완전연결망이며, 입력 벡터 길이는 NR × Ng = 256이다. 입력 데이터셋과 eps_list는 기존 신경망 검증팀이 사용하던 값을 그대로 사용했고, 배치 사이즈는 1로 두었다. 실행 방식은 CROWN의 세 가지 bound 계산 방법인 forward, forward+backward, backward_only를 기준으로 구분하였다. 다만 입력 데이터셋·eps_list·배치 사이즈·실행 방식 관련 설명은 연구 노트만으로 충분히 특정되지 않는 부분으로, 사용자 승인 범위에서 짧게 반영한 것이다.

GPU OPTIMIZED 모드(cuBLAS + Pool)로 CROWN 검증을 실행했을 때 Elapsed time은 229.691800 ms로 기록되었다. 이는 이전 대비 약 100ms 줄어든 값이지만, 기록상 여전히 CPU보다 느리다고 평가되었다. 이에 따라 matmul만 GPU로 실행하는 하이브리드 프로그램을 시도하는 방향이 이어졌다. 한편 현재 커널은 2차원 block 크기와 tid로 단일 샘플에 대한 행렬 연산을 수행하는 방식이며, z축을 추가하면 3차원(multi sample) 처리가 가능한 텐서 코어를 활용할 수 있다는 구상이 함께 정리되어 있다. 다만 이는 현재 구현의 동작 방식과 후속 방향 제안에 해당하며, 실제 3D 커널 구현이나 텐서 코어 활용 결과로 확인된 내용은 아니다.

### 2.2 실행 플랫폼과 소프트웨어 환경

실행 플랫폼과 소프트웨어 환경은 CUDA 툴킷과 nvcc(NVIDIA C Compiler)를 기반으로 하며, CUDA 동작이 필요한 코드만 커널로 바꾸어 컴파일하는 방식으로 진행되었다. CUDA 버전은 13.3(V13.3.73)이다. 컴파일 옵션에는 -lcublas를 사용했으며, -l은 라이브러리 링크 옵션이고 cublas는 NVIDIA가 제공하는 cuBLAS 라이브러리이다. my_lirpa_op.cu에서 cublasDgemm() 함수를 사용하기 때문에 이 라이브러리를 연결해야 하며, CUDA Toolkit 설치 시 cuBLAS가 자동으로 포함되어 별도 설치는 필요하지 않다.

cuBLAS는 NVIDIA GPU에서 빠르게 선형대수 연산을 수행하도록 만든 NVIDIA Developer 가속 라이브러리이며, cuBLAS와 cuSparse 같은 라이브러리는 미리 컴파일된 소스코드 덩어리로 소스코드가 없어 한 번에 컴파일할 수 없다. v1-1-1-1은 메모리풀에 cuBLAS를 도입하고 matvec, matmul을 기존 자체 계산이 아닌 cuBLAS를 활용하도록 한 버전으로, 파일은 my_lirpa_mempool_cuBLAS.cu이다. cuSparse 도입 시도에서는 W, W_pos, W_neg를 네트워크 준비 단계에서 CSR 형식으로 변환하고 cuSPARSE handle 및 CSR descriptor를 유지한 뒤 network_forward()의 dense matvec를 cuSPARSE SpMV로 교체했으며, 기존 matmul은 아직 유지되었다.

CUDA 커널 인자는 포인터(배열)와 스칼라(단일 숫자/열거형)로 구분된다. 포인터는 cudaMalloc·cudaMemcpy로 VRAM에 올린 주소를 넘겨야 하고, 스칼라는 CPU 메모리 값을 커널 실행 시 Parameter Bank/Constant Memory에 함께 실어 보낼 수 있다. 포인터 변수는 크기가 커서 CPU가 커널 매개변수 주머니에 값을 직접 넣어줄 수 없으므로 memcpy로 올려야 하고, 4\~8바이트 수준의 값만 CPU가 직접 참조해 보낼 수 있다.

현재 구성은 pinned Memory 추가, cudaEvent 제어, 필요한 만큼 계산해서 D2H memcpy, certify topk 자료구조 스택화를 포함한다. 그래프와 비교할 때 단일 스트림 입력 복사 최적화를 논의하자는 관점이 제시되었다. 10주차 세미나 이후에는 backward_only CUDA 구현(커널 구현 완료, 최적화 적용 여부 탐색중), cudaGraph 원리 학습, auto lirpa 모델 소통(repo 수령, 데이터셋·모델 동일 확인), 미팅 일정, 배칭+다중 스트림 관련 실제 환경과의 괴리 검토, 컴파일러 팀에 모델 공유가 기록되었다. auto lirpa repo는 https://github.com/horangahor/antenna_auto_lirpa에서 받아 실행해보기로 했다.

pinned memory 성능 측정을 위해 pinned memory 미적용, my_lirpa에 있는 입력 공간 하나(HostAlloc), 지금 하는 방식(HostRegister) 세 가지를 측정하려고 계획했다. cudaHostRegister(Pinned/Register)와 No Pinning(일반 메모리) 간 전체 실행 시간 차이는 787.88초 대 776.70초로 약 1.4%(약 11초)이며, 92만 번 루프 중 1회당 약 12μs 수준의 미세한 차이이다. Bound 단계(전체 85%)에서는 cudaHostRegister가 658.80초로 No Pinning의 663.17초보다 4.37초 더 빨랐고, Infer 단계(전체 15%)에서는 cudaHostRegister가 127.18초로 No Pinning의 111.92초보다 15.26초 더 느려 데이터 전송 직후 동기화가 일어나는 Infer 단계에서 역전되었다.

cudaHostRegister가 No Pinning보다 더 느리게 측정된 이유에 대해 컴퓨터 구조와 GPU 드라이버 레벨에서 매우 명확하고 흥미로운 3가지 기술적 이유가 있다고 기록되었으며, 추론(Infer) 단계에서 시간이 느려졌다는 정성적 관찰도 함께 남았다. GPU 클록을 고정하고 다시 실험하기로 했으며, 이를 위해 GPU 클록 자동 잠금·자동 해제용 RAII 구조체(ScopedGpuClockLock)를 작성했다. CUDA 강의 19장의 GPU 클록 고정을 참고했고, 클록을 2800MHz로 고정하고 돌린 결과(기존 HostRegister)를 확인했다. 현재 클록 확인은 nvidia-smi -q -d CLOCK로, 클록 고정은 sudo nvidia-smi -pm 1(Persistence mode)과 sudo nvidia-smi -lgc 1410(Lock graphics clock)으로 수행한다. 측정 환경 설정으로 Persistence mode(초기화 지연 제거)를 위해 sudo nvidia-smi -pm 1을 사용한다.

호스트 메모리 방식은 Pageable(일반 메모리)와 Pinned Memory로 나누어 비교했다. CUDA 프로그래밍 가이드에 따르면 호스트 메모리가 Pageable일 때 cudaMemcpyAsync는 비동기로 동작하지 않고, CPU가 드라이버 내부 고정 스테이징 버퍼로 동기식 memcpy를 즉시 수행한다. No-Pin 방식에서는 CPU가 1KB 데이터를 L1 캐시 복사 수준으로 스테이징 버퍼에 빠르게 복사한 뒤 다음 코드로 넘어가며, 드라이버 스테이징 버퍼는 GPU 메모리 매퍼에 이미 등록된 고정 주소여서 GPU TLB 미스가 발생하지 않는다.

데이터 규모가 수 MB에서 수백 MB로 커지면 CPU 복사 속도가 감당되지 않으며, 이때는 DMA의 고속 대역폭이 압도적이어서 Pinned Memory가 일반 메모리보다 빠르게 동작한다. 반면 1KB 수준의 작은 데이터에서는 대역폭보다 셋업 지연시간이 지배한다. 단일 채널 벡터처럼 매우 작은 실시간 데이터 환경에서는 PCIe DMA 셋업 오버헤드로 인해 Pinned Memory의 평균 전송 속도가 Pageable 메모리 대비 미세하게 낮게 측정될 수 있다.

평균 처리 속도에서는 No-Pin이 Pinned Memory보다 빨랐지만, 실시간성 관점에서는 차이가 달라졌다. No-Pin은 평소 CPU 캐시 복사로 빠르지만 윈도우 OS의 가상 메모리 정리나 백그라운드 작업이 개입하면 최대 11.6ms까지 지연 스파이크가 발생할 수 있다. 반면 Pinned Memory는 매번 DMA 셋업 비용을 치르는 대신 OS 페이징을 차단하여 어떤 상황에서도 1.64ms를 넘지 않는 안정성을 보였다.

측정 결과, No-Pin의 최대 지연은 8.8ms에서 11.6ms 범위였고 지터는 118μs 수준이었으며, Pinned Memory의 최대 지연은 1.64ms, 지터는 47μs로 나타났다. 더 정밀한 표에서는 No-Pin의 지터가 118.94μs, Pinned Memory의 지터가 47.28μs로 기록되어 Pinned Memory가 최대 지연에서 약 7배 안정적이고 지터는 약 60% 감소하는 경향을 보였다.

infer 단계에서 40,000번 반복하는 동안 CPU 스레드가 cudaStreamSynchronize로 대기하고 깨어나는 과정의 미세 지연과 드라이버 동기화 비용이 맞물려, Pinned Memory 쪽이 총 루프 시간에서 약 13초 정도 느려지는 결과가 나타났다. 이는 1KB의 작은 데이터를 매 루프마다 전송하면서 개별 하드웨어 DMA 셋업을 반복 호출한 오버헤드에 따른 것으로, 총 소요 시간만 보면 No-Pin이 더 빠르지만 지터와 최악 실행 시간에서는 Pinned Memory가 유리하다.

각 최적화 기법을 체계적으로 분리해 ablation study를 수행하지는 못했으며, GPU 클록 고정과 Persistence mode 같은 조건은 나중에 고정된 사항이다. warm up은 초기에 적용되었지만, 실행 조건 중 일부는 최적화 과정에서 적용했다가 되돌리는 방식으로 바뀌어 재현 관련 한계로 남는다.

현재 C++ 멀티스트림 구현은 단일 샘플 커널을 64개 스트림에 각각 런치하는 Task Parallelism 방식이며, 일반 CUDA 코어(FP32)만 사용하고 1024개 처리에 수만 번의 커널 호출이 필요해 약 8분이 소요된다. 방법 A(Multi-Stream 배칭)는 기존 단일 샘플 커널을 유지해 3.2배 가속(25분→8분)을 얻었으나, 스트림 수의 한계(SM 포화)로 7\~8분이 한계선이다.

배치 사이즈 64일 때 약 424초가 걸렸으며, 현재 구현은 배치 사이즈만큼 동일한 수의 독립 스트림을 만들어 각 스트림이 GPU 메모리를 차지하는 방식이다. 배치 사이즈를 512로 하면 메모리를 넘지 않지만 느리며, 그 이유는 각 스트림마다 CPU가 돌아가면서 다음 커널을 런치해줘야 해서 1024개의 스트림이 각각 CPU가 다음 커널을 런치해줄 때까지 기다리고 있기 때문이다. 스트림 수를 64개 정도로 줄이고 배치 사이즈를 1024로 하는 방안은 의미가 없다고 판단했으며, 하나의 스트림이 하나의 입력을 처리하므로 동시에 돌릴 수 있는 데이터가 64개라는 뜻이고 16번씩 나눠서 처리하게 되기 때문이다. 초기 데이터 H2D 비용은 확실히 줄지만, 연산 병목은 스트림이 64개라 한 번에 64개밖에 대응하지 못하는 제약이 있다.

현재 커널은 2차원 block 크기와 tid로 단일 샘플 행렬 연산을 수행하며, fp32 코어로만 동작한다. z축을 추가하면 3차원(multi sample) 처리가 가능한 텐서 코어를 통해 평면 연산을 한 번에 처리할 수 있다. antenna_lirpa는 싱글 스트림으로 동작하지만, cuBLAS Batched GEMM과 텐서 코어 활용으로 현재 C++ 멀티스트림(8분)보다 약 4배 빠르다. auto_lirpa의 빠른 이유는 커널 런치 횟수 감소와 관련된 설명으로 이어진다.

차기 로드맵(방법 C: Batched GEMM, 3D 텐서 연산화)은 CROWN 행렬식을 3D 텐서 레이아웃으로 변환해 cublasSgemmBatched를 호출하고 텐서 코어를 100% 활용하여, antenna_lirpa의 2분을 뛰어넘어 30초\~1분대(전체 40,000개) 진입을 목표로 한다. 각 최적화 기법을 체계적으로 분리하며 ablation study를 해보지 못한 것이 한계로 남는다.

### 2.3 데이터셋·입력 규모와 실행 방식

현재 방식은 Z축=1인 단일 슬라이스로, 그리드 크기를 dim3 grid(num_blocks, 1, 1)로 설정해 한 번에 샘플 1개만 연산한다. 1024개 처리 시 CPU가 커널을 1,024번 발사해야 하므로 CPU 발사 오버헤드가 누적되고 GPU는 샘플 1개씩 받아 처리량이 제한되는 구조가 된다. 반면 auto-LiRPA / 3D Grid 방식은 그리드 크기를 dim3 grid(num_blocks_x, num_blocks_y, 1024)로 설정해 Z축(배치 축)을 1024로 만들고, 1024개 샘플을 하나의 3D 큐브(텐서)로 GPU 메모리에 적재한다. 현재 커널은 2차원 block 크기와 tid로 단일 샘플의 행렬 연산(평면적 계산)을 수행하며, z축을 추가하면 3차원(multi sample)을 처리하는 텐서 코어를 통해 평면 연산을 한 번에 처리할 수 있다. 현재는 2차원 커널이라 fp32 코어로만 수행 중이다.

### 2.4 측정 구간과 측정 방식

추론, bound 계산, 검증 각 단계 종료 시점에 시간을 기록해 E2E 기준으로 각각 시간을 측정하였다. elapsed 타임과 미세한 오차가 있어 3개 누적 시간을 더한 값을 더 올바른 시간으로 판단해 사용하였다. 단일 데이터 측정 검증을 위해 먼저 warm up 코드를 넣었고, 각 forward와 backward는 20번씩 측정을 완료하였다. 튀는 값이 있으나 각 20번 실행 시간의 평균과 분산을 구해 슬라이드에 넣을 예정이었다. 측정 시작을 기준으로 추론 이후 타임스탬프를 찍고 추론 시간을 계산했으며, bound 계산과 출력·실행 결과 확인 절차도 함께 기록하였다.

측정 구간과 방식은 CROWN 검증 실행 종료 시점에 Elapsed time을 기록하는 단일 실행 기준으로 정리되었다. MEMPOOL + Weights PRELOAD ON GPU 모드에서는 eps=1e-06, 출력 차원 16 조건에서 149.820400 ms가 관측되었고, 이후 가중치 사전 업로드 적용 결과는 149\~155ms 범위로 요약되었다. 반복 측정 통계나 측정 구간별 누적 시간 합산 방식은 현재 페이지에 직접 드러나지 않는다.

추론, bound 계산, 검증 각 단계 종료 시점에 시간을 기록해 E2E 기준으로 각각 시간을 측정하였다. elapsed 타임과 미세한 오차가 있어 3개 누적 시간을 더한 값을 더 올바른 시간으로 판단해 사용하였다. 단일 데이터 측정 검증을 위해 먼저 warm up 코드를 넣었고, 각 forward와 backward는 20번씩 측정을 완료하였다. 튀는 값이 있으나 각 20번 실행 시간의 평균과 분산을 구해 슬라이드에 넣을 예정이었다. 측정 시작을 기준으로 추론 이후 타임스탬프를 찍고 추론 시간을 계산했으며, bound 계산과 출력·실행 결과 확인 절차도 함께 기록하였다.

측정은 추론, bound 계산, 검증 값을 나눠 기록하기로 했다. cudaGraph 커널 캡처는 92만 번 입력값 계산 중 1회 CROWN 계산 내 수십 번 커널 호출 상황에서 호출 압축을 노리는 방식으로 검토했으며, 커널 자체 최적화 완료 후 고려할 스냅샷 기능으로 이해했다. 추론·bound를 따로 캡처한 경우와 추론+bound를 한 번에 캡처한 경우를 나눠 커널 런치 비용 최소화를 시도했다.

커널 횟수 측정은 3-layer 네트워크 기준으로 CUDA kernel launch만 세고, H2D/D2H memcpy, cudaStreamSynchronize, cudaGraphLaunch는 제외하였다. graph mode 1은 여전히 샘플당 cudaGraphLaunch가 infer 1회 + bound 1회, 총 2회이다.

측정 방식은 measure_gpu 시스템 인자로 cudaEvent 하드웨어 타이머 측정을 제어하였다. 0은 비활성화, 1은 마지막 샘플만 1회 측정, 2는 매 샘플마다 측정하는 모드로 정의하였다.

실시간성 확인 기준으로 마이크로초\~수 밀리초(ms) 내 제한을 목표로 삼았다.

배칭은 싱글 스트림이 아닌 멀티 스트림을 사용해 데이터를 여러 개 묶어 병렬 처리를 가능하게 하는 방법이며, 기존 데이터셋이 준비된 실험 환경에서는 단일 스트림보다 3배 빨라져 25분에서 8분으로 단축되었다. 현재 C++ 멀티스트림 구현은 단일 샘플 커널을 64개 스트림에 각각 런치하는 Task Parallelism 방식이고, 일반 CUDA 코어(FP32)만 사용하며 1024개 처리에 수만 번의 커널 호출이 필요해 약 8분이 소요된다.

cudaHostRegister(Pinned/Register)와 No Pinning(일반 메모리) 간 전체 실행 시간 차이는 787.88초 대 776.70초로 약 1.4%(약 11초)이며, 92만 번 루프 중 1회당 약 12μs 수준의 미세한 차이이다. Bound 단계(전체 85%)에서는 cudaHostRegister가 658.80초로 No Pinning의 663.17초보다 4.37초 더 빨랐고, Infer 단계(전체 15%)에서는 cudaHostRegister가 127.18초로 No Pinning의 111.92초보다 15.26초 더 느려, 데이터 전송 직후 동기화가 일어나는 Infer 단계에서 역전되었다. cudaHostRegister가 더 느리게 측정된 이유에 대해 컴퓨터 구조와 GPU 드라이버 레벨에서 3가지 기술적 이유가 있다고 기록되었으며, 추론 단계에서 시간이 느려졌다는 정성적 관찰도 함께 남았다.

infer 단계에서 40,000번 동안 CPU 스레드가 cudaStreamSynchronize로 대기하고 깨어나는 과정에서의 미세 지연과 드라이버 동기화 비용이 맞물려, Pinned 쪽이 총 루프 시간에서 약 13초 정도 느려지는 결과가 나왔다. cudaMemcpy 호출의 시작 시간은 0.385727s, 종료 시간은 0.38664s이며, 지속 시간은 약 913.313 μs이다. cudaMemcpy 호출의 상세 표에서는 Start 시간 0.398832s(Duration 26.601 μs, TID 14016), 0.398862s(Duration 1.084 ms, TID 14016), 0.399947s(Duration 192.590 μs, TID 14016)의 세 가지 호출이 기록되었고, Begins 시간은 0.399947s, Ends 시간은 0.40014s이며 지속 시간은 192.590 μs이다.

cudaEvent를 추가한 것이 지연 증가 원인일 가능성이 제기되었으며, 이 영향은 시스템 인자를 넣어 제어해보는 중이다.

### 2.5 재현 관련 정보

평가 대상은 CROWN 검증을 구현한 C++ 프로그램이며, 신경망 구조는 256-491-491-16 크기의 완전연결망이다. 입력 데이터셋과 eps_list는 기존 신경망 검증팀이 사용하던 값을 그대로 사용했고, 실행 방식은 CROWN의 세 가지 방법인 forward, forward+backward, backward_only로 구분했다. 배치 사이즈는 1로 설정했으며, 정확도 지표는 기존 신경망 검증팀 프로그램과 검증 결과·비율이 얼마나 차이나는지를 기준으로 삼았고, 관측된 범위에서는 모두 동일했다.

실행 환경은 GPU OPTIMIZED(cuBLAS + Pool), MEMPOOL + Weights PRELOAD ON GPU, CPU ONLY(no GPU) 등 여러 모드로 기록되었다. GPU OPTIMIZED 모드에서 eps=1e-06, 출력 차원 16 조건으로 CROWN Verification을 실행했을 때 Elapsed time은 229.691800 ms로 관측되었고, MEMPOOL + Weights PRELOAD ON GPU 모드에서는 149.820400 ms, CPU ONLY 모드에서는 500회 반복 총 실행 시간이 39148.493900 ms, 반복당 평균 78.296988 ms로 기록되었다. forward 함수에서 DTOH memcpy를 극단적으로 제거한 뒤에는 64.716000 ms가 관측되었다.

측정 조건 통제를 위해 Persistence mode를 sudo nvidia-smi -pm 1로 활성화하고, 클록 확인은 nvidia-smi -q -d CLOCK, 클록 고정은 sudo nvidia-smi -lgc 1410 등의 명령어로 수행했다. cudaHostRegister(Pinned)와 No Pinning(일반 메모리) 간 전체 실행 시간은 787.88초 대 776.70초로 약 1.4%(약 11초) 차이였으며, 92만 번 루프 기준 1회당 약 12μs 수준의 미세한 차이였다. Bound 단계(전체 85%)에서는 cudaHostRegister가 658.80초로 No Pinning의 663.17초보다 4.37초 빨랐으나, Infer 단계(전체 15%)에서는 cudaHostRegister가 127.18초로 No Pinning의 111.92초보다 15.26초 느려 역전되었다.

antenna_lirpa는 멀티스트림이 아니라 싱글 스트림(Single Stream)으로 동작하지만, cuBLAS Batched GEMM과 텐서 코어 활용으로 현재 C++ 멀티스트림(8분)보다 약 4배 빠르다. GPU 클록 고정 후 재실험을 위해 RAII 방식의 ScopedGpuClockLock 구조체를 작성했으며, 기본 클록 목표값은 2475 MHz로 설정되었다. 다만 이러한 측정·비교는 단일 실행 결과나 figure 캡션에 기록된 값에 기반한 경우가 많아, 반복 측정 통계나 조건별 분리 측정의 충분성은 현재 기록만으로 충분히 제시되지 않는다.

재현 관련 정보로는 모델 파일 로드 시 CustomToLirpa.py를 참조해 모델.bin 구조를 파악한 점, 가중치를 GPU에 사전 업로드하는 pre_upload_weights_to_gpu 함수 구현, backward_bound_gpu에서 new_(upper, lower)_p를 std::swap으로 포인터 스와핑한 점, 1개 커널 호출로 줄이기 위한 커널 퓨전 진행, eps_list 기반 이중 루프와 method 분기에 따른 lirpa_forward_bound_impl·lirpa_backward_bound 호출 및 certify_topk 판정 구조가 기록되어 있다. 그러나 전체 코드·구현물의 완전한 제공 여부, 환경·의존성 명세의 재현 가능 수준, 반복 측정 통계 및 조건별 분리 측정의 충분성, 데이터셋·모델 로드 절차의 재현 가능 세부 정보, 미해결·계획 항목의 재현 영향은 충분히 제시되지 않았다는 한계가 있다.

## 제3장 최적화 구성 요소와 결합 방식

### 3.1 CUDA 포팅 방향과 기본 구성

CUDA 포팅은 C++ 기반 코드에 GPU 동작이 필요한 부분만 커널로 바꾸는 방식으로 접근했다. lirpa_forward_backward_fc_array.cpp의 기본 틀을 유지한 채 병렬 연산이 필요한 구간만 device 함수로 바꾸는 구상을 검토했고, CUDA 동작이 필요한 코드만 수정해도 nvcc에서 컴파일할 수 있다는 점을 전제로 작업을 진행했다. CUDA 컴파일러(nvcc)와 CUDA 13.3(V13.3.73) 환경이 확인되었으며, 이후 최종 포팅·컴파일·실행 검증이 완료되어 기존과 동일하게 동작함을 확인했다. 이 과정에서 testing(present)/crown_test_cpu_iteration.cpp를 컴파일한 .exe 파일들을 사용했으며, 스택 메모리가 기존 128MB로는 부족하여 2GB로 늘리자 컴파일이 되었다.

포팅의 목적은 GPU 가속 효과를 확인하는 데 있었다. CPU 전용 계산 버전과 GPU 버전을 각각 만들어 신경망 정방향 통과와 CROWN 알고리즘(backward) 계산 시간을 측정했으며, 이후 AI를 통해 대략적으로 최적화된 버전(my_lirpa_op_only_GPU, crown_test_op_only_GPU.cu)을 만들어 실행해 보는 시도도 이어졌다. 이 단계의 기록은 포팅 방향과 측정 동기에 해당하며, 실제 정량 성능 수치는 이후 측정 결과에서 다룬다.

라이브러리 활용 측면에서는 cuBLAS를 연결하기 위해 컴파일 옵션에 -lcublas를 사용했다. -l은 라이브러리 링크 옵션이고, cublas는 NVIDIA가 제공하는 cuBLAS 라이브러리이며, my_lirpa_op.cu에서 cublasDgemm() 같은 GPU 최적화 행렬곱 함수를 사용하기 때문에 이 라이브러리 연결이 필요했다. CUDA Toolkit 설치 시 cuBLAS가 자동으로 포함되므로 별도 설치는 필요하지 않았고, cuBLAS는 NVIDIA GPU에서 선형대수 연산을 빠르게 수행하도록 만든 가속 라이브러리로 정리되었다.

이후 구성에서는 메모리풀에 cuBLAS를 도입하고 matvec·matmul을 기존 자체 계산이 아닌 cuBLAS 활용으로 바꾸는 버전(v1-1-1-1, my_lirpa_mempool_cuBlas.cu)이 검토되었다. 또한 cuSparse를 도입해 벡터 곱(spMV)만 적용해 보는 시도도 있었으며, 이 경우 W, W_pos, W_neg를 네트워크 준비 단계에서 CSR 형식으로 변환하고 cuSPARSE handle 및 CSR descriptor를 유지한 뒤 network_forward()의 dense matvec를 cuSPARSE SpMV로 교체했지만, 기존 matmul은 아직 유지되었다.

커널 인자 전달 방식은 포인터와 스칼라로 구분해 정리되었다. 포인터(배열)는 cudaMalloc·cudaMemcpy로 VRAM에 올린 주소를 넘겨야 하고, 스칼라(int·float·double·enum 등)는 CPU 메모리 값을 커널 실행 시 Parameter Bank/Constant Memory에 함께 실어 보낼 수 있다. 포인터 변수는 크기가 커서 CPU가 커널 매개변수 주머니에 값을 직접 넣어줄 수 없으므로 memcpy로 올려야 하며, 4\~8바이트 수준의 값만 CPU가 직접 참조해 보낼 수 있다는 점이 함께 정리되었다.

실행 구성에서는 pinned Memory 추가, cudaEvent 제어, 필요한 만큼 계산해서 D2H memcpy, certify topk 자료구조 스택화가 함께 언급되었다. 이와 별도로 graph와 비교할 때 단일 스트림 입력 복사 최적화를 논의하자는 관점이 제시되었고, 10주차 세미나 이후에는 backward_only CUDA 구현, cudaGraph 원리 학습, auto lirpa 모델 소통(repo 수령, 데이터셋·모델 동일 확인), 미팅 일정, 배칭+다중 스트림 관련 실제 환경과의 괴리 검토, 컴파일러 팀에 모델 공유가 과제로 기록되었다. auto lirpa repo는 https://github.com/horangahor/antenna_auto_lirpa에서 받아 실행해 보기로 했다.

배치·스트림 구성에서는 배치 사이즈 64일 때 약 424초가 걸렸고, 현재 구현은 배치 사이즈만큼 동일한 수의 독립 스트림을 만들어 각 스트림이 GPU 메모리를 차지하는 방식이었다. 배치 사이즈를 512로 하면 메모리를 넘지 않지만 느려졌는데, 이는 각 스트림마다 CPU가 돌아가면서 다음 커널을 런치해줘야 해서 1024개의 스트림이 각각 CPU의 커널 런치를 기다리는 구조였기 때문이다. 스트림 수를 64개 정도로 줄이고 배치 사이즈를 1024로 하는 방안은 하나의 스트림이 하나의 입력을 처리하므로 동시에 돌릴 수 있는 데이터가 64개이고 16번씩 나눠서 처리하게 되어 의미가 없다고 판단되었으며, 초기 데이터 H2D 비용은 줄지만 연산 병목은 스트림이 64개라 한 번에 64개밖에 대응하지 못하는 제약이 있었다.

현재 C++ 멀티스트림 구현은 단일 샘플 커널을 64개 스트림에 각각 런치하는 Task Parallelism 방식이며, 일반 CUDA 코어(FP32)만 사용하고 1024개 처리에 수만 번의 커널 호출이 필요해 약 8분이 소요되었다. 반면 antenna_lirpa는 멀티스트림이 아니라 싱글 스트림(Single Stream)으로 동작하지만, cuBLAS Batched GEMM과 텐서 코어 활용으로 현재 C++ 멀티스트림(8분)보다 약 4배 빠르다. 현재 구현은 2차원 block 크기와 그 안의 tid로 단일 샘플에 대한 행렬 연산(평면적 계산)을 수행 중이며, z축을 추가하면 3차원(multi sample)을 처리하는 텐서 코어를 통해 평면 연산을 한 번에 처리할 수 있다. 차기 로드맵(방법 C: Batched GEMM, 3D 텐서 연산화)은 CROWN 행렬식을 3D 텐서 레이아웃으로 변환해 cublasSgemmBatched를 호출하고 텐서 코어를 100% 활용하여, antenna_lirpa의 2분을 뛰어넘어 30초\~1분대(전체 40,000개) 진입을 목표로 한다.

방법 A(Multi-Stream 배칭, 현재 구현)는 기존 단일 샘플 커널을 유지해 3.2배 가속(25분→8분)을 얻었으나, 스트림 수의 한계(SM 포화)로 7\~8분이 한계선이다. pinned memory 성능 측정을 위해 pinned memory 미적용, my_lirpa에 있는 입력 공간 하나(HostAlloc), 지금 하는 방식(HostRegister) 3가지를 측정하려고 했으며, cudaHostRegister(Pinned/Register)와 No Pinning(일반 메모리) 간 전체 실행 시간 차이는 787.88초 대 776.70초로 약 1.4%(약 11초)이고 92만 번 루프 중 1회당 약 12μs 수준의 미세한 차이였다. Bound 단계(전체 85%)에서는 cudaHostRegister가 658.80초로 No Pinning의 663.17초보다 4.37초 더 빨랐고, Infer 단계(전체 15%)에서는 cudaHostRegister가 127.18초로 No Pinning의 111.92초보다 15.26초 더 느려 데이터 전송 직후 동기화가 일어나는 Infer 단계에서 역전되었다.

cudaHostRegister가 더 느리게 측정된 이유에 대해 컴퓨터 구조와 GPU 드라이버 레벨에서 3가지 기술적 이유가 있다고 기록되었고, 추론(Infer) 단계에서 시간이 느려졌다는 정성적 관찰도 함께 남았다.

GPU 클록 변동을 통제하기 위해 클록을 고정하고 다시 실험하기로 했으며, 이를 위해 GPU 클록 자동 잠금·자동 해제용 RAII 구조체(ScopedGpuClockLock)를 작성했다. 클록을 2800MHz로 고정하고 돌린 결과(기존 HostRegister)가 기록되었고, GPU 클록 고정 방법은 CUDA 강의 19장을 참고했다.

### 3.2 메모리 풀과 cuBLAS 도입

메모리 풀은 할당·해제 반복을 줄이기 위해 도입되었고, cuBLAS는 행렬곱·행렬-벡터 연산을 GPU 최적화 루틴으로 처리하기 위해 적용되었다. 컴파일 옵션 -lcublas로 cuBLAS 라이브러리를 링크하며, my_lirpa_op.cu에서 cublasDgemm()를 사용하기 때문에 이 연결이 필요하다. CUDA Toolkit 설치 시 cuBLAS가 자동 포함되므로 별도 설치는 필요하지 않다. cuBLAS는 NVIDIA GPU에서 선형대수 연산을 빠르게 수행하도록 만든 NVIDIA Developer 가속 라이브러리이다. 메모리 풀과 cuBLAS를 함께 적용한 버전(v1-1-1-1)에서는 matvec, matmul을 기존 자체 계산이 아니라 cuBLAS 활용으로 바꾸었고, 관련 파일은 my_lirpa_mempool_cuBlas.cu이다. 메모리 풀 크기 산정은 Matrix 3개와 Vector 6개를 동시에 사용하는 상황을 근거로 한다.

데이터 규모에 따라 전송 방식의 역할이 갈린다. 수 MB\~수백 MB 수준에서는 CPU 복사 속도가 감당이 어려워지고 DMA의 고속 대역폭이 압도적이 되어 Pinned Memory가 일반 메모리보다 빠르다. 반면 1KB 수준의 작은 데이터에서는 대역폭보다 셋업 지연시간이 지배해, Pinned는 매번 DMA 디스크립터 생성·큐 제출로 호출 1회당 약 1.0\~1.5μs의 오버헤드가 발생하고, No-Pin은 CPU L1/L2 캐시를 이용한 내부 즉시 복사로 더 빠르다.

평균 처리 속도에서는 No-Pin이 더 빠르지만, 실시간성 관점에서는 Pinned Memory가 유리하다. No-Pin은 윈도우 OS의 가상 메모리 정리나 백그라운드 작업 개입 시 최대 11.6ms까지 지연 스파이크가 발생할 수 있고, Pinned Memory는 매번 DMA 셋업 비용을 치르는 대신 OS 페이징을 차단해 어떤 상황에서도 1.64ms를 넘지 않는 안정성을 보인다. 지터는 No-Pin이 118μs, Pinned Memory가 47μs로 관측되었다.

### 3.3 가중치 사전 업로드와 메모리 전송 최적화

**표 3-1. 가중치 사전 업로드 관련 변경점과 절약 효과**

| 변경 위치 | 내용 | 절약 효과/레이어 |
| --- | --- | --- |
| d_W 타입 | double* → Matrix* | 커널에 바로 전달 가능 |
| positive_part(W,d_W) | W 복사 스킵 | 2MB 절약 |
| negative_part(W,d_W) | W 복사 스킵 | 2MB 절약 |
| matmul(A, W,d_W) | B행렬 복사 스킵(backward) | 2MB × 2회 = 4MB 절약 |
| matvec(W, x,d_W) | A행렬 복사 스킵(forward) | 2MB 절약 |



가중치 사전 업로드는 고정된 가중치를 네트워크 로드 시점에 GPU 메모리에 미리 올려, matmul·matvec 호출마다 반복되는 호스트-디바이스 복사를 줄이려는 목적으로 도입되었다. 이를 위해 pre_upload_weights_to_gpu 함수를 구현하여 각 레이어의 가중치 행렬(net->W[i])을 cudaMalloc으로 할당한 뒤 cudaMemcpy2D로 호스트에서 디바이스로 복사하고, 할당된 메모리를 net->d_W[i]에 저장해 두었다. 이후 v1-1-3(crown_test_preload_fix)에서는 GPU 주소를 저장하던 double* 타입을 Matrix*로 바꾸고, pre_upload_weights_to_gpu도 memcpy2D 대신 Matrix를 할당·복사하도록 변경하여 사전 업로드된 가중치를 실제 연산에서 활용하도록 수정하였다. 이 변경으로 positive_part와 negative_part에서 W 복사를 스킵해 각각 2MB를 절약하고, matmul의 B행렬 복사 스킵(backward)으로 4MB, matvec의 A행렬 복사 스킵(forward)으로 2MB를 절약하는 구성이 확인되었다.

이 초기 적용은 v1-1-2에서 처음 이루어져 149\~155ms 범위로 기록되었으며, 가중치만 미리 GPU에 올리는 방식으로 이후 다른 메모리 전송 최적화와 결합되기 전의 결과로 남는다.

다만 bias까지 GPU에 사전 업로드하는 시도도 있었으나, bias는 Vector이고 코드상 약 4KB 정도로 작아 CPU가 연산하기에도 무리가 없는 수준이라 성능 개선에 큰 의미를 미치지 못하는 것으로 판단되었다. 또한 가중치 사전 업로드로 memcpy를 줄이려는 접근 자체는, 실제 활용 구조가 갖춰지기 전에는 기대한 만큼의 효과를 내지 못한 것으로 기록되었다. 이와 함께 forward-backward 간 전달되는 alpha, beta 값을 메모리 풀에 올려 전달 과정을 삭제하고, 레이어별 alpha/beta GPU 버퍼를 메모리 풀에 추가해 backward가 호스트 복사 없이 GPU 버퍼를 직접 사용하도록 바꾸는 등, 메모리 전송 최적화는 가중치 사전 업로드와 별개로도 계속 조정되었다.

프로그램 전체 실행에서 memcpy는 총 18번 발생하고, 내부 6번을 제외하면 외부에서 12번 발생하며, 가중치 행은 가중치, 가중치 양수부/음수부, bias의 3개로 구성되고 신경망 구조 256 * 491 * 491 * 16에 따라 개수만큼 복사된다. 한편 커널 memcpy에서 MAXDIM 512 float 고정 복사를 필요한 크기만 복사하도록 바꾸었을 때는 CPU 계산 오버헤드가 커져 시간이 늘어나는 경우도 기록되어, 복사 크기 축소가 항상 유리한 것은 아니었다.

### 3.4 커널 퓨전과 함수 통합

커널 퓨전은 여러 단계의 커널 호출을 하나로 묶어 런치 오버헤드를 줄이는 방향으로 적용되었다. lirpa_forward_bound 함수 커널 퓨전, backward_matmul_pair_gpu 커널 통합, build_coeff_pair_fused_gpu·backward_bias_pair_fused_gpu 커널 퓨전이 수행되었고, backward_bound_gpu에서는 affine_min/max까지 함께 실행되도록 개선하여 GPU→CPU 메모리 복사를 최소화하였다. 함수 통합은 포인터·스칼라 인자 전달 규칙과 메모리 풀을 활용해 중간 복사·포인터 스와핑을 제거하는 방향으로 진행되었다. new_(upper, lower)_p 포인터 스와핑(std::swap)과 forward-backward 간 alpha/beta 메모리 풀 전달 과정 삭제 및 GPU 버퍼 직접 사용, D2H 복사 제거, 기본 초기 상태 GPU 커널 직접 생성이 함께 적용되었다. 지금까지 수행한 최적화에는 제로 memcpy, 커널 자체 실행 횟수 감소(커널 퓨전·커널 graph), GPU SM 구조를 고려한 FP64→FP32·double→float 변경이 포함된다.

lirpa_forward_bound에서 사용하는 함수들을 커널 퓨전해 호출 횟수를 줄였고, backward_bound_gpu에서는 affine 중복 계산을 삭제해 커널 2개 함수를 줄였다. new_(upper, lower)_p는 복사 대신 std::swap으로 포인터 스와핑했으며, backward의 행렬곱 커널 2개는 backward_matmul_pair_gpu로 통합했다. build_coeff_pair_fused_gpu와 backward_bias_pair_fused_gpu에도 커널 퓨전을 적용했다. 이후 1개 커널 호출로 줄일 수 있는 함수들을 계속 퓨전하는 방향으로 진행했다. 커널 퓨전 적용 후 CROWN Verification 실행에서 Elapsed time이 22.342900 ms로 기록되었고, 22ms 초반까지 나오는 경우도 관측되었다. backward_bound_gpu에 먼저 퓨전을 진행했을 때는 23.925200 ms가 관측되었으며, 컴퓨터 사정에 따라 26ms까지 뛰는 경우도 있었지만 23ms 정도가 보인다는 점이 중요하게 기록되었다. 5번까지 적용했을 때 최고 성능이 나왔다고 기록되었다.

커널 감소 내역을 보면 forward에서는 무거운 커널 연산 호출이 9개 줄었고, backward에서는 forward 부분 12개(9+3), 실제 backward 부분 3개가 줄었다. backward_only는 45회에서 33회로 감소해 26.7%로 가장 적게 줄었으며, 단순 가중치·bias 복사 커널 6개와 부호 분리 커널 6개가 줄어 커널 비용도 다르다. memcpy 호출 횟수는 66개에서 56개로 감소했다. switch 문 안에서 구조체를 선언과 동시에 만들도록 변경하려 했으나, switch 안의 선언문은 중괄호로 스코프를 덮어주지 않으면 컴파일되지 않았다. case 레이블에 따라 fwd, bwd 초기화가 생략되는 문제가 발생해, main 함수 scope의 선언문이 레이블에 의해 생략되지 않도록 작은 스코프를 만들어 해결했다. 커널 memcpy에서 기존에 MAXDIM으로 무조건 512개의 float만큼 복사하던 것을 필요한 만큼의 데이터 크기만 복사하도록 변경했으나, CPU 계산 오버헤드가 더 커져 시간이 늘었다. 이 변경은 복사 크기 조정 시도였으나 시간 증가로 이어졌고, CPU 오버헤드 증가의 정량적 분리 측정 결과는 포함되지 않았다.

### 3.5 메모리 전송 방식 비교와 안정성 관찰

**표 3-2. 메모리 방식별 1회 전송 오버헤드와 920,000회 누적 오버헤드 비교**

| 구분 | 1회 전송 오버헤드 | 920,000회 누적 오버헤드 |
| --- | --- | --- |
| No-Pin (CPU 캐시 복사) | \~0.03 μs | \~0.03초 |
| Pinned (하드웨어 DMA 셋업) | \~1.50 μs | \~1.38초 |



메모리 전송 방식은 cudaHostRegister(Pinned), cudaHostAlloc, No Pinning(일반 메모리) 세 방식으로 비교되었다. 전체 실행 시간은 cudaHostRegister 787.88초, No Pinning 776.70초로 약 1.4%(약 11초) 차이에 그쳤고, 92만 번 루프 기준 1회당 약 12μs 수준의 미세한 차이였다. Bound 단계(전체 85%)에서는 cudaHostRegister가 658.80초로 No Pinning의 663.17초보다 4.37초 빨랐으나, 데이터 전송 직후 동기화가 일어나는 Infer 단계(전체 15%)에서는 cudaHostRegister 127.18초, No Pinning 111.92초로 역전되어 cudaHostRegister가 15.26초 더 느렸다.

**표 3-3. No-Pin과 Pinned Memory의 평균 처리 속도·최대 지연·지터 비교**

| 항목 | No-Pin (일반 메모리) | Pinned Memory ( Register ) |
| --- | --- | --- |
| 평균 처리 속도 | 약 13초 빠름 (CPU 캐시 복사 이득) | 약간 느림 (DMA 셋업 오버헤드) |
| 최대 지연 (Max Spike) | 8.8 ms \~ 11.6 ms (치명적) | 1.64 ms (극도로 안정적) |
| 지터 (Jitter) | 118 $\mu\text{s}$ (불안정) | 47 $\mu\text{s}$ (안정) |



평균 처리 속도에서는 No-Pin이 더 빨랐지만, 최대 지연(Max Spike)은 No-Pin이 8.8\~11.6ms로 치명적이었고 Pinned Memory는 1.64ms로 극도로 안정적이었다. 지터도 No-Pin 118μs, Pinned 47μs로 Pinned가 더 안정적이었다. 이는 No-Pin이 평소 CPU L1/L2 캐시 복사로 빠르지만, OS 페이징 정리나 백그라운드 작업이 개입하면 최대 11.6ms까지 스파이크가 발생할 수 있고, Pinned는 매번 DMA 셋업 비용을 치르는 대신 OS 페이징을 차단해 어떤 상황에서도 1.64ms를 넘지 않는 결정론적 안정성을 보장하기 때문이다.

1KB급 작은 데이터에서는 이 차이가 더 뚜렷하다. Pinned는 매 루프마다 DMA 디스크립터 생성·큐 제출로 약 1.0\~1.5μs의 오버헤드가 발생하고, 920,000회 누적 시 약 1.38초에 이른다. 반면 No-Pin은 드라이버가 하드웨어 DMA를 부르지 않고 CPU 캐시로 내부 즉시 복사해 1회 약 0.02\~0.05μs(20\~50ns)에 끝나며, 누적 오버헤드는 약 0.03초 수준이다. 즉 작은 데이터에서는 대역폭보다 셋업 지연이 지배해 Pinned의 평균 전송 속도가 Pageable 대비 미세하게 낮게 측정될 수 있다.

**표 3-4. 메모리 방식별 cuda stream synchronize·cudaMemcpyAsync·memcpy 복사 시간 평균값 비교**

| 평균값(n = 920000) | cuda stream synchronize | cudaMemcpyAsync | memcpy 복사 시간 |
| --- | --- | --- | --- |
| hostRegister | 323μs | 5.188μs | 1.117μs |
| hostAlloc | 322μs | 5.351μs | 1.142μs |
| noPinning | 314μs | 4.932μs | 340ns |



평균값(n=920000) 기준으로 cuda stream synchronize, cudaMemcpyAsync, memcpy 복사 시간을 비교하면 hostRegister(323μs, 5.188μs, 1.117μs)와 hostAlloc(322μs, 5.351μs, 1.142μs)는 유사한 수준이고, noPinning(314μs, 4.932μs, 340ns)은 memcpy 복사 시간에서 특히 빨랐다. 다만 총 시간만 보면 No-Pin이 빨라 보여도 지터와 최악 실행 시간(WCET) 관점에서는 Pinned가 유리하다. No-Pin의 최대 지연은 8.80\~11.6ms, 지터(표준편차)는 118.94μs이고, Pinned는 최대 지연 1.64ms, 지터 47.28μs로 Pinned가 최대 지연에서 약 7배 안정적이고 지터는 약 60% 감소한다.

실시간 무선 안테나 선택 시스템처럼 1ms 통신 데드라인이 중요한 환경에서는 Pageable 메모리의 최대 11.6ms 지연 스파이크가 치명적이므로, Pinned Memory 도입이 필수적이라고 판단되었다. 다만 cudaMemcpyAsync 호출 시간 측정에서는 pinned 적용 버전이 빠르거나 느리게 측정되어 결과가 일관되지 않았고, 2copy에서 1copy로 변경해 고정 셋업 비용이 줄었을 것으로 기대했으나 마지막 측정에서 nopinned가 더 빠르게 나와 확신할 수 없었다. 이 때문에 pinned memory가 더 느린 이유에 대한 분석은 이 정도로 마무리되었다.

메모리 전송 방식은 cudaHostRegister, cudaHostAlloc(Pinned), No Pinning으로 구분해 비교하였다. 관측 결과 No-Pin이 평균 속도에서는 빠르지만 최대 지연 스파이크와 지터가 크고, Pinned는 최악 지연(WCET)과 지터에서 더 안정적이었다. 1KB급 작은 데이터에서는 DMA 셋업 오버헤드가 누적되어 CPU 캐시 복사의 이득이 역전되는 양상이 나타났다. 이러한 관찰은 실시간성 관점에서 Pinned 도입의 필요성을 판단하는 근거로 사용된다.

### 3.6 CUDA 그래프와 실행 구조 변경

cudaGraph 커널 캡처는 92만 번 입력값 계산 중 한 번의 CROWN 계산 내 수십 번 호출되는 커널을 하나의 호출로 압축해 런치 오버헤드를 줄이는 방향으로 검토되었다. 이는 커널 자체 최적화가 끝난 뒤 고려할 수 있는 스냅샷 생성 기능이라는 조건이 함께 제시되었다. 이를 바탕으로 추론과 bound를 따로 캡처한 경우와 한 번에 캡처한 경우를 구분해 커널 런치 비용을 줄이는 실험을 수행했으며, 각 방식의 정량 성능 수치는 이 기록만으로는 제시되지 않는다.

graph mode=1에서는 샘플당 cudaGraphLaunch가 infer 1회와 bound 1회, 총 2회로 유지되며, 이번 작업에서 그래프 런치 횟수 자체를 줄이지는 않았다. 그럼에도 추론 커널은 그대로 둔 상태에서 샘플 1개 전체 기준으로 Forward 33회→24회, Backward 52회→37회, Backward-only 51회→39회로 커널 호출 횟수가 줄었다. 감소 내역은 Forward에서 lower/upper matmul, lower/upper bias matvec, matrix scaling + vector affine이 각각 2→1로 통합되어 method 0 기준 레이어당 8→5회가 되었고, Backward에서는 split_pos_neg + bias accumulation이 2→1로 줄고 레이어당 backward 단계가 5→4회가 되었다. method 1에서는 forward 쪽 relaxation/cache 통합까지 포함되어 총 15회 감소했으며, Backward-only에서는 각 타깃 레이어의 weight/bias 초기 복사 2회 제거와 split/bias kernel 통합으로 총 12회 감소했다.

커널 호출 횟수 감소가 시간 감소로 바로 이어지지 않는 이유에 대한 의문도 기록되었다. forward에서는 무거운 커널 연산의 호출 횟수가 9개 줄었고, backward에서는 forward 부분 12개(9+3), 실제 backward 부분에서는 3개만 줄었으며, backward_only는 45→33회로 감소 비율이 26.7%로 가장 낮았다. 여기에 단순 가중치·bias 복사 커널 6개와 부호 분리 커널 6개가 줄어든 점까지 더해져, 줄어든 커널의 비용이 서로 다르다는 점이 함께 지적되었다.

CUDA 그래프는 커널 런치 비용을 줄이기 위해 cudaGraph로 추론과 bound를 캡처하는 방식으로 적용되었다. 추론과 bound를 따로 캡처했을 때 기준으로 약 400초 정도 시간이 줄어든 것으로 관측되었다. 이후 커밋 이전 버전(graph만 적용한 버전)을 다시 실행해본 결과 해당 버전이 더 빠른 것으로 관측되었다. 평균으로 측정했을 때 cudaGraph만 적용된 버전과 비교 대상 버전을 비교하면 forward에서는 전체적(추론, bound, 검증)으로 graph 단일 적용이 우수하며 특히 infer_s에서 약 20초 차이가 난다. backward에서는 total 시간이 비슷하며, 그 이유는 infer에서 깎아먹은 약 20초를 bound에서 graph보다 약 20초 빨리 수행하고 있기 때문이다.

실행 구조 변경 측면에서 graph mode=1에서는 샘플당 cudaGraphLaunch가 infer 1회, bound 1회로 총 2회로 유지되었다. memcpy 호출 횟수는 66개에서 56개로 감소하였다. pinned memory 입력층은 제거하되 Graph manager에는 필요에 따라 pinned memory를 선택 할당 가능하도록 남겨 두었다. 이러한 구성 변경을 포함한 실행 시간 감소가 1138s에서 758s로 기록되었다.

## 제4장 실행 시간 결과와 비교 관찰

### 4.1 초기 포팅과 CPU/GPU 버전 비교

CPU ONLY 버전은 CROWN 검증 실행 시 101.237800 ms, GPU 버전은 353.057200 ms, GPU OPTIMIZED(cuBLAS + 메모리 풀)는 229.691800 ms, HYBRID(matmul=GPU, 나머지=CPU)는 201.670100 ms, HYBRID V2는 85.785300 ms로 기록되었다. GPU OPTIMIZED와 HYBRID도 CPU보다 느렸으며, HYBRID V2에서 처음으로 CPU보다 빨라졌다. 이 수치는 모두 단일 실행 결과이며 반복 측정 통계는 없다. 이후 단계에서는 메모리 풀과 warmup, memcpy 제거, 커널 퓨전, CUDA 그래프 적용 등을 차례로 적용하면서 실행 시간을 줄여 나갔다.

**표 4-1. 단일 샘플 기준 Inference time과 Bound time 분해**

| Elapsed time: | 1.9254 ms |
| --- | --- |
| Inference time: | 0.1404 ms |
| Bound time: | 1.7846 ms |



앞선 절대 시간 비교만으로는 각 구성이 시간을 어디에 쓰는지 알기 어렵기 때문에, 이후 비교에서는 단일 샘플 기준으로 Inference time과 Bound time을 분해해 확인한다. 이 분해는 전체 실행 시간에서 추론과 경계 계산이 차지하는 비중을 보여주며, 이후 CUDA 최적화 단계의 시간 구성을 해석하는 기준이 된다.

**표 4-2. forward/backward의 sparse.py 대비 CUDA 가속 배율 및 추론+bound+검증 단축률**

| CROWN method | sparse.py (ms) | CUDA (ms) | bound 계산 성능 | 추론 + bound + 검증 |
| --- | --- | --- | --- | --- |
| forward | 6.951 | 1.307 | 5.32x <br>(81.2% 단축) | 4.86x <br>(79.4% 단축) |
| backward | 8.044 | 1.519 | 5.30x <br>(81.1% 단축) | 4.89x <br>(79.6% 단축) |



40,000회 반복 기준 단계별 시간 분해에서는 backward의 total_s가 481.7157, infer_s가 1.3569, bound_s가 479.6443, certify_s가 0.6957로, forward는 total_s가 438.3345, infer_s가 1.599, bound_s가 435.8792, certify_s가 0.6724로 나타났다. total_s, infer_s, bound_s, certify_s는 각 단계의 누적 시간(초)이고, avg_infer_ms와 avg_bound_ms는 1회당 평균 시간(밀리초)으로 backward avg_infer_ms 0.0015, avg_bound_ms 0.5214, forward avg_infer_ms 0.0017, avg_bound_ms 0.4738로 기록되었다. 두 구성 모두 bound 단계가 시간을 대부분 차지했다.

### 4.2 GPU OPTIMIZED·HYBRID·HYBRID V2 단계 결과

이후 only_GPU와 hybrid를 비교하면서, only_GPU에서 GPU로 돌리던 함수 중 hybrid에서 CPU로 되돌린 함수들을 표로 정리했다. hybrid는 only_GPU에서 matmul(cuBLAS)만 GPU에 남기고 나머지 GPU 커널을 전부 CPU for문으로 되돌린 버전이며, 새로 추가된 것은 없고 GPU 코드를 삭제해 CPU로 회귀함으로써 빨라진 사례로 요약되었다. 이 문단에는 현재 정의와 한 줄 요약만 포함되며, 정량 성능 수치는 포함하지 않는다.

GPU OPTIMIZED·HYBRID·HYBRID V2 단계는 GPU OPTIMIZED에서 HYBRID V2로 진행하며 전체 실행 시간이 85.785300ms로 줄어 CPU보다 빨라졌다는 평가가 나왔다. 이후 matmul만 GPU로 실행하는 하이브리드 시도가 이어졌고, only_GPU에서는 matmul(cuBLAS)만 GPU에 남기고 나머지를 CPU로 회귀시키는 방식으로 hybrid를 정의하였다. 이 단계의 수치와 정의는 앞선 초기 비교 및 hybrid 정의와 겹치므로, 여기서는 단계 진행 방향과 CPU보다 빨라졌다는 평가만 간략히 남긴다.

### 4.3 메모리 풀·warmup·memcpy 제거 단계 결과

메모리 풀과 warmup을 함께 적용한 단일 실행에서 CROWN Verification의 경과 시간은 152.902900 ms로 기록되었다. 여기에 cuBlas를 더한 mempool+cuBlas+warmup 조합에서는 174.978400 ms로 더 느리게 관측되었다. 이후 결과 벡터에 대한 memcpy를 제거한 mempool+warmup 조합에서는 128.894800 ms로 감소하였다. forward 함수에서 장치-호스트 간 memcpy를 극단적으로 제거한 뒤에는 64.716000 ms가 관측되었다. 이 수치들은 모두 단일 실행 결과이며, 반복 측정에 기반한 통계나 조건 간 비교 해석은 현재 기록에 제시되지 않는다.

make_zero_matrix와 vec 연산을 CPU로 되돌리는 조치에서는 22\~25 ms 정도의 감소가 관측되었고, 영벡터를 GPU에서 다시 시도할 때는 3\~5 ms 증가가 나타났다. 결과 저장용 벡터의 memcpy를 추가로 제거하면 약 10 ms가 더 줄어드는 모습이 확인되었다. 다만 각 단계의 감소 폭은 개별 실행에서 관찰된 값이며, 체계적인 제거 실험으로 각 요소의 기여도를 분리한 결과는 아니다. 따라서 이 값들은 p10의 단일 실행 관찰과 같은 성격의 개별 관측으로 보는 것이 적절하다.

make_zero_matrix와 vec 연산을 CPU로 되돌리는 조치에서는 22\~25 ms 정도의 감소가 관측되었고, 영벡터를 GPU에서 다시 시도할 때는 3\~5 ms 증가가 나타났다. 결과 저장용 벡터의 memcpy를 추가로 제거하면 약 10 ms가 더 줄어드는 모습이 확인되었다. 다만 각 단계의 감소 폭은 개별 실행에서 관찰된 값이며, 체계적인 제거 실험으로 각 요소의 기여도를 분리한 결과는 아니다.

### 4.4 커널 퓨전과 함수 통합 단계 결과

lirpa_forward_bound의 함수들을 커널 퓨전해 CROWN Verification을 실행한 결과, 단일 실행 기준으로 22.342900ms가 기록되었고 22ms 초반까지 나오는 경우도 관측되었다. 이후 backward_bound_gpu에서는 affine 중복 계산을 삭제해 커널 2개 함수가 줄고, new_(upper, lower)_p를 복사 대신 std::swap으로 포인터 스와핑했으며, backward의 행렬곱 커널 2개를 backward_matmul_pair_gpu로 통합했다. 이 통합 후에는 22ms가 보이는 비율이 늘고 최저점(28ms)이 잘 보이지 않게 되어 체감상 효과가 있는 것으로 기록되었다. build_coeff_pair_fused_gpu와 backward_bias_pair_fused_gpu의 커널 퓨전도 함께 진행되었다. alpha/beta 값을 메모리 풀에 올려 forward-backward 간 전달 과정을 삭제하고, 레이어별 alpha/beta GPU 버퍼를 추가해 backward가 host에서 H2D 복사하지 않고 GPU 버퍼를 직접 쓰도록 바꾸면서 D2D 복사 4회를 1회로 통합했다.

이 적용 후 단일 실행 기준으로 21.018800ms가 기록되었고 21.0ms 정도로 관측되었다. bias도 메모리 풀에서 관리하도록 변경했으며, 5번까지 적용했을 때 최고 성능이 나왔다고 기록되었다. 이후 affine_min/max까지 backward_bound_gpu에서 실행되도록 개선해 GPU→CPU 메모리 복사를 최소화했고, 미리 작성해둔 퓨전 함수로 affine_min과 affine_max를 하나의 커널로 병합하는 커널 퓨전이 완료되었다. 이 단계에서는 15.751000ms가 기록되었고 15ms 후반까지 나오는 결과가 관측되었다. Backward의 메모리 복사 제거 및 초기화 최적화 후에는 13.939000ms가 기록되었다. 다만 제시된 수치는 모두 단일 실행 결과이며, 반복 측정 통계나 조건별 분리 측정은 현재 기록에 제시되지 않았다.

### 4.5 CUDA 그래프 적용 후 결과

CUDA 그래프를 적용한 결과, backward_only 구성이 787.8832초로 forward 1029초, forward+backward 1138초보다 빠르게 관측되었다. 그래프 적용 후 backward_only는 787.8832초에서 630초로, forward는 1029초에서 668초로 감소하였다. 여기서 backward_only, forward, forward+backward는 각각 backward만, forward만, forward와 backward를 함께 실행한 구성으로, 앞서 나온 hybrid/only_GPU 계열 용어와는 다른 실행 구성 기준이다. forward에서는 추론·bound·검증을 통틀어 graph 단일 적용이 우수했고, 특히 infer_s 기준 약 20초 차이가 났다. backward의 total 시간이 비슷한 이유는 infer에서 줄어든 약 20초를 bound에서 graph보다 약 20초 빨리 수행했기 때문이다. 다만 제시된 수치는 요약값이며 반복 측정 통계는 없다.

### 4.6 메모리 전송 방식 비교 결과

**표 4-3. No-Pin과 Pinned의 최대 지연시간·지터 비교 및 안정성 관찰**

| 지표 | No-Pin (일반 RAM) | Pinned ( cudaHostRegister ) | 차이 |
| --- | --- | --- | --- |
| 최대 지연시간 (Max) | 8.80 ms \~ 11.6 ms | 1.64 ms | 7배 안정 (1ms 통신 타임아웃 방어) |
| 지터 (표준편차) | 118.94 μs | 47.28 μs | 60% 감소 |



cudaHostRegister와 No Pinning의 전체 실행 시간은 787.88초 대 776.70초로 약 1.4%(약 11초) 차이이며, 92만 번 루프 기준 1회당 약 12μs 수준의 미세한 차이였다. Bound 단계(전체 85%)에서는 cudaHostRegister가 658.80초로 No Pinning의 663.17초보다 4.37초 빨랐으나, Infer 단계(전체 15%)에서는 cudaHostRegister가 127.18초로 No Pinning의 111.92초보다 15.26초 느려져 역전되었다. 이 수치는 figure 캡션에 기록된 단일 실행 결과이며, 앞선 메모리 전송 방식 비교 문단들과 함께 cudaHostRegister, hostAlloc, noPinning을 비교하는 관찰의 일부로 볼 수 있다. 반복 측정 통계는 포함하지 않는다.

평균 처리 속도에서는 No-Pin이 약 13초 빨랐지만, 최대 지연시간과 지터에서는 Pinned가 더 안정적이었다. 구체적으로 No-Pin의 최대 지연시간은 8.80\~11.6ms, 지터는 118.94μs였고, Pinned는 최대 지연 1.64ms, 지터 47.28μs로 최대 지연에서 약 7배 안정적이고 지터는 약 60% 감소하였다. 즉 평균에서는 No-Pin이 유리하고, 지연 안정성과 지터 측면에서는 Pinned가 유리한 대비가 나타난다. 이 수치는 표에 제시된 비교 결과이며, 실제 측정 조건이나 반복 측정 통계는 별도로 다루지 않는다.

메모리 전송 방식 비교는 cudaHostRegister, hostAlloc, noPinning의 평균 측정값(n=920000)을 기준으로 정리했다. 측정 항목별로는 cuda stream synchronize가 hostRegister 323μs, hostAlloc 322μs, noPinning 314μs였고, cudaMemcpyAsync는 hostRegister 5.188μs, hostAlloc 5.351μs, noPinning 4.932μs였으며, memcpy 복사 시간은 hostRegister 1.117μs, hostAlloc 1.142μs, noPinning 340ns로 나타났다. 여기서 cuda stream synchronize는 스트림 동기화 시간, cudaMemcpyAsync는 비동기 복사 호출 시간, memcpy 복사 시간은 실제 복사 구간 시간을 뜻한다.

CROWN 검증(eps=1e-06, 출력 차원 16)의 단일 실행 Elapsed time은 16.9148ms로 기록되었다. 버전별 요약에서는 v0 단독 CPU 96ms, v1 커널 함수 전환 355ms, v2 메모리풀·cuBLAS 도입 229ms, v3 CPU·GPU 하이브리드 200ms가 관측되었다. 실시간 멀티스트림 forward_cuda_graph 구성에서는 전체 1055.282초, infer 131.7986초, bound 920.8438초가 측정되었다. 이 값들은 단일 실행 또는 요약 기록이며, 반복 측정 통계나 조건 간 비교 해석은 이 절에 제시되지 않았다. 단일 실행 Elapsed time과 버전별 요약, 실시간 멀티스트림 구성 결과는 서로 다른 요약 단위이므로 여기서는 각각 별도로 남겨 둔다.

## 제5장 한계와 향후 방향

### 5.1 적용 범위와 일반화 제약

본 검증은 256-491-491-16 크기의 신경망과 기존 신경망 검증팀이 사용하던 입력 데이터셋·eps_list를 대상으로 CROWN을 구현한 C++ 프로그램을 평가한 결과이며, GPU 클록 고정과 warm up은 연구 일지에서 확인된 뒤 적용된 사항이다. 신경망 크기가 매우 작아 cuBLAS·cuSparse가 오히려 느려질 수 있어 현 기준 코드에는 포함하지 않았고, 실시간 환경에서 데이터셋을 꽉 채워 넣기 어렵다는 점도 한계로 남는다. CPU보다 빨라지려면 memcpy 병목을 잡아야 한다는 판단이 있었으며, GPU OPTIMIZED 모드에서도 실행 시간이 229.691800 ms로 약 100ms 줄었지만 여전히 CPU보다 느리다고 기록되어 하이브리드 방식(matmul만 GPU로 실행)을 시도하는 동기가 되었다. 각 최적화 기법의 효과를 체계적으로 분리한 ablation study가 이루어지지 못한 점도 한계로 남는다.

현재 C++ 멀티스트림 구현은 단일 샘플 커널을 64개 스트림에 각각 런치하는 Task Parallelism 방식으로, 일반 CUDA 코어(FP32)만 사용하고 1024개 처리에 수만 번의 커널 호출이 필요해 약 8분이 소요된다. 반면 antenna_lirpa는 싱글 스트림으로 동작하지만 cuBLAS Batched GEMM과 텐서 코어 활용으로 현재 C++ 멀티스트림보다 약 4배 빠르다. 차기 로드맵은 CROWN 행렬식을 3D 텐서 레이아웃으로 변환해 cublasSgemmBatched를 호출하고 텐서 코어를 100% 활용하여 antenna_lirpa의 2분을 뛰어넘어 30초\~1분대 진입을 목표로 한다.

측정 측면에서는 warm up을 적용했을 때 걸리는 시간과 각 평균 시간이 더 늘어났고, forward가 warm up 이전 backward 급 속도가 나올 정도였으며, warm up을 해도 스파이크 데이터가 뜨고 가끔 10번 측정 시 평균 시간이 느려지는 문제가 발생했다. warm up도 warm up 이전 버전과 측정 시간에서 큰 차이 나지 않았고, 스파이크가 안 뜰 때의 시간은 오히려 더 안정적인 듯했다. cudaHostRegister와 No Pinning 간 전체 실행 시간 차이는 787.88초 대 776.70초로 약 1.4%(약 11초)이며, 92만 번 루프 중 1회당 약 12μs 수준의 미세한 차이였다. Bound 단계(전체 85%)에서는 cudaHostRegister가 658.80초로 No Pinning의 663.17초보다 4.37초 더 빨랐으나, Infer 단계(전체 15%)에서는 cudaHostRegister가 127.18초로 No Pinning의 111.92초보다 15.26초 더 느려 데이터 전송 직후 동기화가 일어나는 Infer 단계에서 역전되었다.

평균 속도에서는 No-Pin이 13초 빨랐지만 실시간성에서는 치명적인 약점이 있었으며, 최대 지연은 No-Pin이 8.8ms\~11.6ms, Pinned Memory가 1.64ms, 지터는 No-Pin이 118μs, Pinned Memory가 47μs로 나타났다.

최적화 효과 분리와 관련해서는 각 최적화 기법을 체계적으로 분리하며 ablation study를 해보지 못한 것이 한계로 남는다. CPU를 통해 필요한 만큼만 계산하는 부분이 지연 증가의 주요 후보로 좁혀졌고, 스트림 수를 64개 정도로 줄이고 배치 사이즈를 1024로 하는 방안은 하나의 스트림이 하나의 입력을 처리하므로 동시에 돌릴 수 있는 데이터가 64개라는 뜻이고 16번씩 나눠서 처리하게 되어 의미가 없다고 판단했다. 초기 데이터 H2D 비용은 확실히 줄지만 연산 병목은 스트림이 64개라 한 번에 64개밖에 대응하지 못하는 제약이 있다. GPU 클록 고정은 연구 일지에서 봤듯이 나중에 고정된 사항이고, cuda 강의 19장의 GPU 클록 고정을 참고해 클록 확인은 nvidia-smi -q -d CLOCK로, 클록 고정은 sudo nvidia-smi -pm 1과 sudo nvidia-smi -lgc 1410으로 수행했다. 클록을 2800MHz로 고정하고 돌린 결과도 기록되었으나, 이러한 측정 조건과 반복 측정 통계의 한계는 결과 해석 범위를 제한한다.

메모리 전송 방식 비교에서 No-Pin(일반 메모리)은 평소 CPU 캐시로 빠르지만 윈도우 OS의 가상 메모리 정리나 백그라운드 작업이 끼어들면 최대 11.6ms까지 튀는 스파이크가 발생할 수 있고, 이는 1ms 무선 통신 데드라인을 파괴할 수 있다. 반면 Pinned Memory는 매번 DMA 셋업 비용(1\~2μs)을 치르지만 OS 페이징을 차단하여 어떤 상황에서도 1.64ms를 넘지 않는 결정론적 안정성을 보장한다. 단일 채널 벡터(1KB) 같은 초소형 실시간 데이터 환경에서는 PCIe DMA 셋업 오버헤드로 Pinned Memory의 평균 전송 속도가 Pageable 메모리 대비 약 1.4% 낮게 측정될 수 있으나, Pageable 메모리의 최대 11.6ms 지연 스파이크와 비교하면 Pinned Memory는 WCET를 1.64ms로 제한하고 지터를 60% 이상 안정화하므로 실시간 무선 안테나 선택 시스템에서는 Pinned Memory 도입이 필수적이다.

1KB의 작은 데이터를 매 루프마다 전송할 때 Pinned Memory는 매번 하드웨어 DMA 셋업(Descriptor 생성 및 큐 제출)을 새로 수행하여 호출 1회당 약 1.0\~1.5μs의 오버헤드가 발생하고, No-Pin은 CPU의 L1/L2 캐시를 이용한 내부 즉시 복사(staging)로 약 0.02\~0.05μs(20\~50ns)에 복사가 끝나 DMA 셋업보다 30\~50배 빠르다. infer 단계에서 40,000번 동안 CPU 스레드가 cudaStreamSynchronize로 대기하고 깨어나는 과정에서의 미세 지연과 드라이버 동기화 비용이 맞물려 Pinned 쪽이 총 루프 시간에서 약 13초 정도 느려지는 결과가 나왔다. 총 시간(평균 시간)만 보면 No-Pin이 더 빨라 보이지만, 지터와 최악 실행 시간(WCET)을 보면 Pinned가 유리하다. No-Pin의 최대 지연시간은 8.80ms\~11.6ms, 지터(표준편차)는 118.94μs이고, Pinned의 최대 지연시간은 1.64ms, 지터는 47.28μs로 Pinned가 최대 지연에서 약 7배 안정적이고 지터는 약 60% 감소한다.

추론이 끝나기까지의 동기화(synchronize) 시간이 pinned memory 미적용 버전이 가장 빠르며, 이는 H2D 복사 시간의 영향일 수 있다고 분석했다. cudaMemcpyAsync 호출 시간에서 pinned memory 적용 버전이 미적용 버전보다 빠르거나 느리게 측정되어, 2copy에서 1copy로 바꾼 것이 크게 효과를 보지 못했다고 분석했다. 작은 데이터 크기(현재 입력 기준 1KB)를 staging buffer로 옮기는 고정 비용이 크지 않을 수 있다고 해석했다. 여러 번 측정 결과 pinned 적용 버전의 cudaMemcpyAsync가 더 빨라서 2copy에서 1copy로 가면서 고정 setup 비용이 줄었다고 생각했으나, 마지막 측정 결과에서 nopinned가 더 빠르게 나와 확신할 수 없게 되었다. pinned memory가 더 느린 이유에 대한 분석은 이 정도로 마무리하기로 했으며, 이를 분석하는 연구도 아니고 너무 깊게 들어가면 다른 것도 못할 것 같다고 기록했다. 결론 섹션에서 backward_only가 왜 제일 빠른지에 대한 질문을 제기했다.

### 5.2 최적화 효과 분리의 한계

각 최적화 기법을 체계적으로 분리해 개별 효과를 확인하는 ablation study는 수행하지 못했다. 여러 요소가 동시에 바뀌었기 때문에 개별 최적화의 효과를 분리하기 어렵다. 가중치 사전 업로드, make_zero 계열 CPU 회귀, 영벡터 GPU 재시도처럼 효과가 미미하거나 롤백된 사례도 있었고, backward_only는 그래프 미적용 상태에서도 bound 평균이 forward 대비 약 2.5배 수준으로 관측되었다.

이러한 동시 변경 구조는 특정 최적화가 실제 연산 개선에서 비롯된 것인지, 초기화 비용 이동이나 측정 구간 밖의 효과와 섞인 것인지 분리하기 어렵게 만든다. 따라서 관측된 시간 단축을 개별 기법의 효과로 귀속하기보다, 여러 요소가 함께 바뀐 결과로 해석하는 것이 적절하다.

커널 memcpy에서 MAXDIM 512 float 고정 복사를 필요한 크기만 복사하도록 바꾸었으나 CPU 계산 오버헤드가 커져 시간이 늘었고, forward_cuda_graph 전체 시간 약 983초 대비 CPU에서 필요한 만큼만 계산 후 복사한 버전은 1055초로 72초 더 느려졌다.

backward_only는 그래프 미적용 상태에서도 bound 평균이 forward 대비 약 2.5배 수준으로 관측되었다. 현재 구현과 antenna_lirpa의 속도 차이는 스트림 개수보다 연산기(텐서 코어 대 일반 코어)와 커널 호출 방식(3D 텐서 배치 대 단일 샘플 반복)의 체급 차이에서 비롯된다고 해석되나, 이는 정성적 해석이며 각 요인의 기여도를 정량적으로 분리한 실험 결과는 포함하지 않는다.

### 5.3 측정 조건과 반복 측정 통계의 한계

GPU OPTIMIZED 모드의 229.691800 ms, MEMPOOL + Weights PRELOAD ON GPU의 149.820400 ms, mempool + warmup의 128.894800 ms와 152.902900 ms, DTOH memcpy 제거 후 64.716000 ms, 커널 퓨전 적용 후 22.342900 ms, alpha/beta 메모리 풀 적용 후 21.018800 ms, mempool + warmup calc success의 15.828400 ms 등은 모두 해당 조건의 단일 실행 결과로 확인된다. CPU ONLY iteration ver의 193.665600 ms 역시 단일 실행 값이다. GPU OPTIMIZED 적용 후 약 100ms가 줄었지만 여전히 CPU보다 느리다고 평가했고, 50ms만 더 단축하면 CPU를 따라잡을 수 있다고 판단했으나, CPU 버전의 정확한 수치나 반복 측정 기반 비교는 이 자료에 제시되지 않았다.

측정 조건의 명시성도 제한적이다. cudaHostRegister나 No Pinning 비교, 클록 고정, Persistence mode 등 측정 조건이 원문에 직접 명시되어 있지 않다. warm up을 적용했음에도 스파이크 데이터가 발생하고, 가끔 10번 측정 시 평균 시간이 느려지는 문제가 보고되어 반복 측정의 안정성 역시 완전히 확보되지 않았다.

현재 C++ 멀티스트림 구현은 단일 샘플 커널을 64개 스트림에 각각 런치하는 Task Parallelism 방식으로, 일반 CUDA 코어(FP32)만 사용하고 1024개 처리에 수만 번의 커널 호출이 필요해 약 8분이 소요된다. 이 결과는 figure 캡션에 기록된 단일 서술이며, 반복 측정 통계나 조건별 분리 측정은 함께 제시되지 않는다. cudaHostRegister와 No Pinning의 전체 실행 시간 차이는 787.88초 대 776.70초로 약 1.4%(약 11초)이며, 92만 번 루프 중 1회당 약 12μs 수준의 미세한 차이로 보고되었다. Bound 단계(전체 85%)에서는 cudaHostRegister가 658.80초로 No Pinning의 663.17초보다 4.37초 빨랐으나, Infer 단계(전체 15%)에서는 cudaHostRegister가 127.18초로 No Pinning의 111.92초보다 15.26초 느려져 데이터 전송 직후 동기화가 일어나는 단계에서 역전되었다.

그러나 cudaMemcpyAsync 호출 시간에서 pinned 적용 버전이 빠르거나 느리게 측정되어 결과가 일관되지 않았고, 마지막 측정에서는 nopinned가 더 빠르게 나와 확신할 수 없게 되었다. 또한 클록 고정, Persistence mode 등 측정 조건이 원문에 직접 명시되어 있지 않으며, pinned 적용 여부에 따라 cudaMemcpyAsync 결과가 일관되지 않아 확정하기 어렵다는 판단이 기록되었다.

많은 실행 결과는 단일 실행 또는 요약값으로 기록되어 반복 측정 통계가 충분히 제시되지 않았다. HYBRID 모드(201.670100 ms)와 HYBRID V2 모드(85.785300 ms)는 각각 단일 실행 결과이며, CPU 버전이나 이전 모드와의 반복 측정 기반 비교는 현재 페이지에 없다. HYBRID V2의 500회 반복 누적 시간(49416.462000 ms)과 평균 반복 시간(98.832924 ms)도 단일 실행 기록으로 남는다. CPU ONLY iteration ver의 193ms는 그림의 193.665600 ms를 반올림한 값이며, 기존 backward 대비 약 93ms 느리다는 비교는 기록자의 정성적 진술로만 존재한다.

측정 조건도 원문에 직접 명시되어 있지 않다. cudaHostRegister/No Pinning 비교, 클록 고정, Persistence mode 같은 조건은 현재 페이지에서 직접 확인되지 않는다. pinned 적용 여부에 따라 cudaMemcpyAsync 결과가 일관되지 않아 확정하기 어렵다는 판단도 기록자 의견으로 남는다. 메모리 풀과 warm up 조합이 거의 200ms 단축했다는 평가, mempool의 ensure_pool() 할당이 cuBlas+warmup과 크게 다르지 않다는 판단, cuBlas 영향이 크지 않다는 판단 역시 정량 분리 측정이 아니라 정성적 비교로 제시된다.

최적화 효과를 개별 기법 단위로 분리하기 어려운 점도 한계로 남는다. 메모리 풀, warm up, memcpy 제거, 커널 퓨전, CUDA 그래프 등 여러 변경이 함께 적용되거나 적용·철회가 반복되어 각 기법의 기여도를 따로 측정하지 못했다. cuSPARSE SpMV/SpMM은 현재 모델 크기와 호출 패턴에서 느려져 현 기준 코드에는 포함하지 않았고, 공식 결과는 24 ms dense baseline으로 유지하며 cuSPARSE는 별도 benchmark 옵션으로 비교하는 방향이 기록되었다. SpMM 적용 후 약 38\~40 ms로 회귀한 현상도 오버헤드가 계산 이득보다 크다는 해석과 함께 남았지만, setup/launch 비용과 계산 이득의 정량 분리는 제시되지 않았다.

그 밖에 network_forward()가 아직 GPU 파이프라인이 아니어서 최적화가 적용되지 않은 상태라는 점, 단일 테스트에서 forward와 backward 간 3배 차이가 예상되지만 92만 개 데이터에서는 1분 정도 차이로 비슷해지고 이 문제가 아직 해결되지 않았다는 점도 한계로 기록된다. 현재 구현과 antenna_lirpa의 속도 차이는 스트림 개수보다 연산기(텐서 코어 대 일반 코어)와 커널 호출 방식(3D 텐서 배치 대 단일 샘플 반복)의 체급 차이로 해석되나, 이 원인 해석도 정량 분리 실험으로 확인되지는 않았다.

커널 퓨전 적용 후 22.342900 ms가 기록되었고 22 ms 초반까지 나오는 경우가 관측되었으며, alpha/beta 메모리 풀 적용 후 21.0 ms 정도가 보고되었으나, 이는 정성적 요약이거나 단일 실행값에 가깝다. 각 forward·backward를 20번씩 측정해 평균과 분산을 산출할 계획이 기록되었지만, 실제 통계 수치는 이 자료에 제시되지 않았다.

cudaHostRegister가 No Pinning보다 느리게 측정된 이유에 대해 컴퓨터 구조와 GPU 드라이버 레벨의 3가지 기술적 이유가 있다고 기록되었으나, 구체적 이유는 이 요소만으로 제시되지 않는다. GPU 클록 고정과 Persistence mode 설정은 이후 단계에서 다루어졌으며, cudaHostRegister/No Pinning 비교와 클록·Persistence mode 등 측정 조건이 처음부터 함께 통제되었는지는 분명하지 않다.

pinned 적용 여부에 따라 cudaMemcpyAsync 결과가 일관되지 않아 확정하기 어렵다는 판단이 남는다. 현재 가장 중요한 병목이 memcpy이며 이를 해결해야 CPU보다 빨라질 수 있다고 보았고, GPU OPTIMIZED 모드 이후에도 CPU보다 느려 matmul만 GPU로 실행하는 하이브리드 프로그램을 시도하였다. 다만 하이브리드 프로그램의 실제 구현 완료와 측정 결과는 이 자료에 제시되지 않는다.

실시간성을 확인하려면 마이크로초에서 수 밀리초(ms) 내로 제한해야 한다고 기록되었으나, 실제 달성 여부나 측정 근거는 이 요소만으로 제시되지 않는다. 따라서 관측된 실행 시간은 해당 조건에서 얻은 결과로 해석해야 하며, 모든 환경의 보장 상한이나 검증된 절대 성능으로 일반화하기는 어렵다.

### 5.4 향후 검토 방향

본 연구의 실행 시간 개선은 특정 CROWN 구현과 제한된 측정 조건에서 관측된 결과이므로, 다른 신경망 검증 환경이나 배치·네트워크 구성으로 바로 일반화하기는 어렵다. 최적화 과정에서 메모리 풀, 가중치 사전 업로드, memcpy 제거, CUDA 그래프 등 여러 기법을 함께 적용하거나 번갈아 적용했기 때문에, 각 기법의 개별 효과를 체계적으로 분리한 ablation 결과는 현재 기록에 없다. 또한 실행 시간 관측은 단일 실행이나 제한된 반복 측정 위주로 정리되어 있어, 조건별 평균·분산 같은 반복 측정 통계는 아직 충분히 정리되지 않았다. 따라서 관측된 속도 변화나 Pinned/Paged 메모리 간 차이는 해당 실험 조건에서의 결과로 해석해야 하며, 절대 성능이나 필수 도입 조건으로 단정할 수 없다.

## 제6장 결론

### 6.1 핵심 구성 요소와 결합 방식

CUDA 기반 CROWN 검증 최적화에서는 GPU 포팅 이후 메모리 전송과 커널 호출 구조를 함께 조정하는 방향으로 구성 요소를 결합했다. 초기에는 GPU OPTIMIZED 모드에서도 CPU보다 느려 matmul만 GPU로 실행하는 하이브리드 방식을 시도했고, 이후 cuBLAS 예열, 가중치 GPU 사전 업로드, 16×491 행렬 등 필요한 부분만 복사하는 방식이 정리되었다. 실행 과정에서 가장 중요한 병목은 memcpy로 인식되었으며, 메모리 풀과 warm up 조합만으로 거의 200ms가 단축되는 효과가 관측되었다. 이후 forward 함수에서 DTOH memcpy를 극단적으로 제거해 CROWN Verification 실행 시간이 64.716ms로 기록되었고, lirpa_forward_bound에서 사용하는 함수들을 커널 퓨전해 성능을 개선했다.

미리 작성해둔 퓨전 함수를 사용해 affine_min과 affine_max를 하나의 커널로 병합하는 커널 퓨전이 완료되었으며, 지금까지 수행한 최적화로 제로 memcpy, 커널 자체 실행 횟수 감소, 커널 퓨전, 커널 graph, GPU SM 구조를 고려한 FP64→FP32 및 double→float 변경이 진행되었다.

메모리 전송 방식 비교에서는 cudaHostRegister와 No Pinning의 전체 실행 시간 차이가 787.88초 대 776.70초로 약 1.4%(약 11초)에 불과했고, 92만 번 루프 중 1회당 약 12μs 수준의 미세한 차이로 나타났다. Bound 단계(전체 85%)에서는 cudaHostRegister가 658.80초로 No Pinning의 663.17초보다 4.37초 더 빨랐으나, Infer 단계(전체 15%)에서는 cudaHostRegister가 127.18초로 No Pinning의 111.92초보다 15.26초 더 느려 데이터 전송 직후 동기화가 일어나는 구간에서 역전되었다. 이 역전 때문에 전체 평균 처리 속도에서는 No-Pin이 약 13초 빨랐지만, 실시간성 관점에서는 다른 해석이 필요하다.

실시간성 관점에서는 Pinned Memory가 No-Pin보다 유리하다. Pinned Memory는 최대 지연 1.64ms, 지터 47μs로 안정적인 반면, No-Pin은 최대 지연이 8.8\~11.6ms로 치명적이고 지터가 118μs로 불안정하다. 이 차이는 1KB 수준의 작은 데이터를 매 루프마다 전송할 때 Pinned가 매번 하드웨어 DMA 셋업을 수행해 총 소요 시간이 더 길게 나온 데 기인한다. 다만 pinned memory 입력층은 제거했고, Graph manager에는 필요에 따라 pinned memory를 선택 할당 가능하도록 남겨 두었다. 즉 평균 처리 속도에서는 No-Pin이 약 13초 빨랐지만, 최악 지연(WCET)과 지터 안정성에서는 Pinned Memory가 더 유리하다.

싱글 스트림으로 동작하는 antenna_lirpa는 cuBLAS Batched GEMM과 텐서 코어를 활용해 현재 C++ 멀티스트림(8분)보다 약 4배 빠르게 동작한다. 방법 A(Multi-Stream 배칭, 현재 구현)는 기존 단일 샘플 커널을 유지해 3.2배 가속(25분→8분)을 얻었으나, 스트림 수의 한계(SM 포화)로 7\~8분이 한계선이다. 커널 감소 측면에서는 Forward에서 lower/upper matmul 2→1, lower/upper bias matvec 2→1, matrix scaling + vector affine 2→1로 method 0 기준 레이어당 8→5회, Backward에서 split_pos_neg + bias accumulation 2→1 및 레이어당 backward 단계 5→4회로 줄었고, method 1에서는 forward 쪽 relaxation/cache 통합까지 포함되어 총 15회 감소, Backward-only에서는 각 타깃 레이어의 weight/bias 초기 복사 2회 제거와 backward 단계의 split/bias kernel 통합으로 총 12회 감소했다.

### 6.2 주요 실행 시간 결과와 조건

CUDA 기반 CROWN 검증 최적화는 CPU 전용 실행의 느린 처리 시간을 줄이고 실시간 환경 대응을 목표로 진행되었다. 주요 실행 시간 결과는 단일 실행 또는 요약값이며 반복 측정 통계는 없다. CPU ONLY 101.237800ms, GPU 버전 353.057200ms, GPU OPTIMIZED 229.691800ms, HYBRID 201.670100ms, HYBRID V2 85.785300ms, mempool+warmup 152.902900ms, mempool+warmup+결과 벡터 memcpy 제거 128.894800ms, forward 함수 DTOH memcpy 제거 후 64.716000ms, alpha/beta 메모리 풀 적용 후 21.018800ms, affine_min/max 커널 퓨전 완료 후 15.751000ms, Backward 메모리 복사 제거 및 초기화 최적화 후 13.939000ms가 기록되었다. backward_only_cuda_graph 787.8832s는 forward 1029s, forward+backward 1138s보다 빠른 것으로 관측되었다.

실시간 멀티스트림 구성에서 forward_cuda_graph의 전체 시간은 1055.282초, infer는 131.7986초, bound는 920.8438초로 측정되었다. 이 수치는 표의 단일 행에 제시된 값이며, 반복 측정 통계나 다른 조건과의 비교 해석은 포함하지 않는다.

### 6.3 실시간성 관점의 시사점과 향후 방향

실시간 무선 안테나 선택 환경에서 CROWN 검증의 CUDA 가속은 연산기 활용 방식과 메모리 전송 특성을 함께 고려해야 한다. 본 연구의 최적화 과정은 단일 샘플 커널을 유지하는 멀티스트림 배칭과 텐서 코어 기반 배치 GEMM을 구분해 검토했으며, 배칭 구현으로 처리 속도가 빨라지는 관측과 함께 실시간 환경에서는 데이터셋을 가득 채우기 어렵다는 제약을 확인했다. 이 제약은 별도 분기로 보관해 두었다.

memcpy 병목을 줄여야 CPU 대비 속도 우위를 확보할 수 있다는 판단 아래, global memory·SM 병목, Nsight Compute, shared memory, 타일링, cudaGraph 원리 학습과 FP32 변경 및 Nsight Compute 분석, backward_only 속도 원인 조사, pinned memory 성능 측정, 추론·bound·검증 분리 측정 등이 검토·제안 대상으로 남아 있다. 또한 CROWN 행렬식을 3D 텐서 레이아웃으로 변환해 cublasSgemmBatched를 호출하고 텐서 코어를 100% 활용하는 방향은 antenna_lirpa의 2분을 넘어 30초\~1분대(전체 40,000개) 진입을 목표로 하는 차기 로드맵의 과제로 정리된다. 이러한 방향은 계획·제안 성격이며 실제 수행 결과로 대체하지 않는다.
