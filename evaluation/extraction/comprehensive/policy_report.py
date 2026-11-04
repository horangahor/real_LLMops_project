"""Apply the comprehensive policy to a saved extraction without any model call and report the effect.

Usage (repository root):
  python -X utf8 -B evaluation/extraction/comprehensive/policy_report.py \
      [--zip evaluation/extraction/v3/portable-20261102/research-state.zip] [--output DIR]

Reads the latest v3 evidence.json and its source-archive.json directly from the portable ZIP,
so nothing is restored or overwritten.
"""

import argparse
import collections
import copy
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from comprehensive_policy import apply_comprehensive_policy  # noqa: E402
from research_extract_v3 import _refresh_research_from_review  # noqa: E402

DEFAULT_ZIP = ROOT / "evaluation/extraction/v3/portable-20261102/research-state.zip"
REFERENCE = ROOT / "evaluation/extraction/benchmark/reference.json"


def load_from_zip(path):
    archive = zipfile.ZipFile(path)
    names = archive.namelist()
    evidence_names = sorted(n for n in names if "/research-evidence-v3/" in n and n.endswith("/evidence.json")
                            and n.count("/research-evidence-v3/") == 1 and n.split("/research-evidence-v3/")[1].count("/") == 1)
    if not evidence_names:
        raise SystemExit("ZIP에 v3 evidence.json이 없습니다.")
    evidence_name = evidence_names[-1]
    folder = evidence_name.rsplit("/", 1)[0]
    extraction = json.loads(archive.read(evidence_name))
    source = json.loads(archive.read(folder + "/source-archive.json"))
    return extraction, {element["element_id"]: element for element in source["elements"]}, evidence_name


def reference_proxy(extraction, elements):
    """Lexical proxy only: a numeric reference counts as kept when all its numbers appear in writing facts nearby."""
    from research_values import missing_numbers, numeric_atoms
    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))
    writing_ids = set(extraction["writing_fact_ids"])
    writing = [fact for fact in extraction["items"] if fact["id"] in writing_ids]
    fields = ("statement", "limits", "conditions", "observations", "parameters", "measurements")
    rows = []
    for ref in reference["facts"]:
        nearby = [fact for fact in writing if any(abs(source["page"] - ref["page"]) <= 1 for source in fact["sources"])]
        text = "\n".join(json.dumps({k: f.get(k) for k in fields}, ensure_ascii=False) for f in nearby)
        atoms, _ = numeric_atoms(ref["source_evidence"])
        if not atoms:
            rows.append({"id": ref["id"], "page": ref["page"], "status": "manual_check"})
            continue
        missing = missing_numbers(ref["source_evidence"], text)
        rows.append({"id": ref["id"], "page": ref["page"], "status": "kept" if not missing else "missing_numbers",
                     "missing": missing})
    return {"note": "21쪽 표본 참조 42개의 숫자 보존 대리 지표. 의미 판정이 아니다.",
            "counts": dict(collections.Counter(row["status"] for row in rows)), "rows": rows}


def summarize(extraction):
    completion = extraction["completion"]
    gate = completion.get("gate", {})
    return {"items": len(extraction["items"]), "writing_facts": len(extraction["writing_fact_ids"]),
            "unresolved_source_items": len(completion.get("unresolved_source_items", [])),
            "ready_for_drafting": completion.get("ready_for_drafting"),
            "blocking": dict(collections.Counter(row["category"] for row in gate.get("blocking", []))),
            "warnings": dict(collections.Counter(row["category"] for row in gate.get("warnings", [])))}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", type=Path, default=DEFAULT_ZIP)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "results")
    args = parser.parse_args()
    original, elements, name = load_from_zip(args.zip)
    before = summarize(original)
    before["reference_proxy"] = reference_proxy(original, elements)["counts"]
    extraction = copy.deepcopy(original)
    apply_comprehensive_policy(extraction, elements, refresh=_refresh_research_from_review)
    after = summarize(extraction)
    proxy = reference_proxy(extraction, elements)
    after["reference_proxy"] = proxy["counts"]
    report = {"source_zip": str(args.zip.relative_to(ROOT)) if args.zip.is_relative_to(ROOT) else str(args.zip),
              "evidence": name.split("draft_history/")[-1], "before": before, "after": after,
              "numeric_flags": extraction["comprehensive_policy"]["numeric_flags"],
              "blocking_items": extraction["completion"]["blocking_source_items"],
              "warning_items": [row for row in extraction["completion"]["gate"]["warnings"]
                                if row["category"] != "quarantined_fact"],
              "reference_proxy": proxy}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "policy-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"before": before, "after": after, "numeric_flags": len(report["numeric_flags"])},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
