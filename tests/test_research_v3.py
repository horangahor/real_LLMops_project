import copy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from paper_plan import normalize_research
from planned_paper import PlannedPaper, request_json
from research_extract_v3 import apply_source_review, attribution_scopes, audit_timed_out, call, caption_conflicts, checked_ledger, extract_page, ground, reconcile_page, repair_numbers, verification_packet, verify_page, writing_eligible
from research_sources_v3 import covered_fraction, suspicious_number_spacing
from research_coverage import conservation_issues


def element():
    return {"p7:e1": {"element_id": "p7:e1", "page": 7, "category": "paragraph",
                      "origin": "standard_parse", "text": "v 3-2-8 실행 시간 12.5ms"}}


def raw_fact():
    return {"statement": "v3-2-8 실행 시간은12.5ms다.", "limits": "해당 실행 기록이다.",
            "kind": "result", "claim_status": "observed", "source_origin": "measurement_log",
            "conditions": [], "observations": [], "parameters": [], "measurements": [], "element_ids": ["p7:e1"]}


class ResearchV3Tests(unittest.TestCase):
    def test_rescue_with_nonexistent_source_ids_is_quarantined_and_preserved(self):
        import json
        invalid = raw_fact()
        invalid["element_ids"] = ["p7:nonexistent"]
        engine = Mock()
        engine.call.side_effect = [
            {"ledger": {"p7:e1": {"state": "unresolved", "fact_ids": [], "note": "원문 미보존"}}},
            {"facts": [invalid]}]
        with TemporaryDirectory() as temporary:
            result = reconcile_page(engine, Path(temporary), element(), 7, [])
            saved = json.loads((Path(temporary) / "coverage/page-0007.json").read_text(encoding="utf-8"))
        self.assertEqual(result["additions"], [])
        self.assertEqual(result["ledger"]["p7:e1"]["state"], "unresolved")
        self.assertEqual(saved["rescue_history"][0]["rejected_facts"], [invalid])

    def test_final_audit_json_failure_is_saved_as_unresolved_instead_of_aborting(self):
        import json
        engine = Mock()
        engine.call.side_effect = RuntimeError("모델이 완결된 JSON을 반환하지 못했습니다.")
        with TemporaryDirectory() as temporary:
            result = reconcile_page(engine, Path(temporary), element(), 7, [])
            saved = json.loads((Path(temporary) / "coverage/page-0007.json").read_text(encoding="utf-8"))
        self.assertEqual(result["ledger"]["p7:e1"]["state"], "unresolved")
        self.assertEqual(saved["rescue_history"][0]["stage"], "reconcile")
        self.assertEqual(engine.call.call_count, 1)

    def test_rescue_json_failure_preserves_the_missing_source_and_does_not_loop(self):
        engine = Mock()
        engine.call.side_effect = [
            {"ledger": {"p7:e1": {"state": "unresolved", "fact_ids": [], "note": "원문 미보존"}}},
            RuntimeError("모델이 완결된 JSON을 반환하지 못했습니다.")]
        with TemporaryDirectory() as temporary:
            result = reconcile_page(engine, Path(temporary), element(), 7, [])
        self.assertEqual(result["ledger"]["p7:e1"]["state"], "unresolved")
        self.assertIn("복구 응답 미완료", result["ledger"]["p7:e1"]["note"])
        self.assertEqual(engine.call.call_count, 2)

    def test_final_recheck_failure_keeps_already_resolved_source_rows(self):
        sources = element()
        sources["p7:e2"] = {**sources["p7:e1"], "element_id": "p7:e2", "text": "연구 내용"}
        engine = Mock()
        engine.call.side_effect = [
            {"ledger": {"p7:e1": {"state": "no_research", "fact_ids": [], "note": "표제"},
                        "p7:e2": {"state": "unresolved", "fact_ids": [], "note": "누락"}}},
            {"facts": []}, RuntimeError("모델이 완결된 JSON을 반환하지 못했습니다.")]
        with TemporaryDirectory() as temporary:
            result = reconcile_page(engine, Path(temporary), sources, 7, [])
        self.assertEqual(result["ledger"]["p7:e1"]["state"], "no_research")
        self.assertEqual(result["ledger"]["p7:e2"]["state"], "unresolved")

    def test_malformed_json_response_pairs_are_not_requested_again_on_resume(self):
        response = Mock(status_code=200, json=lambda: {"choices": [{"finish_reason": "stop", "message": {"content": '{"incomplete":'}}]})
        with TemporaryDirectory() as temporary, patch("planned_paper.requests.post", return_value=response) as post:
            engine = PlannedPaper(base_dir=temporary, api_key="test-key")
            for _ in range(2):
                with self.assertRaisesRegex(RuntimeError, "완결된 JSON"):
                    engine.call(Path(temporary), "review", "system", {}, {}, inference_settings={"reasoning_effort": "medium"})
            self.assertEqual(post.call_count, 4)

    def test_standard_recovery_stops_after_one_round_and_keeps_missing_sources_open(self):
        engine = Mock()
        def respond(folder, name, system, packet, schema, **kwargs):
            if "rescue" in name:
                return {"facts": []}
            return {"ledger": {"p7:e1": {"state": "unresolved", "fact_ids": [], "note": "원문 내용 미보존"}}}
        engine.call.side_effect = respond
        with TemporaryDirectory() as temporary, patch.dict("os.environ", {"RESEARCH_MAX_RECOVERY_ROUNDS": "1"}):
            result = reconcile_page(engine, Path(temporary), element(), 7, [])
        self.assertEqual(engine.call.call_count, 3)
        self.assertEqual(result["ledger"]["p7:e1"]["state"], "unresolved")

    def test_final_checkpoint_reuses_identical_inputs_but_not_changed_source(self):
        engine = Mock()
        engine.call.return_value = {"ledger": {"p7:e1": {"state": "no_research", "fact_ids": [], "note": "표제"}}}
        with TemporaryDirectory() as temporary, patch.dict("os.environ", {"RESEARCH_MAX_RECOVERY_ROUNDS": "0"}):
            result = reconcile_page(engine, Path(temporary), element(), 7, [])
            engine.call.reset_mock()
            self.assertEqual(reconcile_page(engine, Path(temporary), element(), 7, []), result)
            engine.call.assert_not_called()
            changed = copy.deepcopy(element())
            changed["p7:e1"]["text"] = "새 실험 내용"
            reconcile_page(engine, Path(temporary), changed, 7, [])
            self.assertTrue(engine.call.called)

    def test_recheck_targets_only_unresolved_elements_and_preserves_resolved_rows(self):
        sources = element()
        sources["p7:e2"] = {**sources["p7:e1"], "element_id": "p7:e2", "text": "새 연구 관찰"}
        engine = Mock()
        packets = []
        def respond(folder, name, system, packet, schema, **kwargs):
            packets.append((name, packet))
            if "rescue" in name:
                return {"facts": []}
            return {"ledger": {key: {"state": "no_research" if key == "p7:e1" else "unresolved",
                                      "fact_ids": [], "note": "원문 검사"} for key in packet["target_element_ids"]}}
        engine.call.side_effect = respond
        with TemporaryDirectory() as temporary, patch.dict("os.environ", {"RESEARCH_MAX_RECOVERY_ROUNDS": "1"}):
            result = reconcile_page(engine, Path(temporary), sources, 7, [])
        self.assertEqual(packets[0][1]["target_element_ids"], ["p7:e1", "p7:e2"])
        self.assertEqual(packets[1][1]["target_element_ids"], ["p7:e2"])
        self.assertEqual(packets[2][1]["target_element_ids"], ["p7:e2"])
        self.assertEqual(set(result["ledger"]), set(sources))

    def test_legacy_final_page_is_replayed_offline_before_checkpointing(self):
        from research_extract_v3 import _reconcile_page
        with TemporaryDirectory() as temporary, patch("planned_paper.request_json") as request:
            request.return_value = {"ledger": {"p7:e1": {"state": "no_research", "fact_ids": [], "note": "표제"}}}
            engine = PlannedPaper(base_dir=temporary, api_key="test-key")
            folder = Path(temporary)
            expected = _reconcile_page(engine, folder, element(), 7, [], 5, targeted=False)
            request.reset_mock()
            self.assertEqual(reconcile_page(engine, folder, element(), 7, []), expected)
            request.assert_not_called()

    def bad_number_fact(self):
        fact = raw_fact()
        fact["statement"] = "실행 시간은 999.5ms다."
        return fact

    def test_numeric_empty_json_splits_candidates_without_renumbering_them(self):
        engine = Mock()
        engine.call.side_effect = [RuntimeError("모델이 완결된 JSON을 반환하지 못했습니다."),
                                   {"repairs": {"0": [raw_fact()]}}, {"repairs": {"1": [raw_fact()]}}]
        result = repair_numbers(engine, Path("unused"), element(), [self.bad_number_fact()] * 2, "numbers")
        self.assertEqual(len(result), 2)
        self.assertTrue(all(not f["numeric_issues"] for f in result))
        self.assertEqual([c.args[1] for c in engine.call.call_args_list], ["numbers", "numbers-split-a", "numbers-split-b"])
        self.assertEqual(set(engine.call.call_args.args[3]["bad_facts"]), {"1"})

    def test_single_candidate_empty_json_keeps_original_as_unresolved(self):
        engine = Mock()
        engine.call.side_effect = RuntimeError("모델이 완결된 JSON을 반환하지 못했습니다.")
        result = repair_numbers(engine, Path("unused"), element(), [self.bad_number_fact()], "numbers")
        self.assertEqual(result[0]["statement"], self.bad_number_fact()["statement"])
        self.assertTrue(result[0]["numeric_issues"])
        self.assertTrue(result[0]["repair_unresolved"])
        self.assertIn("완결된 JSON", result[0]["numeric_repair_error"])
        result[0].update(support="supported", attribution_preserved=True, writing_role="research_fact")
        self.assertFalse(writing_eligible(result[0]))
        self.assertEqual(engine.call.call_count, 1)

    def test_numeric_empty_json_recursively_splits_but_does_not_drop_candidates(self):
        engine = Mock()
        engine.call.side_effect = RuntimeError("모델이 완결된 JSON을 반환하지 못했습니다.")
        result = repair_numbers(engine, Path("unused"), element(), [self.bad_number_fact()] * 4, "numbers")
        self.assertEqual(len(result), 4)
        self.assertTrue(all(f["repair_unresolved"] and f["numeric_issues"] for f in result))
        self.assertEqual(engine.call.call_count, 7)

    def test_numeric_api_failure_is_not_mistaken_for_empty_json(self):
        engine = Mock()
        engine.call.side_effect = RuntimeError("Solar 요청 실패 (HTTP 401)")
        with self.assertRaisesRegex(RuntimeError, "401"):
            repair_numbers(engine, Path("unused"), element(), [self.bad_number_fact()], "numbers")
        self.assertEqual(engine.call.call_count, 1)

    def test_cached_medium_and_low_empty_numeric_responses_can_resume_without_repeating_requests(self):
        response = Mock(status_code=200, json=lambda: {"choices": [{"finish_reason": "stop", "message": {"content": None}}]})
        with TemporaryDirectory() as temporary, patch("planned_paper.requests.post", return_value=response) as post:
            engine = PlannedPaper(base_dir=temporary, api_key="test-key")
            for _ in range(2):
                result = repair_numbers(engine, Path(temporary), element(), [self.bad_number_fact()], "numbers")
                self.assertTrue(result[0]["numeric_issues"])
                self.assertTrue(result[0]["repair_unresolved"])
            self.assertEqual(post.call_count, 4)

    def test_long_native_retry_paths_are_saved_and_reused_without_more_requests(self):
        from document_parse import filesystem_path
        response = Mock(status_code=200, json=lambda: {"choices": [{"finish_reason": "stop", "message": {"content": None}}]})
        with TemporaryDirectory() as temporary, patch("planned_paper.requests.post", return_value=response) as post:
            folder = Path(temporary) / ("source-context-" * 7) / "global-review"
            while len(str(folder.absolute())) < 190:
                folder = folder / "review"
            engine = PlannedPaper(base_dir=temporary, api_key="test-key")
            for _ in range(2):
                with self.assertRaisesRegex(RuntimeError, "완결된 JSON"):
                    engine.call(folder, "page-0091-global-verify", "system", {}, {},
                                inference_settings={"reasoning_effort": "medium"})
            self.assertEqual(post.call_count, 4)
            for cached in filesystem_path(folder / "responses").iterdir():
                cached.unlink()

    def test_empty_audit_json_is_explicitly_unresolved_for_final_review(self):
        import json
        engine = Mock()
        engine.call.side_effect = RuntimeError("모델이 완결된 JSON을 반환하지 못했습니다.")
        with TemporaryDirectory() as temporary:
            result = extract_page(engine, Path(temporary), element(), 7, [ground(raw_fact(), element())])
            saved = json.loads((Path(temporary) / "pages/page-0007.json").read_text(encoding="utf-8"))
        self.assertTrue(result["unresolved"])
        self.assertEqual(result["ledger"]["p7:e1"]["state"], "unresolved")
        self.assertTrue(saved["audit"]["deferred_after_empty_json"])
        self.assertEqual(len(saved["initial"]), 1)

    def audit_response(self, indices):
        return {"additions": [], "invalid_fact_indices": indices,
                "ledger": {"p7:e1": {"state": "represented", "fact_refs": [0], "addition_refs": [], "note": "원문 대조"}}}

    def test_invalid_audit_indices_retry_only_the_audit_and_preserve_rejected_response(self):
        engine = Mock()
        engine.call.side_effect = [self.audit_response([1]), self.audit_response([])]
        with TemporaryDirectory() as temporary:
            result = extract_page(engine, Path(temporary), element(), 7, [ground(raw_fact(), element())])
        self.assertEqual(len(result["facts"]), 1)
        self.assertEqual(engine.call.call_count, 2)
        retry = engine.call.call_args
        self.assertEqual(retry.args[1], "page-0007-audit-index-repair")
        self.assertEqual(retry.args[3]["valid_fact_indices"], [0])
        self.assertEqual(retry.args[4]["properties"]["invalid_fact_indices"]["items"]["maximum"], 0)

    def test_repeated_invalid_indices_quarantine_facts_and_keep_unresolved_evidence(self):
        import json
        for bad in ([1], [-1], [True], ["0"], [[0]]):
            with self.subTest(indices=bad), TemporaryDirectory() as temporary:
                engine = Mock()
                engine.call.side_effect = [self.audit_response(bad), self.audit_response(bad)]
                result = extract_page(engine, Path(temporary), element(), 7, [ground(raw_fact(), element())])
                saved = json.loads((Path(temporary) / "pages/page-0007.json").read_text(encoding="utf-8"))
                self.assertEqual(result["facts"], [])
                self.assertEqual(result["ledger"]["p7:e1"]["state"], "unresolved")
                self.assertTrue(result["unresolved"])
                self.assertEqual(len(saved["initial"]), 1)
                self.assertEqual(len(saved["audit"]["rejected_audits"]), 2)
                self.assertEqual(engine.call.call_count, 2)

    def test_index_repair_request_failure_defers_instead_of_aborting_extraction(self):
        engine = Mock()
        engine.call.side_effect = [self.audit_response([9]), RuntimeError("Solar HTTP 429")]
        with TemporaryDirectory() as temporary:
            result = extract_page(engine, Path(temporary), element(), 7, [ground(raw_fact(), element())])
        self.assertEqual(result["facts"], [])
        self.assertTrue(result["unresolved"])
        self.assertEqual(engine.call.call_count, 2)

    def test_cached_invalid_audit_reuses_the_separate_successful_repair(self):
        with TemporaryDirectory() as temporary, patch("planned_paper.request_json") as request:
            request.side_effect = [self.audit_response([4]), self.audit_response([])]
            engine = PlannedPaper(base_dir=temporary)
            folder = Path(temporary)
            for _ in range(2):
                result = extract_page(engine, folder, element(), 7, [ground(raw_fact(), element())])
                self.assertEqual(len(result["facts"]), 1)
            self.assertEqual(request.call_count, 2)
            self.assertEqual(len(list((folder / "responses").glob("*.json"))), 2)

    def test_valid_invalidation_still_removes_the_fact_without_retry(self):
        engine = Mock()
        engine.call.return_value = self.audit_response([0])
        with TemporaryDirectory() as temporary:
            result = extract_page(engine, Path(temporary), element(), 7, [ground(raw_fact(), element())])
        self.assertEqual(result["facts"], [])
        self.assertEqual(engine.call.call_count, 1)

    def test_empty_initial_facts_cannot_be_invalidated(self):
        engine = Mock()
        engine.call.side_effect = [self.audit_response([0]), self.audit_response([0])]
        with TemporaryDirectory() as temporary:
            result = extract_page(engine, Path(temporary), element(), 7, [])
        self.assertEqual(result["facts"], [])
        self.assertTrue(result["unresolved"])
        self.assertEqual(engine.call.call_args.args[4]["properties"]["invalid_fact_indices"]["maxItems"], 0)

    def test_version_prefix_spacing_is_equivalent_but_quotes_are_untouched(self):
        result = ground(raw_fact(), element())
        self.assertEqual(result["numeric_issues"], [])
        self.assertEqual(result["sources"][0]["quote"], element()["p7:e1"]["text"])

    def test_represented_source_needs_an_actual_fact_link(self):
        ledger = {"p7:e1": {"state": "represented", "fact_refs": [], "note": "읽음"}}
        with self.assertRaises(ValueError):
            checked_ledger(ledger, element(), [raw_fact()])

    def test_missing_source_entry_or_wrong_source_reference_is_rejected(self):
        with self.assertRaises(ValueError):
            checked_ledger({}, element(), [raw_fact()])
        other = copy.deepcopy(raw_fact())
        other["element_ids"] = ["p8:e2"]
        with self.assertRaises(ValueError):
            checked_ledger({"p7:e1": {"state": "represented", "fact_refs": [0], "note": "수집"}}, element(), [other])

    def test_recovery_addition_can_cover_an_element_but_nonexistent_index_cannot(self):
        row = {"p7:e1": {"state": "represented", "fact_refs": [], "addition_refs": [0], "note": "빠진 측정을 보완"}}
        checked_ledger(row, element(), [], [raw_fact()])
        with self.assertRaises(ValueError):
            checked_ledger(row, element(), [], [])

    def test_ai_advice_requires_attribution_and_context_only_role(self):
        fact = {"support": "supported", "numeric_issues": [], "attribution_preserved": True,
                "claim_status": "hypothesis", "source_origin": "ai_advice", "writing_role": "context_only"}
        self.assertTrue(writing_eligible(fact))
        fact["writing_role"] = "research_fact"
        self.assertFalse(writing_eligible(fact))
        fact.update(writing_role="context_only", attribution_preserved=False)
        self.assertFalse(writing_eligible(fact))

    def test_incomplete_extraction_cannot_silently_start_drafting(self):
        package = {"research": {"title": "연구", "facts": []}, "completion": {"ready_for_drafting": False}}
        with patch.object(PlannedPaper, "load_evidence", return_value=package):
            with self.assertRaisesRegex(ValueError, "미해결"):
                PlannedPaper().load_research({}, research_pdf="unused.pdf")

    def test_context_role_survives_normalization_into_writer_input(self):
        fact = {"id": "F1", "statement": "AI가 가설을 제안했다.", "writing_role": "context_only", "attribution_preserved": True}
        normalized = normalize_research({"title": "연구", "facts": [fact]})
        self.assertEqual(normalized["facts"][0]["writing_role"], "context_only")

    def test_ocr_suspicion_does_not_silently_merge_two_numbers(self):
        self.assertTrue(suspicious_number_spacing("8 23s로 줄었다"))
        self.assertFalse(suspicious_number_spacing("조건 8 23"))
        self.assertFalse(suspicious_number_spacing("823s로 줄었다"))

    def test_transient_rate_limit_gets_one_bounded_retry(self):
        engine = Mock()
        engine.call.side_effect = [RuntimeError("Solar HTTP 429"), {"ok": True}]
        with patch("research_extract_v3.time.sleep") as sleep:
            self.assertEqual(call(engine, "arg"), {"ok": True})
        self.assertEqual(engine.call.call_count, 2)
        sleep.assert_called_once_with(5)

    def test_final_coverage_recovers_missing_source_content_then_rechecks(self):
        engine = Mock()
        identifier = "P0007R0F0001"
        engine.call.side_effect = [
            {"ledger": {"p7:e1": {"state": "unresolved", "fact_ids": [], "note": "실행 시간 누락"}}},
            {"facts": [raw_fact()]},
            {"checks": {identifier: {"support": "supported", "claim_status": "observed", "source_origin": "measurement_log", "attribution_preserved": True, "contradictions": [], "missing_support": [], "note": "원문 일치"}}},
            {"ledger": {"p7:e1": {"state": "represented", "fact_ids": [identifier], "note": "실행 시간 보존"}}}]
        with TemporaryDirectory() as temporary:
            result = reconcile_page(engine, Path(temporary), element(), 7, [])
        self.assertEqual(result["ledger"]["p7:e1"]["state"], "represented")
        self.assertEqual(len(result["additions"]), 1)
        self.assertTrue(writing_eligible(result["additions"][0]))
        self.assertEqual(engine.call.call_count, 4)

    def test_completion_claim_without_actual_fact_ids_stays_unresolved(self):
        engine = Mock()
        def respond(folder, name, system, packet, schema, **kwargs):
            if "rescue" in name:
                return {"facts": []}
            return {"ledger": {"p7:e1": {"state": "represented", "fact_ids": [], "note": "읽었다고 주장"}}}
        engine.call.side_effect = respond
        with TemporaryDirectory() as temporary:
            result = reconcile_page(engine, Path(temporary), element(), 7, [])
        self.assertEqual(result["ledger"]["p7:e1"]["state"], "unresolved")
        self.assertEqual(result["additions"], [])

    def test_verification_keeps_a_log_with_its_actual_adjacent_caption(self):
        sources = {
            "p7:e1": {**element()["p7:e1"], "category": "figure", "text": "Elapsed 12.5ms"},
            "p7:e2": {**element()["p7:e1"], "element_id": "p7:e2", "category": "caption", "text": "method A"},
            "p7:e3": {**element()["p7:e1"], "element_id": "p7:e3", "category": "figure", "text": "Elapsed 18.2ms"},
            "p7:e4": {**element()["p7:e1"], "element_id": "p7:e4", "category": "caption", "text": "method B"}}
        fact = {"id": "F1", "statement": "method A 시간은12.5ms다.", "sources": [{"element_id": "p7:e1"}]}
        packet = verification_packet([fact], sources)
        context = {e["element_id"]: e for e in packet["source_context"]}
        self.assertEqual(context["p7:e1"]["next_id"], "p7:e2")
        self.assertEqual(context["p7:e2"]["text"], "method A")
        self.assertNotIn("p7:e4", context)

    def test_only_unfinished_timeout_defers_the_early_audit(self):
        import json
        with TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / "responses").mkdir()
            prefix = "page-0007-audit-" + "a" * 20
            path = folder / "responses" / (prefix + ".native.json")
            path.write_text(json.dumps({"request_error": "ReadTimeout"}))
            self.assertTrue(audit_timed_out(folder, "page-0007-audit"))
            path.with_name(prefix + ".json").write_text("{}")
            self.assertFalse(audit_timed_out(folder, "page-0007-audit"))

    def test_supported_flag_cannot_override_an_explicit_condition_conflict(self):
        fact = ground(raw_fact(), element())
        check = {"support": "supported", "claim_status": "observed", "source_origin": "measurement_log", "attribution_preserved": True,
                 "contradictions": ["값은 있지만 실행 모드 라벨이 다른 측정에서 왔다."], "missing_support": [], "note": "라벨 충돌"}
        apply_source_review(fact, check, element())
        self.assertEqual(fact["support"], "unsupported")

    def test_explicit_ai_quote_scope_requires_attribution_and_ends_at_heading(self):
        sources = {
            "p7:e1": {**element()["p7:e1"], "text": "Claude의 답변은"},
            "p7:e2": {**element()["p7:e1"], "element_id": "p7:e2", "text": "복사가 원인일 수 있다."},
            "p7:e3": {**element()["p7:e1"], "element_id": "p7:e3", "category": "heading1", "text": "새 실험"},
            "p7:e4": {**element()["p7:e1"], "element_id": "p7:e4", "text": "직접 측정한 결과 12.5ms"}}
        scope = attribution_scopes(sources)
        self.assertIn("p7:e2", scope)
        self.assertNotIn("p7:e4", scope)
        fact = {"statement": "작성자는 복사가 원인이라고 판단했다.", "sources": [{"element_id": "p7:e2"}]}
        check = {"support": "supported", "claim_status": "interpretation", "source_origin": "research_note", "attribution_preserved": True,
                 "contradictions": [], "missing_support": [], "note": "원문에 있다."}
        apply_source_review(fact, check, sources)
        self.assertEqual(fact["source_origin"], "ai_advice")
        self.assertFalse(fact["attribution_preserved"])
        self.assertEqual(fact["support"], "unsupported")

    def test_explicit_negative_review_note_cannot_be_approved_with_empty_issue_arrays(self):
        fact = ground(raw_fact(), element())
        check = {"support": "supported", "claim_status": "observed", "source_origin": "measurement_log", "attribution_preserved": True,
                 "contradictions": [], "missing_support": [], "note": "조건 라벨이 원문과 다르게 부여된 기록이다."}
        apply_source_review(fact, check, element())
        self.assertEqual(fact["support"], "unsupported")
        self.assertTrue(fact["verification_conflicts"])

    def test_image_coverage_uses_union_and_cannot_be_inflated_by_duplicate_parse_boxes(self):
        self.assertEqual(covered_fraction((0, 0, 10, 10), [(0, 0, 5, 10), (5, 0, 10, 10)]), 1)
        self.assertEqual(covered_fraction((0, 0, 10, 10), [(0, 0, 5, 10), (0, 0, 5, 10)]), .5)
        self.assertEqual(covered_fraction((0, 0, 10, 10), [(20, 20, 30, 30)]), 0)

    def test_source_index_change_reuses_only_identical_model_request_fingerprints(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / "research-evidence-v3"
            client = Mock(return_value={"result": "saved"})
            engine = PlannedPaper(base_dir=temporary, client=client)
            engine.evidence_cache_root = root
            first = engine.call(root / "old-source", "audit", "system", {"source": "original"}, {"type": "object"})
            second = engine.call(root / "new-source", "audit", "system", {"source": "original"}, {"type": "object"})
            self.assertEqual(first, second)
            self.assertEqual(client.call_count, 1)
            engine.call(root / "new-source", "audit", "system", {"source": "changed"}, {"type": "object"})
            self.assertEqual(client.call_count, 2)

    def test_reasoning_setting_is_part_of_the_request_cache_identity(self):
        with TemporaryDirectory() as temporary, patch("planned_paper.request_json", return_value={"ok": True}) as request:
            engine = PlannedPaper(base_dir=temporary)
            folder = Path(temporary) / "run"
            engine.call(folder, "review", "system", {"fact": "example"}, {"type": "object"})
            engine.call(folder, "review", "system", {"fact": "example"}, {"type": "object"}, inference_settings={"reasoning_effort": "medium"})
            engine.call(folder, "review", "system", {"fact": "example"}, {"type": "object"}, inference_settings={"reasoning_effort": "medium"})
            self.assertEqual(request.call_count, 2)
            self.assertEqual(len(list((folder / "responses").glob("*.json"))), 2)

    def test_reasoning_only_response_retries_without_caching_an_empty_answer(self):
        responses = [Mock(status_code=200, json=lambda: {"choices": [{"finish_reason": "stop", "message": {"content": None}}]}),
                     Mock(status_code=200, json=lambda: {"choices": [{"finish_reason": "stop", "message": {"content": '{"ok":true}'}}]})]
        with TemporaryDirectory() as temporary, patch("planned_paper.requests.post", side_effect=responses) as post:
            result = request_json("system", {}, {}, Path(temporary) / "response.json", "test-key", {"reasoning_effort": "medium"})
            self.assertEqual(result, {"ok": True})
            self.assertEqual(post.call_count, 2)

    def test_two_invalid_medium_answers_fall_back_once_to_low_with_separate_cache_identity(self):
        def response(content):
            return Mock(status_code=200, json=lambda: {"choices": [{"finish_reason": "stop", "message": {"content": content}}]})
        with TemporaryDirectory() as temporary, patch("planned_paper.requests.post", side_effect=[response(None), response(None), response('{"ok":true}')]) as post:
            engine = PlannedPaper(base_dir=temporary, api_key="test-key")
            args = (Path(temporary), "review", "system", {}, {})
            result = engine.call(*args, inference_settings={"reasoning_effort": "medium"})
            self.assertEqual(result, {"ok": True})
            self.assertEqual(post.call_count, 3)
            self.assertEqual(post.call_args.kwargs["json"]["reasoning_effort"], "low")
            self.assertEqual(engine.call(*args, inference_settings={"reasoning_effort": "medium"}), result)
            self.assertEqual(post.call_count, 3)

    def test_empty_review_batch_is_split_without_losing_or_approving_unchecked_facts(self):
        facts = []
        for identifier in ("F1", "F2"):
            fact = ground(raw_fact(), element())
            fact["id"] = identifier
            facts.append(fact)
        engine = Mock()
        def respond(folder, name, system, packet, schema, **kwargs):
            keys = list(schema["properties"]["checks"]["properties"])
            if len(keys) > 1:
                raise RuntimeError("모델이 완결된 JSON을 반환하지 못했습니다.")
            return {"checks": {keys[0]: {"support": "supported", "claim_status": "observed", "source_origin": "measurement_log", "attribution_preserved": True,
                                         "contradictions": [], "missing_support": [], "note": "원문 일치"}}}
        engine.call.side_effect = respond
        result = verify_page(engine, Path("unused"), element(), {"page": 7, "facts": facts})
        self.assertEqual([f["id"] for f in result["facts"]], ["F1", "F2"])
        self.assertTrue(all(writing_eligible(f) for f in result["facts"]))
        self.assertEqual(engine.call.call_count, 3)

    def test_semantic_completion_flag_cannot_hide_an_omitted_source_identifier(self):
        source = {"text": "대형 모델이 TPU 메모리에 맞지 않을 때 어떻게 나누어 처리할지 문의했다."}
        self.assertTrue(conservation_issues(source, [{"statement": "메모리를 나누는 방식을 문의했다."}], "represented"))
        self.assertFalse(conservation_issues(source, [{"statement": source["text"]}], "represented"))

    def test_raw_data_status_cannot_hide_a_missing_labelled_latency(self):
        source = {"text": "Mean Latency: 73.125000 us"}
        self.assertTrue(conservation_issues(source, [{"statement": "결과 행렬을 출력했다."}], "raw_data"))
        self.assertFalse(conservation_issues(source, [{"measurements": [{"metric": "평균 지연", "value": "73.125", "unit": "us"}]}], "raw_data"))

    def test_clipped_screenshot_title_is_not_a_mandatory_research_identifier(self):
        source = {"category": "figure", "text": "EXEC WIN\nMean Latency: 73.125 us"}
        self.assertTrue(conservation_issues(source, [], "represented"))
        self.assertFalse(conservation_issues(source, [{"statement": "평균 지연 73.125 us"}], "represented"))

    def test_prose_time_report_must_survive_outside_quotes(self):
        source = {"category": "paragraph", "text": "작성자는 약 43ms 단축이라고 보고했다."}
        self.assertTrue(conservation_issues(source, [{"statement": "단축이라고 보고했다.", "sources": [{"quote": source["text"]}]}], "represented"))
        self.assertFalse(conservation_issues(source, [{"statement": source["text"]}], "represented"))

    def test_following_execution_caption_cannot_be_swapped_with_previous_caption(self):
        elements = {
            "p7:e0": {"element_id": "p7:e0", "page": 7, "origin": "standard_parse", "category": "caption", "text": "실행인자 없는 backward"},
            "p7:e1": {"element_id": "p7:e1", "page": 7, "origin": "standard_parse", "category": "figure", "text": "elapsed: 42.5s"},
            "p7:e2": {"element_id": "p7:e2", "page": 7, "origin": "standard_parse", "category": "caption", "text": "이번 실행인자 없는 버전 forward"}}
        fact = {"statement": "backward 시간은 42.5s다.", "sources": [{"element_id": "p7:e1"}]}
        self.assertTrue(caption_conflicts(fact, elements))
        fact["statement"] = "forward 시간은 42.5s다."
        self.assertFalse(caption_conflicts(fact, elements))
        elements["p7:e2"]["text"] = "forward와 backward를 비교해보자"
        fact["statement"] = "backward 시간은 42.5s다."
        self.assertFalse(caption_conflicts(fact, elements))

    def test_source_authored_uncertainty_is_retained_only_as_context(self):
        fact = {"support": "supported", "numeric_issues": [], "attribution_preserved": True,
                "claim_status": "unclear", "source_origin": "research_note", "writing_role": "context_only"}
        self.assertTrue(writing_eligible(fact))
        fact["writing_role"] = "research_fact"
        self.assertFalse(writing_eligible(fact))
        fact.update(writing_role="context_only", support="partial")
        self.assertFalse(writing_eligible(fact))

    def test_cache_only_lookup_never_starts_a_model_request(self):
        with TemporaryDirectory() as temporary:
            client = Mock(return_value={"ok": True})
            engine = PlannedPaper(base_dir=temporary, client=client)
            args = (Path(temporary), "review", "system", {}, {})
            with self.assertRaises(FileNotFoundError):
                engine.call(*args, cache_only=True)
            client.assert_not_called()
            expected = engine.call(*args)
            self.assertEqual(engine.call(*args, cache_only=True), expected)
            self.assertEqual(client.call_count, 1)


if __name__ == "__main__":
    unittest.main()
