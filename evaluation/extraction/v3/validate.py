"""Replay current extraction through the app gateway with network and manual/reference inputs blocked."""

import hashlib
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
from research_extract_v3 import writing_eligible


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    source = BASE / "input/GPU 프로그래밍의 핵심_ CUDA로 배우는 병렬 처리 기술.pdf"
    preserved_paths = [HERE.parent / "cuda-evidence.json", HERE.parent / "v2/evidence.json",
                       BASE / "draft_history/planned/generic/cbda24cff2b53e863951/draft.md"]
    preserved = {path: digest(path) for path in preserved_paths}
    read = Path.read_text
    def source_only(path, *args, **kwargs):
        p = path.resolve()
        if path.name in {"research_evidence.json", "Results & Discussion.json"} or BASE / "evaluation" in p.parents:
            raise AssertionError("Manual/evaluation input entered extraction")
        return read(path, *args, **kwargs)
    with patch.object(requests, "post", side_effect=AssertionError("Network disabled")), \
            patch.object(Path, "read_text", new=source_only), \
            patch("paper_draft_agent.load_paper_structure", side_effect=AssertionError("Golden guide entered extraction")):
        result = PaperDraftOrchestrator().run_pipeline(research_pdf_path=source, extract_only=True)
    evidence = result["evidence_extraction"]
    assert not result["draft_markdown"]
    assert evidence == json.loads((HERE / "evidence.json").read_text(encoding="utf-8"))
    archive = json.loads(Path(evidence["source_archive_path"]).read_text(encoding="utf-8"))
    elements = {e["element_id"]: e for e in archive["elements"]}
    assert evidence["source"]["sha256"] == digest(source)
    assert set(elements) == set(evidence["element_ledger"])
    facts = {f["id"]: f for f in evidence["items"]}
    assert len(facts) == len(evidence["items"])
    admitted = {f["id"] for f in facts.values() if writing_eligible(f)}
    assert admitted == set(evidence["writing_fact_ids"]) == {f["id"] for f in evidence["research"]["facts"]}
    for row in evidence["element_ledger"].values():
        assert set(row["fact_ids"]) <= admitted
        if row["state"] in ("represented", "duplicate"):
            assert row["fact_ids"]
    links = 0
    for fact in facts.values():
        for link in fact["sources"]:
            original = elements[link["element_id"]]
            assert link["page"] == original["page"] and link["quote"] == original["text"]
            links += 1
        if fact["id"] in admitted and fact["source_origin"] == "ai_advice":
            assert fact["attribution_preserved"] and fact["writing_role"] == "context_only"
    completion = evidence["completion"]
    open_rows = [key for key, row in evidence["element_ledger"].items() if row["state"] in ("unresolved", "unreadable")]
    if not completion["ready_for_drafting"]:
        assert not completion["ready_for_drafting"]
        with patch.object(PlannedPaper, "load_evidence", return_value=evidence):
            try:
                PlannedPaper().load_research({}, research_pdf="unused.pdf")
            except ValueError as error:
                assert "미해결" in str(error)
            else:
                raise AssertionError("Incomplete research entered drafting")
    assert all(digest(path) == value for path, value in preserved.items())
    write_json(HERE / "validation.json", {"offline_current_gateway_replay": "passed", "network_disabled": True,
        "manual_and_evaluation_reads_blocked": True, "golden_guide_load_blocked": True,
        "exact_source_links_checked": links, "all_source_elements_accounted_for": len(elements),
        "unresolved_element_ids": open_rows, "drafting_gate_checked": True,
        "source_sha256": digest(source), "prediction_sha256": digest(HERE / "evidence.json"),
        "previous_draft_and_predictions_preserved": {str(p.relative_to(BASE)): h for p, h in preserved.items()},
        "independent_quality_evaluation": False})
    print(json.dumps({"offline_current_gateway_replay": "passed", "source_links": links,
                      "elements": len(elements), "unresolved_elements": len(open_rows)}))


if __name__ == "__main__":
    main()
