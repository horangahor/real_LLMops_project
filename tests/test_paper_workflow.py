"""외부 API를 호출하지 않고 orchestration과 산출물 계약을 검증한다."""

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import paper_draft_agent as paper
from paper_quality import extraction_fingerprint, known_quality_issues, prepare_research_evidence


RESEARCH = {
    "project_name": "CUDA test research",
    "overall_result_summary": "Research summary marker",
    "optimization_methods": [{"method_name": "memory reuse", "metric_after": "10 ms"}],
}


def review_report():
    return {"approved": True, "issues": [], "evidence_checks": [
        {"section": section, "claim": "test claim", "evidence_ids": [], "status": "needs_check"}
        for section in paper.GENERATION_ORDER
    ]}


def conclusion(prefix):
    return "\n\n".join(f"{prefix} paragraph {index}" for index in range(4))


class PaperWorkflowTests(unittest.TestCase):
    def setUp(self):
        test_root = Path(__file__).resolve().parent
        self.temp_dir = tempfile.TemporaryDirectory(dir=test_root, prefix="workflow_test_")
        self.base_dir = Path(self.temp_dir.name)
        if not self.base_dir.resolve().is_relative_to(test_root):
            raise RuntimeError("테스트 임시 폴더가 작업 폴더를 벗어났습니다.")
        self.addCleanup(self.temp_dir.cleanup)
        self.input_json = self.base_dir / "research.json"
        self.input_json.write_text(json.dumps(RESEARCH), encoding="utf-8")
        self.style_json = self.base_dir / "style.json"
        self.style_json.write_text(json.dumps({"paper_structure_profile": "STYLE_MARKER"}), encoding="utf-8")
        self.orchestrator = paper.PaperDraftOrchestrator(api_key="test-key")
        self.orchestrator.base_dir = self.base_dir

    def test_workers_receive_facts_and_dependencies_then_synthesis_reads_all_sections(self):
        calls = []

        def fake_solar(system_prompt, user_prompt, api_key, reasoning_effort=None):
            self.assertEqual(api_key, "test-key")
            self.assertIn("Research summary marker", user_prompt)
            if "심사자" not in system_prompt:
                self.assertIn("STYLE_MARKER", user_prompt)
            self.assertIn("연구 사실의 근거", system_prompt)
            index = len(calls)
            calls.append((system_prompt, user_prompt))
            if index < 5:
                section = paper.GENERATION_ORDER[index]
                for earlier in paper.GENERATION_ORDER[:index]:
                    self.assertIn(f"WORKER_BODY_{earlier}", user_prompt)
                if section == "6":
                    return conclusion("WORKER_BODY_6")
                return f"### {section}.1 소절\n\nWORKER_BODY_{section}"
            for section in paper.GENERATION_ORDER:
                prefix = "WORKER_BODY" if index <= 6 else "EDITED_BODY"
                self.assertIn(f"{prefix}_{section}", user_prompt)
            if "심사자" in system_prompt:
                # 종합 후 검토는 편집된 본문을 받는다.
                return json.dumps(review_report())
            return json.dumps({"sections": {section: conclusion("EDITED_BODY_6") if section == "6"
                                            else f"EDITED_BODY_{section}" for section in paper.GENERATION_ORDER}})

        progress = []
        with patch.object(paper, "call_solar", side_effect=fake_solar):
            result = self.orchestrator.run_pipeline(
                results_json_path=self.input_json, structure_json_path=self.style_json,
                progress_callback=lambda pct, message: progress.append(pct),
            )
        self.assertEqual(len(calls), 8)
        draft = result["draft_markdown"]
        self.assertIn("## 제2장 관련 연구\n\n## 제3장", draft)
        self.assertNotIn("WORKER_BODY_", draft)
        for section in paper.GENERATION_ORDER:
            self.assertIn(f"EDITED_BODY_{section}", draft)
        self.assertEqual(progress, sorted(progress))
        self.assertEqual(progress[-1], 100)
        self.assertEqual((self.base_dir / "paper_draft_full.md").read_text(encoding="utf-8"), draft)
        self.assertEqual((self.base_dir / "paper_draft_full.txt").read_text(encoding="utf-8"), draft)
        saved = json.loads((self.base_dir / "paper_draft_sections.json").read_text(encoding="utf-8"))
        self.assertIn("WORKER_BODY_4", saved["section_drafts"]["4"])
        self.assertEqual(saved["related_work"], "")
        self.assertEqual(result["metrics"]["total_methods"], 1)

    def test_uploaded_pdf_is_extracted_even_when_cached_json_exists(self):
        pdf = self.base_dir / "research.pdf"
        pdf.write_bytes(b"test PDF placeholder")
        (self.base_dir / "Results & Discussion.json").write_text("{}", encoding="utf-8")
        extractor = Mock(return_value=RESEARCH)
        module = types.ModuleType("method_result")
        module.run_cuda_optimization_agent = extractor
        mocked_result = {"draft_markdown": "full draft", "section_drafts": {}, "sections": {},
                         "review": review_report(), "review_history": []}
        with patch.dict(sys.modules, {"method_result": module}), \
                patch.object(paper, "write_paper", return_value=mocked_result), \
                patch.object(paper, "load_extracted_results") as load_cache:
            self.orchestrator.run_pipeline(research_pdf_path=pdf, structure_json_path=self.style_json)
        extractor.assert_called_once_with(pdf)
        load_cache.assert_not_called()

    def test_synthesis_failure_keeps_existing_draft_files(self):
        for name in ("paper_draft_full.md", "paper_draft_full.txt"):
            (self.base_dir / name).write_text("previous user draft", encoding="utf-8")
        with patch.object(paper.SectionWriter, "write", return_value="worker draft"), \
                patch.object(paper.PaperReviewer, "review", return_value=review_report()), \
                patch.object(paper, "call_solar", return_value='{"sections": {"1": "incomplete"}}'):
            with self.assertRaisesRegex(ValueError, "모두 포함"):
                self.orchestrator.run_pipeline(results_json_path=self.input_json,
                                               structure_json_path=self.style_json)
        for name in ("paper_draft_full.md", "paper_draft_full.txt"):
            self.assertEqual((self.base_dir / name).read_text(encoding="utf-8"), "previous user draft")

    def test_synthesis_rejects_related_work_and_empty_sections(self):
        base = {section: "body" for section in paper.GENERATION_ORDER}
        for sections in ({**base, "2": "unwanted related work"}, {**base, "6": ""}):
            with self.subTest(sections=sections), \
                    patch.object(paper, "call_solar", return_value=json.dumps({"sections": sections})):
                with self.assertRaises(ValueError):
                    paper.PaperSynthesizer("key").synthesize(base, RESEARCH, "")

    def test_missing_explicit_pdf_or_json_does_not_fall_back_to_cached_data(self):
        with self.assertRaises(FileNotFoundError):
            self.orchestrator.run_pipeline(research_pdf_path=self.base_dir / "missing.pdf")
        with self.assertRaises(FileNotFoundError):
            self.orchestrator.run_pipeline(results_json_path=self.base_dir / "missing.json")

    def test_conflicting_input_sources_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "하나만"):
            self.orchestrator.run_pipeline(research_pdf_path="a.pdf", results_json_path=self.input_json)

    def test_truncated_response_is_not_accepted_as_a_finished_chapter(self):
        response = Mock(status_code=200)
        response.json.return_value = {"choices": [{"finish_reason": "length",
                                                    "message": {"content": "unfinished"}}]}
        with patch.object(paper.requests, "post", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "잘렸습니다"):
                paper.call_solar("system", "user", "key")

    def test_review_reasoning_parameter_is_only_sent_to_supported_models(self):
        response = Mock(status_code=200)
        response.json.return_value = {"choices": [{"finish_reason": "stop", "message": {"content": "body"}}]}
        for model, supported in (("solar-pro4", True), ("solar-pro", False)):
            with self.subTest(model=model), patch.object(paper, "MODEL_NAME", model), \
                    patch.object(paper.requests, "post", return_value=response) as request:
                self.assertEqual(paper.call_solar("system", "user", "key", reasoning_effort="low"), "body")
                payload = request.call_args.kwargs["json"]
                self.assertEqual(payload["model"], model)
                self.assertEqual("reasoning_effort" in payload, supported)

    def test_embedded_chapter_headings_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "다른 장"):
            paper._section_body("intro body\n\n## 제2장 관련 연구\nshould be blank")

    def test_known_bad_conclusion_fails_local_review(self):
        issues = known_quality_issues({"6": "### 6.1 요약\n13.939ms로 CPU 대비 5.3배 빨라졌다.\n커널 호출 40% 감소."})
        self.assertGreaterEqual(len(issues), 4)

    def test_conclusion_cannot_repeat_all_intermediate_measurements(self):
        text = conclusion("10ms, 20ms, 30ms, 40ms, 50ms, 60ms")
        issues = known_quality_issues({"6": text})
        self.assertTrue(any("수치를 과도하게" in issue["reason"] for issue in issues))

    def test_separate_observations_do_not_trigger_mixed_ratio_check(self):
        body = "13.939ms가 관측되었다. 별도 sparse.py 비교에서는 5.3배였다."
        self.assertFalse(known_quality_issues({"5": body}))
        disclaimer = "13.939ms 관측을 CPU 대비 25.3배 가속으로 단정하지 않는다."
        self.assertFalse(known_quality_issues({"5": disclaimer}))

    def test_evidence_profile_is_bound_to_extraction_and_original_pdf(self):
        import hashlib
        service_dir = self.base_dir / "service"
        service_dir.mkdir()
        pdf = self.base_dir / "source.pdf"
        pdf.write_bytes(b"source revision 1")
        profile = {"extraction_sha256": extraction_fingerprint(RESEARCH),
                   "source_file": pdf.name, "source_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
                   "review_scope": "test", "verified_facts": [{"id": "E01", "finding": "reviewed fact"}],
                   "research_findings": [], "open_questions": [], "extraction_issues": []}
        (service_dir / "research_evidence.json").write_text(json.dumps(profile), encoding="utf-8")
        evidence = prepare_research_evidence(RESEARCH, service_dir)
        self.assertEqual(evidence["evidence_status"], "source_reviewed")
        self.assertNotIn("optimization_methods", evidence)
        self.assertNotIn("review_scope", evidence["source"])
        changed = prepare_research_evidence({**RESEARCH, "project_name": "different PDF"}, service_dir)
        self.assertEqual(changed["evidence_status"], "unreviewed_extraction")
        self.assertNotIn("verified_facts", changed)
        pdf.write_bytes(b"source revision 2")
        with self.assertRaisesRegex(ValueError, "변경"):
            prepare_research_evidence(RESEARCH, service_dir)

    def test_reviewer_cannot_approve_known_regression(self):
        sections = {section: "body" for section in paper.GENERATION_ORDER}
        sections["6"] = conclusion("result")
        sections["3"] = "CROWN (Convex Relaxation for ONNX Networks)"
        with patch.object(paper, "call_solar", return_value=json.dumps(review_report())):
            report = paper.PaperReviewer("key").review(sections, RESEARCH)
        self.assertFalse(report["approved"])

    def test_failed_quality_gate_keeps_last_saved_draft_and_saves_candidate(self):
        output = self.base_dir / "paper_draft_full.md"
        output.write_text("last saved draft", encoding="utf-8")
        report = {**review_report(), "approved": False, "issues": [
            {"section": "6", "severity": "error", "reason": "unsupported comparison"}]}
        sections = {section: "candidate body" for section in paper.GENERATION_ORDER}
        with patch.object(paper.SectionWriter, "write", return_value="draft"), \
                patch.object(paper.PaperReviewer, "review", return_value=report), \
                patch.object(paper.PaperSynthesizer, "synthesize", return_value=sections) as edit:
            with self.assertRaises(paper.DraftQualityError):
                self.orchestrator.run_pipeline(results_json_path=self.input_json,
                                               structure_json_path=self.style_json)
        self.assertEqual(edit.call_count, 2)
        self.assertEqual(output.read_text(encoding="utf-8"), "last saved draft")
        self.assertTrue((self.base_dir / "paper_draft_candidate.md").exists())
        self.assertTrue((self.base_dir / "paper_draft_review_failed.json").exists())

    def test_interrupted_generation_resumes_only_matching_source_and_prompts(self):
        checkpoint = self.base_dir / "working.json"
        with patch.object(paper.SectionWriter, "write", side_effect=["saved chapter three", RuntimeError("interrupted")]):
            with self.assertRaisesRegex(RuntimeError, "interrupted"):
                paper.write_paper(RESEARCH, "style", "key", checkpoint_path=checkpoint)
        self.assertEqual(json.loads(checkpoint.read_text(encoding="utf-8"))["section_drafts"],
                         {"3": "saved chapter three"})
        sections = {section: "final body" for section in paper.GENERATION_ORDER}
        with patch.object(paper.SectionWriter, "write", return_value="new chapter") as worker, \
                patch.object(paper.PaperReviewer, "review", return_value=review_report()), \
                patch.object(paper.PaperSynthesizer, "synthesize", return_value=sections):
            paper.write_paper(RESEARCH, "style", "key", checkpoint_path=checkpoint)
            self.assertEqual(worker.call_count, 4)
            self.assertEqual(worker.call_args_list[0].args[0], "4")
            worker.reset_mock()
            paper.write_paper(RESEARCH, "changed style", "key", checkpoint_path=checkpoint)
            self.assertEqual(worker.call_count, 5)


if __name__ == "__main__":
    unittest.main()
