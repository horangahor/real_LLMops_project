import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from document_parse import write_json
from drafting_budget import DraftingBudgetError, compact_packet, request_bytes, request_limit
from editorial_patch import (ASSEMBLY_POLICY, ASSEMBLY_BATCH_POLICY, ASSEMBLY_INSTRUCTION,
                             assembly_schema, expand_assembly_slots)
from editorial_revision import edit_editorial, _edit_editorial_legacy, editorial_sources
from planned_paper import PlannedPaper, fingerprint
from review_test_support import editorial_reply
from test_editorial_revision import fixture


class EditorialAssemblyTests(unittest.TestCase):
    def test_initial_edit_reads_full_context_and_keeps_exact_text_without_echoing_it(self):
        for level in ("section", "paper"):
            with self.subTest(level=level), TemporaryDirectory() as tmp:
                _, packet, previous, _ = fixture()
                calls = []
                def client(system, body, schema, path):
                    calls.append(copy.deepcopy(body))
                    self.assertEqual(body["operation"], "editorial_assembly")
                    self.assertEqual(body["output_mode"], "fixed_spans")
                    self.assertEqual(set(body["source_parts"]["s1"]), {"p0", "p1"})
                    self.assertNotIn("revision", body)
                    self.assertNotIn("facts", body)
                    self.assertNotIn("evidence_ids", json.dumps(body))
                    return editorial_reply(body)
                engine = PlannedPaper(tmp, client)
                result = edit_editorial(engine, Path(tmp), "generate-0", level, previous, {"s1": packet})
                self.assertEqual(result, previous)
                self.assertEqual(edit_editorial(engine, Path(tmp), "generate-0", level, previous, {"s1": packet}), result)
                self.assertEqual(len(calls), 1)
                self.assertTrue((Path(tmp) / f"generate-0-{ASSEMBLY_POLICY}-provenance.json").is_file())

    def test_initial_replace_delete_and_join_preserve_individual_citation_bindings(self):
        _, packet, previous, _ = fixture()
        packet["subsection_assignments"]["p0"]["evidence_ids"] = ["F1", "F2"]
        previous["s1"]["parts"]["p0"] = "관측 A다. [근거:F1]\n\n중복 B다. [근거:F2]\n\n관측 C다. [근거:F1]"
        before = copy.deepcopy(previous)
        def client(system, body, schema, path):
            raw = editorial_reply(body)
            a, b, c = body["source_parts"]["s1"]["p0"]
            slots = raw["sections"]["s1"]["parts"]["p0"]
            slots[a["id"]].update(action="replace", text="A를 간결히 설명한다.")
            slots[b["id"]].update(action="delete")
            slots[c["id"]].update(action="replace", text="이어서 C를 설명한다.", join_previous=True)
            return raw
        with TemporaryDirectory() as tmp:
            result = edit_editorial(PlannedPaper(tmp, client), Path(tmp), "edit", "section", previous, {"s1": packet})
        self.assertEqual(previous, before)
        self.assertEqual(result["s1"]["parts"]["p0"], "A를 간결히 설명한다. [근거:F1] 이어서 C를 설명한다. [근거:F1]")
        self.assertEqual(result["s1"]["parts"]["p1"], previous["s1"]["parts"]["p1"])

    def test_format_repair_keeps_full_context_and_never_applies_partial_invalid_edit(self):
        _, packet, previous, _ = fixture()
        calls = []
        def client(system, body, schema, path):
            calls.append(copy.deepcopy(body))
            raw = editorial_reply(body)
            units = body["source_parts"]["s1"]["p0"]
            raw["sections"]["s1"]["parts"]["p0"][units[0]["id"]].update(action="replace", text="정상 연결이다.")
            if len(calls) == 1:
                raw["sections"]["s1"]["parts"]["p0"]["UNKNOWN"] = {"action": "delete", "text": "", "join_previous": False}
            return raw
        with TemporaryDirectory() as tmp:
            result = edit_editorial(PlannedPaper(tmp, client), Path(tmp), "edit", "section", previous, {"s1": packet})
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["source_parts"], calls[1]["source_parts"])
        self.assertIn("invalid_response", calls[1])
        self.assertTrue(result["s1"]["parts"]["p0"].startswith("정상 연결이다."))

    def test_completed_provenance_cache_is_reused_without_a_fixed_slot_model_call(self):
        _, packet, previous, _ = fixture()
        calls = []
        def client(system, body, schema, path):
            calls.append(body)
            self.assertNotIn("output_mode", body)
            return editorial_reply(body)
        with TemporaryDirectory() as tmp:
            engine = PlannedPaper(tmp, client)
            old = _edit_editorial_legacy(engine, Path(tmp), "generate-0", "section", previous, {"s1": packet})
            self.assertEqual(edit_editorial(engine, Path(tmp), "generate-0", "section", previous, {"s1": packet}), old)
        self.assertEqual(len(calls), 1)

    def test_timed_out_legacy_request_is_preserved_and_new_request_uses_fixed_spans(self):
        _, packet, previous, _ = fixture()
        native_paths = []
        def timeout_client(system, body, schema, path):
            native_paths.append(path)
            write_json(path, {"received_response": False, "request_error": "ReadTimeout"})
            raise RuntimeError("test legacy timeout")
        with TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, "legacy timeout"):
                _edit_editorial_legacy(PlannedPaper(tmp, timeout_client), Path(tmp), "generate-0", "section", previous, {"s1": packet})
            native = native_paths[0].read_bytes()
            calls = []
            def client(system, body, schema, path):
                calls.append(path.name)
                self.assertEqual(body["output_mode"], "fixed_spans")
                return editorial_reply(body)
            result = edit_editorial(PlannedPaper(tmp, client), Path(tmp), "generate-0", "section", previous, {"s1": packet})
            self.assertEqual(result, previous)
            self.assertEqual(native_paths[0].read_bytes(), native)
            self.assertEqual(len(calls), 1)
            self.assertIn(ASSEMBLY_POLICY, calls[0])

    def test_flat_schema_avoids_repeated_wrappers_and_rejects_join_in_nonfirst_span(self):
        _, packet, previous, _ = fixture()
        previous["s1"]["parts"]["p0"] = "관측 A다. [근거:F1] 관측 B다. [근거:F1]"
        parts, _, _ = editorial_sources(previous, {"s1": packet})
        schema = assembly_schema(parts)
        self.assertNotIn('"source_id"', json.dumps(schema))
        raw = editorial_reply({"output_mode": "fixed_spans", "source_parts": parts})
        raw["sections"]["s1"]["parts"]["p0"][parts["s1"]["p0"][1]["id"]]["join_previous"] = True
        with self.assertRaises(ValueError):
            expand_assembly_slots(raw, parts)

    def test_large_initial_edit_keeps_all_136_paragraphs_but_unchanged_output_has_no_prose(self):
        _, packet, previous, _ = fixture()
        previous["s1"]["parts"]["p0"] = "\n\n".join(f"Existing paragraph {i} " + "x" * 780 + " [근거:F1]" for i in range(135))
        calls = []
        def client(system, body, schema, path):
            calls.append(body)
            self.assertEqual(sum(len(u) for u in body["source_parts"]["s1"].values()), 136)
            self.assertLessEqual(sum(len(u) for rows in body["editable_spans"].values() for u in rows.values()), 24)
            self.assertLessEqual(request_bytes(system, compact_packet(body), schema), int(request_limit() * .75))
            raw = editorial_reply(body)
            self.assertLess(len(json.dumps(raw).encode()), len(previous["s1"]["parts"]["p0"].encode()) * .25)
            return raw
        with TemporaryDirectory() as tmp:
            result = edit_editorial(PlannedPaper(tmp, client), Path(tmp), "generate-0", "section", previous, {"s1": packet})
        self.assertEqual(result, previous)
        self.assertGreater(len(calls), 1)
        ids = [u for body in calls for rows in body["editable_spans"].values() for units in rows.values() for u in units]
        self.assertEqual(len(ids), 136)
        self.assertEqual(len(set(ids)), 136)

    def large_fixture(self):
        _, packet, previous, _ = fixture()
        previous["s1"]["parts"]["p0"] = "\n\n".join(f"원래 문맥 {i}다. [근거:F1]" for i in range(32))
        return packet, previous

    def test_batches_share_latest_full_context_and_resume_only_incomplete_requests(self):
        packet, previous = self.large_fixture()
        calls, interrupted = [], []
        def client(system, body, schema, path):
            calls.append(copy.deepcopy(body))
            raw = editorial_reply(body)
            first = body["source_parts"]["s1"]["p0"][0]
            if body["batch"]["index"] == 0:
                raw["sections"]["s1"]["parts"]["p0"][first["id"]].update(action="replace", text="앞 묶음에서 정리한 문맥이다.")
            else:
                self.assertEqual(first["text"], "앞 묶음에서 정리한 문맥이다.")
                if not interrupted:
                    interrupted.append(True)
                    raise RuntimeError("batch interruption")
            return raw
        before = copy.deepcopy(previous)
        with TemporaryDirectory() as tmp:
            engine = PlannedPaper(tmp, client)
            with self.assertRaisesRegex(RuntimeError, "batch interruption"):
                edit_editorial(engine, Path(tmp), "generate-0", "section", previous, {"s1": packet})
            self.assertEqual(previous, before)
            progress = json.loads((Path(tmp) / f"generate-0-{ASSEMBLY_BATCH_POLICY}-progress.json").read_bytes())
            self.assertEqual(progress["status"], "pending")
            self.assertEqual(len(progress["completed_batches"]), 1)
            count = len(calls)
            result = edit_editorial(engine, Path(tmp), "generate-0", "section", previous, {"s1": packet})
            self.assertTrue(result["s1"]["parts"]["p0"].startswith("앞 묶음에서 정리한 문맥이다."))
            self.assertTrue(all(body["batch"]["index"] == 1 for body in calls[count:]))
            count = len(calls)
            self.assertEqual(edit_editorial(engine, Path(tmp), "generate-0", "section", previous, {"s1": packet}), result)
            self.assertEqual(len(calls), count)

    def test_batch_rejects_returning_other_readonly_context_slots_before_applying_changes(self):
        packet, previous = self.large_fixture()
        calls = []
        def client(system, body, schema, path):
            calls.append(copy.deepcopy(body))
            raw = editorial_reply(body)
            if len(calls) == 1:
                foreign = body["source_parts"]["s1"]["p0"][-1]["id"]
                raw["sections"]["s1"]["parts"]["p0"][foreign] = {"action": "delete", "text": "", "join_previous": False}
            return raw
        with TemporaryDirectory() as tmp:
            result = edit_editorial(PlannedPaper(tmp, client), Path(tmp), "generate-0", "section", previous, {"s1": packet})
        self.assertEqual(result, previous)
        self.assertEqual(len(calls), 3)
        self.assertIn("invalid_response", calls[1])
        self.assertEqual(calls[0]["source_parts"], calls[1]["source_parts"])

    def test_large_successful_v1_response_is_reused_before_switching_to_batches(self):
        packet, previous = self.large_fixture()
        parts, _, _ = editorial_sources(previous, {"s1": packet})
        section = packet["section_plan"]
        body = {"operation": "editorial_assembly", "output_mode": "fixed_spans", "review_policy": ASSEMBLY_POLICY,
            "workflow_stage": "section", "base_fingerprint": fingerprint(previous),
            "outline": [{**{k: section[k] for k in ("id", "title", "purpose", "subsections")},
                         "required_content": [i["description"] for i in section["required_items"]]}], "source_parts": parts}
        calls = []
        def client(system, packet, schema, path):
            calls.append(packet)
            return editorial_reply(packet)
        with TemporaryDirectory() as tmp:
            engine = PlannedPaper(tmp, client)
            engine.call(Path(tmp), f"generate-0-{ASSEMBLY_POLICY}", ASSEMBLY_INSTRUCTION, compact_packet(body), assembly_schema(parts))
            self.assertEqual(edit_editorial(engine, Path(tmp), "generate-0", "section", previous, {"s1": packet}), previous)
            self.assertTrue((Path(tmp) / f"generate-0-{ASSEMBLY_POLICY}-provenance.json").is_file())
        self.assertEqual(len(calls), 1)

    def test_initial_full_context_over_budget_stops_without_a_model_call(self):
        _, packet, previous, _ = fixture()
        calls = []
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {"PAPER_REQUEST_MAX_BYTES": "4000"}):
            with self.assertRaisesRegex(DraftingBudgetError, "전체 본문 문맥"):
                edit_editorial(PlannedPaper(tmp, lambda *a: calls.append(a)), Path(tmp), "edit", "section", previous, {"s1": packet})
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
