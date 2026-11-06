# 표 2-1 출판용 구조 정리 미리보기

기존 초안과 원자료를 덮어쓰지 않고 표 구조만 정리한 별도 미리보기입니다. 실제 API를 호출하지 않았습니다.

### 구성 비교

**표 2-1. 함수 / only_GPU / hybrid / 복잡도**

| 함수 | only_GPU | hybrid | 복잡도 |
| --- | --- | --- | --- |
| make_zero_matri X | GPU ( cudaMemset ) | CPU (그냥 생성자 초기화) | - |
| make_zero_vecto r | GPU ( cudaMemset ) | CPU (그냥 생성자 초기화) | - |
| make_eye | GPU 커널 | CPU for 문 | O(n) |
| mat_add | GPU 커널 + 메모리 풀 | CPU for 문 | O(n2) |
| positive_part | GPU 커널 + 메모리 풀 | CPU for 문 | O(n2) |
| negative_part | GPU 커널 + 메모리 풀 | CPU for 문 | O(n²) |
| rowwise_scale | GPU 커널 + 메모리 풀 | CPU for 문 | O(n2) |
| affine_min | GPU 커널 | CPU for 문 | O(n2) |
| affine_max | GPU 커널 | CPU for 문 | O(n2) |
| matmul | cuBLAS + 메모리풀 | cuBLAS + 메모리풀 (동 일) | O(n³) |



주: 그리고 GPU 풀 구조체도 축소되었습니다:

주: ● only_GPU: d_mat[4] + d_vec[2] (행렬 4개, 벡터 2개 미리 할당) ● hybrid: d_A, d_B, d_C 딱 3개만 (matmul 전용)

이 표는 두 구성의 함수별 CPU·GPU 실행 위치와 계산 복잡도를 정리한 자료다. 실행 시간의 측정 결과표와 구분한다.
