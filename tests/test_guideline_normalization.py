import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from paper_plan import bind_plan_evidence, project_profile, reference_catalog, validate_plan
from planned_paper import PlannedPaper
from test_planned_paper import FakeClient, plan, research


def fixture():
    reference = {"profiles": [{"section_guidelines": [{"role": "methods", "purpose": "조건과 범위",
        "required_content": ["비교 조건", "해석 범위"], "paragraph_flow": [], "figures_tables": []}],
        "style_rules": [], "observed_outline": []}]}
    value = plan()
    section = value["sections"][1]
    section.update(reference_ids=["ref1_methods"], reference_adaptation="조건과 범위를 설명한다.")
    section["required_items"][0]["guideline_ids"] = ["ref1_methods_required_2", "ref1_methods_required_1",
                                                    "ref1_methods_required_2", "ref1_methods_required_1"]
    return value, reference


class GuidelineNormalizationTests(unittest.TestCase):
    def test_exact_duplicates_are_removed_in_original_order_and_audited_without_mutating_input(self):
        value, reference = fixture()
        original = copy.deepcopy(value)
        result = bind_plan_evidence(value, research())
        validate_plan(result, research(), reference_catalog(reference), project_profile("generic"))
        self.assertEqual(result["sections"][1]["required_items"][0]["guideline_ids"],
                         ["ref1_methods_required_2", "ref1_methods_required_1"])
        self.assertEqual(result["guideline_id_normalizations"], [{"section_id": "s1", "item_id": "item1",
            "removed_duplicate_ids": ["ref1_methods_required_2", "ref1_methods_required_1"]}])
        self.assertEqual(value, original)
        repeated = bind_plan_evidence(result, research())
        self.assertEqual(repeated["guideline_id_normalizations"], result["guideline_id_normalizations"])

    def test_unknown_and_unselected_guide_ids_still_fail_with_exact_scope(self):
        for invalid in ("unknown", "ref2_methods_required_1"):
            value, reference = fixture()
            reference["profiles"].append(copy.deepcopy(reference["profiles"][0]))
            value["sections"][1]["required_items"][0]["guideline_ids"] = [invalid, invalid]
            normalized = bind_plan_evidence(value, research())
            with self.assertRaises(ValueError) as caught:
                validate_plan(normalized, research(), reference_catalog(reference), project_profile("generic"))
            for detail in ("골든 가이드에 없습니다", "s1", "item1", invalid):
                self.assertIn(detail, str(caught.exception))

    def test_direct_validator_reports_duplicates_separately_from_missing_criteria(self):
        value, reference = fixture()
        with self.assertRaisesRegex(ValueError, "작성 기준 ID가 중복") as caught:
            validate_plan(value, research(), reference_catalog(reference), project_profile("generic"))
        self.assertNotIn("가이드에 없습니다", str(caught.exception))

    def test_cached_plan_is_normalized_without_new_plan_or_correction_api_call(self):
        value, reference = fixture()
        with TemporaryDirectory() as tmp:
            client = FakeClient(value)
            engine = PlannedPaper(tmp, client)
            result = engine.run(research(), reference, plan_only=True)
            cached_path = next((Path(result["run_dir"]) / "responses").glob("plan-*.json"))
            cached = cached_path.read_bytes()
            self.assertEqual(len(json.loads(cached)["value"]["sections"][1]["required_items"][0]["guideline_ids"]), 4)
            self.assertEqual(len(result["plan"]["sections"][1]["required_items"][0]["guideline_ids"]), 2)
            engine.run(research(), reference, plan_only=True)
            self.assertEqual(len(client.calls), 1)
            self.assertEqual(cached_path.read_bytes(), cached)


if __name__ == "__main__":
    unittest.main()
