import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from bounded_review import finalize_review, review_bounded
from planned_paper import PlannedPaper, index_paragraphs, review_schema
from review_findings import match_quote, verify_findings
from review_response import candidate_review_system, checked_review, repair_review_selection
from test_hierarchical_drafting import Client
from test_planned_paper import plan, research


def contract_fixture():
    data, value = research(), plan(2)
    data["facts"][0].update(statement="구조체를 안에서 선언하도록 해봤다.", limits="변경 시도 기록이다.",
        sources=[{"page": 50, "element_id": "p50:e352", "origin": "standard_parse", "quote": "안에서 선언과 동시에 만들어지도록 해봤다."}])
    data["facts"][1]["sources"] = [{"page": 51, "element_id": "p51:e1", "quote": "관측값은 12였다."}]
    value["sections"][0]["required_items"][0]["evidence_ids"] = ["F1", "F2"]
    bodies = {"s0": "안에서 선언하도록 변경해 보았다. [근거:F1]\n\n관측값은 12였다. [근거:F2]",
              "s1": "변경 시도를 기록하였다. [근거:F1]"}
    raw = {"checks": [{"item_id": "item0", "verdict": "met", "paragraph_ids": ["s0_p1"], "evidence_ids": ["F1", "F2"]},
                      {"item_id": "item1", "verdict": "met", "paragraph_ids": ["s1_p1"], "evidence_ids": ["F1"]}],
           "reference_checks": [], "issues": []}
    return data, value, bodies, raw


def proof_response(packet, decision="wording", violation="expression"):
    return {"findings": {key: {"decision": decision, "violation_type": violation,
        "draft_quote": "안에서 선언하도록 변경해 보았다.", "evidence_id": "F1",
        "source_quote": "안에서 선언과 동시에 만들어지도록 해봤다.",
        "reason": "두 표현 모두 변경 시도를 보고하며 성공이나 일반적 성과를 추가하지 않았다."}
        for key in packet["findings"]}}


class ReviewContractTests(unittest.TestCase):
    def test_quote_matching_allows_whitespace_layout_only_and_preserves_the_original_span(self):
        original = "앞 문장. main 함수 scope의 선언문은 무조건\n선언이 되어야한다. 뒤 문장."
        self.assertEqual(match_quote("main 함수 scope의 선언문은 무조건 선언이 되어야한다.", original),
                         "main 함수 scope의 선언문은 무조건\n선언이 되어야한다.")
        self.assertEqual(match_quote("조건 A는 12 ms였다.", "조건\tA는  12\u00a0ms였다."), "조건\tA는  12\u00a0ms였다.")
        for quote, text in [("1 2 ms", "12 ms"), ("12 ms", "1 2 ms"), ("12 ms", "12 s"),
                            ("4배 빠르다", "4배 느리다"), ("해결하였다", "해결을 시도했다"),
                            ("1.4%", "14%"), ("512", "5 12"), ("", "본문")]:
            with self.subTest(quote=quote, text=text):
                self.assertIsNone(match_quote(quote, text))

    def test_review_source_quote_with_flattened_line_break_passes_without_extra_correction(self):
        data, value, bodies, raw = contract_fixture()
        data["facts"][0]["sources"][0]["quote"] = "안에서 선언과\n동시에 만들어지도록 해봤다."
        original = copy.deepcopy(data)
        raw["issues"] = [{"section_id": "s0", "severity": "error", "paragraph_id": "s0_p1", "reason": "시도 표현 확인", "evidence_ids": ["F1"]}]
        calls = []
        def client(system, request, schema, path):
            calls.append(request)
            return proof_response(request)
        with TemporaryDirectory() as tmp:
            result = verify_findings(PlannedPaper(tmp, client), Path(tmp), "review", raw, value, data, bodies)
            self.assertEqual(len(calls), 1)
            self.assertEqual(result["issues"][0]["severity"], "warning")
            self.assertIn("\n", result["issues"][0]["adjudication"]["matched_source_quote"])
            self.assertEqual(data, original)

    def test_classifies_selected_paragraph_omission_separately_from_absent_evidence(self):
        _, value, bodies, raw = contract_fixture()
        check = checked_review(raw, value, bodies)["checks"][0]
        self.assertEqual(check["missing_section_evidence_ids"], [])
        self.assertEqual(check["unselected_cited_evidence_ids"], ["F2"])
        self.assertEqual(check["failure_owner"], "reviewer")
        bodies["s0"] = "안에서 선언하도록 변경해 보았다. [근거:F1]"
        check = checked_review(raw, value, bodies)["checks"][0]
        self.assertEqual(check["missing_section_evidence_ids"], ["F2"])
        self.assertEqual(check["failure_owner"], "writer")

    def test_cached_review_repairs_only_selection_preserves_body_and_reuses_correction(self):
        data, value, bodies, raw = contract_fixture()
        original = copy.deepcopy((bodies, raw))
        packet = {"research": data, "plan": value, "draft_paragraphs": index_paragraphs(bodies), "reference_guides": {}}
        calls = []
        def client(system, request, schema, path):
            calls.append(request.get("operation", "review"))
            if request.get("operation") == "repair_review_selection":
                return {"selections": {"item0": {"paragraph_ids": ["s0_p1", "s0_p2"], "evidence_ids": ["F1", "F2"]}}}
            return copy.deepcopy(raw)
        with TemporaryDirectory() as tmp:
            engine = PlannedPaper(tmp, client)
            # Seed a historical report, using the exact legacy request identity.
            schema = review_schema(value, packet["draft_paragraphs"])
            engine.call(Path(tmp), "review", candidate_review_system("system"), packet, schema)
            corrected, report = review_bounded(engine, Path(tmp), "review", "system", packet, schema, value, bodies)
            self.assertTrue(report["approved"])
            self.assertEqual(calls, ["review", "review"])
            self.assertEqual(corrected["checks"][0]["paragraph_ids"], ["s0_p1", "s0_p2"])
            self.assertEqual((bodies, raw), original)
            review_bounded(engine, Path(tmp), "review", "system", packet, schema, value, bodies)
            self.assertEqual(len(calls), 2)

    def test_selection_repair_cannot_remove_existing_paragraphs_add_unknown_ids_or_change_issues(self):
        data, value, bodies, raw = contract_fixture()
        raw["issues"] = [{"section_id": "s0", "severity": "warning", "paragraph_id": "s0_p1", "reason": "유지할 지적", "evidence_ids": ["F1"]}]
        invalid = [{"paragraph_ids": ["s0_p2"], "evidence_ids": ["F1", "F2"]},
                   {"paragraph_ids": ["s0_p1", "other"], "evidence_ids": ["F1", "F2"]},
                   {"paragraph_ids": ["s0_p1", "s0_p2"], "evidence_ids": ["invented"]}]
        for row in invalid:
            with self.subTest(row=row), TemporaryDirectory() as tmp:
                engine = PlannedPaper(tmp, lambda *args: {"selections": {"item0": row}})
                result, report = repair_review_selection(engine, Path(tmp), "review", raw, checked_review(raw, value, bodies), value, data, bodies)
                self.assertFalse(report["approved"])
                self.assertEqual(result["issues"], raw["issues"])
                self.assertEqual(report["checks"][0]["failure_owner"], "reviewer")

    def test_legacy_adjudication_replay_is_available_without_being_in_the_runtime(self):
        data, value, bodies, raw = contract_fixture()
        raw["checks"][0]["paragraph_ids"].append("s0_p2")
        raw["issues"] = [{"section_id": "s0", "severity": "error", "paragraph_id": "s0_p1",
                          "reason": "원문과 일치하지만 실제 변경으로 확대할 여지가 있다", "evidence_ids": ["F1"]}]
        before = copy.deepcopy((bodies, raw))
        with TemporaryDirectory() as tmp:
            engine = PlannedPaper(tmp, lambda system, request, schema, path: proof_response(request))
            result = verify_findings(engine, Path(tmp), "review", raw, value, data, bodies)
            report = checked_review(result, value, bodies)
            self.assertTrue(report["approved"])
            self.assertEqual(result["issues"][0]["severity"], "warning")
            self.assertEqual(result["issues"][0]["adjudication"]["original_issue"], raw["issues"][0])
            self.assertEqual((bodies, raw), before)

    def test_real_claim_expansion_stays_blocking_after_successful_selection_repair(self):
        data, value, bodies, raw = contract_fixture()
        raw["issues"] = [{"section_id": "s0", "severity": "error", "paragraph_id": "s0_p1", "reason": "완료를 새로 단정했다", "evidence_ids": ["F1"]}]
        def client(system, request, schema, path):
            if request.get("operation") == "repair_review_selection":
                return {"selections": {"item0": {"paragraph_ids": ["s0_p1", "s0_p2"], "evidence_ids": ["F1", "F2"]}}}
            response = proof_response(request, "body_error", "scope_expansion")
            for row in response["findings"].values():
                row["reason"] = "원문은 시도만 기록했으나 본문이 해결 완료를 단정했다."
            return response
        with TemporaryDirectory() as tmp:
            _, report = finalize_review(PlannedPaper(tmp, client), Path(tmp), "review", raw, checked_review(raw, value, bodies), value, data, bodies)
            self.assertFalse(report["approved"])
            self.assertEqual(report["checks"][0]["verdict"], "met")
            self.assertEqual(report["issues"][0]["failure_owner"], "writer")

    def test_fabricated_quotes_unknown_evidence_and_expression_only_errors_stay_review_errors(self):
        data, value, bodies, raw = contract_fixture()
        raw["issues"] = [{"section_id": "s0", "severity": "error", "paragraph_id": "s0_p1", "reason": "잘못된 지적", "evidence_ids": ["F1"]}]
        changes = [{"draft_quote": "본문에 없는 성공 주장"}, {"source_quote": "없는 원문"}, {"evidence_id": "unknown"},
                   {"decision": "body_error", "violation_type": "expression"}, {"decision": "uncertain"},
                   {"source_quote": data["facts"][0]["statement"]}]  # source quotes take priority over extracted wording
        for change in changes:
            def client(system, request, schema, path):
                response = proof_response(request)
                response["findings"]["issue0"].update(change)
                return response
            with self.subTest(change=change), TemporaryDirectory() as tmp:
                result = verify_findings(PlannedPaper(tmp, client), Path(tmp), "review", raw, value, data, bodies)
                self.assertEqual(result["issues"][0]["severity"], "error")
                self.assertEqual(result["issues"][0]["failure_owner"], "reviewer")

    def test_blocking_draft_issue_revises_writer_without_findings_adjudication_or_publish(self):
        client = Client()
        def response(system, request, schema, path):
            if request.get("operation") == "verify_review_findings":
                return {"findings": {key: {"decision": "uncertain", "violation_type": "scope_expansion", "draft_quote": "",
                    "evidence_id": "none", "source_quote": "", "reason": "원문으로 차이를 확인할 수 없다."} for key in request["findings"]}}
            return client(system, request, schema, path)
        client.reject = "subsection-s0-p0"
        with TemporaryDirectory() as tmp:
            folder = Path(tmp) / "run"
            folder.mkdir()
            (folder / "draft.md").write_text("기존 초안", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "test correction required"):
                PlannedPaper(tmp, response).run(research(), output_dir=folder)
            self.assertEqual(sum(s == "subsection-s0-p0" and k == "generate" for s, k, _ in client.events), 3)
            self.assertFalse(any(s == "section-s0" for s, _, _ in client.events))
            self.assertEqual((folder / "draft.md").read_text(encoding="utf-8"), "기존 초안")
            self.assertFalse((folder / "workflow/subsection-s0-p0/approved.json").exists())

    def test_workflow_selection_omission_does_not_spend_writer_revision_attempt(self):
        client = Client()
        client.plan["sections"][0]["required_items"][0]["evidence_ids"] = ["F1", "F2"]
        body = "조건을 비교했다. [근거:F1]\n\n관측값은 12였다. [근거:F2]"
        operations = []
        def response(system, request, schema, path):
            if request.get("operation") == "repair_review_selection":
                operations.append("selection")
                return {"selections": {"item0": {"paragraph_ids": ["s0_p1", "s0_p2"], "evidence_ids": ["F1", "F2"]}}}
            value = client(system, request, schema, path)
            if path.parent.parent.name == "subsection-s0-p0":
                if "parts" in schema["properties"]:
                    value["parts"]["p0"] = body
                elif "checks" in schema["properties"]:
                    value["checks"][0]["paragraph_ids"] = ["s0_p1"]
            return value
        with TemporaryDirectory() as tmp:
            result = PlannedPaper(tmp, response).run(research())
            self.assertTrue(result["review"]["approved"])
            self.assertEqual(sum(s == "subsection-s0-p0" and k == "generate" for s, k, _ in client.events), 1)
            self.assertEqual(operations, [])
            approved = json.loads((Path(result["run_dir"]) / "workflow/subsection-s0-p0/approved.json").read_text(encoding="utf-8"))
            self.assertEqual(approved["value"]["sections"]["s0"]["parts"]["p0"], body)

    def test_verification_budget_failure_keeps_review_blocked_without_api_or_writer(self):
        data, value, bodies, raw = contract_fixture()
        raw["issues"] = [{"section_id": "s0", "severity": "error", "paragraph_id": "s0_p1", "reason": "판단 필요", "evidence_ids": ["F1"]}]
        with TemporaryDirectory() as tmp, patch("review_findings.fits_request", return_value=False):
            calls = []
            result = verify_findings(PlannedPaper(tmp, lambda *args: calls.append(args)), Path(tmp), "review", raw, value, data, bodies)
            self.assertEqual(calls, [])
            self.assertEqual(result["issues"][0]["failure_owner"], "reviewer")

    def test_invalid_source_quote_repairs_only_review_proof_once_and_preserves_original_finding(self):
        data, value, bodies, raw = contract_fixture()
        raw["issues"] = [{"section_id": "s0", "severity": "error", "paragraph_id": "s0_p1", "reason": "확대할 여지", "evidence_ids": ["F1"]}]
        calls = []
        def client(system, request, schema, path):
            calls.append(request)
            response = proof_response(request)
            if len(calls) == 1:
                response["findings"]["issue0"]["source_quote"] = "원문에 없는 구절"
            return response
        with TemporaryDirectory() as tmp:
            result = verify_findings(PlannedPaper(tmp, client), Path(tmp), "review", raw, value, data, bodies)
            self.assertEqual(len(calls), 2)
            self.assertIn("validation_error", calls[1]["findings"]["issue0"])
            self.assertEqual(result["issues"][0]["severity"], "warning")
            self.assertEqual(result["issues"][0]["adjudication"]["original_issue"], raw["issues"][0])

    def test_transport_interruption_during_findings_check_reuses_original_review_on_resume(self):
        data, value, bodies, raw = contract_fixture()
        raw["checks"][0]["paragraph_ids"].append("s0_p2")
        raw["issues"] = [{"section_id": "s0", "severity": "error", "paragraph_id": "s0_p1", "reason": "시도 표현 확인", "evidence_ids": ["F1"]}]
        packet = {"research": data, "plan": value, "draft_paragraphs": index_paragraphs(bodies), "reference_guides": {}}
        calls, interrupted = [], False
        def client(system, request, schema, path):
            nonlocal interrupted
            operation = request.get("operation", "review")
            calls.append(operation)
            if operation == "verify_review_findings":
                if not interrupted:
                    interrupted = True
                    raise RuntimeError("findings transport interruption")
                return proof_response(request)
            return copy.deepcopy(raw)
        with TemporaryDirectory() as tmp:
            engine = PlannedPaper(tmp, client)
            schema = review_schema(value, packet["draft_paragraphs"])
            _, report = review_bounded(engine, Path(tmp), "review", "system", packet, schema, value, bodies)
            self.assertFalse(report["approved"])
            self.assertNotIn("verify_review_findings", calls)
            self.assertEqual(calls.count("review"), 1)
            before = len(calls)
            review_bounded(engine, Path(tmp), "review", "system", packet, schema, value, bodies)
            self.assertEqual(len(calls), before)


if __name__ == "__main__":
    unittest.main()
