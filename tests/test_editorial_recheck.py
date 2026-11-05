import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from drafting_budget import DraftingBudgetError, compact_packet, request_bytes, request_limit
from editorial_recheck import POLICY
from editorial_review import _review_editorial_legacy, review_editorial
from planned_paper import PlannedPaper, index_paragraphs
from test_planned_paper import plan


def finding(pid="s0_p1", reason="연결을 보완한다.", quote="이전 본문이다.", section="s0", category="flow", severity="error"):
    return {"section_id": section, "paragraph_id": pid, "category": category,
            "severity": severity, "reason": reason, "quote": quote}


class EditorialRecheckTests(unittest.TestCase):
    def test_empty_pending_list_does_not_request_a_new_editorial_review(self):
        def client(*args):
            raise AssertionError("There are no existing findings to recheck")
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {"PAPER_REQUEST_MAX_BYTES": "4000"}):
            _, report = review_editorial(PlannedPaper(tmp, client), Path(tmp), "review", "section", plan(2),
                                         {"s0": "현재 본문이다. [근거:F1]"}, {}, [])
            self.assertTrue(report["approved"])

    def test_duplicate_prior_quotes_are_pooled_once_and_original_history_is_untouched(self):
        pending = [finding(reason="첫 지적"), finding(reason="둘째 지적", severity="warning")]
        original = copy.deepcopy(pending)
        bodies = {"s0": "현재 연결 문장이다. [근거:F1]"}
        calls = []
        def client(system, packet, schema, path):
            calls.append(packet)
            self.assertEqual(len(packet["previous_paragraphs"]), 1)
            self.assertEqual(len({i["quote_ref"] for i in packet["previous_findings"]}), 1)
            self.assertTrue(all("quote" not in i for i in packet["previous_findings"]))
            self.assertEqual(next(iter(packet["previous_paragraphs"].values()))["text"], pending[0]["quote"])
            return {"issues": [{k: pending[0][k] for k in ("section_id", "paragraph_id", "category", "severity", "reason")}]}
        with TemporaryDirectory() as tmp:
            _, report = review_editorial(PlannedPaper(tmp, client), Path(tmp), "review", "section", plan(2), bodies, {}, pending)
            audit = json.loads((Path(tmp) / f"review-{POLICY}-input.json").read_bytes())
        self.assertFalse(report["approved"])
        self.assertEqual(pending, original)
        self.assertEqual(audit["original_findings"], original)
        self.assertEqual(audit["coverage"]["findings"], 2)
        self.assertEqual(len(calls), 1)

    def test_body_windows_and_finding_groups_cover_every_finding_paragraph_and_neighbor_pair(self):
        bodies = {sid: "\n\n".join((f"문단 {i} " + "설명 " * 160 + "[근거:F1]") for i in range(8)) for sid in ("s0", "s1")}
        paragraphs = index_paragraphs(bodies)
        pending = [finding(pid, f"기존 지적 {pid}", row["text"], row["section_id"]) for pid, row in paragraphs.items()]
        calls = []
        def client(system, packet, schema, path):
            calls.append(copy.deepcopy(packet))
            sids = {p["section_id"] for p in packet["draft_paragraphs"].values()}
            self.assertTrue(all(i["section_id"] in sids for i in packet["previous_findings"]))
            self.assertLessEqual(request_bytes(system, compact_packet(packet), schema), int(request_limit() * .75))
            return {"issues": []}
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {"PAPER_REQUEST_MAX_BYTES": "16000"}):
            _, report = review_editorial(PlannedPaper(tmp, client), Path(tmp), "review", "paper", plan(2), bodies, {}, pending)
        self.assertTrue(report["approved"])
        self.assertGreater(len(calls), 1)
        self.assertEqual({pid for p in calls for pid in p["draft_paragraphs"]}, set(paragraphs))
        self.assertEqual({i["finding_id"] for p in calls for i in p["previous_findings"]}, {f"finding-{i}" for i in range(len(pending))})
        pairs = {pair for p in calls for pair in zip(p["draft_paragraphs"], list(p["draft_paragraphs"])[1:])}
        self.assertTrue(set(zip(paragraphs, list(paragraphs)[1:])) <= pairs)

    def test_renumbered_or_deleted_old_paragraph_id_does_not_drop_the_finding(self):
        pending = [finding("s0_p999", quote="통합 이전의 문단이다.")]
        calls = []
        def client(system, packet, schema, path):
            calls.append(packet)
            self.assertEqual(packet["previous_findings"][0]["paragraph_id"], "s0_p999")
            self.assertEqual(set(packet["draft_paragraphs"]), {"s0_p1"})
            return {"issues": []}
        with TemporaryDirectory() as tmp:
            review_editorial(PlannedPaper(tmp, client), Path(tmp), "review", "section", plan(2),
                             {"s0": "통합 후 현재 문단이다. [근거:F1]"}, {}, pending)
        self.assertEqual(len(calls), 1)

    def large_history(self):
        return [finding(reason=f"기존 지적 {i}", quote=f"이전 문단 {i}: " + "a" * 6000,
                        category="flow" if i < 30 else "style") for i in range(60)]

    def test_interrupted_group_reuses_completed_cached_response_on_resume(self):
        pending = self.large_history()
        bodies = {"s0": "현재 본문이다. [근거:F1]"}
        calls, interrupted = [], []
        def client(system, packet, schema, path):
            calls.append(copy.deepcopy(packet))
            if len(calls) == 2 and not interrupted:
                interrupted.append(True)
                raise RuntimeError("test recheck group interruption")
            return {"issues": []}
        with TemporaryDirectory() as tmp:
            engine = PlannedPaper(tmp, client)
            with self.assertRaisesRegex(RuntimeError, "group interruption"):
                review_editorial(engine, Path(tmp), "review", "section", plan(2), bodies, {}, pending)
            completed_ids = [i["finding_id"] for i in calls[0]["previous_findings"]]
            before = len(calls)
            _, report = review_editorial(engine, Path(tmp), "review", "section", plan(2), bodies, {}, pending)
            self.assertTrue(report["approved"])
            self.assertTrue(all([i["finding_id"] for i in p["previous_findings"]] != completed_ids for p in calls[before:]))
            count = len(calls)
            review_editorial(engine, Path(tmp), "review", "section", plan(2), bodies, {}, pending)
            self.assertEqual(len(calls), count)

    def test_recheck_rejects_a_category_from_a_different_pending_group(self):
        pending = self.large_history()
        calls = []
        def client(system, packet, schema, path):
            calls.append(copy.deepcopy(packet))
            if len(calls) == 1:
                self.assertEqual({i["category"] for i in packet["previous_findings"]}, {"flow"})
                return {"issues": [{"section_id": "s0", "paragraph_id": "s0_p1", "category": "style",
                                    "severity": "error", "reason": "다른 묶음의 문제 유형이다."}]}
            return {"issues": []}
        with TemporaryDirectory() as tmp:
            review_editorial(PlannedPaper(tmp, client), Path(tmp), "review", "section", plan(2),
                             {"s0": "현재 본문이다. [근거:F1]"}, {}, pending)
        self.assertIn("invalid_review", calls[1])
        self.assertEqual(calls[0]["previous_findings"], calls[1]["previous_findings"])

    def test_completed_old_recheck_response_is_reused_without_new_api_call(self):
        pending = [finding()]
        bodies = {"s0": "현재 문단이다. [근거:F1]"}
        calls = []
        def client(system, packet, schema, path):
            calls.append(packet)
            self.assertNotIn("recheck_policy", packet)
            return {"issues": []}
        with TemporaryDirectory() as tmp:
            engine = PlannedPaper(tmp, client)
            _review_editorial_legacy(engine, Path(tmp), "review", "section", plan(2), bodies, {}, pending)
            review_editorial(engine, Path(tmp), "review", "section", plan(2), bodies, {}, pending)
        self.assertEqual(len(calls), 1)

    def test_real_metadata_overflow_is_reported_as_combined_input_and_preserves_history(self):
        pending = [finding(quote="x" * 200000)]
        with TemporaryDirectory() as tmp:
            def client(*args):
                raise AssertionError("Over-budget input must not call the API")
            with self.assertRaisesRegex(DraftingBudgetError, "문단.*이전 지적"):
                review_editorial(PlannedPaper(tmp, client), Path(tmp), "review", "section", plan(2),
                                 {"s0": "작은 문단이다. [근거:F1]"}, {}, pending)
            detail = json.loads((Path(tmp) / f"review-{POLICY}-budget-failure.json").read_bytes())
            self.assertLess(detail["paragraph_bytes"], 1000)
            self.assertGreater(detail["history_bytes"], 180000)
            audit = json.loads((Path(tmp) / f"review-{POLICY}-input.json").read_bytes())
            self.assertEqual(audit["original_findings"], pending)


if __name__ == "__main__":
    unittest.main()
