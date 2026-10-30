"""Replay the current production gateway with all network/manual evidence/reference reads blocked."""

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

import requests
from document_parse import write_json
from paper_draft_agent import PaperDraftOrchestrator
from planned_paper import PlannedPaper
from research_extract_v2 import writing_eligible
from research_values import normalize_measurement


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    # The default has advanced to v3. Replay the frozen v2 extractor through the gateway explicitly.
    specification = importlib.util.spec_from_file_location("frozen_research_extract_v2", HERE / "code/research_extract_v2.py")
    frozen = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(frozen)
    def extract_v2(engine, source):
        engine.last_extraction = frozen.extract_evidence(source, engine)
        return engine.last_extraction
    source = BASE / "input/GPU 프로그래밍의 핵심_ CUDA로 배우는 병렬 처리 기술.pdf"
    previous = BASE / "draft_history/planned/generic/cbda24cff2b53e863951/draft.md"
    baseline = HERE.parent / "cuda-evidence.json"
    preserved = {path: digest(path) for path in (previous, baseline)}
    read = Path.read_text

    def source_only(path, *args, **kwargs):
        resolved = path.resolve()
        if path.name in {"research_evidence.json", "Results & Discussion.json"} or (BASE / "evaluation") in resolved.parents:
            raise AssertionError("Manual or evaluation evidence entered extraction")
        return read(path, *args, **kwargs)

    with patch.object(requests, "post", side_effect=AssertionError("Network disabled")), \
            patch.object(PlannedPaper, "extract_evidence", new=extract_v2), \
            patch.object(Path, "read_text", new=source_only), \
            patch("paper_draft_agent.load_paper_structure", side_effect=AssertionError("Golden guide entered extraction")):
        result = PaperDraftOrchestrator().run_pipeline(research_pdf_path=source, extract_only=True)
    evidence = result["evidence_extraction"]
    assert not result["draft_markdown"]
    assert evidence == json.loads((HERE / "evidence.json").read_text(encoding="utf-8"))
    assert evidence["source"]["sha256"] == digest(source)
    index = json.loads(Path(evidence["source_index_path"]).read_text(encoding="utf-8"))
    elements = {e["element_id"]: e for e in index["elements"]}
    links = 0
    for fact in evidence["items"]:
        for link in fact["sources"]:
            original = elements[link["element_id"]]
            assert link["page"] == original["page"] and link["quote"] == original["text"]
            links += 1
        for measurement in fact["measurements"]:
            normalize_measurement({**measurement, "value": measurement["raw_value"]},
                                  "\n".join(elements[key]["text"] for key in measurement["element_ids"]))
    assert links == evidence["diagnostics"]["source_links"]
    assert set(evidence["coverage"]) == {f"p{i}" for i in range(1, 85)}
    writing = {f["id"] for f in evidence["research"]["facts"]}
    assert writing == set(evidence["writing_fact_ids"])
    assert writing == {f["id"] for f in evidence["items"] if writing_eligible(f)}
    assert all(digest(path) == value for path, value in preserved.items())
    write_json(HERE / "validation.json", {"offline_production_replay": "passed", "exact_source_links_checked": links,
               "source_sha256": digest(source), "prediction_sha256": digest(HERE / "evidence.json"),
               "all_84_pages_accounted_for": True, "manual_and_evaluation_file_reads_blocked": True,
               "golden_guide_load_blocked": True, "network_disabled": True, "extractor_pinned_to_frozen_v2": True,
               "previous_draft_and_v1_preserved": {str(p.relative_to(BASE)): h for p, h in preserved.items()},
               "diagnostics": evidence["diagnostics"], "independent_quality_evaluation": False})
    print(json.dumps({"offline_production_replay": "passed", "source_links": links, "writing_facts": len(writing)}))


if __name__ == "__main__":
    main()
