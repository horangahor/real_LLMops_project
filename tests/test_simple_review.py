import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from bounded_review import approved_review_packet, review_bounded
from editorial_review import checked_editorial_review, review_editorial
from planned_paper import PlannedPaper, fingerprint, index_paragraphs, review_schema
from test_hierarchical_drafting import Client
from test_planned_paper import plan, research


class SimpleReviewTests(unittest.TestCase):
    def test_runtime_roles_get_only_the_data_they_review_and_never_call_findings_or_link_agents(self):
        data = research()
        data["facts"][0]["sources"] = [{"element_id": "p1:e1", "page": 1, "quote": "RAW_SOURCE_NOT_FOR_DRAFT_REVIEW"}]
        data["facts"][0].update(conditions=["같은 입력"], evidence_limitations=["관찰 범위"], support="supported")
        client, requests = Client(), []
        def response(system, packet, schema, path):
            requests.append((system, copy.deepcopy(packet), copy.deepcopy(schema)))
            return client(system, packet, schema, path)
        with TemporaryDirectory() as tmp, patch("review_findings.verify_findings", side_effect=AssertionError("removed adjudication")), \
                patch("citation_repair.repair_leaf_citations", side_effect=AssertionError("removed link agent")):
            result = PlannedPaper(tmp, response).run(data)
            self.assertTrue(result["review"]["approved"])
            self.assertEqual(result["review"]["review_kind"], "editorial")
            self.assertFalse(result["review"]["required_content_coverage"]["rechecked"])
        leaves = [p for _, p, s in requests if "checks" in s["properties"]]
        editors = [p for _, p, _ in requests if p.get("operation") == "editorial_review"]
        self.assertEqual(len(leaves), 4)
        self.assertEqual(len(editors), 4)
        for packet in leaves:
            self.assertNotIn("RAW_SOURCE_NOT_FOR_DRAFT_REVIEW", json.dumps(packet))
            self.assertNotIn("source_elements", packet)
            self.assertNotIn("section_packets", packet)
            for fact in packet["research"]["facts"]:
                self.assertNotIn("sources", fact)
                self.assertIn("statement", fact)
                self.assertIn("limits", fact)
        for packet in editors:
            self.assertEqual(set(packet), {"operation", "workflow_stage", "outline", "draft_paragraphs"})
        self.assertFalse(any(p.get("operation") in ("repair_review_selection", "verify_review_findings") for _, p, _ in requests))

    def test_editorial_rejection_revises_only_editor_and_does_not_repeat_subsection_review(self):
        client = Client()
        client.reject_once = "section-s1"
        with TemporaryDirectory() as tmp:
            result = PlannedPaper(tmp, client).run(research())
            self.assertTrue(result["review"]["approved"])
        counts = [(s, k) for s, k, _ in client.events]
        self.assertEqual(counts.count(("section-s1", "generate")), 2)
        self.assertEqual(counts.count(("section-s1", "review")), 2)
        self.assertEqual(counts.count(("subsection-s1-p0", "review")), 1)
        revision = next(p["revision"] for s, k, p in client.events if s == "section-s1" and k == "generate" and "revision" in p)
        self.assertEqual(revision["review"]["checks"], [])
        self.assertNotIn("evidence_link_gaps", revision)

    def test_legacy_approved_editor_body_is_reused_but_reviewed_under_editorial_policy(self):
        client = Client()
        with TemporaryDirectory() as tmp:
            engine = PlannedPaper(tmp, client)
            first = engine.run(research())
            root = Path(first["run_dir"]) / "workflow/section-s0"
            path = root / "approved.json"
            saved = json.loads(path.read_text(encoding="utf-8"))
            body = copy.deepcopy(saved["value"]["sections"])
            saved["value"]["raw_review"] = {"checks": [], "reference_checks": [], "issues": []}
            saved["sha256"] = fingerprint(saved["value"])
            path.write_text(json.dumps(saved), encoding="utf-8")
            before = len(client.events)
            result = engine.run(research())
            self.assertTrue(result["review"]["approved"])
            self.assertEqual([(s, k) for s, k, _ in client.events[before:]], [("section-s0", "review")])
            updated = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(updated["value"]["sections"], body)
            self.assertEqual(updated["value"]["raw_review"]["review_policy"], "editorial-v1")
            self.assertTrue((root / "checkpoint-history" / f"approved-{saved['sha256']}.json").is_file())

    def test_editorial_bad_paragraph_id_repairs_report_without_writing_body_or_reading_evidence(self):
        value = plan(2)
        bodies = {"s0": "연결할 문단이다. [근거:F1]", "s1": "결론 문단이다. [근거:F1]"}
        calls = []
        def client(system, packet, schema, path):
            calls.append(packet)
            self.assertNotIn("research", packet)
            return {"issues": [{"section_id": "s0", "paragraph_id": "unknown", "category": "flow", "severity": "error", "reason": "연결"}]} if len(calls) == 1 else {"issues": []}
        with TemporaryDirectory() as tmp:
            _, report = review_editorial(PlannedPaper(tmp, client), Path(tmp), "review", "paper", value, bodies, {})
            self.assertTrue(report["approved"])
            self.assertEqual(len(calls), 2)
            self.assertIn("invalid_review", calls[1])

    def test_editorial_output_cannot_request_a_source_verification_category(self):
        value = plan(2)
        raw = {"issues": [{"section_id": "s0", "paragraph_id": "s0_p1", "category": "hallucination", "severity": "error", "reason": "원문 검토"}]}
        with self.assertRaisesRegex(ValueError, "문제 유형"):
            checked_editorial_review(raw, value, {"s0": "본문", "s1": "결론"}, {})

    def test_editorial_windows_cover_all_paragraphs_and_all_adjacent_pairs_without_evidence(self):
        value = plan(2)
        bodies = {sid: "\n\n".join((f"문단 {i} " + "설명 " * 270 + "[근거:F1]") for i in range(9)) for sid in ("s0", "s1")}
        all_ids = list(index_paragraphs(bodies))
        seen = []
        def client(system, packet, schema, path):
            seen.append(list(packet["draft_paragraphs"]))
            self.assertNotIn("facts", packet)
            return {"issues": []}
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {"PAPER_REQUEST_MAX_BYTES": "12000"}):
            _, report = review_editorial(PlannedPaper(tmp, client), Path(tmp), "review", "paper", value, bodies, {})
            self.assertTrue(report["approved"])
        self.assertGreater(len(seen), 1)
        self.assertEqual({pid for batch in seen for pid in batch}, set(all_ids))
        self.assertTrue(set(zip(all_ids, all_ids[1:])) <= {pair for batch in seen for pair in zip(batch, batch[1:])})

    def test_old_source_quote_failure_cache_is_not_read_by_new_approved_fact_review(self):
        data, value = research(), plan(2)
        data["facts"][0]["sources"] = [{"page": 1, "quote": "LEGACY_RAW_QUOTE"}]
        bodies = {sid: "승인된 근거를 설명한다. [근거:F1]" for sid in ("s0", "s1")}
        packet = {"research": data, "plan": value, "draft_paragraphs": index_paragraphs(bodies), "reference_guides": {}}
        raw = {"checks": [{"item_id": f"item{i}", "verdict": "met", "paragraph_ids": [f"s{i}_p1"], "evidence_ids": ["F1"]} for i in range(2)], "reference_checks": [], "issues": []}
        calls = []
        def client(system, request, schema, path):
            calls.append(request)
            return copy.deepcopy(raw)
        with TemporaryDirectory() as tmp, patch("review_findings.verify_findings", side_effect=AssertionError("must not run")):
            engine = PlannedPaper(tmp, client)
            schema = review_schema(value, packet["draft_paragraphs"])
            engine.call(Path(tmp), "review", "old source system", packet, schema)
            _, report = review_bounded(engine, Path(tmp), "review", "old source system", packet, schema, value, bodies)
            self.assertTrue(report["approved"])
            self.assertEqual(report["review_policy"], "approved-facts-v1")
            self.assertEqual(len(calls), 2)
            self.assertNotIn("LEGACY_RAW_QUOTE", json.dumps(calls[-1]))
            before = len(calls)
            review_bounded(engine, Path(tmp), "review", "old source system", packet, schema, value, bodies)
            self.assertEqual(len(calls), before)


if __name__ == "__main__":
    unittest.main()
