"""Selected-section generation must never invoke the paper editor or planner."""
import copy
import json
import unittest
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory

from planned_paper import PlannedPaper
from section_drafting import run_saved_section, load_section_inputs
from test_hierarchical_drafting import Client
from test_planned_paper import research


class SectionDraftingTests(unittest.TestCase):
    def test_selected_section_runs_its_children_then_first_editor_only(self):
        with TemporaryDirectory() as tmp:
            client = Client()
            engine = PlannedPaper(tmp, client)
            planned = engine.run(research(), plan_only=True, writing_target_chars=30000)
            folder = Path(planned["run_dir"])
            client.events.clear()
            result = run_saved_section(engine, folder, "s1")
            stages = [(s, k) for s, k, p in client.events if "workflow_stage" in p]
            expected = ["subsection-s1-p0", "subsection-s1-p1", "section-s1"]
            self.assertEqual(stages, [(s, k) for s in expected for k in ("generate", "review")])
            self.assertEqual([s["id"] for s in result["workflow"]["stages"]], expected)
            self.assertEqual(result["scope"], "section")
            self.assertEqual(result["writing_length"]["scope"], "section")
            self.assertIn("제2장", result["draft_markdown"])
            self.assertIn("2.1", result["draft_markdown"])
            self.assertTrue(result["provenance"])
            self.assertTrue(all(p["evidence"] for p in result["provenance"]))
            self.assertTrue((folder / "section-runs/s1/result.json").is_file())
            self.assertFalse((folder / "draft.md").exists())
            self.assertFalse((folder / "workflow/paper").exists())
            self.assertFalse((Path(tmp) / "draft_history/planned/latest.json").exists())
            # A second click revalidates completed checkpoints, with zero model calls.
            client.events.clear()
            again = run_saved_section(engine, folder, "s1")
            self.assertEqual(client.events, [])
            self.assertEqual(result["draft_markdown"], again["draft_markdown"])

    def test_full_draft_and_aggregate_reports_are_not_replaced(self):
        with TemporaryDirectory() as tmp:
            client = Client()
            engine = PlannedPaper(tmp, client)
            full = engine.run(research())
            folder = Path(full["run_dir"])
            names = ["draft.md", "sections.json", "review.json", "workflow.json", "review-warnings.json", "writing-length-report.json"]
            before = {name: (folder / name).read_bytes() for name in names}
            pointer = Path(tmp) / "draft_history/planned/latest.json"
            pointer_before = pointer.read_bytes()
            client.events.clear()
            run_saved_section(engine, folder, "s1")
            self.assertEqual(client.events, [])
            self.assertEqual(before, {name: (folder / name).read_bytes() for name in names})
            self.assertEqual(pointer.read_bytes(), pointer_before)

    def test_partial_checkpoints_can_be_used_by_a_later_full_run(self):
        with TemporaryDirectory() as tmp:
            client = Client()
            engine = PlannedPaper(tmp, client)
            planned = engine.run(research(), plan_only=True)
            run_saved_section(engine, Path(planned["run_dir"]), "s1")
            client.events.clear()
            full = engine.run(research())
            self.assertFalse(any(s.startswith("subsection-s1") or s == "section-s1" for s, _, _ in client.events))
            self.assertTrue(any(s == "paper" for s, _, _ in client.events))
            self.assertTrue(full["draft_markdown"])

    def test_missing_or_modified_plan_inputs_stop_before_any_model_call(self):
        with TemporaryDirectory() as tmp:
            client = Client()
            engine = PlannedPaper(tmp, client)
            planned = engine.run(research(), plan_only=True)
            folder = Path(planned["run_dir"])
            client.events.clear()
            for sid in ("../../paper", "missing"):
                with self.assertRaises(ValueError):
                    run_saved_section(engine, folder, sid)
            path = folder / "contexts/subsections/s1-p0.json"
            value = json.loads(path.read_text(encoding="utf-8"))
            value["facts"][0]["statement"] = "not the original evidence"
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "일치하지"):
                load_section_inputs(folder, "s1")
            self.assertEqual(client.events, [])

    def test_current_editing_rules_update_saved_section_but_reuse_its_leaf_checkpoints(self):
        from writing_policy import load_policy
        with TemporaryDirectory() as tmp:
            client, calls = Client(), []
            def respond(system, packet, schema, path):
                calls.append((system, copy.deepcopy(packet)))
                return client(system, packet, schema, path)
            engine = PlannedPaper(tmp, respond)
            full = engine.run(research())
            folder = Path(full["run_dir"])
            leaves = {p: p.read_bytes() for p in (folder / "workflow").glob("subsection-s1-*/approved.json")}
            original_context = (folder / "contexts/sections/s1.json").read_bytes()
            changed = load_policy()
            changed["version"] = "editing-only-test"
            changed["editing"].append("CURRENT_EDITOR_RULE_FOR_SAVED_PLAN")
            client.events.clear()
            calls.clear()
            with patch("writing_policy.load_policy", return_value=changed):
                run_saved_section(engine, folder, "s1")
            self.assertTrue(client.events)
            self.assertTrue(all(stage == "section-s1" for stage, _, _ in client.events))
            self.assertEqual(leaves, {p: p.read_bytes() for p in leaves})
            self.assertEqual((folder / "contexts/sections/s1.json").read_bytes(), original_context)
            editor_calls = [(s, p) for s, p in calls if p.get("operation") == "editorial_assembly"]
            self.assertTrue(editor_calls)
            self.assertTrue(all("CURRENT_EDITOR_RULE_FOR_SAVED_PLAN" in system for system, _ in editor_calls))
            audit = json.loads((folder / "workflow/section-s1/generate-0-editing-input.json").read_text(encoding="utf-8"))
            self.assertEqual(audit["editing_policies"]["s1"]["version"], "editing-only-test")
            self.assertIn("editing_targets", audit)


if __name__ == "__main__":
    unittest.main()
