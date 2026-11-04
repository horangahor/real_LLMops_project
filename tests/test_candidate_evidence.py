import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from bounded_drafting import REVISION, generation_fragments
from bounded_review import _coverage_packet, review_bounded
from planned_paper import GROUNDING, WRITER, PlannedPaper, index_paragraphs, review_schema
from review_response import checked_review
from test_draft_revision import revision_fixture
from test_hierarchical_drafting import Client
from test_planned_paper import plan, research


def candidate_fixture(count=47):
    value = plan(2)
    ids = [f"E{i:05d}" for i in range(count)]
    value["sections"][0]["evidence_ids"] = ids[:]
    value["sections"][0]["required_items"][0].update(evidence_ids=ids[:], description="선택한 구현 방식과 한계를 설명한다.")
    bodies = {"s0": f"구현 방식과 한계를 설명한다. [근거:{ids[0]}]", "s1": "결론이다. [근거:F1]"}
    raw = {"checks": [{"item_id": "item0", "verdict": "met", "paragraph_ids": ["s0_p1"], "evidence_ids": [ids[0]]},
                      {"item_id": "item1", "verdict": "met", "paragraph_ids": ["s1_p1"], "evidence_ids": ["F1"]}],
           "reference_checks": [], "issues": []}
    return value, bodies, raw


class CandidateEvidenceTests(unittest.TestCase):
    def test_47_candidates_do_not_require_47_citations(self):
        value, bodies, raw = candidate_fixture()
        original = copy.deepcopy((value, bodies, raw))
        report = checked_review(raw, value, bodies)
        self.assertTrue(report["approved"])
        self.assertEqual(report["required_content_coverage"]["value"], 1)
        self.assertEqual(len(report["checks"][0]["unused_candidate_evidence_ids"]), 46)
        self.assertNotIn("missing_body_evidence_ids", report["checks"][0])
        self.assertEqual((value, bodies, raw), original)

    def test_required_comparison_content_still_fails_even_when_some_candidate_is_cited(self):
        value, bodies, raw = candidate_fixture()
        value["sections"][0]["required_items"][0]["description"] = "두 방법의 결과와 비교 조건을 설명한다."
        raw["checks"][0].update(verdict="missing")
        report = checked_review(raw, value, bodies)
        self.assertFalse(report["approved"])
        self.assertEqual(report["required_content_coverage"]["met"], 1)
        self.assertEqual(report["checks"][0]["verdict"], "missing")

    def test_reported_used_evidence_must_really_be_cited_and_cannot_use_other_items_candidates(self):
        value, bodies, raw = candidate_fixture()
        raw["checks"][0]["evidence_ids"].append("E00001")
        report = checked_review(raw, value, bodies)
        self.assertFalse(report["approved"])
        self.assertEqual(report["checks"][0]["missing_body_evidence_ids"], ["E00001"])
        # Even a section-known ID cannot be used as support for a different item's claim.
        value["sections"][0]["evidence_ids"].append("OTHER")
        raw["checks"][0]["evidence_ids"] = ["OTHER"]
        with self.assertRaisesRegex(ValueError, "후보 근거 범위"):
            checked_review(raw, value, bodies)

    def test_met_without_any_selected_support_is_not_approved(self):
        value, bodies, raw = candidate_fixture()
        raw["checks"][0]["evidence_ids"] = []
        report = checked_review(raw, value, bodies)
        self.assertFalse(report["approved"])
        self.assertEqual(report["checks"][0]["failure_owner"], "reviewer")

    def test_semantic_revision_does_not_turn_all_unused_candidates_into_missing_evidence_tasks(self):
        _, _, packet, _, _ = revision_fixture()
        check = packet["revision"]["review"]["checks"][0]
        check.update(verdict="missing", evidence_ids=["F0"])
        for field in ("model_verdict", "missing_body_evidence_ids", "missing_section_evidence_ids", "missing_review_evidence_ids"):
            check.pop(field, None)
        packet["revision"]["evidence_link_gaps"] = []
        with patch.dict("os.environ", {"PAPER_REQUEST_MAX_BYTES": "36000"}):
            tasks = generation_fragments(GROUNDING + WRITER + REVISION, packet, {"s0": packet})
        requests = [request for _, _, _, request, schema in tasks if schema is not None]
        self.assertTrue(requests)
        self.assertFalse(any(r["fragment"].get("operation") == "missing_evidence" for r in requests))
        self.assertFalse(any(r["fragment"].get("missing_evidence_ids") for r in requests))
        self.assertTrue(any("F11" in [f["id"] for f in r["facts"]] for r in requests))  # available context, not mandatory usage

    def test_unused_candidates_do_not_spend_a_writer_revision_or_citation_repair(self):
        client = Client()
        client.plan["sections"][0]["required_items"][0]["evidence_ids"] = ["F1", "F2"]
        def response(system, packet, schema, path):
            raw = client(system, packet, schema, path)
            if path.parent.parent.name == "subsection-s0-p0":
                if "parts" in schema["properties"]:
                    raw["parts"]["p0"] = "필수 내용을 선택한 근거 범위에서 설명한다. [근거:F1]"
                elif "checks" in schema["properties"]:
                    raw["checks"][0]["evidence_ids"] = ["F1"]
            return raw
        with TemporaryDirectory() as tmp:
            result = PlannedPaper(tmp, response).run(research())
            events = [kind for stage, kind, _ in client.events if stage == "subsection-s0-p0"]
            self.assertEqual(events, ["generate", "review"])
            saved = json.loads((Path(result["run_dir"]) / "workflow/subsection-s0-p0/approved.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["value"]["raw_review"]["checks"][0]["evidence_ids"], ["F1"])
            self.assertTrue(result["review"]["approved"])

    def test_old_review_requests_are_not_reused_under_the_new_policy(self):
        value, bodies, raw = candidate_fixture(2)
        data = research()
        data["facts"] = [{"id": f"E{i:05d}", "statement": f"기록 {i}", "limits": "기록 범위", "sources": []} for i in range(2)] + data["facts"]
        packet = {"research": data, "plan": value, "draft_paragraphs": index_paragraphs(bodies), "reference_guides": {}}
        calls = []
        def client(system, request, schema, path):
            calls.append(system)
            return copy.deepcopy(raw)
        with TemporaryDirectory() as tmp:
            engine = PlannedPaper(tmp, client)
            schema = review_schema(value, packet["draft_paragraphs"])
            engine.call(Path(tmp), "review", "legacy system", packet, schema)
            _, report = review_bounded(engine, Path(tmp), "review", "legacy system", packet, schema, value, bodies)
            self.assertEqual(len(calls), 2)
            self.assertIn("candidate-pool-v1", calls[-1])
            self.assertTrue(report["approved"])

    def test_coverage_has_candidate_meanings_and_limits_without_repeating_source_quotes(self):
        from test_drafting_budget import fixture
        data, _, _, _, packet = fixture()
        original = copy.deepcopy(packet)
        scoped = _coverage_packet(packet, {})
        for before, after in zip(data["facts"], scoped["research"]["facts"]):
            self.assertEqual(after["statement"], before["statement"])
            self.assertEqual(after["limits"], before["limits"])
            self.assertNotIn("sources", after)
        self.assertEqual(packet, original)


if __name__ == "__main__":
    unittest.main()
