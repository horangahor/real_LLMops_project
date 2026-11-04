import copy
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from evidence_requirements import fingerprint
from requirement_extraction import extract_requirement_evidence
from test_evidence_requirements import raw_fact


class CollectionProgressTests(unittest.TestCase):
    def setup_collection(self, root):
        pdf = root / "journal.pdf"
        pdf.write_bytes(b"offline journal fixture")
        source = {"run_dir": str(root / "draft_history/parse-api-v1/document/research-sources-v3"),
                  "page_count": 2, "source": {"file": pdf.name, "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest()},
                  "elements": [{"element_id": f"p{p}:e1", "page": p, "category": "paragraph",
                                "origin": "standard_parse", "text": "메모리를 재사용한다."} for p in (1, 2)],
                  "pdf_image_inventory": []}
        question = {"id": "Q1", "question": "구현 방법은?", "expected_fields": ["구현 방법"], "priority": "required",
                    "applicability": {"kind": "universal", "condition": "모든 연구"}}
        requirements = {"scope": "topic_independent", "requirements": [question, {**question, "id": "Q2"}]}
        applicability = {key: {"status": "applicable", "reason": "모든 연구"} for key in ("Q1", "Q2")}
        engine = Mock(base_dir=root)
        self.page_calls = []
        self.fail_page = None
        self.invalid_page = None

        def call(folder, name, system, packet, schema, **kwargs):
            if name.startswith("requirement-page-"):
                page = packet["target_page"]
                self.page_calls.append(page)
                if page == self.fail_page:
                    self.fail_page = None
                    raise RuntimeError("offline page interruption")
                if page == self.invalid_page:
                    return {"facts": [], "existing_links": [{"fact_id": "unknown", "element_ids": [f"p{page}:e1"], "requirement_ids": ["Q1"]}]}
                if page == 1 or not packet["preserved_evidence"]:
                    raw = raw_fact(page)
                    if page == 2:
                        raw["requirement_ids"] = ["Q1", "Q2"]
                    return {"facts": [raw], "existing_links": []}
                self.assertEqual(packet["preserved_evidence"][0]["id"], "E00001")
                return {"facts": [], "existing_links": [{"fact_id": "E00001", "element_ids": ["p2:e1"], "requirement_ids": ["Q2"]}]}
            if name.startswith("requirement-check-"):
                return {"status": "sufficient", "evidence_ids": ["E00001"], "missing_fields": [], "reason": "원문과 일치"}
            raise AssertionError("Unexpected model request " + name)

        engine.call.side_effect = call
        return pdf, source, requirements, applicability, engine

    @staticmethod
    def verified(_engine, _folder, _elements, packet, **kwargs):
        return {"facts": [{**copy.deepcopy(fact), "support": "supported", "support_note": "원문과 일치",
                           "attribution_preserved": True, "writing_role": "research_fact"} for fact in packet["facts"]]}

    @staticmethod
    def progress_path(root):
        return next(root.glob("draft_history/parse-api-v1/*/research-evidence-requirements-v2/*/collection-progress.json"))

    def test_interruption_resumes_at_next_page_without_replaying_completed_page_or_applicability(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf, source, requirements, applicability, engine = self.setup_collection(root)
            self.fail_page = 2
            with patch("requirement_extraction.load_complete_sources", return_value=source), \
                    patch("requirement_extraction.assess_applicability", return_value=applicability) as assess, \
                    patch("requirement_extraction.verify_page", side_effect=self.verified):
                with self.assertRaisesRegex(RuntimeError, "offline page interruption"):
                    extract_requirement_evidence(pdf, engine, requirements)
                progress = json.loads(self.progress_path(root).read_text(encoding="utf-8"))
                self.assertEqual(progress["value"]["completed_page"], 1)
                self.assertEqual(progress["value"]["scanned_pages"], [1])
                self.assertEqual(progress["value"]["raw_items"][0]["id"], "E00001")
                assess.side_effect = AssertionError("Already completed applicability must not be replayed")
                result = extract_requirement_evidence(pdf, engine, requirements)
            self.assertEqual(self.page_calls, [1, 2, 2])
            self.assertTrue(result["completion"]["ready_for_drafting"])
            self.assertEqual(result["writing_fact_ids"], ["E00001"])
            self.assertEqual(result["items"][0]["requirement_ids"], ["Q1", "Q2"])
            self.assertEqual([s["element_id"] for s in result["items"][0]["sources"]], ["p1:e1", "p2:e1"])

    def test_source_review_interruption_does_not_replay_any_collection_pages(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf, source, requirements, applicability, engine = self.setup_collection(root)
            with patch("requirement_extraction.load_complete_sources", return_value=source), \
                    patch("requirement_extraction.assess_applicability", return_value=applicability) as assess, \
                    patch("requirement_extraction.verify_page", side_effect=RuntimeError("offline source review interruption")):
                with self.assertRaisesRegex(RuntimeError, "offline source review interruption"):
                    extract_requirement_evidence(pdf, engine, requirements)
                state = json.loads(self.progress_path(root).read_text(encoding="utf-8"))["value"]
                self.assertEqual(state["completed_page"], 2)
                assess.side_effect = AssertionError("Applicability replay")
                with patch("requirement_extraction.verify_page", side_effect=self.verified):
                    result = extract_requirement_evidence(pdf, engine, requirements)
            self.assertEqual(self.page_calls, [1, 2])
            self.assertTrue(result["completion"]["ready_for_drafting"])

    def test_invalid_page_stays_pending_across_interruption_and_still_blocks_drafting(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf, source, requirements, applicability, engine = self.setup_collection(root)
            self.invalid_page, self.fail_page = 1, 2
            with patch("requirement_extraction.load_complete_sources", return_value=source), \
                    patch("requirement_extraction.assess_applicability", return_value=applicability), \
                    patch("requirement_extraction.verify_page", side_effect=self.verified):
                with self.assertRaisesRegex(RuntimeError, "offline page interruption"):
                    extract_requirement_evidence(pdf, engine, requirements)
                state = json.loads(self.progress_path(root).read_text(encoding="utf-8"))["value"]
                self.assertEqual(state["pending_pages"], [1])
                self.assertEqual(state["raw_items"], [])
                result = extract_requirement_evidence(pdf, engine, requirements)
            self.assertEqual(self.page_calls, [1, 1, 2, 2])
            self.assertFalse(result["completion"]["ready_for_drafting"])
            self.assertEqual(result["completion"]["pending_extraction_pages"], [1])
            self.assertTrue(result["completion"]["unresolved_source_items"])

    def test_corrupt_or_invalid_progress_stops_before_any_further_model_call(self):
        for invalid in ("checksum", "input", "page_range", "future_source"):
            with self.subTest(invalid=invalid), TemporaryDirectory() as tmp:
                root = Path(tmp)
                pdf, source, requirements, applicability, engine = self.setup_collection(root)
                self.fail_page = 2
                with patch("requirement_extraction.load_complete_sources", return_value=source), \
                        patch("requirement_extraction.assess_applicability", return_value=applicability):
                    with self.assertRaises(RuntimeError):
                        extract_requirement_evidence(pdf, engine, requirements)
                    path = self.progress_path(root)
                    saved = json.loads(path.read_text(encoding="utf-8"))
                    if invalid == "input":
                        saved["input_fingerprint"] = "other-input"
                    elif invalid == "page_range":
                        saved["value"]["completed_page"] = 3
                        saved["sha256"] = fingerprint(saved["value"])
                    else:
                        saved["value"]["raw_items"][0]["element_ids"] = ["p2:e1"]
                        if invalid == "future_source":
                            saved["sha256"] = fingerprint(saved["value"])
                    path.write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")
                    before = engine.call.call_count
                    with self.assertRaisesRegex(ValueError, "페이지 수집 재개"):
                        extract_requirement_evidence(pdf, engine, requirements)
                    self.assertEqual(engine.call.call_count, before)

    def test_changed_source_or_question_starts_separate_collection(self):
        for changed in ("source", "question"):
            with self.subTest(changed=changed), TemporaryDirectory() as tmp:
                root = Path(tmp)
                pdf, source, requirements, applicability, engine = self.setup_collection(root)
                self.fail_page = 2
                with patch("requirement_extraction.load_complete_sources", return_value=source), \
                        patch("requirement_extraction.assess_applicability", return_value=applicability) as assess, \
                        patch("requirement_extraction.verify_page", side_effect=self.verified):
                    with self.assertRaises(RuntimeError):
                        extract_requirement_evidence(pdf, engine, requirements)
                    first = self.progress_path(root)
                    if changed == "source":
                        pdf.write_bytes(b"different journal")
                        source["source"]["sha256"] = hashlib.sha256(pdf.read_bytes()).hexdigest()
                    else:
                        requirements["requirements"][0]["question"] = "다른 질문"
                    result = extract_requirement_evidence(pdf, engine, requirements)
                    self.assertEqual(assess.call_count, 2)
                self.assertEqual(self.page_calls, [1, 2, 1, 2])
                self.assertNotEqual(first.parent, Path(result["run_dir"]))

    def test_completed_assessment_checkpoint_remains_the_preferred_resume_path(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf, source, requirements, applicability, engine = self.setup_collection(root)
            with patch("requirement_extraction.load_complete_sources", return_value=source), \
                    patch("requirement_extraction.assess_applicability", return_value=applicability) as assess, \
                    patch("requirement_extraction.verify_page", side_effect=self.verified) as verify:
                expected = extract_requirement_evidence(pdf, engine, requirements)
                self.progress_path(root).write_text("outdated collection file", encoding="utf-8")
                assess.side_effect = AssertionError("Applicability replay")
                verify.side_effect = AssertionError("Source review replay")
                actual = extract_requirement_evidence(pdf, engine, requirements)
            self.assertEqual(actual, expected)
            self.assertEqual(self.page_calls, [1, 2])


if __name__ == "__main__":
    unittest.main()
