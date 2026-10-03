import os
import sys
import time
import json
import requests
from pathlib import Path
from typing import Any, Dict, List, Optional
from config import UPSTAGE_API_KEY, METHOD_RESULT_AGENT_ID, METHOD_RESULT_CONFIG_ID

BASE_URL_V2 = "https://api.upstage.ai/v2"
API_KEY = UPSTAGE_API_KEY
AGENT_ID = METHOD_RESULT_AGENT_ID or "agt_9wpjTr9DgD6KiG2ozqGUzW"
CONFIG_ID = METHOD_RESULT_CONFIG_ID or "2"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

def upload_file(file_path: str | Path) -> str:
    """
    로컬 파일 경로를 받아 Upstage Files API (v2)에 업로드하고 file_id를 반환합니다.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {file_path}")

    url = f"{BASE_URL_V2}/files"
    headers = {"Authorization": f"Bearer {API_KEY}"}

    print(f"[*] 파일 업로드 중: {path.name} ({path.stat().st_size:,} bytes)...")
    with open(path, "rb") as f:
        files = {"file": f}
        data = {"purpose": "user_data"}
        resp = requests.post(url, headers=headers, files=files, data=data, timeout=120)

    if resp.status_code != 200:
        raise RuntimeError(f"파일 업로드 실패 ({resp.status_code}): {resp.text}")

    resp_data = resp.json()
    file_id = resp_data.get("id")
    if not file_id:
        raise RuntimeError(f"응답에서 file_id를 찾을 수 없습니다: {resp_data}")

    print(f"[+] 파일 업로드 성공 -> File ID: {file_id}")
    return file_id

def start_agent_run(file_id: str) -> str:
    """
    file_id로 Upstage Studio Agent 실행 작업을 생성합니다.
    """
    url = f"{BASE_URL_V2}/responses"
    payload = {
        "model": AGENT_ID,
        "include": ["last"],
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_file",
                        "file_id": file_id
                    }
                ]
            }
        ],
        "config_id": CONFIG_ID
    }

    print(f"[*] Agent 실행 요청 (Agent ID: {AGENT_ID}, Config ID: {CONFIG_ID})...")
    resp = requests.post(url, headers=HEADERS, json=payload, timeout=120)
    print("start status:", resp.status_code)
    
    if resp.status_code != 200:
        print("start body:", resp.text)
        resp.raise_for_status()

    data = resp.json()
    run_id = data.get("id") or data.get("run_id")
    if not run_id:
        raise RuntimeError(f"응답에서 run_id를 찾을 수 없습니다: {data}")
    return run_id

def get_run(run_id: str) -> Dict[str, Any]:
    """
    실행 상태/결과 조회
    """
    url = f"{BASE_URL_V2}/responses/{run_id}?include=last"
    resp = requests.get(url, headers={"Authorization": f"Bearer {API_KEY}"}, timeout=120)
    resp.raise_for_status()
    return resp.json()

def wait_for_run(run_id: str, interval: int = 3, timeout_sec: int = 600) -> Dict[str, Any]:
    """
    완료될 때까지 polling
    """
    start = time.time()
    print(f"[*] 실행 완료 대기 중 (Run ID: {run_id})...")

    while True:
        data = get_run(run_id)
        status = data.get("status")
        elapsed = int(time.time() - start)
        print(f"[{elapsed:3d}s] run status: {status}")

        if status in ("completed", "failed", "canceled"):
            return data

        if time.time() - start > timeout_sec:
            raise TimeoutError(f"run did not finish within {timeout_sec} seconds")

        time.sleep(interval)

def extract_agent_output(run_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    응답 구조에서 에이전트 추출 결과 JSON을 유연하게 탐색하여 파싱합니다.
    """
    # 1. output_text 필드가 문자열 JSON인 경우 우선 확인
    output_text = run_result.get("output_text")
    if output_text and isinstance(output_text, str):
        try:
            parsed = json.loads(output_text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    # 2. candidates 확인
    candidates = [
        run_result.get("outputs"),
        run_result.get("result"),
        run_result.get("data"),
    ]

    for c in candidates:
        if isinstance(c, dict):
            if "cuda_optimization_research_log" in c:
                value = c["cuda_optimization_research_log"]
                if isinstance(value, dict):
                    return value
            if "optimization_methods" in c or "document_title" in c or "methods_and_results" in c:
                return c

    # 3. output 리스트 내 메시지 탐색
    outputs_list = run_result.get("output")
    if isinstance(outputs_list, list):
        for item in reversed(outputs_list):
            if not isinstance(item, dict):
                continue

            # (A) content 필드가 리스트인 경우 ([{'type': 'output_text', 'text': '...'}])
            content_val = item.get("content")
            if isinstance(content_val, list):
                for part in content_val:
                    if isinstance(part, dict) and "text" in part:
                        text_str = part["text"]
                        if isinstance(text_str, str):
                            try:
                                parsed = json.loads(text_str)
                                if isinstance(parsed, dict):
                                    return parsed
                            except json.JSONDecodeError:
                                pass

            # (B) content_parsed, raw_content, content, additional_values 확인
            for content_key in ("content_parsed", "raw_content", "content", "additional_values"):
                val = item.get(content_key)
                if isinstance(val, dict):
                    if "optimization_methods" in val or "document_title" in val or "methods_and_results" in val:
                        return val
                if isinstance(val, str):
                    try:
                        parsed_val = json.loads(val)
                        if isinstance(parsed_val, dict):
                            if "optimization_methods" in parsed_val or "document_title" in parsed_val or "methods_and_results" in parsed_val:
                                return parsed_val
                    except json.JSONDecodeError:
                        pass

    # 4. step 결과 안쪽에 들어있는 경우 탐색
    steps = run_result.get("steps") or run_result.get("node_results") or []
    if isinstance(steps, list):
        for step in steps:
            if not isinstance(step, dict):
                continue
            for key in ("output", "result", "data"):
                v = step.get(key)
                if isinstance(v, dict):
                    if "cuda_optimization_research_log" in v and isinstance(v["cuda_optimization_research_log"], dict):
                        return v["cuda_optimization_research_log"]
                    if "optimization_methods" in v or "document_title" in v or "methods_and_results" in v:
                        return v

    raise RuntimeError(f"could not find extract output in response: {run_result}")

def print_summary(extract_result: Dict[str, Any]) -> None:
    print("\n" + "=" * 60)
    print("=== DOCUMENT LEVEL ===")
    print("document_title:", extract_result.get("document_title", ""))
    print("experiment_date:", extract_result.get("experiment_date", ""))
    print("project_name:", extract_result.get("project_name", ""))
    print("overall_result_summary:", extract_result.get("overall_result_summary", ""))

    # optimization_methods 또는 methods_and_results 지원
    methods: List[Dict[str, Any]] = extract_result.get("optimization_methods") or extract_result.get("methods_and_results") or []

    print(f"\n=== OPTIMIZATION METHODS ({len(methods)}) ===")
    print("=" * 60)
    for i, m in enumerate(methods, start=1):
        print(f"\n[{i}]")
        print("method_name:", m.get("method_name", ""))
        if "method_category" in m:
            print("method_category:", m.get("method_category", ""))
        if "target_component" in m:
            print("target_component:", m.get("target_component", ""))
        if "baseline_issue" in m:
            print("baseline_issue:", m.get("baseline_issue", ""))
        if "change_applied" in m:
            print("change_applied:", m.get("change_applied", ""))
        if "expected_effect" in m:
            print("expected_effect:", m.get("expected_effect", ""))
        if "measured_effect" in m:
            print("measured_effect:", m.get("measured_effect", ""))
        if "metric_name" in m:
            print("metric_name:", m.get("metric_name", ""))
        if "metric_before" in m:
            print("metric_before:", m.get("metric_before", ""))
        if "metric_after" in m:
            print("metric_after:", m.get("metric_after", ""))
        if "result" in m:
            print("result:", m.get("result", ""))
        if "description" in m:
            print("description:", m.get("description", ""))
        if "file_version" in m:
            print("file_version:", m.get("file_version", ""))
        if "evidence_section" in m:
            print("evidence_section:", m.get("evidence_section", ""))
        if "evidence_text" in m:
            print("evidence_text:", m.get("evidence_text", ""))

def run_cuda_optimization_agent(file_path_or_id: str | Path) -> Dict[str, Any]:
    """
    로컬 파일 경로 또는 이미 업로드된 file_id를 받아 에이전트를 실행하고 결과를 반환합니다.
    """
    target = str(file_path_or_id).strip()

    # 이미 업로드된 file_id(file_...)인지, 아니면 파일 경로인지 판별
    if target.startswith("file_") and not Path(target).exists():
        file_id = target
        print(f"[*] 기존 File ID 사용: {file_id}")
    else:
        file_id = upload_file(target)

    run_id = start_agent_run(file_id)
    print("run_id:", run_id)

    run_result = wait_for_run(run_id)

    if run_result.get("status") != "completed":
        raise RuntimeError(f"agent run failed: {run_result}")

    extract_result = extract_agent_output(run_result)

    # 추출 결과 JSON 파일로 저장
    output_json_path = Path(__file__).resolve().parent / "Results & Discussion.json"
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(extract_result, f, ensure_ascii=False, indent=2)
    print(f"[+] 추출 결과가 저장되었습니다: {output_json_path}")

    return extract_result

if __name__ == "__main__":
    # 1. 커맨드라인 인자가 있으면 해당 파일 경로 사용
    if len(sys.argv) > 1:
        target_path = sys.argv[1]
    else:
        # 2. 기본 PDF 경로 탐색 (상위 디렉터리 또는 절대 경로)
        base_dir = Path(__file__).resolve().parent.parent
        default_file = base_dir / "GPU 프로그래밍의 핵심_ CUDA로 배우는 병렬 처리 기술.pdf"
        if default_file.exists():
            target_path = str(default_file)
        else:
            target_path = r"C:\Users\user\Desktop\LLMops\GPU 프로그래밍의 핵심_ CUDA로 배우는 병렬 처리 기술.pdf"

    print(f"[*] 대상 파일: {target_path}")
    result = run_cuda_optimization_agent(target_path)
    print_summary(result)