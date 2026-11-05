import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from bounded_drafting import generate_bounded
from draft_prose import JoinedParagraphsError, render_parts
from paper_context import build_contexts
from planned_paper import GROUNDING, WRITER, PlannedPaper, parts_schema
from prose_format_repair import POLICY, repair_joined_paragraphs
from test_drafting_budget import fixture
from test_hierarchical_drafting import assigned_plan
from test_planned_paper import research


def setup():
    packet = build_contexts(assigned_plan(), research(), {})["subsections"]["s0"]["p0"]
    response = {"parts": {"p0": [{"text": "첫 조건의 관측이다.\n\n두 번째 관측과 한계다.",
                                    "evidence_ids": ["F1", "F2"]}]}}
    return packet, response


class ProseFormatRepairTests(unittest.TestCase):
    def test_joined_text_reports_structure_error_without_demanding_inline_citations(self):
        packet, response = setup()
        with self.assertRaises(JoinedParagraphsError) as caught:
            render_parts(response, packet)
        self.assertIn("2개 문단", str(caught.exception))
        self.assertNotIn("text의 인용 표시를 제거", str(caught.exception))

    def test_format_call_returns_only_per_paragraph_ids_preserving_exact_text_and_order(self):
        packet, response = setup()
        response["parts"]["p0"].append({"text": "별도 정상 문단이다.", "evidence_ids": ["F1"]})
        before = copy.deepcopy(response)
        calls = []
        def client(system, request, schema, path):
            calls.append(request)
            self.assertEqual(set(schema["properties"]), {"evidence_by_paragraph"})
            self.assertEqual(request["paragraphs"]["paragraph_1"]["text"], "첫 조건의 관측이다.")
            self.assertEqual(request["paragraphs"]["paragraph_2"]["text"], "두 번째 관측과 한계다.")
            return {"evidence_by_paragraph": {"paragraph_1": ["F1"], "paragraph_2": ["F2"]}}
        with TemporaryDirectory() as tmp:
            engine = PlannedPaper(tmp, client)
            result = repair_joined_paragraphs(engine, Path(tmp), "repair", response, {"s0": packet}, True)
            self.assertEqual(result["parts"]["p0"], [
                {"text": "첫 조건의 관측이다.", "evidence_ids": ["F1"]},
                {"text": "두 번째 관측과 한계다.", "evidence_ids": ["F2"]}, before["parts"]["p0"][1]])
            self.assertEqual(response, before)
            audit = json.loads((Path(tmp) / f"repair-{POLICY}.json").read_text(encoding="utf-8"))
            self.assertFalse(audit["body_rewritten"])
            self.assertEqual(repair_joined_paragraphs(engine, Path(tmp), "repair", response, {"s0": packet}, True), result)
            self.assertEqual(len(calls), 1)

    def test_invalid_mapping_or_missing_paragraph_is_not_applied(self):
        for links in ({"paragraph_1": ["unknown"], "paragraph_2": ["F2"]},
                      {"paragraph_1": ["F1"]}, {"paragraph_1": [], "paragraph_2": ["F2"]}):
            with self.subTest(links=links), TemporaryDirectory() as tmp:
                packet, response = setup()
                before = copy.deepcopy(response)
                client = lambda *args: {"evidence_by_paragraph": links}
                with self.assertRaisesRegex(ValueError, "문단별 근거 연결 형식 보정에 실패"):
                    repair_joined_paragraphs(PlannedPaper(tmp, client), Path(tmp), "repair", response, {"s0": packet}, True)
                self.assertEqual(response, before)
                audit = json.loads((Path(tmp) / f"repair-{POLICY}.json").read_text(encoding="utf-8"))
                self.assertEqual(audit["status"], "rejected")

    def test_unknown_original_ids_and_tables_remain_invalid_before_repair_call(self):
        for text, ids in (("첫 문단\n\n둘째 문단", ["unknown"]),
                          ("첫 문단\n\n| 직접 | 표 |", ["F1"])):
            packet, _ = setup()
            response = {"parts": {"p0": [{"text": text, "evidence_ids": ids}]}}
            calls = []
            with TemporaryDirectory() as tmp, self.assertRaises(ValueError):
                repair_joined_paragraphs(PlannedPaper(tmp, lambda *args: calls.append(args)),
                                         Path(tmp), "repair", response, {"s0": packet}, True)
            self.assertFalse(calls)

    def test_whole_generation_uses_one_format_repair_without_rewriting_prose(self):
        packet, response = setup()
        calls = []
        def client(system, request, schema, path):
            calls.append(request)
            if request.get("operation") == POLICY:
                return {"evidence_by_paragraph": {"paragraph_1": ["F1"], "paragraph_2": ["F2"]}}
            return copy.deepcopy(response)
        with TemporaryDirectory() as tmp:
            engine = PlannedPaper(tmp, client)
            result = generate_bounded(engine, Path(tmp), "generate", GROUNDING + WRITER,
                                      packet, parts_schema(packet), {"s0": packet}, True)
            self.assertEqual(len(calls), 2)
            self.assertEqual([p["text"] for p in result["parts"]["p0"]], response["parts"]["p0"][0]["text"].split("\n\n"))
            self.assertEqual(generate_bounded(engine, Path(tmp), "generate", GROUNDING + WRITER,
                packet, parts_schema(packet), {"s0": packet}, True), result)
            self.assertEqual(len(calls), 2)

    def test_split_generation_reuses_existing_repair_slot_and_completed_mapping_cache(self):
        packet = fixture()[2]["subsections"]["s0"]["p0"]
        calls = []
        def client(system, request, schema, path):
            calls.append(request)
            if request.get("operation") == POLICY:
                return {"evidence_by_paragraph": {key: [row["candidate_evidence_ids"][0]]
                                                  for key, row in request["paragraphs"].items()}}
            ids = [request["facts"][0]["id"]]
            text = "첫 관측이다.\n\n조건과 한계다." if len(calls) == 1 else "나머지 관측이다."
            return {"parts": {"p0": [{"text": text, "evidence_ids": ids}]}}
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {"PAPER_REQUEST_MAX_BYTES": "24000"}):
            engine = PlannedPaper(tmp, client)
            result = generate_bounded(engine, Path(tmp), "generate", GROUNDING + WRITER,
                                      packet, parts_schema(packet), {"s0": packet}, True)
            self.assertEqual(sum(p.get("operation") == POLICY for p in calls), 1)
            self.assertFalse(any("fragment_validation_error" in p for p in calls))
            self.assertIn("첫 관측이다. [근거:F0]\n\n조건과 한계다. [근거:F0]", result["parts"]["p0"])
            count = len(calls)
            self.assertEqual(generate_bounded(engine, Path(tmp), "generate", GROUNDING + WRITER,
                packet, parts_schema(packet), {"s0": packet}, True), result)
            self.assertEqual(len(calls), count)


if __name__ == "__main__":
    unittest.main()
