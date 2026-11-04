import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from planned_paper import PlannedPaper
from test_hierarchical_drafting import Client
from test_planned_paper import research


class WriterRevisionRegressionTests(unittest.TestCase):
    def workflow_client(self, reject_repaired=False, interrupt=False, no_match=False):
        client = Client()
        client.plan["sections"][0]["required_items"][0]["evidence_ids"] = ["F1", "F2"]
        repaired_seen = False
        interrupted = False
        def response(system, packet, schema, path):
            nonlocal repaired_seen, interrupted
            raw = client(system, packet, schema, path)
            if path.parent.parent.name != "subsection-s0-p0":
                return raw
            if "parts" in schema["properties"]:
                if "revision" in packet:
                    if interrupt and not interrupted:
                        interrupted = True
                        raise RuntimeError("revision interruption")
                    repaired_seen = True
                raw["parts"]["p0"] = "조건 A를 비교했다. 관측값은 12였다. [근거:" + (
                    "F1,F2]" if repaired_seen and not no_match else "F1]")
            elif "checks" in schema["properties"] and reject_repaired and repaired_seen:
                raw["issues"].append({"section_id": "s0", "severity": "error", "paragraph_id": "s0_p1",
                                      "reason": "연결한 근거의 원문과 본문이 다르다", "evidence_ids": ["F2"]})
            return raw
        return client, response

    def test_workflow_revises_writer_directly_without_a_separate_link_agent_and_reuses_on_resume(self):
        with TemporaryDirectory() as tmp:
            client, response = self.workflow_client()
            engine = PlannedPaper(tmp, response)
            result = engine.run(research())
            local = [(s, k) for s, k, _ in client.events if s == "subsection-s0-p0"]
            self.assertEqual(local, [("subsection-s0-p0", k) for k in ("generate", "review", "generate", "review")])
            self.assertTrue(result["review"]["approved"])
            before = len(client.events)
            self.assertEqual(engine.run(research())["draft_markdown"], result["draft_markdown"])
            self.assertEqual(len(client.events), before)

    def test_repaired_citations_preserve_remaining_source_findings_as_warnings(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp) / "run"
            folder.mkdir()
            (folder / "draft.md").write_text("기존 초안", encoding="utf-8")
            client, response = self.workflow_client(reject_repaired=True)
            result = PlannedPaper(tmp, response).run(research(), output_dir=folder)
            self.assertEqual(sum(k == "citation_repair" for _, k, _ in client.events), 0)
            self.assertTrue((folder / "workflow/subsection-s0-p0/approved.json").exists())
            self.assertEqual((folder / "draft.md").read_text(encoding="utf-8"), result["draft_markdown"])
            self.assertTrue(any(s == "section-s0" for s, _, _ in client.events))
            self.assertIn("원문과 본문이 다르다", result["review"]["content_warnings"][0]["reason"])
            self.assertFalse(result["review"]["content_approved"])

    def test_interruption_during_writer_revision_resumes_cached_body_and_review(self):
        with TemporaryDirectory() as tmp:
            client, response = self.workflow_client(interrupt=True)
            engine = PlannedPaper(tmp, response)
            with self.assertRaisesRegex(RuntimeError, "revision interruption"):
                engine.run(research())
            before = len(client.events)
            result = engine.run(research())
            self.assertEqual(client.events[before][:2], ("subsection-s0-p0", "generate"))
            self.assertTrue(result["review"]["approved"])

    def test_no_supported_link_does_not_silently_satisfy_the_required_item(self):
        with TemporaryDirectory() as tmp:
            client, response = self.workflow_client(no_match=True)
            result = PlannedPaper(tmp, response).run(research())
            check = next(c for c in result["review"]["checks"] if c["item_id"] == client.plan["sections"][0]["required_items"][0]["id"])
            self.assertEqual(check["verdict"], "missing")
            self.assertEqual(check["missing_section_evidence_ids"], ["F2"])
            self.assertLess(result["review"]["required_content_coverage"]["value"], 1)
            snapshot = result["review_warnings"]["stages"][0]["snapshot"]
            self.assertNotIn("F2", snapshot["paragraphs"]["s0_p1"]["text"])
            self.assertTrue(result["review"]["content_warnings"])
            self.assertEqual(sum(k == "citation_repair" for _, k, _ in client.events), 0)
            self.assertEqual(sum(k == "generate" and s == "subsection-s0-p0" for s, k, _ in client.events), 3)


if __name__ == "__main__":
    unittest.main()
