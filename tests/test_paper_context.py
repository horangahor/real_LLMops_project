import copy
import json
import unittest

from paper_context import build_contexts


def fixture():
    facts = [{"id": key, "statement": key + "의 관측 결과", "limits": "이 실험 범위만 해당",
              "conditions": ["동일 입력, 예열 후"], "claim_status": "observed", "source_origin": "measurement_log",
              "writing_role": "research_fact", "measurements": [{"value": "12.5", "unit": "ms", "condition": "평균"}],
              "sources": [{"element_id": key + "_source", "page": 7, "quote": key + " 원문과 캡션 " * 60}]}
             for key in ("A", "B", "C", "SHARED", "UNRELATED")]
    section = {"id": "methods", "title": "방법", "purpose": "비교 방법과 적용 범위를 설명", "role": "methods",
               "status": "write", "subsections": ["조건 비교", "적용 범위"], "depends_on": [],
               "evidence_ids": ["A", "B", "C", "SHARED"], "reference_ids": ["guide"], "table_ids": [],
               "required_items": [
                   {"id": "compare", "description": "A와 B의 조건을 비교", "evidence_ids": ["A", "B"],
                    "guideline_ids": ["g1"], "subsection_index": 0},
                   {"id": "scope", "description": "C의 적용 범위", "evidence_ids": ["C"],
                    "guideline_ids": ["g2"], "subsection_index": 1}]}
    catalog = {"guide": {"id": "guide", "role": "methods", "purpose": "방법을 설명",
                         "required_content": ["조건을 비교", "범위를 명시"],
                         "criteria": [{"id": "g1", "description": "조건을 비교"}, {"id": "g2", "description": "범위를 명시"}],
                         "paragraph_flow": ["설계 근거 다음 조건과 한계"], "style_rules": ["조건을 명확히"],
                         "not_to_transfer": ["다른 논문의 수치를 가져오지 않는다"]}}
    return {"title": "CUDA 연구", "sections": [section], "generation_order": ["methods"]}, {"facts": facts, "tables": []}, catalog


class PaperContextTests(unittest.TestCase):
    def test_explicit_allocation_excludes_unrelated_facts_and_retains_comparison_pair(self):
        plan, research, catalog = fixture()
        bundle = build_contexts(plan, research, catalog)
        first = bundle["subsections"]["methods"]["p0"]
        second = bundle["subsections"]["methods"]["p1"]
        self.assertEqual([f["id"] for f in first["facts"]], ["A", "B", "SHARED"])
        self.assertEqual([f["id"] for f in second["facts"]], ["C", "SHARED"])
        self.assertNotIn("UNRELATED", json.dumps(bundle, ensure_ascii=False))
        self.assertEqual(first["facts"][0], research["facts"][0])
        self.assertEqual(first["section_plan"]["required_items"][0]["id"], "compare")
        self.assertLess(bundle["allocation_report"][0]["part_input_characters"]["p0"],
                        bundle["allocation_report"][0]["section_input_characters"])

    def test_conditions_limits_provenance_and_quotes_are_not_summarized_or_truncated(self):
        plan, research, catalog = fixture()
        original = copy.deepcopy((plan, research, catalog))
        result = build_contexts(plan, research, catalog)
        preserved = result["subsections"]["methods"]["p0"]["facts"][0]
        self.assertEqual(preserved, research["facts"][0])
        self.assertEqual((plan, research, catalog), original)
        preserved["sources"][0]["quote"] = "changed copy"
        self.assertEqual((plan, research, catalog), original)

    def test_part_guidelines_keep_only_linked_requirements_and_preserve_style_and_limits(self):
        plan, research, catalog = fixture()
        result = build_contexts(plan, research, catalog)
        guide = result["subsections"]["methods"]["p1"]["reference_guides"][0]
        self.assertEqual(guide["criteria"], [{"id": "g2", "description": "범위를 명시"}])
        self.assertEqual(guide["required_content"], ["범위를 명시"])
        for field in ("paragraph_flow", "style_rules", "not_to_transfer"):
            self.assertEqual(guide[field], catalog["guide"][field])

    def test_table_keeps_all_comparison_sides_when_one_side_is_assigned(self):
        plan, research, catalog = fixture()
        plan["sections"][0]["required_items"][0]["evidence_ids"] = ["A"]
        plan["sections"][0]["required_items"][1]["evidence_ids"] = ["B", "C"]
        plan["sections"][0]["table_ids"] = ["T1"]
        research["tables"] = [{"id": "T1", "evidence_ids": ["A", "B"], "columns": ["조건", "시간"],
                               "rows": [["A", "12.5ms"], ["B", "15.2ms"]]}]
        result = build_contexts(plan, research, catalog)["subsections"]["methods"]["p0"]
        self.assertEqual([f["id"] for f in result["facts"]], ["A", "B", "SHARED"])
        self.assertEqual(result["tables"], research["tables"])

    def test_legacy_plan_preserves_full_section_context_and_labels_fallback(self):
        plan, research, catalog = fixture()
        for item in plan["sections"][0]["required_items"]:
            del item["subsection_index"]
        bundle = build_contexts(plan, research, catalog)
        for part in bundle["subsections"]["methods"].values():
            self.assertEqual([f["id"] for f in part["facts"]], ["A", "B", "C", "SHARED"])
            self.assertEqual(part["allocation"], "section_fallback")

    def test_partial_or_invalid_part_assignments_are_not_guessed(self):
        for invalid in (None, 2, -1, True):
            plan, research, catalog = fixture()
            plan["sections"][0]["required_items"][1]["subsection_index"] = invalid
            with self.subTest(index=invalid), self.assertRaises(ValueError):
                build_contexts(plan, research, catalog)

    def test_empty_part_is_rejected_instead_of_dropping_its_purpose(self):
        plan, research, catalog = fixture()
        plan["sections"][0]["required_items"][1]["subsection_index"] = 0
        with self.assertRaisesRegex(ValueError, "소절"):
            build_contexts(plan, research, catalog)

    def test_unknown_fact_or_guide_is_rejected(self):
        for field in ("evidence_ids", "reference_ids"):
            plan, research, catalog = fixture()
            plan["sections"][0][field].append("unknown")
            with self.subTest(field=field), self.assertRaises(ValueError):
                build_contexts(plan, research, catalog)

    def test_unbound_research_requirement_keeps_full_guide_instead_of_guessing_applicability(self):
        plan, research, catalog = fixture()
        plan["sections"][0]["required_items"][0]["guideline_ids"] = []
        result = build_contexts(plan, research, catalog)["subsections"]["methods"]["p0"]
        self.assertEqual(result["reference_guides"], list(catalog.values()))

    def test_dependency_context_contains_outline_metadata_not_other_chapter_evidence(self):
        plan, research, catalog = fixture()
        prior = copy.deepcopy(plan["sections"][0])
        prior.update(id="prior", title="이전 장", evidence_ids=["UNRELATED"])
        prior["required_items"] = [dict(prior["required_items"][0], evidence_ids=["UNRELATED"])]
        prior["subsections"] = []
        plan["sections"].insert(0, prior)
        plan["sections"][1]["depends_on"] = ["prior"]
        result = build_contexts(plan, research, catalog)["sections"]["methods"]
        self.assertEqual(set(result["context"]["prior"]), {"title", "purpose", "role", "subsections"})
        self.assertNotIn("UNRELATED", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
