"""Validate and export the two development runs without making network requests."""

import hashlib
import json
import platform
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE))
import requests
from document_parse import artifact_directory, parse_document, write_json
from paper_outline import element_key, element_text
from planned_paper import PlannedPaper
from structure_profiles import load_profiles


def main():
    destination = BASE / "evaluation/planning/examples"
    destination.mkdir(parents=True, exist_ok=True)
    records = []
    normalize = lambda text: "".join(char for char in text.casefold() if char.isalnum())
    with patch.object(requests, "post", side_effect=AssertionError("Network disabled during validation")):
        for name in ("npu", "rgbd"):
            folder = BASE / f"draft_history/planned-validation/{name}-indexed"
            research = json.loads((folder / "research.json").read_text(encoding="utf-8"))
            reference = {"profiles": load_profiles(BASE / f"draft_history/planned-validation/{name}-reference.json")}
            engine = PlannedPaper(client=lambda *args: (_ for _ in ()).throw(AssertionError("Unexpected model call")))
            # Keep the original relative output path used by the CLI metrics, while fingerprints bind the data.
            result = engine.run(research, reference, output_dir=Path(f"draft_history/planned-validation/{name}-indexed"))
            pdf = BASE / "golden sample" / research["source"]["file"]
            digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
            assert digest == research["source"]["sha256"]
            parsed = parse_document(pdf, artifact_directory(pdf, BASE / "draft_history/parse-api-v1"))
            elements = {element_key(element): element for element in parsed["elements"]}
            quote_count = 0
            for fact in research["facts"]:
                for source in fact["sources"]:
                    element = elements[source["element_id"]]
                    assert source["page"] == element["page"]
                    assert normalize(source["quote"]) in normalize(element_text(element))
                    quote_count += 1
            plan, metrics = result["plan"], result["metrics"]
            for filename in ("plan.json", "draft.md", "review.json", "metrics.json"):
                shutil.copy2(folder / filename, destination / f"{name}-{filename}")
            records.append({"case": name, "source_file": research["source"]["file"], "source_sha256": digest,
                "reference_file": Path(reference["profiles"][0]["file"]).name,
                "facts": len(research["facts"]), "source_quote_links_checked": quote_count,
                "title": plan["title"], "sections": [{"id": s["id"], "title": s["title"], "role": s["role"],
                    "subsections": s["subsections"], "reference_ids": s["reference_ids"],
                    "reference_adaptation": s["reference_adaptation"]} for s in plan["sections"]],
                "metrics": metrics, "critical_review_errors": sum(i["severity"] == "error" for i in result["review"]["issues"]),
                "review_rounds": len(result["review_history"]), "offline_replay": "passed",
                "draft_sha256": hashlib.sha256((folder / "draft.md").read_bytes()).hexdigest()})
    metadata = {"python_version": platform.python_version(), "cases": records,
                "independent_quality_evaluation": False, "development_samples": True,
                "first_attempt_success_rate_measured": False,
                "code_sha256": {name: hashlib.sha256((BASE / name).read_bytes()).hexdigest()
                                for name in ("paper_plan.py", "planned_paper.py")}}
    write_json(BASE / "evaluation/planning/validation.json", metadata)
    lines = ["# 연구별 작성 계획·초안 실행 검증", "",
             "같은 generic 프로젝트 설정과 같은 코드에 서로 다른 연구 PDF를 입력했다. 기존 CUDA 고정 작성기와 저장 초안은 변경하지 않았다.",
             "입력 연구와 다른 논문의 가이드만 교차 연결했다. 원문 Parse 캐시를 재사용했고, 현재 코드로 네트워크를 금지한 전체 재생도 통과했다.", "",
             "| 연구 입력 | 참고 가이드 | 근거 수 | 생성 장 수 | 필수 내용 충족 (LLM 보조) | 참고 적용 (LLM 보조) | 로컬 검증 |",
             "|---|---|---:|---:|---:|---|---|"]
    for record in records:
        coverage = record["metrics"]["required_content_coverage"]
        application = record["metrics"]["reference_application"]
        lines.append(f"| {record['case'].upper()} | {'RGBD' if record['case']=='npu' else 'NPU'} | {record['facts']} | {len(record['sections'])} | {coverage['met']}/{coverage['total']} | 적용 {application['applied']}, 부분 {application['partial']}, 미확인 {application['not_visible']} | 통과 |")
    for record in records:
        name = record["case"]
        lines += ["", f"## {name.upper()} 계획", "", f"제목: {record['title']}", "",
                  f"[계획 JSON](examples/{name}-plan.json) · [생성 초안](examples/{name}-draft.md) · [검토 기록](examples/{name}-review.json)", "",
                  "| 장 | 역할 | 소절 수 | 참고 구성 적용 계획 |", "|---|---|---:|---|"]
        lines += [f"| {s['title']} | {s['role']} | {len(s['subsections'])} | {s['reference_adaptation']} |" for s in record["sections"]]
    lines += ["", "## 결과의 의미와 한계", "",
              "- 일반 연구 입력은 optimization_methods 목록이나 CUDA/CROWN 전용 장 제목을 요구하지 않는다. 장 수·소절·필수 내용·근거·참고 적용 방식이 계획으로 전달된다.",
              "- 완료까지 출력 스키마·근거 연결·검토 프로토콜을 개선하고 제한된 수정/재시도를 수행했다. 첫 시도 성공률·처리 속도·비용의 통제 실험이 아니다.",
              "- source_quote_links_checked는 인용 문자열이 실제 원문 요소와 페이지에 존재한다는 검사다. 추출 주장의 의미·수치 해석·인과의 정확성 점수가 아니다.",
              "- 필수 내용과 참고 적용 수치는 LLM 보조 판정이다. 문단 ID의 존재를 코드로 확인하지만 그 문단이 항목을 충분히 설명하는지는 별도 사람 검수가 필요하다.",
              "- 새 과학적 성과를 만든 것이 아니라 이미 제공된 두 논문을 연구 입력으로 재구성한 개발 실행 검증이다. 독립 보류 평가셋의 일반화 성능이 아니다.",
              "- 원본 행·열이 제공되지 않은 표는 모델이 만들어 배치할 수 없다. PDF 표의 자동 행·열 구조화는 추가 구현 대상이며 수작업 표로 대체하지 않는다.",
              "- CUDA 수작업 근거는 과거 기록으로 보존하며 현재 실행 경로에서 로드하지 않는다. CUDA 프로젝트도 input/ 원본 PDF에서 자동 추출한다.", "",
              "## 재생 검증", "", "```powershell", "python -X utf8 -B evaluation/planning/summarize_runs.py", "```", "",
              "ignored 실행 폴더가 필요하다. 다른 PC에서 실제 모델을 다시 실행하려면 새 출력 폴더를 지정한다. 원문 PDF와 API 설정은 별도로 준비한다.", ""]
    (BASE / "evaluation/planning/validation.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"offline_replay": "passed", "cases": [{"case": r["case"], "sections": len(r["sections"]),
                     "facts": r["facts"], "critical_errors": r["critical_review_errors"]} for r in records]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
