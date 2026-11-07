import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from paper_context import build_contexts
from paper_display import safe_markdown
from paper_plan import project_profile, validate_plan
from planned_paper import PlannedPaper, compose_parts, render_paper
from publication_tables import selection_report
from test_hierarchical_drafting import Client, assigned_plan
from test_planned_paper import FakeClient, plan, research
from table_placement import resolve_table_placements
from writing_length import apply_length_targets
from writing_policy import attach_policy, composition_issues, instructions, length_issues, load_policy


def table_fixture():
    data, value = research(), assigned_plan()
    data["tables"] = [{"id": key, "caption": caption, "columns": ["조건", "값"], "rows": [["A", 12]],
                       "evidence_ids": [evidence]} for key, caption, evidence in (
                           ("T1", "첫 소절 비교", "F1"), ("T2", "둘째 소절 비교", "F2"), ("unused", "보관 표", "F2"))]
    section = value["sections"][1]
    section["table_ids"] = ["T2", "T1"]
    section["table_placements"] = [{"table_id": "T1", "subsection_index": 0, "reason": "첫 질문에 필요한 비교"},
                                    {"table_id": "T2", "subsection_index": 1, "reason": "둘째 질문에 필요한 비교"}]
    return data, value


class CompositionPolicyTests(unittest.TestCase):
    def test_length_policy_changes_reuse_plan_without_sending_limits_or_selecting_less_content(self):
        with TemporaryDirectory() as tmp:
            client = FakeClient(plan())
            engine = PlannedPaper(tmp, client)
            first = engine.run(research(), plan_only=True)
            original = (Path(first["run_dir"]) / "plan.json").read_bytes()
            changed = load_policy()
            changed.update(version="writer-length-test", max_subsection_chars=500, max_section_chars=2000,
                           max_paragraph_chars=200, length_tolerance_ratio=1.5)
            changed["writing"].append("WRITER_ONLY_LENGTH_RULE")
            with patch("writing_policy.load_policy", return_value=changed):
                second = engine.run(research(), plan_only=True, writing_target_chars=5000)
            self.assertNotEqual(first["run_dir"], second["run_dir"])
            self.assertEqual(first["plan"], second["plan"])
            self.assertEqual(len(client.calls), 1)
            planner_system = client.calls[0][0]
            for token in ("공통 분량 상한", "writing_budget", "글자 수", "상한 안에서", "WRITER_ONLY_LENGTH_RULE"):
                self.assertNotIn(token, planner_system)
            self.assertEqual((Path(first["run_dir"]) / "plan.json").read_bytes(), original)

    def test_numeric_targets_reach_both_editors_without_new_length_gates(self):
        client, calls = Client(), []
        def respond(system, packet, schema, path):
            calls.append((system, copy.deepcopy(packet), schema))
            return client(system, packet, schema, path)
        with TemporaryDirectory() as tmp:
            result = PlannedPaper(tmp, respond).run(research(), writing_target_chars=40)
        writers = [(s, p) for s, p, schema in calls if "parts" in schema["properties"]]
        editors = [(s, p) for s, p, _ in calls if p.get("operation") in ("editorial_assembly", "editorial_revision")]
        self.assertTrue(writers)
        self.assertTrue(editors)
        self.assertTrue(all("공통 분량 상한" in s and p.get("writing_budget") for s, p in writers))
        self.assertEqual({p["workflow_stage"] for _, p in editors}, {"section", "paper"})
        for system, packet in editors:
            self.assertNotIn("writing_targets", packet)
            self.assertIn("공통 편집 분량 기준", system)
            self.assertIn("editing_targets", packet)
            self.assertNotIn("writing_budget", packet)
            for section in packet["editing_targets"].values():
                self.assertEqual(section["max_section_chars"], 6000)
                for part in section["parts"].values():
                    self.assertIn("target_chars", part)
                    self.assertEqual(part["max_chars"], 2000)
                    self.assertGreaterEqual(part["current_chars"], 0)
        self.assertFalse(any(i.get("validation_code") == "composition_length" and stage["level"] != "subsection"
            for stage in result["review_warnings"]["stages"] for i in stage["warnings"]))
        packet = {"composition_policy": load_policy(), "writing_budget": {"target_chars": 1}}
        body = {"s": {"parts": {"p0": "관측 범위의 설명이다. " * 100}}}
        for level in ("section", "paper"):
            self.assertFalse(composition_issues(body, {"s": packet}, level))
        self.assertTrue(composition_issues(body, {"s": packet}, "subsection"))

    def test_manual_policy_reaches_planner_and_changed_rule_creates_new_plan_without_overwrite(self):
        with TemporaryDirectory() as tmp:
            client = FakeClient(plan())
            engine = PlannedPaper(tmp, client)
            first = engine.run(research(), plan_only=True)
            system = client.calls[0][0]
            self.assertIn("핵심 질문", system)
            self.assertIn("모든 표를 선택하지 않는다", system)
            self.assertIn("table_placements", system)
            saved = Path(first["run_dir"]) / "plan.json"
            old = saved.read_bytes()
            changed = load_policy()
            changed["planning"].append("이번 공통 정책의 추가적인 구성 규칙이다.")
            with patch("writing_policy.load_policy", return_value=changed):
                second = engine.run(research(), plan_only=True)
            self.assertNotEqual(first["run_dir"], second["run_dir"])
            self.assertEqual(len(client.calls), 2)
            self.assertEqual(saved.read_bytes(), old)
            self.assertIn("추가적인 구성 규칙", client.calls[-1][0])

    def test_policy_applies_to_different_structures_without_number_specific_rules(self):
        for count in (2, 4, 5):
            with self.subTest(count=count):
                value, data = plan(count), research()
                contexts = build_contexts(value, data, {})
                attach_policy(contexts, load_policy())
                apply_length_targets(value, contexts, 30000)
                lengths = []
                for sid, children in contexts["subsections"].items():
                    for child in children.values():
                        lengths.append(child["writing_budget"]["target_chars"])
                        self.assertIn("핵심 주장", child["writing_guidance"])
                        self.assertEqual(child["facts"], contexts["sections"][sid]["facts"])
                self.assertLessEqual(sum(lengths), 30000)
                self.assertTrue(all(length <= 1600 for length in lengths))
                self.assertTrue(all(p["editorial_guidance"] for p in contexts["sections"].values()))

    def test_invalid_tolerance_is_rejected(self):
        for ratio in (0.9, True, float("inf")):
            with self.subTest(ratio=ratio), TemporaryDirectory() as tmp:
                value = load_policy()
                value["length_tolerance_ratio"] = ratio
                path = Path(tmp) / "rules.json"
                path.write_text(json.dumps(value), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_policy(path)

    def test_code_detects_total_length_even_when_everything_is_one_paragraph(self):
        packet = {"composition_policy": {"version": "test", "length_tolerance_ratio": 1.25},
                  "writing_budget": {"target_chars": 100}, "target_heading": "임의의 연구 질문"}
        value = {"arbitrary": {"parts": {"p0": "x" * 126 + " [근거:F1]"}}}
        issues = length_issues(value, {"arbitrary": packet}, "subsection")
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["validation_code"], "composition_length")
        self.assertIn("임의의 연구 질문", issues[0]["reason"])
        value["arbitrary"]["parts"]["p0"] = "x" * 125
        self.assertFalse(length_issues(value, {"arbitrary": packet}, "subsection"))

    def test_length_excess_uses_existing_writer_revision_then_stops_requesting_shortening(self):
        client, generated = Client(), []
        def respond(system, packet, schema, path):
            raw = client(system, packet, schema, path)
            if path.parent.parent.name == "subsection-s0-p0" and "parts" in schema["properties"]:
                generated.append(packet)
                if len(generated) == 1:
                    raw["parts"]["p0"] = "긴 반복 설명이다. " * 200 + "[근거:F1,F2]"
            return raw
        with TemporaryDirectory() as tmp:
            result = PlannedPaper(tmp, respond).run(research(), writing_target_chars=100)
            self.assertEqual(len(generated), 2)
            issue = generated[1]["revision"]["review"]["issues"][0]
            self.assertEqual(issue["validation_code"], "composition_layout")
            self.assertEqual(result["writing_length"]["composition_status"], "within_tolerance")

    def test_exhausted_length_revisions_remain_visible_and_cached_without_restarting(self):
        client = Client()
        def respond(system, packet, schema, path):
            raw = client(system, packet, schema, path)
            if path.parent.parent.name == "subsection-s0-p0" and "parts" in schema["properties"]:
                raw["parts"]["p0"] = "긴 반복 설명이다. " * 100 + "[근거:F1,F2]"
            return raw
        with TemporaryDirectory() as tmp:
            engine = PlannedPaper(tmp, respond)
            result = engine.run(research(), writing_target_chars=100)
            self.assertTrue(result["review"]["approved"])
            self.assertEqual(result["writing_length"]["composition_status"], "needs_shortening")
            self.assertEqual(sum(s == "subsection-s0-p0" and k == "generate" for s, k, _ in client.events), 5)  # bounded local growth repairs
            self.assertTrue(any(i.get("validation_code") == "paragraph_revision_deferred" for stage in
                result["review_warnings"]["stages"] for i in stage["warnings"]))
            self.assertTrue(any(i.get("validation_code") == "composition_length" for stage in
                result["review_warnings"]["stages"] for i in stage["warnings"]))
            count = len(client.events)
            resumed = engine.run(research(), writing_target_chars=100)
            self.assertEqual(len(client.events), count)
            self.assertEqual(resumed["draft_markdown"], result["draft_markdown"])

    def test_selected_tables_stay_in_their_own_subsections_and_unused_data_is_preserved(self):
        data, value = table_fixture()
        before = copy.deepcopy((data, value))
        validate_plan(value, data, {}, project_profile("generic"))
        contexts = build_contexts(value, data, {})
        self.assertEqual([t["id"] for t in contexts["subsections"]["s1"]["p0"]["tables"]], ["T1"])
        self.assertEqual([t["id"] for t in contexts["subsections"]["s1"]["p1"]["tables"]], ["T2"])
        sections = {sid: compose_parts({"parts": {key: "관측을 설명한다. [근거:" + ",".join(child["section_plan"]["evidence_ids"]) + "]"
                    for key, child in contexts["subsections"][sid].items()}}, packet)
                    for sid, packet in contexts["sections"].items()}
        output = render_paper(value, sections, data)
        self.assertLess(output.index("표 2-1. 첫 소절 비교"), output.index("### 2.2"))
        self.assertGreater(output.index("표 2-2. 둘째 소절 비교"), output.index("### 2.2"))
        self.assertNotIn("보관 표", output)
        self.assertEqual(selection_report(value, data)["archived_table_ids"], ["unused"])
        self.assertEqual((data, value), before)

    def test_invalid_or_duplicate_table_anchor_is_rejected(self):
        for index in (99, True):
            data, value = table_fixture()
            value["sections"][1]["table_placements"][0]["subsection_index"] = index
            with self.assertRaisesRegex(ValueError, "소절 위치"):
                validate_plan(value, data, {}, project_profile("generic"))
        data, value = table_fixture()
        value["sections"][1]["table_placements"].pop()
        with self.assertRaisesRegex(ValueError, "배치가 누락"):
            validate_plan(value, data, {}, project_profile("generic"))

    def test_tildes_are_literal_in_prose_and_tables_but_code_math_and_urls_are_unchanged(self):
        text = "149~155ms, 5~10ms, ~0.03μs\n| ~1.5 | 8~11 |\n`~/x ~ y`\n$x~y$\n$$a~b$$\n\\(a~b\\)\n[1~2~3](https://example.com/~user)\nhttps://example.com/~user\n```python\nx = '~'\n```"
        result = safe_markdown(text)
        self.assertIn(r"149\~155ms, 5\~10ms, \~0.03μs", result)
        self.assertIn(r"| \~1.5 | 8\~11 |", result)
        for token in ("`~/x ~ y`", "$x~y$", "$$a~b$$", r"\(a~b\)", "https://example.com/~user", "x = '~'"):
            self.assertIn(token, result)
        self.assertIn(r"[1\~2\~3](https://example.com/~user)", result)
        self.assertEqual(safe_markdown(result), result)

    def test_table_conflict_resolution_removes_the_losing_subsection_anchor(self):
        data, value = table_fixture()
        for section in value["sections"][:2]:
            section["table_ids"] = ["T1"]
            section["table_placements"] = [{"table_id": "T1", "subsection_index": 0, "reason": "핵심 비교"}]
        def client(*args):
            return {"placements": {"T1": {"section_id": "s1", "reason": "방법 설명에 해당하는 비교"}}}
        with TemporaryDirectory() as tmp:
            result = resolve_table_placements(PlannedPaper(tmp, client), Path(tmp), value, data)
        validate_plan(result, data, {}, project_profile("generic"))
        self.assertEqual(result["sections"][0]["table_placements"], [])
        self.assertEqual(result["sections"][1]["table_placements"][0]["table_id"], "T1")

    def test_selected_tables_and_policy_are_visible_in_completed_pipeline_report(self):
        data, value = table_fixture()
        with TemporaryDirectory() as tmp:
            result = PlannedPaper(tmp, Client(value)).run(data)
            self.assertEqual(result["review"]["table_selection"]["selected"], 2)
            self.assertEqual(result["review"]["table_selection"]["archived"], 1)
            self.assertEqual(result["review"]["composition_policy"], load_policy())
            self.assertNotIn("보관 표", result["draft_markdown"])
            self.assertLess(result["draft_markdown"].index("첫 소절 비교"), result["draft_markdown"].index("### 2.2"))


if __name__ == "__main__":
    unittest.main()
