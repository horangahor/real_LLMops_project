import copy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from bounded_drafting import generate_bounded
from draft_prose import (LEGACY_INLINE_INSTRUCTION, PROTOCOL, STRUCTURED_CITATION_INSTRUCTION,
                         prose_schema, render_part, render_parts)
from drafting_budget import SOURCE_PROTOCOL, compact_packet
from paper_context import build_contexts
from planned_paper import GROUNDING, WRITER, PlannedPaper, parts_schema
from test_drafting_budget import fixture
from test_hierarchical_drafting import assigned_plan
from test_planned_paper import research


class WriterCitationProtocolTests(unittest.TestCase):
    def test_new_whole_and_split_requests_have_one_citation_format_instruction(self):
        for split in (False, True):
            with self.subTest(split=split), TemporaryDirectory() as tmp:
                packet = (fixture()[2]["subsections"]["s0"]["p0"] if split else
                          build_contexts(assigned_plan(), research(), {})["subsections"]["s0"]["p0"])
                calls = []
                def client(system, request, schema, path):
                    calls.append(system)
                    self.assertNotIn(LEGACY_INLINE_INSTRUCTION, system)
                    self.assertIn(STRUCTURED_CITATION_INSTRUCTION, system)
                    self.assertIn("text에 [근거:...]를 직접 쓰지 않는다", system)
                    return {"parts": {"p0": [{"text": "관측 범위를 설명한다.",
                                              "evidence_ids": [request["facts"][0]["id"]]}]}}
                with patch.dict("os.environ", {"PAPER_REQUEST_MAX_BYTES": "24000"}):
                    result = generate_bounded(PlannedPaper(tmp, client), Path(tmp), "generate", GROUNDING + WRITER,
                                              packet, parts_schema(packet), {"s0": packet}, True)
                self.assertTrue(render_parts(result, packet)["parts"]["p0"])
                self.assertEqual(len(calls) > 1, split)

    def test_valid_old_structured_cache_is_reused_without_regenerating_prose(self):
        packet = build_contexts(assigned_plan(), research(), {})["subsections"]["s0"]["p0"]
        calls = []
        def client(*args):
            calls.append(args)
            return {"parts": {"p0": [{"text": "기존 본문이다.", "evidence_ids": ["F1"]}]}}
        with TemporaryDirectory() as tmp:
            engine = PlannedPaper(tmp, client)
            old = engine.call(Path(tmp), "generate", GROUNDING + WRITER + PROTOCOL + SOURCE_PROTOCOL,
                              compact_packet(packet), prose_schema(packet))
            result = generate_bounded(engine, Path(tmp), "generate", GROUNDING + WRITER,
                                      packet, parts_schema(packet), {"s0": packet}, True)
        self.assertEqual(result, old)
        self.assertEqual(len(calls), 1)

    def test_prefix_conflict_stays_invalid_and_reports_both_representations(self):
        response = [{"text": "기록된 관측이다. [근거:E_ab12]", "evidence_ids": ["H_ab12"]}]
        before = copy.deepcopy(response)
        with self.assertRaises(ValueError) as caught:
            render_part(response, ["H_ab12"], "p0")
        for value in ("E_ab12", "H_ab12", "미허용 본문 ID", "접두사를 추측"):
            self.assertIn(value, str(caught.exception))
        self.assertEqual(response, before)

    def test_split_repair_receives_exact_conflict_and_can_resume_without_extra_calls(self):
        packet = fixture()[2]["subsections"]["s0"]["p0"]
        calls = []
        def client(system, request, schema, path):
            calls.append(request)
            evidence_id = request["facts"][0]["id"]
            if len(calls) == 1:
                text = "관측이다. [근거:wrong_prefix]"
            else:
                text = "배정된 관측 범위만 설명한다."
            if "fragment_validation_error" in request:
                self.assertIn("wrong_prefix", request["fragment_validation_error"]["error"])
                self.assertIn(evidence_id, request["fragment_validation_error"]["error"])
                self.assertIn("text의 인용 표시를 제거", request["fragment_validation_error"]["error"])
            return {"parts": {"p0": [{"text": text, "evidence_ids": [evidence_id]}]}}
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {"PAPER_REQUEST_MAX_BYTES": "24000"}):
            engine = PlannedPaper(tmp, client)
            result = generate_bounded(engine, Path(tmp), "generate", GROUNDING + WRITER,
                                      packet, parts_schema(packet), {"s0": packet}, True)
            self.assertTrue(any("fragment_validation_error" in request for request in calls))
            self.assertNotIn("wrong_prefix", result["parts"]["p0"])
            count = len(calls)
            self.assertEqual(generate_bounded(engine, Path(tmp), "generate", GROUNDING + WRITER,
                packet, parts_schema(packet), {"s0": packet}, True), result)
            self.assertEqual(len(calls), count)


if __name__ == "__main__":
    unittest.main()
