import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from content_review_completion import POLICY, finish_content_review, reconcile_generation_warnings
from planned_paper import PlannedPaper, load_latest
from test_hierarchical_drafting import Client
from test_planned_paper import research


class ContentWarningTests(unittest.TestCase):
    def report(self):
        return {"approved": False, "issues": [{"section_id": "s0", "paragraph_id": "s0_p1",
            "severity": "error", "reason": "원래 지적", "evidence_ids": ["F1"], "failure_owner": "writer"}],
            "checks": [{"item_id": "item", "verdict": "missing"}],
            "required_content_coverage": {"met": 0, "total": 1, "value": 0}}

    def completion(self, revisions=2):
        return {"policy": POLICY, "status": "needs_attention", "revisions": revisions, "reason": "revision_limit"}

    def test_only_exhaustion_defers_errors_without_falsifying_coverage_or_mutating_original(self):
        report = self.report()
        original = copy.deepcopy(report)
        self.assertEqual(finish_content_review(report, "leaf"), original)
        result = finish_content_review(report, "leaf", self.completion())
        self.assertEqual(report, original)
        self.assertTrue(result["approved"])
        self.assertFalse(result["content_approved"])
        self.assertEqual(result["checks"], original["checks"])
        self.assertEqual(result["required_content_coverage"]["value"], 0)
        self.assertEqual(result["content_warnings"][0]["stage"], "leaf")
        self.assertEqual(result["content_warnings"][0]["reason"], "원래 지적")
        self.assertEqual(result["content_warnings"][0]["original_severity"], "error")

    def test_completion_cannot_skip_revision_opportunities_or_defer_reviewer_format_errors(self):
        for revisions in (0, 1, True, "2"):
            with self.subTest(revisions=revisions), self.assertRaises(ValueError):
                finish_content_review(self.report(), "leaf", self.completion(revisions))
        report = self.report()
        report["issues"][0]["failure_owner"] = "reviewer"
        with self.assertRaisesRegex(ValueError, "경고로 전환할 수 없습니다"):
            finish_content_review(report, "leaf", self.completion())

    def test_warning_summary_survives_parent_interruption_and_resume_without_duplicate_findings(self):
        with TemporaryDirectory() as tmp:
            client = Client()
            client.reject = "subsection-s1-p1"
            client.fail_once = "section-s1"
            engine = PlannedPaper(tmp, client)
            with self.assertRaisesRegex(RuntimeError, "test interruption"):
                engine.run(research())
            summary_path = next(Path(tmp).glob("draft_history/planned/*/*/review-warnings.json"))
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["warning_count"], 1)
            snapshot = summary["stages"][0]
            self.assertEqual(snapshot["stage"], "subsection-s1-p1")
            self.assertEqual(snapshot["evidence"][0]["id"], "F2")
            self.assertTrue(Path(snapshot["review_path"]).is_file())
            before = len(client.events)
            result = engine.run(research())
            self.assertFalse(any(s == "subsection-s1-p1" for s, _, _ in client.events[before:]))
            self.assertEqual(result["review_warnings"]["warning_count"], 1)
            self.assertEqual(len(result["review"]["content_warnings"]), 1)
            self.assertEqual(result["metrics"]["content_warnings"], 1)
            self.assertEqual(load_latest(tmp)["review_warnings"], result["review_warnings"])
            checkpoint = json.loads(Path(snapshot["checkpoint_path"]).read_text(encoding="utf-8"))["value"]
            self.assertEqual(checkpoint["raw_review"]["issues"][0]["severity"], "error")
            self.assertEqual(checkpoint["content_completion"]["revisions"], 2)

    def test_resolved_after_revision_does_not_leave_stale_warnings(self):
        with TemporaryDirectory() as tmp:
            client = Client()
            client.reject_once = "subsection-s1-p1"
            result = PlannedPaper(tmp, client).run(research())
            self.assertEqual(result["review_warnings"]["warning_count"], 0)
            self.assertEqual(result["review"]["content_warnings"], [])
            self.assertTrue(result["review"]["content_approved"])

    def test_reload_uses_completed_review_snapshot_instead_of_later_progress_summary(self):
        with TemporaryDirectory() as tmp:
            client = Client()
            client.reject = "subsection-s1-p1"
            result = PlannedPaper(tmp, client).run(research())
            path = Path(result["run_dir"]) / "review-warnings.json"
            path.write_text(json.dumps({"warning_count": 0, "stages": []}), encoding="utf-8")
            self.assertEqual(load_latest(tmp)["review_warnings"], result["review_warnings"])

    def test_fragment_gap_reaches_final_summary_and_reuses_checkpoint_without_falsifying_missing_check(self):
        from drafting_budget import fits_request
        client = Client()
        client.plan["sections"][0]["required_items"][0]["evidence_ids"] = ["F1", "F2"]
        fragments = []
        def response(system, request, schema, path):
            result = client(system, request, schema, path)
            if path.parent.parent.name == "subsection-s0-p0" and "parts" in schema["properties"]:
                result["parts"]["p0"] = [{"text": "원래 근거만 쓴 본문이다.", "evidence_ids": ["F1"]}]
                if request.get("fragment", {}).get("operation") == "missing_evidence":
                    fragments.append(copy.deepcopy(request))
            return result
        def split_revisions(system, packet, schema):
            if packet.get("workflow_stage") == "subsection" and packet.get("revision", {}).get("previous_sections"):
                return False
            return fits_request(system, packet, schema)
        with TemporaryDirectory() as tmp, patch("bounded_drafting.fits_request", side_effect=split_revisions):
            engine = PlannedPaper(tmp, response)
            result = engine.run(research())
            warnings = [i for i in result["review"]["content_warnings"] if i.get("validation_code") == "fragment_missing_evidence"]
            self.assertEqual(len(warnings), 1)
            self.assertEqual(warnings[0]["evidence_ids"], ["F2"])
            self.assertEqual(warnings[0]["generation_request"], "generate-2")
            self.assertEqual(len(fragments), 4)  # Two revisions, each with one local correction.
            self.assertFalse(result["review"]["content_approved"])
            self.assertEqual(next(c for c in result["review"]["checks"] if c["item_id"] == "item0")["verdict"], "missing")
            summary = next(s for s in result["review_warnings"]["stages"] if s["stage"] == "subsection-s0-p0")
            self.assertEqual({f["id"] for f in summary["evidence"]}, {"F1", "F2"})
            saved = json.loads(Path(summary["checkpoint_path"]).read_text(encoding="utf-8"))["value"]
            self.assertEqual(saved["generation_warnings"][0]["evidence_ids"], ["F2"])
            before = len(client.events)
            again = engine.run(research())
            self.assertEqual(len(client.events), before)
            self.assertEqual(again["review_warnings"], result["review_warnings"])

    def test_fragment_warnings_are_cleared_when_later_body_cites_gap_and_reject_out_of_scope_ids(self):
        packet = {"section_plan": {"evidence_ids": ["F1", "F2"]}}
        warning = {"section_id": "s0", "part": "p0", "evidence_ids": ["F2"], "fragment_batch": "missing-0",
                   "repair_attempts": 1, "validation_code": "fragment_missing_evidence"}
        self.assertEqual(reconcile_generation_warnings([warning],
            {"s0": {"parts": {"p0": "보완한 본문 [근거:F1,F2]"}}}, {"s0": packet}), [])
        warning["evidence_ids"] = ["UNKNOWN"]
        with self.assertRaises(ValueError):
            reconcile_generation_warnings([warning], {"s0": {"parts": {"p0": "본문 [근거:F1]"}}}, {"s0": packet})


if __name__ == "__main__":
    unittest.main()
