import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from comprehensive_policy import (apply_comprehensive_policy, apply_numeric_policy, classify_open_items,
                                  decimal_comma_suspects, is_non_research)
from research_extract_v3 import _refresh_research_from_review, accept_gate_item, load_saved_evidence

BREAKDOWN = ("total elapsed: 630.94s Phase Timing Breakdown (all eps X all data) "
             "infer : 131,248s (20.8%) bound : 497.107s (78.8%) certify : 1,613s (0.3%)")


def fact(fact_id, element_id, statement="연구 사실", measurements=(), **extra):
    value = {"id": fact_id, "statement": statement, "limits": "", "kind": "result", "claim_status": "observed",
             "source_origin": "measurement_log", "conditions": [], "observations": [], "parameters": [],
             "measurements": list(measurements), "rejected_measurements": [], "numeric_issues": [],
             "sources": [{"element_id": element_id, "page": int(element_id.split(":")[0][1:]), "quote": ""}],
             "support": "supported", "support_note": "", "attribution_preserved": True,
             "verification_conflicts": [], "verification_missing_support": [], "evidence_limitations": [],
             "writing_role": "research_fact"}
    value.update(extra)
    return value


def element(key, text, category="paragraph"):
    return {"element_id": key, "page": int(key.split(":")[0][1:]), "text": text, "category": category}


def extraction(items, ledger, unresolved, elements):
    value = {"title": "연구", "source": {"sha256": "x"}, "items": items,
             "writing_fact_ids": [item["id"] for item in items], "structured_tables": [],
             "element_ledger": ledger, "human_fact_reviews": [], "human_evidence_exclusions": [],
             "human_duplicate_decisions": [],
             "completion": {"pages_reviewed": 1, "source_pages": 1, "elements_reviewed": len(elements),
                            "source_elements": len(elements), "unresolved_source_items": unresolved,
                            "unreviewed_elements": [], "quarantined_fact_ids": [], "ready_for_drafting": False}}
    _refresh_research_from_review(value)
    return value


def unresolved(key, note):
    return {"state": "unresolved", "fact_ids": [], "note": note}


class DecimalCommaTest(unittest.TestCase):
    def test_total_and_share_expose_decimal_comma(self):
        suspects = {row["raw"]: row for row in decimal_comma_suspects(BREAKDOWN)}
        self.assertEqual(set(suspects), {"131,248s", "1,613s"})
        self.assertEqual(suspects["131,248s"]["decimal"], "131.248")
        self.assertEqual(len(suspects["131,248s"]["reasons"]), 2)

    def test_real_thousands_and_other_units_are_not_flagged(self):
        self.assertEqual(decimal_comma_suspects("total elapsed: 3000.0s infer : 1,500s (50.0%)"), [])
        self.assertEqual(decimal_comma_suspects("total elapsed: 806.54s 처리량 약 1,168 samples/s"), [])
        self.assertEqual(decimal_comma_suspects("infer : 131,248s (20.8%)"), [])

    def test_flag_excludes_fact_from_writing_until_review_and_is_idempotent(self):
        elements = {"p83:e638": element("p83:e638", BREAKDOWN, "figure")}
        wrong = fact("P0083F0001", "p83:e638", measurements=[
            {"metric": "infer", "value": "131248", "unit": "s", "condition": "all eps", "element_ids": ["p83:e638"]}])
        right = fact("P0083F0002", "p83:e638", measurements=[
            {"metric": "bound", "value": "497.107", "unit": "s", "condition": "all eps", "element_ids": ["p83:e638"]}])
        value = extraction([wrong, right], {}, [], elements)
        self.assertTrue(apply_comprehensive_policy(value, elements, refresh=_refresh_research_from_review))
        self.assertEqual(value["writing_fact_ids"], ["P0083F0002"])
        self.assertIn("131.248s일 가능성", value["items"][0]["numeric_issues"][0])
        self.assertEqual(value["items"][0]["measurements"][0]["value"], "131248")
        self.assertEqual([row["fact_id"] for row in value["comprehensive_policy"]["numeric_flags"]], ["P0083F0001"])
        self.assertFalse(apply_comprehensive_policy(value, elements, refresh=_refresh_research_from_review))

    def test_human_reviewed_fact_is_not_reflagged(self):
        elements = {"p83:e638": element("p83:e638", BREAKDOWN, "figure")}
        wrong = fact("P0083F0001", "p83:e638", measurements=[
            {"metric": "infer", "value": "131248", "unit": "s", "condition": "all eps", "element_ids": ["p83:e638"]}])
        value = extraction([wrong], {}, [], elements)
        value["human_fact_reviews"] = [{"fact_id": "P0083F0001", "review_id": "r"}]
        self.assertEqual(apply_numeric_policy(value, elements), [])


class GateTest(unittest.TestCase):
    def setUp(self):
        self.elements = {
            "p1:e0": element("p1:e0", "= ====="),
            "p1:e1": element("p1:e1", "진 행 사항", "heading1"),
            "p1:e2": element("p1:e2", "1560s도 나왔단 말이지..", "heading1"),
            "p1:e3": element("p1:e3", "Output Dimension: 16"),
            "p1:e4": element("p1:e4", "my_lirpa 계산에는 NVIDIA가 제공하는 cuBLAS 라이브러리를 링크해 사용한다"),
            "p1:e5": element("p1:e5", "이제 forward 함수에서 DTOH하는 memcpy를 극단적으로 없앴다. 6 4ms 엄청 줄었다"),
            "p1:review:e0": element("p1:review:e0", "이제 forward 함수에서 DTOH하는 memcpy를 극단적으로 없앴다."),
            "p1:review:e1": element("p1:review:e1", "64ms 엄청 줄었다"),
            "p1:e6": element("p1:e6", "warm up은 효과가 있어 각 버전에서 50ms 정도 단축됨"),
        }
        self.items = [fact("P0001F0001", "p1:e4", statement="cuBLAS 라이브러리를 사용한다"),
                      fact("P0001F0002", "p1:e5", statement="forward에서 memcpy를 없앴다")]
        notes = {"p1:e0": "실제 구조화된 작성 근거 연결이 없습니다. 구분선",
                 "p1:e1": "제목",
                 "p1:e2": "반응 진술 미보존",
                 "p1:e3": "값 미보존",
                 "p1:e4": "원문 식별자 미보존: NVIDIA. 내용은 보존",
                 "p1:review:e0": "재판독본 귀속 누락",
                 "p1:review:e1": "64ms 관찰 미보존",
                 "p1:e6": "최종 원문 검사 응답 미완료: 모델이 완결된 JSON을 반환하지 못했습니다."}
        self.ledger = {key: unresolved(key, note) for key, note in notes.items()}
        self.ledger["p1:e4"]["fact_ids"] = ["P0001F0001"]
        self.ledger["p1:e5"] = {"state": "represented", "fact_ids": ["P0001F0002"], "note": ""}
        self.unresolved = [f"{key}: {note}" for key, note in notes.items()] + ["p1: 이미지0 판독 불가"]

    def categories(self, rows):
        return {row["item"].split(": ")[0]: row["category"] for row in rows}

    def test_blocking_and_warning_split(self):
        value = extraction(self.items, self.ledger, self.unresolved, self.elements)
        blocking, warnings = classify_open_items(value, self.elements)
        self.assertEqual(self.categories(blocking), {"p1:e2": "missing_content", "p1:e3": "missing_content",
                                                     "p1:review:e1": "missing_content", "p1:e6": "response_failure"})
        self.assertEqual(self.categories(warnings), {"p1:e0": "non_research", "p1:e1": "non_research",
                                                     "p1:e4": "acronym_only", "p1:review:e0": "reread_duplicate",
                                                     "p1": "unreadable_image"})

    def test_gate_opens_only_without_blocking_items(self):
        value = extraction(self.items, self.ledger, self.unresolved, self.elements)
        apply_comprehensive_policy(value, self.elements)
        self.assertFalse(value["completion"]["ready_for_drafting"])
        self.assertEqual(len(value["completion"]["blocking_source_items"]), 4)
        self.assertEqual(value["completion"]["unresolved_source_items"], self.unresolved)
        warning_only = [item for item in self.unresolved if item.split(":")[1] in (" 이미지0 판독 불가",)
                        or item.split(": ")[0] in ("p1:e0", "p1:e1", "p1:e4", "p1:review:e0")]
        value["completion"]["unresolved_source_items"] = warning_only
        value["completion"]["quarantined_fact_ids"] = ["P0001F0009"]
        apply_comprehensive_policy(value, self.elements)
        self.assertTrue(value["completion"]["ready_for_drafting"])
        self.assertIn("quarantined_fact", {row["category"] for row in value["completion"]["gate"]["warnings"]})

    def test_missing_source_archive_keeps_ledger_items_blocking(self):
        value = extraction(self.items, self.ledger, self.unresolved, self.elements)
        apply_comprehensive_policy(value, None)
        self.assertFalse(value["completion"]["ready_for_drafting"])
        self.assertEqual({row["category"] for row in value["completion"]["gate"]["blocking"]},
                         {"source_unavailable"})

    def test_non_research_rule(self):
        self.assertTrue(is_non_research(element("p1:e9", "그 래서")))
        self.assertTrue(is_non_research(element("p1:e9", "3. Pinned Memory는 언제 빛을 발하는가?", "heading1")))
        self.assertFalse(is_non_research(element("p1:e9", "2. 숫자로 보는 1 KB의 역설", "heading1")))
        self.assertFalse(is_non_research(element("p1:e9", "그러는 사이에 backward_only에 대한 결과가 나왔다")))


class IsolationTest(unittest.TestCase):
    def test_question_based_path_does_not_use_comprehensive_policy(self):
        root = Path(__file__).resolve().parents[1]
        for name in ("requirement_extraction.py", "requirement_intervention.py", "requirement_applicability.py"):
            text = (root / name).read_text(encoding="utf-8")
            self.assertNotIn("comprehensive_policy", text)
            self.assertNotIn("apply_policy", text)

    def test_load_saved_evidence_applies_policy_without_models(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            pdf = base / "research.pdf"
            pdf.write_bytes(b"%PDF-1.4 test")
            digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
            run = base / "draft_history/parse-api-v1/doc/research-evidence-v3/abc"
            run.mkdir(parents=True)
            elements = [element("p83:e638", BREAKDOWN, "figure"), element("p83:e639", "= =====")]
            (run / "source-archive.json").write_text(json.dumps({"elements": elements}), encoding="utf-8")
            wrong = fact("P0083F0001", "p83:e638", measurements=[
                {"metric": "infer", "value": "131248", "unit": "s", "condition": "all eps", "element_ids": ["p83:e638"]}])
            right = fact("P0083F0002", "p83:e638")
            value = extraction([wrong, right], {"p83:e639": unresolved("p83:e639", "구분선")},
                               ["p83:e639: 구분선"], {item["element_id"]: item for item in elements})
            value.update(source={"sha256": digest}, run_dir=str(run), source_archive_path=str(run / "source-archive.json"),
                         human_measurement_reviews=[], semantic_duplicate_review={"groups": []})
            (run / "evidence.json").write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
            loaded = load_saved_evidence(pdf, base)
            self.assertEqual(loaded["writing_fact_ids"], ["P0083F0002"])
            self.assertTrue(loaded["completion"]["ready_for_drafting"])
            saved = json.loads((run / "evidence.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["completion"]["gate"]["warnings"][0]["category"], "non_research")

    def test_person_can_accept_a_blocking_item_bound_to_its_text(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            pdf = base / "research.pdf"
            pdf.write_bytes(b"%PDF-1.4 accept")
            run = base / "draft_history/parse-api-v1/doc/research-evidence-v3/abc"
            run.mkdir(parents=True)
            elements = [element("p1:e0", "그러는 사이에 backward_only에 대한 결과가 나왔다"),
                        element("p1:e1", "warm up을 하면 각 버전에서 50ms 정도 단축됨")]
            (run / "source-archive.json").write_text(json.dumps({"elements": elements}), encoding="utf-8")
            items = ["p1:e0: 전환 문장 미보존", "p1:e1: 50ms 단축 미보존"]
            value = extraction([fact("P0001F0001", "p1:e1")],
                               {"p1:e0": unresolved("p1:e0", "전환 문장 미보존"),
                                "p1:e1": unresolved("p1:e1", "50ms 단축 미보존")},
                               items, {item["element_id"]: item for item in elements})
            value.update(source={"sha256": hashlib.sha256(pdf.read_bytes()).hexdigest()}, run_dir=str(run),
                         source_archive_path=str(run / "source-archive.json"), human_measurement_reviews=[],
                         semantic_duplicate_review={"groups": []})
            (run / "evidence.json").write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
            loaded = load_saved_evidence(pdf, base)
            self.assertEqual(loaded["completion"]["blocking_source_items"], items)
            with self.assertRaises(ValueError):
                accept_gate_item(loaded, items[0], " ")
            accept_gate_item(loaded, items[0], "초안에 필요 없는 전환 문장")
            self.assertEqual(loaded["completion"]["blocking_source_items"], [items[1]])
            accept_gate_item(loaded, items[1], "다른 페이지 근거로 대체")
            self.assertTrue(loaded["completion"]["ready_for_drafting"])
            reloaded = load_saved_evidence(pdf, base)
            self.assertTrue(reloaded["completion"]["ready_for_drafting"])
            accepted = [row for row in reloaded["completion"]["gate"]["warnings"] if row["category"] == "human_accepted"]
            self.assertEqual([row["reason"] for row in accepted], ["초안에 필요 없는 전환 문장", "다른 페이지 근거로 대체"])
            reloaded["completion"]["unresolved_source_items"] = ["p1:e1: 50ms 단축 미보존 (재추출 후 변경)"]
            apply_comprehensive_policy(reloaded, {item["element_id"]: item for item in elements})
            self.assertFalse(reloaded["completion"]["ready_for_drafting"])


if __name__ == "__main__":
    unittest.main()
