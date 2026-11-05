import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from editorial_patch import (SubsectionRemovalError, apply_editorial_patch,
                             assemble_editorial_patch, revise_editorial_patch)
from editorial_revision import editorial_sources
from planned_paper import PlannedPaper, load_latest
from review_test_support import editorial_reply
from test_editorial_patch import setup_patch, keep_slots, span
from test_hierarchical_drafting import Client
from test_planned_paper import research


class EditorialPreservationTests(unittest.TestCase):
    def test_whole_subsection_deletion_identifies_scope_and_applies_nothing(self):
        packet, previous, _, parts, origins = setup_patch()
        before = copy.deepcopy(previous)
        raw = keep_slots(parts)
        for key, units in parts["s1"].items():
            for unit in units:
                span(raw, key, unit).update(action="delete")
        with self.assertRaises(SubsectionRemovalError) as caught:
            apply_editorial_patch(raw, previous, {"s1": packet}, parts, origins)
        self.assertEqual({r["part"] for r in caught.exception.subsections}, {"p0", "p1"})
        self.assertIn("keep 또는 replace", str(caught.exception))
        self.assertEqual(previous, before)

    def test_repair_can_shorten_subsection_while_retaining_core_body(self):
        packet, previous, report, parts, _ = setup_patch()
        calls = []
        def client(system, body, schema, path):
            calls.append(copy.deepcopy(body))
            self.assertIn("소절 전체를 삭제하거나 빈 본문", system)
            raw = editorial_reply(body)
            for unit in parts["s1"]["p0"]:
                span(raw, "p0", unit).update(action="delete")
            if len(calls) == 2:
                self.assertEqual(body["invalid_response"]["validation_code"], "subsection_removal")
                self.assertEqual(body["invalid_response"]["protected_subsections"][0]["part"], "p0")
                span(raw, "p0", parts["s1"]["p0"][0]).update(action="replace", text="소절의 핵심 설명과 적용 범위를 간결히 남긴다.")
            return raw
        with TemporaryDirectory() as tmp:
            result = revise_editorial_patch(PlannedPaper(tmp, client), Path(tmp), "edit", "section", previous, {"s1": packet}, report)
        self.assertEqual(len(calls), 2)
        self.assertEqual(result["s1"]["parts"]["p0"], "소절의 핵심 설명과 적용 범위를 간결히 남긴다. [근거:F1]")
        self.assertEqual(result["s1"]["parts"]["p1"], previous["s1"]["parts"]["p1"])

    def test_exhausted_repair_keeps_erased_part_and_applies_other_valid_changes(self):
        for initial in (True, False):
            with self.subTest(initial=initial), TemporaryDirectory() as tmp:
                packet, previous, report, _, _ = setup_patch()
                calls = []
                def client(system, body, schema, path):
                    calls.append(body)
                    raw = editorial_reply(body)
                    for slot in raw["sections"]["s1"]["parts"]["p1"].values():
                        spans = slot.get("spans", {"flat": slot})
                        for value in spans.values():
                            value.update(action="delete", text="")
                    first = next(iter(raw["sections"]["s1"]["parts"]["p0"].values()))
                    target = next(iter(first["spans"].values())) if "spans" in first else first
                    target.update(action="replace", text="다른 소절의 연결은 정상적으로 보완했다.")
                    return raw
                engine = PlannedPaper(tmp, client)
                def execute():
                    if initial:
                        return assemble_editorial_patch(engine, Path(tmp), "edit", "section", previous, {"s1": packet})
                    return revise_editorial_patch(engine, Path(tmp), "edit", "paper", previous, {"s1": packet}, report)
                result = execute()
                self.assertEqual(len(calls), 2)
                self.assertEqual(result["s1"]["parts"]["p1"], previous["s1"]["parts"]["p1"])
                self.assertIn("다른 소절의 연결은", result["s1"]["parts"]["p0"])
                provenance = json.loads(next(Path(tmp).glob("*-provenance.json")).read_text(encoding="utf-8"))
                self.assertEqual(provenance["preserved_subsections"][0]["part"], "p1")
                self.assertEqual(execute(), result)
                self.assertEqual(len(calls), 2)

    def test_batched_deletions_cannot_cumulatively_erase_subsection(self):
        packet, previous, _, _, _ = setup_patch()
        calls = []
        def client(system, body, schema, path):
            calls.append(body)
            raw = editorial_reply(body)
            for slot in raw["sections"]["s1"]["parts"].get("p0", {}).values():
                slot.update(action="delete", text="")
            return raw
        with TemporaryDirectory() as tmp, patch("editorial_patch.ASSEMBLY_BATCH_SPANS", 1):
            result = assemble_editorial_patch(PlannedPaper(tmp, client), Path(tmp), "edit", "section", previous, {"s1": packet})
            provenance = json.loads(next(Path(tmp).glob("*-provenance.json")).read_text(encoding="utf-8"))
        self.assertEqual(result, previous)
        self.assertEqual(provenance["preserved_subsections"][0]["part"], "p0")
        self.assertEqual(len(calls), 6)  # Five batches and one bounded repair.

    def test_other_invalid_edits_still_fail_and_do_not_publish_partial_changes(self):
        packet, previous, report, parts, _ = setup_patch()
        before = copy.deepcopy(previous)
        def client(system, body, schema, path):
            raw = keep_slots(parts)
            for unit in parts["s1"]["p0"]:
                span(raw, "p0", unit).update(action="delete")
            raw["sections"]["s1"]["parts"]["p1"]["UNKNOWN"] = {}
            return raw
        with TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "고정 출력 칸"):
                revise_editorial_patch(PlannedPaper(tmp, client), Path(tmp), "edit", "section", previous, {"s1": packet}, report)
            self.assertFalse(list(Path(tmp).glob("*-provenance.json")))
        self.assertEqual(previous, before)

    def test_preservation_warning_reaches_final_review_and_survives_cache_reload(self):
        client = Client()
        client.reject_once = "section-s1"
        def respond(system, body, schema, path):
            raw = client(system, body, schema, path)
            if body.get("operation") == "editorial_revision" and path.parent.parent.name == "section-s1":
                for slot in raw["sections"]["s1"]["parts"]["p1"].values():
                    for value in slot["spans"].values():
                        value.update(action="delete", text="")
            return raw
        with TemporaryDirectory() as tmp:
            engine = PlannedPaper(tmp, respond)
            result = engine.run(research())
            warnings = result["review"]["editorial_warnings"]
            guarded = [w for w in warnings if w.get("validation_code") == "subsection_removal_prevented"]
            self.assertEqual(len(guarded), 1)
            self.assertEqual(guarded[0]["part"], "p1")
            self.assertEqual(result["review"]["editorial_status"], "needs_attention")
            self.assertIn("배정된 원문 범위의 설명이다.", result["sections"]["s1"])
            self.assertEqual(load_latest(tmp)["review"]["editorial_warnings"], warnings)
            count = len(client.events)
            resumed = engine.run(research())
            self.assertEqual(resumed["review"]["editorial_warnings"], warnings)
            self.assertEqual(len(client.events), count)


if __name__ == "__main__":
    unittest.main()
