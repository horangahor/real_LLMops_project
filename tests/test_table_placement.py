import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

from paper_plan import bind_plan_evidence, project_profile, validate_plan
from planned_paper import PlannedPaper, render_paper
from table_placement import resolve_table_placements
from test_planned_paper import FakeClient, plan, research


def fixture():
    value, data = plan(4), research()
    value["sections"][2]["role"] = "evaluation"
    data["tables"] = [
        {"id": "T1", "caption": "성능 비교", "columns": ["조건", "값"], "rows": [["B", "12"]], "evidence_ids": ["F2"]},
        {"id": "T2", "caption": "실험 설정", "columns": ["조건"], "rows": [["같은 입력"]], "evidence_ids": ["F1"]},
        {"id": "T3", "caption": "단독 배치", "columns": ["조건"], "rows": [["A"]], "evidence_ids": ["F1"]}]
    value["sections"][1]["table_ids"] = ["T1", "T2", "T3"]
    value["sections"][2]["table_ids"] = ["T1", "T2"]
    return value, data


def selection():
    return {"placements": {"T1": {"section_id": "s2", "reason": "측정 결과표는 평가 장에 배치한다."},
                           "T2": {"section_id": "s1", "reason": "설정표는 방법 장에 배치한다."}}}


class TablePlacementTests(unittest.TestCase):
    def test_conflicts_are_resolved_without_changing_evidence_or_unrelated_plan_fields(self):
        value, data = fixture()
        original, original_data = copy.deepcopy(value), copy.deepcopy(data)
        engine = Mock()
        engine.call.return_value = selection()
        with TemporaryDirectory() as tmp:
            fixed = resolve_table_placements(engine, Path(tmp), value, data)
            saved = json.loads((Path(tmp) / "table-placement.json").read_text(encoding="utf-8"))
        engine.call.assert_called_once()
        packet = engine.call.call_args.args[3]
        self.assertEqual([c["table"]["id"] for c in packet["conflicts"]], ["T1", "T2"])
        self.assertEqual(packet["conflicts"][0]["table"], data["tables"][0])
        self.assertEqual(fixed["sections"][1]["table_ids"], ["T2", "T3"])
        self.assertEqual(fixed["sections"][2]["table_ids"], ["T1"])
        for before, after in zip(original["sections"], fixed["sections"]):
            self.assertEqual({k: v for k, v in before.items() if k != "table_ids"},
                             {k: v for k, v in after.items() if k != "table_ids"})
        self.assertEqual(value, original)
        self.assertEqual(data, original_data)
        self.assertEqual(len(saved["adjustments"]), 2)
        self.assertEqual(saved["adjustments"][0]["original_section_ids"], ["s1", "s2"])
        validate_plan(fixed, data, {}, project_profile("generic"))
        rendered = render_paper(fixed, {s["id"]: "본문 [근거:F1]" for s in fixed["sections"]}, data)
        self.assertEqual(rendered.count("성능 비교"), 1)
        self.assertEqual(rendered.count("실험 설정"), 1)

    def test_no_conflict_needs_no_model_call(self):
        value, data = fixture()
        value["sections"][2]["table_ids"] = []
        engine = Mock()
        with TemporaryDirectory() as tmp:
            fixed = resolve_table_placements(engine, tmp, value, data)
        self.assertEqual(fixed, value)
        engine.call.assert_not_called()

    def test_invalid_placement_is_corrected_once_with_feedback(self):
        value, data = fixture()
        wrong = selection()
        wrong["placements"]["T1"]["section_id"] = "s0"
        engine = Mock()
        engine.call.side_effect = [wrong, selection()]
        with TemporaryDirectory() as tmp:
            fixed = resolve_table_placements(engine, tmp, value, data)
            rejected = json.loads((Path(tmp) / "table-placement-rejected-0.json").read_text(encoding="utf-8"))
        self.assertEqual(engine.call.call_count, 2)
        self.assertEqual(rejected["response"], wrong)
        self.assertIn("previous_error", engine.call.call_args.args[3])
        validate_plan(fixed, data, {}, project_profile("generic"))

    def test_missing_extra_unknown_and_blank_selections_never_change_the_plan(self):
        missing = selection()
        del missing["placements"]["T2"]
        extra = selection()
        extra["placements"]["T3"] = {"section_id": "s1", "reason": "not a conflict"}
        unknown = selection()
        unknown["placements"]["T1"]["section_id"] = "unknown"
        blank = selection()
        blank["placements"]["T1"]["reason"] = " "
        for bad in (missing, extra, unknown, blank, None, {"sections": []}):
            with self.subTest(response=bad), TemporaryDirectory() as tmp:
                value, data = fixture()
                original = copy.deepcopy(value)
                engine = Mock()
                engine.call.return_value = bad
                with self.assertRaisesRegex(ValueError, "표 배치 보정"):
                    resolve_table_placements(engine, tmp, value, data)
                self.assertEqual(value, original)
                self.assertEqual(engine.call.call_count, 2)
                self.assertTrue((Path(tmp) / "table-placement-rejected-1.json").exists())
                self.assertFalse((Path(tmp) / "table-placement.json").exists())

    def test_overlap_preflight_still_rejects_unknown_tables_and_other_plan_errors(self):
        value, data = fixture()
        validate_plan(value, data, {}, project_profile("generic"), allow_table_overlap=True)
        with self.assertRaisesRegex(ValueError, "중복 배치"):
            validate_plan(value, data, {}, project_profile("generic"))
        for mutate in (lambda p: p["sections"][1]["table_ids"].append("missing"),
                       lambda p: p["sections"][0]["evidence_ids"].append("unknown")):
            invalid = copy.deepcopy(value)
            mutate(invalid)
            with self.assertRaises(ValueError):
                validate_plan(invalid, data, {}, project_profile("generic"), allow_table_overlap=True)
        value["sections"][1]["table_ids"].append("missing")
        engine = Mock()
        with TemporaryDirectory() as tmp, self.assertRaisesRegex(ValueError, "존재하지 않는 표"):
            resolve_table_placements(engine, tmp, value, data)
        engine.call.assert_not_called()

    def test_pipeline_reuses_plan_and_placement_responses_instead_of_regenerating_plan(self):
        value, data = fixture()
        fake = FakeClient(value)
        def client(system, packet, schema, path):
            if "placements" in schema["properties"]:
                fake.calls.append((system, packet))
                return selection()
            return fake(system, packet, schema, path)
        with TemporaryDirectory() as tmp:
            engine = PlannedPaper(tmp, client)
            first = engine.run(data, plan_only=True)
            second = engine.run(data, plan_only=True)
            self.assertEqual(first["plan"], second["plan"])
            self.assertEqual(len(fake.calls), 2)  # one planner + one placement decision
            folder = Path(first["run_dir"])
            self.assertFalse((folder / "plan-rejected.json").exists())
            self.assertTrue((folder / "table-placement.json").exists())
            validate_plan(first["plan"], data, {}, project_profile("generic"))


if __name__ == "__main__":
    unittest.main()
