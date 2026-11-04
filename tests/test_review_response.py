import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from planned_paper import PlannedPaper, index_paragraphs, review_schema
from review_response import checked_review, correction_schema, normalize_review_response
from test_hierarchical_drafting import Client
from test_planned_paper import plan, research


class ReviewResponseTests(unittest.TestCase):
    def test_only_exact_duplicate_rows_are_removed_in_first_seen_order(self):
        check = {"item_id": "item0", "verdict": "met", "paragraph_ids": ["s0_p1"], "evidence_ids": ["F1"]}
        second = {**check, "item_id": "item1"}
        ref = {"section_id": "s0", "reference_id": "g", "verdict": "applied",
               "paragraph_ids": ["s0_p1"], "reason": "본문에 적용됨"}
        raw = {"checks": [check, second, copy.deepcopy(check)], "reference_checks": [ref, copy.deepcopy(ref)], "issues": []}
        original = copy.deepcopy(raw)
        result = normalize_review_response(raw)
        self.assertEqual(raw, original)
        self.assertEqual(result["checks"], [check, second])
        self.assertEqual(result["reference_checks"], [ref])
        self.assertEqual(result["response_normalizations"], [
            {"field": "checks", "item_id": "item0", "removed_index": 2},
            {"field": "reference_checks", "section_id": "s0", "reference_id": "g", "removed_index": 1}])

    def test_conflicting_verdicts_evidence_or_paragraphs_are_never_collapsed(self):
        check = {"item_id": "item0", "verdict": "met", "paragraph_ids": ["s0_p1"], "evidence_ids": ["F1"]}
        for change in ({"verdict": "missing"}, {"evidence_ids": ["F2"]}, {"paragraph_ids": ["s0_p2"]}):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "서로 다른"):
                normalize_review_response({"checks": [check, {**check, **change}], "reference_checks": [], "issues": []})
        ref = {"section_id": "s0", "reference_id": "g", "verdict": "applied"}
        with self.assertRaisesRegex(ValueError, "서로 다른"):
            normalize_review_response({"checks": [], "reference_checks": [ref, {**ref, "verdict": "not_visible"}], "issues": []})

    def test_normalization_keeps_unknown_ids_missing_checks_and_invalid_quotes_blocked(self):
        value = plan(2)
        bodies = {s["id"]: "원문 범위 설명이다. [근거:F1]" for s in value["sections"]}
        paragraphs = index_paragraphs(bodies)
        good = {"checks": [{"item_id": f"item{i}", "verdict": "met", "paragraph_ids": [f"s{i}_p1"],
                            "evidence_ids": ["F1"]} for i in range(2)], "reference_checks": [], "issues": []}
        for mutate in (lambda r: r["checks"][0].update(item_id="unknown"),
                       lambda r: r["checks"].pop(),
                       lambda r: r["checks"][0].update(paragraph_ids=["missing"]),
                       lambda r: r["checks"][0].update(evidence_ids=["unknown"])):
            raw = copy.deepcopy(good)
            mutate(raw)
            with self.assertRaises(ValueError):
                checked_review(raw, value, bodies)
        self.assertEqual(len(paragraphs), 2)

    def test_identical_duplicates_across_all_stages_need_no_extra_model_call(self):
        client = Client()
        def duplicate(system, packet, schema, path):
            result = client(system, packet, schema, path)
            if "checks" in schema["properties"]:
                result["checks"].append(copy.deepcopy(result["checks"][0]))
            return result
        with TemporaryDirectory() as tmp:
            engine = PlannedPaper(tmp, duplicate)
            result = engine.run(research())
            self.assertEqual(len(client.events), 17)
            self.assertTrue(result["review"]["approved"])
            self.assertEqual(result["review"]["review_kind"], "editorial")
            folder = Path(result["run_dir"]) / "workflow/subsection-s1-p1"
            raw_path = next((folder / "responses").glob("review-0-*.json"))
            raw = json.loads(raw_path.read_text(encoding="utf-8"))
            self.assertEqual(len(raw["value"]["checks"]), 2)
            before = len(client.events)
            self.assertEqual(engine.run(research())["draft_markdown"], result["draft_markdown"])
            self.assertEqual(len(client.events), before)

    def test_conflict_repairs_only_review_without_rewriting_body(self):
        for target in ("subsection-s1-p1",):
            with self.subTest(target=target), TemporaryDirectory() as tmp:
                client, corrupted = Client(), False
                def conflict(system, packet, schema, path):
                    nonlocal corrupted
                    result = client(system, packet, schema, path)
                    if path.parent.parent.name == target and "checks" in schema["properties"] and not corrupted:
                        corrupted = True
                        result["checks"].append({**copy.deepcopy(result["checks"][0]), "verdict": "missing"})
                    return result
                result = PlannedPaper(tmp, conflict).run(research())
                self.assertTrue(result["review"]["approved"])
                events = [(s, k) for s, k, _ in client.events]
                self.assertEqual(events.count((target, "generate")), 1)
                self.assertEqual(events.count((target, "review")), 2)
                correction = next(p for s, _, p in client.events if s == target and "rejected_review" in p)
                self.assertIn("서로 다른", correction["validation_error"])
                self.assertEqual(correction["expected_item_ids"], [i["id"] for s in correction["plan"]["sections"] for i in s["required_items"]])
                self.assertTrue((Path(result["run_dir"]) / "workflow" / target / "review-0-validation-0.json").exists())

    def test_repeated_invalid_reviews_keep_candidate_and_stop_before_parent(self):
        client = Client()
        def conflict(system, packet, schema, path):
            result = client(system, packet, schema, path)
            if path.parent.parent.name == "subsection-s1-p1" and "checks" in schema["properties"]:
                result["checks"].append({**copy.deepcopy(result["checks"][0]), "verdict": "missing"})
            return result
        with TemporaryDirectory() as tmp:
            folder = Path(tmp) / "run"
            folder.mkdir()
            (folder / "draft.md").write_text("previous draft", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "검토 응답 보정 후에도"):
                PlannedPaper(tmp, conflict).run(research(), output_dir=folder)
            self.assertEqual((folder / "draft.md").read_text(encoding="utf-8"), "previous draft")
            self.assertFalse(any(s == "section-s1" for s, _, _ in client.events))
            stage = folder / "workflow/subsection-s1-p1"
            self.assertTrue((stage / "candidate.json").exists())
            self.assertTrue((stage / "review-0-validation-1.json").exists())
            self.assertFalse((stage / "approved.json").exists())
            self.assertEqual(sum(s == "subsection-s1-p1" and k == "generate" for s, k, _ in client.events), 1)
            self.assertEqual(sum(s == "subsection-s1-p1" and k == "review" for s, k, _ in client.events), 2)

    def test_corrected_missing_verdict_still_requires_body_revision(self):
        client = Client()
        def conflict_then_missing(system, packet, schema, path):
            result = client(system, packet, schema, path)
            if path.parent.parent.name == "subsection-s1-p1" and "checks" in schema["properties"]:
                if path.name.startswith("review-0-correction-1"):
                    result["checks"][0].update(verdict="missing", paragraph_ids=[], evidence_ids=[])
                elif path.name.startswith("review-0-"):
                    result["checks"].append({**copy.deepcopy(result["checks"][0]), "verdict": "missing"})
            return result
        with TemporaryDirectory() as tmp:
            result = PlannedPaper(tmp, conflict_then_missing).run(research())
            self.assertTrue(result["review"]["approved"])
            self.assertEqual(sum(s == "subsection-s1-p1" and k == "generate" for s, k, _ in client.events), 2)
            revision = next(p["revision"] for s, _, p in client.events if s == "subsection-s1-p1" and "revision" in p)
            self.assertFalse(revision["review"]["approved"])
            self.assertEqual(revision["review"]["checks"][0]["verdict"], "missing")

    def test_resume_after_correction_transport_failure_reuses_original_body_and_review(self):
        client, interrupted = Client(), False
        def flaky(system, packet, schema, path):
            nonlocal interrupted
            result = client(system, packet, schema, path)
            if path.parent.parent.name == "subsection-s1-p1" and "checks" in schema["properties"]:
                if path.name.startswith("review-0-correction-1"):
                    if not interrupted:
                        interrupted = True
                        raise RuntimeError("correction transport interrupted")
                else:
                    result["checks"].append({**copy.deepcopy(result["checks"][0]), "verdict": "missing"})
            return result
        with TemporaryDirectory() as tmp:
            engine = PlannedPaper(tmp, flaky)
            with self.assertRaisesRegex(RuntimeError, "correction transport interrupted"):
                engine.run(research())
            before = len(client.events)
            result = engine.run(research())
            self.assertTrue(result["review"]["approved"])
            first_resumed = client.events[before]
            self.assertEqual(first_resumed[:2], ("subsection-s1-p1", "review"))
            self.assertIn("rejected_review", first_resumed[2])
            self.assertEqual(sum(s == "subsection-s1-p1" and k == "generate" for s, k, _ in client.events), 1)

    def test_keyed_correction_binds_exact_item_and_guide_slots_and_validates_ids(self):
        value = plan(2)
        value["sections"][0]["reference_ids"] = ["guide1", "guide2"]
        bodies = {s["id"]: "원문 범위 설명이다. [근거:F1]" for s in value["sections"]}
        schema = correction_schema(review_schema(value, index_paragraphs(bodies)), value)
        self.assertEqual(set(schema["properties"]["checks"]["properties"]), {"item0", "item1"})
        self.assertEqual(set(schema["properties"]["reference_checks"]["properties"]["s0"]["properties"]),
                         {"guide1", "guide2"})
        raw = {"checks": {f"item{i}": {"verdict": "met", "paragraph_ids": [f"s{i}_p1"], "evidence_ids": ["F1"]}
                          for i in range(2)}, "reference_checks": {"s0": {
                    key: {"verdict": "partial", "paragraph_ids": ["s0_p1"], "reason": "일부 활성 기준이 반영됨"}
                    for key in ("guide1", "guide2")}}, "issues": []}
        result = checked_review(raw, value, bodies)
        self.assertTrue(result["approved"])
        self.assertEqual(result["reference_application"]["partial"], 2)
        for mutate in (lambda r: r["checks"].pop("item1"),
                       lambda r: r["checks"].update(unknown=r["checks"]["item0"]),
                       lambda r: r["reference_checks"]["s0"].pop("guide2"),
                       lambda r: r["reference_checks"].update(unknown={}),
                       lambda r: r["reference_checks"]["s0"]["guide1"].update(paragraph_ids=["missing"])):
            invalid = copy.deepcopy(raw)
            mutate(invalid)
            with self.assertRaises(ValueError):
                checked_review(invalid, value, bodies)

    def test_reference_criteria_use_one_aggregate_slot_from_first_request(self):
        client = Client()
        client.plan["sections"][1].update(reference_ids=["ref1_methods"], reference_adaptation="방법의 조건을 설명한다.")
        reference = {"profiles": [{"section_guidelines": [{"role": "methods", "purpose": "방법 설명",
            "required_content": ["조건 설명"], "paragraph_flow": [], "figures_tables": []}],
            "style_rules": [], "observed_outline": []}]}
        def response(system, packet, schema, path):
            raw = client(system, packet, schema, path)
            if "checks" not in schema["properties"]:
                return raw
            raw["reference_checks"] = [{"section_id": s["id"], "reference_id": key, "verdict": "applied",
                "paragraph_ids": [next(p for p, row in packet["draft_paragraphs"].items() if row["section_id"] == s["id"])],
                "reason": "기준 반영"} for s in packet["plan"]["sections"] for key in s["reference_ids"]]
            if path.parent.parent.name == "subsection-s1-p0":
                if schema["properties"]["checks"]["type"] == "array":
                    raw["reference_checks"].append({**raw["reference_checks"][0], "verdict": "not_visible",
                                                   "paragraph_ids": [], "reason": "다른 기준은 미반영"})
                else:
                    raw["reference_checks"][0].update(verdict="partial", reason="활성 기준의 반영 범위를 종합 평가함")
                    raw["checks"] = {r["item_id"]: {k: v for k, v in r.items() if k != "item_id"} for r in raw["checks"]}
                    raw["reference_checks"] = {"s1": {r["reference_id"]: {k: v for k, v in r.items()
                        if k not in ("section_id", "reference_id")} for r in raw["reference_checks"]}}
            return raw
        with TemporaryDirectory() as tmp:
            engine = PlannedPaper(tmp, response)
            result = engine.run(research(), reference)
            self.assertTrue(result["review"]["approved"])
            self.assertEqual(sum(s == "section-s1" and k == "generate" for s, k, _ in client.events), 1)
            self.assertEqual(sum(s == "section-s1" and k == "review" for s, k, _ in client.events), 1)
            saved = json.loads((Path(result["run_dir"]) / "workflow/subsection-s1-p0/approved.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["value"]["raw_review"]["reference_checks"][0]["verdict"], "partial")
            before = len(client.events)
            engine.run(research(), reference)
            self.assertEqual(len(client.events), before)

    def test_unused_candidates_do_not_become_missing_content_or_fabricated_citations(self):
        value = plan(2)
        value["sections"][0]["required_items"][0]["evidence_ids"] = ["F1", "F2"]
        bodies = {s["id"]: "기록의 설명이다. [근거:F1]" for s in value["sections"]}
        raw = {"checks": [{"item_id": f"item{i}", "verdict": "met", "paragraph_ids": [f"s{i}_p1"],
                            "evidence_ids": ["F1"]} for i in range(2)], "issues": [], "reference_checks": []}
        original = copy.deepcopy(raw)
        result = checked_review(raw, value, bodies)
        self.assertTrue(result["approved"])
        check = result["checks"][0]
        self.assertEqual(check["verdict"], "met")
        self.assertEqual(check["evidence_ids"], ["F1"])
        self.assertEqual(check["unused_candidate_evidence_ids"], ["F2"])
        self.assertNotIn("missing_body_evidence_ids", check)
        self.assertFalse(any(i["severity"] == "error" for i in result["issues"]))
        self.assertEqual(raw, original)

    def test_listing_all_ids_does_not_pass_when_selected_paragraph_does_not_cite_them(self):
        value = plan(2)
        value["sections"][0]["required_items"][0]["evidence_ids"] = ["F1", "F2"]
        bodies = {"s0": "조건이다. [근거:F1]\n\n다른 문단의 결과다. [근거:F2]", "s1": "결론이다. [근거:F1]"}
        raw = {"checks": [{"item_id": "item0", "verdict": "met", "paragraph_ids": ["s0_p1"], "evidence_ids": ["F1", "F2"]},
                          {"item_id": "item1", "verdict": "met", "paragraph_ids": ["s1_p1"], "evidence_ids": ["F1"]}],
               "issues": [], "reference_checks": []}
        result = checked_review(raw, value, bodies)
        self.assertFalse(result["approved"])
        self.assertEqual(result["checks"][0]["missing_review_evidence_ids"], [])
        self.assertEqual(result["checks"][0]["missing_body_evidence_ids"], ["F2"])
        raw["checks"][0]["paragraph_ids"].append("s0_p2")
        self.assertTrue(checked_review(raw, value, bodies)["approved"])

    def test_missing_content_goes_back_to_writer_without_report_format_repair(self):
        client = Client()
        client.plan["sections"][0]["required_items"][0]["evidence_ids"] = ["F1", "F2"]
        first = True
        def response(system, packet, schema, path):
            nonlocal first
            raw = client(system, packet, schema, path)
            if first and path.parent.parent.name == "subsection-s0-p0" and "parts" in schema["properties"]:
                first = False
                raw["parts"]["p0"] = "조건만 설명했다. [근거:F1]"
            return raw
        with TemporaryDirectory() as tmp:
            result = PlannedPaper(tmp, response).run(research())
            self.assertTrue(result["review"]["approved"])
            selected = [(s, k, p) for s, k, p in client.events if s == "subsection-s0-p0"]
            self.assertEqual(sum(k == "generate" for _, k, _ in selected), 2)
            self.assertEqual(sum(k == "review" for _, k, _ in selected), 2)
            self.assertFalse(any("rejected_review" in p for _, _, p in selected))
            revision = next(p["revision"] for _, k, p in selected if k == "generate" and "revision" in p)
            self.assertEqual(revision["review"]["checks"][0]["missing_body_evidence_ids"], ["F2"])


if __name__ == "__main__":
    unittest.main()
