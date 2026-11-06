import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from editorial_review import checked_editorial_review
from planned_paper import PlannedPaper, index_paragraphs, review_schema
from review_response import checked_review, review_with_repair
from test_hierarchical_drafting import Client
from test_planned_paper import plan, research


def fixture():
    value = plan(2)
    value["sections"][0].update(reference_ids=["guide"], reference_adaptation="구성 기준을 연구에 적용한다.")
    bodies = {"s0": "관측과 한계를 설명했다. [근거:F1]", "s1": "결론의 적용 범위다. [근거:F1]"}
    raw = {"checks": [{"item_id": f"item{i}", "verdict": "met", "paragraph_ids": [f"s{i}_p1"], "evidence_ids": ["F1"]}
                      for i in range(2)], "issues": [], "reference_checks": [
        {"section_id": "s0", "reference_id": "guide", "verdict": "partial", "paragraph_ids": [], "reason": "일부 기준은 반영되지 않았다."}]}
    packet = {"research": research(), "plan": value, "draft_paragraphs": index_paragraphs(bodies),
              "reference_guides": {}, "review_policy": "approved-facts-v1", "coverage_policy": "content-coverage-v2"}
    return value, bodies, raw, packet


class ReferenceLinkCompletionTests(unittest.TestCase):
    def test_repeated_empty_guide_selection_defers_only_after_correction_and_reuses_raw_cache(self):
        value, bodies, raw, packet = fixture()
        original, calls = copy.deepcopy((value, bodies, raw)), []
        def client(system, request, schema, path):
            calls.append(request)
            return copy.deepcopy(raw)
        with TemporaryDirectory() as tmp:
            engine = PlannedPaper(tmp, client)
            result, report = review_with_repair(engine, Path(tmp), "review", "reviewer", packet,
                review_schema(value, packet["draft_paragraphs"]), value, bodies)
            self.assertEqual(len(calls), 2)
            self.assertTrue(report["approved"])
            self.assertEqual(report["reference_application"]["partial"], 0)
            self.assertEqual(report["reference_application"]["not_visible"], 0)
            self.assertEqual(report["reference_application"]["incomplete"], 1)
            check = report["reference_checks"][0]
            self.assertEqual(check["model_verdict"], "partial")
            self.assertEqual(check["review_status"], "incomplete")
            self.assertEqual(check["reason"], raw["reference_checks"][0]["reason"])
            self.assertEqual(report["issues"][0]["validation_code"], "reference_link_incomplete")
            self.assertEqual(report["issues"][0]["repair_attempts"], 1)
            self.assertEqual(checked_review(result, value, bodies), report)
            saved = {p: p.read_bytes() for p in (Path(tmp) / "responses").glob("*.json")}
            again = review_with_repair(engine, Path(tmp), "review", "reviewer", packet,
                review_schema(value, packet["draft_paragraphs"]), value, bodies)
            self.assertEqual(again, (result, report))
            self.assertEqual(len(calls), 2)
            self.assertTrue(all(p.read_bytes() == data for p, data in saved.items()))
        self.assertEqual((value, bodies, raw), original)

    def test_successful_correction_keeps_confirmed_guide_judgment_without_warning(self):
        value, bodies, raw, packet = fixture()
        calls = []
        def client(*args):
            calls.append(1)
            result = copy.deepcopy(raw)
            if len(calls) == 2:
                result["reference_checks"][0]["paragraph_ids"] = ["s0_p1"]
            return result
        with TemporaryDirectory() as tmp:
            _, report = review_with_repair(PlannedPaper(tmp, client), Path(tmp), "review", "reviewer", packet,
                review_schema(value, packet["draft_paragraphs"]), value, bodies)
        self.assertEqual(report["reference_application"]["partial"], 1)
        self.assertFalse(report["issues"])

    def test_empty_selection_never_hides_other_invalid_ids_or_missing_review_rows(self):
        value, bodies, good, packet = fixture()
        mutations = [lambda r: r["reference_checks"][0].update(reference_id="UNKNOWN"),
                     lambda r: r["reference_checks"][0].update(paragraph_ids=["UNKNOWN"]),
                     lambda r: r["reference_checks"][0].update(paragraph_ids=["s1_p1"]),
                     lambda r: r["checks"][0].update(evidence_ids=["UNKNOWN"]),
                     lambda r: r["checks"].pop(),
                     lambda r: r["issues"].append({"section_id": "s0", "paragraph_id": "s0_p1", "severity": "error",
                                                  "reason": "유효하지 않은 연결", "evidence_ids": ["UNKNOWN"]})]
        for mutate in mutations:
            raw = copy.deepcopy(good)
            mutate(raw)
            with self.subTest(mutation=mutate), TemporaryDirectory() as tmp:
                with self.assertRaises(ValueError):
                    review_with_repair(PlannedPaper(tmp, lambda *args: copy.deepcopy(raw)), Path(tmp), "review", "reviewer", packet,
                        review_schema(value, packet["draft_paragraphs"]), value, bodies)

    def test_semantic_errors_remain_blocking_and_incomplete_guide_is_inherited(self):
        value, bodies, raw, packet = fixture()
        raw["issues"] = [{"section_id": "s0", "paragraph_id": "s0_p1", "severity": "error",
                          "reason": "관측을 확정된 성과로 확대했다.", "evidence_ids": ["F1"]}]
        with TemporaryDirectory() as tmp:
            _, report = review_with_repair(PlannedPaper(tmp, lambda *args: copy.deepcopy(raw)), Path(tmp), "review", "reviewer", packet,
                review_schema(value, packet["draft_paragraphs"]), value, bodies)
        self.assertFalse(report["approved"])
        self.assertEqual(report["issues"][0]["severity"], "error")
        inherited = checked_editorial_review({"issues": []}, value, bodies, {"leaf": report})
        self.assertEqual(inherited["reference_application"]["incomplete"], 1)
        self.assertEqual(inherited["reference_application"]["partial"], 0)

    def test_full_pipeline_preserves_warning_and_resumes_checkpoint_without_rewriting(self):
        client = Client()
        client.plan["sections"][0].update(reference_ids=["ref1_introduction"], reference_adaptation="연구 배경의 구성을 적용한다.")
        reference = {"profiles": [{"observed_outline": [], "style_rules": [], "not_to_transfer": [],
                                  "section_guidelines": [{"role": "introduction", "purpose": "연구 배경 구성",
                                    "required_content": ["연구 배경"], "paragraph_flow": [], "figures_tables": []}]}]}
        def respond(system, packet, schema, path):
            raw = client(system, packet, schema, path)
            if "checks" in schema["properties"]:
                raw["reference_checks"] = [{"section_id": s["id"], "reference_id": ref, "verdict": "partial",
                    "paragraph_ids": [], "reason": "일부 기준의 반영 연결을 확인하지 못했다."}
                    for s in packet["plan"]["sections"] for ref in s["reference_ids"]]
            return raw
        with TemporaryDirectory() as tmp:
            engine = PlannedPaper(tmp, respond)
            result = engine.run(research(), reference)
            self.assertFalse(result["review"]["content_approved"])
            self.assertEqual(result["review_warnings"]["warning_count"], 1)
            self.assertEqual(result["review"]["reference_application"]["incomplete"], 1)
            events = [(s, k) for s, k, _ in client.events if s == "subsection-s0-p0"]
            self.assertEqual(events.count(("subsection-s0-p0", "generate")), 1)
            self.assertEqual(events.count(("subsection-s0-p0", "review")), 2)
            root = Path(result["run_dir"])
            checkpoint = json.loads((root / "workflow/subsection-s0-p0/approved.json").read_bytes())["value"]
            self.assertEqual(checkpoint["raw_review"]["reference_checks"][0]["model_verdict"], "partial")
            self.assertTrue((root / "workflow/subsection-s0-p0/review-0-reference-link-completion-v1.json").is_file())
            before = len(client.events)
            again = engine.run(research(), reference)
            self.assertEqual(len(client.events), before)
            self.assertEqual(again["review_warnings"]["warning_count"], 1)
            self.assertEqual(again["draft_markdown"], result["draft_markdown"])


if __name__ == "__main__":
    unittest.main()
