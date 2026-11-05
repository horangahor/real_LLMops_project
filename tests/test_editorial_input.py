import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from drafting_budget import DraftingBudgetError, compact_packet, fits_request, request_bytes, request_limit
from editorial_input import fits_editorial_request, repair_request
from editorial_patch import (PRESERVATION_INSTRUCTION, assemble_editorial_patch,
                             call_preserving_subsections)
from editorial_revision import editorial_sources
from planned_paper import PlannedPaper
from review_test_support import editorial_reply
from test_editorial_revision import fixture


class EditorialInputTests(unittest.TestCase):
    def test_actual_limit_accepts_requests_in_old_reserved_range_without_changing_other_packers(self):
        packet = {"text": "x" * 200000}
        self.assertFalse(fits_request("system", packet, {}))
        self.assertTrue(fits_editorial_request("system", packet, {}))
        self.assertFalse(fits_editorial_request("system", {"text": "x" * 250000}, {}))

    def test_real_size_boundary_is_inclusive(self):
        base = request_bytes("system", compact_packet({"text": ""}), {})
        packet = {"text": "x" * (request_limit() - base)}
        self.assertTrue(fits_editorial_request("system", packet, {}))
        packet["text"] += "x"
        self.assertFalse(fits_editorial_request("system", packet, {}))

    def test_repair_keeps_context_findings_and_protected_scopes_without_failed_prose_copy(self):
        packet = {"source_parts": {"s": {"p0": [{"id": "s_p1_s1", "paragraph_id": "s_p1", "text": "본문 전체"}]}},
                  "outline": ["목차"], "revision": {"review": {"issues": [{"reason": "기존 연결 지적"}]}}}
        error = {"reason": "s_p1_s1: 잘못된 출력 칸", "response": {"text": "실패 응답의 중복 본문" * 10000},
                 "validation_code": "subsection_removal", "protected_subsections": [{"section_id": "s", "part": "p0"}]}
        before = copy.deepcopy((packet, error))
        result = repair_request(packet, error, "형식만 보정한다.")
        self.assertEqual(result["source_parts"], packet["source_parts"])
        self.assertEqual(result["revision"], packet["revision"])
        self.assertEqual(result["outline"], packet["outline"])
        self.assertNotIn("response", result["invalid_response"])
        self.assertEqual(result["invalid_response"]["affected_spans"], ["s_p1_s1"])
        self.assertEqual(result["invalid_response"]["protected_subsections"], error["protected_subsections"])
        self.assertEqual((packet, error), before)

    def test_large_full_context_and_repair_fit_without_cutting_text_or_repeating_invalid_body(self):
        _, packet, previous, _ = fixture()
        previous["s1"]["parts"]["p0"] = "Complete original context. " * 7300 + "[근거:F1]"
        parts, _, _ = editorial_sources(previous, {"s1": packet})
        calls = []
        def client(system, body, schema, path):
            calls.append(copy.deepcopy(body))
            self.assertEqual(body["source_parts"], parts)
            self.assertLessEqual(request_bytes(system, compact_packet(body), schema), request_limit())
            self.assertGreater(request_bytes(system, compact_packet(body), schema), int(request_limit() * .75))
            raw = editorial_reply(body)
            if len(calls) == 1:
                raw["EXTRA"] = {"text": "failed response copied prose" * 5000}
            if "invalid_response" in body:
                self.assertNotIn("response", body["invalid_response"])
            return raw
        with TemporaryDirectory() as tmp:
            result = assemble_editorial_patch(PlannedPaper(tmp, client), Path(tmp), "generate-0", "paper", previous, {"s1": packet})
            original = json.loads(next(Path(tmp).glob("*-invalid-0.json")).read_text(encoding="utf-8"))
            audit = json.loads(next(Path(tmp).glob("*-repair-input.json")).read_text(encoding="utf-8"))
        self.assertEqual(result, previous)
        self.assertIn("EXTRA", original["response"])
        self.assertTrue(audit["full_context_preserved"])
        self.assertGreater(audit["original_error_bytes"], 100000)
        self.assertLess(audit["feedback_bytes"], 1000)
        self.assertLess(len(calls), 5)

    def test_request_above_real_cap_is_blocked_before_network(self):
        _, packet, previous, _ = fixture()
        previous["s1"]["parts"]["p0"] = "x" * 250000 + " [근거:F1]"
        calls = []
        with TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(DraftingBudgetError, "상한=240000"):
                assemble_editorial_patch(PlannedPaper(tmp, lambda *args: calls.append(args)), Path(tmp),
                                         "generate-0", "paper", previous, {"s1": packet})
            diagnostic = json.loads(next(Path(tmp).glob("*-budget-failure.json")).read_text(encoding="utf-8"))
        self.assertFalse(calls)
        self.assertEqual(diagnostic["limit_bytes"], 240000)
        self.assertGreater(diagnostic["input_bytes"], 240000)

    def test_valid_legacy_full_feedback_cache_is_reused_and_invalid_cache_is_not(self):
        for valid in (True, False):
            with self.subTest(valid=valid), TemporaryDirectory() as tmp:
                calls = []
                def client(system, packet, schema, path):
                    calls.append(packet)
                    return {"ok": valid or "response" not in packet["invalid_response"]}
                engine = PlannedPaper(tmp, client)
                legacy = {"invalid_response": {"reason": "format", "response": {"long": "body"}}}
                current = {"invalid_response": {"reason": "format"}}
                system = "system" + PRESERVATION_INSTRUCTION
                engine.call(Path(tmp), "repair", system, legacy, {})
                def validate(raw):
                    if not raw["ok"]:
                        raise ValueError("invalid cached edit")
                result = call_preserving_subsections(engine, Path(tmp), "repair", system, current, {},
                                                     legacy_packet=legacy, validate_cached=validate)
                self.assertTrue(result["ok"])
                self.assertEqual(len(calls), 1 if valid else 2)


if __name__ == "__main__":
    unittest.main()
