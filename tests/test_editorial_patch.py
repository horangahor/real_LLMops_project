import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from drafting_budget import DraftingBudgetError
from editorial_patch import apply_editorial_patch, patch_schema
from editorial_revision import editorial_sources, revise_editorial
from planned_paper import PlannedPaper
from review_test_support import editorial_reply
from test_editorial_revision import fixture
from test_hierarchical_drafting import Client
from test_planned_paper import research


def setup_patch():
    _, packet, previous, report = fixture()
    previous["s1"]["parts"]["p0"] = "앞 문맥이다. [근거:F1]\n\n수정 대상이다. [근거:F1]\n\n이어지는 문맥이다. [근거:F1]\n\n끝 문맥이다. [근거:F1]"
    parts, origins, _ = editorial_sources(previous, {"s1": packet})
    return packet, previous, report, parts, origins


def keep_slots(parts):
    return editorial_reply({"source_parts": parts, "output_mode": "fixed_slots"})


def span(raw, key, unit):
    return raw["sections"]["s1"]["parts"][key][unit["paragraph_id"]]["spans"][unit["id"]]


class EditorialPatchTests(unittest.TestCase):
    def test_full_context_is_read_and_only_changed_text_is_returned_in_fixed_slots(self):
        packet, previous, report, parts, _ = setup_patch()
        original = copy.deepcopy(previous)
        seen = []
        def client(system, body, schema, path):
            seen.append(body)
            self.assertEqual(body["source_parts"], parts)
            self.assertNotIn("quote", body["revision"]["review"]["issues"][0])
            self.assertEqual(set(schema["properties"]), {"sections"})
            self.assertNotIn("evidence_ids", json.dumps(schema))
            raw = keep_slots(parts)
            units = parts["s1"]["p0"]
            for unit in units[1:3]:
                span(raw, "p0", unit).update(action="replace", text="보완한 연결 문장이다.")
            raw["sections"]["s1"]["parts"]["p0"][units[2]["paragraph_id"]]["join_previous"] = True
            return raw
        with TemporaryDirectory() as tmp:
            result = revise_editorial(PlannedPaper(tmp, client), Path(tmp), "edit", "section", previous, {"s1": packet}, report)
            self.assertEqual(len(seen), 1)
            self.assertEqual(previous, original)
            self.assertEqual(result["s1"]["parts"]["p1"], previous["s1"]["parts"]["p1"])
            self.assertEqual(result["s1"]["parts"]["p0"], "앞 문맥이다. [근거:F1]\n\n보완한 연결 문장이다. [근거:F1] 보완한 연결 문장이다. [근거:F1]\n\n끝 문맥이다. [근거:F1]")
            log = json.loads((Path(tmp) / "edit-editorial-fixed-slots-v1-provenance.json").read_text(encoding="utf-8"))
            self.assertEqual(len(log["changes"]), 2)
            self.assertEqual(len(log["paragraph_joins"]), 1)

    def test_schema_binds_each_source_to_its_own_part_and_paragraph_without_location_fields(self):
        _, _, _, parts, _ = setup_patch()
        schema = patch_schema(parts)
        tree = schema["properties"]["sections"]["properties"]["s1"]["properties"]["parts"]["properties"]
        for key, units in parts["s1"].items():
            self.assertEqual(set(tree[key]["required"]), {u["paragraph_id"] for u in units})
            for unit in units:
                fields = tree[key]["properties"][unit["paragraph_id"]]["properties"]["spans"]["properties"][unit["id"]]
                self.assertEqual(set(fields["properties"]), {"action", "text"})
            foreign = parts["s1"]["p1" if key == "p0" else "p0"]
            for unit in foreign:
                self.assertNotIn(unit["id"], json.dumps(tree[key]))
        for field in ('"source_id"', '"section_id"', '"part"', '"paragraph_ids"'):
            self.assertNotIn(field, json.dumps(schema))

    def test_deleting_a_fixed_span_drops_its_citation_without_touching_other_prose(self):
        packet, previous, _, _, _ = setup_patch()
        packet["subsection_assignments"]["p0"]["evidence_ids"] = ["F1", "F2"]
        previous["s1"]["parts"]["p0"] = previous["s1"]["parts"]["p0"].replace("수정 대상이다. [근거:F1]", "수정 대상이다. [근거:F2]")
        parts, origins, _ = editorial_sources(previous, {"s1": packet})
        raw = keep_slots(parts)
        span(raw, "p0", parts["s1"]["p0"][1]).update(action="delete")
        result, trace = apply_editorial_patch(raw, previous, {"s1": packet}, parts, origins)
        self.assertNotIn("F2", result["s1"]["parts"]["p0"])
        self.assertEqual(trace["omitted_sources"][0]["origin"]["evidence_ids"], ["F2"])
        self.assertEqual(result["s1"]["parts"]["p1"], previous["s1"]["parts"]["p1"])

    def test_keep_preserves_exact_body_and_citations_even_when_model_echoes_unused_text(self):
        packet, previous, _, parts, origins = setup_patch()
        raw = keep_slots(parts)
        span(raw, "p0", parts["s1"]["p0"][0])["text"] = "유지 동작에서 이 필드는 적용하지 않는다."
        result, trace = apply_editorial_patch(raw, previous, {"s1": packet}, parts, origins)
        self.assertEqual(result, previous)
        self.assertIsNot(result, previous)
        self.assertTrue(all(not values for values in trace.values()))

    def test_wrong_slots_unknown_ids_and_old_range_format_are_rejected_atomically(self):
        packet, previous, _, parts, origins = setup_patch()
        valid = keep_slots(parts)
        units = parts["s1"]["p0"]
        def missing(raw):
            del raw["sections"]["s1"]["parts"]["p0"][units[0]["paragraph_id"]]
        def foreign(raw):
            slot = raw["sections"]["s1"]["parts"]["p0"][units[0]["paragraph_id"]]["spans"]
            slot[parts["s1"]["p1"][0]["id"]] = {"action": "replace", "text": "다른 소절이다."}
        def binding_field(raw):
            span(raw, "p0", units[0])["source_id"] = parts["s1"]["p1"][0]["id"]
        def empty_part(raw):
            for unit in parts["s1"]["p1"]:
                span(raw, "p1", unit).update(action="delete")
        def bad_text(raw):
            span(raw, "p0", units[0]).update(action="replace", text="확정했다. [근거:F2]")
        for mutate in (missing, foreign, binding_field, empty_part, bad_text):
            raw = copy.deepcopy(valid)
            mutate(raw)
            snapshot = copy.deepcopy(previous)
            with self.subTest(case=mutate.__name__), self.assertRaises(ValueError):
                apply_editorial_patch(raw, previous, {"s1": packet}, parts, origins)
            self.assertEqual(previous, snapshot)
        with self.assertRaisesRegex(ValueError, "고정 출력 칸"):
            apply_editorial_patch({"edits": []}, previous, {"s1": packet}, parts, origins)

    def test_same_part_spans_keep_their_own_citations_after_merge(self):
        packet, previous, _, _, _ = setup_patch()
        packet["subsection_assignments"]["p0"]["evidence_ids"] = ["F1", "F2"]
        previous["s1"]["parts"]["p0"] = "관측 A다. [근거:F1] 관측 B다. [근거:F2]"
        parts, origins, _ = editorial_sources(previous, {"s1": packet})
        raw = keep_slots(parts)
        a, b = parts["s1"]["p0"]
        span(raw, "p0", a).update(action="replace", text="A의 범위다.")
        span(raw, "p0", b).update(action="replace", text="B의 범위다.")
        result, _ = apply_editorial_patch(raw, previous, {"s1": packet}, parts, origins)
        self.assertEqual(result["s1"]["parts"]["p0"], "A의 범위다. [근거:F1] B의 범위다. [근거:F2]")

    def test_join_previous_never_joins_across_subsection_boundary(self):
        packet, previous, _, parts, origins = setup_patch()
        raw = keep_slots(parts)
        unit = parts["s1"]["p1"][0]
        raw["sections"]["s1"]["parts"]["p1"][unit["paragraph_id"]]["join_previous"] = True
        result, trace = apply_editorial_patch(raw, previous, {"s1": packet}, parts, origins)
        self.assertEqual(result, previous)
        self.assertFalse(trace["paragraph_joins"])

    def test_format_repair_keeps_full_context_and_never_applies_invalid_first_response(self):
        packet, previous, report, parts, _ = setup_patch()
        calls = []
        def client(system, body, schema, path):
            calls.append(body)
            self.assertEqual(body["source_parts"], parts)
            raw = keep_slots(parts)
            unit = parts["s1"]["p0"][0]
            span(raw, "p0", unit).update(action="replace", text="보완한 연결 문장이다.")
            if len(calls) == 1:
                span(raw, "p0", unit)["source_id"] = "unknown"
            return raw
        with TemporaryDirectory() as tmp:
            result = revise_editorial(PlannedPaper(tmp, client), Path(tmp), "edit", "section", previous, {"s1": packet}, report)
        self.assertEqual(len(calls), 2)
        self.assertIn("invalid_response", calls[1])
        self.assertTrue(result["s1"]["parts"]["p0"].startswith("보완한 연결 문장이다."))

    def test_full_context_is_not_silently_truncated_when_over_budget(self):
        packet, previous, report, _, _ = setup_patch()
        calls = []
        with TemporaryDirectory() as tmp, patch.dict("os.environ", {"PAPER_REQUEST_MAX_BYTES": "4000"}):
            with self.assertRaisesRegex(DraftingBudgetError, "전체 본문 문맥"):
                revise_editorial(PlannedPaper(tmp, lambda *a: calls.append(a)), Path(tmp), "edit", "section", previous, {"s1": packet}, report)
        self.assertFalse(calls)

    def test_cache_is_bound_to_citation_snapshot_and_does_not_reuse_old_range_policy(self):
        packet, previous, report, _, _ = setup_patch()
        packet["subsection_assignments"]["p0"]["evidence_ids"] = ["F1", "F2"]
        calls = []
        def client(system, body, schema, path):
            calls.append((body, path.name))
            raw = keep_slots(body["source_parts"])
            span(raw, "p0", body["source_parts"]["s1"]["p0"][0]).update(action="replace", text="보완한 연결 문장이다.")
            return raw
        with TemporaryDirectory() as tmp:
            engine = PlannedPaper(tmp, client)
            first = revise_editorial(engine, Path(tmp), "generate-2", "section", previous, {"s1": packet}, report)
            newer = copy.deepcopy(previous)
            newer["s1"]["parts"]["p0"] = newer["s1"]["parts"]["p0"].replace("F1", "F2")
            second = revise_editorial(engine, Path(tmp), "generate-2", "section", newer, {"s1": packet}, report)
            revise_editorial(engine, Path(tmp), "generate-2", "section", newer, {"s1": packet}, report)
        self.assertEqual(len(calls), 2)
        self.assertNotEqual(calls[0][0]["base_fingerprint"], calls[1][0]["base_fingerprint"])
        self.assertTrue(all("editorial-fixed-slots-v1" in path for _, path in calls))
        self.assertIn("[근거:F1]", first["s1"]["parts"]["p0"])
        self.assertIn("[근거:F2]", second["s1"]["parts"]["p0"])

    def test_duplicate_paragraph_text_is_updated_by_fixed_original_position(self):
        packet, previous, _, _, _ = setup_patch()
        same = "같은 문단이다. [근거:F1]"
        previous["s1"]["parts"]["p0"] = same + "\n\n" + same
        parts, origins, _ = editorial_sources(previous, {"s1": packet})
        raw = keep_slots(parts)
        span(raw, "p0", parts["s1"]["p0"][1]).update(action="replace", text="두 번째 문단만 보완했다.")
        result, _ = apply_editorial_patch(raw, previous, {"s1": packet}, parts, origins)
        self.assertEqual(result["s1"]["parts"]["p0"], same + "\n\n두 번째 문단만 보완했다. [근거:F1]")

    def test_runtime_rechecks_the_complete_assembled_section_after_fixed_slot_edit(self):
        client = Client()
        client.reject_once = "section-s1"
        rechecks = []
        def response(system, body, schema, path):
            if body.get("review_scope") == "previous_findings_only":
                rechecks.append(copy.deepcopy(body))
            return client(system, body, schema, path)
        with TemporaryDirectory() as tmp:
            result = PlannedPaper(tmp, response).run(research())
        self.assertTrue(result["review"]["approved"])
        self.assertEqual(len(rechecks), 1)
        rows = rechecks[0]["draft_paragraphs"]
        self.assertEqual(len(rows), 2)
        self.assertTrue(all("연결을 보완했다" in row["text"] for row in rows.values()))
        self.assertEqual(sum(s == "subsection-s1-p0" and k == "review" for s, k, _ in client.events), 1)


if __name__ == "__main__":
    unittest.main()
