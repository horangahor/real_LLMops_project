import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from bounded_drafting import REVISION, cited_ids, generate_bounded, generation_fragments
from draft_diagnostics import review_diagnostics, save_review_diagnostics
from planned_paper import GROUNDING, WRITER, PlannedPaper, parts_schema
from review_response import checked_review
from test_drafting_budget import fixture


def revision_fixture():
    research, plan, contexts, _, _ = fixture()
    packet = copy.deepcopy(contexts["subsections"]["s0"]["p0"])
    before = ("이미 검토한 첫 문단이다. [근거:F0,F1,F2]\n\n"
              "추정을 확정 결과처럼 쓴 문단이다. [근거:F3,F4,F5]\n\n"
              "유지해야 하는 마지막 문단이다. [근거:F6,F7,F8]")
    local_plan = {**plan, "sections": [packet["section_plan"]], "generation_order": ["s0"]}
    raw = {"checks": [{"item_id": "item0", "verdict": "met", "paragraph_ids": ["s0_p1", "s0_p2", "s0_p3"],
                       "evidence_ids": [f"F{i}" for i in range(12)]}], "reference_checks": [],
           "issues": [{"section_id": "s0", "severity": "error", "paragraph_id": "s0_p2",
                       "reason": "추정은 구현 결과가 아니다. 한계를 명시한다.", "evidence_ids": ["F3"]}]}
    report = checked_review(raw, local_plan, {"s0": before})
    packet["workflow_stage"] = "subsection"
    packet["revision"] = {"previous_sections": {"s0": {"parts": {"p0": before}}}, "review": report,
        "evidence_link_gaps": [{"item_id": "item0", "evidence_id": f["id"], "statement": f["statement"]}
                               for f in research["facts"][9:]], "content_repair_instruction": "기존 지적을 수정한다."}
    return research, local_plan, packet, before, report


class DraftRevisionTests(unittest.TestCase):
    def test_split_revision_uses_latest_body_and_preserves_unaffected_windows(self):
        _, _, packet, before, _ = revision_fixture()
        original = copy.deepcopy(packet)
        with patch.dict("os.environ", {"PAPER_REQUEST_MAX_BYTES": "36000"}):
            tasks = generation_fragments(GROUNDING + WRITER + REVISION, packet, {"s0": packet})
        passthrough = [request["passthrough"] for _, _, _, request, schema in tasks if schema is None]
        self.assertEqual(passthrough, [before.split("\n\n")[0], before.split("\n\n")[2]])
        requests = [request for _, _, _, request, schema in tasks if schema is not None]
        edits = [r for r in requests if r["fragment"]["operation"] == "revise_paragraph"]
        gaps = [r for r in requests if r["fragment"]["operation"] == "missing_evidence"]
        self.assertTrue(edits)
        self.assertTrue(gaps)
        self.assertTrue(all(r["source_body"] == before.split("\n\n")[1] for r in edits))
        self.assertTrue(all(r["fragment"]["paragraph_id"] == "s0_p2" for r in edits))
        self.assertEqual({f["id"] for r in edits for f in r["facts"]}, {"F3", "F4", "F5"})
        self.assertEqual({f["id"] for r in gaps for f in r["facts"]}, {"F9", "F10", "F11"})
        self.assertTrue(all(not r["source_body"] for r in gaps))
        for request in gaps:
            self.assertEqual(request["revision"]["review"]["checks"][0]["missing_body_evidence_ids"],
                             [f["id"] for f in request["facts"]])
        self.assertEqual(packet, original)

    def test_editors_also_revise_latest_candidate_instead_of_original_children(self):
        _, _, packet, _, _ = revision_fixture()
        packet["workflow_stage"] = "section"
        packet["child_parts"] = {"p0": "오래된 하위 본문이다. [근거:F0]"}
        with patch.dict("os.environ", {"PAPER_REQUEST_MAX_BYTES": "36000"}):
            tasks = generation_fragments(GROUNDING + WRITER + REVISION, packet, {"s0": packet})
        self.assertFalse(any("오래된 하위" in str(request) for _, _, _, request, _ in tasks))

    def test_generation_keeps_existing_content_adds_only_missing_facts_and_resumes_after_interruption(self):
        _, plan, packet, before, _ = revision_fixture()
        seen, interrupted = [], False
        def client(system, request, schema, path):
            nonlocal interrupted
            seen.append(copy.deepcopy(request))
            if len(seen) == 2 and not interrupted:
                interrupted = True
                raise RuntimeError("revision transport interruption")
            ids = [f["id"] for f in request["facts"]]
            if request["fragment"]["operation"] == "missing_evidence":
                text = "누락된 관측 기록을 조건의 범위에서 보완한다."
            else:
                text = "해당 기록은 구현 결과가 아닌 추정이다."
            return {"parts": {"p0": [{"text": text, "evidence_ids": ids}]}}
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {"PAPER_REQUEST_MAX_BYTES": "36000"}):
            engine = PlannedPaper(tmp, client)
            with self.assertRaisesRegex(RuntimeError, "revision transport"):
                generate_bounded(engine, Path(tmp), "generate-1", GROUNDING + WRITER, packet,
                                 parts_schema(packet), {"s0": packet}, True)
            completed = copy.deepcopy(seen[0])
            count = len(seen)
            result = generate_bounded(engine, Path(tmp), "generate-1", GROUNDING + WRITER, packet,
                                      parts_schema(packet), {"s0": packet}, True)
            self.assertNotEqual(seen[count], completed)
            body = result["parts"]["p0"]
            self.assertTrue(body.startswith(before.split("\n\n")[0]))
            self.assertIn(before.split("\n\n")[2], body)
            self.assertNotIn("추정을 확정 결과처럼", body)
            self.assertEqual(cited_ids(body), {f"F{i}" for i in range(12)})
            # Same strict validator, not an exemption for newly repaired content.
            raw = {"checks": [{"item_id": "item0", "verdict": "met", "evidence_ids": [f"F{i}" for i in range(12)],
                               "paragraph_ids": [f"s0_p{i+1}" for i in range(len(body.split('\n\n')))]}],
                   "reference_checks": [], "issues": []}
            self.assertTrue(checked_review(raw, plan, {"s0": body})["approved"])
            manifest = json.loads((Path(tmp) / "generate-1-split-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(sum(t.get("preserved_connecting_text", False) for t in manifest["tasks"]), 2)

    def test_missing_evidence_fragment_that_omits_requested_ids_is_rejected_locally(self):
        _, _, packet, _, _ = revision_fixture()
        seen = []
        def client(system, request, schema, path):
            seen.append(request)
            ids = [f["id"] for f in request["facts"]]
            return {"parts": {"p0": [{"text": "수정한 본문이다.", "evidence_ids": ids[:1]}]}}
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {"PAPER_REQUEST_MAX_BYTES": "50000"}):
            with self.assertRaisesRegex(ValueError, "분할 본문"):
                generate_bounded(PlannedPaper(tmp, client), Path(tmp), "generate-1", GROUNDING + WRITER,
                                 packet, parts_schema(packet), {"s0": packet}, True)
            self.assertTrue(any("fragment_validation_error" in r for r in seen))
            self.assertFalse((Path(tmp) / "approved.json").exists())

    def test_diagnostics_distinguish_missing_citations_from_unselected_cited_paragraphs_and_user_approval(self):
        data, plan, packet, before, report = revision_fixture()
        data["facts"][9].update(support="user_accepted", source_origin="user_addendum", provisional_decision_id="D")
        # F8 exists in the body but was omitted from the reviewer's paragraph selection.
        report["checks"][0]["paragraph_ids"] = ["s0_p1", "s0_p2"]
        report["checks"][0]["missing_body_evidence_ids"].insert(0, "F8")
        details = review_diagnostics("subsection-s0-p0", plan, data, {"s0": before}, report)
        facts = {f["id"]: f for f in details["items"][0]["evidence"]}
        self.assertTrue(facts["F8"]["cited_anywhere_in_section"])
        self.assertFalse(facts["F8"]["cited_in_selected_paragraphs"])
        self.assertTrue(facts["F9"]["user_accepted"])
        self.assertFalse(facts["F10"]["user_accepted"])
        self.assertEqual(facts["F10"]["sources"][0]["element_id"], "p1:e10")
        with TemporaryDirectory() as tmp:
            path = save_review_diagnostics(tmp, "review-1", "subsection-s0-p0", plan, data, {"s0": before}, report)
            self.assertTrue(path.is_file())
            md = (Path(tmp) / "failure-details.md").read_text(encoding="utf-8")
            self.assertIn("F9", md)
            self.assertIn("p1:e10", md)
            self.assertIn("추정은 구현 결과가 아니다", md)


if __name__ == "__main__":
    unittest.main()
