import copy
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from requirement_applicability import assess_applicability
from requirement_extraction import extract_requirement_evidence


def bank():
    return {"version": "common-evidence-requirements-v1", "scope": "topic_independent", "requirements": [
        {"id": "method", "question": "어떤 방법을 수행했는가?", "expected_fields": ["수행 방법"], "priority": "required",
         "applicability": {"kind": "universal", "condition": "모든 연구에서 수행 방법 확인"}},
        {"id": "training", "question": "학습을 수행했다면 그 설정은 무엇인가?", "expected_fields": ["수행한 경우 학습 설정"],
         "priority": "required", "applicability": {"kind": "conditional", "condition": "연구에서 학습을 수행한 경우"}}]}


def source(root, text):
    pdf = root / "journal.pdf"
    pdf.write_bytes(text.encode("utf-8"))
    return pdf, {"run_dir": str(root / "draft_history/parse-api-v1/document/research-sources-v3"),
        "page_count": 1, "source": {"file": pdf.name, "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest()},
        "elements": [{"element_id": "p1:e1", "page": 1, "category": "paragraph", "origin": "standard_parse", "text": text}],
        "pdf_image_inventory": []}


class ApplicabilityTests(unittest.TestCase):
    def test_absence_of_a_conditional_activity_stays_uncertain_not_not_applicable(self):
        engine = Mock()
        engine.call.return_value = {"signals": []}
        with TemporaryDirectory() as tmp:
            _, original = source(Path(tmp), "방법을 구현했다.")
            result = assess_applicability(engine, Path(tmp), bank(), original)
        self.assertEqual(result["method"]["status"], "applicable")
        self.assertEqual(result["training"]["status"], "uncertain")
        self.assertEqual(engine.call.call_count, 1)

    def test_not_applicable_without_source_support_is_rejected(self):
        engine = Mock()
        engine.call.side_effect = [{"signals": [{"requirement_id": "training", "status": "not_applicable",
            "element_ids": ["p1:e1"], "reason": "학습 미수행 기록"}]},
            {"status": "not_applicable", "support_element_ids": [], "reason": "학습 없음"}]
        with TemporaryDirectory() as tmp:
            _, original = source(Path(tmp), "학습을 수행하지 않았다.")
            with self.assertRaisesRegex(ValueError, "원문 근거"):
                assess_applicability(engine, Path(tmp), bank(), original)

    def test_invented_signal_source_is_rejected_before_a_decision(self):
        engine = Mock()
        engine.call.return_value = {"signals": [{"requirement_id": "training", "status": "not_applicable",
            "element_ids": ["invented"], "reason": "미수행"}]}
        with TemporaryDirectory() as tmp:
            _, original = source(Path(tmp), "연구 기록")
            with self.assertRaises(ValueError):
                assess_applicability(engine, Path(tmp), bank(), original)
        self.assertEqual(engine.call.call_count, 1)

    def test_duplicate_signal_source_ids_are_normalized_before_validation(self):
        engine = Mock()
        engine.call.side_effect = [
            {"signals": [{"requirement_id": "training", "status": "applicable",
                "element_ids": ["p1:e1", "p1:e1"], "reason": "학습 수행 기록"}]},
            {"status": "applicable", "support_element_ids": ["p1:e1"], "reason": "적용"}]
        with TemporaryDirectory() as tmp:
            _, original = source(Path(tmp), "학습을 수행했다.")
            result = assess_applicability(engine, Path(tmp), bank(), original)
            saved = json.loads((Path(tmp) / "applicability.json").read_text(encoding="utf-8"))
        self.assertEqual(result["training"]["support_element_ids"], ["p1:e1"])
        self.assertEqual(saved["signals"]["training"][0]["element_ids"], ["p1:e1"])
        self.assertEqual(saved["normalizations"][0]["kind"], "duplicate_element_ids")

    def test_conflicting_signals_can_remain_uncertain_with_preserved_source(self):
        engine = Mock()
        engine.call.side_effect = [{"signals": [
            {"requirement_id": "training", "status": "applicable", "element_ids": ["p1:e1"], "reason": "학습 언급"},
            {"requirement_id": "training", "status": "not_applicable", "element_ids": ["p1:e1"], "reason": "미수행 언급"}]},
            {"status": "uncertain", "support_element_ids": ["p1:e1"], "reason": "상충하여 적용 여부 미확인"}]
        with TemporaryDirectory() as tmp:
            _, original = source(Path(tmp), "이전 학습 기록과 현재 미수행 기록의 대상이 불명확하다.")
            result = assess_applicability(engine, Path(tmp), bank(), original)
        self.assertEqual(result["training"]["status"], "uncertain")
        self.assertEqual(result["training"]["sources"][0]["quote"], original["elements"][0]["text"])

    def collect(self, tmp, applicability):
        root = Path(tmp)
        text = {"not_applicable": "방법을 구현했다. 학습을 수행하지 않고 추론만 수행했다.",
                "applicable": "방법을 구현했다. 학습을 수행했다.", "uncertain": "방법을 구현했다."}[applicability]
        pdf, original = source(root, text)
        engine = Mock(base_dir=root)
        seen = []
        def respond(folder, name, system, packet, schema, **kwargs):
            seen.append(name)
            if name.startswith("applicability-scan"):
                return {"signals": [] if applicability == "uncertain" else [
                    {"requirement_id": "training", "status": applicability, "element_ids": ["p1:e1"], "reason": text}]}
            if name.startswith("applicability-check"):
                return {"status": applicability, "support_element_ids": ["p1:e1"], "reason": text}
            if name.startswith("requirement-page"):
                ids = {q["id"] for q in packet["evidence_requirements"]}
                self.assertEqual("training" in ids, applicability != "not_applicable")
                self.assertNotIn("research_scope", packet)
                return {"facts": [{"statement": "방법을 구현했다.", "limits": "구현 기록이다.", "kind": "method",
                    "claim_status": "documented_method", "source_origin": "research_note", "conditions": [], "observations": [],
                    "parameters": [], "measurements": [], "element_ids": ["p1:e1"], "requirement_ids": ["method"],
                    "supplemental_reason": ""}], "existing_links": []}
            if name.endswith("-verify"):
                return {"checks": {"E00001": {"support": "supported", "claim_status": "documented_method",
                    "source_origin": "research_note", "attribution_preserved": True, "contradictions": [],
                    "missing_support": [], "evidence_limitations": [], "note": "원문과 일치"}}}
            if name == "requirement-check-method":
                return {"status": "sufficient", "evidence_ids": ["E00001"], "missing_fields": [], "reason": "수행 방법 기록"}
            raise AssertionError(name)
        engine.call.side_effect = respond
        common = bank()
        before = copy.deepcopy(common)
        with patch("requirement_extraction.load_complete_sources", return_value=original):
            result = extract_requirement_evidence(pdf, engine, common)
        self.assertEqual(common, before)
        self.assertLess(seen.index("applicability-scan-0001"), seen.index("requirement-page-0001"))
        self.assertTrue((Path(result["run_dir"]) / "applicability.json").is_file())
        return result

    def test_same_common_bank_handles_different_journals_with_distinct_gates(self):
        expected = {"not_applicable": ("not_applicable", True), "applicable": ("missing", False),
                    "uncertain": ("applicability_uncertain", False)}
        for decision, (status, ready) in expected.items():
            with self.subTest(decision=decision), TemporaryDirectory() as tmp:
                result = self.collect(tmp, decision)
                self.assertEqual(result["requirement_coverage"]["training"]["status"], status)
                self.assertEqual(result["completion"]["ready_for_drafting"], ready)
                self.assertEqual(result["requirements"], bank())
                self.assertEqual(result["research"]["requirement_applicability"], result["requirement_applicability"])
                if decision == "not_applicable":
                    self.assertEqual(result["completion"]["unresolved_requirement_ids"], [])
                if decision == "uncertain":
                    self.assertEqual(result["completion"]["unresolved_applicability_ids"], ["training"])
                    self.assertEqual(result["completion"]["unresolved_requirement_ids"], [])


if __name__ == "__main__":
    unittest.main()
