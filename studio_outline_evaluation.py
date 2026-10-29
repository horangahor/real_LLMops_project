"""Studio의 서술형 구조 분석에서 명시된 번호 목차만 평가용으로 읽는다.

Studio 응답을 수정하거나 별도 LLM을 호출하지 않는다. 역할과 페이지는 추론하지 않는다.
"""

import argparse
import hashlib
import json
import re
from pathlib import Path

from golden_evaluation import EVALUATION_VERSION, evaluate_outline, fraction, percent, ratio, verify_source

BASE = Path(__file__).resolve().parent


def extract_numbered_outline(markdown):
    match = re.search(r"(?m)^##\s+섹션 계층 및 순서\s*$", markdown)
    if not match:
        raise ValueError("Studio 응답에 '섹션 계층 및 순서' 분석 구간이 없습니다.")
    block = markdown[match.end():]
    next_heading = re.search(r"(?m)^##\s+", block)
    if next_heading:
        block = block[:next_heading.start()]
    block = re.sub(r"【†\d+】", "", block)
    titles = []
    for span in re.findall(r"\*\*(.+?)\*\*", block, re.S):
        for fragment in re.split(r"\s*(?:→|,)\s*", span):
            fragment = " ".join(fragment.split())
            parsed = re.fullmatch(r"(\d+(?:\.\d+)*)\s+(.+)", fragment)
            if parsed:
                titles.append((parsed.group(1), fragment))
    if not titles:
        raise ValueError("Studio 분석 구간에 명시적인 번호·제목 목록이 없습니다.")
    roots, by_number, orphans = [], {}, []
    for number, title in titles:
        node = {"title": title, "role": "other", "source_pages": None, "children": []}
        parent_number = number.rpartition(".")[0] or None
        if parent_number and parent_number in by_number:
            by_number[parent_number]["children"].append(node)
        else:
            roots.append(node)
            if parent_number:
                orphans.append({"title": title, "missing_parent_number": parent_number})
        # Retain duplicate predictions for scoring; children use the first declared parent.
        by_number.setdefault(number, node)
    return {"observed_outline": roots, "adapter": "explicit-numbered-markdown-v1",
            "role_placeholder": "other is a technical placeholder, not a Studio role classification",
            "parent_policy": "Parent links reconstructed only from numbers explicitly in Studio output",
            "unresolved_parents": orphans}


def evaluate_studio_markdown(markdown, reference):
    derived = extract_numbered_outline(markdown)
    report = evaluate_outline(derived, reference)
    # The Markdown output never supplies machine-readable role/page labels.
    # Report these as unassessed, rather than scoring our own invented labels.
    for name in ("role_accuracy_on_matched", "fully_correct_item_recall", "page_accuracy_on_matched"):
        report["metrics"][name] = fraction(0, 0)
    for row in report["matches"]:
        row.update(predicted_role=None, role_correct=None, fully_correct=None, page_correct=None)
    report["native_structured_outline"] = False
    report["role_and_page_assessment"] = "not provided as structured labels; not inferred"
    report["parent_assessment"] = derived["parent_policy"]
    report["adapter"] = derived["adapter"]
    return derived, report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--structure", type=Path, required=True, help="Studio 구조 분석 단계의 원본 Markdown")
    parser.add_argument("--reference", type=Path, default=BASE/"evaluation/golden/npu-reference.json")
    parser.add_argument("--output", type=Path, default=BASE/"evaluation/golden/results/npu-studio.json")
    args = parser.parse_args(argv)
    if args.output.suffix != ".json":
        raise ValueError("평가 출력은 .json이어야 합니다.")
    reference_bytes = args.reference.read_bytes()
    reference = json.loads(reference_bytes)
    source_hash = verify_source(reference, BASE.parent/reference["source_file"])
    markdown = args.structure.read_text(encoding="utf-8")
    derived, report = evaluate_studio_markdown(markdown, reference)
    report.update(evaluation_version=EVALUATION_VERSION, source_file=reference["source_file"],
                  source_sha256=source_hash, reference_sha256=hashlib.sha256(reference_bytes).hexdigest(),
                  prediction_path=args.structure.as_posix(),
                  prediction_sha256=hashlib.sha256(args.structure.read_bytes()).hexdigest(),
                  prediction_provenance="studio_agent_markdown", reference_items=reference["items"],
                  annotation_provenance=reference["annotation_provenance"], scope=reference["scope"])
    derived_path = args.output.with_name(args.output.stem+"-derived-outline.json")
    protected = {args.structure.resolve(), args.reference.resolve(), (BASE/"paper_structure_analysis.json").resolve()}
    if any(path.resolve() in protected for path in (args.output, args.output.with_suffix(".md"), derived_path)):
        raise ValueError("평가 출력으로 원본 입력을 덮어쓸 수 없습니다.")
    metrics = report["metrics"]
    heading = metrics["heading_number_and_identity"]
    lines = ["# Studio 골든 샘플 구조 평가", "",
             f"원본: `{reference['source_file']}`", "",
             "Studio 구조 분석 단계의 Markdown에서 ‘섹션 계층 및 순서’ 구간에 명시된 번호·제목만 코드로 추출했다. 원문 기준표를 이용해 누락 제목을 채우거나 별도 LLM으로 재분석하지 않았다.",
             "서술형 응답에 역할·페이지 필드가 없으므로 해당 지표는 N/A다. 계층은 응답에 실제 적힌 절 번호로 복원했으며 Studio가 계층 JSON을 직접 반환했다는 뜻이 아니다.", "",
             "| 지표 | 결과 |", "|---|---:|",
             f"| 명시적인 제목+번호 정밀도 | {ratio(heading['precision'])} |",
             f"| 명시적인 제목+번호 재현율 | {ratio(heading['recall'])} |",
             f"| 명시적인 제목+번호 F1 | {percent(heading['f1'])} |",
             f"| 명시 번호로 복원한 계층 정확도 | {ratio(metrics['parent_accuracy_on_matched'])} |",
             f"| 번호가 맞는 하위 절 재현율 | {ratio(metrics['exact_subsection_recall'])} |",
             "| 구조화된 역할·페이지 라벨 정확도 | N/A (필드 미제공) |", "",
             "## 상세", "", "| 원문 번호·제목 | 명시적인 출력 |", "|---|---|"]
    rows = {row["reference_id"]: row for row in report["matches"]}
    for item in reference["items"]:
        value = rows[item["id"]]["prediction_title"] if item["id"] in rows else "번호·실제 제목 미제공"
        lines.append(f"| {item['id']} {item['title']} | {value} |")
    lines.extend(["", "## 해석", "",
                  "번호·제목 목록에 없는 절도 서술형 본문에서 간접적으로 설명될 수 있다. 이 평가는 명시된 번호 목차의 완전성을 측정하며, 응답 전체의 의미적 이해를 측정하지 않는다.",
                  "관찰 목차 JSON과 일반 글쓰기 분석은 서로 다른 출력 계약이다. 이 결과는 현재 서비스의 schema_version 2 프로파일을 직접 대체할 수 없다.",
                  "한 문서·한 번의 Studio 실행이며 기준표는 Codex가 원문 대조로 작성한 초기 자료로 독립 검수 전이다. 이전 직접 API 실행과 워크플로우·출력 형식이 달라 같은 모델의 설정 변경 효과를 분리한 실험은 아니다.", "",
                  "## 재현", "", "```powershell",
                  f".\\.venv\\Scripts\\python.exe -X utf8 -B studio_outline_evaluation.py --structure {args.structure.as_posix()} --output evaluation/golden/results/npu-studio-recheck.json",
                  "```", ""])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    derived_path.write_text(json.dumps(derived, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    args.output.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"reference_items": report["reference_count"], "explicit_titles": report["prediction_count"],
                      "title_number_f1": heading["f1"], "report": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
