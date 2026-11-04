# CROWN 검증 CUDA 가속 최적화 과정 및 성능 분석

## 제1장 서론

신경망 검증은 학습된 모델이 주어진 입력 영역 내에서 안전하거나 신뢰할 수 있는 출력을 내는지 확인하는 실용적 도구로 자리 잡고 있으며, 특히 안전 민감 응용에서는 단일 추론 속도보다 검증의 신뢰도와 소요 시간이 함께 중요해진다. CROWN 검증은 이러한 맥락에서 신경망의 구간 경계를 계산하는 대표적 접근법 중 하나로 활용되지만, 완전 연결 구조가 깊어지거나 평가 지점이 늘어날수록 단일 실행의 경과 시간이 실용적 부담으로 작용할 수 있다. 이에 본 연구는 CROWN 검증의 계산 경로 중 병렬화가 가능한 부분을 CUDA 환경으로 옮겨 GPU 가속을 시도하고, 초기 포팅 이후 나타난 성능 저하를 출발점으로 삼아 커널·메모리·타이밍 측정 구조를 단계적으로 최적화하는 것을 목표로 한다. 

본 연구의 1차 목표는 테스트 데이터 1개와 eps=10^-6 조건에서 CROWN 알고리즘을 수행해 16개 출력을 얻는 것이며, 이를 위해 원본 C++ 파일의 기본 틀을 유지한 채 병렬 연산이 필요한 부분만 커널 함수로 교체하는 방식으로 CUDA 포팅을 진행했다. 포팅 직후 컴파일 및 실행 검증에서 기존과 동일하게 동작함을 확인했고, CUDA 동작이 필요한 코드만 수정해도 nvcc로 컴파일이 가능하다는 점을 전제로 작업을 수행했다. 

그러나 초기 GPU 버전(my_lirpa.cu, 모든 병렬 함수를 커널로 교체)의 단일 실행 경과 시간은 353.057200ms로, CPU only 버전의 101.237800ms보다 느렸다. 이 역전 현상은 GPU 가속이 단순히 병렬 함수를 늘리는 것만으로 달성되지 않으며, 메모리 복사와 커널 구성, 단계별 비용 분해가 함께 고려되어야 함을 보여준다. 본 연구는 이 문제를 출발점으로 삼아 forward 함수의 DTOH memcpy를 극단적으로 제거해 약 103ms에서 약 64ms 수준으로 줄이고, backward_bound_gpu에서 affine 중복 계산을 삭제하며 new_(upper,lower)_p를 복사 대신 std::swap 포인터 스와핑으로 바꾸고, backward 행렬곱 커널 2개를 backward_matmul_pair_gpu로 합치고 build_coeff_pair_fused_gpu와 backward_bias_pair_fused_gpu의 커널 퓨전을 적용했다. 그 결과 실행 시간은 최저 약 21.3753ms까지 감소했으며, backward 호출 시 forward 중간 결과의 CPU 복사 여부를 플래그로 제어해 약 17.2236ms까지 추가로 낮추고 memcpy 호출 횟수도 66회에서 56회로 줄였다. 

이후에는 backward_bound_gpu에서 GPU 계산 결과를 CPU로 옮긴 뒤 affine_min/max를 CPU에서 수행하고 다시 GPU 계산이 돌아가는 불필요한 GPU→CPU→GPU→CPU 복사 구조를 개선해, affine_min/max까지 backward_bound_gpu에서 실행되도록 바꾸어 GPU→CPU 복사를 최소화했다. 또한 Forward 단계의 입력 버퍼(x0 ± eps)를 Backward에서 재사용해 H2D 복사를 제거하고, 단위행렬·영벡터 같은 default 초기 상태를 GPU 커널에서 직접 생성해 PCIe 통신 오버헤드를 줄이는 방향을 적용했다. 

복사 제어는 플래그 구조로도 세분화했다. Forward는 중간 결과(layer_bound 복사용), final_affine 복사용, 최종 결과 복사용의 3개 플래그로 나누고, backward도 layer_bound와 affine_bound 복사 제어 플래그를 각각 2개로 분리했다. 특히 forward 최종 계산(result→lower/upper bounds)의 D2H 복사 비효율을 개선해 backward가 forward보다 느렸던 문제를 해결했다. 

성능 분석의 신뢰성을 높이기 위해 추론, bound 계산, 검증 시간을 각각 분리 측정하기 위해 각 단계 끝마다 타임스탬프를 기록해 누적했고, forward와 backward 각각 20회 측정을 진행했다. 다만 warmup을 적용했을 때 평균 시간이 오히려 늘어나거나 스파이크가 발생하는 현상이 있었고, 변동 계수(CV)를 통해 간헐적 스파이크와 분산을 확인했으나 원인은 규명되지 않았다. 

이후 Real-Time Single-Sample(B=1) Latency Analysis에서는 평균 지연 1145.24 us, P99 1311.90 us, 최대 7830.90 us, 처리량 873.18 samples/sec가 측정되었고, 전체 elapsed 1055.28s 중 bound가 87.3%, infer가 12.5%, certify가 0.2%를 차지했다. 평가 샘플이 10만개로 제한된 것은 표본 측정 목적이며, cudaEvent 측정 제어 인자에 따라 드라이버 오버헤드가 달라질 수 있다는 점도 함께 고려되었다. 

추가로 CROWN 3가지 방법에서 사용하는 커널을 퓨전하고 backward_only에서 메모리 복사 커널을 제거한 결과, 전체 elapsed 시간은 787s에서 630s로 약 157초 줄어들었다. 

종합하면 본 연구의 기여는 CROWN 검증의 CUDA 포팅 자체를 수행하는 데 그치지 않고, 초기 GPU 버전이 CPU보다 느렸던 문제에서 출발해 커널 퓨전, 메모리 복사 최소화, 단계별 타이밍 분해, 플래그 기반 복사 제어, affine_min/max의 GPU 내 처리, 입력 버퍼 재사용과 default 초기 상태의 GPU 직접 생성 등을 순차적으로 적용해 실행 시간을 단계적으로 낮춘 최적화 과정 자체에 있다. 다만 측정 환경, GPU 모델, 머신 사양, 반복·웜업 조건의 세부 정보는 일부 명시되지 않았으므로, 각 시점의 elapsed time과 지연 지표는 해당 측정 조건에서의 결과로 해석해야 한다. 

## 제2장 실험 구성 및 CUDA 포팅 방법

### 2.1 CUDA 환경 및 포팅 방식

본 연구의 CUDA 포팅은 NVIDIA CUDA 컴파일러 드라이버(nvcc) release 13.3, V13.3.73을 기준으로 진행되었다 . 이 환경은 CUDA 동작이 필요한 코드만 별도로 교체하더라도 nvcc로 컴파일이 가능하다는 점을 전제로 하며, 기존 C++ 코드와의 호환성을 유지한 채 GPU 가속을 적용하는 방향으로 설계되었다 . 포팅의 출발점은 lirpa_forward_backward_fc_array.cpp의 기본 틀을 유지하는 것이었고, 병렬 연산이 필요한 부분만 device, 즉 GPU에서 동작하는 커널 함수로 교체하는 방식으로 접근하였다 . 초기 포팅 이후에는 컴파일 및 실행 검증을 통해 기존과 동일하게 동작함을 확인하였다 . 이 과정에서 배열을 통한 연산이 먼저 포팅 대상이 되었고, 최종적으로는 포팅과 컴파일, 실행 검증이 모두 완료되어 동일 동작이 확인되었다 .

검증 대상 신경망은 Fully Connected 구조이며, 입력은 256개(16×16), 은닉층은 2개로 N^(1)=491, N^(2)=491, 출력은 16개로 구성된다 . 이 구조는 교수 안내 메시지에서 제시된 가정값을 바탕으로 하며, 층별 뉴런 수와 입출력 차원은 해당 가정값 기준으로 서술된다 . 1차 목표는 테스트 데이터 1개와 eps=10^-6 조건에서 CROWN 알고리즘을 실행하여 16개 출력을 뽑는 것이다 . 이를 위해 기존 가상 신경망 대신 실제 신경망을 로드하는 방향이 함께 제시되었으며, my_lirpa.cu에서 실제 신경망을 로드해 16개 출력을 얻는 것을 1차 목표로 삼는 흐름이 확인된다 .

최적화 적용은 backward_bound_gpu와 관련 커널 함수를 중심으로 진행되었다. 먼저 backward_bound_gpu에서 사용하는 affine 중복 계산을 삭제하여 커널 함수 수를 줄였고, new_(upper, lower)_p를 복사하는 대신 std::swap을 이용한 포인터 스와핑으로 변경하였다 . 또한 backward에서 사용하던 행렬곱 커널 2개를 하나로 합친 backward_matmul_pair_gpu를 도입하였고, build_coeff_pair_fused_gpu와 backward_bias_pair_fused_gpu의 커널 퓨전을 적용하였다 . 이와 함께 기존 backward_bound_gpu에서는 GPU 계산 결과를 CPU로 옮긴 뒤 CPU에서 affine_min/max를 수행하고, 다시 affine_min/max가 GPU에서 계산되어 GPU→CPU→GPU→CPU의 불필요한 복사가 발생하는 문제가 있었다 . 이를 affine_min/max까지 backward_bound_gpu에서 실행되도록 개선하여 GPU→CPU 복사를 최소화하였다 .

추가로 forward 단계의 입력 버퍼(x0 ± eps)를 backward에서 재사용해 H2D 복사를 제거하고, 단위행렬/영벡터 같은 default 초기 상태를 GPU 커널에서 직접 생성하여 PCIe 통신 오버헤드를 최소화하였다 . Forward 단계에서는 중간 결과(layer_bound 복사용), final_affine 복사용, 최종 결과 복사용으로 플래그를 3개로 나누고, backward에서도 layer_bound와 affine_bound 복사 제어 플래그를 각각 2개로 분리하였다 . 이후 forward 최종 계산(result→lower/upper bounds)의 D2H 복사 비효율을 개선하여 backward가 forward보다 느렸던 문제를 해결하였다 . 또한 CROWN 3가지 방법에서 사용하는 커널을 퓨전하고 backward_only에서 메모리 복사 커널을 제거하였다 . 이러한 커널 퓨전과 set_shape 함수를 다른 커널에 직접 내장한 결과 CROWN 검증 실행 시간이 최저 약 21.3753ms까지 감소하였다 . 한편 backward 호출 시 forward 중간 결과를 CPU로 복사할지 여부를 플래그로 제어하여 false 설정 시 memcpy가 현저히 줄어들었고, 실행 시간이 약 17.2236ms로 감소했으며 memcpy 호출 횟수도 66→56회로 줄었다 . 다만 각 최적화의 개별 기여도는 분리 제시되지 않았고, 측정 환경에 따라 실행 시간이 23~26ms 수준으로 변동하는 경우도 함께 기록되었다 .

### 2.2 신경망 구조와 CROWN 검증 조건

CUDA 컴파일 환경은 NVIDIA CUDA 컴파일러 드라이버(nvcc) release 13.3, V13.3.73을 기준으로 하며, CUDA 동작이 필요한 코드만 교체해도 nvcc로 컴파일이 가능하다는 전제 아래 포팅을 진행했다. 원본 C++ 파일인 lirpa_forward_backward_fc_array.cpp의 기본 틀은 그대로 유지하고, 병렬 연산이 필요한 부분만 커널 함수로 바꾸는 방식으로 CUDA 포팅을 시도했으며, 초기 포팅 후 컴파일·실행 검증에서 기존과 동일하게 동작함을 확인했다. 신경망은 Fully Connected 구조로, 입력 256개(16×16), 은닉층 2개(N^(1)=491, N^(2)=491), 출력 16개로 구성된다. 1차 목표는 테스트 데이터 1개와 eps=10^-6을 사용해 CROWN 알고리즘을 돌려 16개 출력을 뽑는 것이며, 실제 신경망 로드 방향은 이 출력 16개를 뽑는 설정을 따른다. 최적화 적용 범위는 backward_bound_gpu를 중심으로 한 affine 중복 제거, new_(upper,lower)_p 복사 대신 std::swap 포인터 스와핑, backward 행렬곱 커널 2개를 하나로 합친 backward_matmul_pair_gpu 도입, build_coeff_pair_fused_gpu 및 backward_bias_pair_fused_gpu 커널 퓨전 등으로 구성된다. 기존 backward_bound_gpu는 GPU 계산 결과를 CPU로 옮긴 뒤 affine_min/max를 CPU에서 수행하고, affine_min/max도 GPU에서 다시 실행되어 GPU→CPU→GPU→CPU의 불필요한 복사가 발생했으나, 이를 affine_min/max까지 backward_bound_gpu에서 실행되도록 개선해 GPU→CPU 복사를 최소화했다. Forward 단계의 입력 버퍼(x0 ± eps)를 Backward에서 재사용해 H2D 복사를 제거하고, 단위행렬/영벡터 같은 default 초기 상태를 GPU 커널에서 직접 생성해 PCIe 통신 오버헤드를 최소화했다. Forward는 중간 결과(layer_bound 복사용), final_affine 복사용, 최종 결과 복사용으로 플래그를 3개로 나누고, backward도 layer_bound와 affine_bound 복사 제어 플래그를 각각 2개로 분리했으며, 이후 forward 최종 계산(result→lower/upper bounds)의 D2H 복사 비효율을 개선해 backward가 forward보다 느렸던 문제를 해결했다. CROWN 3가지 방법에서 사용하는 커널을 퓨전하고 backward_only에서 메모리 복사 커널을 제거했다. 커널 퓨전과 set_shape 함수를 다른 커널에 직접 내장한 결과 CROWN 검증 실행 시간이 최저 약 21.3753ms까지 감소했으며, 측정 환경에 따라 23~26ms 수준으로 변동하는 경우가 있다고 함께 기록되었다. backward 호출 시 forward 중간 결과를 CPU로 복사할지 여부를 플래그로 제어(false 시 memcpy 현저히 감소)하여 실행 시간이 약 17.2236ms로 줄었고, memcpy 호출 횟수도 66→56회로 감소했다.

### 2.3 최적화 적용 범위

CUDA 컴파일 환경은 NVIDIA CUDA 컴파일러 드라이버(nvcc) release 13.3, V13.3.73을 기준으로 하며, CUDA 동작이 필요한 코드만 교체해도 nvcc로 컴파일이 가능하다는 전제 아래 포팅을 진행했다. 포팅은 원본 C++ 파일인 lirpa_forward_backward_fc_array.cpp의 기본 틀을 유지한 채 병렬 연산이 필요한 부분만 커널 함수로 바꾸는 방식으로 수행되었고, 초기 포팅 후 컴파일·실행 검증에서 기존과 동일하게 동작함을 확인했다. 검증에 사용한 신경망은 Fully Connected 구조이며 입력 256개(16×16), 은닉층 2개(N^(1)=491, N^(2)=491), 출력 16개로 구성된다. 1차 목표는 테스트 데이터 1개와 eps=10^-6으로 CROWN 알고리즘을 돌려 16개 출력을 뽑는 것이며, 이는 실제 신경망 로드 방향과 연결된다. 최적화 적용 범위는 backward_bound_gpu를 중심으로 한 affine 중복 계산 삭제, new_(upper,lower)_p 복사 대신 std::swap 포인터 스와핑, backward 행렬곱 커널 2개를 하나로 합친 backward_matmul_pair_gpu 도입, build_coeff_pair_fused_gpu 및 backward_bias_pair_fused_gpu 커널 퓨전 등으로 구성된다. 기존 backward_bound_gpu는 GPU 계산 결과를 CPU로 옮긴 뒤 affine_min/max를 CPU에서 수행하고, affine_min/max도 GPU에서 다시 실행되어 GPU→CPU→GPU→CPU의 불필요한 복사가 발생했으나, 이를 affine_min/max까지 backward_bound_gpu에서 실행되도록 개선해 GPU→CPU 복사를 최소화했다. Forward 단계의 입력 버퍼(x0 ± eps)를 Backward에서 재사용해 H2D 복사를 제거하고, 단위행렬/영벡터 같은 default 초기 상태를 GPU 커널에서 직접 생성해 PCIe 통신 오버헤드를 최소화했다. Forward는 중간 결과(layer_bound 복사용), final_affine 복사용, 최종 결과 복사용으로 플래그를 3개로 나누고, backward도 layer_bound와 affine_bound 복사 제어 플래그를 각각 2개로 분리했으며, 이후 forward 최종 계산(result→lower/upper bounds)의 D2H 복사 비효율을 개선해 backward가 forward보다 느렸던 문제를 해결했다. CROWN 3가지 방법에서 사용하는 커널을 퓨전하고 backward_only에서 메모리 복사 커널을 제거했다. 커널 퓨전과 set_shape 함수를 다른 커널에 직접 내장한 결과 CROWN 검증 실행 시간이 최저 약 21.3753ms까지 감소했으며, 측정 환경에 따라 23~26ms 수준으로 변동하는 경우가 함께 기록되었다. backward 호출 시 forward 중간 결과를 CPU로 복사할지 여부를 플래그로 제어(false 시 memcpy 현저히 감소)하여 실행 시간이 약 17.2236ms로 줄었고, memcpy 호출 횟수도 66→56회로 감소했다.

## 제3장 최적화 단계별 성능 변화

### 3.1 초기 GPU 포팅과 CPU 대비 성능 역전

초기 CUDA 가속 단계에서는 모든 병렬 함수를 GPU 커널로 교체했음에도 CPU 전용 버전보다 실행 시간이 더 길었다. CPU only 버전은 단일 실행 경과 시간이 101.237800ms로 기록된 반면, GPU only 버전(my_lirpa.cu)은 353.057200ms로 측정되어 초기 GPU 포팅이 오히려 성능을 역전시킨 것으로 나타났다 . 이 결과는 GPU 연산 자체보다 커널 호출, 메모리 배치, 호스트-디바이스 간 이동 등 주변 비용이 초기 구현에서 더 크게 작용했음을 시사한다. 다만 해당 수치는 각 실행 출력에 표시된 Elapsed time 기준이며, 측정 반복 횟수나 웜업 여부, 머신 상태가 버전마다 다를 수 있어 동일 조건에서의 직접 비교로 단정하기는 어렵다. 또한 CPU only 96ms라는 별도 정리값(p8:e73)이 함께 언급되어 있어, 이 값이 앞선 101.237800ms와 동일 구간인지 여부는 확인이 필요하다 .

초기 GPU 버전의 높은 실행 시간을 낮추는 첫 번째 계기는 forward 함수에서 발생하는 DTOH(Device-to-Host) memcpy를 극단적으로 제거한 것이었다. 이 조치 이후 CROWN 검증(eps=1e-6, 출력 차원 16)의 실행 시간은 약 103ms에서 약 64ms로 감소했다 . 이 수준은 CPU only 버전과 비슷한 범위로 접근한 것으로 기록되어 있으며, GPU 연산보다 호스트-디바이스 간 복사가 초기 성능 병목의 상당 부분을 차지하고 있었음을 보여준다. 다만 이 값 역시 단일 시점 측정값에 가깝고 측정 환경이나 반복 조건에 따라 변동할 수 있으므로, memcpy 제거의 효과를 절대적인 성능 차이로만 해석하기보다는 복사량 감소가 실행 시간 단축의 주요 방향이었음을 보여주는 단계로 보는 것이 적절하다 .

이후에는 커널 수준의 중복 연산을 줄이고 함수 호출 경계를 최소화하는 방향으로 최적화가 이어졌다. backward_bound_gpu에서 사용하는 affine 중복 계산을 삭제해 커널 함수 수를 줄이고, new_(upper,lower)_p를 복사하는 대신 std::swap을 이용한 포인터 스와핑으로 바꾸었으며, backward에서 쓰이던 행렬곱 커널 2개를 하나의 backward_matmul_pair_gpu로 합쳤다. 여기에 build_coeff_pair_fused_gpu와 backward_bias_pair_fused_gpu의 커널 퓨전이 추가로 적용되었다 . 이러한 커널 퓨전과 함께 set_shape 함수를 다른 커널에 직접 내장한 결과, CROWN 검증 실행 시간은 최저 약 21.3753ms까지 감소했다 . 다만 기록에는 측정 환경에 따라 23~26ms 수준으로 변동하는 경우가 있다고 함께 언급되어 있어, 최저값이 항상 재현되는 단일 성능 지표로 고정된다고 보기는 어렵다 .

커널 퓨전 이후에도 호스트-디바이스 간 복사 관리는 추가로 조정되었다. backward 호출 시 forward를 함께 호출하는 구조에서, forward의 중간 결과를 CPU 메모리에 복사할지 여부를 플래그로 제어하도록 도입한 것이다. 이 플래그를 false로 설정하면 memcpy가 현저히 줄어들었고, 그 결과 실행 시간은 약 17.2236ms로 감소했다 . 이때 memcpy 호출 횟수도 66회에서 56회로 줄어든 것으로 기록되어 있다 . 이 변화는 실행 시간 단축이 단순히 커널 연산량 감소만이 아니라, 중간 결과의 불필요한 왕복 복사 제거와도 연결되어 있음을 보여준다. 다만 플래그 적용 여부에 따른 비교라는 점과, memcpy 횟수 감소가 Nsight 기준이라는 점은 함께 고려해야 하며, 복사 감소와 실행 시간 감소 사이의 정량적 인과가 어느 정도 비율인지까지 이 자료만으로 분리해 말하기는 어렵다 .

복사와 관련된 추가 개선은 데이터 이동 경로 자체를 줄이는 방향으로 이어졌다. 기존 backward_bound_gpu는 GPU에서 계산한 결과를 CPU로 옮긴 뒤 affine_min/max를 CPU에서 수행하고, 이후 affine_min/max가 다시 GPU에서 계산되어 GPU→CPU→GPU→CPU의 불필요한 복사가 발생하는 구조였다. 이를 affine_min/max까지 backward_bound_gpu에서 실행되도록 개선해 GPU→CPU 복사를 최소화했다 . 이와 함께 Forward 단계의 입력 버퍼(x0 ± eps)를 Backward에서 재사용해 H2D 복사를 제거하고, 단위행렬이나 영벡터 같은 default 초기 상태를 GPU 커널에서 직접 생성해 PCIe 통신 오버헤드를 줄이는 조치도 적용되었다 . 이 단계의 예시에서는 전체 elapsed time이 13.939ms 수준으로 낮아진 경우가 제시되었다 . 다만 이 자료에서는 입력 버퍼 재사용과 default 상태 직접 생성의 개별 기여도가 분리 제시되지 않았으므로, 해당 수치가 두 조치의 합인지, 다른 최적화 누적 효과까지 포함된 것인지 정확히 분리하기는 어렵다 .

최적화 이력은 단일 모델·단일 검증 조건에서의 elapsed time 변화를 시계열처럼 따라가며 볼 수 있다. 초기 GPU only 353.057200ms에서 시작해, DTOH memcpy 제거 후 약 103ms에서 약 64ms로 내려오고, 커널 퓨전과 set_shape 내장을 거쳐 최저 약 21.3753ms에 도달했으며, 복사 플래그 도입으로 약 17.2236ms와 memcpy 66→56회 감소가 나타났고, 이후 affine_min/max의 GPU 내 처리와 입력 버퍼 재사용 등을 통해 13.939ms 수준의 예시까지 낮아졌다 . 이 흐름에서 분명한 점은 호스트-디바이스 간 memcpy와 불필요한 왕복 복사를 줄이는 조치가 실행 시간 단축에 반복적으로 기여했다는 것이다. 반면 각 단계의 정량적 인과, 예를 들어 커널 퓨전과 복사 플래그가 각각 몇 퍼센트의 단축을 만들었는지까지는 이 자료만으로 분리하기 어렵다. 또한 측정 반복 횟수, 웜업 여부, 머신 상태, Nsight 기준 memcpy 횟수 등 측정 조건이 단계마다 완전히 동일하다고 단정할 수 없으므로, 단계별 수치를 엄격한 통제 실험의 결과라기보다 최적화 방향에 대한 경험적 변화 순서로 해석하는 것이 적절하다 .

### 3.2 DTOH memcpy 제거와 CPU 수준 근접

CROWN 검증의 CUDA 가속 최적화 과정은 초기 GPU 버전이 CPU only보다 느렸던 역전 현상에서 출발한다. CPU only 버전의 단일 실행 경과 시간은 101.237800ms였으나, 모든 병렬 함수를 커널로 교체한 GPU only 버전(my_lirpa.cu)은 353.057200ms로 더 느렸다. 이 차이는 GPU 연산 자체보다 호스트와 디바이스 간 데이터 이동 및 불필요한 복사 구조에서 비롯된 것으로 보고, 최적화는 memcpy 제거와 커널 구조 개선, 복사 플래그 도입, affine_min/max의 GPU 처리, 입력 버퍼 재사용 순으로 진행되었다.

첫 단계로 forward 함수의 DTOH memcpy를 극단적으로 제거한 결과, CROWN 검증(eps=1e-6, 출력 차원 16)의 실행 시간이 약 103ms에서 약 64ms로 감소했다. 이어서 backward_bound_gpu에서 affine 중복 계산을 삭제하고, new_(upper,lower)_p 복사 대신 std::swap 포인터 스와핑을 적용했으며, backward 행렬곱 커널 2개를 하나로 합친 backward_matmul_pair_gpu를 도입하고 build_coeff_pair_fused_gpu 및 backward_bias_pair_fused_gpu의 커널 퓨전을 적용했다. 여기에 set_shape 함수를 다른 커널에 직접 내장한 결과 실행 시간이 최저 약 21.3753ms까지 감소했으며, 측정 환경에 따라 23~26ms 수준으로 변동하는 경우가 함께 기록되었다.

다음으로는 backward 호출 시 forward 중간 결과를 CPU로 복사할지 여부를 플래그로 제어하도록 개선했다. 플래그를 false로 설정하면 memcpy가 현저히 줄어들어 실행 시간이 약 17.2236ms로 감소했고, memcpy 호출 횟수도 66회에서 56회로 감소했다. 이와 함께 기존 backward_bound_gpu는 GPU 계산 결과를 CPU로 옮긴 뒤 affine_min/max를 CPU에서 수행하고, 다시 affine_min/max를 GPU에서 실행하는 구조여서 GPU→CPU→GPU→CPU의 불필요한 복사가 발생했다. 이를 affine_min/max까지 backward_bound_gpu에서 실행되도록 개선해 GPU→CPU 복사를 최소화했다.

마지막 단계에서는 Forward 단계의 입력 버퍼(x0 ± eps)를 Backward에서 재사용해 H2D 복사를 제거하고, 단위행렬이나 영벡터 같은 default 초기 상태를 GPU 커널에서 직접 생성해 PCIe 통신 오버헤드를 최소화했다. 이 최적화의 개별 기여도는 분리 제시되지 않았으나, 전체 elapsed time이 13.939ms 수준으로 낮아진 예시가 제시되었다. 이처럼 단계별 개선은 CPU only 대비 초기 GPU의 역전 현상을 해소하고, memcpy 제거와 커널 퓨전, 복사 플래그, affine_min/max의 GPU 처리, 입력 버퍼 재사용을 통해 실행 시간을 CPU only 수준에 근접시키는 방향으로 누적되었다.

### 3.3 커널 퓨전 및 set_shape 내장과 최저 elapsed time

CPU only 버전의 단일 실행 경과 시간은 101.237800ms였으나, 모든 병렬 함수를 커널로 교체한 초기 GPU only 버전(my_lirpa.cu)은 353.057200ms로 측정되어 초기 GPU가 CPU보다 느렸다. 이후 forward 함수의 DTOH memcpy를 극단적으로 제거하자 CROWN 검증(eps=1e-6, 출력 차원 16) 실행 시간이 약 103ms에서 약 64ms로 감소했다. 이어서 backward_bound_gpu의 affine 중복 계산을 삭제하고 new_(upper,lower)_p 복사 대신 std::swap 포인터 스와핑을 적용했으며, backward 행렬곱 커널 2개를 하나로 합친 backward_matmul_pair_gpu를 도입하고 build_coeff_pair_fused_gpu 및 backward_bias_pair_fused_gpu 커널 퓨전을 적용했다. 커널 퓨전과 set_shape 함수를 다른 커널에 직접 내장한 결과 실행 시간이 최저 약 21.3753ms까지 감소했으며, 측정 환경에 따라 23~26ms 수준으로 변동하는 경우가 있었다. backward 호출 시 forward 중간 결과를 CPU로 복사할지 여부를 플래그로 제어해 false로 설정하면 memcpy가 현저히 줄어들었고, 이에 따라 실행 시간이 약 17.2236ms로 줄었으며 memcpy 호출 횟수도 66회에서 56회로 감소했다. 또한 기존 backward_bound_gpu는 GPU 계산 결과를 CPU로 옮긴 뒤 affine_min/max를 CPU에서 수행하고 다시 GPU에서 실행하는 GPU→CPU→GPU→CPU 불필요 복사가 발생했으나, affine_min/max까지 backward_bound_gpu에서 실행되도록 개선해 GPU→CPU 복사를 최소화했다. 마지막으로 Forward 단계의 입력 버퍼(x0 ± eps)를 Backward에서 재사용해 H2D 복사를 제거하고, 단위행렬/영벡터 같은 default 초기 상태를 GPU 커널에서 직접 생성해 PCIe 통신 오버헤드를 최소화했으며, 이 최적화가 적용된 예시에서는 전체 elapsed time이 13.939ms 수준으로 낮아졌다.

### 3.4 복사 플래그 도입과 memcpy 감소

CPU only 버전은 단일 실행 경과 시간이 101.237800ms였으나, 모든 병렬 함수를 커널로 교체한 초기 GPU only 버전(my_lirpa.cu)은 353.057200ms로 오히려 더 느렸다. 이후 forward 함수의 DTOH memcpy를 극단적으로 제거하자 CROWN 검증(eps=1e-6, 출력 차원 16) 실행 시간이 약 103ms에서 약 64ms로 감소했다. 여기에 backward_bound_gpu의 affine 중복 계산 삭제, new_(upper,lower)_p 복사 대신 std::swap 포인터 스와핑, backward 행렬곱 커널 2개를 하나로 합친 backward_matmul_pair_gpu 도입, build_coeff_pair_fused_gpu 및 backward_bias_pair_fused_gpu 커널 퓨전, 그리고 set_shape 함수를 다른 커널에 직접 내장하는 최적화를 적용하면서 실행 시간이 최저 약 21.3753ms까지 줄었고, 측정 환경에 따라 23~26ms 수준으로 변동하는 경우도 있었다. 다음 단계로 backward 호출 시 forward 중간 결과를 CPU로 복사할지 여부를 플래그로 제어하도록 하여, false로 설정했을 때 memcpy가 현저히 감소하면서 실행 시간이 약 17.2236ms로 낮아졌고, memcpy 호출 횟수도 66회에서 56회로 줄었다. 아울러 기존 backward_bound_gpu는 GPU 계산 결과를 CPU로 옮긴 뒤 affine_min/max를 CPU에서 수행하고 다시 GPU에서 실행하는 GPU→CPU→GPU→CPU 불필요 복사가 있었는데, affine_min/max까지 backward_bound_gpu에서 실행되도록 개선해 GPU→CPU 복사를 최소화했다. 마지막으로 Forward 단계의 입력 버퍼(x0 ± eps)를 Backward에서 재사용해 H2D 복사를 제거하고, 단위행렬이나 영벡터 같은 default 초기 상태를 GPU 커널에서 직접 생성해 PCIe 통신 오버헤드를 최소화한 결과, 전체 elapsed time이 13.939ms 수준으로 낮아진 예시가 확인되었다.

### 3.5 affine_min/max GPU 내 처리 및 입력 버퍼 재사용

CPU only 버전은 101.237800ms, 초기 GPU only 버전(my_lirpa.cu에서 모든 병렬 함수를 커널로 교체)은 353.057200ms로 측정되어, 첫 GPU 구현이 CPU보다 느렸다. 이후 forward 함수의 DTOH memcpy를 극단적으로 제거하자 CROWN 검증(eps=1e-6, 출력 차원 16) 실행 시간이 약 103ms에서 약 64ms로 감소했다. 이어서 backward_bound_gpu의 affine 중복 계산을 삭제하고, new_(upper,lower)_p 복사 대신 std::swap 포인터 스와핑을 적용했으며, backward 행렬곱 커널 2개를 하나로 합친 backward_matmul_pair_gpu를 도입하고 build_coeff_pair_fused_gpu 및 backward_bias_pair_fused_gpu 커널 퓨전을 적용했다. 여기에 set_shape 함수를 다른 커널에 직접 내장한 결과 실행 시간이 최저 약 21.3753ms까지 줄었고, 측정 환경에 따라 23~26ms 수준으로 변동하는 경우가 함께 기록되었다. backward 호출 시 forward 중간 결과를 CPU로 복사할지 여부를 플래그로 제어해 false일 때 memcpy가 현저히 감소하도록 하자 실행 시간이 약 17.2236ms로 줄고, memcpy 호출 횟수도 Nsight 기준으로 66회에서 56회로 감소했다. 기존 backward_bound_gpu는 GPU 계산 결과를 CPU로 옮긴 뒤 affine_min/max를 CPU에서 수행하고, affine_min/max도 GPU에서 다시 실행되어 GPU→CPU→GPU→CPU의 불필요한 복사가 발생했는데, 이를 affine_min/max까지 backward_bound_gpu에서 실행되도록 개선해 GPU→CPU 복사를 최소화했다. 마지막으로 Forward 단계의 입력 버퍼(x0 ± eps)를 Backward에서 재사용해 H2D 복사를 제거하고, 단위행렬/영벡터 같은 default 초기 상태를 GPU 커널에서 직접 생성해 PCIe 통신 오버헤드를 최소화했으며, 이 최적화 적용 예시에서 전체 elapsed time이 13.939ms 수준으로 낮아졌다.

### 3.6 단계별 성능 변화의 해석

CPU only 버전의 단일 실행 경과 시간은 101.237800ms였으나, 모든 병렬 함수를 커널로 교체한 초기 GPU only 버전(my_lirpa.cu)은 353.057200ms로 오히려 더 느렸다. 이는 GPU 병렬화 도입 직후에도 실행 시간이 CPU보다 크게 증가했던 역전 현상을 보여준다. 이후 forward 함수에서 DTOH memcpy를 극단적으로 제거하자 CROWN 검증(eps=1e-6, 출력 차원 16)의 실행 시간이 약 103ms에서 약 64ms로 감소했다. 다음 단계로 backward_bound_gpu의 affine 중복 계산을 삭제하고, new_(upper,lower)_p 복사 대신 std::swap 포인터 스와핑을 적용했으며, backward 행렬곱 커널 2개를 하나로 합친 backward_matmul_pair_gpu를 도입하고 build_coeff_pair_fused_gpu 및 backward_bias_pair_fused_gpu 커널 퓨전을 적용했다. 여기에 set_shape 함수를 다른 커널에 직접 내장한 결과 실행 시간이 최저 약 21.3753ms까지 감소했으며, 측정 환경에 따라 23~26ms 수준으로 변동하는 경우도 함께 기록되었다. backward 호출 시 forward 중간 결과를 CPU로 복사할지 여부를 플래그로 제어하도록 하여, false 설정 시 memcpy가 현저히 줄어들면서 실행 시간이 약 17.2236ms로 줄었고, memcpy 호출 횟수도 66회에서 56회로 감소했다. 또한 기존 backward_bound_gpu는 GPU 계산 결과를 CPU로 옮긴 뒤 affine_min/max를 CPU에서 수행하고, 이후 affine_min/max를 다시 GPU에서 실행해 GPU→CPU→GPU→CPU의 불필요한 복사가 발생했는데, 이를 affine_min/max까지 backward_bound_gpu에서 실행되도록 개선해 GPU→CPU 복사를 최소화했다. 마지막으로 Forward 단계의 입력 버퍼(x0 ± eps)를 Backward에서 재사용해 H2D 복사를 제거하고, 단위행렬이나 영벡터 같은 default 초기 상태를 GPU 커널에서 직접 생성해 PCIe 통신 오버헤드를 최소화했으며, 이 최적화가 적용된 예시에서는 전체 elapsed time이 13.939ms 수준으로 낮아졌다. 다만 해당 최적화의 개별 기여도는 분리 제시되지 않았고, 각 단계의 수치는 측정 반복 횟수·웜업 여부·머신 상태가 버전마다 다를 수 있는 단일 시점 측정값에 기반한다.

## 제4장 단계별 타이밍 분해와 배치·표본 측정 결과

### 4.1 단계별 타임스탬프 측정 설계

추론, bound 계산, 검증 시간을 각각 분리 측정하기 위해 각 단계 끝마다 타임스탬프를 기록해 누적했고, forward/backward 각각 20회 측정을 진행했다. 측정 코드에서는 신경망 정방향 통과 직후, bound 계산 종료 직후, 검증 종료 직후에 high_resolution_clock 기준으로 t0, t1, t2, t3를 찍어 time_infer_total, time_bound_total, time_certify_total에 누적하는 구조를 사용했다. case 0(ForwardBoundResult)과 case 1(BackwardBoundResult) 모두 동일한 타임스탬프 누적 경로를 따르며, bound 계산 결과는 NRVO를 적용해 4MB 이상 구조체 복사를 0회로 유지했다.  forward/backward 각 20회 측정을 완료했으며, 튀는 값이 존재해 각 20회 실행의 평균과 분산을 구해 슬라이드에 반영할 예정이었다. 

### 4.2 warmup과 스파이크·분산 관찰

warmup을 적용했으나 오히려 걸리는 시간과 각 평균 시간이 더 늘어나는 현상이 관찰되었다.  CV를 통해 간헐적 스파이크와 분산을 확인했으나, warmup 후 평균 증가 및 스파이크의 원인은 규명되지 않았다.  클록 고정, GPU 사용량 측정 등은 원인으로 단정하지 못한 채 향후 확인 항목으로 남아 있다.  즉, warmup이 측정 안정성을 높일 것이라는 기대와 달리 평균 시간 증가와 스파이크가 함께 나타나는 상태가 현재 결과의 한계로 남는다. 

### 4.3 Real-Time Single-Sample(B=1) Latency Analysis

Real-Time Single-Sample(B=1) Latency Analysis에서는 평가 샘플 10만개를 대상으로 평균 지연 1145.24us, P99 1311.90us, 최대 7830.90us, 처리량 873.18 samples/sec가 측정되었다.  전체 elapsed 1055.28s 기준 phase breakdown은 infer 131.799s(12.5%), bound 920.844s(87.3%), certify 1.597s(0.2%)로, bound 계산이 전체 시간의 대부분을 차지했다.  중앙값(P50)은 1136.80us, P95는 1179.00us, jitter(StdDev)는 60.33us였으며, 마지막 샘플 기준 Pure GPU Execution은 953.70us로 보고되었다.  평가 샘플이 10만개로 제한된 것은 표본 측정 목적이며, cudaEvent 측정 제어 인자(measure_gpu)에 따라 드라이버 오버헤드가 달라질 수 있다.  measure_gpu=0은 비활성화, 1은 마지막 샘플만 1회 측정, 2는 매 샘플 측정으로 호출당 20~50us 드라이버 오버헤드가 발생할 수 있어, 최대 지연 7830.90us는 이상치 가능성을 함께 고려해야 한다. 

### 4.4 전체 elapsed 시간 감소와 phase breakdown

전체 elapsed 시간은 787s에서 630s로 약 157초 감소했다.  ‘all eps × all data’ 기준 total elapsed는 630.94s로 줄었고, phase breakdown은 infer 131.248s(20.8%), bound 497.107s(78.8%), certify 1.613s(0.3%)로 변화했다.  Real-Time Single-Sample(B=1) Latency Analysis에서도 평가 샘플 10만개 기준 평균 689.64us, P99 822.90us, 최대 13511.00us, 처리량 1450.02 samples/sec로 측정되어, 이전 측정 대비 평균 지연과 처리량이 개선되었다.  다만 최대 지연은 13511.00us로 더 커져 이상치 해석이 필요하며, 전체 elapsed 감소와 phase 비율 변화는 bound 계산 중심의 시간 구조가 유지된 상태에서 infer와 bound의 절대 시간이 함께 줄어든 결과로 볼 수 있다. 

## 제5장 커널 횟수 감소와 메모리 복사 동작 분석

### 5.1 CROWN 방법별 커널 퓨전 및 복사 커널 제거

CROWN 3가지 방법에서 사용하는 커널을 퓨전하고 backward_only에서 메모리 복사 커널을 제거하였다. 커널 횟수 감소 폭과 시간 감소 폭은 방법별로 비례하지 않는다. forward에서는 무거운 커널 연산 호출 횟수가 9회 줄어 가장 많이 줄었으나, backward_only는 45→33회(26.7%)로 가장 적게 줄었다. 또한 단순 가중치·bias 복사 커널 6개, 부호 분리 커널 6개 감소 등 커널별 비용이 달라 시간 감소와 비례하지 않는다. 여러 번 측정 결과 pinned memory를 미적용한 버전의 복사 속도가 약 3배 빠르다. 작은 전송에서는 CUDA 내부 staging 경로가 pinned direct-DMA 경로보다 유리할 가능성이 있으나, 내부 구현을 직접 확인할 수 없어 확정은 할 수 없다.

### 5.2 방법별 커널 횟수 감소 폭과 시간 감소 폭의 불일치

CROWN의 세 가지 방법에서 사용하는 커널을 퓨전하고, backward_only에서는 메모리 복사 커널을 제거하였다. 그러나 커널 횟수 감소 폭과 시간 감소 폭은 방법별로 비례하지 않는다. forward에서는 무거운 커널 연산 호출 횟수가 9회 줄어 가장 크게 감소했지만, backward_only는 45회에서 33회로 26.7% 줄어 감소 폭이 가장 작았다. 또한 단순 가중치·bias 복사 커널 6개, 부호 분리 커널 6개 감소 등 커널별 비용이 달라, 커널 횟수 감소가 시간 감소와 직접 비례하지 않는다. 한편 여러 번 측정한 결과 pinned memory를 미적용한 버전의 복사 속도가 약 3배 빨랐다. 작은 전송에서는 CUDA 내부 staging 경로가 pinned direct-DMA 경로보다 유리할 가능성이 있으나, 내부 구현을 직접 확인할 수 없어 확정은 할 수 없다.

### 5.3 pinned memory 미적용 버전의 복사 속도 관찰

CROWN의 세 가지 방법에서 사용하는 커널을 퓨전하고, backward_only에서는 메모리 복사 커널을 제거하였다. 커널 횟수 감소 폭과 시간 감소 폭은 방법별로 비례하지 않았다. forward에서는 무거운 커널 연산 호출 횟수가 9회 줄어 가장 크게 감소했지만, backward_only는 45회에서 33회로 26.7% 줄어 감소 폭이 가장 작았다. 또한 단순 가중치·bias 복사 커널 6개와 부호 분리 커널 6개 감소 등 커널별 비용이 달라, 횟수 감소가 시간 감소와 비례하지 않는 것으로 나타났다. 여러 번 측정한 결과, pinned memory를 미적용한 버전의 복사 속도가 약 3배 빨랐다. 작은 전송에서는 CUDA 내부 staging 경로가 pinned direct-DMA 경로보다 유리할 가능성이 있으나, 내부 구현을 직접 확인할 수 없어 확정은 할 수 없다.

### 5.4 memcpy 크기 축소와 CPU 계산 오버헤드 관찰

CROWN의 세 가지 방법에서 사용하는 커널을 퓨전하고, backward_only 구성에서는 메모리 복사 커널을 제거하였다. 그 결과 커널 횟수 감소 폭과 실제 시간 감소 폭이 방법별로 비례하지 않았다. forward에서는 무거운 커널 연산 호출 횟수가 9회 줄어 가장 크게 감소했지만, backward_only는 45회에서 33회로 26.7% 줄어드는 데 그쳐 감소 폭이 가장 작았다. 또한 단순 가중치·bias 복사 커널 6개와 부호 분리 커널 6개 감소처럼 커널 종류별로 비용이 달라, 횟수 감소가 곧바로 시간 감소로 이어지지 않았다. 한편 여러 번 측정한 결과 pinned memory를 적용하지 않은 버전의 복사 속도가 약 3배 빨랐다. 작은 전송(현재 입력 기준 1Kib)에서는 CUDA 내부의 staging 경로가 pinned direct-DMA 경로보다 유리할 가능성이 있으나, 내부 구현을 직접 확인할 수 없어 확정하기는 어렵다.

## 제6장 한계 및 미해결 문제

본 연구의 성능·측정 결과는 제한된 실험 환경에서 얻어졌으며, 결과의 해석 범위를 명확히 하기 위해 다음과 같은 한계와 미해결 문제를 정리한다.

측정 환경 측면에서 CUDA 컴파일 환경은 NVIDIA CUDA 컴파일러 드라이버(nvcc) release 13.3, V13.3.73로 확인되나, CUDA 툴킷·드라이버의 정확한 설치 환경, GPU 모델, 측정 머신 사양은 명시되지 않았다. 버전 표기는 nvcc 출력 텍스트 기준이며, 실제 실행 환경의 세부 조건이 버전만으로 완전히 규정되지는 않는다.

시간 측정 결과에서도 구간 동일성 확인이 필요한 지점이 있다. CROWN 검증의 단일 실행 경과 시간에서 CPU only 버전은 101.237800ms, GPU only 버전(my_lirpa.cu, 모든 병렬 함수를 커널로 교체)은 353.057200ms로 초기 GPU 버전이 CPU보다 느렸다. 다만 별도로 정리된 CPU only 96ms라는 값과는 동일 구간인지 확인이 필요하며, 각 실행 출력에 표시된 Elapsed time 기준이라는 점과 측정 반복 횟수·웜업 여부·머신 상태가 버전마다 다를 수 있다는 점을 함께 고려해야 한다.

warmup 관련 현상도 미해결로 남아 있다. 추론·bound 계산·검증 시간을 각 단계 끝마다 타임스탬프로 기록해 누적하고 forward/backward 각각 20회 측정을 진행했으나, warmup을 적용했을 때 평균 시간이 더 늘어나거나 스파이크가 발생하는 현상이 있었다. CV를 통해 간헐적 스파이크·분산을 확인했지만 원인은 규명되지 않았고, 클록 고정이나 GPU 사용량 측정 등은 향후 확인 항목으로 제시된다.

pinned memory와 관련된 관찰도 인과 확정이 어렵다. 여러 번 측정 결과 pinned memory를 미적용한 버전의 복사 속도가 약 3배 빨랐으며, 작은 전송에서는 CUDA 내부 staging 경로가 pinned direct-DMA 경로보다 유리할 가능성이 제기되었다. 다만 이는 현재 입력 기준 1Kib 수준의 작은 전송 결과이며, CUDA 내부 구현을 직접 확인할 수 없어 인과를 확정할 수 없다.

커널 횟수 감소와 시간 감소 사이의 관계도 정량적 인과 확인이 제한적이다. 커널 횟수 감소 폭과 시간 감소 폭이 방법별로 비례하지 않으며, forward에서는 무거운 커널 연산 호출 횟수가 9회 줄어 가장 많이 줄었고 backward_only는 45→33회(26.7%)로 가장 적게 줄었다. 단순 가중치·bias 복사 커널 6개, 부호 분리 커널 6개 감소 등 커널별 비용이 다르기 때문에, 커널 횟수 감소는 forward/backward/backward_only의 구성 차이와 커널별 비용 차이로 설명되나 시간 감소와의 정량적 인과 확인은 제한적이다.

마지막으로 본 연구에서 아직 해결되지 않은 open questions로는 타일링·스트리밍·커널 퓨전의 대규모 모델 대응, float 전환 및 cuSPARSE 대체 영향, 출력 16개 선택 기준, CROWN 범위 규정 재검토, cuBlas/cuSparse 오버헤드 원인, CUDA core 점유율, forward/backward 3배 차이 소멸 원인, switch문·실행 인자 영향, cudaMemcpy 크기 축소 시 CPU 오버헤드 증가 원인, cudaGraph 캡처 방식 차이, backward_only가 forward보다 빠른 근본 원인, 방법 B/C 성능 차이 및 텐서 코어 활용도, 클록 고정 영향, 단일 스트림 cuBLAS와 멀티스트림 C++ 비교 등이 있다. 이들 항목은 현재 결과의 해석 범위를 제한하며, 향후 실험 설계와 측정 환경 통제를 통해 별도로 다룰 필요가 있다.

## 제7장 결론

CROWN 검증의 CUDA 가속 최적화 작업은 원본 C++ 구현(lirpa_forward_backward_fc_array.cpp)의 기본 틀을 유지한 채 병렬 연산이 필요한 부분만 GPU 커널로 바꾸는 포팅에서 출발했으며, 초기 포팅 후 컴파일·실행 검증에서 기존과 동일하게 동작함을 확인했다. 이후 커널 퓨전과 set_shape 함수를 다른 커널에 직접 내장하는 방식으로 CROWN 검증 실행 시간을 최저 약 21.3753ms까지 줄였고, 측정 환경에 따라 23~26ms 수준으로 변동하는 경우도 함께 기록되었다. 추가로 Forward 단계의 입력 버퍼(x0 ± eps)를 Backward에서 재사용해 H2D 복사를 제거하고, 단위행렬·영벡터 같은 기본 초기 상태를 GPU 커널에서 직접 생성해 PCIe 통신 오버헤드를 최소화한 결과, 전체 elapsed time이 13.939ms 수준으로 낮아진 예시도 확인되었다.

성능 결과는 단일 수치가 아니라 단계별·수준별 관점으로 정리할 필요가 있다. Real-Time Single-Sample(B=1) Latency Analysis에서는 평균 지연 1145.24us, P99 1311.90us, 최대 7830.90us, 처리량 873.18 samples/sec가 측정되었고, 전체 elapsed 1055.28s 중 bound가 87.3%, infer가 12.5%, certify가 0.2%를 차지했다. 이후 추가 최적화를 거친 뒤에는 전체 elapsed가 787s에서 630s로 약 157초 줄었으며, 이 시점의 Real-Time Single-Sample 측정에서는 평균 지연 689.64us, 처리량 1450.02 samples/sec가 기록되었다. 즉, 이 연구의 중심 성과는 정확도 개선이 아니라 검증 실행 시간의 GPU 가속 최적화이며, 초기 CPU 대비 역전 문제에서 출발해 elapsed time 감소와 단계별 타이밍 분해까지의 과정이 핵심 결과로 정리된다.

실용적으로는 CROWN 검증의 반복 실행 부담을 줄여 더 많은 입력·eps 조합에 대한 검증을 수행할 여지를 만들었지만, 측정 환경 명확화, warmup 스파이크 원인 규명, pinned memory와 커널 비용 차이의 정량적 인과 확인, 대규모 모델 대응, 방법 B/C 비교 등은 향후 과제로 남는다. 특히 평가 샘플이 10만개로 제한된 점, cudaEvent 측정 제어 인자에 따라 드라이버 오버헤드가 달라질 수 있는 점, 최대 지연이 이상치일 가능성 등은 결과 해석 시 함께 고려해야 한다.
