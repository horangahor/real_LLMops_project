"""Prepare or generate one isolated chapter; never update the application's latest draft."""

import argparse
import json
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE))

from config import SOLAR_MODEL
from document_parse import write_json
from paper_context import build_contexts
from paper_plan import normalize_research, reference_catalog
from planned_paper import (GROUNDING, WRITER, REVIEWER, PlannedPaper, clean_part, compose_parts,
                          fingerprint, index_paragraphs, materialize_review, parts_schema,
                          review_schema, validate_body, validate_review)


def check_candidate(value, packet, parts):
    checks = {"chapter_format_and_ids": "pending", "part_format_and_ids": {}}
    raw = value.get("parts", {})
    raw = raw if isinstance(raw, dict) else {}
    try:
        body = compose_parts(value, packet)
        checks["chapter_format_and_ids"] = "pass"
    except ValueError as error:
        # Diagnostic candidate only: preserve the failed text, never count it as valid.
        body = "\n\n".join(text for text in raw.values() if isinstance(text, str))
        checks["chapter_format_and_ids"] = str(error)
    for index, (key, part) in enumerate(parts.items()):
        try:
            validate_body(clean_part(raw.get(key), packet, index), part)
            checks["part_format_and_ids"][key] = "pass"
        except ValueError as error:
            checks["part_format_and_ids"][key] = str(error)
    return body, checks


def candidate_accepted(checks, report):
    return (checks["chapter_format_and_ids"] == "pass"
            and all(value == "pass" for value in checks["part_format_and_ids"].values())
            and "review_contract_error" not in report and report.get("approved") is True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--generate", action="store_true", help="Send selected evidence text and writing guides to Upstage Solar.")
    mode.add_argument("--replay", action="store_true", help="Re-evaluate saved responses only; fail if any exact-input cache is missing. No API calls.")
    args = parser.parse_args()
    snapshot = BASE / "evaluation/extraction/v3/current/evidence.json"
    prediction = json.loads(snapshot.read_text(encoding="utf-8"))
    wanted = ["P0058F0006", "P0058F0007", "P0058F0008", "P0058F0009"]
    selected = {f["id"]: f for f in prediction["items"] if f["id"] in wanted}
    if set(selected) != set(wanted) or any(key not in prediction["writing_fact_ids"] or selected[key].get("numeric_issues")
                                          or selected[key].get("support") != "supported" for key in wanted):
        raise ValueError("시험에 사용할 근거가 없거나 작성용 후보 검사를 통과하지 못했습니다.")
    profiles = json.loads((BASE / "paper_structure_analysis.json").read_text(encoding="utf-8"))
    golden = [p for p in profiles if p.get("source_sha256") == "18d91e44744993d41db1fdd401fa0aadd2f7091d9fa1ebb84e4fbbc5bd5887e8"]
    if len(golden) != 1:
        raise ValueError("구조 참고용 NPU 프로파일 선택이 모호합니다.")
    catalog = reference_catalog({"profiles": golden})
    guide_id = "ref1_evaluation"
    catalog = {guide_id: catalog[guide_id]}
    gid = lambda number: f"{guide_id}_required_{number}"
    section = {
        "id": "results_pilot", "title": "계산 구간별 성능 비교와 해석", "role": "evaluation", "status": "write",
        "purpose": "58쪽의 sparse.py/CUDA 비교를 사용해 측정 범위별 결과와 해석 한계를 서술한다.",
        "subsections": ["bound 계산 시간의 비교", "측정 범위에 따른 가속비", "결과 해석의 범위와 한계"],
        "evidence_ids": wanted, "reference_ids": [guide_id], "table_ids": [], "depends_on": [],
        "reference_adaptation": "골든 논문의 질문별 답 제시, 측정 범위 구분, 비교와 한계 서술 방식만 적용한다. NPU 장치·벤더·정확도 표·실험 개수를 이전하지 않는다.",
        "required_items": [
            {"id": "bound_times", "subsection_index": 0, "description": "n=5와 평균 1회 조건에서 forward/backward의 sparse.py와 CUDA 시간 및 bound 가속비를 구분한다.",
             "evidence_ids": wanted[:3], "guideline_ids": [gid(1)]},
            {"id": "combined_scope", "subsection_index": 1, "description": "추론+bound+검증 범위의 forward/backward 가속비와 단축률을 해당 범위로 한정해 제시한다.",
             "evidence_ids": [wanted[3]], "guideline_ids": [gid(6)]},
            {"id": "scope_comparison", "subsection_index": 1, "description": "bound만의 가속비와 추론+bound+검증 가속비를 혼동하지 않고 비교한다.",
             "evidence_ids": wanted[2:], "guideline_ids": [gid(6)]},
            {"id": "interpretation_limits", "subsection_index": 2, "description": "기록된 비교 범위의 결과만 해석하고 미확인 환경·정확성·실시간성·단일 최적화 인과를 성과로 추가하지 않는다.",
             "evidence_ids": wanted, "guideline_ids": [gid(7)]}
        ]}
    plan = {"title": "CUDA 연구 결과 장 시험본", "sections": [section], "generation_order": [section["id"]],
            "rationale": "확인된 한 표 범위의 독립 장 생성 시험. 논문 전체의 계획이 아니다.", "unresolved": []}
    research = normalize_research({"title": plan["title"], "facts": [selected[key] for key in wanted],
                                   "source": prediction["source"], "provenance": "selected_prediction_facts_for_isolated_pilot"})
    contexts = build_contexts(plan, research, catalog)
    packet = contexts["sections"][section["id"]]
    identity = fingerprint({"packet": packet, "writer": WRITER, "reviewer": REVIEWER, "model": SOLAR_MODEL})
    folder = BASE / "draft_history/writing-pilot" / identity[:20]
    write_json(folder / "plan.json", plan)
    write_json(folder / "research.json", research)
    write_json(folder / "writer-input.json", packet)
    write_json(folder / "manifest.json", {"scope": "isolated candidate; does not bypass production drafting gate",
        "source_snapshot": str(snapshot.relative_to(BASE)), "source_sha256": prediction["source"]["sha256"],
        "full_source_ready_for_drafting": prediction["completion"]["ready_for_drafting"],
        "selected_evidence_ids": wanted, "golden_source_sha256": golden[0]["source_sha256"],
        "model": SOLAR_MODEL, "input_fingerprint": identity,
        "api_destination": "https://api.upstage.ai/v1/chat/completions",
        "api_payload_scope": "four selected evidence records with source excerpts and one reusable writing guide; no PDF upload",
        "plan_authorship": "code-authored pilot scope; not a model-generated full-paper plan"})
    print("Prepared:", folder, flush=True)
    if not (args.generate or args.replay):
        print("No external API calls. Pass --generate to run this isolated chapter pilot.")
        return
    engine = PlannedPaper(BASE)
    started = time.monotonic()
    value = engine.call(folder, "chapter-write", GROUNDING + WRITER, packet, parts_schema(packet), cache_only=args.replay)
    body, checks = check_candidate(value, packet, contexts["subsections"][section["id"]])
    write_json(folder / "code-checks.json", checks)
    (folder / "chapter-candidate.md").write_text("# 결과 장 시험본\n\n" + body + "\n", encoding="utf-8")
    paragraphs = index_paragraphs({section["id"]: body})
    review_packet = {"research": research, "plan": plan, "draft_paragraphs": paragraphs, "reference_guides": catalog}
    write_json(folder / "review-input.json", review_packet)
    report = engine.call(folder, "chapter-review", GROUNDING + REVIEWER, review_packet,
                         review_schema(plan, paragraphs), inference_settings={"reasoning_effort": "medium"}, cache_only=args.replay)
    try:
        report = validate_review(materialize_review(report, plan, paragraphs), plan, {section["id"]: body})
    except ValueError as error:
        report = {"review_contract_error": str(error), "raw_review": report, "approved": False}
    write_json(folder / "review.json", report)
    previous = json.loads((folder / "run-summary.json").read_text(encoding="utf-8")) if (folder / "run-summary.json").exists() else {}
    elapsed = round(time.monotonic() - started, 2)
    original_elapsed = previous.get("original_generation_and_review_elapsed_seconds", previous.get("elapsed_seconds_including_cache_lookup")) if args.replay else elapsed
    write_json(folder / "run-summary.json", {"elapsed_seconds_including_cache_lookup": elapsed,
        "original_generation_and_review_elapsed_seconds": original_elapsed,
        "execution_mode": "cache_only_replay" if args.replay else "generation_or_cache",
        "scope": "one chapter; no automatic rewrite or application latest-draft update", "code_checks": checks,
        "review_contract_valid": "review_contract_error" not in report, "model_review_approved": report.get("approved", False),
        "accepted": candidate_accepted(checks, report),
        "diagnostic_review_despite_code_failure": checks["chapter_format_and_ids"] != "pass"})
    print("Saved candidate and review:", folder, flush=True)


if __name__ == "__main__":
    main()
