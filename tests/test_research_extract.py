import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from document_parse import artifact_directory, write_json
from paper_draft_agent import PaperDraftOrchestrator
from paper_plan import project_profile
from planned_paper import PlannedPaper
from research_extract import extract_evidence, render_evidence, validate_annotations


def fact(key="F01", element="p2:e1", value="12.50ms"):
    return {"id": key, "statement": "실행 시간 관측", "limits": "동일 조건 여부 확인 필요",
            "sources": [{"element_id": element, "page": 2, "quote": f"실행 시간 {value}"}]}


def annotation(key="F01"):
    return {"fact_id": key, "kind": "result", "claim_status": "observed", "support": "supported",
            "support_note": "단일 관측이며 인과는 확인하지 않았다.", "conditions": ["단일 실행"],
            "measurements": [{"metric": "실행 시간", "value": "12.50", "unit": "ms",
                              "condition": "단일 실행", "element_ids": ["p2:e1"]}]}


class EvidenceExtractionTests(unittest.TestCase):
    def fixture(self, root, selected=None):
        source = root / "source.pdf"
        source.write_bytes(b"source fixture")
        facts = [fact(), fact("F02", "p2:e2")]
        summary = {"title": "독립적인 연구", "facts": facts[:1], "tables": [], "open_questions": [],
                   "source": {"file": source.name, "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}}
        folder = artifact_directory(source, root / "draft_history/parse-api-v1")
        write_json(folder / "research-candidates.json", {"facts": facts, "selection": selected or ["F01"]})
        parsed = {"elements": [{"page": 2, "id": i, "content": {"text": "실행 시간 12.50ms"}} for i in (1, 2)]}
        return source, facts, summary, parsed

    def test_all_candidates_are_visible_and_measurement_context_survives_normalization(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, facts, summary, parsed = self.fixture(root)
            second = annotation("F02")
            second["measurements"][0]["element_ids"] = ["p2:e2"]
            engine = Mock(base_dir=root)
            engine.research_from_pdf.return_value = summary
            engine.call.return_value = {"items": [annotation(), second]}
            with patch("research_extract.parse_document", return_value=parsed):
                result = extract_evidence(source, engine)
            self.assertEqual(len(result["items"]), 2)
            self.assertEqual(len(result["research"]["facts"]), 1)
            self.assertEqual(result["research"]["facts"][0]["measurements"][0]["value"], "12.50")
            self.assertEqual(result["research"]["facts"][0]["sources"], facts[0]["sources"])
            self.assertTrue((Path(result["run_dir"]) / "evidence.json").is_file())
            self.assertIn("2쪽 · p2:e1", render_evidence(result))

    def test_invented_values_and_other_facts_source_links_are_rejected(self):
        for mutate in (lambda i: i["measurements"][0].update(value="99.9"),
                       lambda i: i["measurements"][0].update(element_ids=["p2:e2"]),
                       lambda i: i["measurements"][0].update(value="12.50→8.00")):
            value = annotation()
            mutate(value)
            with self.assertRaises(ValueError):
                validate_annotations({"items": [value]}, [fact()])

    def test_duplicate_and_missing_classifications_are_rejected(self):
        for items in ([], [annotation(), annotation()]):
            with self.assertRaises(ValueError):
                validate_annotations({"items": items}, [fact()])

    def test_unconfirmed_numeric_values_are_quarantined_and_never_approved(self):
        value = annotation()
        value["measurements"][0]["value"] = "99.9"
        result = validate_annotations({"items": [value]}, [fact()], strict_measurements=False)["F01"]
        self.assertEqual(result["support"], "partial")
        self.assertEqual(result["measurements"], [])
        self.assertEqual(result["rejected_measurements"][0]["value"], "99.9")
        self.assertEqual(value["support"], "supported")

    def test_hypotheses_and_partial_support_remain_visible_but_do_not_feed_writing(self):
        for change in ({"claim_status": "hypothesis"}, {"support": "partial"}, {"support": "unsupported"}):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                source, _, summary, parsed = self.fixture(root)
                first, second = annotation(), annotation("F02")
                first.update(change)
                second["measurements"][0]["element_ids"] = ["p2:e2"]
                engine = Mock(base_dir=root)
                engine.research_from_pdf.return_value = summary
                engine.call.return_value = {"items": [first, second]}
                with patch("research_extract.parse_document", return_value=parsed):
                    result = extract_evidence(source, engine)
                self.assertIsNone(result["research"])
                self.assertEqual(result["diagnostics"]["excluded_selected_ids"], ["F01"])
                self.assertEqual(len(result["items"]), 2)

    def test_invalid_annotation_gets_one_correction_and_never_silently_changes_the_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, _, summary, parsed = self.fixture(root)
            engine = Mock(base_dir=root)
            engine.research_from_pdf.return_value = summary
            engine.call.return_value = {"items": []}
            with patch("research_extract.parse_document", return_value=parsed):
                with self.assertRaises(ValueError):
                    extract_evidence(source, engine)
            self.assertEqual(engine.call.call_count, 2)
            self.assertFalse(list(root.rglob("evidence.json")))

    def test_tampered_candidate_quote_is_rejected_before_any_annotation_request(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, _, summary, parsed = self.fixture(root)
            parsed["elements"][0]["content"]["text"] = "다른 원문"
            engine = Mock(base_dir=root)
            engine.research_from_pdf.return_value = summary
            with patch("research_extract.parse_document", return_value=parsed):
                with self.assertRaisesRegex(ValueError, "Parse 원본"):
                    extract_evidence(source, engine)
            engine.call.assert_not_called()

    def test_extract_only_gateway_does_not_load_references_or_change_the_saved_draft(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            draft = root / "paper_draft_full.md"
            draft.write_text("이전 초안", encoding="utf-8")
            gateway = PaperDraftOrchestrator("test-key")
            gateway.base_dir = root
            package = {"run_dir": str(root / "extraction"), "research": None, "items": []}
            with patch.object(PlannedPaper, "load_evidence", return_value=package), \
                    patch.object(PlannedPaper, "run", side_effect=AssertionError("writer called")), \
                    patch("paper_draft_agent.load_paper_structure", side_effect=AssertionError("reference loaded")):
                result = gateway.run_pipeline(research_pdf_path=root / "source.pdf", extract_only=True,
                                              structure_json_path=root / "missing-reference.json")
            self.assertEqual(result["evidence_extraction"], package)
            self.assertEqual(draft.read_text(encoding="utf-8"), "이전 초안")

    def test_no_usable_evidence_stops_normal_drafting(self):
        engine = PlannedPaper()
        with patch.object(engine, "load_evidence", return_value={"research": None}):
            with self.assertRaisesRegex(ValueError, "작성에 사용할"):
                engine.load_research(project_profile("generic"), research_pdf="source.pdf")


if __name__ == "__main__":
    unittest.main()
