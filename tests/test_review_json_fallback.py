import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from bounded_review import review_bounded
from planned_paper import PlannedPaper, index_paragraphs, review_schema
from test_hierarchical_drafting import Client
from test_planned_paper import plan, research


def fixture():
    value, data = plan(2), research()
    bodies = {"s0": "동일 조건의 관측이다. [근거:F1]", "s1": "관측 범위의 결론이다. [근거:F1]"}
    packet = {"research": data, "plan": value, "draft_paragraphs": index_paragraphs(bodies), "reference_guides": {}}
    return value, bodies, packet


def coverage_response(packet):
    return {"checks": {item["id"]: {"verdict": "met", "paragraph_ids": [
                pid for pid, p in packet["draft_paragraphs"].items() if p["section_id"] == s["id"]],
                "evidence_ids": ["F1"]} for s in packet["plan"]["sections"] for item in s["required_items"]},
            "reference_checks": {}, "issues": []}


class ReviewJSONFallbackTests(unittest.TestCase):
    def test_two_malformed_responses_use_existing_split_review_and_reuse_all_cached_work(self):
        value, bodies, packet = fixture()
        calls = []
        def post(*args, **kwargs):
            request = json.loads(kwargs["json"]["messages"][1]["content"])
            calls.append(request)
            if request.get("evidence_usage_targets"):
                content = json.dumps({"issues": []})
            elif request.get("coverage_policy"):
                content = json.dumps(coverage_response(request))
            else:
                content = '{"checks":'  # HTTP 200 + stop does not imply valid JSON.
            return Mock(status_code=200, json=lambda: {"choices": [
                {"finish_reason": "stop", "message": {"content": content}}], "usage": {"completion_tokens": 12}})
        original = copy.deepcopy(packet)
        with TemporaryDirectory() as tmp, patch("planned_paper.requests.post", side_effect=post):
            engine = PlannedPaper(tmp, api_key="test-key")
            raw, report = review_bounded(engine, Path(tmp), "review-0", "reviewer", packet,
                review_schema(value, packet["draft_paragraphs"]), value, bodies)
            self.assertTrue(report["approved"])
            self.assertEqual(len([p for p in calls if not p.get("coverage_policy") and not p.get("evidence_usage_targets")]), 2)
            self.assertEqual(len([p for p in calls if p.get("evidence_usage_targets")]), 2)
            self.assertEqual(len([p for p in calls if p.get("coverage_policy")]), 1)
            fallback = json.loads((Path(tmp) / "review-0-split-review-fallback.json").read_bytes())
            self.assertFalse(fallback["body_rewritten"])
            original_responses = {p: p.read_bytes() for p in (Path(tmp) / "responses").glob("*.native*.json")}
            audit = next(json.loads(p.read_bytes()) for p in original_responses
                         if p.name.endswith(".native.request.json") and "coverage" not in p.name and "approved-evidence" not in p.name)
            self.assertEqual(audit["attempts"][-1]["finish_reason"], "stop")
            self.assertIn("json_error", audit["attempts"][-1])
            before = len(calls)
            again = review_bounded(engine, Path(tmp), "review-0", "reviewer", packet,
                review_schema(value, packet["draft_paragraphs"]), value, bodies)
            self.assertEqual(again, (raw, report))
            self.assertEqual(len(calls), before)
            self.assertTrue(all(p.read_bytes() == data for p, data in original_responses.items()))
        self.assertEqual(packet, original)

    def test_transport_and_id_errors_do_not_turn_into_split_review_or_approval(self):
        value, bodies, packet = fixture()
        for failure in ("transport", "ids"):
            def client(system, request, schema, path):
                if failure == "transport":
                    raise RuntimeError("외부 API 응답을 받지 못했습니다.")
                raw = coverage_response(request)
                raw["checks"]["item0"]["paragraph_ids"] = ["UNKNOWN"]
                return raw
            with self.subTest(failure=failure), TemporaryDirectory() as tmp:
                with self.assertRaises(RuntimeError if failure == "transport" else ValueError):
                    review_bounded(PlannedPaper(tmp, client), Path(tmp), "review-0", "reviewer", packet,
                        review_schema(value, packet["draft_paragraphs"]), value, bodies)
                self.assertFalse((Path(tmp) / "review-0-split-review-fallback.json").exists())

    def test_split_fallback_preserves_evidence_usage_errors(self):
        value, bodies, packet = fixture()
        def client(system, request, schema, path):
            if request.get("coverage_policy"):
                return coverage_response(request)
            if request.get("evidence_usage_targets"):
                pid = next(iter(request["draft_paragraphs"]))
                return {"issues": [{"section_id": request["draft_paragraphs"][pid]["section_id"], "paragraph_id": pid,
                                    "severity": "error", "reason": "관측을 확정 성과로 확대했다.", "evidence_ids": ["F1"]}]}
            raise RuntimeError("모델이 완결된 JSON을 반환하지 못했습니다.")
        with TemporaryDirectory() as tmp:
            _, report = review_bounded(PlannedPaper(tmp, client), Path(tmp), "review-0", "reviewer", packet,
                review_schema(value, packet["draft_paragraphs"]), value, bodies)
        self.assertFalse(report["approved"])
        self.assertTrue(any(i["severity"] == "error" and i.get("review_stage") == "evidence_usage" for i in report["issues"]))

    def test_completed_subsection_checkpoint_reuses_fallback_without_rewriting_body(self):
        client, audits = Client(), []
        target = "subsection-s1-p1"
        def respond(system, request, schema, path):
            if path.parent.parent.name == target:
                if request.get("evidence_usage_targets"):
                    audits.append(request)
                    return {"issues": []}
                if "checks" in schema["properties"] and not request.get("coverage_policy"):
                    raise RuntimeError("모델이 완결된 JSON을 반환하지 못했습니다.")
            return client(system, request, schema, path)
        with TemporaryDirectory() as tmp:
            engine = PlannedPaper(tmp, respond)
            first = engine.run(research())
            self.assertTrue(first["review"]["approved"])
            self.assertEqual(sum(s == target and k == "generate" for s, k, _ in client.events), 1)
            self.assertTrue(audits)
            count = len(client.events), len(audits)
            again = engine.run(research())
            self.assertEqual((len(client.events), len(audits)), count)
            self.assertEqual(first["draft_markdown"], again["draft_markdown"])


if __name__ == "__main__":
    unittest.main()
