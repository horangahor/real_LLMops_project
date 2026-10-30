import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

from research_extract_v2 import extract_block, ground_fact, verify_block, writing_eligible
from research_sources import blank_pages
from research_values import missing_numbers, normalize_measurement


def elements():
    return {"p1:e1": {"element_id": "p1:e1", "page": 1, "category": "paragraph", "origin": "standard_parse",
                     "text": "복사 횟수 19→11회, 시간 12.500000ms. eps=10^-6. 버전 V4.12.7."}}


def fact():
    return {"statement": "복사 횟수는19회에서11회로감소했다.", "limits": "단일실행예시다.",
            "kind": "result", "claim_status": "observed", "source_origin": "measurement_log",
            "conditions": [], "observations": [], "parameters": [], "element_ids": ["p1:e1"],
            "measurements": [{"metric": "실행 시간", "value": "12.5ms", "value_kind": "scalar",
                              "unit": "ms", "condition": "단일 실행", "element_ids": ["p1:e1"]}]}


class ResearchV2Tests(unittest.TestCase):
    def test_scientific_math_and_superscript_notation_are_equivalent_without_changing_values(self):
        for source in ("eps=10^-6", "eps=10^{-6}", "eps=10⁻⁶", "eps=0.000001"):
            self.assertEqual(missing_numbers("epsilon 1e-06", source), [])

    def test_decimal_comma_and_trailing_zero_are_normalized(self):
        self.assertEqual(missing_numbers("시간229.6918ms", "Elapsed:229,691800 ms"), [])
        result = normalize_measurement({"value": "229.691800 ms", "unit": "ms", "value_kind": "scalar"}, "229,691800 ms")
        self.assertEqual(result["value"], "229.6918")
        self.assertEqual(result["raw_value"], "229.691800 ms")

    def test_range_is_distinct_from_an_invalid_compound_scalar(self):
        result = normalize_measurement({"value": "5~10ms", "unit": "ms", "value_kind": "range"}, "5 ~ 10ms")
        self.assertEqual(result["normalization_status"], "normalized")
        with self.assertRaises(ValueError):
            normalize_measurement({"value": "5ms (10%)", "unit": "ms", "value_kind": "scalar"}, "5ms (10%)")

    def test_single_literal_mistyped_as_range_is_preserved_with_audit(self):
        result = normalize_measurement({"value": "12.500000", "unit": "ms", "value_kind": "range"}, "12.5ms")
        self.assertEqual(result["value"], "12.5")
        self.assertEqual(result["value_kind"], "scalar")
        self.assertEqual(result["declared_value_kind"], "range")
        with self.assertRaises(ValueError):
            normalize_measurement({"value": "0.93", "unit": "ratio", "value_kind": "range"}, "93%")

    def test_versions_are_checked_as_identifiers(self):
        self.assertEqual(missing_numbers("버전 V4.12.7", elements()["p1:e1"]["text"]), [])
        self.assertEqual(missing_numbers("버전 V4.12.8", elements()["p1:e1"]["text"]), ["V4.12.8"])
        self.assertEqual(missing_numbers("v1-1-3의방법", "v1-1-3의 방법을 바꿨다"), [])

    def test_numeric_repair_is_bound_to_failed_items_instead_of_reextracting_the_whole_block(self):
        bad = fact()
        bad["statement"] = "복사횟수가14회에서8회로줄었다."
        response = {"title": "모의연구", "facts": [bad], "coverage": {"p1": {"status": "extracted", "note": "검토"}}}
        engine = Mock()
        engine.call.side_effect = [response, {"repairs": {"r0": [fact()]}}]
        result = extract_block(engine, Path("unused"), elements(), [1], 0)
        self.assertEqual(len(result["facts"]), 1)
        self.assertEqual(result["facts"][0]["numeric_issues"], [])
        self.assertEqual(set(engine.call.call_args.args[3]["rejected_candidates"]), {"r0"})
        self.assertEqual(set(engine.call.call_args.args[4]["properties"]["repairs"]["properties"]), {"r0"})
        self.assertEqual(len(result["rejected_initial"]), 1)

    def test_read_timeout_splits_only_failed_pages_and_preserves_coverage(self):
        with TemporaryDirectory() as temporary:
            folder = Path(temporary)
            source = elements()
            source["p2:e2"] = {**source["p1:e1"], "page": 2, "element_id": "p2:e2"}
            engine = Mock()
            def respond(root, name, system, packet, schema):
                if name == "extract-block-000":
                    responses = folder / "responses"
                    responses.mkdir()
                    (responses / (name + "-" + "a" * 20 + ".native.json")).write_text(json.dumps({"request_error": "ReadTimeout"}))
                    raise RuntimeError("timeout")
                page = packet["target_pages"][0]
                value = fact()
                value["element_ids"] = [f"p{page}:e{page}"]
                value["measurements"] = []
                return {"title": "모의연구", "facts": [value], "coverage": {f"p{page}": {"status": "extracted", "note": "검토"}}}
            engine.call.side_effect = respond
            result = extract_block(engine, folder, source, [1, 2], 0)
            self.assertEqual(set(result["coverage"]), {"p1", "p2"})
            self.assertEqual(len(result["facts"]), 2)
            self.assertEqual(engine.call.call_count, 3)

    def test_correct_runtime_cannot_mask_invented_counts_in_the_statement(self):
        value = fact()
        value["statement"] = "복사횟수14회에서8회로감소하고시간은12.5ms였다."
        item = ground_fact(value, elements())
        self.assertTrue(item["numeric_issues"])
        item["id"] = "F1"
        engine = Mock()
        result = verify_block(engine, Path("unused"), [item], 0)[0]
        engine.call.assert_not_called()
        self.assertFalse(writing_eligible(result))
        self.assertEqual(result["support"], "unsupported")

    def test_invalid_extra_measurement_does_not_discard_a_supported_method(self):
        value = fact()
        value["kind"] = "method"
        value["measurements"][0]["value"] = "99.9"
        item = ground_fact(value, elements())
        self.assertEqual(item["numeric_issues"], [])
        self.assertEqual(item["measurements"], [])
        self.assertEqual(len(item["rejected_measurements"]), 1)
        item["id"] = "F1"
        engine = Mock()
        engine.call.return_value = {"checks": {"F1": {"support": "supported", "claim_status": "documented_method",
                                                      "source_origin": "research_note", "note": "주진술은원문에있다."}}}
        result = verify_block(engine, Path("unused"), [item], 0)[0]
        self.assertTrue(writing_eligible(result))

    def test_ai_advice_is_not_admitted_as_implemented_research(self):
        item = {"support": "supported", "numeric_issues": [], "claim_status": "documented_method", "source_origin": "ai_advice"}
        self.assertFalse(writing_eligible(item))
        item.update(source_origin="quoted_instruction", claim_status="planned")
        self.assertTrue(writing_eligible(item))

    def test_all_conditions_are_checked_and_other_sources_cannot_be_used(self):
        value = fact()
        value["conditions"] = ["배치1024"]
        self.assertTrue(ground_fact(value, elements())["numeric_issues"])
        value["element_ids"] = ["p2:missing"]
        with self.assertRaises(ValueError):
            ground_fact(value, elements())

    def test_blank_region_detection_is_content_driven_without_document_specific_pages(self):
        document = {"elements": [{"page": 7, "category": "list", "content": {"text": ""}, "coordinates": [1]},
                                 {"page": 19, "category": "table", "content": {"text": ""}, "coordinates": [1]},
                                 {"page": 3, "category": "page_footer", "content": {"text": ""}, "coordinates": [1]},
                                 {"page": 4, "category": "paragraph", "content": {"text": "원문"}, "coordinates": [1]}]}
        self.assertEqual(blank_pages(document), [7, 19])


if __name__ == "__main__":
    unittest.main()
