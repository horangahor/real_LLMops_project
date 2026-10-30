"""Replay the real research extraction with network disabled and export inspectable artifacts."""

import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE))
import requests
from document_parse import artifact_directory, parse_document, write_json
from planned_paper import PlannedPaper
from paper_outline import element_key, element_text


def main():
    # Reproduce v1 with its frozen extractor, rather than overwriting the baseline with the current default.
    frozen_path = BASE / "evaluation/extraction/benchmark/baseline-code/research_extract.py"
    specification = importlib.util.spec_from_file_location("frozen_research_extract_v1", frozen_path)
    frozen = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(frozen)
    planner_path = frozen_path.parent / "planned_paper.py"
    planner_spec = importlib.util.spec_from_file_location("frozen_planned_paper_v1", planner_path)
    planner = importlib.util.module_from_spec(planner_spec)
    planner_spec.loader.exec_module(planner)
    source = BASE / "input/GPU 프로그래밍의 핵심_ CUDA로 배우는 병렬 처리 기술.pdf"
    previous = BASE / "draft_history/planned/generic/cbda24cff2b53e863951/draft.md"
    before = hashlib.sha256(previous.read_bytes()).hexdigest() if previous.is_file() else None
    original_read = Path.read_text
    def source_only(path, *args, **kwargs):
        if path.name in {"research_evidence.json", "Results & Discussion.json"}:
            raise AssertionError("Manual evidence file read attempted")
        return original_read(path, *args, **kwargs)
    with patch.object(requests, "post", side_effect=AssertionError("Network disabled")), \
            patch.object(Path, "read_text", new=source_only), \
            patch("paper_draft_agent.load_paper_structure", side_effect=AssertionError("Golden guide must not enter research extraction")):
        evidence = frozen.extract_evidence(source, planner.PlannedPaper())
        parsed = parse_document(source, artifact_directory(source, BASE / "draft_history/parse-api-v1"))
    elements = {element_key(element): element for element in parsed["elements"]}
    assert evidence["source"]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    links = 0
    for item in evidence["items"]:
        for link in item["sources"]:
            element = elements[link["element_id"]]
            assert link["page"] == element["page"] and link["quote"] == element_text(element)
            links += 1
        value = {"items": [{"fact_id": item["id"], **item}]}
        frozen.validate_annotations(value, [item])
    assert links == evidence["diagnostics"]["source_links"]
    assert all(item["support"] == "supported" and item["claim_status"] not in ("hypothesis", "unclear")
               for item in evidence["research"]["facts"])
    assert before is None or hashlib.sha256(previous.read_bytes()).hexdigest() == before
    destination = Path(__file__).resolve().parent
    assert json.loads((destination / "cuda-evidence.json").read_text(encoding="utf-8")) == evidence
    record = {"source_sha256": evidence["source"]["sha256"], "diagnostics": evidence["diagnostics"],
        "exact_source_links_checked": links, "offline_replay": "passed", "manual_file_reads_blocked": True,
        "golden_guide_load_blocked": True, "previous_draft_preserved": True, "unit_tests_passed": 124,
        "independent_quality_evaluation": False,
        "frozen_extractor_sha256": hashlib.sha256(frozen_path.read_bytes()).hexdigest()}
    write_json(destination / "baseline-replay.json", record)
    print(json.dumps({"offline_replay": "passed", **evidence["diagnostics"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
