# 작성 검토 실패: subsection-evaluation-p2

## 검토 지적

- [코드의 필수 내용·근거 연결 검사; 처리 책임: writer] 필수 내용 eval_item_3: missing. 검토자가 사용했다고 보고한 근거의 인용이 본문 전체에서 누락됐습니다. 누락 근거=E00115
  - 문단: 미지정; 근거: E00115
- [composition; 처리 책임: writer] ### 3.3 오류·실패 양상과 해석: 본문 2958자 / 목표 1200자 / 허용 상한 1500자로 허용 범위를 초과했습니다. 핵심 설명·조건·반례·한계를 남기고 반복·로그·수치 열거를 줄여 목표 분량에 맞추세요. 소절 삭제나 긴 한 문단으로 합치는 방식은 쓰지 마세요.
  - 문단: none; 근거: 미지정

## eval_item_3: 오류 양상과 실패 사례를 정리한다. GPU OPTIMIZED 모드 이후에도 CPU보다 느려 matmul만 GPU로 실행하는 하이브리드 프로그램을 시도했다는 점, cuBLAS 도입 후 결과가 안 좋아졌다는 점, cuSparse spMV 적용 결과가 느려져 spMM 도입까지 검토하기로 했다는 점, spMM 적용 후 거의 40ms로 회귀했다는 점, 40000번 루프에서 forward가 backward보다 느려진 점, cudaHostRegister가 No Pinning보다 느리게 측정된 점, pinned 적용 버전의 cudaMemcpyAsync가 더 빨랐다가 마지막 측정에서 nopinned가 더 빠르게 나와 확신할 수 없게 된 점 등을 연구 일지에서 확인된 범위로 제시한다.

- 검토자 판정: met; 코드 검증 후: missing
- 배정 근거: 29개; 본문 전체 인용 누락: 1개; 검토 문단 선택 누락: 0개; 검토 목록 누락: 0개

### E00115

network_forward()는 전체 타이머에 포함되지만, 현재 cuSPARSE pipeline이 완성된 상태가 아니며, SpMV/SpMM 호출마다 descriptor와 buffer 처리 비용이 추가된다.

- 임시 승인: 아니오; 성격: research_fact; 출처: research_note
- 원문 위치: 30쪽/p30:enh:e5
- 선택 문단 인용: False; 장 전체 인용: False; 검토 목록: True
- 해석 한계: 현재 파이프라인 상태와 오버헤드 구조에 대한 설명 기록이며, 정량 분리 측정 결과는 제시되지 않았다.

