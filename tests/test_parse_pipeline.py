"""Source anchoring, false-heading rejection, cache integrity, and structured guidance."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import document_parse as client
import paper_structure as analysis
from paper_outline import extract_numbered_outline
from structure_profiles import PROFILE_EXAMPLE


def element(identifier, text, category="heading1", page=1):
    return {"id": identifier, "page": page, "category": category,
            "content": {"text": text}, "coordinates": [{"x": 0.1, "y": 0.2}]}


def document():
    return {"model": "document-parse-260930", "elements": [
        element(1, "1. Introduction"),
        element(2, "This paragraph was incorrectly tagged as a heading."),
        element(3, "2. Methods", "paragraph", 2),
        element(4, "2.1. Experimental setup", page=2),
        element(5, "2.1.1. Sample preparation", "paragraph", 2),
        element(6, "computed as:", page=2),
        element(7, "z = Model(x)", page=2),
        element(8, "Table 1. Comparison of models", "caption", 2),
        element(9, "References", page=3),
        element(10, "1. Smith et al.", "paragraph", 3),
    ]}


class ParsePipelineTests(unittest.TestCase):
    def test_same_parse_recovers_paragraph_headings_without_promoting_prose_or_equations(self):
        outline = extract_numbered_outline(document())
        self.assertEqual([x["number"] for x in outline["selected_headings"]], ["1", "2", "2.1", "2.1.1"])
        child = outline["observed_outline"][1]["children"][0]["children"][0]
        self.assertEqual(child["title"], "2.1.1 Sample preparation")
        self.assertEqual(child["source_pages"], [2])
        self.assertEqual(child["source_element_id"], "p2:e5")

    def test_missing_parent_and_ambiguous_number_are_rejected_without_inventing_sections(self):
        for items in ([element(1, "1 Introduction"), element(2, "2.1 Methods")],
                      [element(1, "1 Introduction"), element(2, "1 Different section")]):
            with self.assertRaises(ValueError):
                extract_numbered_outline({"elements": items})

    def test_plain_numeric_body_and_roman_only_papers_are_not_silently_accepted(self):
        for item in (element(1, "12 samples were measured", "paragraph"),
                     element(1, "I. Introduction")):
            with self.assertRaisesRegex(ValueError, "자동 분석 범위 밖"):
                extract_numbered_outline({"elements": [item]})

    def test_duplicate_and_paragraph_number_conflict_do_not_duplicate_real_headings(self):
        outline = extract_numbered_outline({"elements": [
            element(1, "1 Introduction"), element(2, "1 Introduction", page=2),
            element(3, "1. First step", "paragraph", 2), element(4, "2 Methods", page=2),
        ]})
        self.assertEqual(len(outline["selected_headings"]), 2)
        self.assertEqual(len(outline["rejected_candidates"]), 2)

    def test_html_only_content_and_wrapped_heading_retain_the_source_page(self):
        item = element(1, "", page=4)
        item["content"] = {"html": "<h1>1. A wrapped<br>section title</h1>"}
        result = extract_numbered_outline({"elements": [item]})
        self.assertEqual(result["selected_headings"][0]["title"], "1 A wrapped section title")
        self.assertEqual(result["observed_outline"][0]["source_pages"], [4])

    def test_wrapped_paragraph_titles_and_larger_undotted_titles_are_recovered(self):
        intro = element(1, "1 Introduction", "paragraph")
        intro["content"]["html"] = "<p style='font-size:20px'>1 Introduction</p>"
        body = element(2, "Body text with ordinary prose. " * 12, "paragraph")
        body["content"]["html"] = "<p style='font-size:16px'>Body</p>"
        wrapped = element(3, "1.1 Does the system work with\nmultiple inputs?", "paragraph")
        result = extract_numbered_outline({"elements": [intro, body, wrapped]})
        self.assertEqual([x["title"] for x in result["selected_headings"]],
                         ["1 Introduction", "1.1 Does the system work with multiple inputs?"])

    def test_page_numbers_and_authors_misclassified_as_headings_are_excluded(self):
        header1 = element(1, "2 Example Author et al.", page=2)
        header2 = element(2, "4 Example Author et al.", page=4)
        for header in (header1, header2):
            header["coordinates"] = [{"x": 0.2, "y": 0.11}, {"x": 0.4, "y": 0.13}]
        result = extract_numbered_outline({"elements": [element(3, "1 Introduction"), header1, header2]})
        self.assertEqual(len(result["selected_headings"]), 1)
        self.assertEqual(len(result["rejected_candidates"]), 2)

    def test_raw_parse_is_preserved_cached_and_bound_to_pdf_and_settings(self):
        response = Mock(status_code=200)
        response.json.return_value = document()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pdf = root / "sample.pdf"
            pdf.write_bytes(b"original PDF bytes")
            run = root / "run"
            with patch.object(client, "UPSTAGE_API_KEY", "test-key"), patch.object(client.requests, "post", return_value=response) as post:
                first = client.parse_document(pdf, run)
                second = client.parse_document(pdf, run)
            self.assertEqual(first, second)
            self.assertEqual(post.call_count, 1)
            self.assertEqual(json.loads((run / "parse-response.json").read_text(encoding="utf-8")), document())
            self.assertEqual(post.call_args.kwargs["data"]["mode"], "standard")
            self.assertIn("coordinates", post.call_args.kwargs["data"])
            with self.assertRaisesRegex(ValueError, "원본 또는 설정"):
                client.parse_document(pdf, run, mode="enhanced")
            pdf.write_bytes(b"changed PDF bytes")
            with self.assertRaisesRegex(ValueError, "원본 또는 설정"):
                client.parse_document(pdf, run)

    def test_tampered_parse_cache_and_invalid_elements_are_rejected(self):
        response = Mock(status_code=200)
        response.json.return_value = document()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pdf = root / "sample.pdf"
            pdf.write_bytes(b"pdf")
            with patch.object(client, "UPSTAGE_API_KEY", "test-key"), patch.object(client.requests, "post", return_value=response):
                client.parse_document(pdf, root / "run")
            (root / "run/parse-response.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "캐시가 변경"):
                client.parse_document(pdf, root / "run")
        invalid = document()
        invalid["elements"][0]["page"] = True
        with self.assertRaises(ValueError):
            client.validate_parse(invalid)

    def test_guidance_cannot_add_headings_change_pages_or_skip_source_ids(self):
        outline = extract_numbered_outline(document())
        content = copy.deepcopy(PROFILE_EXAMPLE)
        content["section_roles"] = [{"element_id": x["element_id"], "role": "methods"}
                                    for x in outline["selected_headings"]]
        content["observed_outline"] = [{"title": "invented", "source_pages": [99]}]
        profile = analysis.build_profile(json.dumps(content), outline, "source.pdf")
        self.assertEqual(profile["observed_outline"][0]["title"], "1 Introduction")
        self.assertEqual(profile["observed_outline"][0]["source_pages"], [1])
        content["section_roles"].pop()
        with self.assertRaisesRegex(ValueError, "누락·추가"):
            analysis.build_profile(json.dumps(content), outline, "source.pdf")
        content["section_roles"].append({"element_id": "invented", "role": "methods"})
        with self.assertRaises(ValueError):
            analysis.build_profile(json.dumps(content), outline, "source.pdf")

    def test_guidance_uses_strict_json_schema_and_raw_response_is_saved(self):
        response = Mock(status_code=200)
        response.json.return_value = {"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]}
        schema = analysis.guidance_schema(extract_numbered_outline(document())["selected_headings"])
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "response.json"
            with patch.object(analysis, "UPSTAGE_API_KEY", "test-key"), patch.object(analysis.requests, "post", return_value=response) as post:
                analysis.run_chat("system", "source", schema=schema, response_path=target)
            output = post.call_args.kwargs["json"]["response_format"]
            self.assertEqual(output["type"], "json_schema")
            self.assertTrue(output["json_schema"]["strict"])
            self.assertTrue(target.is_file())

    def test_source_specific_identifiers_must_not_be_copied_into_reusable_guidance(self):
        source = {"elements": [element(1, "ABC-Net uses XYZ inputs.")]}
        content = copy.deepcopy(PROFILE_EXAMPLE)
        content["style_rules"] = ["ABC-Net의 입력 조건을 설명한다."]
        with self.assertRaisesRegex(ValueError, "원문 전용 식별자"):
            analysis.validate_reusable_guidance(content, source)
        content["style_rules"] = ["제안 방법의 입력 조건을 설명한다."]
        content["not_to_transfer"] = ["ABC-Net", "XYZ"]
        analysis.validate_reusable_guidance(content, source)

    def test_guidance_correction_changes_only_reusable_prose_and_is_bounded(self):
        source = document()
        source["elements"].append(element(11, "ABC-Net model"))
        outline = extract_numbered_outline(source)
        content = copy.deepcopy(PROFILE_EXAMPLE)
        content["section_roles"] = [{"element_id": item["element_id"], "role": "methods"}
                                    for item in outline["selected_headings"]]
        content["style_rules"] = ["ABC-Net의 구조를 설명한다."]
        replacement = {key: copy.deepcopy(content[key]) for key in ("style_rules", "section_guidelines")}
        replacement["style_rules"] = ["제안 방법의 구조를 설명한다."]
        replacement["section_roles"] = []
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(analysis, "run_chat", return_value=json.dumps(replacement)) as call:
                profile, accepted, _ = analysis.checked_guidance(json.dumps(content), outline, "source.pdf",
                                                                  source, analysis.guidance_schema(outline["selected_headings"]), Path(temporary))
            self.assertEqual(call.call_count, 1)
            self.assertEqual(profile["title"], content["title"])
            self.assertEqual(json.loads(accepted)["section_roles"], content["section_roles"])
            with patch.object(analysis, "run_chat", return_value=json.dumps({key: content[key] for key in ("style_rules", "section_guidelines")})) as call:
                with self.assertRaises(analysis.GuidanceTransferError):
                    analysis.checked_guidance(json.dumps(content), outline, "source.pdf", source,
                                               analysis.guidance_schema(outline["selected_headings"]), Path(temporary))
            self.assertEqual(call.call_count, 1)


if __name__ == "__main__":
    unittest.main()
