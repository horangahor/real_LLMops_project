import copy
import unittest

from publication_table_views import prepare_tables, publication_notes
from publication_tables import render_section_tables, selection_report
from writing_policy import composition_issues


def table(key, ids):
    return {"id": key, "columns": ["Condition", "Value"], "rows": [["A", 12]],
            "evidence_ids": ids, "caption": "Condition comparison"}


def section(ids):
    return {"id": "arbitrary", "status": "write", "table_ids": ids, "required_items": [], "subsections": []}


class PublicationUnitsTests(unittest.TestCase):
    def test_raw_console_headers_are_withheld_but_parameter_comparison_columns_remain(self):
        trace = table("trace", ["F1"])
        trace["columns"] = ["eps=", "1e-06: T=39969", "| F=31 |", "time=5.04s"]
        trace["rows"] = [["x", "y", "z", "w"]]
        valid = table("experiment", ["F1"])
        valid.update(columns=["Input", "n=10", "n=20"], rows=[["A", 12, 24]])
        source = {"tables": [trace, valid]}
        original = copy.deepcopy(source)
        result = prepare_tables(source)
        self.assertEqual([t["id"] for t in result["tables"]], ["experiment"])
        self.assertEqual(result["audit"][0]["status"], "withheld")
        self.assertEqual(source, original)

    def test_only_interpretation_notes_are_printed_and_source_prose_is_preserved_in_audit(self):
        notes = ["그리고 구성 요소도 축소되었습니다:", "추가 변경 이력", "단위: ms",
                 {"kind": "condition", "text": "Only measurements at 20°C are shown."},
                 {"kind": "changelog", "text": "Implementation was edited."}]
        kept, withheld = publication_notes(notes)
        self.assertEqual(kept, ["단위: ms", "Only measurements at 20°C are shown."])
        t = table("T1", ["F1"])
        t["notes"] = notes
        data, plan = {"tables": [t]}, {"sections": [section(["T1"])]}
        raw = copy.deepcopy(data)
        body = "An observed comparison. [근거:F1]"
        output = render_section_tables(body, plan["sections"][0], {"T1": t}, 1)
        self.assertIn("주: 단위: ms", output)
        self.assertIn("20°C", output)
        self.assertNotIn("축소되었습니다", output)
        report = selection_report(plan, data, {"arbitrary": body})
        self.assertEqual(report["notes"][0]["withheld"], withheld)
        self.assertEqual(data, raw)

    def test_tables_have_separate_explanation_paragraphs_in_original_prose_order(self):
        tables = {"T1": table("T1", ["F1"]), "T2": table("T2", ["F2"])}
        tables["T1"]["caption"] = "First comparison"
        tables["T2"]["caption"] = "Second comparison"
        body = "First interpretation. [근거:F1]\n\nSecond interpretation. [근거:F2]"
        output = render_section_tables(body, section(["T1", "T2"]), tables, 4)
        positions = [output.index(s) for s in ["First comparison", "First interpretation", "Second comparison", "Second interpretation"]]
        self.assertEqual(positions, sorted(positions))

    def test_shared_explanation_does_not_create_a_stack_or_duplicate_the_paragraph(self):
        tables = {key: table(key, ["F1"]) for key in ("T1", "T2", "T3")}
        plan = {"sections": [section(list(tables))]}
        body = "One supported interpretation. [근거:F1]"
        output = render_section_tables(body, plan["sections"][0], tables, 7)
        self.assertEqual(output.count("**표"), 1)
        self.assertEqual(output.count("One supported interpretation"), 1)
        report = selection_report(plan, {"tables": list(tables.values())}, {"arbitrary": body})
        self.assertEqual((report["planned"], report["selected"], report["archived"]), (3, 1, 2))
        self.assertEqual(len(report["withheld_tables"]), 2)

    def test_internal_caption_is_never_used_as_public_title(self):
        t = table("source_table_0019", ["F1"])
        t["caption"] = "source_table_0019"
        s = section([t["id"]])
        s["table_placements"] = [{"table_id": t["id"], "subsection_index": 0, "caption": "source_table_0019 raw"}]
        output = render_section_tables("Observation. [근거:F1]", s, {t["id"]: t}, 1)
        self.assertNotIn("source_table", output)
        self.assertIn("Condition / Value", output)

    def test_meta_narrator_and_excess_explanation_use_existing_composition_repair(self):
        packet = {"composition_policy": {"version": "test", "length_tolerance_ratio": 1.25, "max_paragraph_chars": 800},
                  "tables": [table("T1", ["F1"])]}
        body = "작성자는 관측했다. [근거:F1]\n\n기록자의 판단이다. [근거:F1]\n\n연구노트의 저자는 시도했다. [근거:F1]"
        original = copy.deepcopy(packet)
        issues = composition_issues({"s": {"parts": {"p0": body}}}, {"s": packet}, "subsection")
        self.assertEqual({i["validation_code"] for i in issues}, {"composition_style", "composition_layout"})
        self.assertTrue(any("3개" in i["reason"] for i in issues))
        self.assertEqual(packet, original)
        safe = {"s": {"parts": {"p0": "시도하였다. `기록자는` $작성자는$ [근거:F1]"}}}
        self.assertFalse(composition_issues(safe, {"s": packet}, "subsection"))


if __name__ == "__main__":
    unittest.main()
