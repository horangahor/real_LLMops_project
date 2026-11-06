import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from bounded_drafting import (FRAGMENT, call_structured, generate_bounded, scope_fragment_revision)
from draft_prose import PROTOCOL, prose_schema
from drafting_budget import SOURCE_PROTOCOL, compact_packet
from planned_paper import GROUNDING, WRITER, PlannedPaper, parts_schema
from test_draft_revision import revision_fixture


def packet_fixture():
    return {"section_plan": {"evidence_ids": ["F1"]}, "subsection_headings": [],
        "facts": [{"id": "F1", "statement": "현재 문단의 관측", "sources": [{"quote": "원문 전체"}]}],
        "tables": [], "source_body": "현재 문단이다. [근거:F1]",
        "human_guidance": [{"question_id": "Q1", "action": "accept_limited", "instruction": "이 범위만"}],
        "fragment": {"section_id": "arbitrary", "part": "p0", "operation": "revise_paragraph", "paragraph_id": "arbitrary_p3"},
        "revision": {"content_repair_instruction": "기존 지적을 반영한다.", "review": {"checks": [], "issues": [
            {"section_id": "arbitrary", "paragraph_id": "arbitrary_p2", "severity": "warning", "evidence_ids": [],
             "reason": "다른 문단의 지적", "quote": "다른 문단에서만 쓰는 관측이다. [근거:F2]"},
            {"section_id": "arbitrary", "paragraph_id": "arbitrary_p3", "severity": "error", "evidence_ids": ["F1"],
             "reason": "현재 조건을 보완한다.", "quote": "현재 문단이다. [근거:F1]"},
            {"section_id": "arbitrary", "paragraph_id": "none", "severity": "error", "evidence_ids": [],
             "reason": "중복 설명을 줄인다."}]}}}


class FragmentReviewScopeTests(unittest.TestCase):
    def test_neighbor_warning_cannot_enter_current_paragraph_rewrite(self):
        original = packet_fixture()
        before = copy.deepcopy(original)
        scoped = scope_fragment_revision(original)
        issues = scoped["revision"]["review"]["issues"]
        self.assertEqual([r["paragraph_id"] for r in issues], ["arbitrary_p3", "none"])
        self.assertNotIn("다른 문단에서만", json.dumps(scoped, ensure_ascii=False))
        self.assertNotIn("quote", issues[0])
        for field in ("source_body", "facts", "tables", "human_guidance", "section_plan"):
            self.assertEqual(scoped[field], original[field])
        self.assertEqual(original, before)

    def test_missing_content_fragment_receives_global_findings_without_other_paragraphs(self):
        packet = packet_fixture()
        packet["fragment"] = {"operation": "missing_evidence"}
        packet["source_body"] = ""
        scoped = scope_fragment_revision(packet)
        self.assertEqual([r["paragraph_id"] for r in scoped["revision"]["review"]["issues"]], ["none"])

    def test_derived_warning_history_cannot_reintroduce_excluded_sibling_quotes(self):
        packet = packet_fixture()
        packet["revision"]["review"]["content_warnings"] = [copy.deepcopy(packet["revision"]["review"]["issues"][0])]
        packet["revision"]["review"]["checks"] = [{"item_id": "item", "verdict": "met", "evidence_ids": ["F1"],
            "paragraph_quotes": ["다른 문단에서만 쓰는 관측이다. [근거:F2]"]}]
        scoped = scope_fragment_revision(packet)
        self.assertNotIn("content_warnings", scoped["revision"]["review"])
        self.assertNotIn("다른 문단에서만", json.dumps(scoped, ensure_ascii=False))
        self.assertIn("content_warnings", packet["revision"]["review"])
        self.assertEqual(scoped["revision"]["review"]["checks"], [{"item_id": "item", "verdict": "met", "evidence_ids": ["F1"]}])

    def test_wrong_prior_answer_is_saved_locally_but_not_resent_as_repair_prose(self):
        packet = packet_fixture()
        packet["fragment_validation_error"] = {"error": "범위 밖 ID=F2", "response": {"text": "다른 문단의 잘못된 답"}}
        scoped = scope_fragment_revision(packet)
        self.assertEqual(scoped["fragment_validation_error"], {"error": "범위 밖 ID=F2"})
        self.assertIn("response", packet["fragment_validation_error"])

    def test_valid_complete_old_fragment_cache_is_reused_without_new_request(self):
        packet, calls = packet_fixture(), []
        def client(*args):
            calls.append(args)
            return {"parts": {"p0": [{"text": "현재 관측이다.", "evidence_ids": ["F1"]}]}}
        with TemporaryDirectory() as tmp:
            engine = PlannedPaper(tmp, client)
            system = "system" + FRAGMENT + PROTOCOL
            engine.call(Path(tmp), "fragment", system + SOURCE_PROTOCOL, compact_packet(packet), prose_schema(packet))
            result = call_structured(engine, Path(tmp), "fragment", system, packet, prose_schema(packet), fragment=True)
        self.assertEqual(result["parts"]["p0"][0]["evidence_ids"], ["F1"])
        self.assertEqual(len(calls), 1)

    def test_invalid_old_cache_is_kept_but_new_scoped_request_does_not_repeat_its_failure(self):
        packet, calls = packet_fixture(), []
        def client(system, request, schema, path):
            calls.append(copy.deepcopy(request))
            if len(calls) == 1:
                return {"parts": {"p0": [{"text": "다른 문단이다. [근거:F2]", "evidence_ids": ["F1"]}]}}
            self.assertNotIn("다른 문단에서만", json.dumps(request, ensure_ascii=False))
            return {"parts": {"p0": [{"text": "현재 관측만 설명한다.", "evidence_ids": ["F1"]}]}}
        with TemporaryDirectory() as tmp:
            engine = PlannedPaper(tmp, client)
            system = "system" + FRAGMENT + PROTOCOL
            engine.call(Path(tmp), "fragment", system + SOURCE_PROTOCOL, compact_packet(packet), prose_schema(packet))
            cached_path = next((Path(tmp) / "responses").glob("fragment-*.json"))
            raw = cached_path.read_bytes()
            result = call_structured(engine, Path(tmp), "fragment", system, packet, prose_schema(packet), fragment=True)
            self.assertEqual(len(calls), 2)
            self.assertEqual(call_structured(engine, Path(tmp), "fragment", system, packet, prose_schema(packet), fragment=True), result)
            self.assertEqual(len(calls), 2)
            self.assertEqual(cached_path.read_bytes(), raw)
            audit = json.loads((Path(tmp) / "fragment-revision-input-scope.json").read_text(encoding="utf-8"))
            self.assertTrue(audit["source_body_unchanged"])
            self.assertTrue(audit["facts_unchanged"])

    def test_joined_old_paragraphs_still_use_lossless_format_repair_instead_of_regeneration(self):
        packet, calls = packet_fixture(), []
        def client(*args):
            calls.append(args)
            return {"parts": {"p0": [{"text": "첫 문단\n\n둘째 문단", "evidence_ids": ["F1"]}]}}
        with TemporaryDirectory() as tmp:
            engine = PlannedPaper(tmp, client)
            system = "system" + FRAGMENT + PROTOCOL
            original = engine.call(Path(tmp), "fragment", system + SOURCE_PROTOCOL, compact_packet(packet), prose_schema(packet))
            self.assertEqual(call_structured(engine, Path(tmp), "fragment", system, packet, prose_schema(packet), fragment=True), original)
            self.assertEqual(len(calls), 1)

    def test_split_pipeline_scopes_findings_and_preserves_unmodified_paragraphs(self):
        _, _, packet, before, _ = revision_fixture()
        packet["revision"]["review"]["issues"].append({"section_id": "s0", "paragraph_id": "s0_p1", "severity": "warning",
            "evidence_ids": [], "reason": "다른 문단의 참고 지적", "quote": "현재 답으로 복사하면 안 되는 문단 [근거:F0]"})
        original, requests = copy.deepcopy(packet), []
        def client(system, request, schema, path):
            requests.append(request)
            pid = request["fragment"].get("paragraph_id")
            self.assertTrue(all(i.get("paragraph_id") in (None, "none", pid)
                for i in request.get("revision", {}).get("review", {}).get("issues", [])))
            self.assertNotIn("현재 답으로 복사하면", json.dumps(request, ensure_ascii=False))
            return {"parts": {"p0": [{"text": "현재 조각의 조건과 한계를 설명한다.",
                                      "evidence_ids": [f["id"] for f in request["facts"]]}]}}
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {"PAPER_REQUEST_MAX_BYTES": "36000"}):
            result = generate_bounded(PlannedPaper(tmp, client), Path(tmp), "generate", GROUNDING + WRITER,
                                      packet, parts_schema(packet), {"s0": packet}, True)
        self.assertTrue(requests)
        self.assertIn(before.split("\n\n")[0], result["parts"]["p0"])
        self.assertIn(before.split("\n\n")[2], result["parts"]["p0"])
        self.assertEqual(packet, original)


if __name__ == "__main__":
    unittest.main()
