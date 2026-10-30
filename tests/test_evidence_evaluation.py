import copy
import unittest

from evaluation.extraction.benchmark.evaluate import score


def fixture():
    prediction = {"source": {"sha256": "source"}, "items": [
        {"id": "F1", "kind": "result", "support": "supported", "measurements": [{"value": "12ms"}]},
        {"id": "F2", "kind": "method", "support": "supported", "rejected_measurements": [{"value": "1e-6"}]}],
        "writing_fact_ids": ["F1", "F2"], "diagnostics": {"excluded_selected_ids": []},
        "research": {"open_questions": ["별도 질문"]}}
    reference = {"source_sha256": "source", "facts": [{"id": "R1", "page": 1, "kind": "result"},
        {"id": "R2", "page": 1, "kind": "method"}, {"id": "R3", "page": 1, "kind": "limitation"}]}
    facts = [{"id": key, "document_support": verdict, "linked_support": verdict,
              "claim_strength_preserved": True, "acceptable_kinds": [kind]}
             for key, verdict, kind in (("F1", "full", "result"), ("F2", "partial", "method"))]
    measured = [{"id": key, "fact_id": fact, "state": state, "pdf_grounded": True,
                 "measurement_applicable": True, "value_unit_correct": True, "condition_correct": True,
                 "linked_value_supported": True} for key, fact, state in (("F1.a0", "F1", "accepted"), ("F2.r0", "F2", "rejected"))]
    matches = [{"reference_id": "R1", "verdict": "full", "prediction_ids": ["F1"], "question_verdict": "missing", "question_indices": []},
        {"reference_id": "R2", "verdict": "partial", "prediction_ids": ["F2"], "question_verdict": "missing", "question_indices": []},
        {"reference_id": "R3", "verdict": "missing", "prediction_ids": [], "question_verdict": "full", "question_indices": [0]}]
    annotation = {"source_sha256": "source", "prediction_sha256": "prediction", "fact_reviews": facts,
                  "measurement_reviews": measured, "reference_matches": matches}
    protocol = {"source_sha256": "source", "prediction_sha256": "prediction", "sampling": {"pages": [1]}}
    return prediction, reference, annotation, protocol


class EvidenceEvaluationTests(unittest.TestCase):
    def test_partial_facts_do_not_count_as_full_and_questions_do_not_gain_source_linked_credit(self):
        result = score(*fixture())["metrics"]
        self.assertEqual(result["candidate_document_faithfulness"]["value"], .5)
        self.assertEqual(result["sampled_required_fact_coverage"]["value"], 1 / 3)
        self.assertEqual(result["sampled_required_fact_any_text_coverage"]["value"], 2 / 3)
        self.assertEqual(result["writing_gate_document_faithfulness"]["value"], .5)

    def test_correct_source_value_and_scalar_format_are_separate_metrics(self):
        metrics = score(*fixture())["metrics"]
        self.assertEqual(metrics["accepted_measurement_tuple_correct"]["value"], 1)
        self.assertEqual(metrics["accepted_scalar_value_format"]["value"], 0)
        self.assertEqual(metrics["quarantined_correct_measurement_tuples"]["value"], 1)

    def test_missing_or_duplicate_annotation_cannot_silently_shrink_denominator(self):
        for remove in (True, False):
            pred, ref, annotation, protocol = fixture()
            if remove:
                annotation["fact_reviews"].pop()
            else:
                annotation["fact_reviews"].append(copy.deepcopy(annotation["fact_reviews"][0]))
            with self.assertRaises(ValueError):
                score(pred, ref, annotation, protocol)

    def test_different_source_or_prediction_hash_is_rejected(self):
        for key in ("source_sha256", "prediction_sha256"):
            pred, ref, annotation, protocol = fixture()
            annotation[key] = "other"
            with self.assertRaises(ValueError):
                score(pred, ref, annotation, protocol)

    def test_unknown_prediction_or_question_ids_are_rejected(self):
        for key in ("prediction_ids", "question_indices"):
            pred, ref, annotation, protocol = fixture()
            annotation["reference_matches"][0][key] = ["unknown"] if key == "prediction_ids" else [99]
            with self.assertRaises(ValueError):
                score(pred, ref, annotation, protocol)

    def test_string_boolean_is_rejected(self):
        pred, ref, annotation, protocol = fixture()
        annotation["measurement_reviews"][0]["value_unit_correct"] = "false"
        with self.assertRaises(ValueError):
            score(pred, ref, annotation, protocol)


if __name__ == "__main__":
    unittest.main()
