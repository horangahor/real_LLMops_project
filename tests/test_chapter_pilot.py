import unittest

from evaluation.writing.run_chapter_pilot import candidate_accepted, check_candidate
from paper_context import build_contexts
from test_paper_context import fixture


class ChapterPilotTests(unittest.TestCase):
    def setUp(self):
        plan, research, catalog = fixture()
        contexts = build_contexts(plan, research, catalog)
        self.packet = contexts["sections"]["methods"]
        self.parts = contexts["subsections"]["methods"]

    def test_whole_chapter_in_first_part_is_rejected_despite_model_approval(self):
        value = {"parts": {"p0": "### 1.1 조건 비교\n\n비교했다. [근거:A]\n\n### 1.2 적용 범위\n\n범위다. [근거:C]", "p1": ""}}
        body, checks = check_candidate(value, self.packet, self.parts)
        self.assertIn("### 1.2", body)
        self.assertNotEqual(checks["chapter_format_and_ids"], "pass")
        self.assertNotEqual(checks["part_format_and_ids"]["p1"], "pass")
        self.assertFalse(candidate_accepted(checks, {"approved": True}))

    def test_chapter_allowed_evidence_can_still_violate_part_allocation(self):
        _, checks = check_candidate({"parts": {"p0": "범위다. [근거:C]", "p1": "범위다. [근거:C]"}}, self.packet, self.parts)
        self.assertEqual(checks["chapter_format_and_ids"], "pass")
        self.assertNotEqual(checks["part_format_and_ids"]["p0"], "pass")
        self.assertFalse(candidate_accepted(checks, {"approved": True}))

    def test_valid_parts_and_valid_semantic_review_are_both_required(self):
        _, checks = check_candidate({"parts": {"p0": "비교했다. [근거:A] [근거:B]", "p1": "범위다. [근거:C]"}}, self.packet, self.parts)
        self.assertTrue(candidate_accepted(checks, {"approved": True}))
        self.assertFalse(candidate_accepted(checks, {"approved": False}))
        self.assertFalse(candidate_accepted(checks, {"approved": True, "review_contract_error": "invalid"}))


if __name__ == "__main__":
    unittest.main()
