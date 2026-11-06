import copy
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from drafting_budget import compact_packet, request_bytes
from planned_paper import PlannedPaper, index_paragraphs, review_schema
from review_response import (KEYED_REVIEW, correction_schema, fits_review_request,
    review_correction_packet, review_correction_system, review_with_repair)
from test_planned_paper import plan


def fixture():
    value = plan(2)
    bodies = {s["id"]: "Observed a limited result, without independent validation. [근거:F1]" for s in value["sections"]}
    packet = {"plan": value, "draft_paragraphs": index_paragraphs(bodies),
        "research": {"human_guidance": [{"question_id": "Q1", "action": "accept_limited", "writing_instruction": "Only observed conditions."}]},
        "reference_guides": {}, "review_policy": "approved-facts-v1", "coverage_policy": "content-coverage-v2"}
    good = {"checks": {f"item{i}": {"verdict": "met", "paragraph_ids": [f"s{i}_p1"], "evidence_ids": ["F1"]} for i in range(2)},
            "reference_checks": {}, "issues": []}
    bad = copy.deepcopy(good)
    bad["checks"]["item0"]["paragraph_ids"] = ["nonexistent"]
    bad["issues"] = [{"section_id": "s0", "paragraph_id": "nonexistent", "severity": "error", "evidence_ids": ["F1"],
                      "reason": "Repeated prior review text. " * 4000}]
    return value, bodies, packet, good, bad


class ReviewInputBudgetTests(unittest.TestCase):
    def test_oversized_repair_keeps_full_original_input_and_reuses_completed_response(self):
        value, bodies, packet, good, bad = fixture()
        original = copy.deepcopy(packet)
        schema = review_schema(value, packet["draft_paragraphs"])
        wire = correction_schema(schema, value)
        base = request_bytes("review" + KEYED_REVIEW, compact_packet(packet), wire)
        limit = max(4000, base + 5000)
        calls = []
        def client(system, request, _schema, path):
            calls.append(copy.deepcopy(request))
            return bad if len(calls) == 1 else good
        with TemporaryDirectory() as tmp, patch.dict(os.environ, {"PAPER_REQUEST_MAX_BYTES": str(limit)}):
            engine = PlannedPaper(tmp, client)
            raw, report = review_with_repair(engine, Path(tmp), "review", "review", packet, schema, value, bodies)
            self.assertTrue(report["approved"])
            self.assertEqual(len(calls), 2)
            repaired = calls[1]
            self.assertEqual(repaired["repair_input_policy"], "review-diagnostics-only-v1")
            self.assertTrue(all(repaired[k] == v for k, v in original.items()))
            saved = json.loads((Path(tmp) / "review-validation-0.json").read_bytes())
            self.assertEqual(saved["raw_response"], bad)
            audit = json.loads((Path(tmp) / "review-correction-input.json").read_bytes())
            self.assertGreater(audit["original_input_bytes"], limit)
            self.assertLessEqual(audit["input_bytes"], limit)
            review_with_repair(engine, Path(tmp), "review", "review", packet, schema, value, bodies)
            self.assertEqual(len(calls), 2)
        self.assertEqual(packet, original)

    def test_completed_legacy_large_correction_is_reused_without_another_model_call(self):
        value, bodies, packet, good, bad = fixture()
        schema = review_schema(value, packet["draft_paragraphs"])
        wire = correction_schema(schema, value)
        base = request_bytes("review" + KEYED_REVIEW, compact_packet(packet), wire)
        with TemporaryDirectory() as tmp, patch.dict(os.environ, {"PAPER_REQUEST_MAX_BYTES": str(max(4000, base + 5000))}):
            calls = []
            def client(*args):
                calls.append(args)
                return bad if len(calls) == 1 else good
            engine = PlannedPaper(tmp, client)
            engine.call(Path(tmp), "review", "review" + KEYED_REVIEW, compact_packet(packet), wire)
            # The exact error string is part of the historical request identity.
            from review_response import checked_review
            try:
                checked_review(bad, value, bodies)
            except ValueError as error:
                correction = review_correction_packet(packet, value, bad, error)
            engine.call(Path(tmp), "review-correction-1", review_correction_system("review", packet), compact_packet(correction), wire)
            snapshots = {p: p.read_bytes() for p in (Path(tmp) / "responses").glob("*.json")}
            self.assertTrue(review_with_repair(engine, Path(tmp), "review", "review", packet, schema, value, bodies)[1]["approved"])
            self.assertEqual(len(calls), 2)
            self.assertTrue(all(p.read_bytes() == content for p, content in snapshots.items()))

    def test_preflight_counts_repeated_fixed_key_schema_instead_of_array_schema(self):
        value, bodies, packet, _, _ = fixture()
        section = value["sections"][0]
        section["required_items"] = [{"id": f"requirement{i}", "description": "A required comparison", "evidence_ids": ["F1"]} for i in range(30)]
        packet["draft_paragraphs"] = {f"s0_p{i}": {"section_id": "s0", "text": "A short observation [근거:F1]"} for i in range(100)}
        schema = review_schema(value, packet["draft_paragraphs"])
        array_size = request_bytes("review", compact_packet(packet), schema)
        keyed_size = request_bytes("review" + KEYED_REVIEW, compact_packet(packet), correction_schema(schema, value))
        self.assertGreater(keyed_size, array_size)
        limit = max(4000, (array_size + keyed_size) // 2)
        self.assertLess(array_size, limit)
        with patch.dict(os.environ, {"PAPER_REQUEST_MAX_BYTES": str(limit)}):
            self.assertFalse(fits_review_request("review", packet, schema, value))


if __name__ == "__main__":
    unittest.main()
