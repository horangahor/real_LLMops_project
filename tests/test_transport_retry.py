import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import requests

from drafting_budget import call_bounded
from planned_paper import PlannedPaper, request_json


def response(status=200, finish="stop"):
    return Mock(status_code=status, json=lambda: {"choices": [
        {"finish_reason": finish, "message": {"content": '{"ok": true}'}}]})


class TransportRetryTests(unittest.TestCase):
    def test_default_recovers_timeout_or_connection_failure_inside_same_call(self):
        for failure in (requests.ReadTimeout, requests.ConnectionError):
            with self.subTest(failure=failure.__name__), TemporaryDirectory() as tmp, \
                    patch("planned_paper.time.sleep") as sleep, \
                    patch("planned_paper.requests.post", side_effect=[failure(), response()]) as post:
                packet = {"paragraph": "배정된 문맥을 그대로 유지한다."}
                original = copy.deepcopy(packet)
                path = Path(tmp) / "review.native.json"
                self.assertEqual(request_json("system", packet, {}, path, "test-key"), {"ok": True})
                self.assertEqual(post.call_count, 2)
                self.assertEqual(post.call_args_list[0].kwargs["json"], post.call_args_list[1].kwargs["json"])
                self.assertEqual(packet, original)
                sleep.assert_called_once_with(1)
                audit = json.loads(path.with_suffix(".request.json").read_bytes())
                self.assertEqual(audit["transport_retries"], 1)
                self.assertEqual([a["transport_attempt"] for a in audit["attempts"]], [0, 1])
                self.assertEqual(audit["attempts"][0]["request_error"], failure.__name__)
                self.assertEqual(audit["attempts"][1]["http_status"], 200)
                self.assertEqual(len(list(Path(tmp).glob("*-transport-error-*.json"))), 1)
                self.assertNotIn("test-key", json.dumps(audit))

    def test_generation_editing_and_review_bounded_calls_use_same_policy_and_cache_success(self):
        for name in ("generate-0", "editorial_assembly", "editorial_revision", "editorial_recheck"):
            with self.subTest(name=name), TemporaryDirectory() as tmp, patch("planned_paper.time.sleep"), \
                    patch("planned_paper.requests.post", side_effect=[requests.ReadTimeout(), response()]) as post:
                engine = PlannedPaper(tmp, api_key="test-key")
                result = call_bounded(engine, Path(tmp), name, "system", {"input": "unchanged"}, {}, source_protocol=False)
                self.assertEqual(result, {"ok": True})
                self.assertEqual(post.call_count, 2)
                self.assertEqual(call_bounded(engine, Path(tmp), name, "system", {"input": "unchanged"}, {}, source_protocol=False), result)
                self.assertEqual(post.call_count, 2)
                audit = json.loads(next((Path(tmp) / "responses").glob("*.native.request.json")).read_bytes())
                self.assertEqual(audit["transport_retries"], 1)

    def test_both_attempts_fail_then_error_is_raised_and_no_success_cache_is_written(self):
        with TemporaryDirectory() as tmp, patch("planned_paper.time.sleep") as sleep, \
                patch("planned_paper.requests.post", side_effect=requests.ReadTimeout()) as post:
            with self.assertRaisesRegex(RuntimeError, "ReadTimeout.*전송 시도 2회"):
                PlannedPaper(tmp, api_key="test-key").call(Path(tmp), "review", "system", {}, {})
            self.assertEqual(post.call_count, 2)
            sleep.assert_called_once_with(1)
            self.assertEqual(len(list(Path(tmp).rglob("*-transport-error-*.json"))), 2)
            for path in Path(tmp).rglob("*.json"):
                self.assertNotIn("request_fingerprint", json.loads(path.read_bytes()))

    def test_explicit_zero_retries_is_honored_by_real_engine_and_direct_transport(self):
        for direct in (False, True):
            with self.subTest(direct=direct), TemporaryDirectory() as tmp, patch("planned_paper.time.sleep") as sleep, \
                    patch("planned_paper.requests.post", side_effect=requests.ReadTimeout()) as post:
                with self.assertRaisesRegex(RuntimeError, "전송 시도 1회"):
                    if direct:
                        request_json("system", {}, {}, Path(tmp) / "review.native.json", "test-key", transport_retries=0)
                    else:
                        PlannedPaper(tmp, api_key="test-key").call(Path(tmp), "review", "system", {}, {}, transport_retries=0)
                self.assertEqual(post.call_count, 1)
                sleep.assert_not_called()

    def test_old_completed_cache_survives_default_retry_policy_change(self):
        with TemporaryDirectory() as tmp, patch("planned_paper.requests.post", return_value=response()) as post:
            engine = PlannedPaper(tmp, api_key="test-key")
            original = engine.call(Path(tmp), "review", "system", {}, {}, transport_retries=0)
            records = {p.name: p.read_bytes() for p in (Path(tmp) / "responses").glob("*.json")}
            self.assertEqual(engine.call(Path(tmp), "review", "system", {}, {}), original)
            self.assertEqual(post.call_count, 1)
            self.assertEqual(records, {p.name: p.read_bytes() for p in (Path(tmp) / "responses").glob("*.json")})

    def test_http_error_or_unfinished_content_is_not_retried_as_network_failure(self):
        for reply, message in ((response(status=400), "HTTP 400"), (response(finish="length"), "정상 완료")):
            with self.subTest(message=message), TemporaryDirectory() as tmp, patch("planned_paper.time.sleep") as sleep, \
                    patch("planned_paper.requests.post", return_value=reply) as post:
                with self.assertRaisesRegex((RuntimeError, ValueError), message):
                    PlannedPaper(tmp, api_key="test-key").call(Path(tmp), "review", "system", {}, {})
                self.assertEqual(post.call_count, 1)
                sleep.assert_not_called()

    def test_custom_client_owns_transport_and_is_not_implicitly_called_twice(self):
        client = Mock(side_effect=RuntimeError("custom transport failure"))
        with TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, "custom transport failure"):
                PlannedPaper(tmp, client).call(Path(tmp), "review", "system", {}, {})
        self.assertEqual(client.call_count, 1)


if __name__ == "__main__":
    unittest.main()
