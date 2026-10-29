import json
import unittest

from golden_evaluation import evaluate_outline
from studio_json_evaluation import decode_document, explicit_outline


class StudioJsonEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.document = {"sections": [
            {"id": "a", "title": "1 Introduction", "parent_id": None, "evidence_ids": ["s1"]},
            {"id": "b", "title": "1.1 Problem", "parent_id": "a", "evidence_ids": ["s2"]}],
            "evidence": [{"evidence_id": "s1", "page": 1}, {"evidence_id": "s2", "page": 2}]}
        self.reference = {"items": [
            {"id": "1", "title": "Introduction", "aliases": [], "role": "introduction", "parent": None, "page": 1},
            {"id": "1.1", "title": "Problem", "aliases": [], "role": "introduction", "parent": "1", "page": 2}]}

    def test_transport_wrapped_json_is_decoded_without_new_content(self):
        decoded, status = decode_document(json.dumps(json.dumps(self.document)))
        self.assertEqual(decoded, self.document)
        self.assertTrue(status["strict_valid"])

    def test_invalid_raw_control_requires_explicit_diagnostic_mode(self):
        text = '{"quote":"first\nsecond"}'
        with self.assertRaises(json.JSONDecodeError):
            decode_document(text)
        decoded, status = decode_document(text, diagnostic_controls=True)
        self.assertEqual(decoded["quote"], "first\nsecond")
        self.assertFalse(status["strict_valid"])
        self.assertIsNotNone(status["error"])

    def test_native_parent_and_evidence_pages_are_used(self):
        result = evaluate_outline(explicit_outline(self.document), self.reference)
        self.assertEqual(result["metrics"]["parent_accuracy_on_matched"]["value"], 1)
        self.assertEqual(result["metrics"]["page_accuracy_on_matched"]["value"], 1)

    def test_wrong_parent_is_not_repaired_from_number(self):
        self.document["sections"][1]["parent_id"] = None
        result = evaluate_outline(explicit_outline(self.document), self.reference)
        self.assertEqual(result["metrics"]["child_parent_accuracy_on_matched_children"]["value"], 0)

    def test_missing_evidence_is_not_filled_from_reference(self):
        self.document["sections"][1]["evidence_ids"] = ["missing"]
        derived = explicit_outline(self.document)
        self.assertEqual(len(derived["missing_evidence_links"]), 1)
        self.assertIsNone(derived["observed_outline"][0]["children"][0]["source_pages"])

    def test_duplicate_ids_and_cycles_fail_explicitly(self):
        self.document["sections"][1]["id"] = "a"
        with self.assertRaises(ValueError):
            explicit_outline(self.document)
        self.document["sections"][1]["id"] = "b"
        self.document["sections"][0]["parent_id"] = "b"
        with self.assertRaises(ValueError):
            explicit_outline(self.document)

    def test_headings_schema_uses_its_own_pages(self):
        source = {"headings": [{"evidence_id": "h1", "heading_text": "1 Introduction", "parent_evidence_id": None, "page": 4}]}
        self.assertEqual(explicit_outline(source)["observed_outline"][0]["source_pages"], [4])
