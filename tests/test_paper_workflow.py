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
from paper_prompts import (
    SECTION_SUBSECTIONS, CONCLUSION_MAX_CHARACTERS, CONCLUSION_RECOMMENDED_PERFORMANCE_VALUES,
)
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


def chapter_body(section, prefix):
    if section == "6":
        return conclusion(prefix)
    if section == "1":
        return prefix + " introduction paragraphs"
    return "\n\n".join(f"### {section}.{index} {title}\n\n{prefix} body {index}"
                        for index, title in enumerate(SECTION_SUBSECTIONS[section], 1))


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
                return chapter_body(section, f"WORKER_BODY_{section}")
            for section in paper.GENERATION_ORDER:
                prefix = "WORKER_BODY" if index <= 6 else "EDITED_BODY"
                self.assertIn(f"{prefix}_{section}", user_prompt)
            if "심사자" in system_prompt:
                # 종합 후 검토는 편집된 본문을 받는다.
                return json.dumps(review_report())
            return json.dumps({"sections": {section: chapter_body(section, f"EDITED_BODY_{section}")
                                            for section in paper.GENERATION_ORDER}})

        progress = []
        with patch.object(paper, "call_solar", side_effect=fake_solar):
            result = self.orchestrator.run_pipeline(planning_mode="legacy_cuda",
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
        (self.base_dir / "research_evidence.json").write_text("MANUAL PROFILE MUST NOT BE READ", encoding="utf-8")
        extractor = Mock(return_value=RESEARCH)
        module = types.ModuleType("method_result")
        module.run_cuda_optimization_agent = extractor
        mocked_result = {"draft_markdown": "full draft", "section_drafts": {}, "sections": {},
                         "review": review_report(), "review_history": []}
        with patch.dict(sys.modules, {"method_result": module}), \
                patch.object(paper, "write_paper", return_value=mocked_result), \
                patch.object(paper, "load_extracted_results") as load_cache:
            self.orchestrator.run_pipeline(planning_mode="legacy_cuda", research_pdf_path=pdf, structure_json_path=self.style_json)
        extractor.assert_called_once_with(pdf)
        load_cache.assert_not_called()

    def test_synthesis_failure_keeps_existing_draft_files(self):
        for name in ("paper_draft_full.md", "paper_draft_full.txt"):
            (self.base_dir / name).write_text("previous user draft", encoding="utf-8")
        with patch.object(paper.SectionWriter, "write", return_value="worker draft"), \
                patch.object(paper.PaperReviewer, "review", return_value=review_report()), \
                patch.object(paper, "call_solar", return_value='{"sections": {"1": "incomplete"}}'):
            with self.assertRaisesRegex(ValueError, "모두 포함"):
                self.orchestrator.run_pipeline(planning_mode="legacy_cuda", results_json_path=self.input_json,
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
            self.orchestrator.run_pipeline(planning_mode="legacy_cuda", research_pdf_path=self.base_dir / "missing.pdf")
        with self.assertRaises(FileNotFoundError):
            self.orchestrator.run_pipeline(planning_mode="legacy_cuda", results_json_path=self.base_dir / "missing.json")

    def test_conflicting_input_sources_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "하나만"):
            self.orchestrator.run_pipeline(planning_mode="legacy_cuda", research_pdf_path="a.pdf", results_json_path=self.input_json)

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

    def test_writing_policy_leakage_is_advisory_but_scientific_limits_are_preserved(self):
        body = ("연구 자료에서 CROWN이라는 명칭이 등장한다. 약어의 풀이는 검토된 자료에서 "
                "확인되지 않았으므로 이 장에서는 약어를 풀지 않는다.")
        issues = known_quality_issues({"1": body})
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["severity"], "warning")
        self.assertIn(issues[0]["quote"], body)
        self.assertFalse(known_quality_issues({"1": "CROWN 검증 계산의 GPU 실행을 다룬다. "
                                             "개별 최적화 효과를 분리하지 못했다. "
                                             "[확인 필요: GPU 모델]"}))

    def test_conclusion_number_count_is_advisory_and_does_not_block_saving(self):
        sections = {section: chapter_body(section, "body") for section in paper.GENERATION_ORDER}
        sections["6"] = conclusion(", ".join(f"{index}ms" for index in range(1, 14)))
        with patch.object(paper.SectionWriter, "write", side_effect=lambda section, *_: sections[section]), \
                patch.object(paper.PaperSynthesizer, "synthesize", return_value=sections), \
                patch.object(paper, "call_solar", return_value=json.dumps(review_report())):
            result = self.orchestrator.run_pipeline(planning_mode="legacy_cuda", results_json_path=self.input_json,
                                                    structure_json_path=self.style_json)
        self.assertTrue(result["review"]["approved"])
        issue, = result["review"]["issues"]
        self.assertEqual(issue["severity"], "warning")
        self.assertIn("13개 / 권장 10개", issue["reason"])
        saved = json.loads((self.base_dir / "paper_draft_review.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["review"], result["review"])
        self.assertEqual((self.base_dir / "paper_draft_full.md").read_text(encoding="utf-8"),
                         result["draft_markdown"])

    def test_number_count_warning_does_not_allow_unsupported_claims(self):
        sections = {section: chapter_body(section, "body") for section in paper.GENERATION_ORDER}
        sections["6"] = conclusion(", ".join(f"{index}ms" for index in range(1, 14)))
        sections["6"] += " 커널 호출 40% 감소."
        with patch.object(paper, "call_solar", return_value=json.dumps(review_report())):
            report = paper.PaperReviewer("key").review(sections, RESEARCH)
        self.assertFalse(report["approved"])
        self.assertTrue(any(issue["severity"] == "warning" for issue in report["issues"]))
        self.assertTrue(any(issue["severity"] == "error" and "근거 없는 커널" in issue["reason"]
                            for issue in report["issues"]))

    def test_relaxed_conclusion_limits_accept_current_size_and_boundaries(self):
        # 실제 실패 사례(약 2,300자·수치 8개)와 새 상한을 모두 허용한다.
        for size, count in ((2302, 8), (CONCLUSION_MAX_CHARACTERS, CONCLUSION_RECOMMENDED_PERFORMANCE_VALUES)):
            with self.subTest(size=size, count=count):
                text = conclusion(", ".join(f"{index}ms" for index in range(1, count + 1)))
                text += "가" * (size - len(text))
                self.assertFalse(known_quality_issues({"6": text}))
                sections = {section: chapter_body(section, "body") for section in paper.GENERATION_ORDER}
                sections["6"] = text
                with patch.object(paper, "call_solar", return_value=json.dumps(review_report())):
                    self.assertTrue(paper.PaperReviewer("key").review(sections, RESEARCH)["approved"])

    def test_conclusion_length_message_reports_measured_limit(self):
        text = conclusion("result")
        text += "가" * (CONCLUSION_MAX_CHARACTERS + 1 - len(text))
        issues = known_quality_issues({"6": text})
        self.assertEqual(len(issues), 1)
        self.assertIn(f"{CONCLUSION_MAX_CHARACTERS + 1:,}자", issues[0]["reason"])
        self.assertIn(f"최대 {CONCLUSION_MAX_CHARACTERS:,}자", issues[0]["reason"])
        self.assertNotIn("반복", issues[0]["reason"])

    def test_separate_observations_do_not_trigger_mixed_ratio_check(self):
        body = "13.939ms가 관측되었다. 별도 sparse.py 비교에서는 5.3배였다."
        self.assertFalse(known_quality_issues({"5": chapter_body("5", body)}))
        disclaimer = "13.939ms 관측을 CPU 대비 25.3배 가속으로 단정하지 않는다."
        self.assertFalse(known_quality_issues({"5": chapter_body("5", disclaimer)}))

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
        input_dir = service_dir / "input"
        input_dir.mkdir()
        local_pdf = input_dir / pdf.name
        local_pdf.write_bytes(b"source revision 1")
        self.assertEqual(prepare_research_evidence(RESEARCH, service_dir)["evidence_status"], "source_reviewed")
        # A new local revision must not shadow an unchanged legacy source.
        local_pdf.write_bytes(b"source revision 2")
        pdf.write_bytes(b"source revision 1")
        self.assertEqual(prepare_research_evidence(RESEARCH, service_dir)["evidence_status"], "source_reviewed")
        pdf.unlink()
        with self.assertRaisesRegex(ValueError, "변경"):
            prepare_research_evidence(RESEARCH, service_dir)

    def test_reviewer_cannot_approve_known_regression(self):
        sections = {section: "body" for section in paper.GENERATION_ORDER}
        sections["6"] = conclusion("result")
        sections["3"] = "CROWN (Convex Relaxation for ONNX Networks)"
        with patch.object(paper, "call_solar", return_value=json.dumps(review_report())):
            report = paper.PaperReviewer("key").review(sections, RESEARCH)
        self.assertFalse(report["approved"])

    def test_simplified_outline_rejects_extra_sections_and_intro_headings(self):
        sections = {section: chapter_body(section, "body") for section in paper.GENERATION_ORDER}
        self.assertFalse(known_quality_issues(sections))
        cases = {
            "1": "### 1.1 연구 배경\n\nbody",
            "3": sections["3"] + "\n\n#### 3.3.1 추가 소절\n\nbody",
            "4": sections["4"] + "\n\n### 4.4 런타임 최적화\n\nbody",
            "5": sections["5"] + "\n\n### 5.6 결과 요약\n\nbody",
        }
        for section, body in cases.items():
            with self.subTest(section=section):
                issues = known_quality_issues({**sections, section: body})
                self.assertTrue(any(issue["section"] == section and "소절 구성" in issue["reason"]
                                    for issue in issues))

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
                self.orchestrator.run_pipeline(planning_mode="legacy_cuda", results_json_path=self.input_json,
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
            worker.reset_mock()
            with patch.object(paper, "PAPER_EDITORIAL_RULES", "updated editorial rules"):
                paper.write_paper(RESEARCH, "changed style", "key", checkpoint_path=checkpoint)
            self.assertEqual(worker.call_count, 5)


if __name__ == "__main__":
    unittest.main()
