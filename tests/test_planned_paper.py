import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from paper_plan import bind_plan_evidence, normalize_research, plan_schema, project_profile, reference_catalog, validate_plan
from planned_paper import PlannedPaper, compose_parts, index_paragraphs, load_latest, materialize_review, render_paper, request_json, validate_body, validate_review


def research(title="수질 처리 비교"):
    return normalize_research({"title": title, "provenance": "synthetic_test_fixture",
        "facts": [{"id": "F1", "statement": "두 처리 조건을 같은 입력에서 비교했다.", "limits": "모의 자료다."},
                  {"id": "F2", "statement": "조건 B의 관측값은 12였다.", "limits": "전체 원인을 분리하지 않았다."}]})


def plan(count=3, placeholder=False):
    roles = ["introduction"] + ["methods"] * (count - 2) + ["conclusion"]
    sections = []
    for index, role in enumerate(roles):
        key = f"s{index}"
        sections.append({"id": key, "title": f"연구별 장 {index}", "role": role, "purpose": "주어진 근거를 설명한다.",
            "status": "write", "subsections": ["설계 근거", "적용 범위"] if role == "methods" else [],
            "evidence_ids": ["F1", "F2"], "reference_ids": [], "reference_adaptation": "",
            "table_ids": [], "depends_on": [f"s{index-1}"] if index else [],
            "required_items": [{"id": f"item{index}", "description": "관측과 범위를 설명한다.", "evidence_ids": ["F1"]}]})
    if placeholder:
        sections.insert(1, {"id": "related", "title": "관련 연구", "role": "related_work", "purpose": "저자가 작성한다.",
            "status": "placeholder", "subsections": [], "evidence_ids": [], "reference_ids": [],
            "reference_adaptation": "", "table_ids": [], "depends_on": [], "required_items": []})
    return {"title": "자료에 맞춘 제목", "rationale": "입력 근거의 역할에 맞춰 구성한다.", "sections": sections,
            "generation_order": [f"s{i}" for i in range(count)], "unresolved": ["독립 검증 필요"]}


class FakeClient:
    def __init__(self, selected_plan, reject=False):
        self.plan = selected_plan
        self.calls = []
        self.reject = reject

    def __call__(self, system, packet, schema, path):
        self.calls.append((system, packet))
        properties = schema["properties"]
        if "generation_order" in properties:
            return copy.deepcopy(self.plan)
        if "parts" in properties:
            return {"parts": {key: "두 처리 조건을 같은 입력에서 비교했다. [근거:F1] 관측값 12는 입력 자료의 범위에서 해석한다. [근거:F2]"
                              for key in properties["parts"]["properties"]}}
        if "checks" in properties:
            paragraph_for = lambda key: next(identifier for identifier, p in packet["draft_paragraphs"].items() if p["section_id"] == key)
            return {"checks": [{"item_id": item["id"], "verdict": "met",
                                "paragraph_ids": [paragraph_for(section["id"])], "evidence_ids": ["F1"]}
                               for section in packet["plan"]["sections"] for item in section["required_items"]],
                    "issues": [{"section_id": "s0", "severity": "error", "paragraph_id": "none", "reason": "검토 미통과 시험", "evidence_ids": []}] if self.reject else [],
                    "reference_checks": [{"section_id": s["id"], "reference_id": key, "verdict": "partial", "paragraph_ids": [paragraph_for(s["id"])], "reason": "시험용 판정"}
                                         for s in packet["plan"]["sections"] for key in s["reference_ids"]]}
        return {"sections": {key: {"parts": {part: "두 처리 조건을 같은 입력에서 비교했다. [근거:F1] 관측값 12는 입력 자료의 범위에서 해석한다. [근거:F2]"
                                             for part in value["properties"]["parts"]["properties"]}}
                             for key, value in properties["sections"]["properties"].items()}}


class PlannedPaperTests(unittest.TestCase):
    def test_cuda_profile_extracts_its_pdf_and_ignores_handwritten_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = project_profile("cuda")
            source = root / profile["research_pdf"]
            source.parent.mkdir()
            source.write_bytes(b"PDF fixture")
            for name in ("research_evidence.json", "Results & Discussion.json"):
                (root / name).write_text("THIS MUST NOT BE READ", encoding="utf-8")
            engine = PlannedPaper(root)
            with patch.object(engine, "extract_evidence", return_value={"research": research()}) as extract, \
                    patch("paper_quality.prepare_research_evidence", side_effect=AssertionError("manual profile")):
                result = engine.load_research(profile)
            extract.assert_called_once_with(source)
            self.assertEqual(result, research())

    def test_missing_project_pdf_never_falls_back_to_handwritten_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "research_evidence.json").write_text(json.dumps(research()), encoding="utf-8")
            (root / "Results & Discussion.json").write_text(json.dumps(research()), encoding="utf-8")
            with self.assertRaisesRegex(FileNotFoundError, "원본 PDF"):
                PlannedPaper(root).load_research(project_profile("cuda"))

    def test_drafting_entry_rejects_direct_fact_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "handwritten.json"
            source.write_text(json.dumps(research()), encoding="utf-8")
            engine = PlannedPaper(temporary)
            with patch.object(engine, "research_from_pdf") as extract:
                with self.assertRaisesRegex(ValueError, "직접 입력하지"):
                    engine.load_research(project_profile("generic"), research_json=source)
            extract.assert_not_called()

    def test_unresolved_requirement_cannot_be_counted_as_evidence_backed_met(self):
        value = plan()
        value["sections"][0]["required_items"][0]["evidence_ids"] = []
        with tempfile.TemporaryDirectory() as temporary:
            result = PlannedPaper(temporary, FakeClient(value)).run(research())
        check = next(c for c in result["review"]["checks"] if c["item_id"] == "item0")
        self.assertEqual(check["verdict"], "needs_check")
        self.assertIn("validation_note", check)
        self.assertEqual(result["review"]["required_content_coverage"]["total"], 2)

    def test_malformed_json_retries_once_and_preserves_both_native_responses(self):
        def response(content):
            return Mock(status_code=200, json=lambda: {"choices": [{"finish_reason": "stop", "message": {"content": content}}]})
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "reply.native.json"
            with patch("planned_paper.requests.post", side_effect=[response('{"ok": tru'), response('{"ok": true}')]) as post:
                result = request_json("system", {"input": "fixture"}, {}, path, "test-key")
            self.assertEqual(result, {"ok": True})
            self.assertEqual(post.call_count, 2)
            self.assertEqual(len(list(Path(temporary).glob("*.json"))), 2)
            self.assertIn("JSON", post.call_args.kwargs["json"]["messages"][-1]["content"])

    def test_repeated_malformed_json_does_not_become_a_success_cache(self):
        response = Mock(status_code=200, json=lambda: {"choices": [{"finish_reason": "stop", "message": {"content": "{"}}]})
        with tempfile.TemporaryDirectory() as temporary:
            engine = PlannedPaper(temporary, client=lambda system, packet, schema, path: request_json(system, packet, schema, path, "test-key"))
            with patch("planned_paper.requests.post", return_value=response) as post:
                with self.assertRaisesRegex(RuntimeError, "완결된 JSON"):
                    engine.call(Path(temporary), "fixture", "system", {}, {})
            self.assertEqual(post.call_count, 2)
            self.assertFalse(any("value" in json.loads(p.read_text(encoding="utf-8")) for p in Path(temporary).rglob("*.json")))

    def test_pdf_source_quote_and_page_are_copied_from_selected_element(self):
        original = {"elements": [{"page": 7, "id": 3, "content": {"text": "동일 입력에서 12를 관측했다."}}]}
        extracted = {"title": "비교 연구", "open_questions": [], "facts": [
            {"statement": "12를 관측했다.", "limits": "단일 관측", "element_ids": ["p7:e3"]}]}
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source.pdf"
            source.write_bytes(b"source fixture")
            engine = PlannedPaper(temporary)
            with patch("planned_paper.parse_document", return_value=original), \
                    patch.object(engine, "call", return_value=extracted) as call:
                result = engine.research_from_pdf(source)
            self.assertEqual(call.call_count, 1)
            self.assertEqual(call.call_args.args[4]["properties"]["facts"]["maxItems"], 18)
            self.assertEqual(result["facts"][0]["sources"][0],
                             {"element_id": "p7:e3", "page": 7, "quote": "동일 입력에서 12를 관측했다."})

    def test_pdf_unknown_source_id_never_becomes_research(self):
        original = {"elements": [{"page": 1, "id": 1, "content": {"text": "실제 원문"}}]}
        invalid = {"title": "비교 연구", "open_questions": [], "facts": [
            {"statement": "관측", "limits": "", "element_ids": ["p2:e1"]}]}
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source.pdf"
            source.write_bytes(b"source fixture")
            engine = PlannedPaper(temporary)
            with patch("planned_paper.parse_document", return_value=original), \
                    patch.object(engine, "call", return_value=invalid):
                with self.assertRaisesRegex(ValueError, "원문 요소 ID"):
                    engine.research_from_pdf(source)
            self.assertFalse(list(Path(temporary).rglob("research.json")))

    def test_long_pdf_extracts_each_page_group_and_selects_across_all_groups(self):
        original = {"elements": [{"page": i, "id": i, "content": {"text": f"{i}쪽 원문"}} for i in range(1, 44)]}
        calls = []
        def fake(folder, name, system, packet, schema):
            calls.append(name)
            if "selected_by_group" in schema["properties"]:
                return {"title": "전체 연구", "selected_by_group": {"group0": ["F01"], "group1": ["F09"], "group2": ["F17"]}}
            key = packet[0]["element_id"]
            return {"title": "구간 연구", "open_questions": [], "facts": [
                {"statement": f"구간 근거 {i}", "limits": "모의 자료", "element_ids": [key]} for i in range(8)]}
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source.pdf"
            source.write_bytes(b"long fixture")
            engine = PlannedPaper(temporary)
            with patch("planned_paper.parse_document", return_value=original), patch.object(engine, "call", side_effect=fake):
                result = engine.research_from_pdf(source)
            self.assertEqual(len(calls), 4)
            self.assertEqual([f["sources"][0]["page"] for f in result["facts"]], [1, 21, 41])

    def test_same_pipeline_handles_different_topics_and_section_counts_without_cuda_prompts(self):
        for title, count in (("수질 처리 비교", 3), ("네트워크 경로 선택", 5)):
            with self.subTest(title=title), tempfile.TemporaryDirectory() as temporary:
                fake = FakeClient(plan(count))
                engine = PlannedPaper(temporary, fake)
                result = engine.run(research(title))
                self.assertEqual(len(result["sections"]), count)
                self.assertEqual(len(fake.calls), count + 2)
                self.assertNotIn("CUDA", result["draft_markdown"])
                self.assertTrue(all("CROWN" not in system and "CUDA" not in system for system, _ in fake.calls))
                self.assertNotIn("[근거:", result["draft_markdown"])
                self.assertEqual(result["review"]["required_content_coverage"]["value"], 1)
                before = len(fake.calls)
                resumed = engine.run(research(title))
                self.assertEqual(resumed["draft_markdown"], result["draft_markdown"])
                self.assertEqual(len(fake.calls), before)
                self.assertEqual(load_latest(temporary)["draft_markdown"], result["draft_markdown"])

    def test_cuda_policy_retains_empty_related_work_without_fixed_chapter_workers(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = PlannedPaper(temporary, FakeClient(plan(3, True))).run(research(), project="cuda")
            self.assertIn("## 제2장 관련 연구\n\n## 제3장", result["draft_markdown"])
            self.assertEqual(len(result["sections"]), 3)

    def test_plan_rejects_unknown_evidence_cycles_and_missing_required_content(self):
        for mutate in (lambda p: p["sections"][0]["evidence_ids"].append("alien"),
                       lambda p: p["sections"][0]["depends_on"].append("s2"),
                       lambda p: p["sections"][0].update(required_items=[]),
                       lambda p: p["generation_order"].append("s0")):
            value = plan()
            mutate(value)
            with self.assertRaises(ValueError):
                validate_plan(value, research(), {}, project_profile("generic"))

    def test_reference_guides_must_match_roles_and_reach_writer_packets(self):
        reference = {"profiles": [{"section_guidelines": [{"role": "methods", "purpose": "GUIDE_MARKER", "required_content": [], "paragraph_flow": [], "figures_tables": []}],
                                   "style_rules": ["STYLE_MARKER"], "observed_outline": []}]}
        value = plan()
        with self.assertRaises(ValueError):
            validate_plan(value, research(), reference_catalog(reference), project_profile("generic"))
        value["sections"][1].update(reference_ids=["ref1_methods"], reference_adaptation="설계 동기에서 동작 설명으로 전개한다.")
        with tempfile.TemporaryDirectory() as temporary:
            fake = FakeClient(value)
            PlannedPaper(temporary, fake).run(research(), reference)
        writer_packet = next(packet for _, packet in fake.calls if packet.get("section_plan", {}).get("id") == "s1")
        self.assertEqual(writer_packet["reference_guides"][0]["purpose"], "GUIDE_MARKER")
        self.assertIn("설계 동기", writer_packet["section_plan"]["reference_adaptation"])
        value["sections"][0].update(reference_ids=["ref1_methods"], reference_adaptation="잘못 연결")
        with self.assertRaises(ValueError):
            validate_plan(value, research(), reference_catalog(reference), project_profile("generic"))

    def test_plan_preview_never_calls_writers_and_other_inputs_cannot_reuse_run_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            fake = FakeClient(plan())
            engine = PlannedPaper(temporary, fake)
            folder = Path(temporary) / "run"
            result = engine.run(research(), output_dir=folder, plan_only=True)
            self.assertEqual(len(fake.calls), 1)
            self.assertFalse((folder / "draft.md").exists())
            self.assertEqual(result["draft_markdown"], "")
            with self.assertRaises(ValueError):
                engine.run(research("다른 연구"), output_dir=folder)

    def test_writer_cannot_add_headings_or_invent_fact_ids(self):
        packet = {"subsection_headings": [], "section_plan": {"evidence_ids": ["F1"]}}
        for body in ("## 제1장 CUDA\n본문 [근거:F1]", "본문 [근거:fake]", "인용 없는 주장"):
            with self.assertRaises(ValueError):
                validate_body(body, packet)
        self.assertIn("본문", validate_body("본문 [근거:F1, F2]", {**packet, "section_plan": {"evidence_ids": ["F1", "F2"]}}))

    def test_schema_constrains_resource_ids_and_forbids_unavailable_tables(self):
        properties = plan_schema(research(), {})["properties"]["sections"]["items"]["properties"]
        self.assertEqual(properties["table_ids"]["type"], "null")
        self.assertEqual(properties["reference_ids"]["type"], "null")
        self.assertEqual(properties["evidence_ids"]["items"]["enum"], ["F1", "F2"])

    def test_reference_application_requires_real_quotes_and_all_selected_guides(self):
        value = plan(2)
        value["sections"][0]["reference_ids"] = ["ref1_introduction"]
        sections = {s["id"]: "실제 문장 [근거:F1]" for s in value["sections"]}
        report = {"checks": [{"item_id": f"item{i}", "verdict": "met", "quote": "실제 문장", "evidence_ids": ["F1"]} for i in range(2)], "issues": [], "reference_checks": []}
        with self.assertRaises(ValueError):
            validate_review(report, value, sections)
        report["reference_checks"] = [{"section_id": "s0", "reference_id": "ref1_introduction", "verdict": "applied", "quote": "가짜 인용", "reason": "설명"}]
        with self.assertRaises(ValueError):
            validate_review(report, value, sections)
        report["reference_checks"][0]["quote"] = "실제 문장"
        self.assertEqual(validate_review(report, value, sections)["reference_application"]["applied"], 1)

    def test_requirements_bind_known_facts_without_inventing_or_changing_original_plan(self):
        value = plan()
        value["sections"][0]["evidence_ids"] = ["F2"]
        linked = bind_plan_evidence(value, research())
        self.assertEqual(linked["sections"][0]["evidence_ids"], ["F2", "F1"])
        self.assertEqual(value["sections"][0]["evidence_ids"], ["F2"])
        value["sections"][0]["required_items"][0]["evidence_ids"] = ["invented"]
        with self.assertRaises(ValueError):
            bind_plan_evidence(value, research())

    def test_reviewer_must_cover_every_item_and_quote_existing_text(self):
        value = plan()
        sections = {s["id"]: "실제 문장 [근거:F1]" for s in value["sections"]}
        good = {"checks": [{"item_id": f"item{i}", "verdict": "met", "quote": "실제 문장", "evidence_ids": ["F1"]} for i in range(3)], "issues": [], "reference_checks": []}
        self.assertTrue(validate_review(good, value, sections)["approved"])
        bad = copy.deepcopy(good)
        bad["checks"].pop()
        with self.assertRaises(ValueError):
            validate_review(bad, value, sections)
        bad = copy.deepcopy(good)
        bad["checks"][0]["quote"] = "존재하지 않는 문장"
        with self.assertRaises(ValueError):
            validate_review(bad, value, sections)

    def test_failed_review_preserves_previous_draft_and_keeps_candidate(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / "run"
            folder.mkdir()
            target = folder / "draft.md"
            target.write_text("previous accepted draft", encoding="utf-8")
            with self.assertRaises(ValueError):
                PlannedPaper(temporary, FakeClient(plan(), reject=True)).run(research(), output_dir=folder)
            self.assertEqual(target.read_text(encoding="utf-8"), "previous accepted draft")
            self.assertTrue((folder / "candidate.md").exists())

    def test_table_values_are_rendered_by_code_at_planned_location(self):
        data = research()
        data["tables"] = [{"id": "t1", "evidence_ids": ["F2"], "caption": "동일 조건 비교", "columns": ["조건", "값"], "rows": [["B", "12"]], "scope": "모의 자료"}]
        value = plan()
        value["sections"][1]["table_ids"] = ["t1"]
        validate_plan(value, data, {}, project_profile("generic"))
        draft = render_paper(value, {s["id"]: "본문 [근거:F1]" for s in value["sections"]}, data)
        self.assertIn("표 2-1", draft)
        self.assertIn("| B | 12 |", draft)

    def test_code_assembles_headings_from_parts_and_keeps_empty_or_extra_parts_invalid(self):
        packet = {"subsection_headings": ["### 2.1 조건", "### 2.2 결과"], "section_plan": {"evidence_ids": ["F1"]}}
        value = {"parts": {"p0": "조건 설명 [근거:F1]", "p1": "결과 설명 [근거:F1]"}}
        body = compose_parts(value, packet)
        self.assertIn("### 2.1 조건\n\n조건 설명", body)
        redundant = copy.deepcopy(value)
        redundant["parts"]["p0"] = "### 2.1 조건\n\n조건 설명 [근거:F1]"
        self.assertEqual(compose_parts(redundant, packet), body)
        redundant["parts"]["p0"] = "### 2.9 계획 밖\n\n조건 설명 [근거:F1]"
        with self.assertRaises(ValueError):
            compose_parts(redundant, packet)
        for change in ({"p0": "본문 [근거:F1]"}, {"p0": "본문 [근거:F1]", "p1": ""}):
            with self.assertRaises(ValueError):
                compose_parts({"parts": change}, packet)

    def test_paragraph_ids_materialize_actual_draft_quotes_and_reject_other_sections(self):
        value = plan(2)
        sections = {"s0": "초안의 실제 문장 [근거:F1]", "s1": "다른 장 문장 [근거:F1]"}
        paragraphs = index_paragraphs(sections)
        report = {"checks": [{"item_id": "item0", "verdict": "met", "paragraph_ids": ["s0_p1"], "evidence_ids": ["F1"]}], "reference_checks": [], "issues": []}
        materialized = materialize_review(report, value, paragraphs)
        self.assertEqual(materialized["checks"][0]["quote"], sections["s0"])
        report["checks"][0]["paragraph_ids"] = ["s1_p1"]
        with self.assertRaises(ValueError):
            materialize_review(report, value, paragraphs)

    def test_unsupported_related_work_is_omitted_and_number_prefixes_are_canonicalized(self):
        value = plan(3, True)
        value["sections"][0]["title"] = "1. 서론"
        value["sections"][2]["subsections"] = ["3.1 조건", "3.2 결과"]
        linked = bind_plan_evidence(value, research(), project_profile("generic"))
        self.assertEqual(linked["omitted_empty_related_work"], ["related"])
        self.assertEqual(linked["sections"][0]["title"], "서론")
        self.assertEqual(linked["sections"][1]["subsections"], ["조건", "결과"])
        validate_plan(linked, research(), {}, project_profile("generic"))

    def test_empty_part_is_repaired_in_isolation_once_and_revalidated(self):
        packet = {"paper_title": "주제", "subsection_headings": ["### 1.1 조건", "### 1.2 결과"],
                  "section_plan": {"title": "방법", "evidence_ids": ["F1"]}, "facts": [], "context": {}}
        calls = []
        def fake(system, value, schema, path):
            calls.append(value)
            return {"text": "수정된 결과 설명 [근거:F1]"}
        with tempfile.TemporaryDirectory() as temporary:
            body = PlannedPaper(temporary, fake).repair_parts(Path(temporary), "section", {"parts": {"p0": "조건 설명 [근거:F1]", "p1": ""}}, packet)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["target_part"], "p1")
        self.assertIn("### 1.2 결과", body)

    def test_application_gateway_defaults_to_pdf_extraction_without_manual_evidence(self):
        import paper_draft_agent as gateway
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "research.pdf"
            source.write_bytes(b"PDF fixture")
            style = root / "style.json"
            style.write_text(json.dumps({"paper_structure_profile": "legacy style"}), encoding="utf-8")
            engine = gateway.PaperDraftOrchestrator("test-key")
            engine.base_dir = root
            fake = FakeClient(plan())
            with patch("planned_paper.request_json", side_effect=lambda system, packet, schema, path, key: fake(system, packet, schema, path)), \
                    patch.object(gateway, "load_extracted_results", side_effect=AssertionError("CUDA-only loader called")), \
                    patch("paper_quality.prepare_research_evidence", side_effect=AssertionError("CUDA evidence applied")), \
                    patch("planned_paper.PlannedPaper.extract_evidence", return_value={"research": research()}) as extract:
                result = engine.run_pipeline(research_pdf_path=source, structure_json_path=style,
                                             project_id="generic", plan_only=True)
            extract.assert_called_once_with(source)
            self.assertEqual(len(result["plan"]["sections"]), 3)
            self.assertEqual(len(fake.calls), 1)

    def test_latest_plan_tampering_cannot_show_old_draft_as_a_matching_review(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = PlannedPaper(temporary, FakeClient(plan())).run(research())
            (Path(result["run_dir"]) / "plan.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "계획·검토 기록"):
                load_latest(temporary)


if __name__ == "__main__":
    unittest.main()
