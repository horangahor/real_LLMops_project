import copy
import json
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from bounded_drafting import cited_ids
from editorial_review import checked_editorial_review, review_editorial
from editorial_revision import edit_editorial, editorial_sources, revise_editorial, revision_changes
from paper_context import build_contexts
from planned_paper import PlannedPaper
from test_hierarchical_drafting import Client, assigned_plan
from test_planned_paper import plan, research
from review_test_support import editorial_reply


def fixture():
    value, data = assigned_plan(), research()
    packet = build_contexts(value, data, {})["sections"]["s1"]
    previous = {"s1": {"parts": {
        "p0": "같은 연구 목표를 설명한다. [근거:F1]\n\n목표를 다시 설명한다. [근거:F1]",
        "p1": "같은 연구 목표를 설명한다. [근거:F2]"}}}
    bodies = {"s1": "### 제목\n\n" + previous["s1"]["parts"]["p0"] + "\n\n### 다음\n\n" + previous["s1"]["parts"]["p1"]}
    report = checked_editorial_review({"issues": [{"section_id": "s1", "paragraph_id": "s1_p3",
        "category": "duplication", "severity": "error", "reason": "s1_p2와 목표 진술이 중복된다."}]}, value, bodies, {})
    return value, packet, previous, report


def unchanged_patch(packet):
    return editorial_reply(packet)


class EditorialRevisionTests(unittest.TestCase):
    def test_merge_keeps_separate_citation_anchors_and_delete_drops_only_deleted_origin(self):
        _, packet, previous, report = fixture()
        packet["subsection_assignments"]["p0"]["evidence_ids"] = ["F1", "F2"]
        previous["s1"]["parts"]["p0"] = "관측 A이다. [근거:F1] 삭제할 관측 B이다. [근거:F2]\n\n관측 C이다. [근거:F1]"
        def client(system, body, schema, path):
            raw = unchanged_patch(body)
            units = body["source_parts"]["s1"]["p0"]
            raw["sections"]["s1"]["parts"]["p0"] = [{"segments": [
                {"text": "관측 A를 간결히 설명한다.", "source_id": units[0]["id"]},
                {"text": "이어서 관측 C를 설명한다.", "source_id": units[2]["id"]}]}]
            self.assertNotIn("evidence_ids", json.dumps(schema))
            return raw
        with TemporaryDirectory() as tmp:
            result = edit_editorial(PlannedPaper(tmp, client), Path(tmp), "edit", "section", previous, {"s1": packet}, report)
            text = result["s1"]["parts"]["p0"]
            self.assertEqual(text, "관측 A를 간결히 설명한다. [근거:F1] 이어서 관측 C를 설명한다. [근거:F1]")
            trace = json.loads((Path(tmp) / "edit-editorial-provenance-v2-provenance.json").read_text(encoding="utf-8"))
            kept = [row for row in trace["segments"] if row["part"] == "p0"]
            self.assertEqual([row["origin"]["evidence_ids"] for row in kept], [["F1"], ["F1"]])
            self.assertEqual(kept[0]["text"], "관측 A를 간결히 설명한다.")
            self.assertEqual(kept[0]["origin"]["text"], "관측 A이다.")

    def test_different_sources_are_not_pooled_at_the_end_of_a_merged_paragraph(self):
        _, packet, previous, _ = fixture()
        packet["subsection_assignments"]["p0"]["evidence_ids"] = ["F1", "F2"]
        previous["s1"]["parts"]["p0"] = "같은 표현이다. [근거:F1]\n\n같은 표현이다. [근거:F2]"
        def client(system, body, schema, path):
            raw = unchanged_patch(body)
            units = body["source_parts"]["s1"]["p0"]
            self.assertNotEqual(units[0]["id"], units[1]["id"])
            raw["sections"]["s1"]["parts"]["p0"] = [{"segments": [
                {"text": "첫 번째 관측이다.", "source_id": units[0]["id"]},
                {"text": "두 번째 관측이다.", "source_id": units[1]["id"]}]}]
            return raw
        with TemporaryDirectory() as tmp:
            result = edit_editorial(PlannedPaper(tmp, client), Path(tmp), "assemble", "section", previous, {"s1": packet})
        self.assertEqual(result["s1"]["parts"]["p0"], "첫 번째 관측이다. [근거:F1] 두 번째 관측이다. [근거:F2]")

    def test_existing_joint_citation_is_preserved_without_guessing_which_id_to_remove(self):
        _, packet, previous, report = fixture()
        packet["subsection_assignments"]["p0"]["evidence_ids"] = ["F1", "F2"]
        previous["s1"]["parts"]["p0"] = "두 기록을 함께 설명한다. [근거:F2,F1]"
        parts, origins, _ = editorial_sources(previous, {"s1": packet})
        unit = parts["s1"]["p0"][0]
        self.assertNotIn("evidence_ids", unit)
        self.assertEqual(origins[unit["id"]]["evidence_ids"], ["F2", "F1"])
        with TemporaryDirectory() as tmp:
            result = edit_editorial(PlannedPaper(tmp, lambda s,p,c,f: unchanged_patch(p)), Path(tmp), "edit", "section", previous, {"s1": packet}, report)
        self.assertEqual(result, previous)

    def test_editor_cannot_return_evidence_ids_or_inline_citations(self):
        _, packet, previous, report = fixture()
        for error_kind in ("field", "inline"):
            with self.subTest(kind=error_kind), TemporaryDirectory() as tmp:
                def client(system, body, schema, path):
                    raw = unchanged_patch(body)
                    segment = raw["sections"]["s1"]["parts"]["p0"][0]["segments"][0]
                    if error_kind == "field":
                        segment["evidence_ids"] = ["F2"]
                    else:
                        segment["text"] += " [근거:F2]"
                    return raw
                with self.assertRaisesRegex(ValueError, "기존 문단 연결 형식 보정"):
                    edit_editorial(PlannedPaper(tmp, client), Path(tmp), "edit", "section", previous, {"s1": packet}, report)

    def test_editor_can_merge_paragraphs_with_cross_part_context_without_reading_sources(self):
        _, packet, previous, report = fixture()
        packet["facts"][0]["sources"] = [{"quote": "RAW_SOURCE_" * 50000}]
        requests = []
        def client(system, body, schema, path):
            requests.append(body)
            self.assertNotIn("source_elements", body)
            self.assertNotIn("RAW_SOURCE_", json.dumps(body))
            self.assertEqual(set(body["source_parts"]["s1"]), {"p0", "p1"})
            self.assertNotIn("evidence_ids", json.dumps(body))
            self.assertEqual(body["revision"]["review"]["issues"][0]["paragraph_id"], "s1_p3")
            self.assertIn("s1_p2", body["revision"]["review"]["issues"][0]["reason"])
            return {"sections": {"s1": {"parts": {
                "p0": [{"segments": [{"text": "연구 목표를 한 곳에 정리한다.", "source_id": body["source_parts"]["s1"]["p0"][0]["id"]}]}],
                "p1": [{"segments": [{"text": "다음 소절에서는 관측 결과를 설명한다.", "source_id": body["source_parts"]["s1"]["p1"][0]["id"]}]}]}}}}
        with TemporaryDirectory() as tmp:
            result = edit_editorial(PlannedPaper(tmp, client), Path(tmp), "edit", "section", previous, {"s1": packet}, report)
        self.assertEqual(len(requests), 1)
        changes = revision_changes(previous, result, {"s1": packet}, report["issues"])
        self.assertTrue(changes["prose_changed"])
        self.assertEqual(len(changes["changed_parts"]), 2)
        self.assertFalse(changes["unchanged_findings"])

    def test_unchanged_editor_skips_repeated_review_and_persists_visible_warnings_on_resume(self):
        client = Client()
        client.reject = "section-s1"
        edits = []
        def response(system, body, schema, path):
            if body.get("operation") == "editorial_revision":
                edits.append(copy.deepcopy(body))
                return unchanged_patch(body)
            return client(system, body, schema, path)
        with TemporaryDirectory() as tmp:
            engine = PlannedPaper(tmp, response)
            result = engine.run(research())
            self.assertTrue(result["review"]["approved"])
            self.assertEqual(result["review"]["editorial_status"], "needs_attention")
            warnings = result["review"]["editorial_warnings"]
            self.assertEqual(len(warnings), 1)
            self.assertEqual(warnings[0]["stage"], "section-s1")
            self.assertTrue(warnings[0]["deferred"])
            self.assertEqual(len(edits), 2)
            self.assertEqual(edits[1]["revision"]["previous_revision_result"], "unchanged")
            self.assertEqual(sum(s == "section-s1" and k == "review" for s, k, _ in client.events), 1)
            root = Path(result["run_dir"]) / "workflow/section-s1"
            saved = json.loads((root / "approved.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["value"]["editorial_completion"]["reason"], "unchanged")
            self.assertEqual(saved["value"]["raw_review"]["issues"][0]["severity"], "error")
            before = len(client.events)
            rerun = engine.run(research())
            self.assertEqual(len(client.events), before)
            self.assertEqual(len(edits), 2)
            self.assertEqual(rerun["review"]["editorial_warnings"], warnings)
            self.assertEqual(rerun["metrics"]["editorial_warnings"], 1)

    def test_recheck_targets_previous_findings_even_after_paragraphs_are_merged_and_renumbered(self):
        value, _, _, report = fixture()
        bodies = {"s1": "목표를 한 곳에서 설명한다. [근거:F1]"}
        seen = []
        def client(system, packet, schema, path):
            seen.append(packet)
            self.assertEqual(packet["review_scope"], "previous_findings_only")
            self.assertEqual(packet["previous_findings"][0]["paragraph_id"], "s1_p3")
            self.assertEqual(set(packet["draft_paragraphs"]), {"s1_p1"})
            # A new category is a malformed recheck, never a reason to rewrite.
            return {"issues": [{"section_id": "s1", "paragraph_id": "s1_p1", "category": "style",
                "severity": "error", "reason": "새로운 취향 지적"}]} if len(seen) == 1 else {"issues": []}
        with TemporaryDirectory() as tmp:
            _, result = review_editorial(PlannedPaper(tmp, client), Path(tmp), "recheck", "section", value, bodies, {}, report["issues"])
        self.assertTrue(result["approved"])
        self.assertEqual(len(seen), 2)
        self.assertIn("invalid_review", seen[1])

    def test_interrupted_recheck_resumes_with_saved_revision_without_rewriting_children(self):
        client = Client()
        client.reject_once = "section-s1"
        interrupted, edits = [], []
        def response(system, body, schema, path):
            if body.get("operation") == "editorial_revision":
                edits.append(copy.deepcopy(body))
            if body.get("review_scope") == "previous_findings_only" and not interrupted:
                interrupted.append(True)
                raise RuntimeError("test recheck interruption")
            return client(system, body, schema, path)
        with TemporaryDirectory() as tmp:
            folder = Path(tmp) / "run"
            folder.mkdir()
            (folder / "draft.md").write_text("previous draft", encoding="utf-8")
            engine = PlannedPaper(tmp, response)
            with self.assertRaisesRegex(RuntimeError, "test recheck interruption"):
                engine.run(research(), output_dir=folder)
            self.assertEqual((folder / "draft.md").read_text(encoding="utf-8"), "previous draft")
            before = len(client.events)
            result = engine.run(research(), output_dir=folder)
            self.assertTrue(result["review"]["approved"])
            self.assertEqual(len(edits), 1)
            self.assertFalse(any(s.startswith("subsection-s1") for s, _, _ in client.events[before:]))
            self.assertEqual(sum(s == "section-s1" and k == "generate" for s, k, _ in client.events), 2)

    def test_citation_only_changes_do_not_count_as_prose_revision(self):
        _, packet, previous, report = fixture()
        result = copy.deepcopy(previous)
        result["s1"]["parts"]["p0"] = result["s1"]["parts"]["p0"].replace("목표", "목 표")
        changes = revision_changes(previous, result, {"s1": packet}, report["issues"])
        self.assertFalse(changes["prose_changed"])
        self.assertEqual(len(changes["unchanged_findings"]), 1)

    def test_paragraph_merge_is_a_real_edit_even_when_wording_is_unchanged(self):
        _, packet, previous, report = fixture()
        result = copy.deepcopy(previous)
        result["s1"]["parts"]["p0"] = result["s1"]["parts"]["p0"].replace("\n\n", " ")
        changes = revision_changes(previous, result, {"s1": packet}, report["issues"])
        self.assertTrue(changes["prose_changed"])
        self.assertEqual(changes["changed_parts"], [{"section_id": "s1", "part": "p0"}])

    def test_unused_candidate_ids_cannot_be_added_by_source_free_editor(self):
        _, packet, previous, report = fixture()
        packet["subsection_assignments"]["p0"]["evidence_ids"].append("F2")
        calls = []
        def client(system, body, schema, path):
            calls.append(body)
            self.assertNotIn("allowed_evidence_ids", body)
            raw = unchanged_patch(body)
            raw["sections"]["s1"]["parts"]["p0"][0]["segments"][0]["source_id"] = body["source_parts"]["s1"]["p1"][0]["id"]
            return raw
        with TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "형식 보정"):
                edit_editorial(PlannedPaper(tmp, client), Path(tmp), "edit", "section", previous, {"s1": packet}, report)
        self.assertEqual(len(calls), 2)

    def test_invalid_editor_response_still_blocks_publication_and_preserves_previous_draft(self):
        client = Client()
        client.reject = "paper"
        def response(system, body, schema, path):
            if body.get("operation") == "editorial_revision":
                raw = editorial_reply(body)
                unit = body["source_parts"]["s0"]["p0"][0]
                raw["sections"]["s0"]["parts"]["p0"][unit["paragraph_id"]]["spans"][unit["id"]]["source_id"] = "UNKNOWN"
                return raw
            return client(system, body, schema, path)
        with TemporaryDirectory() as tmp:
            folder = Path(tmp) / "run"
            folder.mkdir()
            (folder / "draft.md").write_text("previous draft", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "형식 보정"):
                PlannedPaper(tmp, response).run(research(), output_dir=folder)
            self.assertEqual((folder / "draft.md").read_text(encoding="utf-8"), "previous draft")
            self.assertFalse((folder / "workflow/paper/approved.json").exists())

    def test_bounded_editor_keeps_context_and_every_part_without_source_batches(self):
        _, packet, previous, report = fixture()
        previous["s1"]["parts"] = {key: "\n\n".join(f"설명 {n} " + "문장 " * 280 + f"[근거:{eid}]" for n in range(8))
            for key, eid in (("p0", "F1"), ("p1", "F2"))}
        calls = []
        def client(system, body, schema, path):
            calls.append(body)
            self.assertTrue(body["context_paragraphs"])
            self.assertNotIn("facts", body)
            return unchanged_patch(body)
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {"PAPER_REQUEST_MAX_BYTES": "24000"}):
            result = edit_editorial(PlannedPaper(tmp, client), Path(tmp), "edit", "section", previous, {"s1": packet}, report)
        self.assertGreater(len(calls), 1)
        self.assertEqual(result, previous)


if __name__ == "__main__":
    unittest.main()
