import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from bounded_review import COVERAGE_SYSTEM, _coverage_packet, approved_review_packet, coverage_tasks, review_bounded
from drafting_budget import fits_request
from planned_paper import PlannedPaper, index_paragraphs, review_schema
from review_response import review_with_repair
from test_drafting_budget import fixture
from test_planned_paper import plan, research


class ContentCoverageTests(unittest.TestCase):
    def test_coverage_format_repair_uses_body_and_criteria_without_requesting_fact_review(self):
        value = plan(2)
        bodies = {sid: "조건과 결과를 설명한다. [근거:F1]" for sid in ("s0", "s1")}
        packet = _coverage_packet({"research": research(), "plan": value,
            "draft_paragraphs": index_paragraphs(bodies), "reference_guides": {}}, {})
        calls = []
        def client(system, request, schema, path):
            calls.append((system, request))
            self.assertNotIn("facts", request["research"])
            if len(calls) == 1:
                return {"checks": [], "reference_checks": [], "issues": []}
            return {"checks": [{"item_id": f"item{i}", "verdict": "met", "paragraph_ids": [f"s{i}_p1"],
                                "evidence_ids": ["F1"]} for i in range(2)], "reference_checks": [], "issues": []}
        with TemporaryDirectory() as tmp:
            _, report = review_with_repair(PlannedPaper(tmp, client), Path(tmp), "coverage", COVERAGE_SYSTEM,
                packet, review_schema(value, packet["draft_paragraphs"]), value, bodies)
        self.assertTrue(report["approved"])
        self.assertEqual(len(calls), 2)
        self.assertNotIn("원래 연구 근거와 draft_paragraphs를 다시 대조한다", calls[1][0])
        self.assertIn("근거 사용 대조는 선행 단계에서 수행했다", calls[1][0])

    def test_hundreds_of_facts_do_not_expand_coverage_input_or_drop_any_body(self):
        data, value = research(), plan(2)
        facts = [{"id": f"E{i:05d}", "statement": "LONG_APPROVED_STATEMENT " * 90,
                  "limits": "APPROVED_LIMITATION " * 50, "sources": []} for i in range(259)]
        data["facts"] = facts
        ids = [f["id"] for f in facts]
        value["sections"] = [value["sections"][0]]
        value["generation_order"] = ["s0"]
        value["sections"][0]["evidence_ids"] = ids[:]
        value["sections"][0]["required_items"][0]["evidence_ids"] = ids[:]
        value["audit_history"] = "PLAN_AUDIT_NOT_FOR_REVIEW " * 5000
        bodies = {"s0": "\n\n".join(f"결과 {i}와 비교 조건을 설명한다. [근거:{ids[i]}]" for i in range(37))}
        packet = approved_review_packet({"research": data, "plan": value,
            "draft_paragraphs": index_paragraphs(bodies), "reference_guides": {}})
        original = copy.deepcopy(packet)
        summary = {"checked_paragraph_ids": list(packet["draft_paragraphs"]), "checked_evidence_ids": ids[:37],
                   "issue_count": 1, "blocking_paragraph_ids": ["s0_p1"]}
        tasks = coverage_tasks(packet, summary)
        self.assertEqual(len(tasks), 1)
        scoped = tasks[0][1]
        self.assertNotIn("facts", scoped["research"])
        self.assertNotIn("tables", scoped["research"])
        self.assertNotIn("LONG_APPROVED_STATEMENT", json.dumps(scoped))
        self.assertNotIn("PLAN_AUDIT_NOT_FOR_REVIEW", json.dumps(scoped))
        self.assertEqual(scoped["draft_paragraphs"], packet["draft_paragraphs"])
        self.assertEqual(scoped["evidence_usage_summary"]["blocking_paragraph_ids"], ["s0_p1"])
        self.assertTrue(fits_request(COVERAGE_SYSTEM, scoped, review_schema(scoped["plan"], scoped["draft_paragraphs"])))
        self.assertEqual(packet, original)

    def test_related_limited_acceptance_and_unbound_exclusions_are_preserved(self):
        data, value = research(), plan(2)
        value["sections"][0].update(evidence_ids=["F1"], reference_ids=["g1"])
        value["sections"][1].update(evidence_ids=["F2"], reference_ids=["g2"])
        data["facts"][0]["provisional_decision_id"] = "D1"
        data["facts"][1]["provisional_decision_id"] = "D2"
        data["human_guidance"] = [
            {"id": "D1", "question_id": "Q1", "action": "accept_limited", "provided_text": "관찰 범위만 사용한다.", "writing_instruction": "추가 통계를 요구하지 않는다."},
            {"id": "D2", "question_id": "Q2", "action": "accept_limited", "provided_text": "다른 소절의 범위"},
            {"id": "D3", "question_id": "Q3", "action": "exclude", "writing_instruction": "제외한 내용을 요구하지 않는다."}]
        data["requirement_coverage"] = {
            "Q1": {"status": "accepted_limited", "missing_fields": ["통계"], "evidence_ids": ["F1"], "decision_id": "D1"},
            "Q2": {"status": "accepted_limited", "evidence_ids": ["F2"], "decision_id": "D2"},
            "Q3": {"status": "excluded", "evidence_ids": [], "decision_id": "D3"},
            "OTHER": {"status": "sufficient", "evidence_ids": ["F2"]}}
        data["requirement_applicability"] = {key: {"status": "applicable"} for key in data["requirement_coverage"]}
        packet = {"research": data, "plan": value, "draft_paragraphs": index_paragraphs({"s0": "관찰 범위다. [근거:F1]", "s1": "다른 범위다. [근거:F2]"}),
                  "reference_guides": {"g1": {"id": "g1", "criteria": []}, "g2": {"id": "g2", "criteria": []}}}
        scoped = _coverage_packet(packet, {}, [value["sections"][0]])
        self.assertEqual(scoped["research"]["human_guidance"], [data["human_guidance"][0], data["human_guidance"][2]])
        self.assertEqual(set(scoped["research"]["requirement_coverage"]), {"Q1", "Q3"})
        self.assertEqual(scoped["research"]["requirement_coverage"]["Q1"]["missing_fields"], ["통계"])
        self.assertEqual(set(scoped["reference_guides"]), {"g1"})

    def test_prior_usage_error_remains_blocking_even_when_coverage_reports_met(self):
        _, value, _, bodies, packet = fixture()
        for fact in packet["research"]["facts"]:
            fact["parameters"] = [{"name": "approved", "value": "x" * 6000}]
        seen = []
        def client(system, request, schema, path):
            if "evidence_usage_targets" in request:
                target = request["evidence_usage_targets"][0]
                return {"issues": [{"section_id": target["section_id"], "paragraph_id": target["paragraph_id"],
                    "severity": "error", "reason": "조건을 확대해 사용했다.", "evidence_ids": ["F5"]}]} if target["section_id"] == "s0" and "F5" in target["evidence_ids"] else {"issues": []}
            seen.append(request)
            self.assertEqual(request["coverage_policy"], "content-coverage-v2")
            self.assertNotIn("facts", request["research"])
            self.assertTrue(request["evidence_usage_summary"]["prior_findings_preserved"])
            return {"checks": [{"item_id": item["id"], "verdict": "met", "evidence_ids": item["evidence_ids"],
                "paragraph_ids": [pid for pid, row in request["draft_paragraphs"].items() if row["section_id"] == s["id"]]}
                for s in request["plan"]["sections"] for item in s["required_items"]], "reference_checks": [], "issues": []}
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {"PAPER_REQUEST_MAX_BYTES": "24000"}):
            _, report = review_bounded(PlannedPaper(tmp, client), Path(tmp), "review", "review", packet, review_schema(value, packet["draft_paragraphs"]), value, bodies)
            self.assertFalse(report["approved"])
            self.assertTrue(any(i["reason"] == "조건을 확대해 사용했다." for i in report["issues"]))
            saved = json.loads((Path(tmp) / "review-evidence-usage.json").read_text(encoding="utf-8"))
            self.assertTrue(saved["issues"])
        self.assertEqual(len(seen), 1)


if __name__ == "__main__":
    unittest.main()
