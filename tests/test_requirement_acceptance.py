import copy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import test_requirement_intervention as fixtures
import test_planned_paper as paper_fixtures
from document_parse import write_json
from paper_plan import normalize_research
from planned_paper import PlannedPaper
from requirement_extraction import assess_requirements, finish_assessment
from requirement_intervention import (RequirementInterruption, accept_limited_instruction, apply_decisions,
    pause, provisional_fact, read_json, reference_decisions, writing_allowed)
from research_extract_v3 import writing_eligible


TEXT = "기존 검증 문제의 입력 구성을 그대로 재사용했다. 정확도 수치는 따로 기록하지 않았다. 이 범위만 짧게 반영해줘."


class LimitedAcceptanceTests(unittest.TestCase):
    def accept(self, root):
        with self.assertRaises(RequirementInterruption) as caught:
            pause(root, fixtures.question(), fixtures.row(), [fixtures.fact()], "질문 대기")
        return accept_limited_instruction(root, caught.exception.pending["id"], TEXT)

    def test_explicit_acceptance_preserves_original_missing_result_and_does_not_call_model(self):
        with TemporaryDirectory() as tmp, patch("requests.sessions.Session.request", side_effect=AssertionError("network")):
            root = Path(tmp)
            d = self.accept(root)
            self.assertEqual(d["action"], "accept_limited")
            self.assertEqual(d["original_assessment"], fixtures.row())
            self.assertEqual(d["provided_text"], TEXT)
            self.assertEqual(read_json(root / "pending-question.json")["status"], "instruction_saved")
            with self.assertRaises(ValueError):
                accept_limited_instruction(root, d["pending_id"], TEXT)

    def test_blank_acceptance_is_not_saved(self):
        with TemporaryDirectory() as tmp:
            with self.assertRaises(RequirementInterruption) as caught:
                pause(tmp, fixtures.question(), fixtures.row(), [], "대기")
            with self.assertRaises(ValueError):
                accept_limited_instruction(tmp, caught.exception.pending["id"], " ")
            self.assertIsNone(read_json(Path(tmp) / "human-decisions.json"))

    def test_acceptance_allows_its_exact_user_account_but_not_arbitrary_unverified_facts(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            d = self.accept(root)
            f = provisional_fact(d)
            self.assertFalse(writing_eligible(f))
            self.assertTrue(writing_allowed(f, [d]))
            self.assertFalse(writing_allowed(f, []))
            self.assertFalse(writing_allowed({**f, "statement": "조작한 결과는 99%다."}, [d]))
            self.assertFalse(writing_allowed({**f, "requirement_ids": ["Q2"]}, [d]))
            self.assertFalse(writing_allowed(f, [d, {**fixtures.decision(), "action": "exclude"}]))
            engine = Mock()
            engine.call.side_effect = AssertionError("Acceptance must not trigger interpretation or source review")
            items, history = apply_decisions(engine, root, {"requirements": [fixtures.question()]}, [], {})
            self.assertEqual(items, [f])
            result = assess_requirements(engine, root, {"requirements": [fixtures.question()]}, items,
                                         {"Q1": {"status": "uncertain"}}, history)
            self.assertEqual(result["Q1"]["status"], "accepted_limited")
            self.assertEqual(result["Q1"]["missing_fields"], fixtures.row()["missing_fields"])
            self.assertEqual(result["Q1"]["original_assessment"], fixtures.row())

    def finish(self, root, pending=None, unsupported=False, second_question=False):
        pdf = root / "journal.pdf"
        pdf.write_bytes(b"test fixture")
        import hashlib
        source = {"source": {"file": pdf.name, "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest()},
                  "run_dir": str(root / "sources"), "page_count": 1, "pdf_image_inventory": [],
                  "elements": [{"element_id": "p1:e1", "page": 1, "category": "paragraph", "origin": "standard_parse",
                                "text": fixtures.fact()["statement"]}]}
        questions = [fixtures.question()]
        applicability = {"Q1": {"status": "applicable"}}
        if second_question:
            questions.append({**fixtures.question(), "id": "Q2"})
            applicability["Q2"] = {"status": "applicable"}
        engine = Mock()
        engine.call.side_effect = AssertionError("Unexpected model call")
        items = [{**fixtures.fact(), "support": "unsupported"}] if unsupported else []
        return finish_assessment(pdf, engine, root, source, {"requirements": questions}, items,
                                 applicability, [1], pending or [])

    def test_gate_is_relaxed_for_current_question_only_and_keeps_missing_metadata(self):
        for kwargs in ({}, {"pending": [1]}, {"unsupported": True}, {"second_question": True},
                       {"unsupported": True, "pending": [1]},
                       {"unsupported": True, "second_question": True}):
            with self.subTest(kwargs=kwargs), TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.accept(root)
                result = self.finish(root, **kwargs)
                blocked = bool(kwargs.get("pending") or kwargs.get("second_question"))
                self.assertEqual(result["completion"]["ready_for_drafting"], not blocked)
                self.assertEqual(result["completion"]["provisionally_accepted_question_ids"], ["Q1"])
                self.assertEqual(result["requirement_coverage"]["Q1"]["missing_fields"], ["정확도 지표"])
                normalized = normalize_research(result["research"])
                self.assertTrue(normalized["facts"][0]["user_provided"])
                self.assertEqual(normalized["facts"][0]["support"], "user_accepted")
                self.assertEqual(normalized["facts"][0]["sources"][0]["quote"], TEXT)
                if kwargs.get("second_question"):
                    self.assertEqual(result["completion"]["unresolved_requirement_ids"], ["Q2"])
                if kwargs.get("unsupported"):
                    self.assertEqual(result["completion"]["quarantined_fact_ids"], ["E00001"])
                    self.assertNotIn("E00001", result["writing_fact_ids"])
                    self.assertNotIn("E00001", [f["id"] for f in normalized["facts"]])
                    self.assertEqual(result["items"][0]["support"], "unsupported")
                    self.assertEqual(read_json(root / "evidence.json")["items"][0]["support"], "unsupported")
                    if not blocked:
                        engine = PlannedPaper(root)
                        with patch.object(engine, "load_evidence", return_value=result):
                            self.assertEqual(engine.load_research({}), result["research"])

    def test_quarantined_candidates_alone_do_not_supply_writing_evidence(self):
        with TemporaryDirectory() as tmp:
            result = self.finish(Path(tmp), unsupported=True)
            self.assertFalse(result["completion"]["ready_for_drafting"])
            self.assertEqual(result["writing_fact_ids"], [])
            self.assertIsNone(result["research"])
            self.assertEqual(result["completion"]["unresolved_requirement_ids"], ["Q1"])

    def test_limited_scope_reaches_plan_writer_and_review_without_forcing_original_fields(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.accept(root)
            package = self.finish(root)
            research = package["research"]
            catalog = {"g": {"criteria": [{"id": "g_required_1", "description": "정확도 수치 필수"}],
                             "required_content": ["정확도 수치 필수"]}}
            self.assertEqual(reference_decisions(catalog, research)["g"]["required_content"], [])
            key = research["facts"][0]["id"]
            plan = paper_fixtures.plan(2)
            for section in plan["sections"]:
                section["evidence_ids"] = [key]
                section["required_items"] = [{"id": "item_" + section["id"], "description": "입력 구성 재사용을 간결히 설명한다.",
                                               "evidence_ids": [key], "guideline_ids": []}]
            seen = []
            def client(system, packet, schema, path):
                seen.append((system, packet))
                props = schema["properties"]
                if packet.get("operation") in ("editorial_assembly", "editorial_revision"):
                    from review_test_support import editorial_reply
                    self.assertNotIn("facts", packet)
                    return editorial_reply(packet)
                if packet.get("operation") == "editorial_review":
                    self.assertNotIn("research", packet)
                    return {"issues": []}
                if "generation_order" in props:
                    return copy.deepcopy(plan)
                if "parts" in props:
                    self.assertEqual(packet["human_guidance"][0]["action"], "accept_limited")
                    self.assertEqual(packet["facts"][0]["support"], "user_accepted")
                    return {"parts": {"p0": "기존 검증 문제의 입력 구성을 그대로 재사용하였다. [근거:" + key + "]"}}
                if "sections" in props:
                    return {"sections": {sid: {"parts": {"p0":
                        "기존 검증 문제의 입력 구성을 그대로 재사용하였다. [근거:" + key + "]"}}
                        for sid in props["sections"]["properties"]}}
                if "checks" in props:
                    self.assertEqual(packet["research"]["requirement_coverage"]["Q1"]["status"], "accepted_limited")
                    paragraphs = packet["draft_paragraphs"]
                    return {"checks": [{"item_id": s["required_items"][0]["id"], "verdict": "met", "evidence_ids": [key],
                        "paragraph_ids": [next(i for i, p in paragraphs.items() if p["section_id"] == s["id"])]} for s in packet["plan"]["sections"]],
                        "issues": [], "reference_checks": []}
                raise AssertionError(str(path))
            result = PlannedPaper(root, client=client).run(research)
            self.assertTrue(result["review"]["approved"])
            self.assertNotIn("미확인", result["draft_markdown"])
            self.assertEqual(len(seen), 11)  # plan + two leaf pairs + two section pairs + paper pair

    def test_streamlit_accept_button_bypasses_interpreter_and_resumes(self):
        from streamlit.testing.v1 import AppTest
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(RequirementInterruption) as caught:
                pause(root, fixtures.question(), fixtures.row(), [], "질문 대기")
            result = {"draft_markdown": "", "plan": {"title": "제한된 범위의 계획", "rationale": "설명 범위 반영", "sections": [], "unresolved": []}}
            with patch("paper_draft_agent.PaperDraftOrchestrator.run_pipeline", return_value=result) as pipeline, \
                 patch("planned_paper.load_latest", return_value=None), \
                 patch("requirement_intervention_view.submit_instruction", side_effect=AssertionError("Interpreter must not veto explicit acceptance")), \
                 patch("requests.sessions.Session.request", side_effect=AssertionError("Unexpected network")):
                app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "streamlit_app.py"), default_timeout=15)
                app.session_state["pending_requirement"] = caught.exception.pending
                app.session_state["pending_requirement_request"] = {"planning_mode": "adaptive", "evidence_mode": "requirements", "plan_only": True}
                app.run()
                next(t for t in app.text_area if t.label == "이 질문을 어떻게 처리할까요?").input(TEXT)
                next(b for b in app.button if b.label == "현재 정보로 임시 승인하고 계속").click().run()
                self.assertFalse(list(app.exception))
                self.assertFalse(list(app.error))
                self.assertTrue(pipeline.call_args.kwargs["plan_only"])
                self.assertEqual(read_json(root / "human-decisions.json")[0]["action"], "accept_limited")
                self.assertEqual(app.session_state["paper_plan"]["title"], "제한된 범위의 계획")


if __name__ == "__main__":
    unittest.main()
