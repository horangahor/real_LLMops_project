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

    def test_reported_used_evidence_must_be_cited_even_when_outside_item_candidates(self):
        value, bodies, raw = candidate_fixture()
        raw["checks"][0]["evidence_ids"].append("E00001")
        report = checked_review(raw, value, bodies)
        self.assertFalse(report["approved"])
        self.assertEqual(report["checks"][0]["missing_body_evidence_ids"], ["E00001"])
        # Section/subsection allocation remains the boundary, not the item pool.
        value["sections"][0]["evidence_ids"].append("OTHER")
        raw["checks"][0]["evidence_ids"] = ["OTHER"]
        report = checked_review(raw, value, bodies)
        self.assertFalse(report["approved"])
        self.assertEqual(report["checks"][0]["missing_body_evidence_ids"], ["OTHER"])
        self.assertEqual(report["checks"][0]["missing_section_evidence_ids"], ["OTHER"])
        self.assertEqual(report["checks"][0]["failure_owner"], "writer")
        bodies["s0"] += "\n\n별도로 배정된 승인 근거로 내용을 설명한다. [근거:OTHER]"
        raw["checks"][0]["paragraph_ids"].append("s0_p2")
        report = checked_review(raw, value, bodies)
        self.assertTrue(report["approved"])
        self.assertEqual(report["checks"][0]["used_non_candidate_evidence_ids"], ["OTHER"])

    def test_candidate_membership_does_not_bypass_section_or_paragraph_boundaries(self):
        value, bodies, raw = candidate_fixture()
        for eid in ("UNKNOWN", "F1"):
            with self.subTest(evidence_id=eid):
                raw["checks"][0]["evidence_ids"] = [eid]
                with self.assertRaisesRegex(ValueError, "해당 장에 없는 근거"):
                    checked_review(raw, value, bodies)
        value["sections"][0]["evidence_ids"].append("OTHER")
        bodies["s0"] += "\n\n사용된 다른 승인 근거다. [근거:OTHER]"
        raw["checks"][0]["evidence_ids"] = ["OTHER"]
        report = checked_review(raw, value, bodies)
        self.assertFalse(report["approved"])
        self.assertEqual(report["checks"][0]["unselected_cited_evidence_ids"], ["OTHER"])
        self.assertEqual(report["checks"][0]["failure_owner"], "reviewer")
        raw["checks"][0]["paragraph_ids"] = ["s1_p1"]
        with self.assertRaisesRegex(ValueError, "없는 초안 문단"):
            checked_review(raw, value, bodies)

    def test_semantic_findings_are_preserved_when_reported_evidence_is_outside_candidates(self):
        value, bodies, raw = candidate_fixture()
        value["sections"][0]["evidence_ids"].append("OTHER")
        bodies["s0"] = "잘못 확대하여 쓴 주장이다. [근거:OTHER]"
        raw["checks"][0]["evidence_ids"] = ["OTHER"]
        raw["issues"] = [{"section_id": "s0", "paragraph_id": "s0_p1", "severity": "error",
                          "reason": "관찰을 검증 완료로 확대했다.", "evidence_ids": ["OTHER"]}]
        report = checked_review(raw, value, bodies)
        self.assertFalse(report["approved"])
        self.assertEqual(report["checks"][0]["verdict"], "met")
        self.assertEqual(report["issues"][0]["reason"], raw["issues"][0]["reason"])
        raw["issues"] = []
        raw["checks"][0]["verdict"] = "missing"
        self.assertFalse(checked_review(raw, value, bodies)["approved"])

    def test_empty_candidate_pool_can_use_actual_assigned_cited_support(self):
        value, bodies, raw = candidate_fixture()
        value["sections"][0]["required_items"][0]["evidence_ids"] = []
        report = checked_review(raw, value, bodies)
        self.assertTrue(report["approved"])
        self.assertEqual(report["required_content_coverage"]["total"], 2)
        from editorial_review import checked_editorial_review
        inherited = checked_editorial_review({"issues": []}, value, bodies, {"leaf": report})
        self.assertEqual(inherited["required_content_coverage"]["total"], 2)

    def test_diagnostics_include_missing_used_evidence_outside_item_candidates(self):
        from draft_diagnostics import review_diagnostics
        value = plan(2)
        bodies = {sid: "배정된 근거의 설명이다. [근거:F1]" for sid in ("s0", "s1")}
        raw = {"checks": [{"item_id": f"item{i}", "verdict": "met", "paragraph_ids": [f"s{i}_p1"],
                            "evidence_ids": ["F2"] if i == 0 else ["F1"]} for i in range(2)],
               "issues": [], "reference_checks": []}
        report = checked_review(raw, value, bodies)
        details = review_diagnostics("subsection-s0-p0", value, research(), bodies, report)
        evidence = {row["id"]: row for row in details["items"][0]["evidence"]}
        self.assertTrue(evidence["F2"]["outside_item_candidates"])
        self.assertTrue(evidence["F2"]["missing_body"])
        self.assertEqual(details["items"][0]["planned_evidence_count"], 1)
        self.assertEqual(details["items"][0]["unused_candidate_count"], 0)

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

    def test_runtime_accepts_actually_used_non_candidate_fact_without_repair_or_rewriting(self):
        client = Client()
        def response(system, packet, schema, path):
            raw = client(system, packet, schema, path)
            if path.parent.parent.name == "subsection-s0-p0":
                if "parts" in schema["properties"]:
                    raw["parts"]["p0"] = "소절에 배정된 다른 승인 근거로 내용을 설명한다. [근거:F2]"
                elif "checks" in schema["properties"]:
                    raw["checks"][0].update(evidence_ids=["F2"], paragraph_ids=list(packet["draft_paragraphs"]))
            return raw
        with TemporaryDirectory() as tmp:
            result = PlannedPaper(tmp, response).run(research())
            self.assertTrue(result["review"]["approved"])
            self.assertEqual([kind for stage, kind, _ in client.events if stage == "subsection-s0-p0"], ["generate", "review"])
            check = next(c for c in result["review"]["checks"] if c["item_id"] == "item0")
            self.assertEqual(check["used_non_candidate_evidence_ids"], ["F2"])
            self.assertEqual(check["unused_candidate_evidence_ids"], ["F1"])

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

    def test_coverage_keeps_body_and_criteria_without_resending_fact_records(self):
        from test_drafting_budget import fixture
        data, _, _, _, packet = fixture()
        original = copy.deepcopy(packet)
        scoped = _coverage_packet(packet, {})
        self.assertNotIn("facts", scoped["research"])
        self.assertNotIn("tables", scoped["research"])
        self.assertEqual(scoped["draft_paragraphs"], packet["draft_paragraphs"])
        self.assertEqual(scoped["plan"]["sections"][0]["required_items"], packet["plan"]["sections"][0]["required_items"])
        self.assertEqual(packet, original)


if __name__ == "__main__":
    unittest.main()
