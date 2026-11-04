"""Reviewed subsection writers, section editors, and a mandatory paper editor."""

import copy
import json
from pathlib import Path

from document_parse import write_json
from paper_plan import object_schema
from review_response import checked_review
from bounded_drafting import generate_bounded
from bounded_review import review_bounded, SIMPLE_REVIEW
from draft_prose import render_parts
from draft_diagnostics import save_review_diagnostics
from editorial_review import POLICY as EDITORIAL_POLICY, checked_editorial_review, review_editorial

VERSION = "hierarchical-drafting-v1"
LEAF = """현재 target_heading 소절 하나만 작성한다. parts.p0에 제목 없는 본문만 반환한다.
배정된 필수 항목·근거·사용자 결정의 범위를 지킨다. 다른 소절의 내용을 채우지 않는다."""
SECTION = """1차 편집자: 검토를 통과한 child_parts를 계획의 순서로 엮어 장 하나를 편집한다.
소절 사이의 중복·용어·논리 연결을 정리하고 각 소절의 필수 내용과 근거 ID를 유지한다.
subsection_assignments의 소절별 근거 범위를 지킨다. 새로운 사실·수치·실험을 추가하지 않는다.
parts의 원래 칸을 모두 유지하고 제목·표는 생성하지 않는다. 검토 지적이 있으면 해당 부분을 수정한다."""
PAPER = """2차 편집자: 검토를 통과한 장들을 전체 논문으로 엮는다.
서론의 목적·방법·결과·결론의 주장 범위, 장 사이 논리 연결, 용어·중복을 정리한다.
계획의 장·소절·필수 내용을 유지한다. section_packets의 소절별 근거 배정을 지킨다.
새로운 사실·수치·실험을 추가하지 않는다. 모든 근거 ID와 사용자 승인 범위를 유지한다.
sections 아래 각 장은 parts의 원래 칸에 제목 없는 본문만 반환한다. placeholder는 출력하지 않는다."""
HUMAN_SCOPE = "\nhuman_guidance의 제외·임시 승인 결정을 지킨다. accepted_limited의 missing_fields를 채우는 새 내용을 요구하거나 추가하지 말고 사용자 설명 범위만 반영한다."
SECTION += HUMAN_SCOPE
PAPER += HUMAN_SCOPE
REVIEW_FOCUS = {
    "subsection": "현재 소절만 검토한다. 배정된 근거의 원문·수치·조건, 필수 내용과 사용자 승인 범위를 대조한다. 다른 소절의 항목을 요구하지 않는다.",
    "section": "1차 편집 결과를 검토한다. 소절 사이 누락·중복·논리 연결과 용어, 각 소절의 근거 배정·필수 내용을 확인한다.",
    "paper": "2차 편집 결과를 검토한다. 서론–방법–결과–결론의 일관성, 장 사이 중복·용어·주장 범위와 근거·필수 내용을 확인한다.",
}
PROMPTS = [LEAF, SECTION, PAPER, REVIEW_FOCUS]
# Keep generation/checkpoint identities stable. The review policy is versioned
# in individual requests/reports, so changing it does not discard written prose.
REVIEW_FOCUS = {
    "subsection": "현재 소절의 본문과 실제 사용한 승인 근거의 대응·조건·한계·필수 내용만 검토한다. 근거 원문을 재검증하지 않는다.",
    "section": "소절 간 중복, 문단 연결, 설명 순서, 용어·문체의 일관성만 검토한다.",
    "paper": "절 간 중복, 전체 논리 흐름, 서론과 결론의 호응, 용어·문체의 통일성만 검토한다.",
}


def run_hierarchical(engine, folder, research, plan, contexts, catalog, progress=None):
    from planned_paper import (GROUNDING, WRITER, REVIEWER, REVIEWER_CACHE_IDENTITY, fingerprint, parts_schema,
        clean_part, compose_parts, validate_body, index_paragraphs, review_schema)
    from paper_context import part_context

    folder = Path(folder)
    stages = []
    by_id = {s["id"]: s for s in plan["sections"]}
    total = sum(len(contexts["subsections"][key]) + 1 for key in plan["generation_order"]) + 1

    def scoped_plan(section):
        return {**copy.deepcopy(plan), "sections": [copy.deepcopy(section)],
                "generation_order": [section["id"]]}

    def scoped_research(packets):
        ids = {f["id"] for p in packets.values() for f in p["facts"]}
        table_ids = {t["id"] for p in packets.values() for t in p["tables"]}
        return {**copy.deepcopy(research),
                "facts": [copy.deepcopy(f) for f in research["facts"] if f["id"] in ids],
                "tables": [copy.deepcopy(t) for t in research["tables"] if t["id"] in table_ids]}

    def normalize(value, packets):
        if not isinstance(value, dict) or set(value) != set(packets):
            raise ValueError("편집 결과에 계획의 장이 누락·추가됐습니다.")
        normalized, bodies = {}, {}
        for sid, packet in packets.items():
            rendered = render_parts(value[sid], packet)
            # Validate every part's allocation even after section/paper editing.
            body = compose_parts(rendered, packet)
            parts = {}
            # Iterate schema order, never provider object order.
            for index, key in enumerate(parts_schema(packet)["properties"]["parts"]["properties"]):
                scoped = part_context(packet, key) if "subsection_assignments" in packet else packet
                parts[key] = validate_body(clean_part(rendered["parts"][key], packet, index),
                                           {**scoped, "subsection_headings": []})
            normalized[sid] = {"parts": parts}
            bodies[sid] = body
        return normalized, bodies

    def stage(name, level, packets, review_plan, system, inputs, single=False, children_reviews=None):
        children_reviews = children_reviews or {}
        local_research = scoped_research(packets)
        local_catalog = {g["id"]: g for p in packets.values() for g in p["reference_guides"]}
        identity = fingerprint({"version": VERSION, "system": system, "reviewer": REVIEWER_CACHE_IDENTITY,
            "focus": PROMPTS[-1][level], "inputs": inputs, "packets": packets,
            "plan": review_plan, "research": local_research, "catalog": local_catalog})
        root = folder / "workflow" / name
        approved_path = root / "approved.json"
        label = {"subsection": "소절 작성", "section": "장별 1차 편집", "paper": "전체 2차 편집"}[level]
        heading = inputs.get("target_heading") or inputs.get("section_plan", {}).get("title", "전체 논문")
        heading = heading.lstrip("# ")
        revalidation_path = root / "checkpoint-revalidation.json"
        reviews, feedback = [], None

        def review_candidate(value, bodies, attempt):
            if level != "subsection":
                return review_editorial(engine, root, f"review-{attempt}", level, review_plan, bodies, children_reviews)
            paragraphs = index_paragraphs(bodies)
            return review_bounded(engine, root, f"review-{attempt}", SIMPLE_REVIEW + "\n" + REVIEW_FOCUS[level],
                {"research": local_research, "plan": review_plan, "draft_paragraphs": paragraphs,
                 "reference_guides": local_catalog, "workflow_stage": level},
                review_schema(review_plan, paragraphs), review_plan, bodies)

        def record():
            stages.append({"id": name, "level": level, "approved": True,
                           "input_fingerprint": identity, "review_path": str(root / "reviews.json")})
            write_json(folder / "workflow.json", {"version": VERSION, "stages": stages})
            if progress:
                progress(20 + int(65 * len(stages) / total), f"{label} 검토 완료 · {heading}")

        def content_feedback(value, report):
            if level != "subsection":
                return {"previous_sections": value, "review": {**report, "checks": []},
                        "content_repair_instruction": "편집 지적의 중복·연결·문체 문제만 수정한다. 승인 근거·연구 주장은 재심사하거나 새로 추가하지 않는다."}
            facts = {f["id"]: f for f in local_research["facts"]}
            gaps = []
            for check in report.get("checks", []):
                missing = check.get("missing_section_evidence_ids", list(dict.fromkeys(
                    check.get("missing_body_evidence_ids", []) + check.get("missing_review_evidence_ids", []))))
                for key in missing:
                    fact = facts[key]
                    gaps.append({"item_id": check["item_id"], "evidence_id": key,
                                 **{field: copy.deepcopy(fact[field]) for field in ("statement", "limits", "writing_role", "claim_status") if field in fact}})
            return {"previous_sections": value, "review": report, "evidence_link_gaps": gaps,
                    "content_repair_instruction": "검토의 원래 지적을 모두 반영한다. evidence_link_gaps의 내용이 이미 본문에 있다면 "
                    "그 내용을 실제로 뒷받침하는 ID를 해당 문단의 evidence_ids에 연결한다. 본문에 없는 내용에 ID만 붙이지 않는다."}

        saved = None
        if approved_path.is_file():
            saved = json.loads(approved_path.read_text(encoding="utf-8"))
        elif revalidation_path.is_file():
            previous = json.loads(revalidation_path.read_text(encoding="utf-8"))
            if previous.get("current_input_fingerprint") == identity and previous.get("status") != "resolved":
                digest = previous.get("checkpoint_sha256")
                if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                    raise ValueError(f"{name}: 저장된 작성 단계의 재검증 기록이 변경됐습니다.")
                saved = json.loads((root / "checkpoint-history" / f"approved-{digest}.json").read_text(encoding="utf-8"))
                if saved.get("sha256") != digest:
                    raise ValueError(f"{name}: 보존된 작성 단계의 식별자가 변경됐습니다.")
        if saved is not None:
            payload = saved["value"]
            if saved["sha256"] != fingerprint(payload):
                raise ValueError(f"{name}: 저장된 작성 단계의 입력·검토 기록이 변경됐습니다.")
            reason, report = "input_changed", None
            if payload["input_fingerprint"] == identity:
                try:
                    value, bodies = normalize(payload["sections"], packets)
                    if level == "subsection":
                        report = checked_review(payload["raw_review"], review_plan, bodies)
                    elif payload["raw_review"].get("review_policy") == EDITORIAL_POLICY:
                        report = checked_editorial_review(payload["raw_review"], review_plan, bodies, children_reviews)
                    else:
                        # An old mixed review must not be used as an editorial
                        # verdict, but the already-written body is reusable.
                        raw, report = review_candidate(value, bodies, "policy-migration")
                        write_json(root / "checkpoint-history" / f"approved-{saved['sha256']}.json", saved)
                        payload = {**payload, "raw_review": raw, "reviews": payload["reviews"] + [report]}
                        saved = {"sha256": fingerprint(payload), "value": payload}
                        if report["approved"]:
                            write_json(approved_path, saved)
                except (ValueError, KeyError, TypeError) as error:
                    reason = "validation_changed"
                    response = payload["sections"]
                    feedback = {"validation_error": str(error),
                                "previous_response": next(iter(response.values())) if single else {"sections": response},
                                "repair_instruction": "보존된 본문을 현재 소절의 문단·근거 연결 규칙에 맞춰 수정한다. 근거가 없는 주장은 삭제·축소한다."}
                else:
                    if report["approved"]:
                        if not approved_path.is_file():
                            write_json(approved_path, saved)
                        if revalidation_path.is_file():
                            revalidation = json.loads(revalidation_path.read_text(encoding="utf-8"))
                            revalidation.update(status="resolved", approved_checkpoint_sha256=saved["sha256"])
                            write_json(revalidation_path, revalidation)
                        record()
                        return value, bodies, report, payload["reviews"]
                    reason = "review_rejected"
                    feedback = content_feedback(value, report)
            # Preserve the previous approval and its history. Changed validation
            # resumes this stage with concrete feedback; changed child inputs
            # regenerate their parent. Integrity mismatches above still stop.
            archive = root / "checkpoint-history" / f"approved-{saved['sha256']}.json"
            write_json(archive, saved)
            revalidation = {"stage": name, "status": "requires_revision", "reason": reason,
                            "checkpoint_sha256": saved["sha256"], "current_input_fingerprint": identity,
                            "stored_input_fingerprint": payload["input_fingerprint"], "review": report}
            write_json(revalidation_path, revalidation)
            if approved_path.is_file():
                approved_path.unlink()
            write_json(folder / "workflow.json", {"version": VERSION, "stages": stages})
            reviews.append({"event": "checkpoint_revalidation", **revalidation, "feedback": feedback})
            write_json(root / "reviews.json", reviews)
            if progress:
                progress(20 + int(65 * len(stages) / total), f"{label} 재개 · {heading} · 기존 승인 재검증 후 수정")

        schema = (parts_schema(next(iter(packets.values()))) if single else
                  object_schema({"sections": object_schema({key: parts_schema(p) for key, p in packets.items()})}))
        last_validation_error, invalid_responses = None, set()
        sid = next(iter(packets))
        attempt, format_attempt = 0, 0
        while attempt < 3:
            request = {**inputs, "workflow_stage": level}
            if feedback:
                request["revision"] = feedback
            if progress:
                suffix = f" · 형식 보정 {format_attempt}차" if format_attempt else ""
                progress(20 + int(65 * len(stages) / total), f"{label} 중 · {heading} · {attempt + 1}차{suffix}")
            request_name = f"generate-{attempt}" + (f"-format-repair-{format_attempt}" if format_attempt else "")
            result = generate_bounded(engine, root, request_name, GROUNDING + "\n" + system,
                                      request, schema, packets, single)
            candidate = {sid: result} if single else (result.get("sections") if isinstance(result, dict) else None)
            try:
                value, bodies = normalize(candidate, packets)
            except (ValueError, KeyError, TypeError) as error:
                last_validation_error = str(error)
                feedback = {**(feedback or {}), "validation_error": str(error), "previous_response": result,
                            "repair_instruction": "각 parts 값을 text와 evidence_ids의 문단 배열로 반환한다. "
                            "오류가 난 문단의 근거 ID를 배정 범위에서 직접 선택하고, 근거가 없는 주장은 삭제·축소한다. "
                            "evidence_ids를 비우거나 이전 실패 응답을 그대로 복사하지 않는다."}
                reviews.append({"attempt": attempt, "format_attempt": format_attempt, "failure_type": "generation_validation", **feedback})
                write_json(root / "reviews.json", reviews)
                write_json(root / "candidate.json", {"sections": candidate, "validation_error": str(error)})
                failure_id = fingerprint({"response": result, "error": str(error)})
                if failure_id in invalid_responses or format_attempt >= 1:
                    break
                invalid_responses.add(failure_id)
                format_attempt += 1
                continue
            last_validation_error = None
            format_attempt = 0
            invalid_responses.clear()
            paragraphs = index_paragraphs(bodies)
            write_json(root / "candidate.json", {"sections": value, "status": "awaiting_review"})
            raw_review, report = review_candidate(value, bodies, attempt)
            reviews.append(report)
            save_review_diagnostics(root, f"review-{attempt}", name, review_plan, local_research, bodies, report)
            write_json(root / "reviews.json", reviews)
            write_json(root / "candidate.json", {"sections": value, "review": report})
            unresolved = [i["reason"] for i in report["issues"]
                          if i["severity"] == "error" and i.get("failure_owner") == "reviewer"]
            if unresolved:
                raise ValueError(f"{name} 검토 응답 확인 보류: {unresolved[0][:300]} "
                                 f"본문은 재작성하지 않고 보존했습니다. 상세: {root / 'failure-details.md'}")
            if report["approved"]:
                payload = {"input_fingerprint": identity, "sections": value,
                           "raw_review": raw_review, "reviews": reviews}
                write_json(approved_path, {"sha256": fingerprint(payload), "value": payload})
                if revalidation_path.is_file():
                    revalidation = json.loads(revalidation_path.read_text(encoding="utf-8"))
                    revalidation.update(status="resolved", approved_checkpoint_sha256=fingerprint(payload))
                    write_json(revalidation_path, revalidation)
                record()
                return value, bodies, report, reviews
            feedback = content_feedback(value, report)
            attempt += 1
        if last_validation_error is not None:
            raise ValueError(f"{name} 본문 형식·근거 연결 검증 미통과: {last_validation_error} 후보와 지적을 {root}에 저장했습니다.")
        reasons = [issue["reason"] for issue in feedback.get("review", {}).get("issues", []) if issue["severity"] == "error"]
        detail = " 원인: " + "; ".join(reason[:240] for reason in reasons[:2]) if reasons else ""
        checks = feedback.get("review", {}).get("checks", [])
        missing_count = len({key for c in checks for key in c.get("missing_section_evidence_ids", c.get("missing_body_evidence_ids", []))})
        selection_count = len({key for c in checks for key in c.get("unselected_cited_evidence_ids", [])})
        counts = (f" 본문 전체 인용 누락 {missing_count}개; 검토 문단 선택 누락 {selection_count}개."
                  if missing_count or selection_count else "")
        failure_label = "근거·필수 내용 검토 미통과" if level == "subsection" else "편집 검토 미통과"
        raise ValueError(f"{name} {failure_label}.{detail}{counts} "
                         f"근거별 원문 위치·임시 승인 여부·검토 사유: {root / 'failure-details.md'}. 후보와 지적을 {root}에 저장했습니다.")

    assembled, drafts, section_reviews = {}, {}, {}
    for sid in plan["generation_order"]:
        packet = contexts["sections"][sid]
        children, child_reviews = {}, {}
        for key, child_packet in contexts["subsections"][sid].items():
            value, _, child_review, _ = stage(f"subsection-{sid}-{key}", "subsection", {sid: child_packet},
                scoped_plan(child_packet["section_plan"]), WRITER + "\n" + LEAF,
                child_packet, single=True)
            children[key] = value[sid]["parts"]["p0"]
            child_reviews[key] = child_review
        drafts[sid] = compose_parts({"parts": children}, packet)
        value, _, section_review, _ = stage(f"section-{sid}", "section", {sid: packet}, scoped_plan(by_id[sid]),
            SECTION, {**packet, "child_parts": children}, single=True, children_reviews=child_reviews)
        assembled.update(value)
        section_reviews[sid] = section_review

    packets = contexts["sections"]
    value, bodies, report, history = stage("paper", "paper", packets, plan, PAPER,
        {"research": scoped_research(packets), "plan": plan, "sections": assembled,
         "section_packets": packets, "reference_guides": catalog}, children_reviews=section_reviews)
    return {"sections": bodies, "drafts": drafts, "review": report,
            "review_history": history, "workflow": {"version": VERSION, "stages": stages}}
