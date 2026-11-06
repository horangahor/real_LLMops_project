import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from paper_draft_agent import PaperDraftOrchestrator


class AdaptiveGatewayTests(unittest.TestCase):
    def test_retired_fixed_mode_is_rejected_before_file_reads_or_api_calls(self):
        with patch("planned_paper.PlannedPaper") as engine, patch("requests.sessions.Session.request") as network:
            with self.assertRaisesRegex(ValueError, "고정 구성 작성 방식은 제거"):
                PaperDraftOrchestrator("test-key").run_pipeline(planning_mode="legacy_cuda", research_pdf_path="missing.pdf")
            engine.assert_not_called()
            network.assert_not_called()

    def test_both_evidence_modes_still_use_current_extraction_gateway(self):
        for mode in ("requirements", "comprehensive"):
            with self.subTest(mode=mode), TemporaryDirectory() as tmp:
                extraction = {"run_dir": str(Path(tmp) / "evidence"), "research": {"facts": []}}
                engine = Mock()
                engine.load_evidence.return_value = extraction
                gateway = PaperDraftOrchestrator("test-key")
                gateway.base_dir = Path(tmp)
                with patch("planned_paper.PlannedPaper", return_value=engine), \
                        patch("paper_draft_agent.load_paper_structure", return_value={"profiles": []}), \
                        patch("evidence_requirements.generate_requirements", return_value={"run_dir": "questions"}) as questions, \
                        patch("requests.sessions.Session.request", side_effect=AssertionError("No network")):
                    result = gateway.run_pipeline(research_pdf_path="source.pdf", evidence_mode=mode, extract_only=True)
                engine.load_evidence.assert_called_once()
                self.assertEqual(result["evidence_extraction"], extraction)
                self.assertEqual(result["draft_markdown"], "")
                self.assertEqual(questions.call_count, 1 if mode == "requirements" else 0)
                if mode == "requirements":
                    self.assertEqual(engine.evidence_requirements, {"run_dir": "questions"})

    def test_app_has_one_writing_flow_and_retains_both_evidence_choices(self):
        from streamlit.testing.v1 import AppTest
        with patch("planned_paper.load_latest", return_value=None), \
                patch("requirement_intervention.restore_pending", return_value=None), \
                patch("requests.sessions.Session.request", side_effect=AssertionError("No network")):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "streamlit_app.py"), default_timeout=15).run()
            self.assertFalse(list(app.exception))
            self.assertNotIn("작성 방식", [r.label for r in app.radio])
            collection = next(r for r in app.radio if r.label == "근거 수집 방식")
            self.assertEqual(collection.options, ["작성지침 → 요구사항 → 근거", "기존 전체 수집"])
            self.assertIn("CUDA 원본 PDF 자동 분석", next(r for r in app.radio if r.label == "데이터 선택").options)
            collection.set_value("기존 전체 수집").run()
            self.assertFalse(list(app.exception))
            self.assertIn("작성 계획만 만들기", [b.label for b in app.button])
