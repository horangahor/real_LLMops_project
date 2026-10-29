import unittest

from studio_outline_evaluation import extract_numbered_outline, evaluate_studio_markdown


TEXT = """## 섹션 계층 및 순서
- 상위 구조는 **1 Introduction → 2 Methods**입니다.【†11】
- 방법은 **2.1 System Design**으로 나뉩니다.【†12】
## 다른 분석
- **3 Imaginary Section**은 이 구간의 목차가 아닙니다.
"""


class StudioOutlineEvaluationTests(unittest.TestCase):
    def test_explicit_titles_and_number_hierarchy_only(self):
        result = extract_numbered_outline(TEXT)
        roots = result["observed_outline"]
        self.assertEqual([node["title"] for node in roots], ["1 Introduction", "2 Methods"])
        self.assertEqual(roots[1]["children"][0]["title"], "2.1 System Design")
        self.assertEqual(result["unresolved_parents"], [])

    def test_unknown_explicit_titles_are_retained_for_false_positive_scoring(self):
        text = TEXT.replace("2 Methods", "2 Methods → 3 Imaginary Section")
        self.assertEqual(extract_numbered_outline(text)["observed_outline"][2]["title"], "3 Imaginary Section")

    def test_orphan_is_reported_without_inventing_a_parent(self):
        result = extract_numbered_outline("## 섹션 계층 및 순서\n- **2.1 System Design**\n")
        self.assertEqual(result["unresolved_parents"][0]["missing_parent_number"], "2")

    def test_duplicates_are_not_silently_deduplicated(self):
        text = TEXT.replace("1 Introduction →", "1 Introduction → 1 Introduction →")
        self.assertEqual(len(extract_numbered_outline(text)["observed_outline"]), 3)

    def test_descriptive_topics_without_numbers_are_not_invented_as_sections(self):
        text = TEXT.replace("**2.1 System Design**", "**System Design, Research Questions, Limitations**")
        self.assertEqual(extract_numbered_outline(text)["observed_outline"][1]["children"], [])

    def test_unsupported_format_fails_explicitly(self):
        with self.assertRaises(ValueError):
            extract_numbered_outline("## 요약\n1 Introduction")

    def test_missing_role_labels_are_unassessed(self):
        reference = {"items": [
            {"id": "1", "title": "Introduction", "aliases": [], "parent": None, "role": "introduction", "page": 1},
            {"id": "2", "title": "Methods", "aliases": [], "parent": None, "role": "methods", "page": 2},
            {"id": "2.1", "title": "System Design", "aliases": [], "parent": "2", "role": "methods", "page": 3},
        ]}
        _, report = evaluate_studio_markdown(TEXT, reference)
        self.assertEqual(report["metrics"]["heading_number_and_identity"]["f1"], 1)
        self.assertEqual(report["metrics"]["parent_accuracy_on_matched"]["value"], 1)
        self.assertIsNone(report["metrics"]["role_accuracy_on_matched"]["value"])
        self.assertTrue(all(row["role_correct"] is None for row in report["matches"]))
