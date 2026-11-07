"""Exercise the local HTTP boundary without making external model calls."""
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from document_parse import write_json
from requirement_intervention import RequirementInterruption
from web_api import create_app


class WebApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        (self.base / "input").mkdir()
        (self.base / "input/research.pdf").write_bytes(b"%PDF-1.4\nfixture")
        self.app = create_app(self.base)
        self.w = self.app.state.workspace
        self.client = TestClient(self.app)
        self.source_id = self.w.sources()[0]["id"]

    def tearDown(self):
        self.w.pool.shutdown(wait=True)
        self.client.close()
        self.tmp.cleanup()

    def start(self, **kwargs):
        return self.client.post("/api/jobs", json=dict(action="plan", source_id=self.source_id,
                                                      mode="requirements", target_chars=30000) | kwargs)

    def wait(self, job_id):
        for _ in range(300):
            job = self.client.get("/api/jobs/" + job_id).json()
            if job["status"] not in ("running", "queued") and self.w.active is None:
                return job
            time.sleep(.01)
        self.fail("background job did not finish")

    def test_bootstrap_is_read_only_and_upload_deduplicates_by_contents(self):
        with patch("web_workspace.PaperDraftOrchestrator") as agent:
            d = self.client.get("/api/bootstrap").json()
            self.assertEqual(d["sources"][0]["id"], self.source_id)
            self.assertNotIn("api_key", d)
            agent.assert_not_called()
        a = self.client.post("/api/sources", files={"file": ("../second.pdf", b"%PDF-1.4\nnew", "application/pdf")})
        b = self.client.post("/api/sources", files={"file": ("second.pdf", b"%PDF-1.4\nnew", "application/pdf")})
        self.assertEqual(a.status_code, 200)
        self.assertEqual(a.json()["id"], b.json()["id"])
        self.assertEqual(a.json()["name"], "second.pdf")
        self.assertEqual(self.client.post("/api/sources", files={"file": ("bad.pdf", b"not a PDF")}).status_code, 400)

    def test_job_uses_existing_gateway_progress_and_persists_result(self):
        with patch("web_workspace.PaperDraftOrchestrator") as agent:
            def run(**kwargs):
                kwargs["progress_callback"](42, "계획 검토 중")
                self.assertEqual(kwargs["research_pdf_path"], str(self.base / "input/research.pdf"))
                self.assertTrue(kwargs["plan_only"])
                self.assertEqual(kwargs["evidence_mode"], "requirements")
                return dict(plan={"title": "연구 계획"}, draft_markdown="", run_dir=str(self.base))
            agent.return_value.run_pipeline.side_effect = run
            r = self.start()
            self.assertEqual(r.status_code, 202)
            job = self.wait(r.json()["id"])
            self.assertEqual(job["status"], "completed")
            self.assertEqual(job["events"][0]["progress"], 42)
            self.assertEqual(self.client.get(f"/api/jobs/{job['id']}/result").json()["plan"]["title"], "연구 계획")
            self.assertTrue((self.w.history / job["id"] / "job.json").is_file())

    def test_duplicate_active_jobs_are_rejected(self):
        release = threading.Event()
        with patch("web_workspace.PaperDraftOrchestrator") as agent:
            agent.return_value.run_pipeline.side_effect = lambda **kw: (release.wait(5) or {})
            try:
                first = self.start().json()
                self.assertEqual(self.start().status_code, 400)
                self.assertEqual(self.client.post(f"/api/evidence/load?source_id={self.source_id}&mode=comprehensive").status_code, 400)
            finally:
                release.set()
                self.wait(first["id"])

    def test_failed_job_keeps_error_and_can_be_repeated(self):
        with patch("web_workspace.PaperDraftOrchestrator") as agent:
            agent.return_value.run_pipeline.side_effect = ValueError("후보 보존: 검토 보류")
            first = self.wait(self.start().json()["id"])
            self.assertEqual(first["status"], "failed")
            self.assertIn("검토 보류", first["message"])
            agent.return_value.run_pipeline.side_effect = None
            agent.return_value.run_pipeline.return_value = dict(draft_markdown="초안", plan={})
            second = self.wait(self.start(action="draft").json()["id"])
            self.assertEqual(second["status"], "completed")
            self.assertNotEqual(first["id"], second["id"])

    def test_user_interruption_preserves_original_request(self):
        pending = dict(id="q123", run_dir=str(self.base / "draft_history/pending"),
                       question={"id": "q1", "question": "어떤 조건인가요?"}, status="waiting_for_user")
        with patch("web_workspace.PaperDraftOrchestrator") as agent:
            agent.return_value.run_pipeline.side_effect = RequirementInterruption(pending)
            job = self.wait(self.start().json()["id"])
            self.assertEqual(job["status"], "awaiting_input")
            self.assertEqual(job["pending"]["id"], "q123")
            request = json.loads((Path(pending["run_dir"]) / "interrupted-request.json").read_text())
            self.assertTrue(request["plan_only"])
            self.assertEqual(request["writing_target_chars"], 30000)

    def test_limited_acceptance_resumes_original_pipeline_not_new_screen_settings(self):
        pending = dict(id="q123", run_dir=str(self.base / "draft_history/pending"), status="waiting_for_user")
        original = dict(research_pdf_path=str(self.base / "input/research.pdf"), planning_mode="adaptive",
                        evidence_mode="requirements", project_id="generic", plan_only=True, writing_target_chars=12000)
        with patch.object(self.w, "pending", return_value=(pending, original)), \
             patch("requirement_intervention.accept_limited_instruction") as accept, \
             patch("web_workspace.PaperDraftOrchestrator") as agent:
            agent.return_value.run_pipeline.return_value = dict(plan={"title": "원래 계획"})
            job = self.wait(self.start(action="limited", pending_id="q123", target_chars=8000).json()["id"])
            self.assertEqual(job["status"], "completed")
            accept.assert_called_once()
            kwargs = agent.return_value.run_pipeline.call_args.kwargs
            self.assertEqual(kwargs["writing_target_chars"], 12000)
            self.assertTrue(kwargs["plan_only"])

    def test_evidence_modes_are_separate_and_reviews_require_explicit_confirmation(self):
        package = dict(items=[dict(id="E1", statement="사실", sources=[dict(page=1)])], writing_fact_ids=["E1"])
        self.w.evidence[(self.source_id, "comprehensive")] = package
        self.assertEqual(self.client.get(f"/api/evidence/facts?source_id={self.source_id}&mode=comprehensive").json()["total"], 1)
        self.assertEqual(self.client.get(f"/api/evidence/facts?source_id={self.source_id}&mode=requirements").status_code, 400)
        review = self.client.post(f"/api/evidence/review?source_id={self.source_id}&mode=comprehensive", json=dict(action="approve_fact", fact_id="E1"))
        self.assertEqual(review.status_code, 400)
        self.assertIn("승인 체크", review.json()["detail"])

    def section_fixture(self):
        import hashlib
        from planned_paper import PlannedPaper
        from test_hierarchical_drafting import Client
        from test_planned_paper import research
        client = Client()
        engine = PlannedPaper(self.base, client)
        data = research()
        data["source"] = dict(sha256=hashlib.sha256(self.w.source(self.source_id).read_bytes()).hexdigest(), file="research.pdf")
        planned = engine.run(data, plan_only=True)
        run_id = "generic:" + Path(planned["run_dir"]).name
        client.events.clear()
        return engine, client, run_id

    def test_section_http_job_uses_saved_plan_without_gateway_and_result_can_reload(self):
        engine, client, run_id = self.section_fixture()
        with patch("planned_paper.PlannedPaper", return_value=engine), patch("web_workspace.PaperDraftOrchestrator") as gateway:
            response = self.start(action="section", mode="comprehensive", run_id=run_id, section_id="s1")
            self.assertEqual(response.status_code, 202, response.text)
            job = self.wait(response.json()["id"])
            self.assertEqual(job["status"], "completed", job["message"])
            result = self.client.get(f"/api/jobs/{job['id']}/result").json()
            self.assertEqual(result["scope"], "section")
            gateway.assert_not_called()
            self.assertNotIn("paper", [s for s, _, _ in client.events])
            restored = self.client.get(f"/api/runs/{run_id}/sections/s1")
            self.assertEqual(restored.status_code, 200)
            self.assertEqual(restored.json()["draft_markdown"], result["draft_markdown"])

    def test_section_job_rejects_wrong_source_mode_or_missing_section_before_start(self):
        _, client, run_id = self.section_fixture()
        self.assertEqual(self.start(action="section", run_id=run_id, section_id="s1").status_code, 400)
        other = self.client.post("/api/sources", files={"file": ("other.pdf", b"%PDF-1.4\nother")}).json()
        self.assertEqual(self.start(action="section", mode="comprehensive", run_id=run_id, section_id="s1", source_id=other["id"]).status_code, 400)
        self.assertEqual(self.start(action="section", mode="comprehensive", run_id=run_id, section_id="paper").status_code, 400)
        self.assertEqual(client.events, [])
        self.assertEqual(self.client.get(f"/api/runs/{run_id}/sections/..%5Cpaper").status_code, 400)

    def test_latex_downloads_saved_paper_and_section_without_generation(self):
        import io
        from zipfile import ZipFile
        from section_drafting import run_saved_section
        engine, client, run_id = self.section_fixture()
        folder = self.w.run_folder(run_id)
        # A plan alone must never be presented as a completed paper.
        self.assertEqual(self.client.get(f"/api/runs/{run_id}/latex").status_code, 400)
        (folder / "draft.md").write_text("# 저장된 초안\n\n## 제1장 서론\n\n관측 50%.", encoding="utf-8")
        section = run_saved_section(engine, folder, "s1")
        before = {p: p.read_bytes() for p in (folder / "draft.md", folder / "plan.json")}
        with patch("web_workspace.PaperDraftOrchestrator") as gateway:
            for path in (f"/api/runs/{run_id}/latex", f"/api/runs/{run_id}/sections/s1/latex"):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200, response.text[:200] if response.status_code != 200 else "")
                self.assertEqual(response.headers["content-type"], "application/zip")
                with ZipFile(io.BytesIO(response.content)) as z:
                    self.assertIn("main.tex", z.namelist())
                    self.assertIn("content.tex", z.namelist())
                    self.assertIn("XeLaTeX", z.read("README.md").decode("utf-8"))
            gateway.assert_not_called()
        self.assertEqual(before, {p: p.read_bytes() for p in before})
        self.assertEqual(self.client.get(f"/api/runs/{run_id}/sections/..%5Cpaper/latex").status_code, 400)

    def test_local_origin_and_path_boundaries(self):
        self.assertEqual(self.client.post("/api/jobs", headers={"Origin": "https://untrusted.example"}, json={}).status_code, 403)
        self.assertEqual(self.client.get("/api/bootstrap", headers={"Host": "evil.example"}).status_code, 400)
        self.assertEqual(self.start(source_id="../../.env").status_code, 400)
        self.assertEqual(self.client.get("/api/runs/generic:..%5C..%5C.env").status_code, 400)
        folder = self.base / "draft_history/planned/generic/abc"
        folder.mkdir(parents=True)
        (folder / "plan.json").write_text('{"sections": []}')
        self.assertEqual(self.client.get("/api/runs/generic:abc").status_code, 200)
        self.assertEqual(self.client.get("/api/runs/generic:abc/download/.env").status_code, 404)

    @unittest.skipUnless(__import__('os').name == 'nt', 'Windows extended paths')
    def test_extended_windows_paths_compare_as_same_workspace(self):
        path = self.base / "draft_history/source-archive.json"
        self.assertEqual(self.w.inside("\\\\?\\" + str(path)), path)


if __name__ == "__main__":
    unittest.main()
