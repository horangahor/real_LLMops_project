import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from citation_repair import link_only_gaps, repair_leaf_citations
from paper_context import build_contexts
from planned_paper import PlannedPaper, compose_parts
from review_response import checked_review
from test_hierarchical_drafting import Client, assigned_plan
from test_planned_paper import research


class CitationRepairTests(unittest.TestCase):
    def fixture(self):
        plan = assigned_plan()
        plan["sections"][0]["required_items"][0]["evidence_ids"] = ["F1", "F2"]
        packet = build_contexts(plan, research(), {})["subsections"]["s0"]["p0"]
        local_plan = {**plan, "sections": [packet["section_plan"]], "generation_order": ["s0"]}
        value = {"s0": {"parts": {"p0": "조건 A를 비교했다. 관측값은 12였다. [근거:F1]\n\n한계도 기록했다. [근거:F1]"}}}
        bodies = {"s0": compose_parts(value["s0"], packet)}
        raw = {"checks": [{"item_id": local_plan["sections"][0]["required_items"][0]["id"],
                           "verdict": "met", "paragraph_ids": ["s0_p1"], "evidence_ids": ["F1", "F2"]}],
               "reference_checks": [], "issues": []}
        return value, bodies, {"s0": packet}, checked_review(raw, local_plan, bodies)

    def repair(self, tmp, response, fixture=None):
        value, bodies, packets, report = fixture or self.fixture()
        def client(system, request, schema, path):
            self.assertEqual([f["id"] for f in request["facts"]], ["F2"])
            self.assertEqual(schema["properties"]["links"]["properties"]["F2"]["properties"]["paragraph_id"]["enum"],
                             ["none", "s0_p1"])
            return copy.deepcopy(response)
        return repair_leaf_citations(PlannedPaper(tmp, client), Path(tmp), "repair", "grounding",
                                     value, bodies, packets, report)

    def test_adds_only_selected_missing_id_and_preserves_all_text_and_old_citations(self):
        original = self.fixture()
        before = copy.deepcopy(original)
        with TemporaryDirectory() as tmp:
            result = self.repair(tmp, {"links": {"F2": {"paragraph_id": "s0_p1", "support_quote": "관측값은 12였다."}}}, original)
            self.assertEqual(result["s0"]["parts"]["p0"],
                             "조건 A를 비교했다. 관측값은 12였다. [근거:F1] [근거:F2]\n\n한계도 기록했다. [근거:F1]")
            self.assertEqual(original, before)
            self.assertEqual(json.loads((Path(tmp) / "repair.json").read_text(encoding="utf-8"))["status"], "awaiting_review")

    def test_unknown_ids_wrong_paragraphs_empty_or_fabricated_quotes_and_new_body_are_rejected(self):
        invalid = [{"links": {}}, {"links": {"unknown": {"paragraph_id": "s0_p1", "support_quote": "관측값은 12였다."}}},
                   {"links": {"F2": {"paragraph_id": "s0_p2", "support_quote": "한계도 기록했다."}}},
                   {"links": {"F2": {"paragraph_id": "s0_p1", "support_quote": ""}}},
                   {"links": {"F2": {"paragraph_id": "s0_p1", "support_quote": "본문에 없는 구절"}}},
                   {"links": {"F2": {"paragraph_id": "s0_p1", "support_quote": "F1"}}},
                   {"links": {"F2": {"paragraph_id": "none", "support_quote": "관측값은 12였다."}}},
                   {"links": {"F2": {"paragraph_id": "s0_p1", "support_quote": "관측값은 12였다."}}, "parts": {}}]
        for response in invalid:
            with self.subTest(response=response), TemporaryDirectory() as tmp:
                self.assertIsNone(self.repair(tmp, response))
                self.assertEqual(json.loads((Path(tmp) / "repair.json").read_text(encoding="utf-8"))["status"], "rejected")

    def test_no_matching_content_falls_back_without_attaching_an_id(self):
        with TemporaryDirectory() as tmp:
            self.assertIsNone(self.repair(tmp, {"links": {"F2": {"paragraph_id": "none", "support_quote": ""}}}))
            self.assertEqual(json.loads((Path(tmp) / "repair.json").read_text(encoding="utf-8"))["status"], "no_supported_link")

    def test_substantive_errors_and_reviewer_missing_content_do_not_use_link_only_repair(self):
        _, _, _, original = self.fixture()
        for change in ("source_error", "missing_content", "missing_review_ids"):
            report = copy.deepcopy(original)
            if change == "source_error":
                report["issues"].append({"severity": "error", "reason": "원문과 수치가 다르다"})
            elif change == "missing_content":
                del report["checks"][0]["model_verdict"]
            else:
                report["checks"][0]["missing_review_evidence_ids"] = ["F2"]
            with self.subTest(change=change):
                self.assertEqual(link_only_gaps(report), [])

    def test_over_budget_repairs_use_normal_revision_without_an_api_call(self):
        with TemporaryDirectory() as tmp, patch("citation_repair.fits_request", return_value=False):
            self.assertIsNone(self.repair(tmp, {"unused": True}))
            self.assertEqual(json.loads((Path(tmp) / "repair.json").read_text(encoding="utf-8"))["status"], "skipped_input_budget")

    def workflow_client(self, reject_repaired=False, interrupt=False, no_match=False):
        client = Client()
        client.plan["sections"][0]["required_items"][0]["evidence_ids"] = ["F1", "F2"]
        repaired_seen = False
        interrupted = False
        def response(system, packet, schema, path):
            nonlocal repaired_seen, interrupted
            raw = client(system, packet, schema, path)
            if path.parent.parent.name != "subsection-s0-p0":
                return raw
            if "links" in schema["properties"]:
                if interrupt and not interrupted:
                    interrupted = True
                    raise RuntimeError("citation interruption")
                repaired_seen = True
                return raw if no_match else {"links": {"F2": {"paragraph_id": "s0_p1", "support_quote": "관측값은 12였다."}}}
            if "parts" in schema["properties"]:
                if "revision" in packet:
                    if interrupt and not interrupted:
                        interrupted = True
                        raise RuntimeError("revision interruption")
                    repaired_seen = True
                raw["parts"]["p0"] = "조건 A를 비교했다. 관측값은 12였다. [근거:" + (
                    "F1,F2]" if repaired_seen and not no_match else "F1]")
            elif "checks" in schema["properties"] and reject_repaired and repaired_seen:
                raw["issues"].append({"section_id": "s0", "severity": "error", "paragraph_id": "s0_p1",
                                      "reason": "연결한 근거의 원문과 본문이 다르다", "evidence_ids": ["F2"]})
            return raw
        return client, response

    def test_workflow_revises_writer_directly_without_a_separate_link_agent_and_reuses_on_resume(self):
        with TemporaryDirectory() as tmp:
            client, response = self.workflow_client()
            engine = PlannedPaper(tmp, response)
            result = engine.run(research())
            local = [(s, k) for s, k, _ in client.events if s == "subsection-s0-p0"]
            self.assertEqual(local, [("subsection-s0-p0", k) for k in ("generate", "review", "generate", "review")])
            self.assertTrue(result["review"]["approved"])
            before = len(client.events)
            self.assertEqual(engine.run(research())["draft_markdown"], result["draft_markdown"])
            self.assertEqual(len(client.events), before)

    def test_repaired_citations_never_override_source_review_failure_or_publish(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp) / "run"
            folder.mkdir()
            (folder / "draft.md").write_text("기존 초안", encoding="utf-8")
            client, response = self.workflow_client(reject_repaired=True)
            with self.assertRaisesRegex(ValueError, "원문과 본문이 다르다"):
                PlannedPaper(tmp, response).run(research(), output_dir=folder)
            self.assertEqual(sum(k == "citation_repair" for _, k, _ in client.events), 0)
            self.assertFalse((folder / "workflow/subsection-s0-p0/approved.json").exists())
            self.assertEqual((folder / "draft.md").read_text(encoding="utf-8"), "기존 초안")
            self.assertFalse(any(s == "section-s0" for s, _, _ in client.events))

    def test_interruption_during_writer_revision_resumes_cached_body_and_review(self):
        with TemporaryDirectory() as tmp:
            client, response = self.workflow_client(interrupt=True)
            engine = PlannedPaper(tmp, response)
            with self.assertRaisesRegex(RuntimeError, "revision interruption"):
                engine.run(research())
            before = len(client.events)
            result = engine.run(research())
            self.assertEqual(client.events[before][:2], ("subsection-s0-p0", "generate"))
            self.assertTrue(result["review"]["approved"])

    def test_no_supported_link_does_not_silently_satisfy_the_required_item(self):
        with TemporaryDirectory() as tmp:
            client, response = self.workflow_client(no_match=True)
            with self.assertRaisesRegex(ValueError, "누락 근거=F2"):
                PlannedPaper(tmp, response).run(research())
            self.assertEqual(sum(k == "citation_repair" for _, k, _ in client.events), 0)
            self.assertEqual(sum(k == "generate" and s == "subsection-s0-p0" for s, k, _ in client.events), 3)


if __name__ == "__main__":
    unittest.main()
