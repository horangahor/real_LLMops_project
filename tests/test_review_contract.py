import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from bounded_review import finalize_review, review_bounded
from planned_paper import PlannedPaper, index_paragraphs, review_schema
from review_response import candidate_review_system, checked_review
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


class ReviewContractTests(unittest.TestCase):
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
                raise AssertionError("Retired selection agent must not be called")
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


    def test_real_claim_expansion_stays_blocking_after_successful_selection_repair(self):
        data, value, bodies, raw = contract_fixture()
        raw["issues"] = [{"section_id": "s0", "severity": "error", "paragraph_id": "s0_p1", "reason": "완료를 새로 단정했다", "evidence_ids": ["F1"]}]
        def client(system, request, schema, path):
            raise AssertionError("Binding existing citations must not call another model")
        with TemporaryDirectory() as tmp:
            _, report = finalize_review(PlannedPaper(tmp, client), Path(tmp), "review", raw, checked_review(raw, value, bodies), value, data, bodies)
            self.assertFalse(report["approved"])
            self.assertEqual(report["checks"][0]["verdict"], "met")
            self.assertEqual(report["issues"][0]["failure_owner"], "writer")


    def test_content_issue_revises_writer_then_defers_without_extra_adjudication(self):
        client = Client()
        def response(system, request, schema, path):
            if request.get("operation") == "verify_review_findings":
                raise AssertionError("Retired source-review agent must not be called")
            return client(system, request, schema, path)
        client.reject = "subsection-s0-p0"
        with TemporaryDirectory() as tmp:
            folder = Path(tmp) / "run"
            folder.mkdir()
            (folder / "draft.md").write_text("기존 초안", encoding="utf-8")
            result = PlannedPaper(tmp, response).run(research(), output_dir=folder)
            self.assertEqual(sum(s == "subsection-s0-p0" and k == "generate" for s, k, _ in client.events), 3)
            self.assertTrue(any(s == "section-s0" for s, _, _ in client.events))
            self.assertEqual((folder / "draft.md").read_text(encoding="utf-8"), result["draft_markdown"])
            self.assertTrue((folder / "workflow/subsection-s0-p0/approved.json").exists())
            self.assertEqual(result["review"]["content_warnings"][0]["reason"], "test correction required")

    def test_workflow_selection_omission_does_not_spend_writer_revision_attempt(self):
        client = Client()
        client.plan["sections"][0]["required_items"][0]["evidence_ids"] = ["F1", "F2"]
        body = "조건을 비교했다. [근거:F1]\n\n관측값은 12였다. [근거:F2]"
        operations = []
        def response(system, request, schema, path):
            if request.get("operation") == "repair_review_selection":
                operations.append("selection")
                raise AssertionError("Retired selection agent must not be called")
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


    def test_cached_blocking_review_reuses_original_response_without_extra_model_calls(self):
        data, value, bodies, raw = contract_fixture()
        raw["checks"][0]["paragraph_ids"].append("s0_p2")
        raw["issues"] = [{"section_id": "s0", "severity": "error", "paragraph_id": "s0_p1", "reason": "시도 표현 확인", "evidence_ids": ["F1"]}]
        packet = {"research": data, "plan": value, "draft_paragraphs": index_paragraphs(bodies), "reference_guides": {}}
        calls = []
        def client(system, request, schema, path):
            operation = request.get("operation", "review")
            calls.append(operation)
            if operation == "verify_review_findings":
                raise AssertionError("Retired source-review agent must not be called")
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
