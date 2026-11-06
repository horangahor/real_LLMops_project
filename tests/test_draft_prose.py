import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from bounded_drafting import generate_bounded
from draft_prose import allowed_ids, prose_schema, render_parts
from drafting_budget import SOURCE_PROTOCOL, compact_packet
from paper_context import build_contexts
from planned_paper import GROUNDING, WRITER, PlannedPaper, parts_schema
from test_drafting_budget import fixture
from test_hierarchical_drafting import Client, assigned_plan
from test_planned_paper import research


def paragraphs(text, ids):
    return [{"text": text, "evidence_ids": ids}]


class StructuredClient(Client):
    def __init__(self):
        super().__init__()
        self.invalid_once = None
        self.permanently_invalid = None

    def __call__(self, system, packet, schema, path):
        value = super().__call__(system, packet, schema, path)
        if ("generation_order" in schema["properties"] or "checks" in schema["properties"]
                or "findings" in schema["properties"] or packet.get("operation") in ("editorial_review", "editorial_revision", "editorial_assembly")):
            return value
        def convert(scoped, part_schema):
            result = {}
            for key, prop in part_schema["properties"]["parts"]["properties"].items():
                if prop["type"] not in ("array", "object"):
                    raise AssertionError("New generation calls must use the paragraph schema")
                ids = allowed_ids(scoped, key)
                result[key] = paragraphs("배정된 기록의 조건과 한계를 설명한다.", ids)
            return {"parts": result}
        if "parts" in schema["properties"]:
            result = convert(packet, schema)
        else:
            result = {"sections": {sid: convert(scoped, schema["properties"]["sections"]["properties"][sid])
                                   for sid, scoped in packet["section_packets"].items()}}
        stage = path.parent.parent.name
        if stage in (self.invalid_once, self.permanently_invalid):
            self.invalid_once = None
            result["parts"]["p0"][0]["evidence_ids"] = []
        return result


class DraftProseTests(unittest.TestCase):
    def packet(self):
        return build_contexts(assigned_plan(), research(), {})["sections"]["s1"]

    def test_paragraph_sources_are_rendered_without_guessing_or_mutating_model_response(self):
        packet = self.packet()
        response = {"parts": {"p0": [
            {"text": "조건 A를 비교했다.", "evidence_ids": ["F1", "F1"]},
            {"text": "같은 입력 범위에서만 해석한다.", "evidence_ids": ["F1"]}],
            "p1": paragraphs("관측값은 12였다.", ["F2"])}}
        original = copy.deepcopy(response)
        result = render_parts(response, packet)
        self.assertEqual(result["parts"]["p0"], "조건 A를 비교했다. [근거:F1]\n\n같은 입력 범위에서만 해석한다. [근거:F1]")
        self.assertEqual(result["parts"]["p1"], "관측값은 12였다. [근거:F2]")
        self.assertEqual(response, original)

    def test_schema_requires_citations_from_each_parts_own_allocation(self):
        schema = prose_schema(self.packet())["properties"]["parts"]["properties"]
        for key, ids in (("p0", ["F1"]), ("p1", ["F2"])):
            self.assertEqual(schema[key]["minItems"], 1)
            self.assertEqual(schema[key]["items"]["required"], ["text", "evidence_ids"])
            selection = schema[key]["items"]["properties"]["evidence_ids"]
            self.assertEqual(selection["minItems"], 1)
            self.assertEqual(selection["items"]["enum"], ids)

    def test_missing_or_invalid_sources_are_rejected_instead_of_auto_attached(self):
        invalid = [[], [{"text": "본문"}], paragraphs("본문", []), paragraphs("본문", ["unknown"]),
                   paragraphs("본문", ["F2"]), paragraphs("", ["F1"]),
                   paragraphs("첫 문단\n\n둘째 문단", ["F1"]), paragraphs("본문 [근거:F2]", ["F1"]),
                   paragraphs("## 새 제목", ["F1"]), paragraphs("| 직접 | 만든 표 |", ["F1"]),
                   "인용 없는 기존 본문"]
        for part in invalid:
            with self.subTest(part=part), self.assertRaises(ValueError):
                render_parts({"parts": {"p0": part, "p1": paragraphs("관측", ["F2"])}}, self.packet())

    def test_redundant_inline_citations_and_joined_paragraphs_normalize_only_when_bindings_match(self):
        packet = self.packet()
        packet["subsection_assignments"]["p0"]["evidence_ids"] = ["F1", "F2"]
        response = {"parts": {"p0": paragraphs("조건 설명이다. [근거:F1]\n\n관측 설명이다. [근거:F2]", ["F1", "F2"]),
                              "p1": paragraphs("관측 설명이다. [근거:F2] [근거:F2]", ["F2"])}}
        original = copy.deepcopy(response)
        rendered = render_parts(response, packet)
        self.assertEqual(rendered["parts"]["p0"], "조건 설명이다. [근거:F1]\n\n관측 설명이다. [근거:F2]")
        self.assertEqual(rendered["parts"]["p1"], "관측 설명이다. [근거:F2]")
        self.assertEqual(response, original)
        for text, ids in (("조건 [근거:F1]\n\n미연결 문단", ["F1"]),
                          ("조건 [근거:F1]\n\n관측 [근거:F2]", ["F1"]),
                          ("조건 [근거:unknown]", ["F1"]), ("조건 [근거:F1]", ["F1", "F2"])):
            bad = copy.deepcopy(response)
            bad["parts"]["p0"] = paragraphs(text, ids)
            with self.subTest(text=text, ids=ids), self.assertRaises(ValueError):
                render_parts(bad, packet)

    def test_format_repair_keeps_content_findings_and_does_not_spend_content_revision_budget(self):
        client = Client()
        client.plan["sections"][0]["required_items"][0]["evidence_ids"] = ["F1", "F2"]
        count = 0
        def response(system, packet, schema, path):
            nonlocal count
            raw = client(system, packet, schema, path)
            if path.parent.parent.name == "subsection-s0-p0" and "parts" in schema["properties"]:
                count += 1
                if count in (1, 3):
                    raw["parts"]["p0"] = "두 번째 근거 연결이 빠진 본문이다. [근거:F1]"
                elif count == 2:
                    raw["parts"]["p0"] = paragraphs("연결이 불명확한 본문 [근거:unknown]", ["F1"])
            return raw
        with TemporaryDirectory() as tmp:
            result = PlannedPaper(tmp, response).run(research())
            self.assertTrue(result["review"]["approved"])
            generations = [p for s, k, p in client.events if s == "subsection-s0-p0" and k == "generate"]
            self.assertEqual(len(generations), 4)  # three content attempts + one format-only repair
            repair_request = next(p for p in generations if "fragment_validation_error" in p or "replacement_validation_error" in p)
            repaired = repair_request["revision"]
            self.assertEqual(repaired["review"]["checks"][0]["missing_body_evidence_ids"], ["F2"])
            self.assertEqual(repaired["evidence_link_gaps"][0]["evidence_id"], "F2")
            self.assertEqual(repaired["evidence_link_gaps"][0]["statement"], research()["facts"][1]["statement"])
            self.assertIn("content_repair_instruction", repaired)
            self.assertNotIn("validation_error", generations[3]["revision"])
            folder = Path(result["run_dir"]) / "workflow/subsection-s0-p0"
            self.assertTrue(list(folder.glob("*invalid-*.json")))

    def test_new_format_runs_through_leaf_and_both_editors_and_reviewers(self):
        with TemporaryDirectory() as tmp:
            client = StructuredClient()
            result = PlannedPaper(tmp, client).run(research())
            self.assertTrue(result["review"]["approved"])
            self.assertEqual(result["metrics"]["reviewed_stages"], 8)
            for event, kind, packet in client.events:
                if kind == "review":
                    self.assertTrue(all("[근거:" in p["text"] for p in packet["draft_paragraphs"].values()))
            before = len(client.events)
            self.assertEqual(PlannedPaper(tmp, client).run(research())["draft_markdown"], result["draft_markdown"])
            self.assertEqual(len(client.events), before)

    def test_missing_source_is_repaired_before_review_without_regenerating_plan(self):
        with TemporaryDirectory() as tmp:
            client = StructuredClient()
            client.invalid_once = "subsection-s1-p1"
            result = PlannedPaper(tmp, client).run(research())
            self.assertTrue(result["review"]["approved"])
            self.assertEqual(sum(s == "subsection-s1-p1" and k == "generate" for s, k, _ in client.events), 2)
            self.assertEqual(sum(s == "subsection-s1-p1" and k == "review" for s, k, _ in client.events), 1)
            revision = next(p["revision"] for s, k, p in client.events if s == "subsection-s1-p1" and "revision" in p)
            self.assertIn("repair_instruction", revision)
            self.assertIn("evidence_ids", revision["validation_error"])
            self.assertEqual(sum("workflow_stage" not in p for _, _, p in client.events), 1)

    def test_identical_invalid_outputs_stop_before_third_call_and_keep_old_draft(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp) / "run"
            folder.mkdir()
            (folder / "draft.md").write_text("이전 초안", encoding="utf-8")
            client = StructuredClient()
            client.permanently_invalid = "subsection-s0-p0"
            with self.assertRaisesRegex(ValueError, "본문 형식·근거 연결 검증 미통과"):
                PlannedPaper(tmp, client).run(research(), output_dir=folder)
            self.assertEqual(sum(s == "subsection-s0-p0" and k == "generate" for s, k, _ in client.events), 2)
            self.assertFalse(any(k == "review" for _, k, _ in client.events))
            self.assertEqual((folder / "draft.md").read_text(encoding="utf-8"), "이전 초안")
            self.assertFalse((folder / "workflow/subsection-s0-p0/approved.json").exists())

    def test_valid_old_compacted_response_is_reused_without_new_call(self):
        packet = build_contexts(assigned_plan(), research(), {})["subsections"]["s1"]["p0"]
        with TemporaryDirectory() as tmp:
            calls = []
            def client(*args):
                calls.append(args)
                return {"parts": {"p0": "기존 검증 본문이다. [근거:F1]"}}
            engine = PlannedPaper(tmp, client)
            expected = engine.call(Path(tmp), "generate", "system" + SOURCE_PROTOCOL, compact_packet(packet), parts_schema(packet))
            actual = generate_bounded(engine, Path(tmp), "generate", "system", packet, parts_schema(packet), {"s1": packet}, True)
            self.assertEqual(actual, expected)
            self.assertEqual(len(calls), 1)

    def test_citation_free_old_cache_is_preserved_but_does_not_replay_as_new_response(self):
        packet = build_contexts(assigned_plan(), research(), {})["subsections"]["s1"]["p0"]
        with TemporaryDirectory() as tmp:
            calls = []
            def client(system, request, schema, path):
                calls.append(schema)
                prop = schema["properties"]["parts"]["properties"]["p0"]
                return {"parts": {"p0": "인용이 빠진 이전 응답" if prop["type"] == "string" else paragraphs("새 본문", ["F1"])}}
            engine = PlannedPaper(tmp, client)
            old = engine.call(Path(tmp), "generate", "system" + SOURCE_PROTOCOL, compact_packet(packet), parts_schema(packet))
            result = generate_bounded(engine, Path(tmp), "generate", "system", packet, parts_schema(packet), {"s1": packet}, True)
            self.assertEqual(render_parts(result, packet)["parts"]["p0"], "새 본문 [근거:F1]")
            self.assertEqual(len(calls), 2)
            self.assertEqual(engine.call(Path(tmp), "generate", "system" + SOURCE_PROTOCOL, compact_packet(packet), parts_schema(packet), cache_only=True), old)
            self.assertTrue((Path(tmp) / "generate-legacy-rejected.json").is_file())

    def test_valid_citations_do_not_erase_source_findings_after_revision_limit(self):
        with TemporaryDirectory() as tmp:
            client = StructuredClient()
            client.reject = "subsection-s0-p0"
            result = PlannedPaper(tmp, client).run(research())
            self.assertEqual(sum(s == "subsection-s0-p0" and k == "review" for s, k, _ in client.events), 3)
            self.assertTrue(any(s == "section-s0" for s, _, _ in client.events))
            self.assertTrue(result["review"]["content_warnings"])
            self.assertFalse(result["review"]["content_approved"])

    def test_split_generations_use_structured_paragraphs_and_preserve_evidence_coverage(self):
        data, _, contexts, _, _ = fixture()
        packet = contexts["subsections"]["s0"]["p0"]
        seen = []
        def client(system, request, schema, path):
            seen.extend(f["id"] for f in request["facts"])
            ids = schema["properties"]["parts"]["properties"]["p0"]["items"]["properties"]["evidence_ids"]["items"]["enum"]
            return {"parts": {"p0": paragraphs("배정된 조건의 관측 기록이다.", ids)}}
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {"PAPER_REQUEST_MAX_BYTES": "24000"}):
            result = generate_bounded(PlannedPaper(tmp, client), Path(tmp), "generate", GROUNDING + WRITER,
                                      packet, parts_schema(packet), {"s0": packet}, True)
            self.assertIn("[근거:", result["parts"]["p0"])
            self.assertEqual(set(seen), {f["id"] for f in data["facts"]})
            self.assertEqual(len(seen), len(set(seen)))
            self.assertTrue((Path(tmp) / "generate-split-manifest.json").is_file())


if __name__ == "__main__":
    unittest.main()
