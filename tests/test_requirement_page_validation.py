import copy
import hashlib
import json
import unittest
import requests
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from planned_paper import PlannedPaper
from requirement_extraction import collect_page, page_request, validate_page_response, extract_requirement_evidence, page_call


def raw(page=1):
    return {"statement": "메모리를 재사용한다.", "limits": "구현 기록이다.", "kind": "method",
        "claim_status": "documented_method", "source_origin": "research_note", "conditions": [],
        "observations": [], "parameters": [], "measurements": [], "element_ids": [f"p{page}:e1"],
        "requirement_ids": ["Q1"], "supplemental_reason": ""}


class PageValidationTests(unittest.TestCase):
    def setUp(self):
        self.elements = {f"p{p}:e1": {"element_id": f"p{p}:e1", "page": p, "category": "paragraph",
            "origin": "standard_parse", "text": "메모리를 재사용한다."} for p in (1, 2)}
        self.questions = {"Q1": {"id": "Q1", "question": "수행 방법은 무엇인가?"}}
        self.applicability = {"Q1": {"status": "applicable", "reason": "다른 페이지의 비공개 단서",
                                   "sources": [{"element_id": "p84:other", "quote": "다른 페이지의 연구 내용"}]}}

    def test_first_page_reuse_must_be_empty_and_applicability_content_cannot_leak_into_page(self):
        packet, schema, _, target = page_request(1, 2, self.elements, self.questions, self.applicability, [])
        self.assertEqual(schema["properties"]["existing_links"]["maxItems"], 0)
        self.assertEqual(packet["requirement_applicability"], {"Q1": {"status": "applicable"}})
        self.assertEqual(target, ["p1:e1"])
        self.assertEqual(packet["context_element_ids"], ["p2:e1"])
        self.assertNotIn("다른 페이지의 비공개 단서", json.dumps(packet, ensure_ascii=False))

    def test_none_sentinel_is_normalized_only_when_it_cannot_represent_a_real_link(self):
        value = {"facts": [raw()], "existing_links": [{"fact_id": "none", "requirement_ids": [], "element_ids": ["p1:e1"]}]}
        checked = validate_page_response(value, [], self.questions, self.elements, 1, ["p1:e1"])
        self.assertEqual(checked["existing_links"], [])
        self.assertEqual(checked["facts"], value["facts"])
        self.assertEqual(len(checked["normalizations"]), 1)
        value["existing_links"][0]["requirement_ids"] = ["Q1"]
        with self.assertRaisesRegex(ValueError, "none"):
            validate_page_response(value, [], self.questions, self.elements, 1, ["p1:e1"])

    def test_other_page_facts_are_rejected_even_when_all_source_ids_exist_in_context(self):
        value = {"facts": [raw(), raw(2)], "existing_links": []}
        with self.assertRaisesRegex(ValueError, r"facts\[1\]"):
            validate_page_response(value, [], self.questions, self.elements, 1, ["p1:e1"])

    def test_invalid_second_link_does_not_partially_modify_existing_evidence(self):
        preserved = [{**raw(), "id": "E00001"}]
        before = copy.deepcopy(preserved)
        value = {"facts": [], "existing_links": [
            {"fact_id": "E00001", "requirement_ids": ["Q1"], "element_ids": ["p2:e1"]},
            {"fact_id": "E404", "requirement_ids": ["Q1"], "element_ids": ["p2:e1"]}]}
        with self.assertRaisesRegex(ValueError, "E404"):
            validate_page_response(value, preserved, self.questions, self.elements, 2, ["p2:e1"])
        self.assertEqual(preserved, before)

    def test_invalid_page_is_corrected_once_with_specific_errors_and_cached_on_resume(self):
        invalid = {"facts": [raw(2)], "existing_links": [{"fact_id": "none", "requirement_ids": [], "element_ids": ["p1:e1"]}]}
        valid = {"facts": [raw()], "existing_links": []}
        packets = []
        def client(system, packet, schema, path):
            packets.append(packet)
            return copy.deepcopy(valid if "correction" in str(path) else invalid)
        packet, schema, context, target = page_request(1, 2, self.elements, self.questions, self.applicability, [])
        with TemporaryDirectory() as tmp:
            engine = PlannedPaper(tmp)
            with patch("planned_paper.request_json", side_effect=lambda system, packet, schema, path, *args, **kwargs: client(system, packet, schema, path)):
                for _ in range(2):
                    result = collect_page(engine, Path(tmp), 1, packet, schema, [], self.questions, context, target)
                    self.assertEqual(result["facts"], [raw()])
            report = json.loads((Path(tmp) / "pages/page-0001-validation.json").read_text(encoding="utf-8"))
        self.assertEqual(len(packets), 2)
        self.assertIn("facts[0]", str(packets[1]["validation_errors"]))
        self.assertNotIn("rejected_response", packets[1])
        self.assertEqual(report["status"], "validated")
        self.assertEqual(len(report["rejected_attempts"]), 1)

    def test_second_invalid_response_is_preserved_as_pending_without_accepting_partial_facts(self):
        packet, schema, context, target = page_request(1, 2, self.elements, self.questions, self.applicability, [])
        engine = Mock()
        engine.call.return_value = {"facts": [raw(), raw(2)], "existing_links": []}
        with TemporaryDirectory() as tmp:
            result = collect_page(engine, Path(tmp), 1, packet, schema, [], self.questions, context, target)
            report = json.loads((Path(tmp) / "pages/page-0001-validation.json").read_text(encoding="utf-8"))
        self.assertTrue(result["validation_pending"])
        self.assertEqual(result["facts"], [])
        self.assertEqual(engine.call.call_count, 2)
        self.assertEqual(report["status"], "pending")
        self.assertEqual(len(report["rejected_attempts"]), 2)

    def test_malformed_correction_response_pauses_only_that_page(self):
        packet, schema, context, target = page_request(1, 2, self.elements, self.questions, self.applicability, [])
        engine = Mock()
        engine.call.side_effect = [
            {"facts": [raw(2)], "existing_links": []},
            RuntimeError("모델이 완결된 JSON을 반환하지 못했습니다. 원본과 재시도 응답은 보존했습니다.")]
        with TemporaryDirectory() as tmp:
            result = collect_page(engine, Path(tmp), 1, packet, schema, [], self.questions, context, target)
            report = json.loads((Path(tmp) / "pages/page-0001-validation.json").read_text(encoding="utf-8"))
        self.assertTrue(result["validation_pending"])
        self.assertEqual(result["facts"], [])
        self.assertEqual(engine.call.call_count, 2)
        self.assertEqual(report["status"], "pending")
        self.assertEqual(len(report["rejected_attempts"]), 2)

    def test_a_pending_page_blocks_drafting_instead_of_becoming_an_empty_success(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "journal.pdf"
            pdf.write_bytes(b"source")
            source = {"run_dir": str(root / "draft_history/parse-api-v1/document/research-sources-v3"),
                "page_count": 1, "source": {"file": pdf.name, "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest()},
                "elements": [self.elements["p1:e1"]], "pdf_image_inventory": []}
            req = {"scope": "topic_independent", "requirements": [{**self.questions["Q1"], "priority": "required",
                "expected_fields": ["수행 방법"], "applicability": {"kind": "universal", "condition": "모든 연구"}}]}
            engine = Mock(base_dir=root)
            engine.call.return_value = {"facts": [raw()], "existing_links": [
                {"fact_id": "E404", "requirement_ids": ["Q1"], "element_ids": ["p1:e1"]}]}
            with patch("requirement_extraction.load_complete_sources", return_value=source):
                result = extract_requirement_evidence(pdf, engine, req)
        self.assertEqual(engine.call.call_count, 2)
        self.assertFalse(result["completion"]["ready_for_drafting"])
        self.assertEqual(result["completion"]["pending_extraction_pages"], [1])
        self.assertEqual(result["items"], [])
        self.assertTrue(result["completion"]["unresolved_source_items"])

    def timeout_error(self):
        error = RuntimeError("외부 API 응답을 받지 못했습니다.")
        error.__cause__ = requests.ReadTimeout("provider read timeout")
        return error

    def test_read_timeout_has_one_bounded_retry_and_resume_reuses_its_cache(self):
        packet = {"source_page_count": 84}
        engine = Mock()
        engine.call.side_effect = [self.timeout_error(), {"facts": [], "existing_links": []}]
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            expected = page_call(engine, folder, "requirement-page-0003", "system", packet, {}, 3)
            self.assertEqual(engine.call.call_count, 2)
            self.assertEqual(engine.call.call_args_list[0].kwargs["timeout_seconds"], 120)
            self.assertEqual(engine.call.call_args_list[1].kwargs["inference_settings"], {"reasoning_effort": "low"})
            self.assertEqual(engine.call.call_args_list[1].kwargs["timeout_seconds"], 120)
            engine.reset_mock()
            engine.call.side_effect = None
            engine.call.return_value = expected
            self.assertEqual(page_call(engine, folder, "requirement-page-0003", "system", packet, {}, 3), expected)
            self.assertEqual(engine.call.call_count, 1)
            self.assertTrue(engine.call.call_args.kwargs["cache_only"])
            self.assertTrue(engine.call.call_args.args[1].endswith("-timeout-retry"))

    def test_two_timeouts_pause_with_page_number_and_keep_the_error_history(self):
        engine = Mock()
        engine.call.side_effect = [self.timeout_error(), self.timeout_error()]
        with TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, "3쪽"):
                page_call(engine, Path(tmp), "requirement-page-0003", "system", {"source_page_count": 84}, {}, 3)
            report = json.loads((Path(tmp) / "pages/requirement-page-0003-transport.json").read_text(encoding="utf-8"))
        self.assertEqual(engine.call.call_count, 2)
        self.assertEqual(len(report["errors"]), 2)
        self.assertFalse(report.get("completed_fallback", False))

    def test_non_timeout_failures_do_not_trigger_a_second_paid_request(self):
        engine = Mock()
        engine.call.side_effect = RuntimeError("Solar 요청 실패 (HTTP 401)")
        with TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, "3쪽"):
                page_call(engine, Path(tmp), "requirement-page-0003", "system", {"source_page_count": 84}, {}, 3)
        self.assertEqual(engine.call.call_count, 1)


if __name__ == "__main__":
    unittest.main()
