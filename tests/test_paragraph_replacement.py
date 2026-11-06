import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from bounded_drafting import REVISION, generate_bounded, generation_fragments
from paragraph_revision import (CITATION_POLICY, LEGACY_INSTRUCTION, POLICY, ParagraphGrowthError,
                                render_replacement, replacement_input, replace_paragraph, scope_request,
                                schema_for)
from draft_prose import PROTOCOL, structured_system
from drafting_budget import call_bounded
from planned_paper import GROUNDING, WRITER, PlannedPaper, parts_schema
from test_draft_revision import revision_fixture


def fixture():
    _, _, packet, before, _ = revision_fixture()
    packet["revision"]["evidence_link_gaps"] = []
    packet["revision"]["review"]["checks"] = []
    return packet, before


class ParagraphReplacementTests(unittest.TestCase):
    def test_wire_separates_existing_citations_without_changing_saved_source_or_facts(self):
        packet, _ = fixture()
        tasks = generation_fragments(GROUNDING + WRITER, packet, {"s0": packet})
        request = next(r for _, _, _, r, schema in tasks if schema is not None)
        request["source_body"] = "조건 A를 유지한다. [근거:E001,Hsample_2] 결과는 관찰이다. [근거:E001]"
        original = copy.deepcopy(request)
        wire = replacement_input(request)
        self.assertEqual(wire["source_body"], "조건 A를 유지한다.  결과는 관찰이다.")
        self.assertEqual(wire["source_evidence_ids"], ["E001", "Hsample_2"])
        self.assertEqual(wire["facts"], original["facts"])
        self.assertEqual(wire["revision"], original["revision"])
        self.assertEqual(request, original)

    def test_mixed_citation_failure_gets_one_correction_with_metadata_only_protocol(self):
        packet, _ = fixture()
        calls = []
        def client(system, request, schema, path):
            calls.append(request)
            self.assertIn("text에는 [근거:...] 표시를 넣지 않는다", system)
            self.assertIn("후보·비교 묶음 전체를 일괄 연결하지 않는다", system)
            self.assertNotIn("[근거:", request["source_body"])
            self.assertEqual(request["source_evidence_ids"], ["F3", "F4", "F5"])
            if len(calls) == 1:
                return {"parts": {"p0": {"text": "추정이다. [근거:F3]", "evidence_ids": ["F3", "F4"]}}}
            self.assertIn("일치하지 않아", request["replacement_validation_error"]["reason"])
            return {"parts": {"p0": {"text": "두 관찰 범위의 추정이다.", "evidence_ids": ["F3", "F4"]}}}
        with TemporaryDirectory() as tmp:
            result = generate_bounded(PlannedPaper(tmp, client), Path(tmp), "generate-1", GROUNDING + WRITER,
                packet, parts_schema(packet), {"s0": packet}, True)
        self.assertEqual(len(calls), 2)
        self.assertIn("두 관찰 범위의 추정이다. [근거:F3,F4]", result["parts"]["p0"])

    def test_valid_old_replacement_is_reused_but_invalid_old_reply_is_preserved_and_bypassed(self):
        packet, _ = fixture()
        tasks = generation_fragments(GROUNDING + WRITER, packet, {"s0": packet})
        request = next(r for _, _, _, r, schema in tasks if schema is not None)
        system = GROUNDING + WRITER
        legacy_system = structured_system(system).replace(PROTOCOL, "") + LEGACY_INSTRUCTION
        for valid in (True, False):
            with self.subTest(valid=valid), TemporaryDirectory() as tmp:
                calls = []
                def client(system, request, schema, path):
                    calls.append(path)
                    text = "추정이다." if valid or len(calls) > 1 else "추정이다. [근거:F3]"
                    return {"parts": {"p0": {"text": text, "evidence_ids": ["F3", "F4"]}}}
                engine = PlannedPaper(tmp, client)
                call_bounded(engine, Path(tmp), "generate-1-" + POLICY, legacy_system, request, schema_for(request))
                old_files = {p: p.read_bytes() for p in (Path(tmp) / "responses").iterdir()}
                old_invalid = Path(tmp) / f"generate-1-{POLICY}-invalid-0.json"
                old_invalid.write_text('{"original":true}', encoding="utf-8")
                result, warning = replace_paragraph(engine, Path(tmp), "generate-1", system, request)
                self.assertIsNone(warning)
                self.assertIn("[근거:F3,F4]", result)
                self.assertEqual(len(calls), 1 if valid else 2)
                if not valid:
                    self.assertIn(CITATION_POLICY, calls[-1].name)
                self.assertEqual(old_invalid.read_text(encoding="utf-8"), '{"original":true}')
                self.assertTrue(all(p.read_bytes() == body for p, body in old_files.items()))

    def test_repeated_mismatches_are_not_repaired_by_unioning_or_discarding_ids(self):
        packet, _ = fixture()
        calls = []
        def client(*args):
            calls.append(1)
            return {"parts": {"p0": {"text": "추정이다. [근거:F3]", "evidence_ids": ["F3", "F4"]}}}
        with TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "본문·근거 형식"):
                generate_bounded(PlannedPaper(tmp, client), Path(tmp), "generate-1", GROUNDING + WRITER,
                    packet, parts_schema(packet), {"s0": packet}, True)
        self.assertEqual(len(calls), 2)

    def test_one_request_one_slot_preserves_comparison_context_and_removes_unrelated_obligations(self):
        packet, before = fixture()
        packet["tables"] = [{"id": "comparison", "evidence_ids": ["F3", "F4"], "columns": ["A", "B"], "rows": [[1, 2]]}]
        original = copy.deepcopy(packet)
        with patch.dict("os.environ", {"PAPER_REQUEST_MAX_BYTES": "50000"}):
            tasks = generation_fragments(GROUNDING + WRITER + REVISION, packet, {"s0": packet})
        edits = [(r, s) for _, _, _, r, s in tasks if s is not None]
        self.assertEqual(len(edits), 1)
        request, schema = edits[0]
        self.assertEqual(request["fragment"]["paragraph_id"], "s0_p2")
        self.assertEqual(request["source_body"], before.split("\n\n")[1])
        self.assertEqual(request["section_plan"]["required_items"], [])
        self.assertTrue(request["section_context"]["required_content_context"])
        self.assertEqual(schema["properties"]["parts"]["properties"]["p0"]["type"], "object")
        self.assertEqual({f["id"] for f in request["facts"]}, {"F3", "F4", "F5"})
        self.assertTrue({"F3", "F4"} <= set(request["tables"][0]["evidence_ids"]))
        by_id = {f["id"]: f for f in packet["facts"]}
        self.assertTrue(all(f == by_id[f["id"]] for f in request["facts"]))
        self.assertEqual(scope_request(request)["section_context"], request["section_context"])
        self.assertEqual(packet, original)

    def test_repeated_multi_paragraph_output_preserves_original_instead_of_growing(self):
        packet, before = fixture()
        calls = []
        def client(system, request, schema, path):
            calls.append(request)
            return {"parts": {"p0": [{"text": "추정이다.", "evidence_ids": ["F3"]}] * 8}}
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {"PAPER_REQUEST_MAX_BYTES": "50000"}):
            engine, warnings = PlannedPaper(tmp, client), []
            result = generate_bounded(engine, Path(tmp), "generate-1", GROUNDING + WRITER, packet,
                parts_schema(packet), {"s0": packet}, True, on_warning=warnings.append)
            self.assertEqual(result["parts"]["p0"], before)
            self.assertEqual(len(calls), 2)
            self.assertEqual(warnings[0]["validation_code"], "paragraph_revision_deferred")
            manifest = json.loads((Path(tmp) / "generate-1-split-manifest.json").read_bytes())
            edits = [t for t in manifest["tasks"] if t.get("operation") == "revise_paragraph"]
            self.assertEqual(len(edits), 1)
            self.assertTrue(edits[0]["original_preserved"])
            self.assertEqual(edits[0]["paragraph_count"], 1)
            generate_bounded(engine, Path(tmp), "generate-1", GROUNDING + WRITER, packet,
                parts_schema(packet), {"s0": packet}, True)
            self.assertEqual(len(calls), 2)

    def test_single_object_replaces_only_target_and_reuses_new_cache(self):
        packet, before = fixture()
        calls = []
        def client(system, request, schema, path):
            calls.append(request)
            return {"parts": {"p0": {"text": "구현 결과가 아닌 추정이다.", "evidence_ids": ["F3", "F4", "F5"]}}}
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {"PAPER_REQUEST_MAX_BYTES": "50000"}):
            engine = PlannedPaper(tmp, client)
            result = generate_bounded(engine, Path(tmp), "generate-1", GROUNDING + WRITER, packet, parts_schema(packet), {"s0": packet}, True)
            paragraphs = result["parts"]["p0"].split("\n\n")
            self.assertEqual(len(paragraphs), 3)
            self.assertEqual(paragraphs[0], before.split("\n\n")[0])
            self.assertEqual(paragraphs[2], before.split("\n\n")[2])
            self.assertIn("구현 결과가 아닌 추정", paragraphs[1])
            self.assertEqual(generate_bounded(engine, Path(tmp), "generate-1", GROUNDING + WRITER, packet, parts_schema(packet), {"s0": packet}, True), result)
            self.assertEqual(len(calls), 1)

    def test_whole_part_length_finding_does_not_rewrite_every_paragraph(self):
        packet, before = fixture()
        packet["revision"]["review"]["issues"] = [{"section_id": "s0", "paragraph_id": "none", "severity": "error",
            "validation_code": "composition_length", "reason": "Shorten the whole part.", "evidence_ids": []}]
        def client(*args):
            raise AssertionError("No paragraph-specific correction exists")
        with TemporaryDirectory() as tmp:
            result = generate_bounded(PlannedPaper(tmp, client), Path(tmp), "generate-1", GROUNDING + WRITER,
                packet, parts_schema(packet), {"s0": packet}, True)
            self.assertEqual(result["parts"]["p0"], before)

    def test_old_whole_revision_cache_cannot_replay_a_multiplied_candidate(self):
        packet, before = fixture()
        calls = []
        def client(system, request, schema, path):
            calls.append(path)
            if len(calls) == 1:
                return {"parts": {"p0": "추정이다. [근거:F3]\n\n" * 8}}
            return {"parts": {"p0": {"text": "추정이다.", "evidence_ids": ["F3"]}}}
        with TemporaryDirectory() as tmp:
            engine = PlannedPaper(tmp, client)
            engine.call(Path(tmp), "generate-1", GROUNDING + WRITER + REVISION, packet, parts_schema(packet))
            old_path = next((Path(tmp) / "responses").glob("generate-1-*.json"))
            old_bytes = old_path.read_bytes()
            result = generate_bounded(engine, Path(tmp), "generate-1", GROUNDING + WRITER, packet, parts_schema(packet), {"s0": packet}, True)
            self.assertEqual(len(result["parts"]["p0"].split("\n\n")), 3)
            self.assertEqual(old_path.read_bytes(), old_bytes)
            self.assertEqual(len(calls), 2)

    def test_unknown_citations_remain_blocking_instead_of_becoming_a_growth_warning(self):
        packet, _ = fixture()
        def client(*args):
            return {"parts": {"p0": {"text": "추정이다.", "evidence_ids": ["UNKNOWN"]}}}
        with TemporaryDirectory() as tmp:
            warnings = []
            with self.assertRaisesRegex(ValueError, "본문·근거 형식"):
                generate_bounded(PlannedPaper(tmp, client), Path(tmp), "generate-1", GROUNDING + WRITER,
                    packet, parts_schema(packet), {"s0": packet}, True, on_warning=warnings.append)
            self.assertEqual(warnings, [])

    def test_multiline_text_cannot_evade_single_paragraph_guard(self):
        packet, _ = fixture()
        tasks = generation_fragments(GROUNDING + WRITER, packet, {"s0": packet})
        request = next(r for _, _, _, r, schema in tasks if schema is not None)
        with self.assertRaises(ParagraphGrowthError):
            render_replacement({"parts": {"p0": {"text": "첫 관측.\n\n다른 관측.", "evidence_ids": ["F3"]}}}, request)

    def test_shared_failed_item_does_not_reintroduce_sibling_paragraph_quotes(self):
        packet, _ = fixture()
        packet["revision"]["review"]["checks"] = [{"item_id": "item0", "verdict": "missing",
            "paragraph_ids": ["s0_p1", "s0_p2"], "evidence_ids": ["F3"],
            "quote": "Sibling quotation", "paragraph_quotes": ["Sibling quotation", "Target quotation"]}]
        tasks = generation_fragments(GROUNDING + WRITER, packet, {"s0": packet})
        request = next(r for _, _, _, r, schema in tasks if schema is not None and r["fragment"].get("paragraph_id") == "s0_p2")
        check = request["revision"]["review"]["checks"][0]
        self.assertEqual(check["paragraph_ids"], ["s0_p2"])
        self.assertNotIn("quote", check)
        self.assertNotIn("paragraph_quotes", check)
        self.assertNotIn("Sibling quotation", json.dumps(scope_request(request)))

    def test_whole_part_length_warning_is_not_forwarded_as_editor_shortening_task(self):
        from test_hierarchical_drafting import Client
        from test_planned_paper import research
        client, editor_packets, leaf_packets = Client(), [], []
        def respond(system, request, schema, path):
            raw = client(system, request, schema, path)
            if request.get("operation") == "editorial_assembly":
                editor_packets.append((path.parent.parent.name, request))
            elif "parts" in schema["properties"]:
                leaf_packets.append(request)
            return raw
        with TemporaryDirectory() as tmp:
            result = PlannedPaper(tmp, respond).run(research(), writing_target_chars=40)
            self.assertTrue(result["review"]["approved"])
            self.assertTrue(editor_packets)
            self.assertFalse(any("소절 전체 축약 과제" in request.get("composition_guidance", "") for stage, request in editor_packets))
            self.assertFalse(any("writing_targets" in request for stage, request in editor_packets))
            self.assertTrue(any(i.get("validation_code") == "composition_length"
                for stage in result["review_warnings"]["stages"] for i in stage["warnings"]))
            self.assertFalse(any(i.get("validation_code") == "composition_length" for request in leaf_packets
                for i in request.get("revision", {}).get("review", {}).get("issues", [])))


if __name__ == "__main__":
    unittest.main()
