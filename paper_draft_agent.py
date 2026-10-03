"""
paper_draft_agent.py

Results & Discussion.json의 최적화 기법/벤치마크 데이터와
paper_structure.json (또는 paper_structure_analysis.json)의 레퍼런스 논문 구조/어투 분석을 결합하여
Upstage Solar LLM으로 논문 4절(연구 방법론) 및 5절(실증 평가 및 고찰) 초안을 작성하는 에이전트 모듈.
"""

import os
import sys
import json
import requests
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from config import UPSTAGE_API_KEY

SOLAR_API_URL = "https://api.upstage.ai/v1/chat/completions"
MODEL_NAME = "solar-pro"


def load_extracted_results(json_path: Optional[str | Path] = None) -> Dict[str, Any]:
    """
    method_result.py가 생성한 정형 결과 JSON 파일을 로드합니다.
    """
    base_dir = Path(__file__).resolve().parent

    if json_path is not None:
        target = Path(json_path)
    else:
        # 1순위: Results & Discussion.json, 2순위: proposal_extracted.json
        candidates = [
            base_dir / "Results & Discussion.json",
            base_dir / "proposal_extracted.json",
        ]
        target = next((p for p in candidates if p.exists()), candidates[0])

    if not target.exists():
        raise FileNotFoundError(
            f"추출 데이터 파일을 찾을 수 없습니다: {target}\n"
            f"먼저 `python method_result.py`를 실행하여 결과를 추출해주세요."
        )

    print(f"[*] 추출 데이터 로드 중: {target.name}")
    with open(target, "r", encoding="utf-8") as f:
        data = json.load(f)

    return data


def load_paper_structure(structure_path: Optional[str | Path] = None) -> str:
    """
    paper_structure.json 또는 paper_structure_analysis.json에서
    레퍼런스 논문의 구조 프로파일과 스타일 체크리스트를 로드합니다.
    """
    base_dir = Path(__file__).resolve().parent

    if structure_path is not None:
        target = Path(structure_path)
    else:
        candidates = [
            base_dir / "paper_structure.json",
            base_dir / "paper_structure_analysis.json",
        ]
        target = next((p for p in candidates if p.exists()), None)

    if not target or not target.exists():
        print("[!] 레퍼런스 논문 구조 분석 파일(paper_structure.json)을 찾을 수 없어 기본 학술 가이드를 사용합니다.")
        return ""

    print(f"[*] 레퍼런스 논문 구조/스타일 로드 중: {target.name}")
    with open(target, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 단일 객체이거나 리스트 형태인 경우 모두 지원
    profiles = []
    if isinstance(data, list):
        for idx, item in enumerate(data, start=1):
            file_name = Path(item.get("file", f"Reference_{idx}")).name
            checklist = item.get("paper_style_checklist", "")
            profile = item.get("paper_structure_profile", "")
            profiles.append(f"### [레퍼런스 논문 {idx}: {file_name}]\n\n{checklist}\n\n{profile}")
    elif isinstance(data, dict):
        checklist = data.get("paper_style_checklist", "")
        profile = data.get("paper_structure_profile", "")
        profiles.append(f"{checklist}\n\n{profile}")

    return "\n\n".join(profiles)


def generate_section4_methodology(
    extracted_data: Dict[str, Any],
    structure_guide: str = "",
    api_key: Optional[str] = None
) -> str:
    """
    제4장 연구 방법론 및 커널 최적화 설계를 매우 상세한 학술 장문으로 작성합니다.
    """
    key = api_key or UPSTAGE_API_KEY
    methods = extracted_data.get("optimization_methods") or extracted_data.get("methods_and_results") or []
    doc_title = extracted_data.get("document_title", "CUDA 최적화")
    project_name = extracted_data.get("project_name", "신경망 가속 최적화")

    system_prompt = f"""
당신은 최고 권위의 컴퓨터 공학 및 GPU 가속 시스템(HPC) 분야의 학술 논문 주저자입니다.
제공된 연구 데이터를 바탕으로 [제4장 연구 방법론 및 커널 최적화 설계 (Methodology & Kernel Optimization)]를 작성하세요.

============================================================
[레퍼런스 구조 및 스타일 가이드]
============================================================
{structure_guide if structure_guide else '학술 논문 IMRAD 형식 준수, 기술적 인과관계 상세 서술'}

============================================================
[필수 작성 지침 - 절대 요약하지 마십시오]
============================================================
1. **압축이나 요약을 절대 금지합니다.** 각 소절마다 최소 3개 이상의 충실한 학술 문단을 작성하여 실제 게재 논문 수준의 깊이를 갖추세요.
2. **문헌 인용 표기([1], [2], 저자명 등)는 일체 쓰지 마세요.**
3. 다음 4개 하위 절을 빠짐없이 상세히 기술하세요:
   - **4.1 전체 가속 파이프라인 및 시스템 아키텍처 개요**: CPU `lirpa_forward_backward_fc_array.cpp`에서 CROWN 바운드 전파를 GPU로 오프로딩하는 전체 파이프라인 아키텍처, 신경망 구조(Fully-Connected, 16개 출력 바운드 산출), 초기 나이브 이식 시 353ms로 CPU(101ms) 대비 3.5배 느렸던 근본 병목 원인을 상세히 서술.
   - **4.2 디바이스 메모리 계층 및 할당 최적화**: 
     - 4.2.1 정적 메모리 풀 사전 할당: 매 함수 호출 시 발생하는 `cudaMalloc`/`cudaFree` 오버헤드를 차단하기 위한 1MB 단위 정적 메모리 풀 구조체 설계 원리.
     - 4.2.2 포인터 스와핑(`std::swap`) 및 버퍼 재사용: 복사 오버헤드를 제거하는 포인터 교체 메커니즘.
     - 4.2.3 Alpha/Beta GPU 버퍼 캐싱 및 Bias 풀 관리: 레이어별 alpha/beta 버퍼를 메모리 풀에 유지하여 forward-backward 간 D2D 복사 4회를 1회로 통합한 원리.
     - 4.2.4 가중치(W, W_pos, W_neg) 사전 GPU 상주 및 불필요한 DTOH 복사 차단 기법.
   - **4.3 CUDA 커널 설계 및 가속 라이브러리 최적화**:
     - 4.3.1 cuBLAS 행렬곱 라이브러리(`cublasDgemm`) 도입 배경과 한계: 나이브 커널 대체 효과 및 작은 행렬 크기에서의 런치 오버헤드.
     - 4.3.2 다중 커널 퓨전: `backward_matmul_pair_gpu`, `build_coeff_pair_fused_gpu`, `affine_minmax_pair_gpu` 통합 과정 및 `set_shape` 함수의 커널 내부 인라인 내장 메커니즘.
     - 4.3.3 불필요한 동기화(`cudaDeviceSynchronize`) 제거 및 enum 인자 값 직접 전달.
   - **4.4 런타임 최적화 및 파이프라인 스케일업**:
     - 4.4.1 CPU-GPU 하이브리드 실행 전략: 행렬곱만 GPU, 벡터 연산은 CPU 회귀.
     - 4.4.2 배치 멀티스트림 비동기 파이프라인: 단일 스트림 병목을 탈피하기 위한 다중 스트림(`cudaStream_t`) 및 동시 실행 설계.
     - 4.4.3 `cudaGraph` 커널 실행 캡처: 50회 이상의 반복 커널 런치를 단일 그래프 실행으로 압축하여 CPU 오버헤드를 원천 차단한 기법.
"""

    user_prompt = f"""
[프로젝트]: {project_name} | {doc_title}
[추출된 최적화 기법 데이터]:
{json.dumps(methods, ensure_ascii=False, indent=2)}

위 데이터를 전부 활용하여 [제4장 연구 방법론 및 커널 최적화 설계]를 실제 투고용 학술 논문 본문처럼 아주 상세하고 깊이 있게 장문으로 작성해주세요. (인용 표기 제외)
"""

    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "model": MODEL_NAME,
        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        "temperature": 0.2
    }
    resp = requests.post(SOLAR_API_URL, headers=headers, json=payload, timeout=180)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def generate_section5_results(
    extracted_data: Dict[str, Any],
    structure_guide: str = "",
    api_key: Optional[str] = None
) -> str:
    """
    제5장 실증 평가 및 결과 고찰을 매우 상세한 학술 장문으로 작성합니다.
    """
    key = api_key or UPSTAGE_API_KEY
    methods = extracted_data.get("optimization_methods") or extracted_data.get("methods_and_results") or []
    doc_title = extracted_data.get("document_title", "CUDA 최적화")
    project_name = extracted_data.get("project_name", "신경망 가속 최적화")

    system_prompt = f"""
당신은 최고 권위의 컴퓨터 공학 및 고성능 컴퓨팅(HPC) 분야의 학술 논문 주저자입니다.
제공된 연구 데이터를 바탕으로 [제5장 실증 평가 및 결과 고찰 (Results & Discussion)]을 작성하세요.

============================================================
[레퍼런스 구조 및 스타일 가이드]
============================================================
{structure_guide if structure_guide else '학술 논문 IMRAD 형식 준수, 정량 벤치마크 및 심층 고찰 서술'}

============================================================
[필수 작성 지침 - 절대 요약하지 마십시오]
============================================================
1. **압축이나 요약을 절대 금지합니다.** 구체적인 수치(ms 단위 실행 시간, NVTX 복사 횟수, 초 단위 처리 시간)를 하나도 빠짐없이 명시하며 문단을 길고 풍부하게 서술하세요.
2. **문헌 인용 표기([1], [2] 등)는 일체 쓰지 마세요.**
3. 다음 5개 하위 절을 명확한 마크다운 표와 함께 상세히 기술하세요:
   - **5.1 실험 환경 및 평가 프로토콜**: 하드웨어 사양, CUDA/cuBLAS 툴킷 버전, 벤치마크 데이터셋(입력 크기 및 epsilon sweep 조건), 성능 측정 기준(Wall-clock time, NVTX 마커).
   - **5.2 점진적 최적화 단계별 성능 분석 (종합 성능 비교표 포함)**:
     - 초기 GPU 포팅(353.057ms, CPU 101ms 대비 3.5배 느림)에서 시작하여
     - cuBLAS 대체 및 메모리 풀(229.691ms)
     - cuBLAS 예열 및 하이브리드 v2(85.785ms - 최초로 CPU 성능 역전)
     - forward DTOH 극단적 제거(64.716ms)
     - 불필요한 동기화 제거(25.457ms)
     - 다중 커널 퓨전 및 set_shape 내장(21.375ms)
     - alpha/beta 버퍼 캐싱 및 bias 메모리 풀(21.018ms)
     - affine_minmax 통합(15.828ms)
     - Backward 메모리 복사 제거 및 GPU 기본 초기화(13.939ms 최종 달성)
     - 위 전체 흐름을 일목요연하게 정리한 **[표 5.1 최적화 단계별 지연시간 및 가속비 비교]**를 반드시 포함하고, 각 단계의 성능 도약 요인을 3개 이상의 상세 문단으로 분석.
   - **5.3 메모리 전송 최적화 및 NVTX 프로파일링 분석**:
     - NVTX 구간 내 `cudaMemcpy` 호출 횟수 감소(109회 ➔ 94회 ➔ 54회)
     - D2H 전송 감소(44회 ➔ 20회, API 시간 7.61ms ➔ 3.51ms)
     - 가중치 및 활성화 함수 enum 값 직접 전달(memcpy 66개 ➔ 56개)에 따른 PCIe 대역폭 절감 효과 분석.
   - **5.4 대규모 워크로드 처리량 스케일업 분석**:
     - 4만개 입력에 대한 단일 스트림 처리(25분) 대비 멀티스트림 배치 시스템(8분)의 3배 이상 처리량 향상 분석.
     - CROWN 캡처 cudaGraph 적용을 통한 단일 CROWN 계산 400초 단축(1564초 ➔ 1114초) 및 커널 런치 오버헤드 제거 효과 상술.
   - **5.5 네거티브 실험 분석 및 엔지니어링 한계 고찰 (학술적 핵심)**:
     - 1) cuSPARSE 도입 실패 요인: CSR 형식 변환 및 SpMV/SpMM 오버헤드로 인해 cuBLAS 대비 오히려 지연시간이 증가한 현상(24ms ➔ 27.1ms 및 38.5ms)의 원인(작은 행렬 차원, 디스크립터 생성 비용) 분석.
     - 2) GPU 웜업의 50ms 초기화 착시 효과 규명: `pre_upload_weights_to_gpu`가 CUDA 컨텍스트 초기화 비용을 타이머 밖으로 밀어낸 웜업 효과였음을 명확히 짚음.
     - 3) Pinned memory 비동기 복사 실패: 단일 그래프 대비 72초 지연(983초 ➔ 1055초)된 PCIe 전송과 호스트 스케줄링 간 불균형 분석.
     - 4) FP32/FP64 정밀도 트레이드오프 및 구조체 재설계 한계.
   - **5.6 소결론 및 시사점**: 본 실증 평가가 제시하는 신경망 포멀 검증 가속화의 핵심 가이드라인 요약.
"""

    user_prompt = f"""
[프로젝트]: {project_name} | {doc_title}
[추출된 최적화 기법 데이터]:
{json.dumps(methods, ensure_ascii=False, indent=2)}

위 데이터를 전부 활용하여 [제5장 실증 평가 및 결과 고찰]을 정식 마크다운 표와 구체적 수치, 심층 분석을 포함하여 실제 학술 논문처럼 매우 방대하고 깊이 있게 장문으로 작성해주세요. (인용 표기 제외)
"""

    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "model": MODEL_NAME,
        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        "temperature": 0.2
    }
    resp = requests.post(SOLAR_API_URL, headers=headers, json=payload, timeout=180)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def generate_paper_sections_draft(
    extracted_data: Dict[str, Any],
    structure_guide: str = "",
    api_key: Optional[str] = None
) -> str:
    """
    제4장(방법론)과 제5장(실증 평가)을 각각 심도 있게 생성한 후 하나의 완성형 논문 초안으로 결합합니다.
    """
    print("[*] 제4장 (연구 방법론 및 커널 최적화 설계) 심층 작성 중...")
    sec4 = generate_section4_methodology(extracted_data, structure_guide, api_key)

    print("[*] 제5장 (실증 평가 및 결과 고찰) 심층 작성 중...")
    sec5 = generate_section5_results(extracted_data, structure_guide, api_key)

    full_draft = f"""# CROWN 신경망 검증을 위한 GPU 가속 및 메모리 계층 최적화 기법 연구

---

{sec4}

---

{sec5}
"""
    return full_draft


class PaperDraftOrchestrator:
    """
    논문 초안 작성 전체 파이프라인을 총괄하는 Orchestrator 클래스.
    1. 연구 원천 문서 분석 및 최적화 기법/수치 추출 (method_result.py)
    2. 레퍼런스 논문 IMRAD 구조 및 서술 스타일 가이드 로드 (paper_structure.py)
    3. Upstage Solar LLM을 통한 제4장(방법론) 및 제5장(결과/고찰) 학술 초안 합성
    4. 벤치마크 지표 계산 및 결과 아티팩트 저장
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or UPSTAGE_API_KEY
        self.base_dir = Path(__file__).resolve().parent

    def run_pipeline(
        self,
        research_pdf_path: Optional[str | Path] = None,
        results_json_path: Optional[str | Path] = None,
        structure_json_path: Optional[str | Path] = None,
        progress_callback: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """
        Orchestration 파이프라인 전체 실행
        """
        # [Stage 1/3] 연구 결과 데이터 준비
        if progress_callback:
            progress_callback(15, "[Stage 1/3] 최적화 기법 및 실측 벤치마크 데이터 로드/추출 중...")

        if results_json_path and Path(results_json_path).exists():
            extracted_data = load_extracted_results(results_json_path)
        elif research_pdf_path and Path(research_pdf_path).exists():
            # PDF가 주어졌으나 캐시된 JSON이 없거나 새로 실행해야 할 경우
            cached_json = self.base_dir / "Results & Discussion.json"
            if cached_json.exists():
                extracted_data = load_extracted_results(cached_json)
            else:
                from method_result import run_cuda_optimization_agent
                extracted_data = run_cuda_optimization_agent(research_pdf_path)
        else:
            extracted_data = load_extracted_results()

        # [Stage 2/3] 레퍼런스 논문 구조/스타일 프로파일링 로드
        if progress_callback:
            progress_callback(50, "[Stage 2/3] 레퍼런스 논문 IMRAD 구조 및 서술 체크리스트 로드 중...")

        structure_guide = load_paper_structure(structure_json_path)

        # [Stage 3/3] Solar LLM 기반 학술 초안 작성
        if progress_callback:
            progress_callback(75, "[Stage 3/3] Upstage Solar LLM을 통한 제4장 및 제5장 논문 초안 작성 중...")

        draft_markdown = generate_paper_sections_draft(
            extracted_data=extracted_data,
            structure_guide=structure_guide,
            api_key=self.api_key,
        )

        # 산출물 저장
        output_md_path = self.base_dir / "paper_draft_section4_5.md"
        with open(output_md_path, "w", encoding="utf-8") as f:
            f.write(draft_markdown)

        # 지표 산출
        methods = extracted_data.get("optimization_methods") or extracted_data.get("methods_and_results") or []
        metrics = {
            "total_methods": len(methods),
            "baseline_latency": "353.057 ms",
            "final_latency": "13.939 ms",
            "latency_reduction_pct": 96.05,
            "speedup_ratio": "25.33x",
            "memcpy_reduction": "109회 -> 54회 (50.5% 감소)",
            "output_md_path": str(output_md_path),
        }

        if progress_callback:
            progress_callback(100, "[완료] 논문 초안 및 벤치마크 지표 오케스트레이션 완료!")

        return {
            "draft_markdown": draft_markdown,
            "extracted_data": extracted_data,
            "structure_guide": structure_guide,
            "metrics": metrics,
        }


def run_paper_drafting_demo(
    input_json_path: Optional[str | Path] = None,
    structure_path: Optional[str | Path] = None
) -> str:
    """
    데모 실행 함수
    """
    orchestrator = PaperDraftOrchestrator()
    result = orchestrator.run_pipeline(
        results_json_path=input_json_path,
        structure_json_path=structure_path,
    )
    return result["draft_markdown"]


if __name__ == "__main__":
    custom_data_path = sys.argv[1] if len(sys.argv) > 1 else None
    custom_struct_path = sys.argv[2] if len(sys.argv) > 2 else None
    draft = run_paper_drafting_demo(custom_data_path, custom_struct_path)
    print("\n--- [초안 미리보기 (일부)] ---")
    print(draft[:1200])

