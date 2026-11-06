import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from bounded_review import finalize_review
from content_review_completion import finish_review_links
from planned_paper import PlannedPaper
from review_response import checked_review
from test_hierarchical_drafting import Client
from test_planned_paper import plan, research


def fixture():
    value = plan(2)
    bodies = {"s0": "조건을 유지해 관측했다. [근거:F1]\n\n관측값은 12였다. [근거:F2]",
              "s1": "관측 범위의 결론이다. [근거:F1]"}
    raw = {"checks": [{"item_id": "item0", "verdict": "met", "paragraph_ids": [], "evidence_ids": []},
                      {"item_id": "item1", "verdict": "met", "paragraph_ids": ["s1_p1"], "evidence_ids": ["F1"]}],
           "reference_checks": [], "issues": []}
    return value, bodies, raw


def reply(request, verdict="met", invalid=None):
    item = request["plan"]["sections"][0]["required_items"][0]["id"]
    return {"checks": {item: {"verdict": verdict, "paragraph_ids": [invalid or "s0_p1"], "evidence_ids": ["F1"]}},
            "reference_checks": {}, "issues": []}


class ReviewLinkCompletionTests(unittest.TestCase):
    def test_empty_review_does_not_label_all_body_citations_as_missing(self):
        value, bodies, raw = fixture()
        report = checked_review(raw, value, bodies)
        self.assertEqual(report["checks"][0]["missing_review_evidence_ids"], [])
        self.assertEqual(report["checks"][0]["missing_section_evidence_ids"], [])
        self.assertEqual(report["issues"][0]["evidence_ids"], [])
        self.assertIn("검토 연결 미완료", report["issues"][0]["reason"])
        self.assertNotIn("누락 근거", report["issues"][0]["reason"])

    def test_correction_targets_only_incomplete_item_preserves_body_and_reuses_cache(self):
        value, bodies, raw = fixture()
        original = copy.deepcopy((value, bodies, raw))
        calls = []
        def client(system, request, schema, path):
            calls.append(request)
            self.assertEqual(list(schema["properties"]["checks"]["properties"]), ["item0"])
            self.assertNotIn("facts", request["research"])
            self.assertEqual(set(request["draft_paragraphs"]), {"s0_p1", "s0_p2"})
            self.assertEqual(request["draft_paragraphs"]["s0_p1"]["text"], bodies["s0"].split("\n\n")[0])
            return reply(request)
        with TemporaryDirectory() as tmp:
            engine = PlannedPaper(tmp, client)
            for _ in range(2):
                result, report = finalize_review(engine, Path(tmp), "review-0", raw,
                    checked_review(raw, value, bodies), value, research(), bodies)
                self.assertTrue(report["approved"])
                self.assertEqual(report["checks"][0]["verdict"], "met")
                self.assertNotIn("review_link_completion", report)
                self.assertEqual(result["checks"][1], raw["checks"][1])
        self.assertEqual(len(calls), 1)
        self.assertEqual((value, bodies, raw), original)

    def test_repeated_empty_selection_is_warning_without_falsifying_coverage(self):
        value, bodies, raw = fixture()
        calls = []
        def client(system, request, schema, path):
            calls.append(request)
            return {"checks": [copy.deepcopy(raw["checks"][0])], "reference_checks": [], "issues": []}
        with TemporaryDirectory() as tmp:
            result, report = finalize_review(PlannedPaper(tmp, client), Path(tmp), "review-0", raw,
                checked_review(raw, value, bodies), value, research(), bodies)
            self.assertEqual(len(calls), 1)
            self.assertTrue(report["approved"])
            self.assertEqual(report["required_content_coverage"]["met"], 1)
            self.assertEqual(report["checks"][0]["verdict"], "missing")
            self.assertEqual(report["checks"][0]["review_status"], "incomplete")
            self.assertEqual(report["issues"][0]["validation_code"], "review_link_incomplete")
            self.assertEqual(report["issues"][0]["severity"], "warning")
            replay = finish_review_links(checked_review(result, value, bodies), report["review_link_completion"])
            self.assertEqual(replay, report)

    def test_reviewer_admitting_needs_check_is_not_turned_into_content_approval(self):
        value, bodies, raw = fixture()
        with TemporaryDirectory() as tmp:
            _, report = finalize_review(PlannedPaper(tmp, lambda s, r, sc, p: reply(r, "needs_check")),
                Path(tmp), "review-0", raw, checked_review(raw, value, bodies), value, research(), bodies)
        self.assertEqual(report["checks"][0]["review_status"], "incomplete")
        self.assertEqual(report["required_content_coverage"]["value"], .5)

    def test_unknown_or_other_section_paragraphs_still_fail_after_format_correction(self):
        value, bodies, raw = fixture()
        for invalid in ("UNKNOWN", "s1_p1"):
            with self.subTest(invalid=invalid), TemporaryDirectory() as tmp:
                with self.assertRaisesRegex(ValueError, "해당 장에 없는"):
                    finalize_review(PlannedPaper(tmp, lambda s, r, sc, p: reply(r, invalid=invalid)),
                        Path(tmp), "review-0", raw, checked_review(raw, value, bodies), value, research(), bodies)

    def test_semantic_errors_are_preserved_when_reviewer_metadata_is_deferred(self):
        value, bodies, raw = fixture()
        raw["issues"] = [{"section_id": "s0", "paragraph_id": "s0_p1", "severity": "error",
                          "reason": "관측을 입증된 성과로 확대했다.", "evidence_ids": ["F1"]}]
        with TemporaryDirectory() as tmp:
            _, report = finalize_review(PlannedPaper(tmp, lambda *args: {
                "checks": [copy.deepcopy(raw["checks"][0])], "issues": [], "reference_checks": []}),
                Path(tmp), "review-0", raw, checked_review(raw, value, bodies), value, research(), bodies)
        self.assertFalse(report["approved"])
        self.assertEqual(report["issues"][0]["reason"], raw["issues"][0]["reason"])
        self.assertEqual(report["issues"][0]["severity"], "error")
        self.assertEqual(report["issues"][1]["severity"], "warning")

    def test_oversized_review_correction_defers_without_slicing_body_or_api_call(self):
        value, bodies, raw = fixture()
        bodies["s0"] = "조건·한계를 보존한다. " * 500 + "[근거:F1]"
        def client(*args):
            raise AssertionError("Oversized inputs must not be sent")
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {"PAPER_REQUEST_MAX_BYTES": "4000"}):
            _, report = finalize_review(PlannedPaper(tmp, client), Path(tmp), "review-0", raw,
                checked_review(raw, value, bodies), value, research(), bodies)
        self.assertEqual(report["review_link_completion"]["attempts"], 0)
        self.assertEqual(report["review_link_completion"]["reason"], "input_budget")
        self.assertTrue(report["approved"])

    def test_warning_checkpoint_resumes_without_review_or_writer_calls(self):
        client, repair_calls = Client(), []
        target = "subsection-s0-p0"
        def respond(system, request, schema, path):
            raw = client(system, request, schema, path)
            if path.parent.parent.name == target and "checks" in schema["properties"]:
                if request.get("review_link_repair"):
                    repair_calls.append(request)
                for check in raw["checks"]:
                    check.update(paragraph_ids=[], evidence_ids=[])
            return raw
        with TemporaryDirectory() as tmp:
            engine = PlannedPaper(tmp, respond)
            result = engine.run(research())
            self.assertEqual(len(repair_calls), 1)
            events = [(stage, kind) for stage, kind, _ in client.events if stage == target]
            self.assertEqual(events.count((target, "generate")), 1)
            self.assertEqual(events.count((target, "review")), 2)
            self.assertEqual(result["review_warnings"]["warning_count"], 1)
            self.assertFalse(result["review"]["content_approved"])
            root = Path(result["run_dir"])
            checkpoint = json.loads((root / "workflow" / target / "approved.json").read_bytes())["value"]
            self.assertEqual(checkpoint["review_link_completion"]["attempts"], 1)
            self.assertEqual(checkpoint["raw_review"]["checks"][0]["evidence_ids"], [])
            count = len(client.events)
            again = engine.run(research())
            self.assertEqual(len(client.events), count)
            self.assertEqual(again["draft_markdown"], result["draft_markdown"])
            self.assertEqual(again["review_warnings"]["warning_count"], 1)


if __name__ == "__main__":
    unittest.main()
