"""로컬 원문 기준표와 같은 PDF를 지정한 Studio Agent/Config로 실행한다.

실제 외부 API 호출 명령이다. 응답과 재개 상태는 기본적으로 ignored draft_history에 보관한다.
목차 채점과 JSON 내용 검증은 별도 평가 도구에서 수행한다.
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE))
import config
from golden_evaluation import verify_source

API = "https://api.upstage.ai/v2"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=BASE/"evaluation/golden/rgbd-reference.json")
    parser.add_argument("--pdf", type=Path, help="생략하면 프로젝트 상위 폴더의 기준표 source_file")
    parser.add_argument("--agent-id", default=config.STRUCTURE_AGENT_ID)
    parser.add_argument("--config-id", default="4", help="최신 자동 선택 대신 명시할 Studio Config ID")
    parser.add_argument("--run-dir", type=Path, default=BASE/"draft_history/studio-rgbd-config4")
    args = parser.parse_args(argv)
    if not config.UPSTAGE_API_KEY or not args.agent_id:
        raise ValueError(".env의 UPSTAGE_API_KEY 및 STRUCTURE_AGENT_ID 또는 --agent-id가 필요합니다.")
    reference = json.loads(args.reference.read_text(encoding="utf-8"))
    pdf = args.pdf or BASE.parent/reference["source_file"]
    digest = verify_source(reference, pdf)
    args.run_dir.mkdir(parents=True, exist_ok=True)
    headers = {"Authorization": f"Bearer {config.UPSTAGE_API_KEY}"}

    def save(name, value):
        (args.run_dir/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")

    def checked(response, filename):
        try:
            body = response.json()
        except ValueError:
            body = {"non_json_response": True, "http_status": response.status_code}
        save(filename, body)
        if response.status_code not in (200, 201, 202):
            raise RuntimeError(f"Studio API 요청 실패: HTTP {response.status_code}. 상세 응답은 로컬에 저장했습니다.")
        return body

    state_path = args.run_dir/"state.json"
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if (state.get("source_sha256"), state.get("agent_id"), state.get("requested_config_id")) != (
                digest, args.agent_id, args.config_id):
            raise ValueError("저장된 실행의 원문·Agent·Config가 다릅니다. 새로운 --run-dir를 사용하세요.")
    else:
        state = {"started_at_utc": datetime.now(timezone.utc).isoformat(),
                 "source_file": reference["source_file"], "source_sha256": digest,
                 "agent_id": args.agent_id, "requested_config_id": args.config_id}
        save("state.json", state)

    if not state.get("file_id"):
        print(f"Uploading {pdf.name} to Upstage Files API", flush=True)
        with pdf.open("rb") as source:
            uploaded = checked(requests.post(API+"/files", headers=headers, files={"file": source},
                                            data={"purpose": "user_data"}, timeout=120), "file-response.json")
        state["file_id"] = uploaded["id"]
        save("state.json", state)
    if not state.get("job_id"):
        payload = {"model": args.agent_id, "config_id": args.config_id, "include": ["all"],
                   "input": [{"role": "user", "content": [{"type": "input_file", "file_id": state["file_id"]}]}]}
        save("submitted-request.json", payload)
        print(f"Running Studio Agent with explicit Config {args.config_id}", flush=True)
        created = checked(requests.post(API+"/responses", headers=headers, json=payload, timeout=120), "create-response.json")
        state["job_id"] = created["id"]
        save("state.json", state)

    start, last_print, last_status = time.monotonic(), -30, None
    while True:
        result = checked(requests.get(API+"/responses/"+state["job_id"], headers=headers,
                                     params={"include": "all"}, timeout=120), "job-response.json")
        status = result.get("status")
        elapsed = time.monotonic()-start
        if status != last_status or elapsed-last_print >= 30:
            print(f"Studio status: {status}; polling {elapsed:.0f}s", flush=True)
            last_status, last_print = status, elapsed
        if status in {"completed", "failed", "canceled", "cancelled", "incomplete"}:
            break
        if elapsed > 600:
            raise TimeoutError("작업이 아직 실행 중입니다. 같은 명령으로 재개하면 저장된 Job을 조회합니다.")
        time.sleep(5)

    labels = {"Instruct - paper_structure_profile": "structure.md",
              "Instruct - paper_style_checklist": "style.md",
              "Instruct - paper_evidence_review": "review.md"}
    outputs = result.get("output", [])
    for index, step in enumerate(outputs, 1):
        raw = "\n".join(item["text"] for item in step.get("content", []) if isinstance(item.get("text"), str))
        (args.run_dir/f"step-{index:02d}-output.txt").write_text(raw, encoding="utf-8")
        if step.get("model") in labels:
            try:
                decoded = json.loads(raw)
            except ValueError:
                decoded = raw
            text = decoded if isinstance(decoded, str) else json.dumps(decoded, ensure_ascii=False, indent=2)
            (args.run_dir/labels[step["model"]]).write_text(text, encoding="utf-8")
    summary = {"status": status, "requested_config_id": args.config_id,
               "stages": [{"name": step.get("model"), "status": step.get("status")} for step in outputs],
               "polling_seconds": round(elapsed, 3), "usage": result.get("usage"),
               "returned_config_id": result.get("config_id"),
               "content_evaluation": "not performed by this runner; use saved outputs and source reference"}
    save("completion.json", summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    if status != "completed":
        code = (result.get("error") or {}).get("code", "unknown")
        raise RuntimeError(f"Studio 작업이 {status}로 종료됐습니다. error={code}. 빈 응답을 정상 결과로 평가하지 마세요.")


if __name__ == "__main__":
    main()
