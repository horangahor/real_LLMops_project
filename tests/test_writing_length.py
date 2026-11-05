import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from bounded_drafting import generation_fragments
from paper_context import build_contexts, part_context
from planned_paper import GROUNDING, WRITER, PlannedPaper, load_latest
from test_draft_revision import revision_fixture
from test_drafting_budget import fixture
from test_hierarchical_drafting import Client, assigned_plan
from test_planned_paper import plan, research
from writing_length import (DEFAULT_TARGET_CHARS, INSTRUCTION, allocate_fragment_targets,
                            apply_length_targets, apportion, narrative_chars, resolve_target)


class WritingLengthTests(unittest.TestCase):
    def test_defaults_environment_and_zero(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(resolve_target(), DEFAULT_TARGET_CHARS)
        with patch.dict("os.environ", {"PAPER_DRAFT_TARGET_CHARS": "20000"}):
            self.assertEqual(resolve_target(), 20000)
            self.assertEqual(resolve_target(0), 0)
            self.assertEqual(resolve_target(40000), 40000)
        for invalid in (-1, True, 3.5, "invalid"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                resolve_target(invalid)

    def test_integer_allocation_does_not_multiply_or_lose_budget(self):
        for total in (0, 1, 7, 30001):
            shares = apportion(total, [2, 4, 2])
            self.assertEqual(sum(shares), total)
            self.assertEqual(shares, apportion(total, [2, 4, 2]))
        self.assertEqual(apportion(5, [1, 1, 1]), [2, 2, 1])
        self.assertEqual(apportion(3, []), [])

    def test_role_and_structure_allocate_same_budget_to_child_and_editor(self):
        value = plan(placeholder=True)
        contexts = build_contexts(value, research(), {})
        before = copy.deepcopy(contexts)
        report = apply_length_targets(value, contexts, 30000)
        self.assertEqual(sum(row["target_chars"] for row in report["subsections"]), 30000)
        self.assertEqual([row["target_chars"] for row in report["subsections"]], [7500] * 4)
        self.assertNotIn("related", contexts["subsections"])
        for sid, parts in contexts["subsections"].items():
            for key, child in parts.items():
                self.assertEqual(child["writing_budget"], part_context(contexts["sections"][sid], key)["writing_budget"])
                self.assertEqual(child["facts"], before["subsections"][sid][key]["facts"])
        self.assertEqual(value, plan(placeholder=True))

    def test_disabled_policy_does_not_change_context(self):
        value = assigned_plan()
        contexts = build_contexts(value, research(), {})
        before = copy.deepcopy(contexts)
        self.assertIsNone(apply_length_targets(value, contexts, 0))
        self.assertEqual(contexts, before)

    def test_narrative_counter_excludes_only_headings_tables_and_citation_markers(self):
        body = "### 소절\n\n조건 A [근거:F1,F2]\n관측 B\n\n| 조건 | 값 |\n| --- | --- |\n| A | 12 |"
        self.assertEqual(narrative_chars(body), len("조건 A\n관측 B"))
        self.assertEqual(narrative_chars("조건 [확인 필요]"), len("조건 [확인 필요]"))

    def test_source_batches_share_one_subsection_target_and_preserve_all_sources(self):
        data, value, contexts, _, _ = fixture()
        apply_length_targets(value, contexts, 4000)
        packet = contexts["subsections"]["s0"]["p0"]
        original = copy.deepcopy(packet)
        with patch.dict("os.environ", {"PAPER_REQUEST_MAX_BYTES": "36000"}):
            tasks = generation_fragments(GROUNDING + WRITER + INSTRUCTION, packet, {"s0": packet})
        requests = [request for _, _, _, request, schema in tasks if schema is not None]
        self.assertGreater(len(requests), 1)
        self.assertEqual(sum(r["writing_budget"]["target_chars"] for r in requests), packet["writing_budget"]["target_chars"])
        self.assertTrue(all(r["writing_budget"]["whole_target_chars"] == 2000 for r in requests))
        seen = {f["id"]: f for r in requests for f in r["facts"]}
        self.assertEqual(seen, {f["id"]: f for f in data["facts"]})
        self.assertEqual(packet, original)

    def test_revisions_and_missing_content_share_remaining_budget_after_preserved_prose(self):
        _, _, packet, _, _ = revision_fixture()
        packet["writing_budget"] = {"target_chars": 1000, "whole_target_chars": 1000,
                                     "paper_target_chars": 30000}
        original = copy.deepcopy(packet)
        with patch.dict("os.environ", {"PAPER_REQUEST_MAX_BYTES": "36000"}):
            tasks = generation_fragments(GROUNDING + WRITER + INSTRUCTION, packet, {"s0": packet})
        kept = sum(narrative_chars(r["passthrough"]) for _, _, _, r, schema in tasks if schema is None)
        requests = [r for _, _, _, r, schema in tasks if schema is not None]
        self.assertTrue(any(r["fragment"].get("operation") == "missing_evidence" for r in requests))
        self.assertEqual(sum(r["writing_budget"]["target_chars"] for r in requests), 1000 - kept)
        self.assertTrue(all(r["writing_budget"]["preserved_chars"] == kept for r in requests))
        self.assertEqual(packet, original)

    def test_preserved_text_can_exceed_target_without_new_length_exception(self):
        packet = {"writing_budget": {"target_chars": 1}}
        tasks = [("s", "p0", "kept", {"passthrough": "이미 저장한 긴 본문"}, None),
                 ("s", "p0", "new", {"facts": []}, {"type": "object"})]
        result = allocate_fragment_targets(tasks, {"s": packet})
        self.assertEqual(result[1][3]["writing_budget"]["target_chars"], 0)
        self.assertEqual(result[0], tasks[0])
        self.assertNotIn("writing_budget", tasks[1][3])

    def test_setting_changes_reuse_plan_preserve_old_draft_and_resume_exact_requests(self):
        with TemporaryDirectory() as tmp:
            client = Client()
            engine = PlannedPaper(tmp, client)
            legacy = engine.run(research(), writing_target_chars=0)
            path = Path(legacy["run_dir"]) / "workflow/subsection-s0-p0/approved.json"
            old_bytes = path.read_bytes()
            current = engine.run(research(), writing_target_chars=30000)
            self.assertNotEqual(legacy["run_dir"], current["run_dir"])
            self.assertEqual(legacy["plan"], current["plan"])
            # Planning packets have 'research', and are the only events at run level.
            self.assertEqual(sum("research" in p and "reference_shapes" in p for _, _, p in client.events), 1)
            self.assertEqual(old_bytes, path.read_bytes())
            before = len(client.events)
            resumed = engine.run(research(), writing_target_chars=30000)
            self.assertEqual(before, len(client.events))
            self.assertEqual(resumed["draft_markdown"], current["draft_markdown"])
            engine.run(research(), writing_target_chars=20000)
            self.assertEqual(sum("reference_shapes" in p for _, _, p in client.events), 1)
            editors = [p for _, _, p in client.events if p.get("operation") == "editorial_assembly"]
            self.assertTrue(any(p.get("writing_targets") for p in editors))

    def test_excess_is_recorded_without_truncating_body_or_rejecting_draft(self):
        with TemporaryDirectory() as tmp:
            result = PlannedPaper(tmp, Client()).run(research(), writing_target_chars=4)
            self.assertTrue(result["review"]["approved"])
            summary = result["writing_length"]
            self.assertEqual(summary["over_target_count"], 4)
            self.assertGreater(summary["actual_final_chars"], 4)
            self.assertIn("배정된 원문 범위의 설명이다.", result["draft_markdown"])
            self.assertIn("[근거:", result["sections"]["s0"])
            self.assertEqual(summary, result["review"]["writing_length"])
            self.assertEqual(summary, load_latest(tmp)["review"]["writing_length"])
            saved = json.loads((Path(result["run_dir"]) / "writing-length-report.json").read_text(encoding="utf-8"))
            self.assertEqual(saved, summary)

    def test_completed_subsection_length_record_survives_later_stage_failure(self):
        with TemporaryDirectory() as tmp:
            client = Client()
            client.fail_once = "section-s0"
            with self.assertRaisesRegex(RuntimeError, "test interruption"):
                PlannedPaper(tmp, client).run(research(), writing_target_chars=30000)
            report_path = next(Path(tmp).glob("draft_history/planned/generic/*/writing-length-report.json"))
            saved = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["status"], "in_progress")
            self.assertEqual(saved["subsections"][0]["section_id"], "s0")
            self.assertGreater(saved["subsections"][0]["draft_chars"], 0)


if __name__ == "__main__":
    unittest.main()
