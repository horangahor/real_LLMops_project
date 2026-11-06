import copy
import re
import unittest

from editorial_patch import apply_editorial_patch
from paper_context import build_contexts
from paper_display import plain_table_text, readable_prose
from test_editorial_patch import keep_slots, setup_patch
from test_planned_paper import plan, research
from writing_length import apply_length_targets
from writing_policy import attach_policy, length_issues, load_policy


class ReadabilityLimitTests(unittest.TestCase):
    def test_caps_limit_total_allocation_without_filling_short_structure_to_paper_target(self):
        value, data = plan(5), research()
        contexts = build_contexts(value, data, {})
        original = copy.deepcopy(data)
        attach_policy(contexts, load_policy())
        report = apply_length_targets(value, contexts, 30000)
        self.assertLess(report["allocated_target_chars"], report["paper_target_chars"])
        self.assertTrue(all(row["target_chars"] <= 1600 and row["max_chars"] == 2000 for row in report["subsections"]))
        for packet in contexts["sections"].values():
            self.assertLessEqual(sum(a["writing_budget"]["target_chars"] for a in packet["subsection_assignments"].values()), 4800)
        self.assertEqual(data, original)

    def test_absolute_subsection_and_section_caps_work_even_with_loose_relative_tolerance(self):
        packet = {"composition_policy": {"length_tolerance_ratio": 10, "max_subsection_chars": 2000, "max_section_chars": 6000},
                  "subsection_assignments": {f"p{i}": {"writing_budget": {"target_chars": 2000, "max_chars": 2000}} for i in range(4)}}
        body = {"s": {"parts": {f"p{i}": "x" * 1750 for i in range(4)}}}
        self.assertFalse(length_issues(body, {"s": packet}, "section"))
        self.assertFalse(length_issues(body, {"s": packet}, "paper"))
        issues = length_issues(body, {"s": packet}, "subsection")
        self.assertEqual(len(issues), 1)
        self.assertIn("절 전체", issues[0]["reason"])
        body["s"]["parts"] = {"p0": "x" * 2001}
        self.assertTrue(any("허용 상한 2000" in i["reason"] for i in length_issues(body, {"s": packet}, "subsection")))

    def test_editorial_join_is_not_controlled_by_writer_length_limits(self):
        packet, previous, _, parts, origins = setup_patch()
        packet["composition_policy"] = {"max_paragraph_chars": 10}
        raw = keep_slots(parts)
        second = parts["s1"]["p0"][1]["paragraph_id"]
        raw["sections"]["s1"]["parts"]["p0"][second]["join_previous"] = True
        result, trace = apply_editorial_patch(raw, previous, {"s1": packet}, parts, origins)
        expected = copy.deepcopy(previous)
        expected["s1"]["parts"]["p0"] = expected["s1"]["parts"]["p0"].replace("\n\n", " ", 1)
        self.assertEqual(result, expected)
        self.assertEqual(len(trace["paragraph_joins"]), 1)
        self.assertNotIn("prevented_paragraph_joins", trace)

    def test_table_decoration_is_removed_without_altering_numbers_units_or_protected_scientific_text(self):
        raw = "8.80 ms ~ 11.6 ms ✨ | 1.64 ms 🛡️ | 47.28 μs | O(n²) | ✅ | ❌ | ⚠️"
        result = plain_table_text(raw)
        for token in ("8.80 ms ~ 11.6 ms", "1.64 ms", "47.28 μs", "O(n²)", "✓", "×", "주의"):
            self.assertIn(token, result)
        self.assertNotIn("✨", result)
        self.assertNotIn("🛡", result)
        self.assertEqual(plain_table_text("`emoji_✨` $x≈y$ https://example.org/🛡"), "`emoji_✨` $x≈y$ https://example.org/🛡")

    def test_readable_view_keeps_sentence_order_and_code_without_cutting_or_rewriting(self):
        text = "Measured 1.64 ms under condition A. " * 70 + "Use `call(x. y)` and $x. y$ unchanged."
        result = readable_prose(text)
        self.assertGreater(result.count("\n\n"), 1)
        self.assertEqual(re.sub(r"\s+", " ", text).strip(), re.sub(r"\s+", " ", result).strip())
        self.assertTrue(all(len(block) <= 600 for block in result.split("\n\n")))
        self.assertIn("`call(x. y)`", result)
        long_sentence = "x" * 900
        self.assertEqual(readable_prose(long_sentence), long_sentence)
        code = "```python\n" + text + "\n```"
        self.assertEqual(readable_prose(code), code)


if __name__ == "__main__":
    unittest.main()
