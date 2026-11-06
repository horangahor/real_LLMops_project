import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from planned_paper import PlannedPaper, fingerprint, load_latest
from test_planned_paper import plan, research


def assigned_plan():
    value = plan()
    section = value["sections"][1]
    section["required_items"][0]["subsection_index"] = 0
    section["required_items"].append({"id": "result_item", "description": "관측값을 설명한다.",
        "evidence_ids": ["F2"], "guideline_ids": [], "subsection_index": 1})
    return value


class Client:
    def __init__(self, selected_plan=None):
        self.plan = selected_plan or assigned_plan()
        self.events = []
        self.fail_once = None
        self.reject = None
        self.reject_once = None
        self.corrupt_editor_once = None

    def __call__(self, system, packet, schema, path):
        stage = path.parent.parent.name
        if packet.get("operation") in ("editorial_revision", "editorial_assembly"):
            from review_test_support import editorial_reply
            self.events.append((stage, "generate", copy.deepcopy(packet)))
            if stage == self.fail_once:
                self.fail_once = None
                raise RuntimeError("test interruption")
            value = editorial_reply(packet)
            if packet["operation"] == "editorial_revision":
                if packet.get("output_mode") == "fixed_slots":
                    for sid, parts in packet["source_parts"].items():
                        for key, units in parts.items():
                            unit = units[0]
                            value["sections"][sid]["parts"][key][unit["paragraph_id"]]["spans"][unit["id"]].update(
                                action="replace", text=unit["text"] + f" 연결을 보완했다 {len(self.events)}.")
                else:
                    for row in value["sections"].values():
                        for paragraphs in row["parts"].values():
                            paragraphs[0]["segments"][0]["text"] += f" 연결을 보완했다 {len(self.events)}."
            if stage == self.corrupt_editor_once:
                self.corrupt_editor_once = None
                sid = "s1"
                if packet.get("output_mode") == "fixed_spans":
                    value["sections"][sid]["parts"]["p1"][packet["source_parts"][sid]["p0"][0]["id"]] = {
                        "action": "keep", "text": "", "join_previous": False}
                else:
                    value["sections"][sid]["parts"]["p1"][0]["segments"][0]["source_id"] = packet["source_parts"][sid]["p0"][0]["id"]
            return value
        if packet.get("operation") == "editorial_review":
            self.events.append((stage, "review", copy.deepcopy(packet)))
            if stage == self.fail_once:
                self.fail_once = None
                raise RuntimeError("test interruption")
            fail = stage == self.reject or stage == self.reject_once
            if stage == self.reject_once:
                self.reject_once = None
            from review_test_support import editorial_review_reply
            return editorial_review_reply(packet, [{"section_id": packet["outline"][0]["id"], "paragraph_id": "none", "category": "flow",
                                "severity": "error", "reason": "test correction required"}] if fail else [])
        if "findings" in schema["properties"] or "links" in schema["properties"]:
            raise AssertionError("Retired review/link agents must not be called")
        kind = "review" if "checks" in schema["properties"] else "generate"
        self.events.append((stage, kind, copy.deepcopy(packet)))
        if stage == self.fail_once:
            self.fail_once = None
            raise RuntimeError("test interruption")
        if "generation_order" in schema["properties"]:
            return copy.deepcopy(self.plan)
        if kind == "review":
            selected = packet["plan"]["sections"]
            def paragraphs(sid, item):
                from bounded_drafting import cited_ids
                return [k for k, p in packet["draft_paragraphs"].items()
                        if p["section_id"] == sid and (not item["evidence_ids"] or set(item["evidence_ids"]) & cited_ids(p["text"]))]
            fail = stage == self.reject or stage == self.reject_once
            if stage == self.reject_once:
                self.reject_once = None
            return {"checks": [{"item_id": item["id"], "verdict": "met",
                                "paragraph_ids": paragraphs(s["id"], item), "evidence_ids": item["evidence_ids"]}
                               for s in selected for item in s["required_items"]],
                    "reference_checks": [], "issues": ([{
                        "section_id": selected[0]["id"], "severity": "error", "paragraph_id": "none",
                        "reason": "test correction required", "evidence_ids": []}] if fail else [])}
        def body(ids):
            return "배정된 원문 범위의 설명이다. [근거:" + ",".join(ids) + "]"
        def parts(scoped):
            assignments = scoped.get("subsection_assignments")
            if assignments:
                return {k: body(a["evidence_ids"]) for k, a in assignments.items()}
            return {"p0": body(scoped["section_plan"]["evidence_ids"])}
        if "parts" in schema["properties"]:
            value = {"parts": parts(packet)}
        else:
            value = {"sections": {sid: {"parts": parts(p)} for sid, p in packet["section_packets"].items()}}
        if stage == self.corrupt_editor_once:
            self.corrupt_editor_once = None
            target = value if "parts" in value else value["sections"]["s1"]
            target["parts"]["p1"] = body(["F1"])
        return value


class HierarchicalDraftingTests(unittest.TestCase):
    def legacy_checkpoint(self, folder, stage="subsection-s0-p0"):
        """Simulate an approval issued before actual paragraph citations were checked."""
        path = Path(folder) / "workflow" / stage / "approved.json"
        saved = json.loads(path.read_text(encoding="utf-8"))
        saved["value"]["sections"]["s0"]["parts"]["p0"] = "기존 본문에서 두 번째 필수 근거가 빠졌다. [근거:F1]"
        saved["sha256"] = fingerprint(saved["value"])
        path.write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")
        return saved

    def test_subsections_are_written_and_reviewed_before_each_parent_and_mandatory_paper_editor(self):
        with TemporaryDirectory() as tmp:
            client = Client()
            result = PlannedPaper(tmp, client).run(research())
            stages = ["subsection-s0-p0", "section-s0", "subsection-s1-p0", "subsection-s1-p1",
                      "section-s1", "subsection-s2-p0", "section-s2", "paper"]
            actual = [(s, kind) for s, kind, p in client.events if "workflow_stage" in p]
            self.assertEqual(actual, [(s, kind) for s in stages for kind in ("generate", "review")])
            leaf_inputs = {s: p for s, kind, p in client.events if s.startswith("subsection") and kind == "generate"}
            self.assertEqual([f["id"] for f in leaf_inputs["subsection-s1-p0"]["facts"]], ["F1"])
            self.assertEqual([f["id"] for f in leaf_inputs["subsection-s1-p1"]["facts"]], ["F2"])
            self.assertEqual(result["metrics"]["reviewed_stages"], 8)
            self.assertTrue(all(s["approved"] for s in result["workflow"]["stages"]))
            self.assertEqual(load_latest(tmp)["draft_markdown"], result["draft_markdown"])
            for stage in stages:
                self.assertTrue((Path(result["run_dir"]) / "workflow" / stage / "approved.json").is_file())

    def test_rejected_subsection_is_revised_locally_before_parent(self):
        with TemporaryDirectory() as tmp:
            client = Client()
            client.reject_once = "subsection-s1-p1"
            result = PlannedPaper(tmp, client).run(research())
            events = [(s, k) for s, k, _ in client.events]
            self.assertEqual(events.count(("subsection-s1-p1", "generate")), 2)
            self.assertEqual(events.count(("subsection-s1-p0", "generate")), 1)
            self.assertEqual(events.count(("section-s1", "generate")), 1)
            revision = next(p for s, k, p in client.events if s == "subsection-s1-p1" and "revision" in p)
            self.assertFalse(revision["revision"]["review"]["approved"])
            self.assertTrue(result["review"]["approved"])

    def test_exhausted_leaf_review_preserves_warnings_and_continues_to_final_draft(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp) / "run"
            folder.mkdir()
            (folder / "draft.md").write_text("previous draft", encoding="utf-8")
            client = Client()
            client.reject = "subsection-s1-p1"
            engine = PlannedPaper(tmp, client)
            result = engine.run(research(), output_dir=folder)
            self.assertEqual((folder / "draft.md").read_text(encoding="utf-8"), result["draft_markdown"])
            self.assertTrue(any(s == "paper" for s, _, _ in client.events))
            candidate = json.loads((folder / "workflow/subsection-s1-p1/candidate.json").read_text(encoding="utf-8"))
            self.assertTrue(candidate["review"]["approved"])
            self.assertFalse(candidate["review"]["content_approved"])
            self.assertEqual(result["review"]["content_warnings"][0]["original_severity"], "error")
            self.assertEqual(result["review"]["content_status"], "needs_attention")
            self.assertEqual(sum(s == "subsection-s1-p1" and k == "review" for s, k, _ in client.events), 3)
            summary = json.loads((folder / "review-warnings.json").read_text(encoding="utf-8"))
            self.assertEqual(summary, result["review_warnings"])
            self.assertEqual(summary["warning_count"], 1)
            self.assertEqual(summary["stages"][0]["completion"]["revisions"], 2)
            self.assertIn("F2", summary["stages"][0]["snapshot"]["paragraphs"]["s1_p1"]["text"])
            before = len(client.events)
            self.assertEqual(engine.run(research(), output_dir=folder)["review_warnings"], summary)
            self.assertEqual(len(client.events), before)

    def test_resume_reuses_only_reviewed_stages_after_transport_interruption(self):
        with TemporaryDirectory() as tmp:
            client = Client()
            client.fail_once = "subsection-s1-p1"
            engine = PlannedPaper(tmp, client)
            with self.assertRaisesRegex(RuntimeError, "test interruption"):
                engine.run(research())
            before = len(client.events)
            result = engine.run(research())
            resumed = client.events[before:]
            self.assertEqual(resumed[0][0], "subsection-s1-p1")
            self.assertFalse(any(s in ("subsection-s0-p0", "section-s0", "subsection-s1-p0") for s, _, _ in resumed))
            before = len(client.events)
            self.assertEqual(engine.run(research())["draft_markdown"], result["draft_markdown"])
            self.assertEqual(len(client.events), before)

    def test_both_editors_cannot_move_evidence_outside_its_subsection(self):
        for target in ("section-s1", "paper"):
            with self.subTest(stage=target), TemporaryDirectory() as tmp:
                client = Client()
                client.corrupt_editor_once = target
                result = PlannedPaper(tmp, client).run(research())
                self.assertEqual(sum(s == target and k == "generate" for s, k, _ in client.events), 2)
                # The invalid edit is rejected before the reviewer can approve it.
                self.assertEqual(sum(s == target and k == "review" for s, k, _ in client.events), 1)
                repaired = next(p for s, k, p in client.events if s == target and "invalid_response" in p)
                self.assertIn("범위", repaired["invalid_response"]["reason"])
                self.assertTrue(result["review"]["approved"])

    def test_editor_review_failure_revises_only_that_editing_stage(self):
        for target in ("section-s1", "paper"):
            with self.subTest(stage=target), TemporaryDirectory() as tmp:
                client = Client()
                client.reject_once = target
                result = PlannedPaper(tmp, client).run(research())
                self.assertEqual(sum(s == target and k == "generate" for s, k, _ in client.events), 2)
                self.assertEqual(sum(s == target and k == "review" for s, k, _ in client.events), 2)
                self.assertEqual(sum(s == "subsection-s1-p1" and k == "generate" for s, k, _ in client.events), 1)
                self.assertTrue(result["review"]["approved"])

    def test_exhausted_editorial_review_preserves_findings_as_warnings_and_publishes_draft(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp) / "run"
            folder.mkdir()
            (folder / "draft.md").write_text("previous draft", encoding="utf-8")
            client = Client()
            client.reject = "paper"
            result = PlannedPaper(tmp, client).run(research(), output_dir=folder)
            self.assertTrue(result["review"]["approved"])
            self.assertEqual(result["review"]["editorial_status"], "needs_attention")
            self.assertTrue(result["review"]["issues"][0]["deferred"])
            self.assertEqual((folder / "draft.md").read_text(encoding="utf-8"), result["draft_markdown"])
            self.assertTrue((folder / "workflow/section-s2/approved.json").is_file())
            self.assertTrue((folder / "workflow/paper/approved.json").is_file())
            self.assertFalse((Path(tmp) / "draft_history/planned/latest.json").exists())

    def test_stage_checkpoint_tampering_is_rejected_before_reuse(self):
        with TemporaryDirectory() as tmp:
            client = Client()
            engine = PlannedPaper(tmp, client)
            result = engine.run(research())
            path = Path(result["run_dir"]) / "workflow/subsection-s1-p1/approved.json"
            saved = json.loads(path.read_text(encoding="utf-8"))
            saved["value"]["sections"]["s1"]["parts"]["p0"] = "changed [근거:F2]"
            path.write_text(json.dumps(saved), encoding="utf-8")
            before = len(client.events)
            with self.assertRaisesRegex(ValueError, "변경"):
                engine.run(research())
            self.assertEqual(len(client.events), before)

    def test_legacy_approval_is_revised_and_changed_child_refreshes_only_its_parent(self):
        with TemporaryDirectory() as tmp:
            client = Client()
            client.plan["sections"][0]["required_items"][0]["evidence_ids"] = ["F1", "F2"]
            def response(system, packet, schema, path):
                raw = client(system, packet, schema, path)
                if path.parent.parent.name == "subsection-s0-p0" and "parts" in schema["properties"] and "revision" in packet:
                    raw["parts"]["p0"] = "두 필수 근거를 다시 설명한 본문이다. [근거:F1,F2]"
                return raw
            engine = PlannedPaper(tmp, response)
            original = engine.run(research())
            folder = Path(original["run_dir"])
            saved = self.legacy_checkpoint(folder)
            before = len(client.events)
            result = engine.run(research())
            events = client.events[before:]
            self.assertTrue(result["review"]["approved"])
            self.assertEqual(sum(s == "subsection-s0-p0" and k == "generate" for s, k, _ in events), 1)
            self.assertEqual(sum(s == "section-s0" and k == "generate" for s, k, _ in events), 1)
            self.assertTrue(all(s in ("subsection-s0-p0", "section-s0", "paper") for s, _, _ in events))
            self.assertEqual(sum(s == "paper" and k == "generate" for s, k, _ in events), 1)
            self.assertIn("두 필수 근거를 다시 설명한 본문이다.", result["draft_markdown"])
            request = next(p for s, k, p in events if s == "subsection-s0-p0" and k == "generate")
            self.assertEqual(request["revision"]["review"]["checks"][0]["missing_body_evidence_ids"], ["F2"])
            archive = folder / "workflow/subsection-s0-p0/checkpoint-history" / f"approved-{saved['sha256']}.json"
            self.assertEqual(json.loads(archive.read_text(encoding="utf-8")), saved)
            for stage in ("subsection-s0-p0", "section-s0"):
                record = json.loads((folder / "workflow" / stage / "checkpoint-revalidation.json").read_text(encoding="utf-8"))
                self.assertEqual(record["status"], "resolved")
                self.assertEqual(record["reason"], "review_rejected" if stage.startswith("subsection") else "input_changed")
            before = len(client.events)
            engine.run(research())
            self.assertEqual(len(client.events), before)

    def test_checkpoint_revision_resumes_after_interruption_with_same_missing_evidence_feedback(self):
        with TemporaryDirectory() as tmp:
            client = Client()
            client.plan["sections"][0]["required_items"][0]["evidence_ids"] = ["F1", "F2"]
            engine = PlannedPaper(tmp, client)
            original = engine.run(research())
            folder = Path(original["run_dir"])
            saved = self.legacy_checkpoint(folder)
            client.fail_once = "subsection-s0-p0"
            with self.assertRaisesRegex(RuntimeError, "test interruption"):
                engine.run(research())
            root = folder / "workflow/subsection-s0-p0"
            self.assertFalse((root / "approved.json").exists())
            self.assertTrue((root / "checkpoint-history" / f"approved-{saved['sha256']}.json").is_file())
            self.assertEqual((folder / "draft.md").read_text(encoding="utf-8"), original["draft_markdown"])
            before = len(client.events)
            result = engine.run(research())
            first = client.events[before]
            self.assertEqual(first[:2], ("subsection-s0-p0", "generate"))
            self.assertEqual(first[2]["revision"]["review"]["checks"][0]["missing_body_evidence_ids"], ["F2"])
            self.assertTrue(result["review"]["approved"])

    def test_legacy_approval_revalidation_preserves_archive_and_defers_after_two_revisions(self):
        with TemporaryDirectory() as tmp:
            client = Client()
            client.plan["sections"][0]["required_items"][0]["evidence_ids"] = ["F1", "F2"]
            def response(system, packet, schema, path):
                raw = client(system, packet, schema, path)
                if path.parent.parent.name == "subsection-s0-p0" and "parts" in schema["properties"] and "revision" in packet:
                    raw["parts"]["p0"] = "내용 검토에서 탈락할 수정 본문이다. [근거:F1,F2]"
                return raw
            engine = PlannedPaper(tmp, response)
            original = engine.run(research())
            folder = Path(original["run_dir"])
            saved = self.legacy_checkpoint(folder)
            client.reject = "subsection-s0-p0"
            before = len(client.events)
            result = engine.run(research())
            root = folder / "workflow/subsection-s0-p0"
            self.assertTrue((root / "approved.json").exists())
            self.assertEqual(json.loads((root / "checkpoint-history" / f"approved-{saved['sha256']}.json").read_text(encoding="utf-8")), saved)
            self.assertEqual((folder / "draft.md").read_text(encoding="utf-8"), result["draft_markdown"])
            self.assertFalse(result["review"]["content_approved"])
            self.assertEqual(sum(s == "subsection-s0-p0" and k == "generate" for s, k, _ in client.events[before:]), 1)  # reuse an identical replacement
            workflow = json.loads((folder / "workflow.json").read_text(encoding="utf-8"))
            self.assertEqual(workflow["stages"][-1]["id"], "paper")

    def test_archived_checkpoint_tampering_still_stops_before_any_new_call(self):
        with TemporaryDirectory() as tmp:
            client = Client()
            client.plan["sections"][0]["required_items"][0]["evidence_ids"] = ["F1", "F2"]
            engine = PlannedPaper(tmp, client)
            original = engine.run(research())
            folder = Path(original["run_dir"])
            saved = self.legacy_checkpoint(folder)
            client.fail_once = "subsection-s0-p0"
            with self.assertRaises(RuntimeError):
                engine.run(research())
            archive = folder / "workflow/subsection-s0-p0/checkpoint-history" / f"approved-{saved['sha256']}.json"
            changed = json.loads(archive.read_text(encoding="utf-8"))
            changed["value"]["sections"]["s0"]["parts"]["p0"] += " 변조"
            archive.write_text(json.dumps(changed), encoding="utf-8")
            before = len(client.events)
            with self.assertRaisesRegex(ValueError, "변경"):
                engine.run(research())
            self.assertEqual(len(client.events), before)

    def test_placeholder_has_no_writer_editor_or_reviewer(self):
        with TemporaryDirectory() as tmp:
            client = Client(plan(3, placeholder=True))
            result = PlannedPaper(tmp, client).run(research(), project="cuda")
            self.assertFalse(any("related" in s for s, _, _ in client.events))
            self.assertIn("## 제2장 관련 연구\n\n## 제3장", result["draft_markdown"])


if __name__ == "__main__":
    unittest.main()
