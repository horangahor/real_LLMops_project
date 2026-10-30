import copy
import unittest

from evaluation.extraction.v2.evaluate import coverage


def fixture():
    return ({"items": [{"id": "F1"}, {"id": "F2"}], "writing_fact_ids": ["F1"]},
            {"facts": [{"id": "R1"}, {"id": "R2"}]},
            {"reference_matches": [
                {"reference_id": "R1", "verdict": "full", "prediction_ids": ["F1", "F2"]},
                {"reference_id": "R2", "verdict": "partial", "prediction_ids": ["F1"]}]})


class EvidenceV2EvaluationTests(unittest.TestCase):
    def test_full_candidate_union_does_not_imply_full_writing_coverage(self):
        result = coverage(*fixture())
        self.assertEqual(result["value"], 0.5)
        self.assertEqual(result["writing_full_strict"], 0)

    def test_missing_duplicate_or_unknown_matches_cannot_shrink_the_denominator(self):
        for mutation in ("missing", "duplicate", "unknown"):
            prediction, reference, annotations = fixture()
            rows = annotations["reference_matches"]
            if mutation == "missing":
                rows.pop()
            elif mutation == "duplicate":
                rows.append(copy.deepcopy(rows[0]))
            else:
                rows[0]["prediction_ids"] = ["missing"]
            with self.assertRaises(ValueError):
                coverage(prediction, reference, annotations)

    def test_full_without_evidence_is_invalid(self):
        prediction, reference, annotations = fixture()
        annotations["reference_matches"][0]["prediction_ids"] = []
        with self.assertRaises(ValueError):
            coverage(prediction, reference, annotations)

    def test_duplicate_references_are_rejected(self):
        prediction, reference, annotations = fixture()
        reference["facts"].append(copy.deepcopy(reference["facts"][0]))
        with self.assertRaises(ValueError):
            coverage(prediction, reference, annotations)


if __name__ == "__main__":
    unittest.main()
