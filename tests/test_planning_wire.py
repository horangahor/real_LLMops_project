import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import requests

from paper_plan import bind_plan_evidence, plan_schema, project_profile, validate_plan
from planned_paper import PlannedPaper, request_json
from planning_wire import (INSTRUCTION, LEGACY_INSTRUCTION, bounded_plan_schema,
                           call_plan, restore_chapter_evidence)
from test_planned_paper import FakeClient, plan, research


def wire_plan():
    value = plan()
    for section in value["sections"]:
        section.pop("evidence_ids")
    return value


def response():
    return Mock(status_code=200, json=lambda: {"choices": [
        {"finish_reason": "stop", "message": {"content": '{"ok": true}'}}]})


class PlanningWireTests(unittest.TestCase):
    def test_wire_exposes_existing_chapter_and_subsection_bounds_without_changing_other_arrays(self):
        original = plan_schema(research(), {}, derive_chapter_evidence=True)
        before = copy.deepcopy(original)
        schema = bounded_plan_schema(original, project_profile("generic"))
        sections = schema["properties"]["sections"]
        self.assertEqual((sections["minItems"], sections["maxItems"]), (2, 8))
        props = sections["items"]["properties"]
        self.assertEqual(props["subsections"]["maxItems"], 6)
        self.assertEqual(props["subsections"]["items"]["type"], "string")
        self.assertNotIn("maxItems", props["depends_on"])
        self.assertNotIn("maxItems", schema["properties"]["generation_order"])
        self.assertNotIn("description", schema["properties"]["generation_order"]["items"])
        self.assertEqual(original, before)

    def test_complete_old_wire_cache_is_reused_and_partial_old_cache_is_preserved_but_bypassed(self):
        for complete in (True, False):
            with self.subTest(complete=complete), TemporaryDirectory() as tmp:
                calls = []
                def client(*args):
                    calls.append(1)
                    value = wire_plan()
                    if not complete and len(calls) == 1:
                        value["sections"] = value["sections"][:1]
                    return value
                engine = PlannedPaper(tmp, client)
                folder = Path(tmp)
                old_wire = plan_schema(research(), {}, derive_chapter_evidence=True)
                legacy_schema = plan_schema(research(), {})
                schema = bounded_plan_schema(old_wire, project_profile("generic"))
                engine.call(folder, "plan", "system" + LEGACY_INSTRUCTION, {}, old_wire)
                path = next((folder / "responses").glob("plan-*.json"))
                original = path.read_bytes()
                actual = call_plan(engine, folder, "plan", "system", {}, schema, legacy_schema)
                self.assertEqual(len(actual["sections"]), 3)
                self.assertEqual(len(calls), 1 if complete else 2)
                self.assertEqual(path.read_bytes(), original)

    def test_partial_plan_reports_missing_chapters_and_reuses_valid_correction(self):
        calls = []
        def client(system, packet, schema, path):
            calls.append(copy.deepcopy(packet))
            value = wire_plan()
            if "rejected_plan" not in packet:
                value["sections"] = value["sections"][:1]
            else:
                self.assertIn("실제=1개", packet["validation_error"])
                self.assertIn("s1", packet["validation_error"])
                self.assertIn("s2", packet["validation_error"])
            return value
        with TemporaryDirectory() as tmp:
            engine = PlannedPaper(tmp, client)
            first = engine.run(research(), plan_only=True)
            root = Path(first["run_dir"])
            originals = {p: p.read_bytes() for p in (root / "responses").glob("*.json")}
            again = engine.run(research(), plan_only=True)
            self.assertEqual(first["plan"], again["plan"])
            self.assertEqual(len(calls), 2)
            self.assertTrue(all(p.read_bytes() == body for p, body in originals.items()))
            self.assertEqual(len(json.loads((root / "plan-rejected.json").read_bytes())["plan"]["sections"]), 1)

    def test_schema_omits_only_derived_chapter_list(self):
        original = plan_schema(research(), {})
        expected = copy.deepcopy(original)
        section = expected["properties"]["sections"]["items"]
        section["properties"].pop("evidence_ids")
        section["required"].remove("evidence_ids")
        self.assertEqual(plan_schema(research(), {}, derive_chapter_evidence=True), expected)
        self.assertEqual(section["properties"]["required_items"]["items"]["properties"]["evidence_ids"]["items"]["enum"], ["F1", "F2"])
        self.assertIn("evidence_ids", original["properties"]["sections"]["items"]["required"])

    def test_restore_and_bind_keep_both_comparison_sides_and_table_evidence(self):
        value, data = wire_plan(), research()
        value["sections"][1]["required_items"][0]["evidence_ids"] = ["F2", "F1", "F2"]
        data["facts"].append({"id": "F3", "statement": "表の条件", "limits": "観測のみ", "sources": []})
        data["tables"] = [{"id": "T1", "evidence_ids": ["F1", "F3"]}]
        value["sections"][1]["table_ids"] = ["T1"]
        original = copy.deepcopy(value)
        result = bind_plan_evidence(restore_chapter_evidence(value), data)
        self.assertEqual(result["sections"][1]["evidence_ids"], ["F2", "F1", "F3"])
        self.assertEqual(result["sections"][1]["required_items"][0]["evidence_ids"], ["F2", "F1"])
        self.assertEqual(value, original)

    def test_legacy_explicit_section_only_support_is_preserved(self):
        value = plan()
        restored = restore_chapter_evidence(value)
        self.assertEqual(restored, value)
        self.assertEqual(bind_plan_evidence(restored, research())["sections"][1]["evidence_ids"], ["F1", "F2"])

    def test_unknown_support_is_rejected_rather_than_removed(self):
        value = wire_plan()
        value["sections"][1]["required_items"][0]["evidence_ids"] = ["unknown"]
        with self.assertRaisesRegex(ValueError, "없는 근거"):
            bind_plan_evidence(restore_chapter_evidence(value), research())

    def test_wire_response_runs_with_one_plan_call_and_full_saved_schema(self):
        fake = FakeClient(wire_plan())
        schemas = []
        def client(system, packet, schema, path):
            schemas.append(copy.deepcopy(schema))
            return fake(system, packet, schema, path)
        with TemporaryDirectory() as tmp:
            engine = PlannedPaper(tmp, client)
            result = engine.run(research(), plan_only=True)
            validate_plan(result["plan"], research(), {}, project_profile("generic"))
            self.assertEqual(result["plan"]["sections"][1]["evidence_ids"], ["F1"])
            folder = Path(result["run_dir"])
            raw = next((folder / "responses").glob("plan-*.json"))
            before = raw.read_bytes()
            self.assertNotIn("evidence_ids", json.loads(before)["value"]["sections"][1])
            self.assertTrue((folder / "contexts/subsections/s1-p0.json").is_file())
            audit = json.loads((folder / "planning-input.json").read_bytes())
            self.assertLess(audit["serialized_input_bytes"], audit["input_bytes"])
            engine.run(research(), plan_only=True)
            self.assertEqual(raw.read_bytes(), before)
        self.assertEqual(len(fake.calls), 1)
        self.assertNotIn("evidence_ids", schemas[0]["properties"]["sections"]["items"]["properties"])
        self.assertIn(INSTRUCTION, fake.calls[0][0])

    def test_completed_legacy_response_is_reused_without_new_api_call(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp) / "draft_history/planned/generic/legacy"
            new_folder = folder.with_name("new-policy")
            fake = FakeClient(plan())
            engine = PlannedPaper(tmp, fake)
            old_schema, schema = plan_schema(research()), plan_schema(research(), derive_chapter_evidence=True)
            original = engine.call(folder, "plan", "system", {}, old_schema)
            path = next((folder / "responses").glob("plan-*.json"))
            before = path.read_bytes()
            actual = call_plan(engine, new_folder, "plan", "system", {}, schema, old_schema)
            self.assertEqual(actual, original)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(len(fake.calls), 1)
            self.assertTrue(list((new_folder / "responses").glob("*.reuse.json")))

    def test_two_failed_sends_never_become_completed_plan_cache(self):
        with TemporaryDirectory() as tmp, patch("planned_paper.time.sleep"), \
                patch("planned_paper.requests.post", side_effect=requests.ReadTimeout()) as post:
            engine = PlannedPaper(tmp, api_key="test-key")
            with self.assertRaisesRegex(RuntimeError, "전송 시도 2회"):
                call_plan(engine, Path(tmp), "plan", "system", {}, {}, {})
            self.assertEqual(post.call_count, 2)
            for path in Path(tmp).rglob("*.json"):
                self.assertNotIn("request_fingerprint", json.loads(path.read_bytes()))

    def test_compact_serialization_preserves_all_values_and_records_actual_bytes(self):
        packet = {"statement": "  시도했으며  완료는 미확인\n", "limits": "수치  12, 조건: A", "sources": [
            {"page": 12, "quote": ' a : "b", c ', "element_id": "src_1"}],
            "human_guidance": {"approval": "limited_accept", "notes": "일부 조건만 허용"}}
        original = copy.deepcopy(packet)
        with TemporaryDirectory() as tmp, patch("planned_paper.requests.post", return_value=response()) as post:
            path = Path(tmp) / "plan.native.json"
            request_json("system", packet, {}, path, "test-key", compact_input=True)
            content = post.call_args.kwargs["json"]["messages"][1]["content"]
            self.assertEqual(json.loads(content), original)
            self.assertEqual(packet, original)
            self.assertLess(len(content), len(json.dumps(packet, ensure_ascii=False)))
            audit = json.loads(path.with_suffix(".request.json").read_bytes())
            self.assertEqual(audit["input_bytes"], len(content.encode("utf-8")))
            self.assertEqual(audit["input_serialization"], "compact-json-v1")
            self.assertEqual(post.call_args.kwargs["timeout"], (15, 300))

    def test_only_plan_transports_use_compact_serialization(self):
        for name in ("plan", "plan-correction", "generate-0", "review-0"):
            with self.subTest(name=name), TemporaryDirectory() as tmp, \
                    patch("planned_paper.requests.post", return_value=response()) as post:
                packet = {"values": ["a", "b"], "nested": {"keep": "a  b"}}
                PlannedPaper(tmp, api_key="test-key").call(Path(tmp), name, "system", packet, {})
                content = post.call_args.kwargs["json"]["messages"][1]["content"]
                expected = json.dumps(packet, ensure_ascii=False,
                                      separators=(",", ":") if name in ("plan", "plan-correction") else None)
                self.assertEqual(content, expected)


if __name__ == "__main__":
    unittest.main()
