import copy
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from paper_plan import validate_plan, project_profile
from planned_paper import PlannedPaper, load_latest, render_paper
from publication_table_views import prepare_tables
from publication_tables import selection_report
from test_hierarchical_drafting import Client, assigned_plan
from test_planned_paper import research
from writing_policy import composition_issues


def merged_table():
    return {"id": "merged", "columns": ["Merged source explanation repeated in each column"] * 3,
            "rows": [["Operation", "Configuration A", "Configuration B"], ["op_name", "device", "host"],
                     ["Shared setup note:"] * 3, ["1", "1", "1"]],
            "evidence_ids": ["F1"], "page": 3, "source_element_id": "p3:e9"}


class PublicationTableViewTests(unittest.TestCase):
    def test_merged_title_uses_existing_header_and_preserves_values_notes_ids_and_raw_source(self):
        source = {"tables": [merged_table()]}
        before = copy.deepcopy(source)
        prepared = prepare_tables(source)
        table = prepared["tables"][0]
        self.assertEqual(table["columns"], ["Operation", "Configuration A", "Configuration B"])
        self.assertEqual(table["rows"], [["op_name", "device", "host"], ["1", "1", "1"]])
        self.assertEqual(table["notes"], ["Shared setup note:"])
        self.assertEqual(table["evidence_ids"], source["tables"][0]["evidence_ids"])
        self.assertEqual(table["source_element_id"], "p3:e9")
        self.assertEqual(prepared["audit"][0]["header_source_row"], 0)
        self.assertEqual(source, before)
        self.assertEqual(prepare_tables({"tables": [table]})["tables"], [table])

    def test_numeric_measurement_row_is_not_guessed_to_be_a_missing_header(self):
        table = merged_table()
        table["rows"] = [["A", "1.2", "3.4"]]
        prepared = prepare_tables({"tables": [table]})
        self.assertEqual(prepared["tables"], [])
        self.assertEqual(prepared["audit"][0]["status"], "withheld")
        self.assertEqual(table["rows"], [["A", "1.2", "3.4"]])

    def test_already_valid_repeated_data_rows_are_not_removed_as_notes(self):
        table = merged_table()
        table["columns"] = ["condition", "value A", "value B"]
        table["rows"] = [["same", "same", "same"], ["1", "1", "1"]]
        self.assertEqual(prepare_tables({"tables": [table]})["tables"], [table])

    def test_table_then_its_own_explanation_is_interleaved_instead_of_stacking_all_tables(self):
        data, value = research(), assigned_plan()
        data["tables"] = [{"id": key, "caption": caption, "columns": ["condition", "value"],
                           "rows": [["A", 12]], "evidence_ids": [fid]} for key, caption, fid in
                          (("T1", "First comparison", "F1"), ("T2", "Second comparison", "F2"))]
        section = value["sections"][1]
        section["table_ids"] = ["T2", "T1"]
        section["table_placements"] = [{"table_id": key, "subsection_index": 0, "reason": "different observation",
                                         "caption": caption} for key, caption in (("T1", "First result"), ("T2", "Second result"))]
        validate_plan(value, data, {}, project_profile("generic"))
        sections = {s["id"]: "Short prose [근거:F1]" for s in value["sections"]}
        sections["s1"] = "### 2.1 설계 근거\n\nFirst explanation [근거:F1]\n\nSecond explanation [근거:F2]\n\n### 2.2 적용 범위\n\nScope [근거:F2]"
        result = render_paper(value, sections, data)
        positions = [result.index(text) for text in ("표 2-1. First result", "First explanation", "표 2-2. Second result", "Second explanation")]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("[근거:", result)
        self.assertEqual(selection_report(value, data, sections)["unlinked_tables"], 0)

    def test_unlinked_selected_table_is_reported_without_fabricating_an_explanation(self):
        data, value = research(), assigned_plan()
        data["tables"] = [{"id": "T", "columns": ["condition", "value"], "rows": [["A", 12]], "evidence_ids": ["F2"]}]
        value["sections"][0]["table_ids"] = ["T"]
        sections = {s["id"]: "Existing explanation [근거:F1]" for s in value["sections"]}
        self.assertEqual(selection_report(value, data, sections)["unlinked_tables"], 1)
        output = render_paper(value, sections, data)
        self.assertEqual(output.count("Existing explanation"), len(value["sections"]))
        self.assertNotIn("표 1-1", output)
        self.assertEqual(selection_report(value, data, sections)["withheld_tables"][0]["withheld_reason"], "no_cited_explanation")

    def test_table_precedes_first_related_paragraph_even_when_later_one_cites_more_cells(self):
        data, value = research(), assigned_plan()
        data["tables"] = [{"id": "T", "caption": "Comparison", "columns": ["condition", "value"],
                           "rows": [["A", 12]], "evidence_ids": ["F1", "F2"]}]
        section = value["sections"][1]
        section["table_ids"] = ["T"]
        section["table_placements"] = [{"table_id": "T", "subsection_index": 1, "reason": "comparison"}]
        sections = {s["id"]: "Other prose [근거:F1]" for s in value["sections"]}
        sections["s1"] = ("### 2.1 설계 근거\n\nEarlier subsection [근거:F1,F2]\n\n"
                          "### 2.2 적용 범위\n\nUnrelated opening\n\nFirst interpretation [근거:F1]\n\n"
                          "Detailed interpretation [근거:F1,F2]")
        before = copy.deepcopy((value, sections, data))
        output = render_paper(value, sections, data)
        ordered = [output.index(text) for text in ("Earlier subsection", "Unrelated opening", "표 2-1.",
                                                   "First interpretation", "Detailed interpretation")]
        self.assertEqual(ordered, sorted(ordered))
        placement = selection_report(value, data, sections)["placements"][0]
        self.assertEqual((placement["subsection_index"], placement["paragraph_index"]), (1, 1))
        self.assertEqual(placement["placement_basis"], "first_available_cited_explanation")
        self.assertEqual((value, sections, data), before)

    def saved_layout(self, base):
        folder = Path(base) / "draft_history/planned/generic/completed"
        folder.mkdir(parents=True)
        data, value = research(), assigned_plan()
        data["tables"] = [{"id": "T", "caption": "Comparison", "columns": ["condition", "value"],
                           "rows": [["A", 12]], "evidence_ids": ["F1"]}]
        section = value["sections"][1]
        section["table_ids"] = ["T"]
        section["table_placements"] = [{"table_id": "T", "subsection_index": 0, "reason": "comparison"}]
        sections = {s["id"]: "Other prose [근거:F1]" for s in value["sections"]}
        sections["s1"] = "### 2.1 설계 근거\n\nFirst interpretation [근거:F1]\n\n### 2.2 적용 범위\n\nScope [근거:F2]"
        updated = render_paper(value, sections, data)
        table_block = updated[updated.index("**표 2-1."):updated.index("First interpretation")]
        old = updated.replace(table_block, "", 1) + "\n\n" + table_block
        (folder / "draft.md").write_text(old, encoding="utf-8")
        report = {"warning_summary": {"warnings": ["existing concern"]}, "table_selection": {"legacy": True}}
        for name, content in (("plan", value), ("research", data), ("sections", {"initial": sections, "final": sections}), ("review", report)):
            (folder / (name + ".json")).write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")
        pointer = {"run_dir": str(folder), "draft_sha256": hashlib.sha256((folder / "draft.md").read_bytes()).hexdigest()}
        for name in ("plan", "review", "sections", "research"):
            pointer[name + "_sha256"] = hashlib.sha256((folder / (name + ".json")).read_bytes()).hexdigest()
        (folder.parents[1] / "latest.json").write_text(json.dumps(pointer), encoding="utf-8")
        return folder, updated, report

    def test_saved_layout_refresh_updates_preview_and_download_body_without_api_or_cache_writes(self):
        with TemporaryDirectory() as tmp, patch("planned_paper.requests.post", side_effect=AssertionError("no API")) as post:
            folder, updated, report = self.saved_layout(tmp)
            before = {p: p.read_bytes() for p in Path(tmp).rglob("*") if p.is_file()}
            stored = load_latest(tmp)
            refreshed = load_latest(tmp, refresh_layout=True)
            self.assertEqual(refreshed["draft_markdown"], updated)
            self.assertTrue(refreshed["layout_refreshed"])
            self.assertEqual(refreshed["stored_draft_markdown"], stored["draft_markdown"])
            self.assertEqual(refreshed["plan"], stored["plan"])
            self.assertEqual(refreshed["review_warnings"], report["warning_summary"])
            self.assertEqual(refreshed["review"]["table_selection"]["placements"][0]["paragraph_index"], 0)
            self.assertEqual(stored["review"], report)
            self.assertTrue(all(p.read_bytes() == content for p, content in before.items()))
            self.assertEqual(set(before), {p for p in Path(tmp).rglob("*") if p.is_file()})
            post.assert_not_called()

    def test_layout_refresh_keeps_checksum_validation_and_supports_older_snapshots(self):
        for name in ("draft.md", "plan.json", "review.json", "sections.json", "research.json"):
            with self.subTest(name=name), TemporaryDirectory() as tmp:
                folder, _, _ = self.saved_layout(tmp)
                with (folder / name).open("a", encoding="utf-8") as changed:
                    changed.write(" ")
                with self.assertRaises(ValueError):
                    load_latest(tmp, refresh_layout=True)
        with TemporaryDirectory() as tmp:
            folder, updated, _ = self.saved_layout(tmp)
            pointer = folder.parents[1] / "latest.json"
            entry = json.loads(pointer.read_text(encoding="utf-8"))
            for name in ("sections_sha256", "research_sha256"):
                entry.pop(name)
            pointer.write_text(json.dumps(entry), encoding="utf-8")
            self.assertEqual(load_latest(tmp, refresh_layout=True)["draft_markdown"], updated)
            (folder / "sections.json").unlink()
            self.assertEqual(load_latest(tmp, refresh_layout=True), load_latest(tmp))

    def test_open_app_refreshes_saved_layout_without_replacing_a_new_plan_preview_or_other_mode(self):
        from streamlit.testing.v1 import AppTest
        with TemporaryDirectory() as tmp:
            folder, _, _ = self.saved_layout(tmp)
            saved, refreshed = load_latest(tmp), load_latest(tmp, refresh_layout=True)
            preview = assigned_plan()
            preview["title"] = "A newer plan preview"
            with patch("planned_paper.load_latest", return_value=refreshed) as load, \
                    patch("requests.sessions.Session.request", side_effect=AssertionError("No API during layout refresh")):
                app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "streamlit_app.py"), default_timeout=15)
                app.session_state["full_paper_draft"] = saved["draft_markdown"]
                app.session_state["draft_mode"] = "adaptive"
                app.session_state["paper_plan"] = preview
                app.run()
                self.assertFalse(list(app.exception))
                self.assertEqual(app.session_state["full_paper_draft"], refreshed["draft_markdown"])
                self.assertEqual(app.session_state["paper_plan"], preview)
                self.assertTrue(load.call_args.kwargs["refresh_layout"])
                load.reset_mock()
                app.session_state["draft_mode"] = "legacy_cuda"
                app.session_state["draft_layout_policy"] = "previous"
                app.session_state["full_paper_draft"] = "Other mode's draft"
                app.run()
                self.assertFalse(list(app.exception))
                self.assertEqual(app.session_state["full_paper_draft"], "Other mode's draft")
                load.assert_not_called()

    def test_planner_and_writers_receive_prepared_views_but_original_research_is_saved_intact(self):
        data, value = research(), assigned_plan()
        data["tables"] = [merged_table()]
        section = value["sections"][1]
        section["table_ids"] = ["merged"]
        section["table_placements"] = [{"table_id": "merged", "subsection_index": 0,
                                         "reason": "component comparison", "caption": "Execution placement comparison"}]
        original, client = copy.deepcopy(data), Client(value)
        with TemporaryDirectory() as tmp:
            result = PlannedPaper(tmp, client).run(data)
            planning = next(p for _, _, p in client.events if "reference_shapes" in p)
            self.assertEqual(planning["research"]["tables"][0]["columns"], merged_table()["rows"][0])
            self.assertEqual(result["research_evidence"]["tables"], original["tables"])
            saved = json.loads((Path(result["run_dir"]) / "research.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["tables"], original["tables"])
            self.assertNotIn("Merged source explanation", result["draft_markdown"])
            self.assertIn("Operation | Configuration A | Configuration B", result["draft_markdown"])
            self.assertNotIn("주: Shared setup note:", result["draft_markdown"])
            self.assertIn("Shared setup note:", result["review"]["table_selection"]["notes"][0]["withheld"])

    def test_bad_publication_view_is_archived_instead_of_printed(self):
        table = merged_table()
        table["rows"] = [["A", "1.2", "3.4"]]
        data, value = research(), assigned_plan()
        data["tables"] = [table]
        value["sections"][0]["table_ids"] = ["merged"]
        sections = {s["id"]: "Existing body [근거:F1]" for s in value["sections"]}
        self.assertNotIn("표 1-1", render_paper(value, sections, data))
        report = selection_report(value, data)
        self.assertEqual(report["selected"], 0)
        self.assertIn("merged", report["archived_table_ids"])
        self.assertEqual(report["preparation"][0]["status"], "withheld")

    def test_dense_and_notebook_prose_produces_layout_and_style_tasks_without_mutating_claims(self):
        body = "기록자는 단일 관측만 확인했다고 판단하였다. " + "실행 조건과 측정 방식이 섞여 있다. " * 80 + "[근거:F1]"
        packet = {"composition_policy": {"version": "test", "length_tolerance_ratio": 1.25, "max_paragraph_chars": 800},
                  "section_plan": {"evidence_ids": ["F1"]}}
        value = {"arbitrary": {"parts": {"p0": body}}}
        issues = composition_issues(value, {"arbitrary": packet}, "subsection")
        self.assertEqual({i["validation_code"] for i in issues}, {"composition_layout", "composition_style"})
        self.assertEqual(value["arbitrary"]["parts"]["p0"], body)
        self.assertTrue(any("시도·제안" in i["reason"] for i in issues))

    def test_quoted_code_and_math_are_not_rewritten_for_narrator_style(self):
        packet = {"composition_policy": {"version": "test", "length_tolerance_ratio": 1.25, "max_paragraph_chars": 800}}
        value = {"s": {"parts": {"p0": "코드 예시 `기록자는`와 수식 $연구노트에 기록$를 보존한다. [근거:F1]"}}}
        self.assertFalse(composition_issues(value, {"s": packet}, "subsection"))

    def test_narrator_style_uses_existing_writer_revision(self):
        client, requests = Client(), []
        def respond(system, packet, schema, path):
            raw = client(system, packet, schema, path)
            if path.parent.parent.name == "subsection-s0-p0" and "parts" in schema["properties"]:
                requests.append(packet)
                if len(requests) == 1:
                    raw["parts"]["p0"] = "기록자는 단일 관측의 범위만 정리하였다. [근거:F1,F2]"
            return raw
        with TemporaryDirectory() as tmp:
            result = PlannedPaper(tmp, respond).run(research())
        self.assertEqual(len(requests), 2)
        self.assertTrue(any(i.get("validation_code") == "composition_style" for i in requests[1]["revision"]["review"]["issues"]))
        self.assertNotIn("기록자는", result["draft_markdown"])
        self.assertEqual(result["review"]["composition_quality"]["status"], "within_checked_rules")


if __name__ == "__main__":
    unittest.main()
