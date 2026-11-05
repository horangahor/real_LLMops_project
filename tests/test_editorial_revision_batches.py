import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from drafting_budget import compact_packet, request_bytes, request_limit
from editorial_patch import (INSTRUCTION, REVISION_BATCH_POLICY, patch_schema, revision_batch_targets)
from editorial_revision import REVISION_POLICY, editorial_sources, revise_editorial
from planned_paper import PlannedPaper, fingerprint
from review_test_support import editorial_reply
from test_editorial_revision import fixture


def setup_revision():
    _, packet, previous, _ = fixture()
    previous["s1"]["parts"]["p0"] = "\n\n".join(f"기존 문단 {i}다. [근거:F1]" for i in range(32))
    parts, _, _ = editorial_sources(previous, {"s1": packet})
    units = parts["s1"]["p0"]
    def issue(pid, reason, severity="error"):
        return {"section_id": "s1", "paragraph_id": pid, "category": "flow", "severity": severity, "reason": reason}
    report = {"issues": [issue(units[5]["paragraph_id"], f"{units[28]['paragraph_id']}와 연결을 보완한다."),
                         issue(units[16]["paragraph_id"], "현재 문단의 흐름을 보완한다.")] + [
        issue(units[0]["paragraph_id"], f"선택적인 문체 개선 {i}: " + "원래 경고 사유. " * 100, "warning") for i in range(114)]}
    return packet, previous, parts, report


class EditorialRevisionBatchTests(unittest.TestCase):
    def test_only_target_errors_references_and_neighbors_are_editable_and_warnings_are_saved(self):
        packet, previous, parts, report = setup_revision()
        original = copy.deepcopy(report)
        calls = []
        def client(system, body, schema, path):
            calls.append(copy.deepcopy(body))
            self.assertEqual(body["source_parts"], parts)
            self.assertEqual(body["output_mode"], "fixed_spans")
            self.assertTrue(all(i["severity"] == "error" for i in body["revision"]["review"]["issues"]))
            self.assertLessEqual(request_bytes(system, compact_packet(body), schema), int(request_limit() * .75))
            return editorial_reply(body)
        with TemporaryDirectory() as tmp, patch("editorial_patch.ASSEMBLY_BATCH_SPANS", 3):
            result = revise_editorial(PlannedPaper(tmp, client), Path(tmp), "generate-1", "section", previous, {"s1": packet}, report)
            progress = json.loads((Path(tmp) / f"generate-1-{REVISION_BATCH_POLICY}-progress.json").read_bytes())
        self.assertEqual(result, previous)
        self.assertEqual(report, original)
        self.assertEqual(progress["deferred_warnings"], report["issues"][2:])
        self.assertEqual(len(calls), 3)
        reasons = [{i["reason"] for i in b["revision"]["review"]["issues"]} for b in calls]
        self.assertEqual(reasons[0], {report["issues"][0]["reason"]})
        self.assertEqual(reasons[1], {report["issues"][1]["reason"]})
        self.assertEqual(reasons[2], {report["issues"][0]["reason"]})
        edited = {key for b in calls for rows in b["editable_spans"].values() for keys in rows.values() for key in keys}
        expected = {parts["s1"]["p0"][i]["id"] for i in (4, 5, 6, 15, 16, 17, 27, 28, 29)}
        self.assertEqual(edited, expected)

    def test_interruption_resumes_remaining_batches_with_prior_changes_in_full_context(self):
        packet, previous, parts, report = setup_revision()
        report["issues"][0]["paragraph_id"] = "none"  # Whole-section flow error.
        calls, interrupted = [], []
        def client(system, body, schema, path):
            calls.append(copy.deepcopy(body))
            raw = editorial_reply(body)
            first = parts["s1"]["p0"][0]["id"]
            if body["batch"]["index"] == 0:
                raw["sections"]["s1"]["parts"]["p0"][first].update(action="replace", text="앞 묶음에서 보완한 연결이다.")
            else:
                self.assertEqual(body["source_parts"]["s1"]["p0"][0]["text"], "앞 묶음에서 보완한 연결이다.")
                if not interrupted:
                    interrupted.append(True)
                    raise RuntimeError("revision batch interruption")
            return raw
        before = copy.deepcopy(previous)
        with TemporaryDirectory() as tmp:
            engine = PlannedPaper(tmp, client)
            with self.assertRaisesRegex(RuntimeError, "revision batch interruption"):
                revise_editorial(engine, Path(tmp), "generate-1", "section", previous, {"s1": packet}, report)
            self.assertEqual(previous, before)
            progress = json.loads((Path(tmp) / f"generate-1-{REVISION_BATCH_POLICY}-progress.json").read_bytes())
            self.assertEqual(progress["status"], "pending")
            count = len(calls)
            result = revise_editorial(engine, Path(tmp), "generate-1", "section", previous, {"s1": packet}, report)
            self.assertTrue(all(b["batch"]["index"] == 1 for b in calls[count:]))
            self.assertTrue(result["s1"]["parts"]["p0"].startswith("앞 묶음에서 보완한 연결이다."))
            count = len(calls)
            self.assertEqual(revise_editorial(engine, Path(tmp), "generate-1", "section", previous, {"s1": packet}, report), result)
            self.assertEqual(len(calls), count)

    def test_other_readonly_context_slots_are_rejected_before_applying_a_batch(self):
        packet, previous, parts, report = setup_revision()
        calls = []
        def client(system, body, schema, path):
            calls.append(copy.deepcopy(body))
            raw = editorial_reply(body)
            if len(calls) == 1:
                raw["sections"]["s1"]["parts"]["p0"][parts["s1"]["p0"][0]["id"]] = {
                    "action": "delete", "text": "", "join_previous": False}
            return raw
        with TemporaryDirectory() as tmp:
            result = revise_editorial(PlannedPaper(tmp, client), Path(tmp), "generate-1", "section", previous, {"s1": packet}, report)
        self.assertEqual(result, previous)
        self.assertEqual(len(calls), 2)
        self.assertIn("invalid_response", calls[1])

    def test_completed_large_fixed_slot_revision_cache_is_still_reused(self):
        packet, previous, parts, report = setup_revision()
        section = packet["section_plan"]
        body = {"operation": "editorial_revision", "output_mode": "fixed_slots", "review_policy": REVISION_POLICY,
            "workflow_stage": "section", "base_fingerprint": fingerprint(previous),
            "outline": [{**{k: section[k] for k in ("id", "title", "purpose", "subsections")},
                         "required_content": [i["description"] for i in section["required_items"]]}],
            "source_parts": parts, "revision": {"review": {"checks": [], "issues": report["issues"]}, "previous_revision_result": None}}
        calls = []
        def client(system, body, schema, path):
            calls.append(body)
            return editorial_reply(body)
        with TemporaryDirectory() as tmp:
            engine = PlannedPaper(tmp, client)
            engine.call(Path(tmp), f"generate-1-{REVISION_POLICY}", INSTRUCTION, compact_packet(body), patch_schema(parts))
            self.assertEqual(revise_editorial(engine, Path(tmp), "generate-1", "section", previous, {"s1": packet}, report), previous)
        self.assertEqual(len(calls), 1)

    def test_warning_only_report_does_not_trigger_rewriting_and_keeps_warning_record(self):
        packet, previous, _, report = setup_revision()
        report["issues"] = report["issues"][2:]
        with TemporaryDirectory() as tmp:
            def client(*args):
                raise AssertionError("Warnings alone must not trigger a large rewrite")
            result = revise_editorial(PlannedPaper(tmp, client), Path(tmp), "generate-1", "section", previous, {"s1": packet}, report)
            progress = json.loads((Path(tmp) / f"generate-1-{REVISION_BATCH_POLICY}-progress.json").read_bytes())
            self.assertEqual(progress["total_batches"], 0)
            self.assertEqual(progress["deferred_warnings"], report["issues"])
            self.assertEqual(result, previous)

    def test_invalid_finding_cannot_be_silently_dropped(self):
        _, _, parts, report = setup_revision()
        report["issues"][0]["paragraph_id"] = "s1_p99999"
        with self.assertRaises(ValueError):
            revision_batch_targets(parts, report["issues"])


if __name__ == "__main__":
    unittest.main()
