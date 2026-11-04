import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from paper_plan import prepare_planning_research
from planned_paper import PlannedPaper, request_json
from test_planned_paper import FakeClient, plan, research


class PlanningRequestTests(unittest.TestCase):
    def test_projection_preserves_claims_restrictions_tables_and_current_user_decisions(self):
        data = research()
        fact = data["facts"][0]
        fact.update(conditions=["동일 입력"], measurements=[{"value": 12, "unit": "ms"}],
                    parameters=[{"name": "batch", "value": 8}], observations=["실패도 관측"],
                    support="user_accepted", writing_role="context_only", claim_status="planned",
                    source_origin="user_addendum", evidence_limitations=["원인 미분리"],
                    requirement_ids=["Q"], support_note="추출 판정 이력", supplemental_reason="추출 경로",
                    attribution_preserved=True, numeric_issues=["미확인"], provisional_decision_id="D")
        data["tables"] = [{"id": "T", "evidence_ids": ["F1", "F2"], "rows": [[12, 15]]}]
        data["evidence_requirements"] = {"requirements": [{"id": "Q", "question": "조건은?", "expected_fields": ["조건"]}],
                                          "reference_guides": {"old": "중복 지침"}, "run_dir": "archive"}
        data["requirement_coverage"] = {"Q": {"status": "accepted_limited", "missing_fields": ["정확도"],
                                             "evidence_ids": ["F1"], "decision_id": "D",
                                             "reason": "검토 이력", "original_assessment": {"status": "missing"}}}
        data["requirement_applicability"] = {"Q": {"status": "applicable", "reason": "연구에 해당",
                                                   "sources": [{"quote": "원문 이력"}], "support_element_ids": ["p1:e1"]}}
        data["human_guidance"] = [{"question_id": "Q", "action": "recheck", "instruction": "이전 지시"},
                                  {"question_id": "Q", "action": "accept_limited", "id": "D",
                                   "provided_text": "새 사용자 설명", "instruction": "이 범위만",
                                   "writing_instruction": "실측으로 쓰지 않음", "acceptance_method": "explicit_button",
                                   "question": {"id": "Q"}, "original_assessment": {"status": "missing"}}]
        original = copy.deepcopy(data)
        selected = prepare_planning_research(data)
        self.assertEqual(data, original)
        self.assertEqual(len(selected["facts"]), len(data["facts"]))
        for key, value in fact.items():
            if key not in ("support_note", "supplemental_reason"):
                self.assertEqual(selected["facts"][0][key], value, key)
        self.assertEqual(selected["tables"], data["tables"])
        self.assertEqual(selected["evidence_requirements"]["requirements"], data["evidence_requirements"]["requirements"])
        self.assertEqual(selected["requirement_coverage"]["Q"]["status"], "accepted_limited")
        self.assertEqual(selected["requirement_coverage"]["Q"]["missing_fields"], ["정확도"])
        self.assertEqual(selected["requirement_applicability"]["Q"]["reason"], "연구에 해당")
        self.assertEqual(selected["human_guidance"], [{k: v for k, v in data["human_guidance"][-1].items()
                                                      if k not in ("question", "original_assessment")}])
        self.assertLess(len(json.dumps(selected)), len(json.dumps(data)))

    def test_large_planning_registry_retains_source_identity_and_user_attribution(self):
        data = research()
        data["facts"] = [dict(copy.deepcopy(data["facts"][0]), id=f"F{i}",
                              sources=[{"element_id": f"p1:e{i}", "page": 1,
                                        "origin": "user_addendum", "quote": "원문" * 100}]) for i in range(41)]
        selected = prepare_planning_research(data)
        self.assertEqual([f["id"] for f in selected["facts"]], [f["id"] for f in data["facts"]])
        for before, after in zip(data["facts"], selected["facts"]):
            self.assertEqual(after["statement"], before["statement"])
            self.assertEqual(after["sources"], [{k: v for k, v in before["sources"][0].items() if k != "quote"}])
        self.assertIn("quote", data["facts"][0]["sources"][0])

    def test_question_text_is_kept_when_not_already_in_question_bank(self):
        data = research()
        data["human_guidance"] = [{"question_id": "Q", "question": "어떤 조건을 제외할까?",
                                   "action": "exclude", "instruction": "해당 조건 제외"}]
        self.assertEqual(prepare_planning_research(data)["human_guidance"], data["human_guidance"])

    def test_writer_changes_reuse_plan_but_planning_instruction_changes_do_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = FakeClient(plan())
            engine = PlannedPaper(tmp, fake)
            first = engine.run(research(), plan_only=True)
            with patch("planned_paper.CONTEXT_VERSION", "changed-context"):
                second = engine.run(research(), plan_only=True)
            self.assertNotEqual(first["run_dir"], second["run_dir"])
            self.assertEqual(len(fake.calls), 1)
            self.assertEqual(first["plan"], second["plan"])
            self.assertTrue(list((Path(second["run_dir"]) / "responses").glob("plan-*.reuse.json")))
            with patch("planned_paper.PLANNER", "새 배정 지시"):
                engine.run(research(), plan_only=True)
            self.assertEqual(len(fake.calls), 2)
            engine.run(research("다른 연구"), plan_only=True)
            self.assertEqual(len(fake.calls), 3)

    def test_changed_user_decision_requires_a_new_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = FakeClient(plan())
            engine = PlannedPaper(tmp, fake)
            data = research()
            data["human_guidance"] = [{"question_id": "Q", "action": "exclude", "instruction": "제외"}]
            engine.run(data, plan_only=True)
            data["human_guidance"].append({"question_id": "Q", "action": "accept_limited", "instruction": "설명만 반영"})
            engine.run(data, plan_only=True)
            self.assertEqual(len(fake.calls), 2)

    @staticmethod
    def response(content='{"ok":true}', status=200):
        return Mock(status_code=status, json=lambda: {"choices": [{"finish_reason": "stop", "message": {"content": content}}],
                                                     "usage": {"prompt_tokens_details": {"cached_tokens": 123}}})

    def test_timeout_retries_same_request_once_and_preserves_failure_and_usage(self):
        with tempfile.TemporaryDirectory() as tmp, patch("planned_paper.time.sleep") as sleep:
            path = Path(tmp) / "plan.native.json"
            with patch("planned_paper.requests.post", side_effect=[requests.ReadTimeout(), self.response()]) as post:
                result = request_json("system", {"fact": "test"}, {}, path, "test-key", transport_retries=1)
            self.assertEqual(result, {"ok": True})
            self.assertEqual(post.call_count, 2)
            self.assertEqual(post.call_args_list[0].kwargs["json"], post.call_args_list[1].kwargs["json"])
            sleep.assert_called_once_with(1)
            failures = list(Path(tmp).glob("*-transport-error-*.json"))
            self.assertEqual(len(failures), 1)
            self.assertEqual(json.loads(failures[0].read_text())["request_error"], "ReadTimeout")
            audit = json.loads(path.with_suffix(".request.json").read_text())
            self.assertEqual(len(audit["attempts"]), 2)
            self.assertEqual(audit["attempts"][-1]["usage"]["prompt_tokens_details"]["cached_tokens"], 123)
            self.assertNotIn("test-key", json.dumps(audit))

    def test_exhausted_timeout_stops_with_specific_error_and_without_success_cache(self):
        with tempfile.TemporaryDirectory() as tmp, patch("planned_paper.time.sleep"):
            engine = PlannedPaper(tmp, api_key="test-key")
            with patch("planned_paper.requests.post", side_effect=requests.ReadTimeout()) as post:
                with self.assertRaisesRegex(RuntimeError, "ReadTimeout.*전송 시도 2회"):
                    engine.call(Path(tmp), "plan", "system", {}, {}, transport_retries=1)
            self.assertEqual(post.call_count, 2)
            for path in Path(tmp).rglob("*.json"):
                self.assertNotIn("value", json.loads(path.read_text()), path.name)

    def test_bad_request_is_not_retried_as_transport_failure(self):
        with tempfile.TemporaryDirectory() as tmp, patch("planned_paper.time.sleep") as sleep:
            with patch("planned_paper.requests.post", return_value=self.response(status=400)) as post:
                with self.assertRaisesRegex(RuntimeError, "HTTP 400"):
                    request_json("system", {}, {}, Path(tmp) / "plan.native.json", "test-key", transport_retries=1)
            self.assertEqual(post.call_count, 1)
            sleep.assert_not_called()

    def test_other_calls_do_not_gain_transport_retries_by_default(self):
        with tempfile.TemporaryDirectory() as tmp, patch("planned_paper.time.sleep") as sleep:
            with patch("planned_paper.requests.post", side_effect=requests.ReadTimeout()) as post:
                with self.assertRaisesRegex(RuntimeError, "전송 시도 1회"):
                    request_json("system", {}, {}, Path(tmp) / "audit.native.json", "test-key")
            self.assertEqual(post.call_count, 1)
            sleep.assert_not_called()

    def test_transport_recovery_and_json_repair_preserve_both_failed_attempts(self):
        with tempfile.TemporaryDirectory() as tmp, patch("planned_paper.time.sleep"):
            path = Path(tmp) / "plan.native.json"
            with patch("planned_paper.requests.post", side_effect=[requests.ReadTimeout(), self.response('{"ok":'), self.response()]) as post:
                self.assertEqual(request_json("system", {}, {}, path, "test-key", transport_retries=1), {"ok": True})
            self.assertEqual(post.call_count, 3)
            self.assertEqual(json.loads(path.read_text())["choices"][0]["message"]["content"], '{"ok":')
            self.assertTrue(path.with_name("plan.native-json-retry-1.json").is_file())
            self.assertEqual(len(list(Path(tmp).glob("*-transport-error-*.json"))), 1)


if __name__ == "__main__":
    unittest.main()
