import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from bounded_drafting import (FRAGMENT, REVISION, cited_ids, compact_fragment_revision,
                              generate_bounded, generation_fragments)
from draft_prose import PROTOCOL
from drafting_budget import compact_packet, request_bytes, request_limit
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
    def test_compact_revision_preserves_sources_conditions_decisions_and_relevant_findings(self):
        source = "현재 문단의 전체 본문이다. [근거:F1]"
        issues = [
            {"paragraph_id": "s0_p2", "reason": "현재 문단의 원래 지적", "quote": source, "evidence_ids": ["F1"]},
            {"paragraph_id": "s0_p1", "reason": "다른 문단의 지적", "quote": "다른 본문", "evidence_ids": ["F1"]},
            {"paragraph_id": "none", "reason": "공통 조건을 유지한다", "evidence_ids": ["F1"]},
            {"paragraph_id": "s0_p2", "reason": "별도 대조 구절을 보존한다", "quote": "중복되지 않은 구절", "evidence_ids": ["F1"]},
        ]
        packet = {"fragment": {"operation": "revise_paragraph", "paragraph_id": "s0_p2"},
            "source_body": source, "facts": [{"id": "F1", "sources": [{"quote": "원문 전체"}],
                "conditions": ["조건 A"], "limits": "관측 범위만 서술"}],
            "tables": [{"id": "t1", "evidence_ids": ["F1"]}],
            "human_guidance": [{"action": "accept_limited", "instruction": "결과로 단정하지 않는다"}],
            "revision": {"review": {"issues": issues, "checks": [{"verdict": "missing"}]}}}
        original = copy.deepcopy(packet)
        result = compact_fragment_revision(packet)
        self.assertEqual(packet, original)
        for key in ("source_body", "facts", "tables", "human_guidance"):
            self.assertEqual(result[key], packet[key])
        rows = result["revision"]["review"]["issues"]
        self.assertEqual([i["reason"] for i in rows], [issues[i]["reason"] for i in (0, 2, 3)])
        self.assertNotIn("quote", rows[0])
        self.assertEqual(rows[2]["quote"], "중복되지 않은 구절")
        self.assertEqual(result["revision"]["review"]["checks"], packet["revision"]["review"]["checks"])
        packet["fragment"] = {"operation": "missing_evidence"}
        packet["source_body"] = ""
        gap = compact_fragment_revision(packet)
        self.assertEqual([i["reason"] for i in gap["revision"]["review"]["issues"]], [issues[2]["reason"]])

    def test_oversized_repeated_revision_quotes_fit_without_splitting_comparison_or_source_text(self):
        _, _, packet, before, _ = revision_fixture()
        middle = before.split("\n\n")[1] + " 원래 문맥을 유지한다." * 300
        previous = before.replace(before.split("\n\n")[1], middle)
        packet["revision"]["previous_sections"]["s0"]["parts"]["p0"] = previous
        packet["tables"] = [{"id": "comparison", "evidence_ids": ["F3", "F4"],
                             "columns": ["조건", "관측"], "rows": [["A", "B"]]}]
        packet["section_plan"]["table_ids"] = ["comparison"]
        packet["revision"]["review"]["issues"] = [
            {"section_id": "s0", "paragraph_id": "s0_p2", "severity": "error",
             "reason": f"조건·한계를 유지해 해당 서술을 수정한다 {i}", "quote": middle, "evidence_ids": ["F3"]}
            for i in range(15)]
        original = copy.deepcopy(packet)
        with patch.dict("os.environ", {"PAPER_REQUEST_MAX_BYTES": "60000"}):
            tasks = generation_fragments(GROUNDING + WRITER + REVISION, packet, {"s0": packet})
            edits = [r for _, _, _, r, schema in tasks if schema and r["fragment"].get("paragraph_id") == "s0_p2"]
            self.assertTrue(edits)
            self.assertTrue(any(r.get("revision", {}).get("scope") for r in edits))
            for _, _, _, request, schema in tasks:
                if schema is not None:
                    self.assertLessEqual(request_bytes(GROUNDING + WRITER + REVISION + FRAGMENT + PROTOCOL,
                        compact_packet(request), schema), int(request_limit() * .75))
            for request in edits:
                self.assertEqual(request["source_body"], middle)
                self.assertEqual(len(request["revision"]["review"]["issues"]), 15)
                self.assertTrue(all("quote" not in i for i in request["revision"]["review"]["issues"]))
                by_id = {f["id"]: f for f in original["facts"]}
                self.assertTrue(all(f == by_id[f["id"]] for f in request["facts"]))
            comparison = next(r for r in edits if r["tables"])
            self.assertTrue({"F3", "F4"} <= {f["id"] for f in comparison["facts"]})
            self.assertEqual(comparison["tables"], original["tables"])
        self.assertEqual(packet, original)

    def test_fitting_revision_also_uses_the_scoped_replacement_contract(self):
        _, _, packet, _, _ = revision_fixture()
        with patch.dict("os.environ", {"PAPER_REQUEST_MAX_BYTES": "50000"}), patch(
                "bounded_drafting.compact_fragment_revision", side_effect=AssertionError("Already-fitting requests must not change")):
            tasks = generation_fragments(GROUNDING + WRITER + REVISION, packet, {"s0": packet})
        self.assertTrue(tasks)
        edits = [request for _, _, _, request, schema in tasks if schema is not None and request["fragment"]["operation"] == "revise_paragraph"]
        self.assertTrue(edits)
        self.assertTrue(all(r["revision"]["scope"]["policy"] == "paragraph-replacement-v1" for r in edits))

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

    def test_missing_evidence_fragment_defers_omissions_after_local_repair_and_replays_from_cache(self):
        _, _, packet, _, _ = revision_fixture()
        seen = []
        def client(system, request, schema, path):
            seen.append(request)
            ids = [f["id"] for f in request["facts"]]
            return {"parts": {"p0": [{"text": "수정한 본문이다.", "evidence_ids": ids[:1]}]}}
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {"PAPER_REQUEST_MAX_BYTES": "50000"}):
            engine, warnings = PlannedPaper(tmp, client), []
            result = generate_bounded(engine, Path(tmp), "generate-1", GROUNDING + WRITER,
                                      packet, parts_schema(packet), {"s0": packet}, True, on_warning=warnings.append)
            self.assertTrue(any("fragment_validation_error" in r for r in seen))
            self.assertTrue(warnings)
            self.assertEqual(warnings[0]["evidence_ids"], ["F10", "F11"])
            self.assertEqual(warnings[0]["repair_attempts"], 1)
            self.assertNotIn("F10", cited_ids(result["parts"]["p0"]))
            manifest = json.loads((Path(tmp) / "generate-1-split-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["content_warnings"], warnings)
            count, replayed = len(seen), []
            self.assertEqual(generate_bounded(engine, Path(tmp), "generate-1", GROUNDING + WRITER,
                packet, parts_schema(packet), {"s0": packet}, True, on_warning=replayed.append), result)
            self.assertEqual(len(seen), count)
            self.assertEqual(replayed, warnings)
            self.assertFalse((Path(tmp) / "approved.json").exists())

    def test_missing_fragment_still_rejects_unknown_empty_and_malformed_citations_after_repair(self):
        _, _, packet, _, _ = revision_fixture()
        for invalid in (["UNKNOWN"], [], None):
            with self.subTest(invalid=invalid), TemporaryDirectory() as tmp, patch.dict(
                    "os.environ", {"PAPER_REQUEST_MAX_BYTES": "50000"}):
                warnings = []
                def client(system, request, schema, path):
                    ids = [f["id"] for f in request["facts"]]
                    if request["fragment"]["operation"] == "missing_evidence":
                        return {"parts": {"p0": [{"text": "잘못된 인용의 본문이다.", "evidence_ids": invalid}]}}
                    return {"parts": {"p0": [{"text": "수정한 본문이다.", "evidence_ids": ids}]}}
                with self.assertRaisesRegex(ValueError, "분할 본문.*원인:"):
                    generate_bounded(PlannedPaper(tmp, client), Path(tmp), "generate-1", GROUNDING + WRITER,
                                     packet, parts_schema(packet), {"s0": packet}, True, on_warning=warnings.append)
                self.assertEqual(warnings, [])
                self.assertFalse((Path(tmp) / "generate-1-split-manifest.json").exists())

    def test_successful_missing_fragment_repair_leaves_no_warning(self):
        _, _, packet, _, _ = revision_fixture()
        repairs = []
        def client(system, request, schema, path):
            ids = [f["id"] for f in request["facts"]]
            if request["fragment"]["operation"] == "missing_evidence" and "fragment_validation_error" not in request:
                ids = ids[:1]
            if "fragment_validation_error" in request:
                repairs.append(request)
            return {"parts": {"p0": [{"text": "근거 범위 내의 보완이다.", "evidence_ids": ids}]}}
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {"PAPER_REQUEST_MAX_BYTES": "50000"}):
            warnings = []
            result = generate_bounded(PlannedPaper(tmp, client), Path(tmp), "generate-1", GROUNDING + WRITER,
                                      packet, parts_schema(packet), {"s0": packet}, True, on_warning=warnings.append)
            self.assertTrue(repairs)
            self.assertEqual(warnings, [])
            self.assertTrue({"F9", "F10", "F11"} <= cited_ids(result["parts"]["p0"]))

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
