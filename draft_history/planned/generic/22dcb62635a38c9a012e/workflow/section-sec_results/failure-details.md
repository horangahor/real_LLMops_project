# 작성 검토 실패: section-sec_results

## 검토 지적

- [editorial; 처리 책임: editor] GPU OPTIMIZED·HYBRID·HYBRID V2 단계 결과를 정리한다고 되어 있으나, p2와 거의 같은 수치와 평가가 반복되고, only_GPU/hybrid 정의도 p7과 겹쳐 절 안에서 중복이 두드러진다.
  - 문단: sec_results_p8; 근거: 미지정
  - 실제 본문: GPU OPTIMIZED·HYBRID·HYBRID V2 단계에서는 GPU OPTIMIZED에서 HYBRID V2로 진행하며 전체 실행 시간이 85.785300ms로 줄어 CPU보다 빨라졌다는 평가가 나왔다. 이후 matmul만 GPU로 실행하는 하이브리드 시도가 이어졌고, only_GPU에서는 matmul(cuBLAS)만 GPU에 남기고 나머지를 CPU로 회귀시키는 방식으로 hybrid를 정의하였다. 이 단계의 수치와 정의는 앞선 p2의 초기 비교 및 p7의 hybrid 정의와 겹치므로, 여기서는 단계 진행 방향과 CPU보다 빨라졌다는 평가만 간략히 남긴다. [근거:E00278,E00279,E00280,E00281,E00282,E00283,E00284,E00286,E00292,E00293,E00294,E00295,E00296,E00297,E00298,E00299,E00300,E00301,E00320,E00346,E00358,E00361]
