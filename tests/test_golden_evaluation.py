import copy
import hashlib
import unittest
from pathlib import Path
from unittest.mock import patch

from golden_evaluation import evaluate_outline, select_profile, verify_source


def node(title, role, children=None, pages=None):
    return {"title": title, "role": role, "children": children or [], "source_pages": pages}


class GoldenEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.reference = {"items": [
            {"id": "1", "title": "Introduction", "aliases": ["서론"], "parent": None,
             "role": "introduction", "page": 1},
            {"id": "2", "title": "Methods", "aliases": ["방법"], "parent": None,
             "role": "methods", "page": 2},
            {"id": "2.1", "title": "System Design", "aliases": [], "parent": "2",
             "role": "methods", "page": 3},
        ]}
        self.profile = {"observed_outline": [
            node("1 서론 (Introduction)", "introduction", pages=[1]),
            node("2 Methods", "methods", [node("2.1 System Design", "methods", pages=[3])], [2]),
        ]}

    def test_correct_tree_scores_one(self):
        result = evaluate_outline(self.profile, self.reference)
        self.assertEqual(result["metrics"]["heading_number_and_identity"]["f1"], 1)
        self.assertEqual(result["metrics"]["fully_correct_item_recall"]["value"], 1)
        self.assertEqual(result["metrics"]["page_accuracy_on_matched"]["value"], 1)

    def test_missing_subsection_cannot_hide_behind_perfect_conditional_scores(self):
        self.profile["observed_outline"][1]["children"] = []
        metrics = evaluate_outline(self.profile, self.reference)["metrics"]
        self.assertEqual(metrics["heading_identity"]["precision"]["value"], 1)
        self.assertAlmostEqual(metrics["heading_identity"]["recall"]["value"], 2/3)
        self.assertIsNone(metrics["child_parent_accuracy_on_matched_children"]["value"])
        self.assertEqual(metrics["exact_subsection_recall"]["value"], 0)

    def test_wrong_number_is_detected_even_with_correct_title(self):
        self.profile["observed_outline"][0]["title"] = "6 서론 (Introduction)"
        result = evaluate_outline(self.profile, self.reference)
        self.assertEqual(result["metrics"]["heading_identity"]["f1"], 1)
        self.assertAlmostEqual(result["metrics"]["heading_number_and_identity"]["precision"]["value"], 2/3)
        self.assertFalse(result["matches"][0]["number_correct"])

    def test_correct_number_with_wrong_title_is_not_a_match(self):
        self.profile["observed_outline"][0]["title"] = "1 Imaginary Heading"
        result = evaluate_outline(self.profile, self.reference)
        self.assertEqual(result["matched_count"], 2)
        self.assertEqual(result["unmatched_predictions"][0]["reason"], "unknown_title")

    def test_lifted_child_keeps_identity_but_fails_parent(self):
        child = self.profile["observed_outline"][1]["children"].pop()
        self.profile["observed_outline"].append(child)
        result = evaluate_outline(self.profile, self.reference)
        self.assertEqual(result["metrics"]["heading_number_and_identity"]["f1"], 1)
        self.assertEqual(result["metrics"]["child_parent_accuracy_on_matched_children"]["value"], 0)
        self.assertAlmostEqual(result["metrics"]["fully_correct_item_recall"]["value"], 2/3)

    def test_extra_and_duplicate_titles_reduce_precision(self):
        self.profile["observed_outline"].extend([
            node("1 Introduction", "introduction"), node("7 Imaginary Heading", "other")])
        result = evaluate_outline(self.profile, self.reference)
        self.assertEqual(result["matched_count"], 3)
        self.assertEqual(result["metrics"]["heading_identity"]["precision"]["value"], 3/5)
        self.assertEqual({row["reason"] for row in result["unmatched_predictions"]}, {"duplicate", "unknown_title"})

    def test_role_mismatch_is_separate_from_title_match(self):
        self.profile["observed_outline"][1]["role"] = "evaluation"
        metrics = evaluate_outline(self.profile, self.reference)["metrics"]
        self.assertEqual(metrics["heading_identity"]["f1"], 1)
        self.assertAlmostEqual(metrics["role_accuracy_on_matched"]["value"], 2/3)

    def test_ambiguous_title_is_not_arbitrarily_assigned(self):
        self.profile["observed_outline"][0]["title"] = "1 Introduction (Methods)"
        result = evaluate_outline(self.profile, self.reference)
        self.assertEqual(result["matched_count"], 2)
        self.assertEqual(result["unmatched_predictions"][0]["reason"], "ambiguous")

    def test_empty_prediction_has_no_fake_perfect_score(self):
        metrics = evaluate_outline({"observed_outline": []}, self.reference)["metrics"]
        self.assertIsNone(metrics["heading_identity"]["precision"]["value"])
        self.assertEqual(metrics["heading_identity"]["recall"]["value"], 0)
        self.assertEqual(metrics["heading_identity"]["f1"], 0)
        self.assertIsNone(metrics["role_accuracy_on_matched"]["value"])

    def test_conflicting_reference_aliases_are_rejected(self):
        self.reference["items"][1]["aliases"].append("Introduction")
        with self.assertRaisesRegex(ValueError, "충돌"):
            evaluate_outline(self.profile, self.reference)

    def test_unknown_parent_does_not_count_as_a_root_match(self):
        intro = self.profile["observed_outline"].pop(0)
        self.profile["observed_outline"].insert(0, node("8 Unknown", "other", [intro]))
        result = evaluate_outline(self.profile, self.reference)
        self.assertFalse(next(row for row in result["matches"] if row["reference_id"] == "1")["parent_correct"])

    def test_missing_pages_and_wrong_pages_are_not_correct(self):
        self.profile["observed_outline"][0]["source_pages"] = None
        self.profile["observed_outline"][1]["source_pages"] = [7]
        result = evaluate_outline(self.profile, self.reference)
        self.assertEqual(result["metrics"]["page_accuracy_on_matched"]["value"], 1/3)

    def test_profile_selection_handles_windows_paths_and_rejects_duplicates(self):
        profile = {"file": r"C:\samples\golden.pdf"}
        self.assertEqual(select_profile([profile], "golden.pdf"), profile)
        with self.assertRaises(ValueError):
            select_profile([profile, copy.deepcopy(profile)], "golden.pdf")

    def test_changed_source_is_rejected(self):
        path = Path("source.pdf")
        reference = {"source_sha256": hashlib.sha256(b"first source").hexdigest()}
        with patch.object(Path, "read_bytes", return_value=b"first source"):
            verify_source(reference, path)
        with patch.object(Path, "read_bytes", return_value=b"changed source"):
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                verify_source(reference, path)

    def test_declared_real_out_of_scope_title_is_not_a_false_positive(self):
        self.reference["excluded_titles"] = ["References"]
        self.profile["observed_outline"].append(node("References", "other"))
        result = evaluate_outline(self.profile, self.reference)
        self.assertEqual(result["raw_prediction_count"], 4)
        self.assertEqual(result["prediction_count"], 3)
        self.assertEqual(len(result["ignored_predictions"]), 1)
        self.assertEqual(result["metrics"]["heading_identity"]["f1"], 1)

    def test_unknown_unnumbered_summaries_are_still_false_positives(self):
        self.reference["excluded_titles"] = ["References"]
        self.profile["observed_outline"].append(node("Imaginary paragraph summary", "introduction"))
        result = evaluate_outline(self.profile, self.reference)
        self.assertEqual(result["prediction_count"], 4)
        self.assertEqual(result["metrics"]["heading_identity"]["false_positive"], 1)

    def test_invented_number_on_excluded_title_is_not_ignored(self):
        self.reference["excluded_titles"] = ["References"]
        self.profile["observed_outline"].append(node("7 References", "other"))
        result = evaluate_outline(self.profile, self.reference)
        self.assertEqual(result["ignored_predictions"], [])
        self.assertEqual(result["metrics"]["heading_identity"]["false_positive"], 1)

    def test_reference_cannot_exclude_a_scored_heading(self):
        self.reference["excluded_titles"] = ["Introduction"]
        with self.assertRaisesRegex(ValueError, "충돌"):
            evaluate_outline(self.profile, self.reference)


if __name__ == "__main__":
    unittest.main()
