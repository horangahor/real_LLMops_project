import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from bounded_drafting import generate_bounded
from bounded_review import review_bounded, source_audit_tasks
from drafting_budget import (DraftingBudgetError, call_bounded, compact_packet, request_bytes, request_limit)
from paper_context import build_contexts
from paper_plan import normalize_research
from planned_paper import (GROUNDING, WRITER, REVIEWER, PlannedPaper, compose_parts,
                           index_paragraphs, parts_schema, review_schema)
from test_planned_paper import plan


def fixture(count=12):
    facts = [{"id": f"F{i}", "statement": f"조건 {i}의 관측 기록이다.", "limits": "동일 조건 범위만 해당한다.",
              "claim_status": "observed", "source_origin": "research_note", "writing_role": "research_fact",
              "sources": [{"element_id": f"p1:e{i}", "page": 1, "quote": f"SOURCE_{i}:" + "x" * 6000,
                           "origin": "standard_parse"}]} for i in range(count)]
    data = normalize_research({"title": "예산 검증용 모의 연구", "facts": facts})
    value = plan(2)
    for section in value["sections"]:
        section["evidence_ids"] = [f["id"] for f in facts]
        section["required_items"][0]["evidence_ids"] = section["evidence_ids"][:]
    contexts = build_contexts(value, data, {})
    body = "자료의 관측 기록을 설명한다. [근거:" + ",".join(f["id"] for f in facts) + "]"
    bodies = {s["id"]: body for s in value["sections"]}
    packet = {"research": data, "plan": value, "draft_paragraphs": index_paragraphs(bodies),
              "reference_guides": {}, "section_packets": contexts["sections"], "workflow_stage": "paper"}
    return data, value, contexts, bodies, packet


class BudgetTests(unittest.TestCase):
    def test_fact_copies_are_removed_and_every_source_is_preserved_once(self):
        data, value, contexts, bodies, packet = fixture(2)
        data["facts"][1]["sources"] = copy.deepcopy(data["facts"][0]["sources"])
        packet["research"] = data
        original = copy.deepcopy(packet)
        compact = compact_packet(packet)
        self.assertEqual(packet, original)
        self.assertEqual(len(compact["source_elements"]), 1)
        for fact in compact["research"]["facts"]:
            source = compact["source_elements"][fact["sources"][0]["source_ref"]]
            self.assertEqual(source, data["facts"][0]["sources"][0])
        self.assertNotIn("facts", compact["section_packets"]["s0"])
        self.assertNotIn("required_items", compact["section_packets"]["s0"]["section_plan"])
        self.assertEqual(compact_packet(compact), compact)
        self.assertEqual(compact["research"]["facts"][0]["statement"], data["facts"][0]["statement"])

    def test_oversized_request_is_blocked_before_any_model_request(self):
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {"PAPER_REQUEST_MAX_BYTES": "24000"}):
            calls = []
            engine = PlannedPaper(tmp, client=lambda *args: calls.append(args))
            with self.assertRaises(DraftingBudgetError):
                call_bounded(engine, Path(tmp), "large", "system", {"text": "x" * 30000}, {})
            self.assertEqual(calls, [])
            self.assertFalse(json.loads(next((Path(tmp) / "request-sizes").glob("*.json")).read_text())["within_budget"])

    def test_large_source_review_covers_all_citations_once_and_preserves_any_error(self):
        data, value, contexts, bodies, packet = fixture()
        for fact in data["facts"]:
            fact["parameters"] = [{"name": "approved_configuration", "value": "x" * 6000}]
        calls = []
        def client(system, request, schema, path):
            calls.append((system, request, schema))
            self.assertLessEqual(request_bytes(system, request, schema), request_limit() + 300)
            if request.get("operation") == "verify_review_findings":
                from review_test_support import confirmed_findings
                return confirmed_findings(request, schema)
            if "evidence_usage_targets" in request:
                target = request["evidence_usage_targets"][0]
                if "F5" in target["evidence_ids"] and target["section_id"] == "s0":
                    return {"issues": [{"section_id": "s0", "severity": "error", "paragraph_id": target["paragraph_id"],
                                        "reason": "원문과 주장 불일치 시험", "evidence_ids": ["F5"]}]}
                return {"issues": []}
            return {"checks": [{"item_id": item["id"], "verdict": "met", "evidence_ids": item["evidence_ids"],
                "paragraph_ids": [next(k for k, p in request["draft_paragraphs"].items() if p["section_id"] == section["id"])]}
                for section in request["plan"]["sections"] for item in section["required_items"]],
                "reference_checks": [], "issues": []}
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {"PAPER_REQUEST_MAX_BYTES": "24000"}):
            engine = PlannedPaper(tmp, client)
            raw, report = review_bounded(engine, Path(tmp), "review", GROUNDING + REVIEWER,
                packet, review_schema(value, packet["draft_paragraphs"]), value, bodies)
            self.assertFalse(report["approved"])
            self.assertTrue(any(i["reason"] == "원문과 주장 불일치 시험" and i["evidence_ids"] == ["F5"] for i in report["issues"]))
            self.assertEqual(next(i for i in report["issues"] if i["reason"] == "원문과 주장 불일치 시험")["review_stage"], "evidence_usage")
            targets = [(row["paragraph_id"], key) for row in raw["evidence_usage_review"]["batches"] for key in row["target_evidence_ids"]]
            self.assertEqual(len(targets), 24)
            self.assertEqual(len(set(targets)), 24)
            self.assertGreater(len(raw["evidence_usage_review"]["batches"]), 2)
            usage_inputs = [r for _, r, _ in calls if "evidence_usage_targets" in r]
            used_facts = {f["id"]: f for r in usage_inputs for f in r["facts"]}
            self.assertEqual(set(used_facts), {f["id"] for f in data["facts"]})
            self.assertTrue(all("sources" not in f for f in used_facts.values()))
            self.assertTrue(all(len(f["parameters"][0]["value"]) == 6000 for f in used_facts.values()))
            before = len(calls)
            _, resumed = review_bounded(engine, Path(tmp), "review", GROUNDING + REVIEWER,
                packet, review_schema(value, packet["draft_paragraphs"]), value, bodies)
            self.assertFalse(resumed["approved"])
            self.assertEqual(len(calls), before)

    def test_large_generation_splits_into_source_bound_paragraphs_and_resumes_after_failure(self):
        data, value, contexts, bodies, packet = fixture()
        scoped = contexts["subsections"]["s0"]["p0"]
        calls, failed = [], False
        def client(system, request, schema, path):
            nonlocal failed
            calls.append(request)
            self.assertLessEqual(request_bytes(system, request, schema), request_limit() + 300)
            if len(calls) == 2 and not failed:
                failed = True
                raise RuntimeError("source batch transport interrupted")
            ids = [f["id"] for f in request["facts"]]
            return {"parts": {"p0": "배정된 기록의 설명이다. [근거:" + ",".join(ids) + "]"}}
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {"PAPER_REQUEST_MAX_BYTES": "24000"}):
            engine = PlannedPaper(tmp, client)
            with self.assertRaisesRegex(RuntimeError, "transport interrupted"):
                generate_bounded(engine, Path(tmp), "generate", GROUNDING + WRITER,
                    scoped, parts_schema(scoped), {"s0": scoped}, True)
            first_ids = [f["id"] for f in calls[0]["facts"]]
            before = len(calls)
            result = generate_bounded(engine, Path(tmp), "generate", GROUNDING + WRITER,
                scoped, parts_schema(scoped), {"s0": scoped}, True)
            self.assertTrue(result["parts"]["p0"])
            self.assertNotEqual([f["id"] for f in calls[before]["facts"]], first_ids)
            saved = json.loads((Path(tmp) / "generate-split-manifest.json").read_text())
            ids = [key for row in saved["tasks"] for key in row["evidence_ids"]]
            self.assertEqual(set(ids), {f["id"] for f in data["facts"]})
            self.assertEqual(len(ids), len(set(ids)))
            compose_parts(result, scoped)

    def test_indivisible_comparison_is_not_truncated_to_fit(self):
        data, value, contexts, bodies, packet = fixture()
        for fact in data["facts"]:
            fact["parameters"] = [{"name": "approved_configuration", "value": "x" * 6000}]
        packet["research"]["tables"] = [{"id": "comparison", "evidence_ids": [f["id"] for f in data["facts"]],
            "columns": ["A", "B"], "rows": [["all", "all"]]}]
        with patch.dict("os.environ", {"PAPER_REQUEST_MAX_BYTES": "24000"}), self.assertRaisesRegex(DraftingBudgetError, "비교 묶음"):
            source_audit_tasks(packet)

    def test_large_whole_paper_editor_is_split_by_section_and_preserves_part_keys(self):
        data, value, contexts, bodies, packet = fixture()
        sections = {key: {"parts": {"p0": body}} for key, body in bodies.items()}
        request = {"research": data, "plan": value, "sections": sections,
                   "section_packets": contexts["sections"], "reference_guides": {}, "workflow_stage": "paper"}
        calls = []
        def client(system, scoped, schema, path):
            calls.append(scoped)
            self.assertLessEqual(request_bytes(system, scoped, schema), request_limit() + 300)
            return {"parts": {"p0": "이 묶음의 결과를 연결한다. [근거:" + ",".join(f["id"] for f in scoped["facts"]) + "]"}}
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {"PAPER_REQUEST_MAX_BYTES": "24000"}):
            engine = PlannedPaper(tmp, client)
            schema = {"type": "object", "properties": {"sections": {"type": "object", "properties": {
                key: parts_schema(p) for key, p in contexts["sections"].items()}}}}
            result = generate_bounded(engine, Path(tmp), "edit", GROUNDING,
                                      request, schema, contexts["sections"], False)
            self.assertEqual(set(result["sections"]), {"s0", "s1"})
            for sid, section in result["sections"].items():
                self.assertEqual(set(section["parts"]), {"p0"})
                compose_parts(section, contexts["sections"][sid])
            self.assertGreater(len(calls), 2)

    def test_cached_completed_large_call_is_reused_without_new_request(self):
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {"PAPER_REQUEST_MAX_BYTES": "24000"}):
            calls = []
            def client(*args):
                calls.append(args)
                return {"ok": True}
            engine = PlannedPaper(tmp, client)
            packet = {"text": "x" * 30000}
            engine.call(Path(tmp), "old", "system", packet, {})
            self.assertEqual(call_bounded(engine, Path(tmp), "old", "system", packet, {}), {"ok": True})
            self.assertEqual(len(calls), 1)

    def test_section_coverage_batches_are_followed_by_overlapping_whole_paper_coherence(self):
        from bounded_review import SIMPLE_REVIEW
        data, _, _, _, _ = fixture()
        for fact in data["facts"]:
            fact["sources"][0]["quote"] = fact["sources"][0]["quote"][:1000]
        value = plan(4)
        ids = [f["id"] for f in data["facts"]]
        for section in value["sections"]:
            section["evidence_ids"] = ids[:]
            section["required_items"][0]["evidence_ids"] = ids[:]
        contexts = build_contexts(value, data, {})
        bodies = {s["id"]: ("본문의 문장이다. " * 220) + " [근거:" + ",".join(ids) + "]" for s in value["sections"]}
        paragraphs = index_paragraphs(bodies)
        packet = {"research": data, "plan": value, "draft_paragraphs": paragraphs,
                  "reference_guides": {}, "section_packets": contexts["sections"], "workflow_stage": "paper"}
        coherence_windows = []
        def client(system, request, schema, path):
            self.assertLessEqual(request_bytes(system, request, schema), request_limit() + 300)
            if request.get("operation") == "verify_review_findings":
                from review_test_support import confirmed_findings
                return confirmed_findings(request, schema)
            if "evidence_usage_targets" in request:
                return {"issues": []}
            if "outline" in request:
                coherence_windows.append(list(request["draft_paragraphs"]))
                pid = next(iter(request["draft_paragraphs"]))
                return {"issues": [{"section_id": request["draft_paragraphs"][pid]["section_id"],
                    "paragraph_id": pid, "severity": "error", "reason": "장 사이 용어 모순 시험", "evidence_ids": ["F0"]}]}
            return {"checks": [{"item_id": i["id"], "verdict": "met", "evidence_ids": i["evidence_ids"],
                "paragraph_ids": [next(key for key, row in request["draft_paragraphs"].items() if row["section_id"] == s["id"])]}
                for s in request["plan"]["sections"] for i in s["required_items"]], "issues": [], "reference_checks": []}
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {"PAPER_REQUEST_MAX_BYTES": "24000"}):
            raw, result = review_bounded(PlannedPaper(tmp, client), Path(tmp), "review", SIMPLE_REVIEW,
                                         packet, review_schema(value, paragraphs), value, bodies)
        self.assertGreater(len(raw["evidence_usage_review"]["coverage_batches"]), 1)
        self.assertGreater(len(coherence_windows), 1)
        expected_pairs = set(zip(paragraphs, list(paragraphs)[1:]))
        checked_pairs = {pair for window in coherence_windows for pair in zip(window, window[1:])}
        self.assertLessEqual(expected_pairs, checked_pairs)
        self.assertFalse(result["approved"])
        self.assertTrue(any(i["reason"] == "장 사이 용어 모순 시험" for i in result["issues"]))


if __name__ == "__main__":
    unittest.main()
